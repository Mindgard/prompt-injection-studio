"""Input validation for values that become paths on the Flipper's SD card.

Payload names reach ``os.path.join`` and decide where a file is written.  A
name is not always typed by hand — it can come from a synced corpus or a
generated library — so a name containing a separator or ``..`` would write
outside the card entirely.  These checks fail on the operator's machine rather
than silently landing a file somewhere unintended.
"""

import os
from collections.abc import Callable

# FAT32 forbids these outright, and the Flipper's own file browser follows
# suit.  Control characters are excluded separately.
_ILLEGAL_CHARACTERS = '<>:"/\\|?*'

# Reserved DOS device names; FAT still refuses these regardless of extension.
_RESERVED_STEMS = frozenset(
    ["CON", "PRN", "AUX", "NUL"] + [f"COM{i}" for i in range(1, 10)] + [f"LPT{i}" for i in range(1, 10)]
)

# The Flipper's storage layer truncates beyond this, which would silently
# collide two payloads with a long shared prefix.
MAX_NAME_LENGTH = 64


def validate_payload_name(name: str) -> str:
    """Return *name* if it is safe to use as a filename on the SD card.

    Args:
        name: The payload name, with or without its extension.

    Returns:
        The name unchanged.

    Raises:
        ValueError: If the name is empty, too long, contains a path separator
            or ``..``, uses a character FAT32 forbids, or is a reserved name.
    """
    for is_bad, message in _NAME_RULES:
        if is_bad(name):
            raise ValueError(message(name))
    return name


def _illegal_characters(name: str) -> str:
    return "".join(sorted({ch for ch in name if ch in _ILLEGAL_CHARACTERS}))


# Each rule is (does this name break it, how to say so).  A table keeps adding
# a rule a one-line change rather than another branch.
_NAME_RULES: tuple[tuple[Callable[[str], bool], Callable[[str], str]], ...] = (
    (
        lambda n: not n or not n.strip(),
        lambda n: "Payload name must not be empty.",
    ),
    (
        lambda n: len(n) > MAX_NAME_LENGTH,
        lambda n: f"Payload name is too long: {len(n)} characters, maximum is {MAX_NAME_LENGTH}.",
    ),
    (
        lambda n: "/" in n or "\\" in n,
        lambda n: f"Payload name must not contain a path separator: {n!r}",
    ),
    (
        lambda n: n == ".." or n.startswith("../") or "/.." in n,
        lambda n: f"Payload name must not contain '..': {n!r}",
    ),
    (
        os.path.isabs,
        lambda n: f"Payload name must be a bare filename, not a path: {n!r}",
    ),
    (
        lambda n: bool(_illegal_characters(n)),
        lambda n: f"Payload name contains characters the SD card cannot store: {_illegal_characters(n)!r}",
    ),
    (
        lambda n: any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in n),
        lambda n: f"Payload name must not contain control characters: {n!r}",
    ),
    (
        lambda n: n.split(".")[0].upper() in _RESERVED_STEMS,
        lambda n: f"Payload name is reserved by the filesystem: {n!r}",
    ),
    (
        lambda n: n != n.strip(),
        lambda n: f"Payload name must not start or end with whitespace: {n!r}",
    ),
    (
        lambda n: n.endswith("."),
        lambda n: f"Payload name must not end with a dot: {n!r}",
    ),
)


def safe_join(directory: str, name: str) -> str:
    """Join *name* onto *directory*, refusing anything that escapes it.

    Validates the name, then confirms the resolved path really is inside
    *directory*.  The second check catches what the first cannot: a symlink
    in the tree, or a mount whose case folding differs from the name given.

    Args:
        directory: The target directory on the SD card.
        name: The filename to place inside it.

    Returns:
        The absolute path to write to.

    Raises:
        ValueError: If the name is unsafe or the result escapes *directory*.
    """
    validate_payload_name(name)

    root = os.path.realpath(directory)
    target = os.path.realpath(os.path.join(root, name))

    if target != root and os.path.commonpath([root, target]) != root:
        raise ValueError(f"Refusing to write outside {directory}: {name!r} resolves to {target}")

    return target
