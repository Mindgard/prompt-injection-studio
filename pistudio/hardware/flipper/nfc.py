"""Flipper Zero NFC prompt injection support.

Write prompt injection payloads to NTAG21x cards as NDEF text records.
When scanned by an NFC-enabled system, the payload is processed.

Attack Scenario:
Many enterprise systems use NFC/RFID cards for authentication. If an
LLM-powered system processes card data (e.g., "Welcome, [cardholder name]"
or badge scanning logs), the card's data fields can contain prompt injections.

The generated ``.nfc`` files follow the Flipper NFC device format version 4
as documented at
https://developer.flipper.net/flipperzero/doxygen/nfc_file_format.html —
a partial dump is rejected by the firmware's parser rather than partially
loaded, so every field the NTAG/Ultralight format requires is emitted.
"""

from dataclasses import dataclass

# NDEF capacity per NTAG variant, taken from the Capability Container byte 2
# that NXP programs at manufacture (NTAG213/215/216 data sheet, "Capability
# Container (CC bytes)").  These are smaller than the advertised 144/504/888
# bytes of user memory because the CC declares the NDEF area specifically.
_NTAG_PROFILES: dict[str, dict[str, int]] = {
    "NTAG213": {"ndef_capacity": 144, "pages_total": 45, "cc_size": 0x12},
    "NTAG215": {"ndef_capacity": 496, "pages_total": 135, "cc_size": 0x3E},
    "NTAG216": {"ndef_capacity": 872, "pages_total": 231, "cc_size": 0x6D},
}

SUPPORTED_CARD_TYPES: dict[str, int] = {name: p["ndef_capacity"] for name, p in _NTAG_PROFILES.items()}

DEFAULT_CARD_TYPE = "NTAG216"

# NDEF record header sizes.  A short record (SR=1) carries a one-byte payload
# length and so caps out at 255 bytes; above that the record must switch to the
# normal layout with a four-byte length.  NFC Forum NDEF 1.0 §3.2.9.
_SHORT_RECORD_HEADER = 5  # flags, type length, 1-byte payload length, type, status
_NORMAL_RECORD_HEADER = 8  # flags, type length, 4-byte payload length, type, status
_SHORT_RECORD_MAX_PAYLOAD = 255

# NDEF TLV framing: 0x03 <len> ... 0xFE.  Messages of 255 bytes or more use the
# three-byte length form 0xFF <hi> <lo>.
_TLV_SHORT_OVERHEAD = 2
_TLV_LONG_OVERHEAD = 4
_TLV_TERMINATOR = 1
_TLV_SHORT_MAX = 254

# Pages 0-2 hold the UID, its check bytes, and the lock bytes; NDEF data starts
# after the capability container at page 3.
_FIRST_DATA_PAGE = 4

# NXP static defaults.  The signature is an ECC value unique to each die; an
# emulated card is not expected to reproduce a genuine one, so this is zeroed
# rather than fabricated to look real.
_SIGNATURE = " ".join(["00"] * 32)
_MIFARE_VERSION = {
    "NTAG213": "00 04 04 02 01 00 0F 03",
    "NTAG215": "00 04 04 02 01 00 11 03",
    "NTAG216": "00 04 04 02 01 00 13 03",
}


@dataclass
class NFCPayload:
    """NFC card with embedded prompt injection."""

    name: str
    payload_text: str
    card_type: str = DEFAULT_CARD_TYPE
    description: str = ""


def get_max_payload_size(card_type: str) -> int:
    """Return the largest payload text, in bytes, that fits on *card_type*.

    Accounts for the NDEF record header, the language code, the TLV framing
    and its terminator.  Both framings are considered, because a small card
    never leaves the compact short-record layout and reporting the larger
    record's overhead would understate its capacity.  Returns 0 for an
    unknown card type.
    """
    profile = _NTAG_PROFILES.get(card_type)
    if profile is None:
        return 0

    capacity = profile["ndef_capacity"]
    # _encoded_size grows monotonically with the text length, so the largest
    # fitting text is found by walking down from the capacity itself.
    for text_len in range(capacity, 0, -1):
        if _encoded_size(text_len) <= capacity:
            return text_len
    return 0


