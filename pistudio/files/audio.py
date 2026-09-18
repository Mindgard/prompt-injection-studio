"""Audio prompt injection writers.

Writer functions for embedding prompt injection payloads into audio
waveforms using various techniques: TTS speech, low-volume whispers,
near-ultrasonic FSK encoding, LSB steganography, and spectrogram
watermarking.
"""

import contextlib
import logging
import os
import struct
import tempfile
import wave

from pistudio.files.audio_helpers import (
    DEFAULT_SAMPLE_RATE,
    DEFAULT_ULTRASONIC_BIT_DURATION,
    DEFAULT_ULTRASONIC_FREQ_0,
    DEFAULT_ULTRASONIC_FREQ_1,
    binary_to_text,
    decrypt_text,
    encrypt_text,
    read_wav_samples,
    text_to_binary,
    write_wav_samples,
)

logger = logging.getLogger(__name__)

# Re-export helpers under legacy private names for backward compatibility
_read_wav_samples = read_wav_samples
_write_wav_samples = write_wav_samples
_text_to_binary = text_to_binary
_binary_to_text = binary_to_text
_encrypt_text = encrypt_text
_decrypt_text = decrypt_text


# ── TTS Writers ────────────────────────────────────────────────────


def write_tts_wav(
    text: str,
    path: str,
    *,
    engine: str = "edge",
    voice: str | None = None,
    rate: str | None = None,
    volume: str | None = None,
) -> None:
    """Generate TTS speech of the prompt as a WAV file.

    Parameters
    ----------
    text:
        The prompt text to synthesize.
    path:
        Output path for the WAV file.
    engine:
        TTS engine name (edge, gtts, pyttsx3, openai).
    voice:
        Voice name/identifier (engine-specific).
    rate:
        Speech rate adjustment (e.g. "+10%", "-20%").
    volume:
        Volume adjustment (e.g. "+50%", "-25%").
    """
    from pistudio.files.audio_tts import get_engine

    tts = get_engine(engine)
    tts.synthesize_sync(text, path, voice=voice, rate=rate, volume=volume)


def write_tts_whisper(
    text: str,
    path: str,
    *,
    engine: str = "edge",
    voice: str | None = None,
    rate: str | None = None,
    carrier_path: str | None = None,
    whisper_volume: float = 0.05,
) -> None:
    """Generate low-volume TTS speech, optionally mixed with carrier audio.

    Parameters
    ----------
    text:
        The prompt text to synthesize.
    path:
        Output path for the WAV file.
    engine:
        TTS engine name.
    voice:
        Voice name/identifier.
    rate:
        Speech rate adjustment.
    carrier_path:
        Optional path to carrier audio to mix the whisper into.
    whisper_volume:
        Volume level for the whisper (0.0-1.0, default 0.05).
    """
    from pistudio.files.audio_tts import get_engine

    # Generate TTS to a temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = tmp.name

    try:
        tts = get_engine(engine)
        tts.synthesize_sync(text, tmp_wav, voice=voice, rate=rate)

        # Read the generated audio
        whisper_samples = read_wav_samples(tmp_wav)

        # Scale to whisper volume
        whisper_samples = [int(s * whisper_volume) for s in whisper_samples]

        if carrier_path and os.path.isfile(carrier_path):
            # Mix with carrier audio
            carrier_samples = read_wav_samples(carrier_path)

            # Extend whisper to match carrier length, or vice versa
            if len(whisper_samples) < len(carrier_samples):
                whisper_samples.extend([0] * (len(carrier_samples) - len(whisper_samples)))
            elif len(carrier_samples) < len(whisper_samples):
                carrier_samples.extend([0] * (len(whisper_samples) - len(carrier_samples)))

            # Mix: add samples and clip to prevent overflow
            mixed = []
            for w, c in zip(whisper_samples, carrier_samples, strict=False):
                val = w + c
                val = max(-32768, min(32767, val))
                mixed.append(val)

            write_wav_samples(path, mixed, DEFAULT_SAMPLE_RATE)
        else:
            # No carrier -- just write the whisper
            write_wav_samples(path, whisper_samples, DEFAULT_SAMPLE_RATE)

    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_wav)


