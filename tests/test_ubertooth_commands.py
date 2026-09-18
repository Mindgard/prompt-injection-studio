"""Tests for hw ubertooth command routing."""

import os
from io import StringIO
from unittest.mock import MagicMock, patch

from rich.console import Console


def _make_shell(tmp_path):
    """Create a MagicMock shell for testing."""
    shell = MagicMock()
    buf = StringIO()
    shell.console = Console(file=buf, no_color=True, width=120)
    shell.session_dir = str(tmp_path / "session")
    os.makedirs(shell.session_dir, exist_ok=True)
    shell.session_dir = shell.session_dir
    shell.json_mode = False
    shell.out = MagicMock()
    shell.audit = MagicMock()
    return shell, buf


def _strip_ansi(text):
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _get_hw_cmd():
    from pistudio.commands.hw.command import HwCommand

    return HwCommand()


class TestUbertoothHelp:
    def test_help_shows_subcommands(self, tmp_path):
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "--help"])
        # Help is sent via shell.out.info
        call_args = shell.out.info.call_args[0][0]
        assert "ble-adv" in call_args
        assert "ble-sniff" in call_args
        assert "bt-scan" in call_args
        assert "trigger" in call_args
        assert "--dry-run" in call_args

    def test_help_via_alias(self, tmp_path):
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ut", "--help"])
        call_args = shell.out.info.call_args[0][0]
        assert "ble-adv" in call_args

    def test_help_no_args(self, tmp_path):
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth"])
        call_args = shell.out.info.call_args[0][0]
        assert "ble-adv" in call_args


class TestUbertoothDevices:
    @patch("pistudio.hardware.ubertooth.device.find_ubertooth", return_value=None)
    def test_no_device_found(self, mock_find, tmp_path):
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "devices"])
        output = buf.getvalue()
        assert "No Ubertooth found" in output

    @patch("pistudio.hardware.ubertooth.device.find_ubertooth")
    @patch("pistudio.hardware.ubertooth.device.check_tools", return_value=[])
    def test_device_found(self, mock_check, mock_find, tmp_path):
        mock_find.return_value = {
            "vid_pid": "1d50:6002",
            "firmware_version": "2020-12-R1",
            "tools": {"ubertooth-btle": True, "ubertooth-scan": True},
        }
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "devices"])
        output = buf.getvalue()
        assert "Ubertooth One" in output

    @patch("pistudio.hardware.ubertooth.device.find_ubertooth")
    @patch("pistudio.hardware.ubertooth.device.check_tools", return_value=["ubertooth-btle"])
    def test_missing_tools_shown(self, mock_check, mock_find, tmp_path):
        mock_find.return_value = {
            "vid_pid": "1d50:6002",
            "firmware_version": "2020-12-R1",
            "tools": {"ubertooth-btle": False, "ubertooth-scan": True},
        }
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "devices"])
        output = buf.getvalue()
        assert "Missing tools" in output


class TestUbertoothBleAdvDryRun:
    @patch("pistudio.hardware.ubertooth.ble_advertise.advertise_hci")
    @patch("pistudio.hardware.payloads.get_payload")
    def test_dry_run_does_not_transmit(self, mock_get, mock_adv, tmp_path):
        from pistudio.hardware.payloads import Payload

        mock_get.return_value = (Payload(name="test", text="hello", category="test", description="test"), "builtin")
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "ble-adv", "test", "--dry-run"])
        output = buf.getvalue()
        mock_adv.assert_not_called()
        assert "--dry-run" in output

    @patch("pistudio.hardware.payloads.get_payload", return_value=None)
    def test_missing_payload(self, mock_get, tmp_path):
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "ble-adv", "nonexistent"])
        shell.out.error.assert_called()
        error_msg = shell.out.error.call_args[0][0]
        assert "not found" in error_msg

    def test_no_payload_name(self, tmp_path):
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "ble-adv"])
        shell.out.error.assert_called()
        error_msg = shell.out.error.call_args[0][0]
        assert "Usage" in error_msg


class TestUbertoothBtScan:
    @patch("pistudio.hardware.ubertooth.classic_scan.scan_discoverable", return_value=[])
    def test_scan_no_devices(self, mock_scan, tmp_path):
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "bt-scan"])
        output = buf.getvalue()
        assert "0 device(s) found" in output

    @patch(
        "pistudio.hardware.ubertooth.classic_scan.scan_discoverable",
        return_value=[{"addr": "AA:BB:CC:DD:EE:FF", "name": "TestDev", "type": "classic"}],
    )
    def test_scan_finds_device(self, mock_scan, tmp_path):
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "bt-scan"])
        output = buf.getvalue()
        assert "1 device(s) found" in output
        assert "AA:BB:CC:DD:EE:FF" in output


class TestUbertoothSpectrum:
    def test_spectrum_not_implemented(self, tmp_path):
        shell, buf = _make_shell(tmp_path)
        hw = _get_hw_cmd()
        hw.execute(shell, ["ubertooth", "spectrum"])
        output = buf.getvalue()
        assert "not yet implemented" in output


class TestUbertoothCompletion:
    def test_top_level_completion(self, tmp_path):
        from pistudio.commands.hw.ubertooth import complete_ubertooth

        shell, _ = _make_shell(tmp_path)
        result = complete_ubertooth(shell, [])
        assert "devices" in result
        assert "ble-adv" in result
        assert "trigger" in result

    def test_partial_completion(self, tmp_path):
        from pistudio.commands.hw.ubertooth import complete_ubertooth

        shell, _ = _make_shell(tmp_path)
        result = complete_ubertooth(shell, ["ble"])
        assert "ble-adv" in result
        assert "ble-sniff" in result
        assert "devices" not in result
