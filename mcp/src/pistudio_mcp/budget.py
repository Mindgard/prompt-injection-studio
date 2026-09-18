"""Rate limit on the tools that act on the physical world.

Concurrency caps bound how many calls run *at once*; this bounds them **over
time**. The failure it exists for is an agent that loops — through a bug, or
because adversarial text in a payload talked it into looping — and keeps
deploying to a device or re-publishing a payload server. A cap on simultaneous
subprocesses does nothing about that: the calls are sequential.

Applied to hardware delivery and to starting the payload server, not to reads.
Listing the payload library a hundred times is wasteful; arming a Flipper a
hundred times is a different kind of problem.
"""

from __future__ import annotations

import threading
import time

from pistudio_mcp import envcfg
from pistudio_mcp.errors import PiStudioMCPError

_WINDOW_SECONDS = 3600.0

# 0 disables the cap. The default is deliberately low: a legitimate session
# deploys to a device a handful of times, and a number that never bites is not a
# control.
_MAX_PER_HOUR = envcfg.integer("PISTUDIO_MCP_MAX_ACTIONS_PER_HOUR", 20, minimum=0)

_lock = threading.Lock()
_timestamps: list[float] = []


def _prune(now: float) -> None:
    cutoff = now - _WINDOW_SECONDS
    _timestamps[:] = [t for t in _timestamps if t > cutoff]


def check_and_consume(action: str) -> None:
    """Record one side-effecting action, or raise if the hourly cap is spent.

    Checked *before* the subprocess starts, so a refused call never reaches the
    device.

    Args:
        action: What was being attempted, for the error message.

    Raises:
        PiStudioMCPError: If the cap is already reached.
    """
    if _MAX_PER_HOUR == 0:
        return
    now = time.monotonic()
    with _lock:
        _prune(now)
        if len(_timestamps) >= _MAX_PER_HOUR:
            oldest = min(_timestamps)
            wait = int(_WINDOW_SECONDS - (now - oldest))
            raise PiStudioMCPError(
                f"{action} is rate-limited: {_MAX_PER_HOUR} side-effecting actions already used "
                f"in the last hour. Next slot in about {max(wait, 1)}s. Raise or disable with "
                "PISTUDIO_MCP_MAX_ACTIONS_PER_HOUR."
            )
        _timestamps.append(now)


def state() -> dict[str, int]:
    """The current budget, for the ``studio_status`` security block."""
    now = time.monotonic()
    with _lock:
        _prune(now)
        return {"max_per_hour": _MAX_PER_HOUR, "used": len(_timestamps)}


def reset() -> None:
    """Clear the window. For tests only."""
    with _lock:
        _timestamps.clear()
