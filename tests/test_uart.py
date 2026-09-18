"""UART delivery: port detection, framing, pacing and the success oracle.

Transport tests run against a pty loopback rather than real hardware, so they
exercise the actual pyserial path — open, write, read, close — without needing
a cable attached. Detection is tested against synthetic ``comports()`` entries,
because the point is recognising adapters this machine may not have.
"""

from __future__ import annotations

import os
import pty
import re
import threading
import time
from dataclasses import dataclass

import pytest

from pistudio.hardware.uart.device import BRIDGE_VENDORS, find_serial_ports, resolve_port
from pistudio.hardware.uart.transmit import LINE_ENDINGS, UartError, UartSettings, send_payload


@dataclass
class FakePort:
    """The subset of a pyserial ListPortInfo that detection reads."""

    device: str
    description: str = "n/a"
    hwid: str = "n/a"
    serial_number: str | None = None


def _ports(monkeypatch, *entries: FakePort) -> None:
    monkeypatch.setattr("serial.tools.list_ports.comports", lambda: list(entries))


FTDI = FakePort("/dev/cu.usbserial-A1", "FT232R USB UART", "USB VID:PID=0403:6001 SER=A1", "A1")
CP210X = FakePort("/dev/ttyUSB0", "CP2102 UART Bridge", "USB VID:PID=10c4:ea60 SER=B2", "B2")
FLIPPER = FakePort("/dev/cu.usbmodemflip_X", "Flipper X", "USB VID:PID=0483:5740 SER=flip_X", "flip_X")
BLUETOOTH = FakePort("/dev/cu.Bluetooth-Incoming-Port")


class TestAdapterDetection:
    """The CDC-ACM detectors miss USB-TTL cables, which is why this exists."""

    def test_an_ftdi_cable_is_found(self, monkeypatch):
        _ports(monkeypatch, FTDI)
        found = find_serial_ports(bridges_only=True)
        assert [p.device for p in found] == ["/dev/cu.usbserial-A1"]
        assert found[0].chip == "FTDI"

    @pytest.mark.parametrize("vid", sorted(BRIDGE_VENDORS))
    def test_every_known_bridge_vendor_is_recognised(self, monkeypatch, vid):
        _ports(monkeypatch, FakePort("/dev/x", "bridge", f"USB VID:PID={vid}:0001"))
        assert find_serial_ports(bridges_only=True)[0].chip == BRIDGE_VENDORS[vid]

    def test_the_bunny_detector_would_have_missed_it(self):
        """The gap this module closes, stated as a test.

        ``find_bunny_serial_ports`` filters for CDC-ACM paths, so an FTDI
        cable enumerating as ``usbserial`` was invisible to every scan.
        """
        from pistudio.hardware.hak5.serial_console import find_bunny_serial_ports

        assert "usbserial" not in " ".join(find_bunny_serial_ports())

    def test_noise_ports_are_hidden(self, monkeypatch):
        _ports(monkeypatch, BLUETOOTH, FTDI)
        assert BLUETOOTH.device not in [p.device for p in find_serial_ports()]

    def test_a_studio_device_says_which_command_owns_it(self, monkeypatch):
        """A Flipper is a serial port too; `uart` is not how to drive it."""
        _ports(monkeypatch, FLIPPER)
        port = find_serial_ports()[0]
        assert port.is_bridge is False
        assert port.owned_by == "hw flipper"

    def test_bridges_sort_before_other_devices(self, monkeypatch):
        _ports(monkeypatch, FLIPPER, FTDI)
        assert find_serial_ports()[0].device == FTDI.device


class TestPortResolution:
    def test_an_explicit_port_always_wins(self, monkeypatch):
        _ports(monkeypatch, FTDI)
        assert resolve_port("/dev/chosen")[0] == "/dev/chosen"

    def test_a_single_adapter_is_selected(self, monkeypatch):
        _ports(monkeypatch, FTDI, FLIPPER)
        port, reason = resolve_port()
        assert port == FTDI.device
        assert "only USB-TTL adapter" in reason

    def test_two_adapters_refuse_to_guess(self, monkeypatch):
        """Picking one risks transmitting into the wrong target."""
        _ports(monkeypatch, FTDI, CP210X)
        port, reason = resolve_port()
        assert port is None
        assert "--serial-port" in reason
        assert FTDI.device in reason and CP210X.device in reason

    def test_no_adapter_names_what_else_is_there(self, monkeypatch):
        _ports(monkeypatch, FLIPPER)
        port, reason = resolve_port()
        assert port is None
        assert FLIPPER.device in reason

    def test_nothing_at_all_says_so(self, monkeypatch):
        _ports(monkeypatch)
        assert resolve_port() == (None, "no serial ports found. Plug in a USB-TTL adapter.")


