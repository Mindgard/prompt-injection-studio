"""Live audio output: play a payload into a room rather than write it to a file.

The rest of the tool writes carriers to disk. This plays one, which is what
turns the existing TTS and ultrasonic generators into a live channel into any
microphone in earshot -- and therefore into whatever transcript that microphone
feeds.

``sounddevice`` is optional. Without it every function degrades to writing a WAV
and telling the operator to play it, so the channel is still usable without a
new dependency.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass

# Playback needs an output device; the generators it wraps do not.
PLAYBACK_EXTRA = "acoustic"


@dataclass(frozen=True, slots=True)
class AudioDevice:
    """An output device the payload can be played through."""

    index: int
    name: str
    channels: int
    default_samplerate: float
    is_default: bool = False


class PlaybackUnavailableError(RuntimeError):
    """Raised when playback is requested without the optional dependency."""


def playback_available() -> bool:
    """Whether live playback can run in this environment."""
    try:
        import sounddevice  # noqa: F401
    except Exception:
        # Catches ImportError and the OSError sounddevice raises when PortAudio
        # is missing at the system level, which pip cannot fix.
        return False
    return True


def install_hint() -> str:
    """How to enable playback."""
    return (
        "Live playback needs sounddevice and a working PortAudio.\n"
        f"  pip install 'prompt-injection-studio[{PLAYBACK_EXTRA}]'\n"
        "Without it, generate a WAV and play it with any audio player:\n"
        '  pistudio audio tts-wav "<payload>" --output payload.wav'
    )


def list_devices() -> list[AudioDevice]:
    """Enumerate output-capable audio devices.

    Raises:
        PlaybackUnavailableError: If sounddevice is not importable.
    """
    if not playback_available():
        raise PlaybackUnavailableError(install_hint())
    import sounddevice as sd

    default_out = sd.default.device[1] if isinstance(sd.default.device, (list, tuple)) else None
    devices: list[AudioDevice] = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_output_channels", 0) < 1:
            continue
        devices.append(
            AudioDevice(
                index=idx,
                name=str(dev.get("name", f"device {idx}")),
                channels=int(dev["max_output_channels"]),
                default_samplerate=float(dev.get("default_samplerate", 44100)),
                is_default=(idx == default_out),
            )
        )
    return devices


def play_wav(path: str, *, device: int | None = None, blocking: bool = True) -> float:
    """Play a WAV file through an output device.

    Args:
        path: WAV file to play.
        device: Output device index; None uses the system default.
        blocking: Wait for playback to finish before returning.

    Returns:
        The duration played, in seconds.

    Raises:
        PlaybackUnavailableError: If sounddevice is not importable.
    """
    if not playback_available():
        raise PlaybackUnavailableError(install_hint())

    import numpy as np
    import sounddevice as sd

    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(width)
    if dtype is None:
        raise ValueError(f"Unsupported WAV sample width: {width} bytes")

    samples = np.frombuffer(frames, dtype=dtype)
    if channels > 1:
        samples = samples.reshape(-1, channels)

    sd.play(samples, samplerate=rate, device=device)
    duration = len(samples) / rate
    if blocking:
        sd.wait()
    return duration


def wav_duration(path: str) -> float:
    """Duration of a WAV file in seconds, without playing it."""
    with wave.open(path, "rb") as wf:
        return wf.getnframes() / wf.getframerate()
