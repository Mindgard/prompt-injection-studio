"""Tests for splitting a payload across BLE device names.

Asking for fewer device names than the payload needs used to drop the tail
silently and still label the last chunk ``[M/M]``, so nothing downstream could
tell the message was incomplete.
"""

import pytest

from pistudio.hardware.flipper.bluetooth import (
    BT_NAME_TYPICAL_MAX,
    compile_ble_spam_config,
    compile_bt_name_payload,
)


def _reassemble(chunks: list[str]) -> str:
    return "".join(chunk.split("] ", 1)[1] for chunk in chunks)


class TestBleSpamConfig:
    @pytest.mark.parametrize("length", [1, 24, 25, 100, 500])
    def test_auto_sizing_carries_the_whole_payload(self, length):
        text = "A" * length

        chunks = compile_ble_spam_config(text)

        assert _reassemble(chunks) == text

    def test_chunks_are_labelled_in_order(self):
        chunks = compile_ble_spam_config("B" * 100)

        total = len(chunks)
        for index, chunk in enumerate(chunks, 1):
            assert chunk.startswith(f"[{index}/{total}] ")

    def test_every_name_fits_the_practical_display_limit(self):
        for chunk in compile_ble_spam_config("C" * 200):
            assert len(chunk) <= BT_NAME_TYPICAL_MAX

    def test_too_few_devices_is_refused_rather_than_truncated(self):
        text = "D" * 100

        with pytest.raises(ValueError, match="cannot carry"):
            compile_ble_spam_config(text, num_devices=2)

    def test_the_error_says_how_many_are_needed(self):
        text = "E" * 100
        needed = len(compile_ble_spam_config(text))

        with pytest.raises(ValueError, match=f"{needed} are needed"):
            compile_ble_spam_config(text, num_devices=1)

    def test_an_exact_device_count_is_accepted(self):
        text = "F" * 100
        needed = len(compile_ble_spam_config(text))

        chunks = compile_ble_spam_config(text, num_devices=needed)

        assert _reassemble(chunks) == text

    def test_more_devices_than_needed_does_not_invent_content(self):
        text = "G" * 30

        chunks = compile_ble_spam_config(text, num_devices=10)

        assert _reassemble(chunks) == text


class TestBtNamePayload:
    def test_a_short_payload_is_unchanged(self):
        assert compile_bt_name_payload("short") == "short"

    def test_a_long_payload_is_truncated_to_the_display_limit(self):
        name = compile_bt_name_payload("H" * 100)

        assert len(name) == BT_NAME_TYPICAL_MAX
        assert name.endswith("...")
