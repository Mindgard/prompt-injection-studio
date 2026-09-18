"""Encoder registry mapping names to Encoder descriptors, plus lookup helpers."""

from __future__ import annotations

from pistudio.encoding.classical import (
    decode_base64,
    decode_hex,
    decode_html_entity,
    decode_rot13,
    decode_url,
    encode_base64,
    encode_hex,
    encode_html_entity,
    encode_rot13,
    encode_url,
)
from pistudio.encoding.confusable import decode_confusable, encode_confusable
from pistudio.encoding.directional import decode_bidi_override, encode_bidi_override
from pistudio.encoding.invisible import (
    decode_unicode_tags,
    decode_variation_selectors,
    decode_zero_width,
    encode_unicode_tags,
    encode_variation_selectors,
    encode_zero_width,
)
from pistudio.encoding.types import Encoder

ENCODER_REGISTRY: dict[str, Encoder] = {
    # ── Invisible (no rendered glyphs) ──
    "zero-width": Encoder(
        "zero-width",
        "Zero-width binary (ZWSP/ZWNJ bits, ZWJ separator)",
        encode_zero_width,
        decode_zero_width,
        visible=False,
        expansion=9.0,
        provider_affinity="openai",
        threat_level="documented",
        notes=(
            "9 characters per input byte -- the highest expansion here. A 32-byte "
            "SSID holds roughly 3 payload characters. Survives HTML text nodes; "
            "stripped by aggressive Unicode normalisation (NFKC)."
        ),
    ),
    "unicode-tags": Encoder(
        "unicode-tags",
        "Unicode Tags block, U+E0000-E007F (Rehberger / Copilot vector)",
        encode_unicode_tags,
        decode_unicode_tags,
        visible=False,
        expansion=1.0,
        provider_affinity="anthropic",
        threat_level="documented",
        notes=(
            "Deprecated since Unicode 5.0 but retained as distinct tokenizer "
            "tokens. Non-ASCII is percent-escaped first, so expansion rises to "
            "roughly 3x for CJK payloads."
        ),
    ),
    "variation-selectors": Encoder(
        "variation-selectors",
        "Variation selectors VS1-VS16, U+FE00-FE0F (4 bits each)",
        encode_variation_selectors,
        decode_variation_selectors,
        visible=False,
        expansion=2.0,
        threat_level="exploratory",
        notes=(
            "Combining marks on a word-joiner carrier. Alters tokenization "
            "without changing rendered text. Font and shaper dependent -- verify "
            "against the real sink."
        ),
    ),
    # ── Visible but disguised ──
    "confusable": Encoder(
        "confusable",
        "Homoglyph substitution (Latin -> Cyrillic/Greek lookalikes)",
        encode_confusable,
        decode_confusable,
        visible=True,
        expansion=1.0,
        threat_level="documented",
        notes=(
            "Reads as ordinary text; defeats exact-match denylists. Only 25 "
            "characters have safe lookalikes, so coverage is partial -- check "
            "`encode preview` before relying on it."
        ),
    ),
    "bidi-override": Encoder(
        "bidi-override",
        "RTL override U+202E, visible order reversed (Trojan Source)",
        encode_bidi_override,
        decode_bidi_override,
        visible=True,
        expansion=1.05,
        threat_level="documented",
        notes="Rendering is target-dependent: terminals and editors apply bidi inconsistently.",
    ),
    # ── Classical ──
    "base64": Encoder(
        "base64",
        "Base64",
        encode_base64,
        decode_base64,
        expansion=1.34,
        threat_level="documented",
        notes="Chain element for nested encoding, e.g. base64+zero-width.",
    ),
    "hex": Encoder("hex", "Hex (lowercase, no separators)", encode_hex, decode_hex, expansion=2.0),
    "url": Encoder(
        "url",
        "Percent-encoding",
        encode_url,
        decode_url,
        # Typical prose, where only spaces and punctuation expand. Rises toward
        # 3x for payloads that are mostly reserved characters, and 9x for
        # multi-byte text, since each UTF-8 byte becomes %XX.
        expansion=1.3,
    ),
    "html-entity": Encoder(
        "html-entity",
        "Decimal HTML entities",
        encode_html_entity,
        decode_html_entity,
        # 4-6 chars per input char: "&#" + 1-3 digits + ";".
        expansion=5.8,
        threat_level="documented",
        notes="Decodes numeric references directly rather than via html.unescape, which drops C0 and remaps C1.",
    ),
    "rot13": Encoder(
        "rot13",
        "ROT-13 (symmetric; no concealment against an aware filter)",
        encode_rot13,
        decode_rot13,
        expansion=1.0,
        threat_level="exploratory",
        notes="Included as the spotlighting cautionary case: a decoding defence can be fed a pre-encoded payload.",
    ),
}


def get_encoder(name: str) -> Encoder | None:
    """Return the encoder registered under *name*, or None."""
    return ENCODER_REGISTRY.get(name)


def encoder_names() -> list[str]:
    """Registered encoder names, in registry (curated) order."""
    return list(ENCODER_REGISTRY)


def list_encoders() -> list[Encoder]:
    """All registered encoders, in registry (curated) order."""
    return list(ENCODER_REGISTRY.values())
