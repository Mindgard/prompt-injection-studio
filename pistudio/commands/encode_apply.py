"""Shared ``--encode`` handling for the commands that deliver payloads.

One helper so `file`, `barcode`, `serve`, and the `hw` deploys all report chain
errors and capacity warnings identically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pistudio.encoding import ChainError, apply_chain

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

# Carrier names accepted here that ``pistudio.carriers`` resolves, mapped to
# the (carrier, field) the registry knows them by.  The registry owns the
# ceilings and, crucially, their *units*: an SSID is 32 bytes, not 32
# characters, and a second copy of that number invited the two to disagree.
_REGISTRY_ALIASES: dict[str, tuple[str, str]] = {
    "ssid": ("wifi", "ssid"),
    "ble-name": ("ble", "gatt_name"),
    "ble-adv": ("ble", "adv_name"),
    "x509-cn": ("x509", "common_name"),
    "x509-san": ("x509", "san_dns"),
    "mdns": ("mdns", "instance_name"),
}

# Ceilings with no registry entry yet, in characters.  These are carriers whose
# capacity depends on the physical tag or symbology rather than a protocol
# field, so they are not modelled as carrier fields.
_LOCAL_LIMITS: dict[str, int] = {
    "nfc-ndef": 500,
    "code39": 80,
}


def apply_encoding(shell: StudioProtocol, text: str, chain: str) -> str | None:
    """Apply the encoder *chain* to *text*, reporting failures to the user.

    Returns:
        The encoded text, or None if the chain was invalid, in which case the
        error has already been printed.
    """
    try:
        encoded = apply_chain(text, chain)
    except ChainError as e:
        shell.out.error(str(e))
        return None

    if not shell.json_mode:
        ratio = len(encoded) / len(text) if text else 1.0
        shell.out.info(f"Encoded with '{chain}': {len(text)} -> {len(encoded)} chars ({ratio:.1f}x)")
    return encoded


def carrier_limit(carrier: str) -> tuple[int, str] | None:
    """The ceiling for *carrier* and the unit it is counted in.

    Resolves through ``pistudio.carriers`` where the carrier is a modelled
    protocol field, so there is one source of truth for both the number and its
    unit. Returns None for an unknown carrier.
    """
    alias = _REGISTRY_ALIASES.get(carrier)
    if alias is not None:
        from pistudio.carriers import get_carrier

        resolved = get_carrier(alias[0])
        spec = resolved.get_field(alias[1]) if resolved else None
        if spec is not None:
            return spec.max_length, spec.unit
    local = _LOCAL_LIMITS.get(carrier)
    return (local, "chars") if local is not None else None


def warn_if_over_capacity(shell: StudioProtocol, text: str, chain: str, carrier: str) -> None:
    """Warn when an encoded payload will not fit *carrier*.

    Advisory only: limits vary by tag type, font, and firmware, so this reports
    rather than blocks. Silent truncation is the failure this exists to prevent
    -- a truncated payload looks like a delivered one.

    Measures in the carrier's own unit. Counting characters against a byte
    ceiling under-reports for any non-ASCII payload: "Ignore all" under
    variation-selectors is 20 characters but 63 bytes, so a character count
    stays silent about a payload that overflows a 32-byte SSID twice over.
    """
    resolved = carrier_limit(carrier)
    if resolved is None:
        return
    limit, unit = resolved

    try:
        encoded = apply_chain(text, chain)
    except ChainError:
        return  # apply_encoding reports the invalid chain

    projected = len(encoded.encode("utf-8")) if unit == "bytes" else len(encoded)
    if projected <= limit:
        return

    # Budget is expressed in payload characters, which is what the operator
    # controls, derived from the measured cost per character of this chain.
    per_char = projected / len(text) if text else 1.0
    budget = int(limit / per_char) if per_char else limit
    shell.out.warn(
        f"Encoded payload is {projected} {unit} but {carrier} holds ~{limit} {unit}. "
        f"Expect truncation. Budget for '{chain}' on {carrier}: ~{budget} chars of payload."
    )
