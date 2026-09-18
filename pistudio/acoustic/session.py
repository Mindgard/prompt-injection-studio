"""Timed multi-utterance delivery across a meeting.

A single utterance carrying a whole payload is conspicuous and lands in one
place. A session script delivers fragments at chosen times so the payload
assembles only in the transcript -- the acoustic analogue of the payload
splitting Unit 42 recorded in web injection, which defeats per-element scanning
because the aggregate is what the model reads.

Timing is not arbitrary. Sullivan's [un]prompted 2026 talk reports that
notetakers weight **primacy and recency**, capturing the opening of a meeting
and transition points as important, and that **format mirroring** -- speaking
the section headings the notetaker will generate -- makes those the headings.
``suggest_windows`` encodes that as advice rather than leaving the operator to
guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MODES = ("tts", "ultrasonic")


@dataclass(frozen=True, slots=True)
class Utterance:
    """One scheduled delivery within a session."""

    at_seconds: int
    text: str
    mode: str = "tts"
    voice: str | None = None
    freq: int | None = None  # ultrasonic carrier, when mode is ultrasonic
    note: str = ""  # operator-facing rationale, e.g. "opening, primacy window"


@dataclass(frozen=True, slots=True)
class Session:
    """An ordered delivery script for one meeting."""

    name: str
    utterances: list[Utterance] = field(default_factory=list)
    description: str = ""

    @property
    def duration(self) -> int:
        """Seconds from start to the last scheduled utterance."""
        return max((u.at_seconds for u in self.utterances), default=0)

    def assembled(self) -> str:
        """The payload as it will appear once the transcript aggregates it."""
        return " ".join(u.text for u in sorted(self.utterances, key=lambda u: u.at_seconds))


_TIMECODE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")


def parse_timecode(value: str) -> int:
    """Parse ``HH:MM:SS``, ``MM:SS``, or a bare second count into seconds.

    Raises:
        ValueError: If the value is not a recognisable timecode.
    """
    text = value.strip()
    if text.isdigit():
        return int(text)
    m = _TIMECODE.match(text)
    if not m:
        raise ValueError(f"Unrecognised timecode '{value}'. Use MM:SS, HH:MM:SS, or a number of seconds.")
    hours, minutes, seconds = m.group(1), int(m.group(2)), int(m.group(3))
    if seconds >= 60:
        raise ValueError(f"Invalid timecode '{value}': seconds must be under 60.")
    total = int(hours or 0) * 3600 + minutes * 60 + seconds
    return total


def format_timecode(seconds: int) -> str:
    """Render seconds as ``MM:SS`` or ``H:MM:SS``."""
    hours, rem = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def load_session(data: dict) -> Session:
    """Build a :class:`Session` from parsed YAML/JSON.

    Raises:
        ValueError: On a missing field, unknown mode, or bad timecode.
    """
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("Session needs a 'name'.")

    raw = data.get("utterances")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"Session '{name}' needs a non-empty 'utterances' list.")

    utterances: list[Utterance] = []
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Utterance {i} in '{name}' is not a mapping.")
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError(f"Utterance {i} in '{name}' has no 'text'.")
        mode = str(item.get("mode") or "tts")
        if mode not in MODES:
            raise ValueError(f"Utterance {i} in '{name}': unknown mode '{mode}'. Use one of {', '.join(MODES)}.")
        at_raw = item.get("at", item.get("at_seconds", 0))
        at = parse_timecode(str(at_raw))
        freq = item.get("freq")
        utterances.append(
            Utterance(
                at_seconds=at,
                text=text,
                mode=mode,
                voice=item.get("voice"),
                freq=int(freq) if freq is not None else None,
                note=str(item.get("note") or ""),
            )
        )

    utterances.sort(key=lambda u: u.at_seconds)
    return Session(name=name, utterances=utterances, description=str(data.get("description") or ""))


def suggest_windows(meeting_minutes: int) -> list[tuple[int, str]]:
    """Delivery windows a notetaker is most likely to weight heavily.

    Derived from Sullivan's account of notetaker behaviour: primacy and recency
    dominate, and transition points read as section boundaries. Advisory -- the
    effect is reported from studies of commercial notetakers, not measured here.

    Returns:
        ``(offset_seconds, rationale)`` pairs, earliest first.
    """
    total = max(1, meeting_minutes) * 60
    windows: list[tuple[int, str]] = [
        (60, "opening: primacy window, weighted most heavily"),
        (total // 3, "first transition: reads as a section boundary"),
        (total // 2, "midpoint: second transition"),
        (max(total - 300, total // 2 + 1), "closing: recency window, action-item capture"),
    ]
    # Collapse windows that land on the same second in a short meeting.
    seen: set[int] = set()
    unique: list[tuple[int, str]] = []
    for offset, why in windows:
        if offset not in seen and offset <= total:
            seen.add(offset)
            unique.append((offset, why))
    return unique


def split_payload(payload: str, parts: int) -> list[str]:
    """Split *payload* into *parts* fragments on word boundaries.

    Fragments assemble in the transcript rather than in any single utterance.
    Splits on words because a mid-word break is likely to be transcribed as a
    different word, corrupting the reassembly.

    Raises:
        ValueError: If *parts* is below 1 or exceeds the word count.
    """
    words = payload.split()
    if parts < 1:
        raise ValueError("parts must be at least 1")
    if parts > len(words):
        raise ValueError(f"Cannot split {len(words)} words into {parts} parts.")

    per, extra = divmod(len(words), parts)
    fragments: list[str] = []
    idx = 0
    for i in range(parts):
        take = per + (1 if i < extra else 0)
        fragments.append(" ".join(words[idx : idx + take]))
        idx += take
    return fragments
