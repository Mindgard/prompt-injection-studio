"""Payload encoding transforms, applied before carrier embedding.

The delivery pipeline is::

    payload -> [encoding transform] -> [carrier]

Both stages compose freely: any encoder feeds any of the file formats,
barcodes, hosted payloads, or hardware delivery paths.

Encoders exist for three reasons:

1. **Concealment.** Zero-width, Unicode Tags, and variation selectors render as
   nothing, so the payload is invisible in a log line or a document.
2. **Filter evasion.** Homoglyphs and bidi overrides read as ordinary text but
   tokenize and string-match differently.
3. **Targeting.** The 2026 Reverse CAPTCHA study found invisible-Unicode
   compliance is provider-specific -- OpenAI models decode zero-width binary,
   Anthropic models prefer Unicode Tags -- and that tool access amplifies
   compliance from under 17% to 98-100%. See ``Encoder.provider_affinity``.
"""

from pistudio.encoding.chain import (
    CHAIN_SEPARATOR,
    ChainError,
    apply_chain,
    chain_expansion,
    chain_is_visible,
    parse_chain,
    reverse_chain,
)
from pistudio.encoding.registry import (
    ENCODER_REGISTRY,
    encoder_names,
    get_encoder,
    list_encoders,
)
from pistudio.encoding.types import Encoder

__all__ = [
    "CHAIN_SEPARATOR",
    "ENCODER_REGISTRY",
    "ChainError",
    "Encoder",
    "apply_chain",
    "chain_expansion",
    "chain_is_visible",
    "encoder_names",
    "get_encoder",
    "list_encoders",
    "parse_chain",
    "reverse_chain",
]
