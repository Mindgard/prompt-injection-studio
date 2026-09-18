"""Carrier descriptors: where a payload can be written, and how much fits.

Mirrors ``pistudio.encoding.types.Encoder`` so a caller can walk encoders and
carriers as one cross-product rather than special-casing each.

The asymmetry worth naming: an encoder has a single ``expansion`` multiplier,
but a carrier has *several* fields with different ceilings, and the gap between
them is usually the finding. An X.509 certificate caps the Common Name at 64
characters while a Subject Alternative Name of the same certificate carries
orders of magnitude more -- so the field a tool validates strictly is rarely
the field an attacker uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# How a field's ceiling is counted. Unicode payloads make this load-bearing:
# a 30-character Unicode Tags payload is 30 codepoints but 120 UTF-8 bytes, so
# a byte-limited carrier rejects what a character-limited one accepts.
LIMIT_UNITS = ("bytes", "chars")


@dataclass(frozen=True, slots=True)
class CarrierField:
    """One writable field within a carrier, and its capacity."""

    name: str  # e.g. "common_name"
    label: str  # e.g. "Subject CN"
    max_length: int  # ceiling in `unit`s; 0 means no practical limit
    unit: str = "chars"  # one of LIMIT_UNITS
    # Whether the field is normally shown to a human somewhere in the pipeline.
    # An invisible field is a better carrier: nobody proofreads it.
    human_visible: bool = True
    # Whether the spec constrains the charset, which is what breaks payloads
    # before length ever does (see GS1 AI 82, which has no space character).
    restricted_charset: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        """Reject a unit the capacity maths would silently misread."""
        if self.unit not in LIMIT_UNITS:
            raise ValueError(f"CarrierField {self.name!r} has unit {self.unit!r}; expected one of {LIMIT_UNITS}")
        if self.max_length < 0:
            raise ValueError(f"CarrierField {self.name!r} has negative max_length {self.max_length}")

    @property
    def unbounded(self) -> bool:
        """Whether the field has no practical ceiling."""
        return self.max_length == 0

    def measure(self, payload: str) -> int:
        """Length of *payload* in this field's unit."""
        return len(payload.encode("utf-8")) if self.unit == "bytes" else len(payload)

    def fits(self, payload: str) -> bool:
        """Whether *payload* is within this field's ceiling."""
        return self.unbounded or self.measure(payload) <= self.max_length

    def headroom(self, payload: str) -> int:
        """Capacity left after *payload*, negative when it overflows.

        Returns 0 for an unbounded field rather than a fictional number: the
        honest answer to "how much room is left" is "the limit is elsewhere".
        """
        if self.unbounded:
            return 0
        return self.max_length - self.measure(payload)


@dataclass(frozen=True, slots=True)
class Carrier:
    """A destination a payload can be written into.

    The pipeline is ``payload -> [encoding transform] -> [carrier]``. A carrier
    describes the destination's capacity and reach; it does not generate the
    artifact, which is the job of the module that owns the format.
    """

    name: str  # e.g. "x509"
    description: str
    fields: tuple[CarrierField, ...]
    requires: str = ""  # pip package name, or "" for stdlib
    group: str = ""  # pip extra group, mirrors pyproject
    # Where the payload ends up being read. Names the sink a delivery result
    # should be scored against.
    sink: str = ""
    threat_level: str = ""  # "documented" or "exploratory"
    notes: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Reject a carrier with no fields or duplicate field names."""
        if not self.fields:
            raise ValueError(f"Carrier {self.name!r} declares no fields")
        names = [f.name for f in self.fields]
        if len(names) != len(set(names)):
            duplicated = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"Carrier {self.name!r} has duplicate field names: {', '.join(duplicated)}")

    def get_field(self, name: str) -> CarrierField | None:
        """Look up a field by name."""
        for f in self.fields:
            if f.name == name:
                return f
        return None

    @property
    def default_field(self) -> CarrierField:
        """The field a payload goes in unless told otherwise.

        The first declared field, so registry order is the editorial choice:
        declare the field an operator would actually reach for first.
        """
        return self.fields[0]

    @property
    def widest_field(self) -> CarrierField:
        """The roomiest field, which is where an overlong payload should go.

        Unbounded fields win outright; among bounded ones, the largest ceiling.
        Byte and character limits are compared as declared -- a byte limit is
        the stricter reading for Unicode, so this never over-promises.
        """
        unbounded = [f for f in self.fields if f.unbounded]
        if unbounded:
            return unbounded[0]
        return max(self.fields, key=lambda f: f.max_length)

    def fields_that_fit(self, payload: str) -> tuple[CarrierField, ...]:
        """Every field *payload* fits in, widest ceiling first."""
        fitting = [f for f in self.fields if f.fits(payload)]
        return tuple(sorted(fitting, key=lambda f: (not f.unbounded, -f.max_length)))
