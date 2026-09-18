"""Flipper Zero serial console helpers.

Provides device detection (finding the Flipper Zero's serial/CDC port) and
an interactive terminal session over the serial connection. Works on
macOS, Linux, and Windows.

Requires ``pyserial`` (``pip install pyserial``).
"""

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Flipper Zero USB identifiers
# VID: 0x0483 (STMicroelectronics - Flipper uses STM32)
# PID: 0x5740 (Virtual COM Port)
_FLIPPER_VID = "0483"
_FLIPPER_PID = "5740"

# Baud rate for Flipper Zero CLI (default)
_BAUD_RATE = 115200


def find_flipper_serial_ports() -> list[str]:
    """Find serial ports that look like a Flipper Zero.

    Returns a list of port device paths (e.g. ``/dev/tty.usbmodemflip_...``
    on macOS, ``/dev/ttyACM0`` on Linux, ``COM3`` on Windows).
    """
    try:
        from serial.tools.list_ports import comports
    except ImportError:
        logger.warning("pyserial not installed — cannot detect serial ports")
        return []

    candidates: list[str] = []
    for port in comports():
        desc = (port.description or "").lower()
        hwid = (port.hwid or "").lower()
        device = (port.device or "").lower()
        manufacturer = (port.manufacturer or "").lower()

        is_candidate = False

        # Check for Flipper Zero VID:PID
        if (
            f"vid:pid={_FLIPPER_VID}:{_FLIPPER_PID}" in hwid
            or "usbmodemflip" in device
            or "flipper" in desc
            or "flipper" in manufacturer
            or "ttyacm" in device
            and "flipper" in desc
        ):
            is_candidate = True

        if is_candidate:
            candidates.append(port.device)

    return sorted(candidates)


def run_flipper_console(
    port: str,
    baud: int = _BAUD_RATE,
    on_output: Callable | None = None,
) -> None:
    """Run an interactive serial console session to Flipper Zero.

    Connects to the given serial port and bridges stdin/stdout to it.
    Press Ctrl+] (or Ctrl+C) to disconnect.

    Args:
        port: Serial port device path.
        baud: Baud rate (default 115200).
        on_output: Optional callback ``(bytes) -> None`` for each chunk
            received from the device. If None, writes to sys.stdout.
    """
    # Reuse the shared serial console implementation
    from pistudio.hardware.hak5.serial_console import run_serial_console

    run_serial_console(port, baud, on_output)


def find_flipper_bridge_port() -> str | None:
    """Find the Flipper Zero bridge serial port (CDC channel 1).

    When the Flipper app enters Remote Mode it switches USB to dual-CDC.
    Channel 0 is the Flipper CLI, channel 1 is the bridge protocol.
    In dual-CDC mode, two Flipper serial ports appear — the bridge is
    the **second** (higher-numbered) one.

    Returns the bridge port path, or None if not found.
    """
    ports = find_flipper_serial_ports()
    if len(ports) >= 2:
        # Dual-CDC active: second port is the bridge channel
        return ports[-1]
    if len(ports) == 1:
        # Only one port visible — Flipper may still be in single-CDC mode
        # (user hasn't entered Remote Mode yet), or the OS merged them.
        # Return it and let the caller attempt a ping.
        return ports[0]
    return None


__all__ = ["find_flipper_serial_ports", "find_flipper_bridge_port", "run_flipper_console"]
