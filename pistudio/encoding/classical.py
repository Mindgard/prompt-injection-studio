"""Classical reversible encodings: base64, hex, URL, HTML entities, ROT-13.

Visible and well known.  Their value is as chain elements -- ``base64`` then
``zero-width`` produces nested encoding requiring two decode passes, one of
Unit 42's catalogued techniques -- and as a control condition when measuring
which transforms a pipeline strips.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import html
import urllib.parse


def encode_base64(text: str) -> str:
    """Base64-encode *text* (UTF-8)."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def decode_base64(text: str) -> str:
    """Decode base64 *text*, tolerating missing padding."""
    padded = text + "=" * (-len(text) % 4)
    try:
        return base64.b64decode(padded).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        return ""


def encode_hex(text: str) -> str:
    """Hex-encode *text* (UTF-8), lowercase, no separators."""
    return text.encode("utf-8").hex()


def decode_hex(text: str) -> str:
    """Decode hex *text*, ignoring whitespace."""
    compact = "".join(text.split())
    try:
        return bytes.fromhex(compact).decode("utf-8", errors="replace")
    except ValueError:
        return ""


def encode_url(text: str) -> str:
    """Percent-encode *text*, escaping every reserved character."""
    return urllib.parse.quote(text, safe="")


def decode_url(text: str) -> str:
    """Decode percent-encoded *text*."""
    return urllib.parse.unquote(text)


def encode_html_entity(text: str) -> str:
    """Encode every character of *text* as a decimal HTML entity.

    Encodes all characters rather than only the reserved ones: partial encoding
    leaves the instruction readable to a text scanner, which defeats the point.
    """
    return "".join(f"&#{ord(ch)};" for ch in text)


def decode_html_entity(text: str) -> str:
    """Decode numeric HTML entities in *text*.

    Deliberately does not use :func:`html.unescape`. That applies the HTML5
    parser error-handling rules, which silently drop C0 controls (``&#31;`` ->
    ``""``) and remap the C1 range (``&#128;`` -> ``€``). Those rules are right
    for rendering a document and wrong for recovering a payload, so numeric
    references are decoded directly and named entities are left to the stdlib.
    """
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "&" and (end := text.find(";", i)) != -1:
            body = text[i + 1 : end]
            if body.startswith("#"):
                digits = body[1:]
                try:
                    cp = int(digits[1:], 16) if digits[:1] in ("x", "X") else int(digits)
                except ValueError:
                    cp = -1
                # Surrogates are not valid scalar values; chr() accepts them but
                # they cannot round-trip through UTF-8.
                if 0 <= cp <= 0x10FFFF and not 0xD800 <= cp <= 0xDFFF:
                    out.append(chr(cp))
                    i = end + 1
                    continue
        out.append(text[i])
        i += 1
    joined = "".join(out)
    # Named entities (&amp;, &lt;) only appear in text this encoder did not
    # produce; hand those to the stdlib.
    return html.unescape(joined) if "&" in joined else joined


def encode_rot13(text: str) -> str:
    """ROT-13 *text*.

    Trivially reversible and symmetric, so it offers no concealment against an
    attacker-aware filter.  Kept because spotlighting's own authors cite ROT-13
    as the cautionary example: a defence that decodes input can be fed a
    pre-encoded payload that decodes *into* the attack.
    """
    return codecs.encode(text, "rot13")


def decode_rot13(text: str) -> str:
    """ROT-13 is its own inverse."""
    return codecs.encode(text, "rot13")
