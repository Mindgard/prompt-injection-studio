"""Flipper Zero device integration — multi-protocol prompt injection.

The Flipper Zero is a portable multi-tool for pentesters that supports
multiple attack vectors: BadUSB (HID), NFC/RFID, and Bluetooth.

Each protocol can be used as a prompt injection delivery mechanism:
- **BadUSB**: Type payloads directly into chat interfaces
- **NFC/RFID**: Store payloads in NDEF text records on cards
- **Bluetooth**: Set device name or BLE advertising data to payloads

Third-Party Attribution:
- Flipper Zero: https://flipperzero.one/
- BadUSB Documentation: https://docs.flipper.net/bad-usb
- NFC Documentation: https://docs.flipper.net/nfc
"""

from pistudio.hardware.flipper.badusb import (
    compile_payload as compile_badusb_payload,
)
from pistudio.hardware.flipper.bluetooth import (
    BT_NAME_MAX_LENGTH,
    compile_ble_spam_config,
    compile_bt_name_payload,
)
from pistudio.hardware.flipper.bridge import FlipperBridge
from pistudio.hardware.flipper.device import (
    deploy_all,
    deploy_badusb,
    deploy_nfc,
    find_flipper_volumes,
)
from pistudio.hardware.flipper.nfc import (
    SUPPORTED_CARD_TYPES,
    NFCPayload,
    compile_ndef_payload,
)
from pistudio.hardware.flipper.sequence import (
    AttackSequence,
    SequenceStep,
    add_step,
    create_sequence,
    deploy_sequence,
    sequence_names,
)
from pistudio.hardware.flipper.serial_console import (
    find_flipper_serial_ports,
    run_flipper_console,
)
from pistudio.hardware.flipper.sync import (
    sync_all,
    sync_payloads,
    sync_results,
)

__all__ = [
    # BadUSB
    "compile_badusb_payload",
    # NFC
    "NFCPayload",
    "compile_ndef_payload",
    "SUPPORTED_CARD_TYPES",
    # Bluetooth
    "compile_bt_name_payload",
    "compile_ble_spam_config",
    "BT_NAME_MAX_LENGTH",
    # Device
    "find_flipper_volumes",
    "deploy_badusb",
    "deploy_nfc",
    "deploy_all",
    # Serial console
    "find_flipper_serial_ports",
    "run_flipper_console",
    # Sync
    "sync_payloads",
    "sync_all",
    "sync_results",
    # Bridge
    "FlipperBridge",
    # Sequence
    "AttackSequence",
    "SequenceStep",
    "create_sequence",
    "add_step",
    "deploy_sequence",
    "sequence_names",
]
