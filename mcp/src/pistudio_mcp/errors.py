"""The one exception type tools raise for a user-facing failure."""

from __future__ import annotations


class PiStudioMCPError(RuntimeError):
    """A tool call failed for a reason the caller should be told about.

    Raised for validation failures, a missing or broken ``pistudio`` binary, a
    refused call (read-only mode, budget), and a non-zero exit from the studio.
    Its message is already redacted by the code that builds it — see
    :mod:`pistudio_mcp.security` — because the caller is a model that may have
    put a credential where an identifier belongs.
    """
