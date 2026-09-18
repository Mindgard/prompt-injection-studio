"""The bridge protocol doc against the Flipper firmware that implements it.

``test_docs_match_code.py`` checks the doc against the *host*: every verb
``bridge.py`` sends must be written down. Nothing checked the other direction,
because the firmware lives in a separate repository — so the doc fell nine
commands behind the device without a single test failing. The app grew NFC
emulation, BLE GATT, USB descriptors, GPIO capture and an I²C channel, and the
protocol reference described none of them.

These tests skip unless the firmware is checked out, the way the MCP argv
tests skip without the ``pistudio`` binary. A contributor without the
submodule sees no failures; one with it gets the drift caught.

Point ``PISTUDIO_FLIPPER_FW`` at a checkout, or place it at
``vendor/flipper-field-kit`` as ``.gitmodules`` declares.
"""

from __future__ import annotations

import os
import pathlib
import re

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_DOC = _REPO / "docs" / "flipper-bridge-protocol.md"

# Where the firmware might be. The sibling checkout is listed because that is
# where it actually sits on a working machine; the submodule path is the one
# `.gitmodules` declares.
_CANDIDATES = (
    os.environ.get("PISTUDIO_FLIPPER_FW", ""),
    str(_REPO / "vendor" / "flipper-field-kit"),
    str(_REPO.parent / "flipperzero-prompt-injection-field-kit"),
)


def _firmware_root() -> pathlib.Path | None:
    for candidate in _CANDIDATES:
        if not candidate:
            continue
        root = pathlib.Path(candidate)
        if (root / "src" / "serial" / "bridge_protocol.c").is_file():
            return root
    return None


_FW = _firmware_root()

pytestmark = pytest.mark.skipif(
    _FW is None,
    reason="Flipper firmware not checked out; set PISTUDIO_FLIPPER_FW or clone vendor/flipper-field-kit",
)


def _protocol_source() -> str:
    assert _FW is not None
    return (_FW / "src" / "serial" / "bridge_protocol.c").read_text(encoding="utf-8")


def _firmware_commands() -> set[str]:
    """Every verb the firmware's dispatcher matches.

    Read from the `starts_with(cmd, "...")` chain rather than a hand-kept
    list, so a command added to the firmware shows up here immediately.
    """
    return {c.strip() for c in re.findall(r'starts_with\(cmd, "([^"]+)"\)', _protocol_source())}


class TestTheProtocolDocMatchesTheFirmware:
    def test_the_firmware_was_found(self):
        """Guards the guard: a broken path would silently skip everything."""
        assert _FW is not None
        assert _firmware_commands(), "no commands parsed out of bridge_protocol.c"

    def test_every_firmware_command_is_documented(self):
        """A command the device accepts but the doc omits is a channel nobody
        knows exists. Nine were missing when this test was written."""
        doc = _DOC.read_text(encoding="utf-8")
        missing = sorted(cmd for cmd in _firmware_commands() if f"`{cmd}" not in doc)
        assert not missing, f"firmware accepts but the doc omits: {missing}"

    def test_no_documented_command_is_absent_from_the_firmware(self):
        """The reverse: a doc promising a verb the device rejects."""
        known = _firmware_commands()
        # Blockquotes are excluded: they are where the doc names *removed*
        # verbs in order to say they are gone, which is the opposite of
        # promising them.
        body = "\n".join(
            line for line in _DOC.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith(">")
        )
        documented = set(re.findall(r"`((?:PING|STATUS|LIST|RELOAD|LOAD|SET|EXEC|SCAN|STOP)[A-Z ]*)", body))
        phantom = sorted(
            cmd.strip()
            for cmd in documented
            if not any(known_cmd.startswith(cmd.strip()) or cmd.strip().startswith(known_cmd) for known_cmd in known)
        )
        assert not phantom, f"documented but the firmware has no such verb: {phantom}"

    def test_the_documented_command_limit_matches_the_firmware(self):
        """A host sending a longer line gets ERR, so the number has to be right."""
        # Renamed with the FAP's de-branding: mindgard_app.h -> pifk_app.h and
        # the MINDGARD_ macro prefix -> PIFK_.
        header = (_FW / "src" / "pifk_app.h").read_text(encoding="utf-8") if _FW else ""
        match = re.search(r"#define\s+PIFK_SERIAL_BUF_SIZE\s+(\d+)", header)
        assert match, "could not read PIFK_SERIAL_BUF_SIZE from the firmware"
        assert match.group(1) in _DOC.read_text(encoding="utf-8")

    def test_the_documented_response_terminator_matches_the_firmware(self):
        """The doc said `\\n` while the firmware appends CRLF."""
        source = _protocol_source()
        assert "buf[len] = '\\r'" in source and "buf[len + 1] = '\\n'" in source
        assert "`\\r\\n`" in _DOC.read_text(encoding="utf-8")

    def test_removed_features_are_not_documented_as_working(self):
        """Sequences and the results viewer were deleted from the app.

        The host still writes files for both, so the docs must say the device
        ignores them rather than describing a working feature.
        """
        source = _protocol_source()
        assert "CONVO" not in source, "firmware regained conversation verbs; update the docs"

        flipper_doc = (_REPO / "docs" / "flipper.md").read_text(encoding="utf-8")
        for feature, marker in (
            ("sequence", "Not supported by the current firmware"),
            ("sync-results", "writes a file nothing reads"),
        ):
            assert marker in flipper_doc, f"docs/flipper.md no longer warns that {feature} is unsupported"