def write_tts_concat(
    text: str,
    path: str,
    *,
    engine: str = "edge",
    voices: list[str] | None = None,
) -> None:
    """Generate TTS with multiple voices concatenated.

    Splits the text into segments and synthesizes each with a different
    voice, then concatenates them. Tests ASR robustness against varied
    speech characteristics.

    Parameters
    ----------
    text:
        The prompt text to synthesize.
    path:
        Output path for the WAV file.
    engine:
        TTS engine name.
    voices:
        List of voice names to cycle through. If None, uses default voices.
    """
    from pistudio.files.audio_tts import get_engine

    # Default voices for edge-tts (varied US English)
    if voices is None:
        voices = [
            "en-US-AriaNeural",
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-US-DavisNeural",
        ]

    # Split text into sentences or chunks
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    if not sentences:
        sentences = [text]

    tts = get_engine(engine)
    all_samples: list[int] = []

    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            continue

        voice = voices[i % len(voices)]

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name

        try:
            tts.synthesize_sync(sentence, tmp_wav, voice=voice)
            samples = read_wav_samples(tmp_wav)
            all_samples.extend(samples)
            # Add a small pause between segments
            all_samples.extend([0] * int(DEFAULT_SAMPLE_RATE * 0.2))
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_wav)

    write_wav_samples(path, all_samples, DEFAULT_SAMPLE_RATE)


# ── Ultrasonic FSK Writer ──────────────────────────────────────────


