"""Homoglyph substitution: Latin characters replaced by lookalike code points.

The output is *visible* but reads as ordinary text to a human, while tokenizing
and string-matching differently.  This defeats exact-match denylists and
keyword filters without concealing the payload from view.

Unit 42's in-the-wild survey records homoglyph substitution as one of its
catalogued instruction-obfuscation techniques.  The substitution is one-way in
practice: several Latin letters have no distinct Cyrillic or Greek lookalike, so
only a subset of characters is mapped and the inverse is ambiguous for text
that legitimately contained Cyrillic.
"""

from __future__ import annotations

# Latin -> visually equivalent Cyrillic/Greek code point.  Restricted to pairs
# that render near-identically in common UI fonts; near-misses would give the
# payload away to a reader, which is the one property this encoder must keep.
_CONFUSABLES: dict[str, str] = {
    "a": "а",  # CYRILLIC SMALL LETTER A
    "c": "с",  # CYRILLIC SMALL LETTER ES
    "e": "е",  # CYRILLIC SMALL LETTER IE
    "i": "і",  # CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I
    "j": "ј",  # CYRILLIC SMALL LETTER JE
    "o": "о",  # CYRILLIC SMALL LETTER O
    "p": "р",  # CYRILLIC SMALL LETTER ER
    "s": "ѕ",  # CYRILLIC SMALL LETTER DZE
    "x": "х",  # CYRILLIC SMALL LETTER HA
    "y": "у",  # CYRILLIC SMALL LETTER U
    "A": "А",
    "B": "В",
    "C": "С",
    "E": "Е",
    "H": "Н",
    "I": "І",
    "J": "Ј",
    "K": "К",
    "M": "М",
    "O": "О",
    "P": "Р",
    "S": "Ѕ",
    "T": "Т",
    "X": "Х",
    "Y": "У",
}

_REVERSE: dict[str, str] = {v: k for k, v in _CONFUSABLES.items()}


def encode_confusable(text: str) -> str:
    """Replace Latin characters in *text* with homoglyphs where one exists."""
    return "".join(_CONFUSABLES.get(ch, ch) for ch in text)


def decode_confusable(text: str) -> str:
    """Map known homoglyphs back to Latin.

    Lossy for input that legitimately contained Cyrillic or Greek: this cannot
    distinguish a substituted "а" from an intentional one.  Provided for
    verification during testing, not as a faithful inverse.
    """
    return "".join(_REVERSE.get(ch, ch) for ch in text)


def confusable_coverage(text: str) -> float:
    """Fraction of characters in *text* that this encoder can substitute.

    Low coverage means the payload is barely altered, so a denylist may still
    match it.  Surfaced by ``encode preview`` so an operator can tell whether
    the transform is doing anything useful for a given payload.
    """
    if not text:
        return 0.0
    return sum(1 for ch in text if ch in _CONFUSABLES) / len(text)
