"""Writing a payload onto a UART line, and reading what comes back.

Delivering text to a serial console is not just ``write(payload)``.  Three
things decide whether the target accepts it:

*Line ending.*  A console waits for a terminator before it acts.  Which one
varies -- ``\\r\\n`` for most embedded monitors and anything DOS-descended,
``\\n`` for Unix-style shells, a bare ``\\r`` for some MCU REPLs.  Send the
wrong one and the payload sits in the target's input buffer, unread.

*Pacing.*  Many embedded consoles poll the UART from the main loop and have no
receive FIFO worth the name.  Bytes arriving back-to-back at 115200 are simply
dropped, which looks like a truncated payload rather than a timing fault.  A
per-character delay fixes it at the cost of speed.

*Reading back.*  Without capturing the reply there is no way to tell "the
target acted on it" from "the target ignored it", which is the whole question
a red-team test is asking.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

__all__ = ["LINE_ENDINGS", "UartError", "UartResult", "UartSettings", "send_payload"]

logger = logging.getLogger(__name__)

#: How to terminate the payload.  Named rather than taken as raw bytes so the
#: choice is visible in help and completion instead of buried in escaping.
LINE_ENDINGS: dict[str, bytes] = {
    "crlf": b"\r\n",
    "lf": b"\n",
    "cr": b"\r",
    "none": b"",
}


class UartError(Exception):
    """The port could not be opened, or the write failed part-way."""


@dataclass(frozen=True, slots=True)
class UartSettings:
    """Everything that decides how bytes hit the wire.

    Defaults target the common case: a 115200 8N1 console expecting CRLF.
    """

    port: str
    baud: int = 115200
    line_ending: str = "crlf"
    char_delay_ms: float = 0.0
    read_for: float = 2.0
    #: 8N1 is near-universal; exposed so an odd target is still reachable.
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1


@dataclass
class UartResult:
    """What happened on the wire."""

    port: str
    baud: int
    bytes_written: int = 0
    reply: bytes = b""
    matched: bool | None = None
    expected: str = ""
    elapsed: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def reply_text(self) -> str:
        """The reply as text, with undecodable bytes shown rather than dropped."""
        return self.reply.decode("utf-8", errors="replace")

    def as_dict(self) -> dict:
        """A JSON-safe view, for ``--json`` and the MCP tool."""
        return {
            "port": self.port,
            "baud": self.baud,
            "bytes_written": self.bytes_written,
            "reply": self.reply_text,
            "reply_bytes": len(self.reply),
            "expected": self.expected,
            "matched": self.matched,
            "elapsed_seconds": round(self.elapsed, 3),
            "notes": self.notes,
        }


def _open(settings: UartSettings):
    """Open the port, translating driver errors into one studio error type."""
    try:
        import serial
    except ImportError as exc:
        raise UartError(
            "pyserial is not installed. Install with: pip install 'prompt-injection-studio[hardware]'"
        ) from exc

    try:
        return serial.Serial(
            settings.port,
            settings.baud,
            bytesize=settings.bytesize,
            parity=settings.parity,
            stopbits=settings.stopbits,
            timeout=0.2,
            write_timeout=5.0,
        )
    except serial.SerialException as exc:
        # The usual causes are a cable pulled since the scan, or another
        # program holding the port, so say both rather than echoing errno.
        raise UartError(
            f"Cannot open {settings.port}: {exc}. Check the cable is attached "
            "and no other program (screen, minicom) holds it."
        ) from exc


def send_payload(text: str, settings: UartSettings, *, expect: str = "") -> UartResult:
    """Transmit *text* and capture the reply.

    Args:
        text: The payload.  Sent as UTF-8; a target expecting 7-bit ASCII will
            see the multi-byte sequences, which is usually what a test wants.
        settings: Port, framing and pacing.
        expect: When given, the reply is searched for this and the result's
            ``matched`` says whether it was found -- the success oracle.

    Returns:
        A :class:`UartResult` describing what was written and received.

    Raises:
        UartError: The port could not be opened, or the write failed.
    """
    ending = LINE_ENDINGS.get(settings.line_ending)
    if ending is None:
        raise UartError(f"Unknown line ending {settings.line_ending!r}. Use one of: {', '.join(LINE_ENDINGS)}")

    body = text.encode("utf-8") + ending
    result = UartResult(port=settings.port, baud=settings.baud, expected=expect)
    started = time.monotonic()

    serial_port = _open(settings)
    try:
        # Drop anything the target said before we arrived, so the reply window
        # captures the response to *this* payload and not stale boot output.
        serial_port.reset_input_buffer()

        if settings.char_delay_ms > 0:
            delay = settings.char_delay_ms / 1000.0
            # A deadline for the whole paced write, not just each byte.  A
            # target that stops reading -- flow control asserted, or simply
            # wedged -- fills the driver buffer and blocks the next write
            # forever; pyserial's write_timeout is per call, so single-byte
            # writes keep "succeeding" until they do not return at all.
            budget = _write_budget(len(body), settings)
            deadline = time.monotonic() + budget
            for index in range(len(body)):
                if time.monotonic() > deadline:
                    raise UartError(
                        f"Timed out after {result.bytes_written} of {len(body)} bytes. "
                        f"The target stopped accepting input -- check flow control, "
                        f"or lower --char-delay ({settings.char_delay_ms}ms)."
                    )
                result.bytes_written += serial_port.write(body[index : index + 1]) or 0
                time.sleep(delay)
        else:
            result.bytes_written = serial_port.write(body) or 0
        serial_port.flush()

        if settings.read_for > 0:
            result.reply = _read_for(serial_port, settings.read_for)
    except Exception as exc:  # noqa: BLE001 - re-raised as UartError below
        raise UartError(f"Write to {settings.port} failed after {result.bytes_written} bytes: {exc}") from exc
    finally:
        serial_port.close()

    result.elapsed = time.monotonic() - started

    if expect:
        result.matched = expect in result.reply_text
    if not result.reply and settings.read_for > 0:
        # Silence is the normal case for a one-way tap, so say what it means
        # rather than letting it read as a failure.
        result.notes.append("No reply. The target may not echo, or RX may not be connected.")

    return result


def _write_budget(length: int, settings: UartSettings) -> float:
    """How long a paced write should be allowed to take, generously.

    The pacing itself sets the floor; the margin covers a slow target without
    letting a wedged one hang the studio.
    """
    paced = length * settings.char_delay_ms / 1000.0
    return max(10.0, paced * 3)


def _read_for(serial_port, seconds: float) -> bytes:
    """Collect output for *seconds*, stopping early once the target goes quiet."""
    deadline = time.monotonic() + seconds
    quiet_after = 0.4
    buffer = bytearray()
    last_byte_at = time.monotonic()

    while time.monotonic() < deadline:
        chunk = serial_port.read(1024)
        if chunk:
            buffer += chunk
            last_byte_at = time.monotonic()
        elif buffer and time.monotonic() - last_byte_at > quiet_after:
            # A console that has finished replying should not cost the caller
            # the rest of the window.
            break
    return bytes(buffer)
