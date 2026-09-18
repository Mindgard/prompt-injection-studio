"""Audio helper functions for WAV I/O, binary encoding, and encryption.

Extracted from ``audio.py`` to keep file sizes manageable.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
import wave

# ── Constants ──────────────────────────────────────────────────────

# Ultrasonic FSK parameters
DEFAULT_ULTRASONIC_FREQ_0 = 17500  # Hz for '0' bit
DEFAULT_ULTRASONIC_FREQ_1 = 19000  # Hz for '1' bit
DEFAULT_ULTRASONIC_BIT_DURATION = 0.02  # seconds per bit
DEFAULT_SAMPLE_RATE = 44100


# ── WAV I/O ───────────────────────────────────────────────────────


def read_wav_samples(path: str) -> list[int]:
    """Read 16-bit PCM samples from a WAV file."""
    with wave.open(path, "r") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        n_frames = wf.getnframes()

        raw = wf.readframes(n_frames)

    # Convert to list of samples
    if sample_width == 2:
        fmt = f"<{len(raw) // 2}h"
        samples = list(struct.unpack(fmt, raw))
    elif sample_width == 1:
        samples = [int.from_bytes(raw[i : i + 1], "little", signed=False) - 128 for i in range(len(raw))]
        samples = [s * 256 for s in samples]  # Scale to 16-bit range
    else:
        raise ValueError(f"Unsupported sample width: {sample_width}")

    # If stereo, take left channel only
    if n_channels == 2:
        samples = samples[::2]

    return samples


def write_wav_samples(path: str, samples: list[int], sample_rate: int) -> None:
    """Write 16-bit PCM samples to a WAV file."""
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        # Clip samples to valid range
        clipped = [max(-32768, min(32767, s)) for s in samples]
        raw = struct.pack(f"<{len(clipped)}h", *clipped)
        wf.writeframes(raw)


# ── Binary Encoding ───────────────────────────────────────────────


def text_to_binary(text: str) -> str:
    """Convert text to binary string."""
    return "".join(format(byte, "08b") for byte in text.encode("utf-8"))


def binary_to_text(binary: str) -> str:
    """Convert binary string to text."""
    # Pad to multiple of 8
    padded = binary + "0" * (8 - len(binary) % 8) if len(binary) % 8 else binary

    bytes_list = []
    for i in range(0, len(padded), 8):
        byte_str = padded[i : i + 8]
        try:
            bytes_list.append(int(byte_str, 2))
        except ValueError:
            break

    # Try to decode, stopping at null or invalid bytes
    result = []
    for b in bytes_list:
        if b == 0:
            break
        try:
            result.append(bytes([b]).decode("utf-8"))
        except UnicodeDecodeError:
            break

    return "".join(result)


# ── Encryption ────────────────────────────────────────────────────


def encrypt_text(text: str, key: str | None = None) -> tuple[str, str]:
    """Encrypt text using a simple XOR cipher with key derivation.

    Returns (encrypted_text_as_hex, key_used).
    """
    if key is None:
        # Generate a random key
        key = os.urandom(16).hex()

    # Derive a key using PBKDF2
    salt = b"mindgard_audio_pi"
    derived = hashlib.pbkdf2_hmac("sha256", key.encode(), salt, 100000, dklen=32)

    # XOR encrypt
    text_bytes = text.encode("utf-8")
    encrypted = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(text_bytes))

    # Add HMAC for integrity
    mac = hmac.new(derived, encrypted, hashlib.sha256).digest()[:8]

    # Return as hex string
    return (mac + encrypted).hex(), key


def decrypt_text(hex_data: str, key: str) -> str:
    """Decrypt text encrypted with encrypt_text."""
    data = bytes.fromhex(hex_data)

    # Derive key
    salt = b"mindgard_audio_pi"
    derived = hashlib.pbkdf2_hmac("sha256", key.encode(), salt, 100000, dklen=32)

    # Verify HMAC
    mac = data[:8]
    encrypted = data[8:]
    expected_mac = hmac.new(derived, encrypted, hashlib.sha256).digest()[:8]

    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Decryption failed: invalid key or corrupted data")

    # XOR decrypt
    decrypted = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(encrypted))

    return decrypted.decode("utf-8")
