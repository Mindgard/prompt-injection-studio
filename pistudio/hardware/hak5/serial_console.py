"""Cross-platform serial console for Bash Bunny.

Provides device detection (finding the Bash Bunny's serial/CDC port) and
an interactive terminal session over the serial connection.  Works on
macOS, Linux, and Windows.

Requires ``pyserial`` (``pip install pyserial``).
"""

import contextlib
import logging
import platform
import sys
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

_SYSTEM = platform.system()  # "Darwin", "Linux", "Windows"

# Baud rate for Bash Bunny serial console
_BAUD_RATE = 115200


# ── Device detection ─────────────────────────────────────────────


def find_bunny_serial_ports() -> list[str]:
    """Find serial ports that look like a Bash Bunny in arming mode.

    Returns a list of port device paths (e.g. ``/dev/tty.usbmodemch0000011``
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

        # A Bunny in arming mode has no distinctive descriptor, so the only
        # available signal is a generic CDC ACM port.  On macOS that pattern
        # matches every USB serial device, so rule out anything positively
        # identified as something else first — otherwise a plugged-in Flipper
        # gets reported as a Bunny.
        if _is_other_known_device(desc, hwid, device):
            continue

        if (
            "usbmodem" in device
            or "ttyacm" in device
            or "bash bunny" in desc
            or "hak5" in desc
            # 1d6b is the Linux Foundation VID used by Linux's USB gadget
            # framework, which is how the Bunny presents its serial port. It is
            # also what a Linux host's own root hubs report, so it is only
            # meaningful here because comports() lists serial ports and never
            # root hubs.
            or "vid:pid=1d6b" in hwid
        ):
            candidates.append(port.device)

    return sorted(candidates)


def _is_other_known_device(desc: str, hwid: str, device: str) -> bool:
    """Return True if a port belongs to a device that is definitely not a Bunny.

    Args:
        desc: Lower-cased port description.
        hwid: Lower-cased hardware ID.
        device: Lower-cased device path.
    """
    # Flipper Zero — its distinctive port name, descriptor, or STM32 VID:PID.
    if "usbmodemflip" in device or "flipper" in desc or "vid:pid=0483:5740" in hwid:
        return True
    # Ubertooth One.
    return "ubertooth" in desc or "vid:pid=1d50" in hwid


# ── Interactive serial console ───────────────────────────────────


def run_serial_console(
    port: str,
    baud: int = _BAUD_RATE,
    on_output: Callable | None = None,
) -> None:
    """Run an interactive serial console session.

    Connects to the given serial port and bridges stdin/stdout to it.
    Press Ctrl+] (or Ctrl+C) to disconnect.

    Args:
        port: Serial port device path.
        baud: Baud rate (default 115200).
        on_output: Optional callback ``(bytes) -> None`` for each chunk
            received from the device.  If None, writes to sys.stdout.
    """
    import serial

    try:
        ser = serial.Serial(port, baud, timeout=0.1)
    except serial.SerialException as e:
        raise ConnectionError(f"Cannot open {port}: {e}") from e

    stop_event = threading.Event()

    # Resolve a raw byte-capable output stream.  A wrapping REPL may replace
    # sys.stdout with a text-only stream that has no .buffer, so prefer the
    # original interpreter stdout, then fall back to text-mode decode.
    _raw_out = None
    if sys.__stdout__ is not None and hasattr(sys.__stdout__, "buffer"):
        _raw_out = sys.__stdout__.buffer
    if _raw_out is None and hasattr(sys.stdout, "buffer"):
        _raw_out = sys.stdout.buffer

    def _reader():
        """Read from serial port and write to stdout."""
        while not stop_event.is_set():
            try:
                data = ser.read(1024)
                if data:
                    if on_output:
                        on_output(data)
                    elif _raw_out is not None:
                        _raw_out.write(data)
                        _raw_out.flush()
                    else:
                        # Text-mode fallback (ThreadAwareStream)
                        sys.stdout.write(data.decode("utf-8", errors="replace"))
                        sys.stdout.flush()
            except (serial.SerialException, OSError):
                if not stop_event.is_set():
                    stop_event.set()
                break

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    # Platform-specific raw input handling
    try:
        if _SYSTEM == "Windows":
            _windows_writer(ser, stop_event)
        else:
            _unix_writer(ser, stop_event)
    finally:
        stop_event.set()
        with contextlib.suppress(OSError):
            ser.close()
        reader_thread.join(timeout=2)


def _unix_writer(ser, stop_event: threading.Event) -> None:
    """Read from stdin in raw mode and write to serial (macOS/Linux)."""
    import os
    import termios
    import tty

    # Use the real stdin fd directly via os.read() to bypass the
    # shell's ThreadAwareStream proxy (which lacks .buffer).
    try:
        # Use the actual stdin fd directly.
        fd = sys.__stdin__.fileno()
    except Exception:
        fd = sys.stdin.fileno()

    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while not stop_event.is_set():
            try:
                ch = os.read(fd, 1)
                if not ch:
                    break
                # Ctrl+] (0x1d) = disconnect
                if ch == b"\x1d":
                    break
                # Ctrl+C also disconnects
                if ch == b"\x03":
                    break
                ser.write(ch)
            except (OSError, KeyboardInterrupt):
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _windows_writer(ser, stop_event: threading.Event) -> None:
    """Read from stdin and write to serial (Windows)."""
    import msvcrt

    while not stop_event.is_set():
        try:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                # Ctrl+] (0x1d) = disconnect
                if ch == b"\x1d":
                    break
                # Ctrl+C also disconnects
                if ch == b"\x03":
                    break
                ser.write(ch)
        except (OSError, KeyboardInterrupt):
            break
