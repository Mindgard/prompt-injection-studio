"""Transport-level tests for the Flipper serial bridge.

These use a fake serial port that behaves like pyserial rather than a
MagicMock, so a change to how the bridge frames or reads a line shows up here
instead of being absorbed by the mock.
"""

import json

import pytest

from pistudio.hardware.flipper.bridge import FlipperBridge


class FakeSerial:
    """A minimal stand-in for ``serial.Serial`` covering what the bridge uses."""

    def __init__(self, responses: list[bytes] | None = None):
        self.is_open = True
        self.timeout = 1.0
        self.written = b""
        self._responses = list(responses or [])

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def flush(self) -> None:
        pass

    def read_until(self, expected: bytes = b"\n", size: int | None = None) -> bytes:
        if not self._responses:
            return b""
        chunk = self._responses.pop(0)
        return chunk[:size] if size is not None else chunk

    def reset_input_buffer(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    @property
    def sent_lines(self) -> list[str]:
        return self.written.decode().splitlines()


def _bridge(responses: list[bytes] | None = None) -> tuple[FlipperBridge, FakeSerial]:
    bridge = FlipperBridge("/dev/fake")
    fake = FakeSerial(responses)
    bridge._serial = fake
    return bridge, fake


class TestStatusParsing:
    def test_a_well_formed_status_is_parsed(self):
        bridge, _ = _bridge([b"OK STATUS idle payloads=25\n"])

        assert bridge.status() == {"state": "idle", "payloads": 25}

    def test_firmware_still_reporting_convos_is_tolerated(self):
        """Older FAP builds send a convos= field the host no longer reads.

        Ignoring an unknown field rather than rejecting the line keeps a
        Flipper running the previous firmware answering STATUS correctly.
        """
        bridge, _ = _bridge([b"OK STATUS idle payloads=25 convos=6\n"])

        status = bridge.status()

        assert status == {"state": "idle", "payloads": 25}
        assert "conversations" not in status

    @pytest.mark.parametrize("value", ["abc", "", "12x", "-", "1.5"])
    def test_a_non_numeric_count_does_not_raise(self, value):
        """A truncated packet or mismatched firmware must not crash a query."""
        bridge, _ = _bridge([f"OK STATUS idle payloads={value}\n".encode()])

        status = bridge.status()

        assert status["payloads"] == 0
        assert status["state"] == "idle"

    def test_no_response_returns_the_unknown_default(self):
        bridge, _ = _bridge([])

        assert bridge.status()["state"] == "unknown"


class TestLoadPayloadFraming:
    @pytest.mark.parametrize(
        "text",
        [
            "plain text",
            "tab\there",
            "carriage\rreturn",
            "new\nline",
            'quote " and backslash \\',
            "control \x01 byte",
        ],
    )
    def test_the_wire_format_is_valid_json(self, text):
        """Hand-rolled escaping missed tabs and CRs, producing unparseable JSON."""
        bridge, fake = _bridge([b"OK LOADED\n"])

        bridge.load_payload("payload", text)

        sent = fake.written.decode().strip()
        assert sent.startswith("LOAD ")
        assert json.loads(sent[len("LOAD ") :]) == {"name": "payload", "text": text}

    def test_a_hostile_name_is_escaped_too(self):
        bridge, fake = _bridge([b"OK LOADED\n"])

        bridge.load_payload('na"me', "text")

        sent = fake.written.decode().strip()
        assert json.loads(sent[len("LOAD ") :])["name"] == 'na"me'

    def test_the_command_occupies_exactly_one_line(self):
        """A payload newline reaching the wire would become a second command."""
        bridge, fake = _bridge([b"OK LOADED\n"])

        bridge.load_payload("payload", "first\nsecond")

        assert len(fake.sent_lines) == 1


class TestSendRefusesMultilineCommands:
    @pytest.mark.parametrize("command", ["EXEC BADUSB a\nSTOP", "PING\r\nSTOP"])
    def test_an_embedded_newline_is_rejected(self, command):
        bridge, fake = _bridge([b"OK\n"])

        with pytest.raises(ValueError, match="single line"):
            bridge._send(command)

        assert fake.written == b""

    def test_an_ordinary_command_is_sent(self):
        bridge, fake = _bridge([b"OK PONG\n"])

        assert bridge.ping() is True
        assert fake.written == b"PING\r\n"


class TestReadIsBounded:
    def test_a_line_without_a_newline_is_capped(self):
        """A device stuck emitting bytes must not grow the buffer forever."""
        bridge, fake = _bridge([b"A" * 200_000])

        assert bridge._recv_line() is None

    def test_a_normal_line_is_returned(self):
        bridge, _ = _bridge([b"OK DONE payload\n"])

        assert bridge._recv_line() == "OK DONE payload"

    def test_a_short_unterminated_line_is_not_treated_as_data(self):
        """Truncation is truncation whatever the length.

        The guard only fired at the size cap, so an oversized read was
        discarded but a short one was returned and then failed to parse. Real
        firmware stopped after a single 64-byte USB CDC packet, and `list`
        reported "No payloads loaded" for a device holding 45 of them.
        """
        from pistudio.hardware.flipper.bridge import IncompleteResponse

        bridge, _ = _bridge([b'DATA [{"name":"ignore-instructions","category":"instruction-over'])

        with pytest.raises(IncompleteResponse):
            bridge._recv_line()

    def test_the_error_names_the_packet_boundary(self):
        """64 bytes exactly points at the firmware's write loop, not the cable."""
        from pistudio.hardware.flipper.bridge import IncompleteResponse

        bridge, _ = _bridge([b"D" * 64])

        with pytest.raises(IncompleteResponse) as exc:
            bridge._recv_line()
        assert "1 USB packet" in str(exc.value)
        assert exc.value.partial == b"D" * 64

    def test_a_truncated_list_does_not_look_like_an_empty_device(self):
        from pistudio.hardware.flipper.bridge import IncompleteResponse

        bridge, _ = _bridge([b'DATA [{"name":"a","category":"b"},{"name":"c","categ'])

        with pytest.raises(IncompleteResponse):
            bridge.list_payloads()

    def test_a_complete_list_still_parses(self):
        bridge, _ = _bridge([b'DATA [{"name":"a","category":"b","builtin":true}]\n'])

        assert bridge.list_payloads() == [{"name": "a", "category": "b", "builtin": True}]

    def test_the_read_is_size_limited(self):
        """The cap must reach pyserial, not just be checked afterwards."""
        captured: dict[str, int | None] = {}

        class RecordingSerial(FakeSerial):
            def read_until(self, expected: bytes = b"\n", size: int | None = None) -> bytes:
                captured["size"] = size
                return b"OK\n"

        bridge = FlipperBridge("/dev/fake")
        bridge._serial = RecordingSerial()

        bridge._recv_line()

        assert captured["size"] is not None and captured["size"] > 0
