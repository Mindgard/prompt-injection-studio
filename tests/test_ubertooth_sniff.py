"""Tests for BLE sniffing and device identification."""

from pistudio.hardware.ubertooth.ble_sniff import (
    identify_ai_devices,
    parse_sniff_output,
)


class TestParseSniffOutput:
    def test_extracts_addresses(self):
        output = (
            "systime=123 ch=37 aa=8e89bed6\n"
            "  AdvA: 00:11:22:33:44:55 (public)\n"
            "systime=124 ch=38 aa=8e89bed6\n"
            "  AdvA: AA:BB:CC:DD:EE:FF (random)\n"
            "systime=125 ch=37 aa=8e89bed6\n"
            "  AdvA: 00:11:22:33:44:55 (public)\n"
        )
        devices = parse_sniff_output(output)
        assert len(devices) == 2
        addrs = {d["addr"] for d in devices}
        assert "00:11:22:33:44:55" in addrs
        assert "AA:BB:CC:DD:EE:FF" in addrs

    def test_counts_seen(self):
        output = (
            "  AdvA: 00:11:22:33:44:55 (public)\n"
            "  AdvA: 00:11:22:33:44:55 (public)\n"
            "  AdvA: 00:11:22:33:44:55 (public)\n"
        )
        devices = parse_sniff_output(output)
        assert devices[0]["seen_count"] == 3

    def test_empty_input(self):
        assert parse_sniff_output("") == []


class TestIdentifyAiDevices:
    def test_matches_by_name(self):
        devices = [
            {"addr": "00:11:22:33:44:55", "name": "Echo Dot"},
            {"addr": "AA:BB:CC:DD:EE:FF", "name": "Logitech Mouse"},
        ]
        ai = identify_ai_devices(devices)
        assert len(ai) == 1
        assert ai[0]["ai_type"] == "Amazon Alexa"

    def test_matches_by_oui(self):
        devices = [{"addr": "44:07:0B:AA:BB:CC", "name": ""}]
        ai = identify_ai_devices(devices)
        assert len(ai) == 1
        assert "Amazon" in ai[0]["ai_type"]

    def test_no_match(self):
        devices = [{"addr": "DE:AD:BE:EF:00:01", "name": "Random Device"}]
        assert identify_ai_devices(devices) == []
