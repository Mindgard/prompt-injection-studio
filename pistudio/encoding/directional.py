"""Unicode bidirectional override: visible order reversed, logical order kept.

U+202E RIGHT-TO-LEFT OVERRIDE forces the following characters to render
right-to-left.  The bytes in the file are unchanged, so a model reading the raw
text sees the payload in its original order while a human reading the rendered
output sees it backwards.

This is the mechanism behind Boucher & Anderson's Trojan Source (2021), which
used bidi controls to make source code review disagree with the compiler.  Unit
42 records the same primitive being used against LLM agents.
"""

from __future__ import annotations

_RLO = "‮"  # RIGHT-TO-LEFT OVERRIDE
_LRO = "‭"  # LEFT-TO-RIGHT OVERRIDE
_PDF = "‬"  # POP DIRECTIONAL FORMATTING


def encode_bidi_override(text: str) -> str:
    """Wrap *text* in an RLO/PDF pair with the characters pre-reversed.

    Reversing the characters *and* applying the override means the rendered
    result reads normally to a human while the logical byte order -- what the
    model tokenizes -- is the reversed form.  Terminals and editors differ in
    how faithfully they apply bidi, so treat rendering as target-dependent and
    verify against the actual sink.
    """
    return f"{_RLO}{text[::-1]}{_PDF}"


def decode_bidi_override(text: str) -> str:
    """Strip directional controls and undo the character reversal."""
    stripped = text.replace(_RLO, "").replace(_LRO, "").replace(_PDF, "")
    return stripped[::-1]
