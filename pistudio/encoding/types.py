"""Encoder descriptor dataclass used by the encoding registry.

Mirrors ``pistudio.files.formats.types.FileFormat`` so the two registries can
share display and install-hint logic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Encoder:
    """Describes a payload text transform applied before carrier embedding.

    The pipeline is ``payload -> [encoding transform] -> [carrier]``, where both
    stages compose freely: any encoder can feed any of the file formats,
    barcodes, hosted payloads, or hardware delivery paths.
    """

    name: str  # e.g. "unicode-tags"
    description: str  # e.g. "Unicode Tags block (U+E0000-E007F)"
    encode: Callable[[str], str]
    # None when the transform cannot be inverted from its output alone.
    decode: Callable[[str], str] | None
    requires: str = ""  # pip package name, or "" for stdlib
    group: str = ""  # pip extra group, mirrors pyproject
    # False when the output carries no glyphs a human reader can see.  Drives
    # the "invisible" column in `encode list`.
    visible: bool = True
    # Output length as a multiple of input length.  Capacity planning: carriers
    # have hard ceilings (BLE name 248 bytes, WiFi SSID 32, X.509 CN 64), so a
    # 9x expansion decides whether a payload fits before anything is written.
    expansion: float = 1.0
    # Which provider's models decode this scheme most readily, per the 2026
    # Reverse CAPTCHA study: OpenAI models favour zero-width binary, Anthropic
    # models favour Unicode Tags.  "" when no affinity is documented.
    provider_affinity: str = ""
    threat_level: str = ""  # "documented" or "exploratory"
    notes: str = ""  # sanitisation and truncation caveats
