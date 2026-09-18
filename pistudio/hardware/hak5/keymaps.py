"""USB HID keycode tables for encoding DuckyScript to ``inject.bin``.

The values are USB HID Usage IDs from the *USB HID Usage Tables*, section 10,
"Keyboard/Keypad Page (0x07)" — the same table every keyboard and DuckyScript
encoder uses.  They describe *which key* is pressed, not which character is
produced: the character depends on the layout the **target** has selected, so
a payload encoded for one layout mistypes on another.  See ``LAYOUTS`` and
``docs/hak5.md`` for why that matters.

Only printable ASCII is representable. A HID keyboard has no code point for
accented letters or emoji; the caller is responsible for rejecting them.
"""

# Modifier bitmask, byte 2 of each inject.bin pair.
MOD_NONE = 0x00
MOD_LCTRL = 0x01
MOD_LSHIFT = 0x02
MOD_LALT = 0x04
MOD_LGUI = 0x08
MOD_RCTRL = 0x10
MOD_RSHIFT = 0x20
MOD_RALT = 0x40
MOD_RGUI = 0x80

# HID usage IDs for named keys used by the compiler's output.
KEY_ENTER = 0x28
KEY_SPACE = 0x2C


def _letters() -> dict[str, tuple[int, int]]:
    """a-z at 0x04.., and A-Z as the same key plus SHIFT."""
    table: dict[str, tuple[int, int]] = {}
    for i in range(26):
        code = 0x04 + i
        table[chr(ord("a") + i)] = (code, MOD_NONE)
        table[chr(ord("A") + i)] = (code, MOD_LSHIFT)
    return table


# Digit row: 1-9 at 0x1E.., 0 at 0x27, with the shifted symbol on each key.
_DIGITS: dict[str, tuple[int, int]] = {
    "1": (0x1E, MOD_NONE),
    "2": (0x1F, MOD_NONE),
    "3": (0x20, MOD_NONE),
    "4": (0x21, MOD_NONE),
    "5": (0x22, MOD_NONE),
    "6": (0x23, MOD_NONE),
    "7": (0x24, MOD_NONE),
    "8": (0x25, MOD_NONE),
    "9": (0x26, MOD_NONE),
    "0": (0x27, MOD_NONE),
    "!": (0x1E, MOD_LSHIFT),
    "@": (0x1F, MOD_LSHIFT),
    "#": (0x20, MOD_LSHIFT),
    "$": (0x21, MOD_LSHIFT),
    "%": (0x22, MOD_LSHIFT),
    "^": (0x23, MOD_LSHIFT),
    "&": (0x24, MOD_LSHIFT),
    "*": (0x25, MOD_LSHIFT),
    "(": (0x26, MOD_LSHIFT),
    ")": (0x27, MOD_LSHIFT),
}

# Punctuation, keyed by HID usage ID with its unshifted and shifted characters.
_PUNCTUATION: dict[str, tuple[int, int]] = {
    " ": (KEY_SPACE, MOD_NONE),
    "-": (0x2D, MOD_NONE),
    "_": (0x2D, MOD_LSHIFT),
    "=": (0x2E, MOD_NONE),
    "+": (0x2E, MOD_LSHIFT),
    "[": (0x2F, MOD_NONE),
    "{": (0x2F, MOD_LSHIFT),
    "]": (0x30, MOD_NONE),
    "}": (0x30, MOD_LSHIFT),
    "\\": (0x31, MOD_NONE),
    "|": (0x31, MOD_LSHIFT),
    ";": (0x33, MOD_NONE),
    ":": (0x33, MOD_LSHIFT),
    "'": (0x34, MOD_NONE),
    '"': (0x34, MOD_LSHIFT),
    "`": (0x35, MOD_NONE),
    "~": (0x35, MOD_LSHIFT),
    ",": (0x36, MOD_NONE),
    "<": (0x36, MOD_LSHIFT),
    ".": (0x37, MOD_NONE),
    ">": (0x37, MOD_LSHIFT),
    "/": (0x38, MOD_NONE),
    "?": (0x38, MOD_LSHIFT),
}

# The complete US layout: character -> (HID usage ID, modifier bitmask).
US_LAYOUT: dict[str, tuple[int, int]] = {**_letters(), **_DIGITS, **_PUNCTUATION}

# Named layouts. Only US is implemented as a full table; the others are
# declared so the CLI can name them and explain that encoding for a non-US
# target needs the layout the target actually uses.
LAYOUTS: dict[str, dict[str, tuple[int, int]]] = {
    "us": US_LAYOUT,
}

DEFAULT_LAYOUT = "us"


def printable_chars(layout: dict[str, tuple[int, int]] = US_LAYOUT) -> set[str]:
    """Return the set of characters *layout* can encode."""
    return set(layout)
