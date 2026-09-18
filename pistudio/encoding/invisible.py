"""Encoders whose output renders as no visible glyphs.

Three independent schemes, each documented against a published attack:

- **zero-width binary** -- ZWSP/ZWNJ as bits, ZWJ as a byte separator.
- **Unicode Tags** -- the deprecated U+E0000 block, the vector Rehberger used
  to smuggle instructions into Microsoft Copilot.
- **variation selectors** -- VS1-VS16 appended to a carrier character, which
  alters tokenization without changing the rendered text (Gao et al.).

All three encode **UTF-8 bytes rather than code points**.  A fixed 8-bit
per-character format silently truncates anything above U+00FF -- a CJK code
point needs 15 bits -- which corrupts non-Latin-1 payloads.  The byte-oriented
form round-trips arbitrary Unicode.
"""

from __future__ import annotations

# ── Zero-width binary ────────────────────────────────────────────

_ZWSP = "​"  # zero-width space        -> bit 0
_ZWNJ = "‌"  # zero-width non-joiner   -> bit 1
_ZWJ = "‍"  # zero-width joiner       -> byte separator


def encode_zero_width(text: str) -> str:
    """Encode *text* as zero-width characters, one group per UTF-8 byte."""
    out: list[str] = []
    for byte in text.encode("utf-8"):
        out.extend(_ZWSP if bit == "0" else _ZWNJ for bit in format(byte, "08b"))
        out.append(_ZWJ)
    return "".join(out)


def decode_zero_width(text: str) -> str:
    """Recover text encoded by :func:`encode_zero_width`.

    Ignores any character outside the three-symbol alphabet, so a payload
    survives being embedded in surrounding visible content.
    """
    bits: list[str] = []
    out = bytearray()
    for ch in text:
        if ch == _ZWSP:
            bits.append("0")
        elif ch == _ZWNJ:
            bits.append("1")
        elif ch == _ZWJ:
            if len(bits) == 8:
                out.append(int("".join(bits), 2))
            bits.clear()
    return out.decode("utf-8", errors="replace")


# ── Unicode Tags (U+E0000 block) ─────────────────────────────────

_TAG_BASE = 0xE0000
_TAG_MIN = 0xE0001
_TAG_MAX = 0xE007F


def encode_unicode_tags(text: str) -> str:
    """Map each UTF-8 byte of *text* into the Unicode Tags block.

    Bytes are offset by U+E0000.  The block only spans U+E0001-U+E007F, so
    bytes above 0x7E are escaped as printable ASCII first: the encoder emits
    the percent-encoded form, keeping every emitted code point inside the
    block while still round-tripping arbitrary Unicode.
    """
    escaped = _percent_escape(text)
    return "".join(chr(_TAG_BASE + ord(ch)) for ch in escaped)


def decode_unicode_tags(text: str) -> str:
    """Recover text encoded by :func:`encode_unicode_tags`."""
    chars = [chr(ord(ch) - _TAG_BASE) for ch in text if _TAG_MIN <= ord(ch) <= _TAG_MAX]
    return _percent_unescape("".join(chars))


def _percent_escape(text: str) -> str:
    """Reduce *text* to printable ASCII, percent-escaping everything else."""
    out: list[str] = []
    for byte in text.encode("utf-8"):
        # 0x25 is '%' itself, which must be escaped to stay unambiguous.
        if 0x20 <= byte <= 0x7E and byte != 0x25:
            out.append(chr(byte))
        else:
            out.append(f"%{byte:02X}")
    return "".join(out)


def _percent_unescape(text: str) -> str:
    """Invert :func:`_percent_escape`."""
    out = bytearray()
    i = 0
    while i < len(text):
        if text[i] == "%" and i + 2 < len(text):
            try:
                out.append(int(text[i + 1 : i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass  # malformed escape; fall through and take the literal
        out.extend(text[i].encode("utf-8"))
        i += 1
    return out.decode("utf-8", errors="replace")


# ── Variation selectors ──────────────────────────────────────────

# VS1-VS16 live at U+FE00-U+FE0F: 16 selectors, so 4 bits each.
_VS_BASE = 0xFE00
_VS_COUNT = 16
# A visible carrier the selectors attach to.  Selectors are combining marks;
# without a base character they render inconsistently across shapers.
_VS_CARRIER = "⁠"  # word joiner: no width, no line-break opportunity


def encode_variation_selectors(text: str) -> str:
    """Encode *text* as variation selectors, two per UTF-8 byte (4 bits each)."""
    out: list[str] = [_VS_CARRIER]
    for byte in text.encode("utf-8"):
        out.append(chr(_VS_BASE + (byte >> 4)))
        out.append(chr(_VS_BASE + (byte & 0x0F)))
    return "".join(out)


def decode_variation_selectors(text: str) -> str:
    """Recover text encoded by :func:`encode_variation_selectors`."""
    nibbles = [ord(ch) - _VS_BASE for ch in text if _VS_BASE <= ord(ch) < _VS_BASE + _VS_COUNT]
    out = bytearray()
    # Trailing odd nibble means truncation in transit; drop it rather than
    # fabricating a byte from half a pair.
    for i in range(0, len(nibbles) - len(nibbles) % 2, 2):
        out.append((nibbles[i] << 4) | nibbles[i + 1])
    return out.decode("utf-8", errors="replace")
