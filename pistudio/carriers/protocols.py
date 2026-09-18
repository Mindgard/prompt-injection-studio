"""Wireless identifier fields as payload carriers.

A device name or network SSID is broadcast to everyone in range, gets written
into scan logs and asset inventories, and is then read back by whatever
summarises those inventories. No pairing, no association, no authentication:
the payload travels because *advertising* is what these fields are for.

The ceilings here are the tight ones in the tool -- a WiFi SSID is 32 bytes,
which is less than one sentence -- so capacity planning matters more than
anywhere else. Byte-counted rather than character-counted, because that is what
the specs say: a 30-character Unicode Tags payload is 120 UTF-8 bytes and does
not fit a field that accepts 32.

This module describes the fields and measures payloads against them. It does
not transmit: broadcasting on these radios is the hardware layer's business,
and the ``hw`` command owns that.
"""

from __future__ import annotations

from pistudio.carriers.types import Carrier, CarrierField

# IEEE 802.11: the SSID element is 0-32 octets.
SSID_MAX_BYTES = 32

# Bluetooth Core: the Complete Local Name in an advertising packet shares a
# 31-octet payload with the other AD structures, each costing 2 bytes of
# header. The GAP device name read over GATT after connecting is far longer,
# which is the same strict-field/loose-field split X.509 has.
BLE_ADV_NAME_MAX_BYTES = 29
BLE_GATT_NAME_MAX_BYTES = 248

# mDNS/DNS-SD instance names are UTF-8 and capped by the DNS label limit.
MDNS_INSTANCE_MAX_BYTES = 63

WIFI_CARRIER = Carrier(
    name="wifi",
    description="802.11 SSID and related identifiers",
    sink="Wireless scan logs, asset inventories, captive portals",
    threat_level="documented",
    aliases=("ssid", "802.11"),
    fields=(
        CarrierField(
            "ssid",
            "SSID",
            SSID_MAX_BYTES,
            unit="bytes",
            notes="IEEE 802.11 caps this at 32 octets, the tightest ceiling in the tool.",
        ),
    ),
    notes="Describes the field only; transmitting is the hw command's job.",
)

BLE_CARRIER = Carrier(
    name="ble",
    description="Bluetooth Low Energy device name fields",
    sink="Bluetooth scan logs, device inventories, pairing dialogs",
    threat_level="documented",
    aliases=("bluetooth",),
    fields=(
        CarrierField(
            "gatt_name",
            "GAP device name (GATT)",
            BLE_GATT_NAME_MAX_BYTES,
            unit="bytes",
            notes="Read after connecting, so it is far roomier than the advertised name.",
        ),
        CarrierField(
            "adv_name",
            "Complete Local Name (advertising)",
            BLE_ADV_NAME_MAX_BYTES,
            unit="bytes",
            notes="Shares a 31-octet advertising payload with other AD structures, so ~29 usable.",
        ),
    ),
    notes="The advertised name reaches every scanner in range without pairing.",
)

MDNS_CARRIER = Carrier(
    name="mdns",
    description="mDNS/DNS-SD service instance names",
    sink="Service discovery logs, network inventories",
    threat_level="exploratory",
    aliases=("bonjour", "dns-sd"),
    fields=(
        CarrierField(
            "instance_name",
            "Service instance name",
            MDNS_INSTANCE_MAX_BYTES,
            unit="bytes",
            notes="UTF-8 permitted by RFC 6763, bounded by the 63-octet DNS label limit.",
        ),
    ),
    notes="Advertised unauthenticated on the local link.",
)
