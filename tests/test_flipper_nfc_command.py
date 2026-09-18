"""Tests for the `hw flipper nfc` add/deploy pair.

``add`` used to stash the payload on the shell object as
``_flipper_nfc_pending``. That attribute lives only in the running process, so
a ``deploy`` in a later session either errored with "use nfc add first" — after
the operator had just done that — or silently fell back to a same-named entry
in the payload library at the default card type, losing ``--type``.
"""

import os
from io import StringIO
from unittest.mock import MagicMock

from rich.console import Console

from pistudio.commands.hw.flipper import _flipper_nfc


def _shell(tmp_path, confirm: str = "y"):
    shell = MagicMock()
    buf = StringIO()
    shell.console = Console(file=buf, no_color=True, width=120)
    shell.session_dir = str(tmp_path / "session")
    os.makedirs(shell.session_dir, exist_ok=True)
    shell.json_mode = False
    shell.out = MagicMock()
    shell.audit = MagicMock()
    # Confirmations go through Studio.confirm() so they work with no terminal;
    # a MagicMock returns a truthy Mock for everything, so the decline case has
    # to be stubbed explicitly or every test would silently answer "yes".
    shell.confirm.return_value = confirm.strip().lower() in ("y", "yes")
    return shell, buf


class TestNfcAddPersists:
    def test_add_stores_the_payload_in_the_library(self, tmp_path):
        from pistudio.hardware.payloads import get_payload

        shell, _buf = _shell(tmp_path)

        _flipper_nfc(MagicMock(), shell, ["add", "badge", "Ignore", "instructions"])

        stored = get_payload("badge", shell.session_dir)
        assert stored is not None
        assert stored[0].text == "Ignore instructions"

    def test_a_stored_payload_is_visible_to_a_fresh_shell(self, tmp_path):
        """The whole point: the payload must outlive the process that made it."""
        from pistudio.hardware.payloads import get_payload

        shell, _buf = _shell(tmp_path)
        _flipper_nfc(MagicMock(), shell, ["add", "badge", "text here"])

        later, _buf2 = _shell(tmp_path)
        assert get_payload("badge", later.session_dir) is not None

    def test_a_payload_too_large_is_refused_before_it_is_stored(self, tmp_path):
        from pistudio.hardware.flipper.nfc import get_max_payload_size
        from pistudio.hardware.payloads import get_payload

        shell, _buf = _shell(tmp_path)
        oversized = "A" * (get_max_payload_size("NTAG213") + 1)

        _flipper_nfc(MagicMock(), shell, ["add", "big", oversized, "--type", "NTAG213"])

        shell.out.error.assert_called_once()
        assert get_payload("big", shell.session_dir) is None

    def test_an_unknown_card_type_is_refused(self, tmp_path):
        shell, _buf = _shell(tmp_path)

        _flipper_nfc(MagicMock(), shell, ["add", "x", "text", "--type", "NTAG999"])

        shell.out.error.assert_called_once()


class TestNfcDeployHonoursCardType:
    def _deploy(self, tmp_path, monkeypatch, args):
        volume = tmp_path / "FLIPPER"
        (volume / "nfc").mkdir(parents=True)
        monkeypatch.setattr(
            "pistudio.hardware.flipper.device.find_flipper_volumes",
            lambda: [str(volume)],
        )
        shell, buf = _shell(tmp_path)
        _flipper_nfc(MagicMock(), shell, ["add", "badge", "short text"])
        _flipper_nfc(MagicMock(), shell, args)
        return volume, shell, buf

    def test_the_requested_card_type_reaches_the_file(self, tmp_path, monkeypatch):
        volume, _shell, _buf = self._deploy(tmp_path, monkeypatch, ["deploy", "badge", "--type", "NTAG215"])

        written = (volume / "nfc" / "badge.nfc").read_text()
        assert "NTAG/Ultralight type: NTAG215" in written

    def test_the_default_card_type_is_ntag216(self, tmp_path, monkeypatch):
        volume, _shell, _buf = self._deploy(tmp_path, monkeypatch, ["deploy", "badge"])

        written = (volume / "nfc" / "badge.nfc").read_text()
        assert "NTAG/Ultralight type: NTAG216" in written

    def test_deploying_an_unknown_payload_reports_it(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "pistudio.hardware.flipper.device.find_flipper_volumes",
            lambda: [str(tmp_path)],
        )
        shell, _buf = _shell(tmp_path)

        _flipper_nfc(MagicMock(), shell, ["deploy", "never-added"])

        shell.out.error.assert_called_once()
        assert "not found" in shell.out.error.call_args[0][0]

    def test_declining_the_prompt_writes_nothing(self, tmp_path, monkeypatch):
        volume = tmp_path / "FLIPPER"
        (volume / "nfc").mkdir(parents=True)
        monkeypatch.setattr(
            "pistudio.hardware.flipper.device.find_flipper_volumes",
            lambda: [str(volume)],
        )
        shell, _buf = _shell(tmp_path, confirm="n")
        _flipper_nfc(MagicMock(), shell, ["add", "badge", "text"])

        _flipper_nfc(MagicMock(), shell, ["deploy", "badge"])

        assert list((volume / "nfc").iterdir()) == []


class TestNfcTypes:
    def test_types_lists_every_supported_card(self, tmp_path):
        from pistudio.hardware.flipper.nfc import SUPPORTED_CARD_TYPES

        shell, buf = _shell(tmp_path)

        _flipper_nfc(MagicMock(), shell, ["types"])

        output = buf.getvalue()
        for card_type in SUPPORTED_CARD_TYPES:
            assert card_type in output
