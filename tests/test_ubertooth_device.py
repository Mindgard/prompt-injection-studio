"""Tests for Ubertooth device detection."""

from unittest.mock import patch

from pistudio.hardware.ubertooth.device import (
    check_tools,
    find_ubertooth,
)


class TestFindUbertooth:
    @patch("subprocess.run")
    def test_found_via_lsusb(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Bus 001 Device 005: ID 1d50:6002"
        with patch("shutil.which", return_value="/usr/bin/ubertooth-btle"):
            result = find_ubertooth()
        assert result is not None
        assert result["vid_pid"] == "1d50:6002"

    @patch("subprocess.run")
    def test_not_found(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        result = find_ubertooth()
        assert result is None


class TestCheckTools:
    @patch("shutil.which", return_value=None)
    def test_missing_tools_reported(self, mock_which):
        missing = check_tools()
        assert "ubertooth-btle" in missing
        assert "ubertooth-scan" in missing

    @patch("shutil.which", return_value="/usr/bin/ubertooth-btle")
    def test_all_tools_present(self, mock_which):
        missing = check_tools()
        assert len(missing) == 0
