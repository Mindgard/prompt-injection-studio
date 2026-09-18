"""Shared ``--payload`` resolution and name completion.

The named-payload library backs ``--payload`` across ``serve``, ``file``,
``audio``, ``barcode``, ``encode`` and every hardware deploy. The three-line
lookup behind it had been written eight times, each copy slightly different:
some filtered by prefix, some did not; some went through ``payload_names()``
and some through ``list_payloads()``.

That divergence is how a real gap hid. ``audio``'s usage documented
``--payload`` while ``audio live`` never parsed it, so the flag was reported as
unknown -- a command advertising an option it did not have. One helper, used
everywhere, plus a guardrail test that every command documenting the flag also
parses and completes it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

__all__ = ["complete_payload_names", "payload_text", "resolve_payload_text"]


def complete_payload_names(source: StudioProtocol | str, prefix: str = "") -> list[str]:
    """Payload names starting with *prefix*, for tab completion.

    Args:
        source: Either the studio context or a session directory. ``hw``'s
            completers take a bare ``session_dir`` so they stay testable
            without constructing a Studio, so both are accepted rather than
            forcing every caller into one shape.
        prefix: Only names starting with this are returned.

    Never raises: a completion callback that throws breaks the prompt, so a
    missing or unreadable library yields no suggestions instead.
    """
    try:
        from pistudio.hardware.payloads import payload_names

        session_dir = source if isinstance(source, str) else source.session_dir
        return [name for name in payload_names(session_dir) if name.startswith(prefix)]
    except Exception:
        return []


def payload_text(shell: StudioProtocol, name: str) -> str | None:
    """Resolve a payload *name* to its text, or None after reporting the error.

    The error names the closest match rather than just failing, because a
    mistyped payload name is the common case and the library has dozens of
    entries.
    """
    from pistudio.hardware.payloads import get_payload

    found = get_payload(name, shell.session_dir)
    if found is not None:
        return found[0].text

    import difflib

    known = complete_payload_names(shell)
    close = difflib.get_close_matches(name, known, n=1, cutoff=0.5)
    hint = f" Did you mean '{close[0]}'?" if close else ""
    shell.out.error(f"Payload '{name}' not found.{hint} List them with 'payloads list'.")
    return None


def resolve_payload_text(
    shell: StudioProtocol,
    positional: list[str],
    name: str | None,
    *,
    usage: str,
) -> str | None:
    """Resolve payload text from inline words or a ``--payload`` name.

    Args:
        shell: The studio context.
        positional: Non-flag tokens, joined with spaces when present.
        name: The ``--payload`` value, if given.
        usage: A one-line usage hint shown when neither source is present.

    Returns:
        The payload text, or None after reporting the problem.
    """
    inline = " ".join(positional).strip()

    if inline and name:
        # Silently preferring one would make the other look broken.
        shell.out.error("Give either inline text or --payload <name>, not both.")
        return None
    if name:
        return payload_text(shell, name)
    if inline:
        return inline

    shell.out.error(usage)
    return None
