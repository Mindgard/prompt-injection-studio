"""Red team hardware integration — USB HID, NFC, Bluetooth, RF injection devices.

This package provides integration with security red teaming hardware for
prompt injection testing via physical attack vectors.

Supported Devices:
- **Bash Bunny**: USB HID + storage combo device from Hak5
- **USB Rubber Ducky**: Pure USB HID injection device from Hak5
- **Flipper Zero**: Multi-protocol device (BadUSB, NFC, Bluetooth, GPIO, QR)
- **Ubertooth One**: BLE sniffing and advertising
- **USB-TTL serial**: Payload delivery over a raw TX/RX serial console

Third-Party Attribution:
- Hak5: https://hak5.org/ (Bash Bunny, USB Rubber Ducky, trademarks of Hak5 LLC)
- Flipper Zero: https://flipperzero.one/ (trademark of Flipper Devices Inc.)
- Ubertooth One: https://greatscottgadgets.com/ubertoothone/

Device-side Flipper Zero firmware lives in its own repository:
https://github.com/Mindgard/flipperzero-prompt-injection-field-kit

This integration is not affiliated with, endorsed by, or sponsored by any
hardware vendor; product names identify the hardware it interoperates with.
Prompt Injection Studio provides tooling for security research and authorised
testing only.
"""

from pistudio.hardware.payloads import (
    Payload,
    add_payload,
    get_payload,
    list_payloads,
    payload_names,
    remove_payload,
    update_payload,
)

__all__ = [
    # Payloads
    "Payload",
    "add_payload",
    "get_payload",
    "list_payloads",
    "payload_names",
    "remove_payload",
    "update_payload",
]
