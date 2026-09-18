"""Compile DuckyScript 1.0 to ``inject.bin`` for the USB Rubber Ducky.

The Ducky (both the 2011 Mk1 and the 2022 Mk2) runs *compiled* bytecode from a
file named ``inject.bin``, unlike the Bash Bunny and Flipper, which interpret
DuckyScript from source.  Hak5's own compiler is a browser IDE with no offline
build, so a payload otherwise had to be pasted into a web page by hand.

This encoder produces the DuckyScript 1.0 binary — a sequence of two-byte
``(keycode, modifier)`` pairs — which the Mk2 still executes for backwards
compatibility.  It covers exactly the commands this tool emits (``STRING``,
``STRINGLN``, ``ENTER``, ``DELAY``, ``DEFAULTDELAY``, ``GUI``, ``REM``); it is
not a general DuckyScript 3.0 compiler, and it rejects anything it cannot
encode rather than emitting bytes that would mistype on the target.

Format, from the reference DuckEncoder (hak5darren / mame82):
  * Each pair is ``[HID keycode, modifier bitmask]``, keycode first.
  * A ``DELAY`` is a ``0x00`` keycode with the millisecond count in the
    modifier byte; counts above 255 ms span several pairs.
"""

import logging

from pistudio.hardware.hak5.keymaps import (
    DEFAULT_LAYOUT,
    KEY_ENTER,
    LAYOUTS,
    MOD_LGUI,
    MOD_NONE,
)

logger = logging.getLogger(__name__)

# A DELAY pair: keycode 0, milliseconds in the modifier byte (max 255 per pair).
_DELAY_KEYCODE = 0x00
_MAX_DELAY_CHUNK = 255

# GUI/WINDOWS with no argument presses the key alone.
_GUI_KEYCODE = 0x00  # keycode 0 + GUI modifier = press the modifier by itself


class UnsupportedCharError(ValueError):
    """A character has no key on the chosen layout.

    Carries the offending characters so the caller can tell the operator
    exactly what to remove.
    """

    def __init__(self, chars: list[str], layout: str):
        self.chars = chars
        self.layout = layout
        shown = ", ".join(repr(c) for c in chars)
        super().__init__(
            f"Cannot type these characters on the '{layout}' keyboard layout: {shown}. "
            "A USB keyboard has no key for them; rewrite the payload in printable ASCII."
        )


def unsupported_chars(text: str, layout: str = DEFAULT_LAYOUT) -> list[str]:
    """Return the distinct characters in *text* the layout cannot type.

    Newlines are allowed — the compiler turns them into ENTER — so they are not
    reported.  The result preserves first-seen order for a stable message.

    Args:
        text: Payload text to check.
        layout: Keyboard layout name.
    """
    table = LAYOUTS[layout]
    seen: dict[str, None] = {}
    for ch in text:
        if ch == "\n" or ch in table or ch in seen:
            continue
        seen[ch] = None
    return list(seen)


def _delay_pairs(ms: int) -> bytearray:
    """Return DELAY pairs totalling *ms* milliseconds."""
    out = bytearray()
    remaining = ms
    while remaining > 0:
        chunk = min(remaining, _MAX_DELAY_CHUNK)
        out += bytes((_DELAY_KEYCODE, chunk))
        remaining -= chunk
    return out


def _char_pairs(text: str, table: dict[str, tuple[int, int]], layout: str) -> bytearray:
    """Return keystroke pairs for *text*, one per character.

    Raises:
        UnsupportedCharError: If any character has no key on *layout*.
    """
    missing = unsupported_chars(text, layout)
    if missing:
        raise UnsupportedCharError(missing, layout)

    out = bytearray()
    for ch in text:
        if ch == "\n":
            out += bytes((KEY_ENTER, MOD_NONE))
            continue
        keycode, modifier = table[ch]
        out += bytes((keycode, modifier))
    return out


def encode(source: str, layout: str = DEFAULT_LAYOUT) -> bytes:
    """Encode DuckyScript *source* to ``inject.bin`` bytes.

    Handles the subset this tool emits. ``DEFAULTDELAY`` sets a pause inserted
    before every subsequent command, matching the firmware's behaviour.

    Args:
        source: DuckyScript source text.
        layout: Keyboard layout name (see ``LAYOUTS``).

    Returns:
        The ``inject.bin`` byte string.

    Raises:
        ValueError: If the layout is unknown, a command is unsupported, or a
            character cannot be typed on the layout.
    """
    if layout not in LAYOUTS:
        raise ValueError(f"Unknown keyboard layout '{layout}'. Available: {', '.join(sorted(LAYOUTS))}")
    table = LAYOUTS[layout]

    out = bytearray()
    default_delay = 0
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith(("REM", "#")):
            continue

        command, _, argument = line.partition(" ")
        command = command.upper()

        if default_delay and command != "DEFAULTDELAY":
            out += _delay_pairs(default_delay)

        if command == "DEFAULTDELAY" or command == "DEFAULT_DELAY":
            default_delay = _parse_int(argument, command)
        elif command == "DELAY":
            out += _delay_pairs(_parse_int(argument, command))
        elif command == "STRING":
            out += _char_pairs(argument, table, layout)
        elif command == "STRINGLN":
            # STRINGLN is DuckyScript 3.0; expand to keystrokes + Enter for 1.0.
            out += _char_pairs(argument + "\n", table, layout)
        elif command == "ENTER":
            out += bytes((KEY_ENTER, MOD_NONE))
        elif command in ("GUI", "WINDOWS"):
            out += _encode_gui(argument, table)
        else:
            raise ValueError(
                f"Cannot encode DuckyScript command '{command}'. This offline encoder covers "
                "STRING, STRINGLN, ENTER, DELAY, DEFAULTDELAY, and GUI; compile richer payloads "
                "with Hak5 PayloadStudio."
            )
    return bytes(out)


def _encode_gui(argument: str, table: dict[str, tuple[int, int]]) -> bytearray:
    """Encode ``GUI`` alone or ``GUI <key>`` (e.g. ``GUI r``)."""
    if not argument:
        return bytearray(bytes((_GUI_KEYCODE, MOD_LGUI)))
    if len(argument) != 1 or argument not in table:
        raise ValueError(f"GUI supports a single printable key, got {argument!r}.")
    keycode, _ = table[argument]
    return bytearray(bytes((keycode, MOD_LGUI)))


def _parse_int(argument: str, command: str) -> int:
    """Parse the integer argument of a delay command."""
    try:
        value = int(argument)
    except ValueError as exc:
        raise ValueError(f"{command} needs a whole number of milliseconds, got {argument!r}.") from exc
    if value < 0:
        raise ValueError(f"{command} cannot be negative, got {value}.")
    return value
