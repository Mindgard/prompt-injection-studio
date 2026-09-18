"""Tests for Flipper SD card filename validation.

Payload names decide where a file is written. They are not always typed by
hand — a name can arrive from a synced corpus or a generated library — so a
name carrying a separator writes outside the card without anyone noticing.
"""

import os

import pytest

from pistudio.hardware.flipper.validate import MAX_NAME_LENGTH, safe_join, validate_payload_name


class TestValidatePayloadName:
    @pytest.mark.parametrize(
        "name",
        ["payload", "ignore-instructions", "badge_attack", "test.v2.txt", "a" * MAX_NAME_LENGTH],
    )
    def test_ordinary_names_are_accepted(self, name):
        assert validate_payload_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "../escape",
            "../../etc/passwd",
            "sub/dir",
            "back\\slash",
            "/absolute",
            "..",
        ],
    )
    def test_traversal_and_separators_are_refused(self, name):
        with pytest.raises(ValueError):
            validate_payload_name(name)

    @pytest.mark.parametrize("name", ["", "   "])
    def test_empty_names_are_refused(self, name):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_payload_name(name)

    def test_overlong_names_are_refused(self):
        with pytest.raises(ValueError, match="too long"):
            validate_payload_name("a" * (MAX_NAME_LENGTH + 1))

    @pytest.mark.parametrize("char", ["<", ">", ":", '"', "|", "?", "*"])
    def test_characters_fat32_forbids_are_refused(self, char):
        with pytest.raises(ValueError, match="cannot store"):
            validate_payload_name(f"payload{char}name")

    @pytest.mark.parametrize("name", ["pay\nload", "pay\rload", "pay\tload", "pay\x00load"])
    def test_control_characters_are_refused(self, name):
        with pytest.raises(ValueError, match="control characters"):
            validate_payload_name(name)

    @pytest.mark.parametrize("name", ["CON", "con.txt", "NUL", "COM1", "lpt9.nfc"])
    def test_reserved_device_names_are_refused(self, name):
        with pytest.raises(ValueError, match="reserved"):
            validate_payload_name(name)

    @pytest.mark.parametrize("name", [" leading", "trailing "])
    def test_surrounding_whitespace_is_refused(self, name):
        with pytest.raises(ValueError, match="whitespace"):
            validate_payload_name(name)

    def test_trailing_dot_is_refused(self):
        with pytest.raises(ValueError, match="end with a dot"):
            validate_payload_name("payload.")


class TestSafeJoin:
    def test_a_valid_name_lands_inside_the_directory(self, tmp_path):
        target = safe_join(str(tmp_path), "payload.txt")

        assert target == os.path.join(os.path.realpath(str(tmp_path)), "payload.txt")

    def test_traversal_cannot_escape_the_directory(self, tmp_path):
        card = tmp_path / "FLIPPER" / "badusb"
        card.mkdir(parents=True)
        (tmp_path / "SENSITIVE").mkdir()

        with pytest.raises(ValueError):
            safe_join(str(card), "../../SENSITIVE/authorized_keys")

    def test_a_symlink_out_of_the_directory_is_refused(self, tmp_path):
        """A name check alone cannot see a symlink; the resolved path can."""
        card = tmp_path / "badusb"
        card.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (card / "escape").symlink_to(outside)

        # "escape/x" is caught by the separator rule; the link target itself
        # must not resolve outside the card either.
        with pytest.raises(ValueError):
            safe_join(str(card), "escape/x")

    def test_written_file_stays_under_the_card(self, tmp_path):
        card = tmp_path / "badusb"
        card.mkdir()

        target = safe_join(str(card), "ok.txt")

        assert os.path.commonpath([os.path.realpath(str(card)), target]) == os.path.realpath(str(card))


class TestDeployRefusesTraversal:
    """The validation has to hold at the deploy entry points, not just alone."""

    def test_badusb_deploy_cannot_write_outside_the_volume(self, tmp_path):
        from pistudio.hardware.flipper.device import deploy_badusb

        volume = tmp_path / "FLIPPER"
        (volume / "badusb").mkdir(parents=True)
        sensitive = tmp_path / "SENSITIVE"
        sensitive.mkdir()

        with pytest.raises(ValueError):
            deploy_badusb("REM x", "../../SENSITIVE/authorized_keys", str(volume))

        assert list(sensitive.iterdir()) == []

    def test_nfc_deploy_cannot_write_outside_the_volume(self, tmp_path):
        from pistudio.hardware.flipper.device import deploy_nfc
        from pistudio.hardware.flipper.nfc import NFCPayload

        volume = tmp_path / "FLIPPER"
        (volume / "nfc").mkdir(parents=True)
        sensitive = tmp_path / "SENSITIVE"
        sensitive.mkdir()

        payload = NFCPayload(name="../../SENSITIVE/badge", payload_text="x")
        with pytest.raises(ValueError):
            deploy_nfc(payload, str(volume))

        assert list(sensitive.iterdir()) == []

    def test_an_ordinary_deploy_still_works(self, tmp_path):
        from pistudio.hardware.flipper.device import deploy_badusb

        volume = tmp_path / "FLIPPER"
        (volume / "badusb").mkdir(parents=True)

        written = deploy_badusb("REM ok", "good-payload", str(volume))

        assert os.path.basename(written) == "good-payload.txt"
        assert os.path.isfile(written)
