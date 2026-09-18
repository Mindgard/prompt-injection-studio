"""Carriers: where a payload can be written, and how much of it fits.

The pipeline is ``payload -> [encoding transform] -> [carrier]``. This package
owns the second stage's *capacity* question -- which fields exist, what they
cap at, and whether a given payload survives the trip -- so that can be asked
before a physical test is spent.

Carriers whose artifacts this package also generates (X.509) live beside the
descriptor; carriers owned by another layer (the radios, driven by ``hw``) are
described here but transmitted there.
"""

from __future__ import annotations

from pistudio.carriers.certs import (
    X509_CARRIER,
    CapacityReport,
    CertError,
    FieldFit,
    analyse,
    generate,
    read_payload,
)
from pistudio.carriers.protocols import BLE_CARRIER, MDNS_CARRIER, WIFI_CARRIER
from pistudio.carriers.registry import (
    CARRIER_REGISTRY,
    carrier_names,
    get_carrier,
    list_carriers,
    tightest_field,
)
from pistudio.carriers.types import LIMIT_UNITS, Carrier, CarrierField

__all__ = [
    "BLE_CARRIER",
    "CARRIER_REGISTRY",
    "LIMIT_UNITS",
    "MDNS_CARRIER",
    "WIFI_CARRIER",
    "X509_CARRIER",
    "CapacityReport",
    "Carrier",
    "CarrierField",
    "CertError",
    "FieldFit",
    "analyse",
    "carrier_names",
    "generate",
    "get_carrier",
    "list_carriers",
    "read_payload",
    "tightest_field",
]
