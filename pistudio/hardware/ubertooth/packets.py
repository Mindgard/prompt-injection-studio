"""BLE advertising packet construction for prompt injection delivery.

Implements five delivery strategies for BLE PI:
1. Micro-payload: single AD field, 25-26 bytes
2. Multi-device flood: numbered chunks across N fake devices
3. BLE 5.0 extended advertising: up to 1,650 bytes single device
4. URL redirect: broadcast short URL, host payload elsewhere
5. Multi-AD packing: maximize single device across ADV + SCAN_RSP
"""

import struct
import subprocess

# AD Type constants (Bluetooth SIG assigned numbers)
AD_FLAGS = 0x01
AD_COMPLETE_LOCAL_NAME = 0x09
AD_SHORT_LOCAL_NAME = 0x08
AD_MFG_SPECIFIC = 0xFF
AD_SERVICE_DATA_16 = 0x16
AD_URI = 0x24

# Capacity limits
MAX_ADV_PAYLOAD = 31
MAX_SCAN_RSP = 31
MAX_EXTENDED_ADV = 1650
FLAGS_OVERHEAD = 3
NAME_OVERHEAD = 2
MFG_OVERHEAD = 4
URI_OVERHEAD = 3

USABLE_NAME_IN_ADV = MAX_ADV_PAYLOAD - FLAGS_OVERHEAD - NAME_OVERHEAD  # 26
USABLE_NAME_IN_RSP = MAX_SCAN_RSP - NAME_OVERHEAD  # 29

FLOOD_NUMBERING_OVERHEAD = 8
FLOOD_CAPACITY = USABLE_NAME_IN_ADV - FLOOD_NUMBERING_OVERHEAD  # 18

TEST_COMPANY_ID = 0xFFFF


def build_ad_structure(ad_type: int, data: bytes) -> bytes:
    """Build a single AD structure: [length][type][data]."""
    length = len(data) + 1
    return struct.pack("BB", length, ad_type) + data


def build_flags_ad() -> bytes:
    """Build standard BLE Flags AD structure (3 bytes)."""
    flags = 0x02 | 0x04  # LE General Discoverable + BR/EDR Not Supported
    return build_ad_structure(AD_FLAGS, bytes([flags]))


def build_name_ad(text: str, complete: bool = True) -> bytes:
    """Build Complete/Short Local Name AD structure."""
    ad_type = AD_COMPLETE_LOCAL_NAME if complete else AD_SHORT_LOCAL_NAME
    return build_ad_structure(ad_type, text.encode("utf-8"))


def build_mfg_data_ad(
    payload: bytes,
    company_id: int = TEST_COMPANY_ID,
) -> bytes:
    """Build Manufacturer Specific Data AD structure."""
    company_bytes = struct.pack("<H", company_id)
    return build_ad_structure(AD_MFG_SPECIFIC, company_bytes + payload)


def build_uri_ad(uri: str) -> bytes:
    """Build URI AD structure. Scheme byte 0x00 = no prefix."""
    data = bytes([0x00]) + uri.encode("utf-8")
    return build_ad_structure(AD_URI, data)


# ---------------------------------------------------------------------------
# Delivery strategy compilers
# ---------------------------------------------------------------------------

_DECOY_NAMES = [
    "Samsung TV",
    "HP LaserJet Pro",
    "Logitech MX Keys",
    "Apple Watch",
    "Bose QC45",
    "Pixel Buds Pro",
    "Dell Monitor",
    "Jabra Elite 85t",
    "Roku Streaming",
    "Sonos One",
    "Canon PIXMA",
    "LG Soundbar",
]


def compile_micro(payload_text: str) -> tuple[bytes, bytes]:
    """Single ADV_IND packet, payload in Complete Local Name.

    For payloads <= 26 bytes.
    """
    truncated = payload_text[:USABLE_NAME_IN_ADV]
    adv = build_flags_ad() + build_name_ad(truncated)
    return adv, b""


def _compile_flood_numbered(
    payload_text: str,
    count: int,
) -> list[tuple[bytes, bytes]]:
    """Chunks with '[1/N] chunk...' prefix."""
    chunks: list[str] = []
    for i in range(0, len(payload_text), FLOOD_CAPACITY):
        chunks.append(payload_text[i : i + FLOOD_CAPACITY])

    if count > 0:
        # Pad or trim to requested count
        while len(chunks) < count:
            chunks.append("")
        chunks = chunks[:count]

    total = len(chunks)
    devices: list[tuple[bytes, bytes]] = []
    for idx, chunk in enumerate(chunks, 1):
        label = f"[{idx}/{total}] {chunk}"
        adv = build_flags_ad() + build_name_ad(label[:USABLE_NAME_IN_ADV])
        devices.append((adv, b""))
    return devices


