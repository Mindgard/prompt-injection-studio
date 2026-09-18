"""Environment-variable parsing for the server's configuration knobs.

A malformed knob must not stop the server from starting. Every setting is read
at import time, and an MCP server that raises during import surfaces in the
client as an opaque "server failed to start" — the traceback lands in a log the
user may never look at. So a bad numeric value warns and falls back to the
default rather than propagating a ``ValueError``.

Booleans are deliberately strict: only ``1``/``true``/``yes``/``on`` enable a
setting, so a typo in a *security* opt-in (``PISTUDIO_MCP_ENABLE_HW=maybe``)
fails closed rather than silently arming hardware delivery.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("pistudio_mcp")


def truthy(value: str | None) -> bool:
    """Whether *value* is an affirmative setting. Anything unrecognized is False."""
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def flag(name: str) -> bool:
    """Read boolean environment variable *name* (absent or unrecognized -> False)."""
    return truthy(os.environ.get(name))


def number(name: str, default: float, *, minimum: float = 0.0) -> float:
    """Read numeric environment variable *name*, warning and falling back on junk.

    Args:
        name: Environment variable to read.
        default: Value used when unset, empty, or unparseable.
        minimum: Floor applied to the parsed value.

    Returns:
        The parsed value clamped to *minimum*, or *default* if unparseable.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        log.warning("%s=%r is not a number — falling back to %g.", name, raw, default)
        return default
    if value < minimum:
        log.warning("%s=%g is below the minimum %g — using %g.", name, value, minimum, minimum)
        return minimum
    return value


def integer(name: str, default: int, *, minimum: int = 1) -> int:
    """Read integer environment variable *name*, warning and falling back on junk."""
    return int(number(name, float(default), minimum=float(minimum)))