class _Loopback:
    """A pty standing in for a target that echoes and replies."""

    def __init__(self, reply: bytes = b"") -> None:
        self._primary, secondary = pty.openpty()
        self.port = os.ttyname(secondary)
        self.received = b""
        self._reply = reply
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        # Keep draining: a pty buffer is small, and a paced write that fills it
        # blocks the sender.  A single read would model a target that stops
        # listening, which is a different test.
        import select

        deadline = time.monotonic() + 8
        replied = False
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self._primary], [], [], 0.1)
            if not ready:
                if self.received and not replied:
                    break
                continue
            try:
                chunk = os.read(self._primary, 4096)
            except OSError:
                break
            if not chunk:
                break
            self.received += chunk
            if self._reply and not replied:
                os.write(self._primary, self._reply)
                replied = True

    def settle(self) -> None:
        self._thread.join(timeout=3)


class TestFraming:
    """The terminator decides whether a console acts on the payload at all."""

    @pytest.mark.parametrize(("name", "expected"), sorted(LINE_ENDINGS.items()))
    def test_each_line_ending_reaches_the_wire(self, name, expected):
        target = _Loopback()
        send_payload("PAYLOAD", UartSettings(port=target.port, line_ending=name, read_for=0))
        target.settle()
        assert target.received == b"PAYLOAD" + expected

    def test_an_unknown_line_ending_is_refused(self):
        with pytest.raises(UartError, match="Unknown line ending"):
            send_payload("x", UartSettings(port="/dev/null", line_ending="wrong"))

    def test_the_payload_is_sent_as_utf8(self):
        target = _Loopback()
        send_payload("Ignore — 無視", UartSettings(port=target.port, line_ending="none", read_for=0))
        target.settle()
        assert target.received.decode("utf-8") == "Ignore — 無視"


class TestPacing:
    def test_a_character_delay_slows_the_write(self):
        """Targets polling the UART from a main loop drop back-to-back bytes."""
        target = _Loopback()
        started = time.monotonic()
        send_payload("0123456789", UartSettings(port=target.port, char_delay_ms=10, read_for=0, line_ending="none"))
        elapsed = time.monotonic() - started
        target.settle()
        assert elapsed >= 0.09, f"10 chars at 10ms should take ~0.1s, took {elapsed:.3f}s"
        assert target.received == b"0123456789"


class TestTheSuccessOracle:
    """Without reading the reply, delivery and silence look identical."""

    def test_a_matching_reply_is_reported(self):
        target = _Loopback(reply=b"OK ACCEPTED\r\n")
        result = send_payload("go", UartSettings(port=target.port, read_for=2.0), expect="OK ACCEPTED")
        assert result.matched is True
        assert "OK ACCEPTED" in result.reply_text

    def test_a_missing_expectation_is_reported(self):
        target = _Loopback(reply=b"ERROR\r\n")
        result = send_payload("go", UartSettings(port=target.port, read_for=1.0), expect="OK")
        assert result.matched is False

    def test_no_expectation_leaves_the_verdict_open(self):
        target = _Loopback(reply=b"hello\r\n")
        assert send_payload("go", UartSettings(port=target.port, read_for=1.0)).matched is None

    def test_silence_is_explained_rather_than_left_bare(self):
        target = _Loopback()
        result = send_payload("go", UartSettings(port=target.port, read_for=0.6))
        target.settle()
        assert result.reply == b""
        assert any("RX" in note for note in result.notes)

    def test_reading_stops_once_the_target_goes_quiet(self):
        """A finished reply should not cost the caller the whole window."""
        target = _Loopback(reply=b"done\r\n")
        started = time.monotonic()
        send_payload("go", UartSettings(port=target.port, read_for=5.0))
        assert time.monotonic() - started < 3.0

    def test_the_result_is_json_safe(self):
        target = _Loopback(reply=b"hi\r\n")
        payload = send_payload("go", UartSettings(port=target.port, read_for=1.0)).as_dict()
        import json

        assert json.loads(json.dumps(payload))["bytes_written"] > 0


class TestFailuresAreActionable:
    def test_a_missing_port_names_the_likely_causes(self):
        with pytest.raises(UartError) as exc:
            send_payload("x", UartSettings(port="/dev/definitely-not-a-port"))
        message = str(exc.value)
        assert "/dev/definitely-not-a-port" in message
        assert "cable" in message


