"""GS1 Application Identifier structures for logistics-label carriers.

A printed label is a write endpoint into someone else's database, and it crosses
organisational boundaries by design: a supplier's label is scanned into a
customer's WMS or ERP, whose free-text fields flow onward into reports an LLM
increasingly summarises.

GS1-128 encodes data as ``(AI)value`` pairs. Most AIs are numeric and fixed
length, which carries no payload; a handful are variable-length alphanumeric,
and those are the ones worth targeting. AI 240 ("additional product
identification") is the most permissive at 30 characters.

The grammar is strict. An invalid barcode is a wasted physical test, and a
result is only meaningful if a *valid* code carried the payload, so this
validates rather than emitting whatever it is handed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# FNC1, the GS1 separator for variable-length fields.  Rendered as <GS> (ASCII
# 29) in the encoded data stream.
FNC1 = "\x1d"

# GS1 AI 82 charset: the subset of ISO 646 that GS1 permits in alphanumeric
# fields.  Excludes the characters that would break the data stream.
_AI82 = re.compile(r'^[!"%&\'()*+,\-./0-9:;<=>?A-Z_a-z]*$')


@dataclass(frozen=True, slots=True)
class ApplicationIdentifier:
    """A GS1 Application Identifier and its content rules."""

    ai: str  # e.g. "240"
    name: str  # e.g. "Additional product identification"
    max_length: int  # maximum content characters
    alphanumeric: bool  # False for digit-only AIs
    fixed_length: bool = False
    notes: str = ""

    @property
    def carries_text(self) -> bool:
        """Whether this AI can carry a text payload at all."""
        return self.alphanumeric and not self.fixed_length


# Variable-length alphanumeric AIs, which are the payload-carrying ones, plus a
# representative fixed/numeric AI so `label list` can show why those are unusable.
AI_REGISTRY: dict[str, ApplicationIdentifier] = {
    "240": ApplicationIdentifier(
        "240",
        "Additional product identification",
        30,
        True,
        notes="Most permissive general-purpose text AI. The default target.",
    ),
    "241": ApplicationIdentifier("241", "Customer part number", 30, True),
    "10": ApplicationIdentifier("10", "Batch or lot number", 20, True, notes="Ubiquitous on production labels."),
    "21": ApplicationIdentifier("21", "Serial number", 20, True, notes="Per-item, so per-item payloads."),
    "22": ApplicationIdentifier("22", "Consumer product variant", 20, True),
    "30": ApplicationIdentifier("30", "Variable count", 8, False, notes="Digit-only; cannot carry text."),
    "90": ApplicationIdentifier(
        "90",
        "Mutually agreed between trading partners",
        30,
        True,
        notes="Defined by agreement, so content rules vary by partner.",
    ),
    "91": ApplicationIdentifier("91", "Company internal information", 90, True, notes="Longest text AI at 90 chars."),
    "01": ApplicationIdentifier("01", "GTIN", 14, False, fixed_length=True, notes="Fixed 14 digits; no payload room."),
}

DEFAULT_AI = "240"


class GS1Error(ValueError):
    """Raised when a payload cannot be encoded under an AI's rules."""


def get_ai(ai: str) -> ApplicationIdentifier | None:
    """Return the registered AI, or None."""
    return AI_REGISTRY.get(ai)


def list_ais() -> list[ApplicationIdentifier]:
    """Registered AIs, text-carrying ones first, then by AI number."""
    return sorted(AI_REGISTRY.values(), key=lambda a: (not a.carries_text, a.ai))


