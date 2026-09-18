"""Finding USB-to-TTL serial adapters.

The studio's existing detectors look for CDC-ACM ports -- ``usbmodem`` on
macOS, ``ttyACM`` on Linux -- because that is how a Bash Bunny and a Flipper
present themselves.  A USB-TTL cable is a different animal: an FTDI, Silicon
Labs, WCH or Prolific bridge chip enumerating as ``usbserial`` / ``ttyUSB``.
It matched none of those patterns, so a cable that was plugged in and working
was invisible to every scan the studio could run.

Detection is by USB vendor ID rather than by device-path shape.  The path
naming differs per platform and per driver version; the VID is assigned by
USB-IF and does not move.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

__all__ = ["BRIDGE_VENDORS", "SerialPort", "find_serial_ports", "resolve_port"]

logger = logging.getLogger(__name__)

#: USB vendor IDs of the common USB-to-TTL bridge chips, lowercase hex.
#: These are the four that account for essentially every cable in the wild.
BRIDGE_VENDORS: dict[str, str] = {
    "0403": "FTDI",
    "10c4": "Silicon Labs CP210x",
    "1a86": "WCH CH340/CH341",
    "067b": "Prolific PL2303",
}

# Devices the studio drives through their own commands.  A Flipper also
# presents a serial port, but `uart` is not how you should talk to it, so it is
# labelled rather than hidden -- seeing it in the list and being told where it
# belongs beats wondering why it is missing.
_KNOWN_DEVICES: dict[str, tuple[str, str]] = {
    "0483": ("Flipper Zero", "hw flipper"),
    "1d6b": ("Linux USB gadget (Bash Bunny?)", "hw bunny"),
}

# Ports the OS always exposes and nobody wants to transmit into.
_NOISE = ("bluetooth", "debug-console", "wlan-debug")


@dataclass(frozen=True, slots=True)
class SerialPort:
    """One serial port the host can see.

    Attributes:
        device: Path to open, e.g. ``/dev/cu.usbserial-BG03G28X``.
        description: What the driver calls it, e.g. ``FT232R USB UART``.
        vid: USB vendor ID, lowercase hex, or ``""`` when unknown.
        pid: USB product ID, lowercase hex, or ``""``.
        serial_number: The adapter's serial, when it reports one.
        chip: Friendly bridge name, or ``""`` if not a recognised bridge.
        owned_by: The studio command that should drive this device instead,
            when it is one the studio already knows about.
    """

    device: str
    description: str = ""
    vid: str = ""
    pid: str = ""
    serial_number: str = ""
    chip: str = ""
    owned_by: str = ""

    @property
    def is_bridge(self) -> bool:
        """Whether this looks like a general-purpose USB-TTL adapter."""
        return bool(self.chip)

    @property
    def label(self) -> str:
        """A one-line description for the port listing."""
        if self.chip:
            return f"{self.chip} — {self.description}" if self.description else self.chip
        return self.description or "unknown serial device"


def _parse_hwid(hwid: str) -> tuple[str, str]:
    """Pull ``(vid, pid)`` out of a pyserial hwid string, lowercased."""
    import re

    match = re.search(r"VID:PID=([0-9a-fA-F]{4}):([0-9a-fA-F]{4})", hwid or "")
    if not match:
        return "", ""
    return match.group(1).lower(), match.group(2).lower()


def find_serial_ports(*, bridges_only: bool = False) -> list[SerialPort]:
    """Return the serial ports the host can see, best candidates first.

    Args:
        bridges_only: Drop anything that is not a recognised USB-TTL bridge.

    Returns:
        Ports sorted with bridges first, then by device path.  Never raises:
        a missing pyserial yields an empty list with a warning, because a
        listing that explodes is worse than one that says "none".
    """
    try:
        from serial.tools.list_ports import comports
    except ImportError:
        logger.warning("pyserial not installed — cannot detect serial ports")
        return []

    ports: list[SerialPort] = []
    for port in comports():
        device = port.device or ""
        if any(noise in device.lower() for noise in _NOISE):
            continue

        vid, pid = _parse_hwid(port.hwid or "")
        chip = BRIDGE_VENDORS.get(vid, "")
        known = _KNOWN_DEVICES.get(vid)
        ports.append(
            SerialPort(
                device=device,
                description=port.description if port.description not in (None, "n/a") else "",
                vid=vid,
                pid=pid,
                serial_number=port.serial_number or "",
                chip=chip,
                owned_by=known[1] if known else "",
            )
        )

    if bridges_only:
        ports = [p for p in ports if p.is_bridge]
    # Bridges first: on a machine with a Flipper attached as well, the cable is
    # what `uart` is for and should be the one auto-selected.
    return sorted(ports, key=lambda p: (not p.is_bridge, p.device))


def resolve_port(explicit: str | None = None) -> tuple[str | None, str]:
    """Choose the port to use.

    Args:
        explicit: A path the caller named, which always wins.

    Returns:
        ``(device, reason)``.  *device* is None when nothing usable was found;
        *reason* explains the choice, or what to do about it, in words meant
        for the person who ran the command.
    """
    if explicit:
        return explicit, "named on the command line"

    bridges = find_serial_ports(bridges_only=True)
    if len(bridges) == 1:
        return bridges[0].device, f"the only USB-TTL adapter attached ({bridges[0].chip})"
    if len(bridges) > 1:
        names = ", ".join(p.device for p in bridges)
        # Guessing between two cables risks transmitting into the wrong
        # target, which is exactly the mistake that is hard to take back.
        return None, f"several USB-TTL adapters attached — choose one with --serial-port: {names}"

    others = find_serial_ports()
    if others:
        hint = ", ".join(p.device for p in others[:3])
        return None, f"no USB-TTL adapter found. Other serial ports are present: {hint}"
    return None, "no serial ports found. Plug in a USB-TTL adapter."