def _encoded_size(text_len: int) -> int:
    """Return the on-card byte count for *text_len* bytes of UTF-8 text."""
    payload = 1 + len("en") + text_len  # status byte + language code + text
    if payload <= _SHORT_RECORD_MAX_PAYLOAD:
        record = _SHORT_RECORD_HEADER - 1 + payload
    else:
        record = _NORMAL_RECORD_HEADER - 1 + payload
    tlv = _TLV_SHORT_OVERHEAD if record <= _TLV_SHORT_MAX else _TLV_LONG_OVERHEAD
    return record + tlv + _TLV_TERMINATOR


def _encode_ndef_text_record(text: str, lang: str = "en") -> bytes:
    """Encode *text* as an NDEF Text Record (type 'T').

    Uses the short-record layout when the payload fits in 255 bytes and the
    normal four-byte-length layout when it does not, so payloads larger than a
    single byte can express are encoded rather than truncated or rejected.

    Args:
        text: The text to carry in the record.
        lang: IANA language code stored alongside the text.

    Returns:
        The encoded NDEF record bytes.
    """
    text_bytes = text.encode("utf-8")
    lang_bytes = lang.encode("ascii")

    # Status byte: bit 7 clear selects UTF-8, bits 0-5 hold the language length.
    status_byte = len(lang_bytes) & 0x3F
    payload = bytes([status_byte]) + lang_bytes + text_bytes

    # MB=1, ME=1, CF=0, IL=0, TNF=1 (NFC Forum Well Known Type).  SR toggles.
    short = len(payload) <= _SHORT_RECORD_MAX_PAYLOAD
    flags = 0xD1 if short else 0xC1
    length_field = bytes([len(payload)]) if short else len(payload).to_bytes(4, "big")

    return bytes([flags, 1]) + length_field + b"\x54" + payload


def _wrap_ndef_tlv(record: bytes) -> bytes:
    """Wrap an NDEF record in its TLV container with a terminator."""
    if len(record) <= _TLV_SHORT_MAX:
        header = bytes([0x03, len(record)])
    else:
        # 0xFF signals a two-byte big-endian length follows.
        header = bytes([0x03, 0xFF]) + len(record).to_bytes(2, "big")
    return header + record + bytes([0xFE])


def _synthesise_uid(name: str) -> list[int]:
    """Derive a stable 7-byte NTAG UID from the payload *name*.

    Byte 0 is 0x04, NXP's manufacturer code, so the card reads as a plausible
    NTAG. The remaining bytes come from the name to keep repeated deployments
    of the same payload stable rather than shuffling UIDs between runs.
    """
    seed = (name.encode("utf-8") + b"\x00" * 6)[:6]
    return [0x04, *seed]


def _uid_pages(uid: list[int]) -> list[str]:
    """Return pages 0-2 for a 7-byte UID, including both BCC check bytes.

    A reader recomputes BCC0 and BCC1 during anti-collision, so a dump with
    the wrong values is rejected before its NDEF content is ever read.
    """
    bcc0 = 0x88 ^ uid[0] ^ uid[1] ^ uid[2]
    bcc1 = uid[3] ^ uid[4] ^ uid[5] ^ uid[6]

    page0 = [uid[0], uid[1], uid[2], bcc0]
    page1 = [uid[3], uid[4], uid[5], uid[6]]
    # Page 2 is BCC1, the internal byte, then the two static lock bytes.
    page2 = [bcc1, 0x48, 0x00, 0x00]
    return [" ".join(f"{b:02X}" for b in page) for page in (page0, page1, page2)]


