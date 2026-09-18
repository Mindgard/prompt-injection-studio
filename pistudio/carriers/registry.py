"""Carrier registry mapping names to Carrier descriptors, plus lookup helpers.

Mirrors ``pistudio.encoding.registry`` so both registries can be walked with
one loop.
"""

from __future__ import annotations

from pistudio.carriers.certs import X509_CARRIER
from pistudio.carriers.protocols import BLE_CARRIER, MDNS_CARRIER, WIFI_CARRIER
from pistudio.carriers.types import Carrier, CarrierField

CARRIER_REGISTRY: dict[str, Carrier] = {
    carrier.name: carrier for carrier in (X509_CARRIER, BLE_CARRIER, WIFI_CARRIER, MDNS_CARRIER)
}

# Aliases resolve to the same descriptor, so "bluetooth" and "ble" agree.
_ALIASES: dict[str, str] = {alias: c.name for c in CARRIER_REGISTRY.values() for alias in c.aliases}


def get_carrier(name: str) -> Carrier | None:
    """Look up a carrier by name or alias, case-insensitively."""
    key = name.strip().lower()
    if key in CARRIER_REGISTRY:
        return CARRIER_REGISTRY[key]
    return CARRIER_REGISTRY.get(_ALIASES.get(key, ""))


def carrier_names() -> list[str]:
    """Canonical carrier names, in registry order."""
    return list(CARRIER_REGISTRY)


def list_carriers() -> list[Carrier]:
    """Every registered carrier, in registry order.

    Registry order is editorial: the roomiest and best-documented carrier
    first, so a reader meets the useful one before the exploratory ones.
    """
    return list(CARRIER_REGISTRY.values())


def tightest_field() -> tuple[Carrier, CarrierField]:
    """The carrier and field with the smallest non-zero ceiling.

    Useful as the worst case for capacity planning: a payload that fits this
    fits everywhere.
    """
    candidates = [(c, f) for c in CARRIER_REGISTRY.values() for f in c.fields if not f.unbounded]
    return min(candidates, key=lambda pair: pair[1].max_length)
