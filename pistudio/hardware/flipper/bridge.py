"""Real-time serial bridge to a Flipper Zero running the companion FAP.

Speaks the line-based text protocol recorded in
``docs/flipper-bridge-protocol.md``.  That document describes the host side
only: the firmware lives in a separate repository and the protocol has not
been checked against it, so where the two disagree the firmware is right.

Requires ``pyserial`` (``pip install pyserial``).
"""

import json
import logging
import threading
import time

logger = logging.getLogger(__name__)

_BAUD_RATE = 115200
_READ_TIMEOUT = 2.0  # seconds to wait for a response line

# Upper bound on a single response line.  The LIST reply carries every payload
# name as JSON, so this is generous, but it stops a device that never sends a
# newline from growing the read buffer without limit.
_MAX_LINE_BYTES = 65536

# A USB CDC bulk transfer is 64 bytes.  Firmware that writes a long reply with
# a single non-blocking write, and does not loop over the remainder, stops on
# this boundary -- which is what a truncated LIST looks like from the host.
_CDC_PACKET_BYTES = 64


class IncompleteResponse(Exception):
    """The device stopped mid-line, so the reply was never terminated.

    Distinct from "no response" and from "a reply this host could not parse":
    the bytes that did arrive are usually valid, just cut short.  Carrying them
    on the exception lets the caller say how far the transfer got, which is the
    difference between "no payloads loaded" and "the device sent 64 of them".
    """

    def __init__(self, partial: bytes) -> None:
        self.partial = partial
        text = partial.decode("utf-8", errors="replace")
        detail = ""
        if len(partial) % _CDC_PACKET_BYTES == 0:
            # Naming the boundary points at the firmware's write loop rather
            # than at the cable or this host's timeout.
            packets = len(partial) // _CDC_PACKET_BYTES
            detail = f" — exactly {packets} USB packet{'s' if packets > 1 else ''}, so the firmware stopped writing"
        super().__init__(f"Flipper sent {len(partial)} bytes with no line terminator{detail}: {text[:120]!r}")


def _parse_count(value: str, field: str) -> int:
    """Return *value* as a count, or 0 if the device sent something else.

    A truncated CDC packet or a firmware built against a different protocol
    version can put anything here. Reporting zero beats a traceback out of a
    status query.
    """
    try:
        return int(value)
    except ValueError:
        logger.warning("Flipper sent a non-numeric %s count: %r", field, value)
        return 0