def compile_ndef_payload(payload: NFCPayload) -> str:
    """Compile *payload* to a Flipper Zero ``.nfc`` file.

    Args:
        payload: The payload, card type and optional description.

    Returns:
        The ``.nfc`` file content, ready to write to the SD card.

    Raises:
        ValueError: If the card type is unknown or the text does not fit.
    """
    profile = _NTAG_PROFILES.get(payload.card_type)
    if profile is None:
        raise ValueError(f"Unsupported card type: '{payload.card_type}'. Supported: {', '.join(_NTAG_PROFILES)}")

    ndef_tlv = _wrap_ndef_tlv(_encode_ndef_text_record(payload.payload_text))
    capacity = profile["ndef_capacity"]
    if len(ndef_tlv) > capacity:
        text_bytes = len(payload.payload_text.encode("utf-8"))
        raise ValueError(
            f"Payload too large for {payload.card_type}: {text_bytes} bytes of text needs "
            f"{len(ndef_tlv)} bytes of NDEF but the card holds {capacity}. "
            f"Max text for this card is ~{get_max_payload_size(payload.card_type)} bytes; "
            f"NTAG216 holds the most at ~{get_max_payload_size('NTAG216')}."
        )

    return "\n".join(_build_nfc_file(payload, profile, ndef_tlv)) + "\n"


def _build_nfc_file(payload: NFCPayload, profile: dict[str, int], ndef_tlv: bytes) -> list[str]:
    """Assemble the lines of a version 4 Flipper NFC device file."""
    uid = _synthesise_uid(payload.name)
    pages_total = profile["pages_total"]

    lines = [
        "Filetype: Flipper NFC device",
        "Version: 4",
        f"# Prompt Injection Studio — NFC prompt injection: {_comment_safe(payload.name)}",
    ]
    if payload.description:
        lines.append(f"# {_comment_safe(payload.description)}")

    lines += [
        "# Device type can be ISO14443-3A, ISO14443-3B, ISO14443-4A, NTAG/Ultralight, Mifare Classic, Mifare DESFire",
        "Device type: NTAG/Ultralight",
        "# UID is common for all formats",
        f"UID: {' '.join(f'{b:02X}' for b in uid)}",
        "# ISO14443-3A specific data",
        "ATQA: 00 44",
        "SAK: 00",
        "# NTAG/Ultralight specific data",
        "Data format version: 2",
        f"NTAG/Ultralight type: {payload.card_type}",
        f"Signature: {_SIGNATURE}",
        f"Mifare version: {_MIFARE_VERSION[payload.card_type]}",
    ]
    for counter in range(3):
        lines.append(f"Counter {counter}: 0")
        lines.append(f"Tearing {counter}: 00")

    lines.append(f"Pages total: {pages_total}")
    lines.append(f"Pages read: {pages_total}")
    lines += _data_pages(uid, profile, ndef_tlv)
    lines.append("Failed authentication attempts: 0")
    return lines


def _data_pages(uid: list[int], profile: dict[str, int], ndef_tlv: bytes) -> list[str]:
    """Return every ``Page N:`` line for the card, zero-filling the tail.

    The firmware reads exactly ``Pages total`` pages, so a dump that stops
    after the payload fails to parse.
    """
    pages = [f"Page {i}: {page}" for i, page in enumerate(_uid_pages(uid))]

    # Page 3 is the capability container: NDEF magic, version 1.0, the NDEF
    # area size in 8-byte units, and read/write access.
    pages.append(f"Page 3: E1 10 {profile['cc_size']:02X} 00")

    padded = ndef_tlv + bytes(-len(ndef_tlv) % 4)
    for offset in range(0, len(padded), 4):
        chunk = padded[offset : offset + 4]
        pages.append(f"Page {_FIRST_DATA_PAGE + offset // 4}: {' '.join(f'{b:02X}' for b in chunk)}")

    for page_num in range(len(pages), profile["pages_total"]):
        pages.append(f"Page {page_num}: 00 00 00 00")

    return pages


def _comment_safe(text: str) -> str:
    """Flatten newlines so text cannot break out of a ``#`` comment line.

    Flipper files are key-value; a newline inside a comment ends it and the
    next line is parsed as a key, letting payload text forge real fields.
    """
    return text.replace("\r", " ").replace("\n", " ")
