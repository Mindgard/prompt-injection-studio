"""Ubertooth One device detection via USB VID:PID.

The Ubertooth is a BLE intelligence sensor. Detection checks for the
USB device and available host tools (ubertooth-btle, ubertooth-scan).
"""

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

UBERTOOTH_USB_VID_PID = "1d50:6002"

REQUIRED_TOOLS = {
    "ubertooth-btle": "BLE sniffing and faux slave",
    "ubertooth-scan": "Classic BT scanning",
}

OPTIONAL_TOOLS = {
    "ubertooth-rx": "Classic BT survey mode",
    "ubertooth-btbb": "Classic BT link-layer",
}


def find_ubertooth() -> dict | None:
    """Detect connected Ubertooth via lsusb or pyusb.

    Returns dict with vid_pid, firmware_version, tools.
    Returns None if no device found.
    """
    try:
        result = subprocess.run(
            ["lsusb", "-d", UBERTOOTH_USB_VID_PID],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        try:
            import usb.core  # noqa: I001

            dev = usb.core.find(idVendor=0x1D50, idProduct=0x6002)
            if dev is None:
                return None
        except ImportError:
            return None

    tools = {}
    for tool in {**REQUIRED_TOOLS, **OPTIONAL_TOOLS}:
        tools[tool] = shutil.which(tool) is not None

    return {
        "vid_pid": UBERTOOTH_USB_VID_PID,
        "firmware_version": _get_firmware_version(),
        "tools": tools,
    }


def _get_firmware_version() -> str:
    """Query firmware version via ubertooth-util."""
    try:
        result = subprocess.run(
            ["ubertooth-util", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def check_tools() -> list[str]:
    """Return list of missing required tools."""
    return [tool for tool in REQUIRED_TOOLS if not shutil.which(tool)]