def _compile_flood_instructed(
    payload_text: str,
    count: int,
) -> list[tuple[bytes, bytes]]:
    """Device 1 = instruction header, rest = payload chunks."""
    instruction = "Read next devices as one msg:"
    header_adv = build_flags_ad() + build_name_ad(instruction[:USABLE_NAME_IN_ADV])
    devices: list[tuple[bytes, bytes]] = [(header_adv, b"")]

    chunks: list[str] = []
    for i in range(0, len(payload_text), USABLE_NAME_IN_ADV):
        chunks.append(payload_text[i : i + USABLE_NAME_IN_ADV])

    if count > 1:
        while len(chunks) < count - 1:
            chunks.append("")
        chunks = chunks[: count - 1]

    for chunk in chunks:
        adv = build_flags_ad() + build_name_ad(chunk[:USABLE_NAME_IN_ADV])
        devices.append((adv, b""))
    return devices


def _compile_flood_scattered(
    payload_text: str,
    count: int,
) -> list[tuple[bytes, bytes]]:
    """PI chunks interleaved with decoy device names."""
    pi_chunks: list[str] = []
    for i in range(0, len(payload_text), USABLE_NAME_IN_ADV):
        pi_chunks.append(payload_text[i : i + USABLE_NAME_IN_ADV])

    devices: list[tuple[bytes, bytes]] = []
    decoy_idx = 0
    for chunk in pi_chunks:
        # Insert a decoy before each PI chunk
        decoy = _DECOY_NAMES[decoy_idx % len(_DECOY_NAMES)]
        decoy_adv = build_flags_ad() + build_name_ad(decoy)
        devices.append((decoy_adv, b""))
        decoy_idx += 1

        adv = build_flags_ad() + build_name_ad(chunk[:USABLE_NAME_IN_ADV])
        devices.append((adv, b""))

    if count > 0:
        while len(devices) < count:
            decoy = _DECOY_NAMES[decoy_idx % len(_DECOY_NAMES)]
            decoy_adv = build_flags_ad() + build_name_ad(decoy)
            devices.append((decoy_adv, b""))
            decoy_idx += 1
        devices = devices[:count]

    return devices


def compile_flood(
    payload_text: str,
    count: int = 0,
    style: str = "instructed",
) -> list[tuple[bytes, bytes]]:
    """Split payload across multiple BLE device advertisements."""
    if style == "numbered":
        return _compile_flood_numbered(payload_text, count)
    if style == "scattered":
        return _compile_flood_scattered(payload_text, count)
    return _compile_flood_instructed(payload_text, count)


def has_ble5_extended_adv(device: str = "hci0") -> bool:
    """Check if system BLE adapter supports LE Extended Advertising."""
    try:
        result = subprocess.run(
            ["hciconfig", device, "features"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "LE Extended Advertising" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def compile_extended_adv(payload_text: str) -> bytes:
    """Up to 1650 bytes on secondary advertising channels."""
    truncated = payload_text[:MAX_EXTENDED_ADV]
    return build_flags_ad() + build_name_ad(truncated)


def compile_url_redirect(url: str) -> tuple[bytes, bytes]:
    """Broadcast a URI in a single ADV_IND packet."""
    adv = build_flags_ad() + build_uri_ad(url[:USABLE_NAME_IN_ADV])
    return adv, b""


def compile_packed(payload_text: str) -> tuple[bytes, bytes]:
    """Pack PI into ADV (Complete Local Name) + SCAN_RSP (Short Local Name)."""
    adv_text = payload_text[:USABLE_NAME_IN_ADV]
    adv = build_flags_ad() + build_name_ad(adv_text, complete=True)
    remaining = payload_text[USABLE_NAME_IN_ADV:]
    scan_rsp = b""
    if remaining:
        scan_rsp = build_name_ad(remaining[:USABLE_NAME_IN_RSP], complete=False)
    return adv, scan_rsp


def compile_auto(
    payload_text: str,
    url: str | None = None,
) -> dict:
    """Auto-select best delivery strategy.

    Returns dict with keys: strategy, devices, note, (extended_data).
    """
    if url is not None:
        adv, rsp = compile_url_redirect(url)
        return {
            "strategy": "url",
            "devices": [(adv, rsp)],
            "note": f"Broadcasting URI: {url[:40]}",
        }

    text_len = len(payload_text)

    if text_len <= USABLE_NAME_IN_ADV:
        adv, rsp = compile_micro(payload_text)
        return {
            "strategy": "micro",
            "devices": [(adv, rsp)],
            "note": f"Single ADV_IND, {text_len} bytes in name field",
        }

    if text_len <= USABLE_NAME_IN_ADV + USABLE_NAME_IN_RSP:
        adv, rsp = compile_packed(payload_text)
        return {
            "strategy": "packed",
            "devices": [(adv, rsp)],
            "note": f"ADV + SCAN_RSP, {text_len} bytes across both packets",
        }

    if text_len <= MAX_EXTENDED_ADV and has_ble5_extended_adv():
        ext_data = compile_extended_adv(payload_text)
        return {
            "strategy": "extended",
            "devices": [],
            "extended_data": ext_data,
            "note": f"BLE 5.0 extended advertising, {text_len} bytes",
        }

    devices = compile_flood(payload_text, style="instructed")
    return {
        "strategy": "flood",
        "devices": devices,
        "note": f"Instructed flood across {len(devices)} devices",
    }