def write_ultrasonic(
    text: str,
    path: str,
    *,
    freq_0: int = DEFAULT_ULTRASONIC_FREQ_0,
    freq_1: int = DEFAULT_ULTRASONIC_FREQ_1,
    bit_duration: float = DEFAULT_ULTRASONIC_BIT_DURATION,
    amplitude: float = 0.1,
    carrier_path: str | None = None,
    encrypt: bool = False,
    key: str | None = None,
) -> None:
    """Encode text as near-ultrasonic FSK tones (16-20 kHz).

    Uses Frequency Shift Keying to encode each bit of the text as a
    tone at either freq_0 (for '0') or freq_1 (for '1'). The resulting
    audio is typically inaudible to humans but detectable by microphones.
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            "numpy is required for ultrasonic encoding. Install with: pip install prompt-injection-studio[embed-audio-adv]"
        ) from exc

    # Optionally encrypt the text
    if encrypt:
        text, used_key = encrypt_text(text, key)
        logger.info(f"Encrypted with key: {used_key[:16]}...")

    # Convert text to binary
    binary_data = text_to_binary(text)

    # Generate FSK audio
    samples_per_bit = int(DEFAULT_SAMPLE_RATE * bit_duration)
    t_bit = np.linspace(0, bit_duration, samples_per_bit, endpoint=False)

    all_samples = []

    # Add a sync preamble: alternating 0/1 pattern
    preamble = "10101010"
    for bit in preamble:
        freq = freq_1 if bit == "1" else freq_0
        tone = np.sin(2 * np.pi * freq * t_bit) * amplitude
        all_samples.extend(tone)

    # Encode the data
    for bit in binary_data:
        freq = freq_1 if bit == "1" else freq_0
        tone = np.sin(2 * np.pi * freq * t_bit) * amplitude
        all_samples.extend(tone)

    # Convert to 16-bit PCM
    samples_array = np.array(all_samples)
    samples_int = (samples_array * 32767).astype(np.int16)

    if carrier_path and os.path.isfile(carrier_path):
        # Mix with carrier
        carrier_samples = read_wav_samples(carrier_path)
        carrier_array = np.array(carrier_samples, dtype=np.float32) / 32767.0

        # Extend or truncate to match
        if len(samples_array) < len(carrier_array):
            samples_array = np.pad(samples_array, (0, len(carrier_array) - len(samples_array)))
        elif len(carrier_array) < len(samples_array):
            carrier_array = np.pad(carrier_array, (0, len(samples_array) - len(carrier_array)))

        # Mix
        mixed = samples_array + carrier_array
        mixed = np.clip(mixed, -1.0, 1.0)
        samples_int = (mixed * 32767).astype(np.int16)

    # Write WAV
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(DEFAULT_SAMPLE_RATE)
        wf.writeframes(samples_int.tobytes())


def decode_ultrasonic(
    path: str,
    *,
    freq_0: int = DEFAULT_ULTRASONIC_FREQ_0,
    freq_1: int = DEFAULT_ULTRASONIC_FREQ_1,
    bit_duration: float = DEFAULT_ULTRASONIC_BIT_DURATION,
    decrypt: bool = False,
    key: str | None = None,
) -> str:
    """Decode text from near-ultrasonic FSK audio."""
    try:
        import numpy as np
        from scipy.fft import fft
    except ImportError as exc:
        raise ImportError(
            "numpy and scipy are required for ultrasonic decoding. "
            "Install with: pip install prompt-injection-studio[embed-audio-adv]"
        ) from exc

    # Read WAV
    samples = read_wav_samples(path)
    samples_array = np.array(samples, dtype=np.float32) / 32767.0

    samples_per_bit = int(DEFAULT_SAMPLE_RATE * bit_duration)

    # Skip preamble (8 bits)
    preamble_samples = samples_per_bit * 8
    data_samples = samples_array[preamble_samples:]

    # Decode each bit.  The stop bound needs the +1: without it the range ends a
    # full bit early and the last bit of the payload is never read, which
    # silently flipped the final character of every message ("abc" decoded as
    # "abb", "instructions" as "instructionr").
    binary_data = ""
    for i in range(0, len(data_samples) - samples_per_bit + 1, samples_per_bit):
        chunk = data_samples[i : i + samples_per_bit]

        # FFT to find dominant frequency
        spectrum = np.abs(fft(chunk))
        freqs = np.fft.fftfreq(len(chunk), 1 / DEFAULT_SAMPLE_RATE)

        # Find peak in positive frequencies
        positive_mask = freqs > 0
        positive_freqs = freqs[positive_mask]
        positive_spectrum = spectrum[positive_mask]

        if len(positive_spectrum) == 0:
            continue

        peak_idx = np.argmax(positive_spectrum)
        peak_freq = positive_freqs[peak_idx]

        # Determine bit value
        dist_0 = abs(peak_freq - freq_0)
        dist_1 = abs(peak_freq - freq_1)
        bit = "1" if dist_1 < dist_0 else "0"
        binary_data += bit

    # Convert binary to text
    text = binary_to_text(binary_data)

    if decrypt:
        if key is None:
            raise ValueError("Decryption key is required when decrypt=True")
        text = decrypt_text(text, key)

    return text


# ── LSB Steganography Writer ───────────────────────────────────────


def write_audio_stego(
    text: str,
    path: str,
    *,
    carrier_path: str | None = None,
    bits_per_sample: int = 1,
) -> None:
    """Encode text into LSBs of WAV PCM samples."""
    # Convert text to binary with length prefix
    text_bytes = text.encode("utf-8")
    length_bytes = struct.pack(">I", len(text_bytes))
    data = length_bytes + text_bytes
    binary_data = "".join(format(byte, "08b") for byte in data)

    if carrier_path and os.path.isfile(carrier_path):
        samples = read_wav_samples(carrier_path)
    else:
        # Generate silent carrier (1 second minimum)
        min_samples = max(len(binary_data) // bits_per_sample + 1000, DEFAULT_SAMPLE_RATE)
        samples = [0] * min_samples

    # Check capacity
    capacity = len(samples) * bits_per_sample
    if len(binary_data) > capacity:
        raise ValueError(
            f"Text too long for carrier audio. Need {len(binary_data)} bits, have {capacity} bits capacity."
        )

    # Embed data into LSBs
    bit_idx = 0
    for i in range(len(samples)):
        if bit_idx >= len(binary_data):
            break

        sample = samples[i]
        # Handle signed 16-bit samples
        if sample < 0:
            sample = sample + 65536  # Convert to unsigned

        # Clear LSBs and set new bits
        mask = ~((1 << bits_per_sample) - 1) & 0xFFFF
        sample = sample & mask

        bits_to_embed = binary_data[bit_idx : bit_idx + bits_per_sample]
        bits_to_embed = bits_to_embed.ljust(bits_per_sample, "0")
        sample = sample | int(bits_to_embed, 2)

        # Convert back to signed
        if sample >= 32768:
            sample = sample - 65536

        samples[i] = sample
        bit_idx += bits_per_sample

    write_wav_samples(path, samples, DEFAULT_SAMPLE_RATE)


def decode_audio_stego(
    path: str,
    *,
    bits_per_sample: int = 1,
) -> str:
    """Decode text from LSBs of WAV PCM samples."""
    samples = read_wav_samples(path)

    # Extract bits from LSBs
    binary_data = ""
    for sample in samples:
        if sample < 0:
            sample = sample + 65536

        bits = format(sample & ((1 << bits_per_sample) - 1), f"0{bits_per_sample}b")
        binary_data += bits

    # Read length prefix (4 bytes = 32 bits)
    if len(binary_data) < 32:
        raise ValueError("Audio too short to contain stego data")

    length_bits = binary_data[:32]
    length = struct.unpack(">I", int(length_bits, 2).to_bytes(4, "big"))[0]

    # Read text data
    text_bits = binary_data[32 : 32 + length * 8]
    if len(text_bits) < length * 8:
        raise ValueError("Audio truncated or corrupted")

    text_bytes = bytes(int(text_bits[i : i + 8], 2) for i in range(0, len(text_bits), 8))
    return text_bytes.decode("utf-8")


# ── Spectrogram Watermark Writer ───────────────────────────────────


def write_spectro_text(
    text: str,
    path: str,
    *,
    duration: float = 5.0,
    freq_min: int = 1000,
    freq_max: int = 8000,
    amplitude: float = 0.3,
) -> None:
    """Embed text as a spectrogram watermark."""
    try:
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            "numpy is required for spectrogram watermarking. Install with: pip install prompt-injection-studio[embed-audio-adv]"
        ) from exc

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise ImportError(
            "Pillow is required for spectrogram watermarking. Install with: pip install prompt-injection-studio[embed]"
        ) from exc

    # Render text as a binary image
    img_width = int(duration * 100)  # 100 pixels per second
    img_height = 64  # Frequency resolution

    img = Image.new("L", (img_width, img_height), 0)
    draw = ImageDraw.Draw(img)

    # Try to use a monospace font, fall back to default
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 12)
    except OSError:
        try:
            font = ImageFont.truetype("Courier", 12)
        except OSError:
            font = ImageFont.load_default()

    # Draw text centered
    draw.text((5, img_height // 2 - 6), text[:50], fill=255, font=font)

    # Convert image to numpy array
    img_array = np.array(img, dtype=np.float32) / 255.0

    # Generate audio from spectrogram
    num_samples = int(duration * DEFAULT_SAMPLE_RATE)
    samples_per_column = num_samples // img_width

    audio = np.zeros(num_samples)

    for col in range(img_width):
        column = img_array[:, col]

        # Map each row to a frequency
        for row, intensity in enumerate(column):
            if intensity < 0.1:
                continue

            # Map row to frequency (top = high freq, bottom = low freq)
            freq = freq_max - (row / img_height) * (freq_max - freq_min)

            # Generate sine wave for this column
            start_sample = col * samples_per_column
            end_sample = min(start_sample + samples_per_column, num_samples)
            t = np.arange(end_sample - start_sample) / DEFAULT_SAMPLE_RATE

            tone = np.sin(2 * np.pi * freq * t) * intensity * amplitude
            audio[start_sample:end_sample] += tone

    # Normalize
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = audio / max_val * amplitude

    # Convert to 16-bit PCM
    samples_int = (audio * 32767).astype(np.int16)

    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(DEFAULT_SAMPLE_RATE)
        wf.writeframes(samples_int.tobytes())
