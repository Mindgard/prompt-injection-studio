"""Live acoustic delivery: a payload spoken into a room, not written to a file.

The channel exists because the sink does. An AI notetaker is, in Joe Sullivan's
framing at [un]prompted 2026, "the only memory of what happens in these
meetings" -- a persisted, authoritative record that an assistant later
summarises. That makes a microphone a write endpoint into a data store an LLM
reads, which is the blind-PI kill chain with no hardware in it::

    speak -> transcript -> stored -> dormant -> "what did we agree?" -> executed

Three pieces:

- :mod:`~pistudio.acoustic.playback` plays a generated carrier through an output
  device, turning the existing TTS and ultrasonic writers into a live channel.
- :mod:`~pistudio.acoustic.session` schedules fragments across a meeting so the
  payload assembles only in the transcript.
- :mod:`~pistudio.acoustic.transcript` scores whether it arrived -- the tool's
  first success oracle, and the owner of the channel-independent verdict
  taxonomy other carriers score against.
"""

from pistudio.acoustic.playback import (
    AudioDevice,
    PlaybackUnavailableError,
    install_hint,
    list_devices,
    play_wav,
    playback_available,
    wav_duration,
)
from pistudio.acoustic.session import (
    MODES,
    Session,
    Utterance,
    format_timecode,
    load_session,
    parse_timecode,
    split_payload,
    suggest_windows,
)
from pistudio.acoustic.transcript import VERDICTS, SurvivalVerdict, normalise, score

__all__ = [
    "MODES",
    "VERDICTS",
    "AudioDevice",
    "PlaybackUnavailableError",
    "Session",
    "SurvivalVerdict",
    "Utterance",
    "format_timecode",
    "install_hint",
    "list_devices",
    "load_session",
    "normalise",
    "parse_timecode",
    "play_wav",
    "playback_available",
    "score",
    "split_payload",
    "suggest_windows",
    "wav_duration",
]