def validate(payload: str, ai: str = DEFAULT_AI) -> tuple[bool, str]:
    """Check *payload* against the rules for *ai*.

    Returns:
        ``(ok, reason)``; reason is "" when ok.
    """
    spec = get_ai(ai)
    if spec is None:
        known = ", ".join(sorted(AI_REGISTRY))
        return False, f"Unknown Application Identifier '{ai}'. Known: {known}"

    if not spec.carries_text:
        why = "fixed-length" if spec.fixed_length else "digit-only"
        return False, f"AI {ai} ({spec.name}) is {why} and cannot carry a text payload."

    if not payload:
        return False, "Payload is empty."

    if len(payload) > spec.max_length:
        return False, (
            f"Payload is {len(payload)} chars but AI {ai} ({spec.name}) holds {spec.max_length}. "
            f"Truncate, or use AI 91 (90 chars)."
        )

    if FNC1 in payload:
        return False, "Payload contains FNC1 (GS), which terminates a variable-length field."

    if not _AI82.match(payload):
        bad = sorted({ch for ch in payload if not _AI82.match(ch)})
        rendered = ", ".join(repr(ch) for ch in bad[:8])
        hint = ""
        if " " in bad:
            # Worth calling out explicitly: GS1's AI 82 charset has no space, so
            # natural-language payloads never validate as-is.  Separator
            # substitution keeps the text legible to a model while staying in
            # charset -- an LLM reads "IGNORE_PRIOR_INSTRUCTIONS" fine.
            hint = " GS1 AI 82 has no space character; try --separator to substitute one (default '_')."
        return False, f"Payload has characters outside the GS1 AI 82 charset: {rendered}.{hint}"

    return True, ""


def to_charset(payload: str, *, separator: str = "_", upper: bool = True) -> str:
    """Coerce *payload* into the GS1 AI 82 charset.

    Substitutes whitespace with *separator* and drops anything still outside the
    charset. Uppercases by default, matching how labels are normally printed.

    The result stays legible to a model -- "IGNORE_PRIOR_INSTRUCTIONS" reads as
    the instruction it is -- which is the property that matters, since the label
    only has to survive as far as a text field an LLM later reads.
    """
    if separator and not _AI82.match(separator):
        raise GS1Error(f"Separator {separator!r} is itself outside the GS1 AI 82 charset.")
    if upper:
        payload = payload.upper()
    # Drop out-of-charset characters *before* splitting on whitespace. Doing it
    # after leaves an em dash as its own token, which joins to a separator on
    # each side and then disappears -- spending two characters of a 30-character
    # budget on nothing.
    kept = "".join(ch for ch in payload if _AI82.match(ch) or ch.isspace())
    return separator.join(kept.split())


def encode(payload: str, ai: str = DEFAULT_AI, *, gtin: str | None = None) -> str:
    """Build a GS1-128 data string carrying *payload* under *ai*.

    Args:
        payload: The text to carry.
        ai: Application Identifier to carry it in.
        gtin: Optional 14-digit GTIN to prefix as AI 01, which makes the label
            look like a normal product label rather than a bare payload.

    Returns:
        The encoded data string, FNC1-terminated when variable length.

    Raises:
        GS1Error: If the payload violates the AI's rules or the GTIN is malformed.
    """
    ok, reason = validate(payload, ai)
    if not ok:
        raise GS1Error(reason)

    parts: list[str] = []
    if gtin is not None:
        if not (gtin.isdigit() and len(gtin) == 14):
            raise GS1Error(f"GTIN must be exactly 14 digits, got '{gtin}' ({len(gtin)} chars).")
        parts.append(f"01{gtin}")

    parts.append(f"{ai}{payload}")
    # Variable-length fields are FNC1-terminated unless last in the stream; a
    # trailing separator is harmless and keeps concatenation safe.
    return FNC1.join(parts) + FNC1 if len(parts) > 1 else f"{ai}{payload}"


def human_readable(payload: str, ai: str = DEFAULT_AI, *, gtin: str | None = None) -> str:
    """The ``(AI)value`` form printed beneath a GS1 barcode."""
    parts: list[str] = []
    if gtin is not None:
        parts.append(f"(01){gtin}")
    parts.append(f"({ai}){payload}")
    return "".join(parts)


def capacity(ai: str = DEFAULT_AI) -> int:
    """Payload characters *ai* can carry, or 0 if it carries no text."""
    spec = get_ai(ai)
    if spec is None or not spec.carries_text:
        return 0
    return spec.max_length
