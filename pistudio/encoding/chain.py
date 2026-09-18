"""Parse and apply encoder chains.

A chain is encoder names joined by ``+``, applied left to right:
``base64+zero-width`` base64-encodes the payload, then hides the result in
zero-width characters.  Decoding reverses the order.
"""

from __future__ import annotations

from pistudio.encoding.registry import encoder_names, get_encoder
from pistudio.encoding.types import Encoder

CHAIN_SEPARATOR = "+"


class ChainError(ValueError):
    """Raised when a chain string names an unknown or unusable encoder."""


def parse_chain(chain: str) -> list[Encoder]:
    """Resolve a chain string into encoders, left to right.

    Args:
        chain: Encoder names joined by ``+``. Empty or whitespace yields [].

    Returns:
        The encoders in application order.

    Raises:
        ChainError: If a name is unknown, listing the valid names.
    """
    if not chain or not chain.strip():
        return []

    encoders: list[Encoder] = []
    for raw in chain.split(CHAIN_SEPARATOR):
        name = raw.strip()
        if not name:
            sep = CHAIN_SEPARATOR
            raise ChainError(f"Empty encoder name in chain '{chain}'. Use 'a{sep}b', not 'a{sep}{sep}b'.")
        enc = get_encoder(name)
        if enc is None:
            raise ChainError(f"Unknown encoder '{name}'. Available: {', '.join(encoder_names())}")
        encoders.append(enc)
    return encoders


def apply_chain(text: str, chain: str) -> str:
    """Apply the encoder *chain* to *text*, left to right."""
    for enc in parse_chain(chain):
        text = enc.encode(text)
    return text


def reverse_chain(text: str, chain: str) -> str:
    """Undo the encoder *chain*, decoding right to left.

    Raises:
        ChainError: If any encoder in the chain is not reversible.
    """
    encoders = parse_chain(chain)
    for enc in reversed(encoders):
        if enc.decode is None:
            raise ChainError(f"Encoder '{enc.name}' cannot be decoded, so the chain '{chain}' is one-way.")
        text = enc.decode(text)
    return text


def chain_expansion(chain: str) -> float:
    """Predicted output-length multiple for *chain*.

    Expansions compound: base64 (1.34x) then zero-width (9x) is about 12x, so a
    200-character payload needs roughly 2,400 characters of carrier. Used to
    warn before writing to a length-limited carrier.
    """
    factor = 1.0
    for enc in parse_chain(chain):
        factor *= enc.expansion
    return factor


def chain_is_visible(chain: str) -> bool:
    """Whether the chain's output still renders visible glyphs.

    The last encoder decides: hiding a visible encoding inside zero-width
    characters yields invisible output, and an empty chain leaves the payload
    as-is.
    """
    encoders = parse_chain(chain)
    if not encoders:
        return True
    return encoders[-1].visible
