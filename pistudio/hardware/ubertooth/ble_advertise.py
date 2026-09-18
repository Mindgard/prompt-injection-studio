"""BLE advertising TX via system HCI adapter.

This is the primary TX path for BLE PI delivery. The Ubertooth's
faux slave mode cannot inject custom AD data -- the system adapter
(hci0) supports full AD type control and MAC randomization.
"""

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)


def _generate_random_bdaddr() -> str:
    """Generate a BLE random static address.

    Sets the two MSBs of the first octet (MSB) to 11 (random static type).
    Returns a colon-separated uppercase hex string (e.g. "C4:A3:...:01").
    """
    addr_bytes = bytearray(os.urandom(6))
    addr_bytes[0] |= 0xC0  # MSBs = 11 for random static type
    return ":".join(f"{b:02X}" for b in addr_bytes)


def advertise_hci(
    adv_data: bytes,
    scan_rsp_data: bytes = b"",
    device: str = "hci0",
    duration_secs: int = 60,
    randomize_addr: bool = True,
) -> None:
    """Advertise using standard HCI commands via hcitool/hciconfig."""
    result = subprocess.run(["hciconfig", device, "up"], capture_output=True, timeout=5)
    if result.returncode != 0:
        logger.warning("hciconfig up failed (rc=%d): %s", result.returncode, result.stderr)

    if randomize_addr:
        random_addr = _generate_random_bdaddr()
        addr_hex = random_addr.replace(":", " ")
        subprocess.run(
            ["hcitool", "-i", device, "cmd", "0x08", "0x0005", addr_hex],
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            [
                "hcitool",
                "-i",
                device,
                "cmd",
                "0x08",
                "0x0006",
                "00",
                "08",
                "00",
                "08",
                "03",
                "01",
                "00",
                "00",
                "00",
                "00",
                "00",
                "00",
                "00",
                "07",
                "00",
            ],
            capture_output=True,
            timeout=5,
        )

    hex_data = adv_data.hex()
    subprocess.run(
        ["hcitool", "-i", device, "cmd", "0x08", "0x0008", f"{len(adv_data):02x}", hex_data],
        capture_output=True,
        timeout=5,
    )

    if scan_rsp_data:
        hex_rsp = scan_rsp_data.hex()
        subprocess.run(
            ["hcitool", "-i", device, "cmd", "0x08", "0x0009", f"{len(scan_rsp_data):02x}", hex_rsp],
            capture_output=True,
            timeout=5,
        )

    subprocess.run(
        ["hcitool", "-i", device, "cmd", "0x08", "0x000a", "01"],
        capture_output=True,
        timeout=5,
    )
    logger.info("HCI advertising enabled on %s", device)

    if duration_secs > 0:
        time.sleep(duration_secs)
        stop_hci_advertising(device)


def stop_hci_advertising(device: str = "hci0") -> None:
    """Disable HCI advertising."""
    subprocess.run(
        ["hcitool", "-i", device, "cmd", "0x08", "0x000a", "00"],
        capture_output=True,
        timeout=5,
    )
    logger.info("HCI advertising disabled on %s", device)
