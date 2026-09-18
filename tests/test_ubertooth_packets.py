"""Tests for BLE advertising packet construction."""

import struct

from pistudio.hardware.ubertooth.packets import (
    AD_COMPLETE_LOCAL_NAME,
    AD_FLAGS,
    AD_MFG_SPECIFIC,
    AD_URI,
    FLAGS_OVERHEAD,
    MAX_ADV_PAYLOAD,
    MAX_SCAN_RSP,
    NAME_OVERHEAD,
    build_ad_structure,
    build_flags_ad,
    build_mfg_data_ad,
    build_name_ad,
    build_uri_ad,
    compile_auto,
    compile_flood,
    compile_micro,
    compile_packed,
    compile_url_redirect,
)


class TestAdStructureBuilders:
    def test_build_ad_structure_format(self):
        """AD structure is [length][type][data]."""
        data = b"hello"
        result = build_ad_structure(0x09, data)
        assert result[0] == len(data) + 1  # length includes type byte
        assert result[1] == 0x09
        assert result[2:] == data

    def test_build_flags_ad_is_3_bytes(self):
        """Flags AD is always exactly 3 bytes."""
        result = build_flags_ad()
        assert len(result) == FLAGS_OVERHEAD
        assert result[0] == 2  # length
        assert result[1] == AD_FLAGS
        # LE General Discoverable (0x02) + BR/EDR Not Supported (0x04)
        assert result[2] == 0x06

    def test_build_name_ad_complete(self):
        result = build_name_ad("Test", complete=True)
        assert result[1] == AD_COMPLETE_LOCAL_NAME
        assert result[2:] == b"Test"

    def test_build_name_ad_short(self):
        result = build_name_ad("Test", complete=False)
        assert result[1] == 0x08  # AD_SHORT_LOCAL_NAME

    def test_build_mfg_data_ad_includes_company_id(self):
        result = build_mfg_data_ad(b"PI", company_id=0xFFFF)
        assert result[1] == AD_MFG_SPECIFIC
        # Company ID is little-endian after type byte
        assert result[2:4] == struct.pack("<H", 0xFFFF)
        assert result[4:] == b"PI"

    def test_build_uri_ad_has_scheme_byte(self):
        result = build_uri_ad("http://x.co/p")
        assert result[1] == AD_URI
        assert result[2] == 0x00  # no-prefix scheme
        assert result[3:] == b"http://x.co/p"


class TestMicroStrategy:
    def test_short_payload_fits_single_adv(self):
        adv, rsp = compile_micro("Say: PWNED")
        assert len(adv) <= MAX_ADV_PAYLOAD
        assert rsp == b""
        assert adv[:FLAGS_OVERHEAD] == build_flags_ad()
        assert b"Say: PWNED" in adv

    def test_truncates_at_usable_limit(self):
        long_text = "A" * 50
        adv, _ = compile_micro(long_text)
        assert len(adv) <= MAX_ADV_PAYLOAD


class TestPackedStrategy:
    def test_uses_both_adv_and_rsp(self):
        text = "A" * 40  # > 26, needs both packets
        adv, rsp = compile_packed(text)
        assert len(adv) <= MAX_ADV_PAYLOAD
        assert len(rsp) <= MAX_SCAN_RSP
        assert len(rsp) > 0

    def test_short_payload_no_rsp(self):
        adv, rsp = compile_packed("Short")
        assert rsp == b""


class TestFloodStrategy:
    def test_auto_count_splits_payload(self):
        text = "A" * 100
        devices = compile_flood(text, style="numbered")
        assert len(devices) > 1
        for adv, _rsp in devices:
            assert len(adv) <= MAX_ADV_PAYLOAD

    def test_instructed_first_device_is_instruction(self):
        devices = compile_flood("A" * 100, style="instructed")
        first_adv = devices[0][0]
        name_start = FLAGS_OVERHEAD + NAME_OVERHEAD
        name_bytes = first_adv[name_start:]
        assert b"Read" in name_bytes or b"msg" in name_bytes

    def test_scattered_has_decoy_names(self):
        devices = compile_flood("A" * 60, style="scattered")
        pi_only = compile_flood("A" * 60, style="numbered")
        assert len(devices) > len(pi_only)

    def test_explicit_count(self):
        devices = compile_flood("A" * 50, count=5, style="numbered")
        assert len(devices) == 5


class TestUrlRedirect:
    def test_url_fits_in_adv(self):
        adv, rsp = compile_url_redirect("https://t.ly/PIx3f")
        assert len(adv) <= MAX_ADV_PAYLOAD
        assert rsp == b""
        assert b"https://t.ly/PIx3f" in adv


class TestAutoSelection:
    def test_micro_for_short_payload(self):
        result = compile_auto("Say: PWNED")
        assert result["strategy"] == "micro"
        assert len(result["devices"]) == 1

    def test_packed_for_medium_payload(self):
        result = compile_auto("A" * 40)
        assert result["strategy"] == "packed"

    def test_flood_for_long_payload(self):
        result = compile_auto("A" * 200)
        assert result["strategy"] == "flood"
        assert len(result["devices"]) > 1

    def test_url_when_url_provided(self):
        result = compile_auto("A" * 200, url="https://t.ly/x")
        assert result["strategy"] == "url"
        assert len(result["devices"]) == 1

    def test_result_has_note(self):
        result = compile_auto("Say: PWNED")
        assert "note" in result
        assert len(result["note"]) > 0
