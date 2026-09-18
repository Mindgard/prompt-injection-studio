"""Tests for BLE advertising TX."""

import re
from unittest.mock import patch

from pistudio.hardware.ubertooth.ble_advertise import (
    _generate_random_bdaddr,
    advertise_hci,
    stop_hci_advertising,
)


class TestRandomBdAddr:
    def test_format_is_valid_mac(self):
        addr = _generate_random_bdaddr()
        assert re.match(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", addr)

    def test_random_static_type_bits(self):
        """Top two bits of first octet (MSB) must be 11."""
        addr = _generate_random_bdaddr()
        first_octet = int(addr.split(":")[0], 16)
        assert first_octet & 0xC0 == 0xC0

    def test_two_calls_produce_different_addresses(self):
        a = _generate_random_bdaddr()
        b = _generate_random_bdaddr()
        assert a != b


class TestAdvertiseHci:
    @patch("subprocess.run")
    def test_calls_hciconfig_up(self, mock_run):
        mock_run.return_value.returncode = 0
        advertise_hci(b"\x02\x01\x06", duration_secs=0)
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("up" in c for c in calls)

    @patch("subprocess.run")
    def test_sets_advertising_data(self, mock_run):
        mock_run.return_value.returncode = 0
        advertise_hci(b"\x02\x01\x06", duration_secs=0)
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("0x0008" in c for c in calls)

    @patch("subprocess.run")
    def test_sets_random_addr_by_default(self, mock_run):
        mock_run.return_value.returncode = 0
        advertise_hci(b"\x02\x01\x06", duration_secs=0)
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("0x0005" in c for c in calls)

    @patch("subprocess.run")
    def test_no_random_addr_when_disabled(self, mock_run):
        mock_run.return_value.returncode = 0
        advertise_hci(b"\x02\x01\x06", duration_secs=0, randomize_addr=False)
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert not any("0x0005" in c for c in calls)


class TestStopAdvertising:
    @patch("subprocess.run")
    def test_disables_advertising(self, mock_run):
        mock_run.return_value.returncode = 0
        stop_hci_advertising()
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("0x000a" in c for c in calls)