class FlipperBridge:
    """Bidirectional serial bridge to a Flipper Zero running the companion FAP.

    Usage::

        bridge = FlipperBridge("/dev/tty.usbmodemflip_12345")
        bridge.connect()
        if bridge.ping():
            bridge.execute_badusb("ignore-instructions")
        bridge.disconnect()
    """

    def __init__(self, port: str, baud: int = _BAUD_RATE):
        self.port = port
        self.baud = baud
        self._serial = None
        self._lock = threading.Lock()

    # ── Connection lifecycle ─────────────────────────────────────

    def connect(self, retries: int = 3, retry_delay: float = 1.0) -> None:
        """Open the serial connection with retry logic."""
        import serial as pyserial

        if self._serial and self._serial.is_open:
            return

        last_error = None
        for attempt in range(1, retries + 1):
            try:
                self._serial = pyserial.Serial(self.port, self.baud, timeout=_READ_TIMEOUT)
                time.sleep(0.1)
                self._serial.reset_input_buffer()
                logger.info("Connected to Flipper at %s @ %d baud (attempt %d)", self.port, self.baud, attempt)
                return
            except (pyserial.SerialException, OSError) as e:
                last_error = e
                logger.warning("Connection attempt %d/%d failed: %s", attempt, retries, e)
                if attempt < retries:
                    time.sleep(retry_delay)

        raise ConnectionError(f"Failed to connect to Flipper at {self.port} after {retries} attempts: {last_error}")

    def disconnect(self) -> None:
        """Close the serial connection."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Disconnected from %s", self.port)
        self._serial = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def ensure_connected(self) -> None:
        """Reconnect if the serial connection has dropped."""
        if not self.is_connected:
            logger.info("Connection lost, attempting reconnect...")
            self._serial = None
            self.connect()

    # ── Low-level send/receive ───────────────────────────────────

    def _send(self, command: str) -> None:
        """Send a command line to the Flipper.

        Raises:
            ConnectionError: If the bridge is not connected.
            ValueError: If *command* spans more than one line.  The protocol is
                line-based, so an embedded newline would arrive as two separate
                commands and the second would be attacker-chosen.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to Flipper")

        if "\n" in command or "\r" in command:
            raise ValueError(f"Bridge commands must be a single line: {command!r}")

        with self._lock:
            line = command.strip() + "\r\n"
            self._serial.write(line.encode("utf-8"))
            self._serial.flush()
            logger.debug("TX: %s", command.strip())

    def _recv_line(self, timeout: float = _READ_TIMEOUT) -> str | None:
        """Read a single response line. Returns None on timeout.

        Uses ``read_until`` rather than ``readline()`` because pyserial's
        ``readline()`` can return partial data when there are brief gaps
        between USB CDC packets (64-byte transfers).  ``read_until`` keeps
        reading until the delimiter is found, the size cap is hit, or the
        timeout expires, so it reliably spans multiple CDC packets.

        Args:
            timeout: Seconds to wait for a complete line.
        """
        if not self.is_connected:
            return None

        old_timeout = self._serial.timeout
        self._serial.timeout = timeout
        try:
            # Cap the read: a device stuck emitting bytes with no newline
            # would otherwise grow this buffer until the timeout expires.
            raw = self._serial.read_until(b"\n", _MAX_LINE_BYTES)
        finally:
            self._serial.timeout = old_timeout

        if not raw:
            return None

        # A response with no terminator is incomplete, whatever its length.
        # This used to be checked only against _MAX_LINE_BYTES, so an oversized
        # read was discarded but a *short* one was not: firmware that stops
        # mid-line after a single 64-byte USB CDC packet returned a truncated
        # line that then failed to parse as JSON, and the caller reported an
        # empty list rather than a broken transfer.
        if not bytes(raw).endswith(b"\n"):
            if len(raw) >= _MAX_LINE_BYTES:
                logger.warning("Discarding oversized bridge response (%d bytes, no newline)", len(raw))
            else:
                raise IncompleteResponse(bytes(raw))
            return None

        line = bytes(raw).decode("utf-8", errors="replace").strip()
        if not line:
            return None

        logger.debug("RX: %s", line[:200])
        return line

    def _send_recv(self, command: str, timeout: float = _READ_TIMEOUT) -> str | None:
        """Send a command and return the first response line."""
        self._send(command)
        return self._recv_line(timeout)

    # ── High-level commands ──────────────────────────────────────

    def ping(self) -> bool:
        """Send PING, return True if we get OK PONG."""
        resp = self._send_recv("PING")
        return resp is not None and "PONG" in resp

    def status(self) -> dict:
        """Query current Flipper state.

        Returns dict with ``state`` and ``payloads`` keys.

        Firmware still reporting a ``convos=`` field is tolerated rather than
        rejected: the field is simply not read, so a Flipper running an older
        FAP keeps answering STATUS correctly.
        """
        resp = self._send_recv("STATUS")
        if resp is None:
            return {"state": "unknown", "payloads": 0}

        # Parse: "OK STATUS idle payloads=25"
        result: dict = {"state": "unknown", "payloads": 0}
        parts = resp.split()
        if len(parts) >= 3 and parts[0] == "OK" and parts[1] == "STATUS":
            result["state"] = parts[2]
            for part in parts[3:]:
                if part.startswith("payloads="):
                    result["payloads"] = _parse_count(part[len("payloads=") :], "payloads")
        return result

    def list_payloads(self) -> list[dict]:
        """List payloads loaded on the Flipper.

        Returns a list of dicts with ``name``, ``category``, ``builtin`` keys.

        Raises:
            IncompleteResponse: The device stopped mid-line.  This is the one
                query whose reply is long enough to span several USB packets,
                so it is where truncating firmware shows up first, and an empty
                list would misreport a transfer fault as an empty device.
        """
        resp = self._send_recv("LIST", timeout=5.0)
        return self._parse_data_line(resp)

    def execute_badusb(self, name: str) -> tuple[bool, str]:
        """Execute a payload via BadUSB.

        Returns ``(success, message)``.
        """
        self._send(f"EXEC BADUSB {name}")
        # First response: OK EXECUTING <name> or ERR ...
        resp = self._recv_line(timeout=5.0)
        if resp is None:
            return False, "No response from Flipper"
        if resp.startswith("ERR"):
            return False, resp

        # Wait for completion: OK DONE <name> or ERR ...
        done = self._recv_line(timeout=120.0)  # BadUSB can take a while
        if done is None:
            return False, "Timed out waiting for execution to complete"
        if done.startswith("OK DONE"):
            return True, done
        return False, done

    def execute_nfc(self, name: str) -> tuple[bool, str]:
        """Write an NFC NDEF file for the named payload on the Flipper.

        Returns ``(success, message)`` where message contains the file path
        on success (``OK WRITTEN /ext/nfc/...``).
        """
        resp = self._send_recv(f"EXEC NFC {name}", timeout=10.0)
        if resp is None:
            return False, "No response from Flipper"
        if resp.startswith("OK WRITTEN"):
            return True, resp
        return False, resp

    def execute_ble(self, name: str) -> tuple[bool, str]:
        """Start BLE extra beacon advertising for the named payload.

        Returns ``(success, message)``.  The Flipper broadcasts for ~60s
        or until ``stop_ble()`` is called.
        """
        resp = self._send_recv(f"EXEC BLE {name}", timeout=10.0)
        if resp is None:
            return False, "No response from Flipper"
        if resp.startswith("OK BROADCASTING"):
            return True, resp
        return False, resp

    def execute_qr(self, name: str) -> tuple[bool, str]:
        """Display the named payload as a QR code on the Flipper screen.

        Returns ``(success, message)``.
        """
        resp = self._send_recv(f"EXEC QR {name}", timeout=5.0)
        if resp is None:
            return False, "No response from Flipper"
        if resp.startswith("OK"):
            return True, resp
        return False, resp

    def stop_ble(self) -> bool:
        """Stop an active BLE broadcast."""
        resp = self._send_recv("STOP BLE")
        return resp is not None and resp.startswith("OK")

    def stop(self) -> bool:
        """Abort the current execution."""
        resp = self._send_recv("STOP")
        return resp is not None and resp.startswith("OK")

    def load_payload(self, name: str, text: str) -> tuple[bool, str]:
        """Push a one-off payload to the Flipper (no SD card needed).

        Returns ``(success, message)``.
        """
        # json.dumps escapes every control character and quotes the name too.
        # Hand-rolled replaces missed tabs and carriage returns, which produced
        # a line the Flipper's parser rejected, and left the name unescaped.
        json_str = json.dumps({"name": name, "text": text}, separators=(",", ":"))
        resp = self._send_recv(f"LOAD {json_str}")
        if resp is None:
            return False, "No response"
        if resp.startswith("OK"):
            return True, resp
        return False, resp

    def reload(self) -> tuple[bool, str]:
        """Hot-reload payloads and sequences from SD card.

        Returns ``(success, message)`` with updated counts.
        """
        resp = self._send_recv("RELOAD")
        if resp is None:
            return False, "No response"
        if resp.startswith("OK"):
            return True, resp
        return False, resp

    def set_delay(self, ms: int) -> bool:
        """Set the BadUSB start delay."""
        resp = self._send_recv(f"SET DELAY {ms}")
        return resp is not None and resp.startswith("OK")

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _parse_data_line(resp: str | None) -> list[dict]:
        """Parse a single DATA [...] response line."""
        if not resp:
            return []

        # Strip "DATA " prefix
        payload = resp
        if payload.startswith("DATA "):
            payload = payload[5:]

        try:
            data = json.loads(payload)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            logger.warning("Failed to parse DATA response: %s", payload[:200])
        return []

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()


__all__ = ["FlipperBridge"]