class TestDiscoverableSettings:
    """A device path should never have to be copied out of lpstat or ls /dev."""

    def test_the_port_setting_offers_what_is_attached(self, monkeypatch):
        from pistudio.core.settings import choices_for

        _ports(monkeypatch, FTDI, CP210X)
        assert set(choices_for("uart.port")) == {FTDI.device, CP210X.device}

    def test_it_does_not_offer_a_device_another_command_owns(self, monkeypatch):
        """`hw flipper` speaks the Flipper's protocol; `uart` should not."""
        from pistudio.core.settings import choices_for

        _ports(monkeypatch, FTDI, FLIPPER)
        assert FLIPPER.device not in choices_for("uart.port")

    def test_detection_does_not_restrict_what_can_be_set(self, tmp_path, monkeypatch):
        """A cable to be plugged in tomorrow is still worth configuring now."""
        from pistudio.core.settings import Settings

        _ports(monkeypatch)
        settings = Settings(tmp_path)
        settings.set("uart.port", "/dev/ttyUSB9")
        assert settings.get("uart.port") == "/dev/ttyUSB9"

    def test_an_enum_setting_is_still_enforced(self, tmp_path):
        """Only discoverable settings are permissive; choices still bind."""
        from pistudio.core.settings import Settings

        with pytest.raises(ValueError, match="must be one of"):
            Settings(tmp_path).set("uart.line_ending", "sideways")

    def test_a_single_candidate_is_filled_in(self, studio, monkeypatch):
        from pistudio.commands import get_command
        from pistudio.core.settings import Settings

        _ports(monkeypatch, FTDI)
        monkeypatch.setattr("pistudio.core.settings._printer_names", lambda: ())
        get_command("settings").execute(studio, ["detect"])
        assert Settings(studio.session_dir).get("uart.port") == FTDI.device

    def test_several_candidates_are_never_guessed(self, studio, monkeypatch):
        """Choosing between two cables risks transmitting into the wrong one."""
        from pistudio.commands import get_command
        from pistudio.core.settings import Settings

        _ports(monkeypatch, FTDI, CP210X)
        monkeypatch.setattr("pistudio.core.settings._printer_names", lambda: ())
        get_command("settings").execute(studio, ["detect"])

        assert Settings(studio.session_dir).is_set("uart.port") is False
        # Colour escapes split the text, so strip them before matching.
        out = re.sub(r"\x1b\[[0-9;]*m", "", studio.buf.getvalue())
        # Both offered as commands the user can paste.
        assert f"settings set uart.port {FTDI.device}" in out
        assert f"settings set uart.port {CP210X.device}" in out


class TestTheCommandSurface:
    """UART lives under `hw`: it is a cable, not a delivery route of its own."""

    def test_it_is_not_a_top_level_command(self):
        from pistudio.commands import get_command

        assert get_command("uart") is None

    def test_it_is_an_hw_subcommand(self):
        from pistudio.commands import get_command

        assert "uart" in get_command("hw").subcommands

    @pytest.mark.parametrize("alias", ["serial", "tty", "🔌"])
    def test_its_aliases_resolve(self, alias):
        from pistudio.commands import get_command

        assert get_command("hw").subcommand_aliases[alias] == "uart"

    def test_hw_completes_it(self):
        """Declared but uncompletable is how a subcommand goes unnoticed."""
        from pistudio.commands import get_command
        from pistudio.core.studio import Studio

        assert "uart" in get_command("hw").complete(Studio(), [""])

    def test_uart_does_not_reuse_the_tcp_port_flag(self):
        """`--port` is the TCP port on `serve`; one word, two meanings."""
        from pistudio.commands.hw.uart import UART_FLAGS

        names = {f.name for f in UART_FLAGS}
        assert "--serial-port" in names
        assert "--port" not in names

    def test_the_help_reads_as_an_hw_subcommand(self):
        from pistudio.commands.hw.uart import uart_usage

        usage = uart_usage()
        assert "hw uart send" in usage
        # A bare `uart send ...` example would not run anywhere.
        assert "\n  uart " not in usage

    def test_transmitting_asks_first(self, studio, monkeypatch):
        """Writing to a UART drives a physical device."""
        from pistudio.commands import get_command

        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        called: list[str] = []
        monkeypatch.setattr(
            "pistudio.hardware.uart.transmit.send_payload",
            lambda *a, **k: called.append("sent"),
        )
        monkeypatch.setattr("pistudio.hardware.uart.device.resolve_port", lambda *a: ("/dev/fake", "test"))

        get_command("hw").execute(studio, ["uart", "send", "payload text"])
        assert called == [], "transmitted without confirmation"
        assert "--yes" in studio.buf.getvalue()
