"""Shared ``--flag value`` parsing.

Commands take the remainder of the argv verbatim and parse it themselves, so
these two operations — read a flag's value, and remove the pair — came up in
enough places to be worth sharing.  Both leave the input untouched.
"""

from __future__ import annotations

__all__ = ["extract_flag", "slugify", "strip_flag", "take_flag", "unknown_flag_message"]


def unknown_flag_message(flag: str, known: list[str] | tuple[str, ...]) -> str:
    """Build the error for an unrecognised *flag*, suggesting a near match.

    A bare "Unknown flag: --voise" is a dead end; naming the flag the user
    probably meant turns it into a one-keystroke fix.
    """
    import difflib

    matches = difflib.get_close_matches(flag, list(known), n=1, cutoff=0.6)
    hint = f" Did you mean '{matches[0]}'?" if matches else ""
    return f"Unknown flag: {flag}.{hint}"


def extract_flag(args: list[str], flag: str) -> str | None:
    """Return the value following *flag*, or None if it is absent."""
    for i, arg in enumerate(args):
        if arg == flag and i + 1 < len(args):
            return args[i + 1]
    return None


def strip_flag(args: list[str], flag: str) -> list[str]:
    """Return *args* without *flag* and the value after it."""
    result: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg == flag:
            skip = True
            continue
        result.append(arg)
    return result


def take_flag(args: list[str], flag: str, default: str | None = None) -> tuple[list[str], str | None]:
    """Read *flag* and remove it in one step.

    Returns:
        ``(remaining_args, value)``, with *value* falling back to *default*.
    """
    value = extract_flag(args, flag)
    if value is None:
        return list(args), default
    return strip_flag(args, flag), value


def slugify(text: str) -> str:
    """Return a short, filename-safe slug for *text*."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:30] if slug else "prompt"
