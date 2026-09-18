"""Tests for Flipper Zero sync and bridge modules (Phases 1c + 2b)."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ── Sync module tests ────────────────────────────────────────────


class TestSyncPayloads:
    """Tests for pistudio.hardware.flipper.sync.sync_payloads."""

    def test_sync_payloads_writes_json(self, tmp_path):
        """Syncing payloads writes a valid JSON file."""
        from pistudio.hardware.flipper.sync import sync_payloads

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)
        flipper_path = str(tmp_path / "flipper_sd")
        os.makedirs(flipper_path, exist_ok=True)

        dest, count = sync_payloads(session_dir, path=flipper_path)
        assert count > 0  # built-in payloads exist
        assert dest.endswith("payloads.json")
        assert os.path.isfile(dest)

        with open(dest) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == count
        # Each entry has the expected keys
        for entry in data:
            assert "name" in entry
            assert "text" in entry
            assert "category" in entry
            assert "description" in entry

    def test_sync_payloads_creates_app_data_dir(self, tmp_path):
        """Sync creates the apps_data/mindgard directory if missing."""
        from pistudio.hardware.flipper.sync import sync_payloads

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)
        flipper_path = str(tmp_path / "flipper_sd")
        os.makedirs(flipper_path, exist_ok=True)

        dest, _ = sync_payloads(session_dir, path=flipper_path)
        assert os.path.isdir(os.path.join(flipper_path, "apps_data", "mindgard"))

    def test_sync_payloads_no_path_no_volume_raises(self, tmp_path):
        """Sync raises FileNotFoundError if no path and no volume detected."""
        from pistudio.hardware.flipper.sync import sync_payloads

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)

        with (
            patch(
                "pistudio.hardware.flipper.device.find_flipper_volumes",
                return_value=[],
            ),
            pytest.raises(FileNotFoundError, match="No Flipper Zero"),
        ):
            sync_payloads(session_dir, path=None)


class TestSyncAll:
    """Tests for pistudio.hardware.flipper.sync.sync_all."""

    def test_sync_all_returns_the_payload_result(self, tmp_path):
        """sync_all keeps a dict so a second library can be added back cheaply."""
        from pistudio.hardware.flipper.sync import sync_all

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)
        flipper_path = str(tmp_path / "flipper_sd")
        os.makedirs(flipper_path, exist_ok=True)

        results = sync_all(session_dir, path=flipper_path)
        assert set(results) == {"payloads"}

        p_path, p_count = results["payloads"]
        assert p_count > 0
        assert os.path.isfile(p_path)

    def test_no_conversations_file_is_written(self, tmp_path):
        """The FAP no longer reads conversations.json, so nothing should emit it."""
        from pistudio.hardware.flipper.sync import sync_all

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)
        flipper_path = str(tmp_path / "flipper_sd")
        os.makedirs(flipper_path, exist_ok=True)

        sync_all(session_dir, path=flipper_path)
        written = [f for _, _, files in os.walk(flipper_path) for f in files]
        assert "conversations.json" not in written


class TestSyncResults:
    """Tests for pistudio.hardware.flipper.sync.sync_results."""

    def test_sync_results_writes_json(self, tmp_path):
        """sync_results writes results.json to the SD card."""
        from pistudio.hardware.flipper.sync import sync_results

        flipper_path = str(tmp_path / "flipper_sd")
        os.makedirs(flipper_path, exist_ok=True)

        results_data = {
            "test_id": "abc123",
            "summary": {"high": 3, "medium": 7, "low": 12},
        }
        dest = sync_results(results_data, path=flipper_path)
        assert dest.endswith("results.json")
        assert os.path.isfile(dest)

        with open(dest) as f:
            written = json.load(f)
        assert written["test_id"] == "abc123"
        assert written["summary"]["high"] == 3


# ── Bridge module tests ──────────────────────────────────────────


class TestFlipperBridge:
    """Tests for pistudio.hardware.flipper.bridge.FlipperBridge."""

    def _make_bridge(self):
        """Create a FlipperBridge with a mock serial connection."""
        from pistudio.hardware.flipper.bridge import FlipperBridge

        bridge = FlipperBridge("/dev/tty.fake", 115200)
        bridge._serial = MagicMock()
        bridge._serial.is_open = True
        # Wire read_until to delegate to readline so _recv_line works
        bridge._serial.read_until = bridge._serial.readline
        return bridge

    def test_ping_success(self):
        """ping() returns True when Flipper responds OK PONG."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK PONG\r\n"
        assert bridge.ping() is True

    def test_ping_failure(self):
        """ping() returns False when no response."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b""
        assert bridge.ping() is False

    def test_status_parsing(self):
        """status() parses the OK STATUS response correctly."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK STATUS connected payloads=25\r\n"
        s = bridge.status()
        assert s["state"] == "connected"
        assert s["payloads"] == 25

    def test_execute_badusb_success(self):
        """execute_badusb() returns success on OK DONE."""
        bridge = self._make_bridge()
        bridge._serial.readline.side_effect = [
            b"OK EXECUTING test-payload\r\n",
            b"OK DONE test-payload\r\n",
        ]
        ok, msg = bridge.execute_badusb("test-payload")
        assert ok is True
        assert "DONE" in msg

    def test_execute_badusb_not_found(self):
        """execute_badusb() returns failure on ERR."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"ERR payload not found: nonexistent\r\n"
        ok, msg = bridge.execute_badusb("nonexistent")
        assert ok is False
        assert "not found" in msg

    def test_stop(self):
        """stop() returns True on OK."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK\r\n"
        assert bridge.stop() is True

    def test_load_payload(self):
        """load_payload() sends correctly escaped JSON."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK loaded test\r\n"
        ok, msg = bridge.load_payload("test", 'Hello "world"\nnewline')
        assert ok is True

        # Verify the sent command had escaped JSON
        sent = bridge._serial.write.call_args[0][0].decode()
        assert "LOAD" in sent
        assert '\\"' in sent  # escaped quotes
        assert "\\n" in sent  # escaped newline

    def test_set_delay(self):
        """set_delay() sends SET DELAY command."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK delay=2000\r\n"
        assert bridge.set_delay(2000) is True
        sent = bridge._serial.write.call_args[0][0].decode()
        assert "SET DELAY 2000" in sent

    def test_list_payloads_parse(self):
        """list_payloads() parses single-line DATA response."""
        bridge = self._make_bridge()
        bridge._serial.readline.side_effect = [
            b'DATA [{"name":"p1","category":"cat","builtin":true},{"name":"p2","category":"cat2","builtin":false}]\r\n',
        ]
        payloads = bridge.list_payloads()
        assert len(payloads) == 2
        assert payloads[0]["name"] == "p1"
        assert payloads[1]["name"] == "p2"

    def test_context_manager(self):
        """FlipperBridge can be used as a context manager."""
        from pistudio.hardware.flipper.bridge import FlipperBridge

        with patch("pistudio.hardware.flipper.bridge.FlipperBridge.connect"):
            with patch("pistudio.hardware.flipper.bridge.FlipperBridge.disconnect"):
                with FlipperBridge("/dev/fake") as bridge:
                    assert bridge is not None

    def test_not_connected_raises(self):
        """Sending when not connected raises ConnectionError."""
        from pistudio.hardware.flipper.bridge import FlipperBridge

        bridge = FlipperBridge("/dev/fake")
        with pytest.raises(ConnectionError, match="Not connected"):
            bridge._send("PING")


# ── HW command integration tests ─────────────────────────────────


class TestSequenceModule:
    """Tests for pistudio.hardware.flipper.sequence."""

    def test_create_sequence(self, tmp_path):
        """create_sequence creates an empty sequence JSON file."""
        from pistudio.hardware.flipper.sequence import create_sequence, get_sequence

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)

        seq = create_sequence("test-sweep", session_dir, description="Test sequence")
        assert seq.name == "test-sweep"
        assert seq.description == "Test sequence"
        assert seq.steps == []

        result = get_sequence("test-sweep", session_dir)
        assert result is not None
        assert result[0].name == "test-sweep"
        assert result[1] == "session"

    def test_add_step(self, tmp_path):
        """add_step appends a step to an existing sequence."""
        from pistudio.hardware.flipper.sequence import add_step, create_sequence

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)

        create_sequence("sweep", session_dir)
        seq = add_step("sweep", "badusb", "ignore-instructions", session_dir, delay_after_ms=5000)
        assert len(seq.steps) == 1
        assert seq.steps[0].protocol == "badusb"
        assert seq.steps[0].payload == "ignore-instructions"
        assert seq.steps[0].delay_after_ms == 5000

    def test_add_step_invalid_protocol(self, tmp_path):
        """add_step rejects invalid protocols."""
        from pistudio.hardware.flipper.sequence import add_step, create_sequence

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)

        create_sequence("bad", session_dir)
        with pytest.raises(ValueError, match="Invalid protocol"):
            add_step("bad", "infrared", "test", session_dir)

    def test_add_step_max_steps(self, tmp_path):
        """add_step rejects more than 8 steps."""
        from pistudio.hardware.flipper.sequence import add_step, create_sequence

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)

        create_sequence("full", session_dir)
        for i in range(8):
            add_step("full", "badusb", f"payload-{i}", session_dir)

        with pytest.raises(ValueError, match="Maximum 8"):
            add_step("full", "badusb", "one-too-many", session_dir)

    def test_list_sequences(self, tmp_path):
        """list_sequences returns all created sequences."""
        from pistudio.hardware.flipper.sequence import create_sequence, list_sequences

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)

        create_sequence("alpha", session_dir)
        create_sequence("beta", session_dir)

        seqs = list_sequences(session_dir)
        names = [s.name for s, _ in seqs]
        assert "alpha" in names
        assert "beta" in names

    def test_remove_sequence(self, tmp_path):
        """remove_sequence deletes the sequence file."""
        from pistudio.hardware.flipper.sequence import (
            create_sequence,
            get_sequence,
            remove_sequence,
        )

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)

        create_sequence("ephemeral", session_dir)
        assert get_sequence("ephemeral", session_dir) is not None

        remove_sequence("ephemeral", session_dir)
        assert get_sequence("ephemeral", session_dir) is None

    def test_deploy_sequence(self, tmp_path):
        """deploy_sequence writes JSON to the Flipper SD card path."""
        from pistudio.hardware.flipper.sequence import (
            add_step,
            create_sequence,
            deploy_sequence,
        )

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)
        flipper_path = str(tmp_path / "flipper_sd")
        os.makedirs(flipper_path, exist_ok=True)

        create_sequence("office-sweep", session_dir, description="Multi-vector")
        add_step("office-sweep", "badusb", "system-prompt-leak", session_dir, delay_after_ms=5000)
        add_step("office-sweep", "nfc", "ignore-instructions", session_dir)

        deployed = deploy_sequence("office-sweep", session_dir, path=flipper_path)
        assert os.path.isfile(deployed)
        assert "sequences" in deployed

        with open(deployed) as f:
            data = json.load(f)
        assert data["name"] == "office-sweep"
        assert len(data["steps"]) == 2
        assert data["steps"][0]["protocol"] == "badusb"
        assert data["steps"][0]["delay_after_ms"] == 5000

    def test_sequence_names(self, tmp_path):
        """sequence_names returns sorted list."""
        from pistudio.hardware.flipper.sequence import create_sequence, sequence_names

        session_dir = str(tmp_path / "session")
        os.makedirs(session_dir, exist_ok=True)

        create_sequence("zulu", session_dir)
        create_sequence("alpha", session_dir)
        names = sequence_names(session_dir)
        assert names == ["alpha", "zulu"]


class TestFlipperBridgeNfcBle:
    """Tests for NFC and BLE bridge commands."""

    def _make_bridge(self):
        from pistudio.hardware.flipper.bridge import FlipperBridge

        bridge = FlipperBridge("/dev/tty.fake", 115200)
        bridge._serial = MagicMock()
        bridge._serial.is_open = True
        bridge._serial.read_until = bridge._serial.readline
        return bridge

    def test_execute_nfc_success(self):
        """execute_nfc() returns success on OK WRITTEN."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK WRITTEN /ext/nfc/mindgard_test.nfc\r\n"
        ok, msg = bridge.execute_nfc("test-payload")
        assert ok is True
        assert "WRITTEN" in msg
        assert "/ext/nfc/" in msg

    def test_execute_nfc_not_found(self):
        """execute_nfc() returns failure on ERR."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"ERR payload not found: missing\r\n"
        ok, msg = bridge.execute_nfc("missing")
        assert ok is False
        assert "not found" in msg

    def test_execute_nfc_write_failure(self):
        """execute_nfc() returns failure on write error."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"ERR failed to write NFC file\r\n"
        ok, msg = bridge.execute_nfc("bad-payload")
        assert ok is False

    def test_execute_nfc_no_response(self):
        """execute_nfc() handles timeout."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b""
        ok, msg = bridge.execute_nfc("timeout")
        assert ok is False
        assert "No response" in msg

    def test_execute_ble_success(self):
        """execute_ble() returns success on OK BROADCASTING."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK BROADCASTING\r\n"
        ok, msg = bridge.execute_ble("test-payload")
        assert ok is True
        assert "BROADCASTING" in msg

    def test_execute_ble_not_found(self):
        """execute_ble() returns failure when payload not found."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"ERR payload not found: missing\r\n"
        ok, msg = bridge.execute_ble("missing")
        assert ok is False

    def test_execute_ble_beacon_failure(self):
        """execute_ble() handles beacon start failure."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"ERR failed to start BLE beacon\r\n"
        ok, msg = bridge.execute_ble("bad")
        assert ok is False

    def test_execute_ble_no_response(self):
        """execute_ble() handles timeout."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b""
        ok, msg = bridge.execute_ble("timeout")
        assert ok is False

    def test_stop_ble_success(self):
        """stop_ble() returns True on OK."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK\r\n"
        assert bridge.stop_ble() is True
        sent = bridge._serial.write.call_args[0][0].decode()
        assert "STOP BLE" in sent

    def test_stop_ble_failure(self):
        """stop_ble() returns False when no response."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b""
        assert bridge.stop_ble() is False

    def test_execute_nfc_sends_correct_command(self):
        """execute_nfc() sends EXEC NFC <name>."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK WRITTEN /ext/nfc/mindgard_test.nfc\r\n"
        bridge.execute_nfc("my-payload")
        sent = bridge._serial.write.call_args[0][0].decode()
        assert "EXEC NFC my-payload" in sent

    def test_execute_ble_sends_correct_command(self):
        """execute_ble() sends EXEC BLE <name>."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK BROADCASTING\r\n"
        bridge.execute_ble("my-payload")
        sent = bridge._serial.write.call_args[0][0].decode()
        assert "EXEC BLE my-payload" in sent

    def test_execute_qr_success(self):
        """execute_qr() returns success when Flipper displays QR."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK DISPLAYING QR\r\n"
        ok, msg = bridge.execute_qr("my-payload")
        assert ok is True
        assert "DISPLAYING QR" in msg

    def test_execute_qr_sends_correct_command(self):
        """execute_qr() sends EXEC QR <name>."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK DISPLAYING QR\r\n"
        bridge.execute_qr("my-payload")
        sent = bridge._serial.write.call_args[0][0].decode()
        assert "EXEC QR my-payload" in sent

    def test_execute_qr_too_long(self):
        """execute_qr() returns error when text exceeds QR capacity."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"ERR text too long for QR (max 106 bytes)\r\n"
        ok, msg = bridge.execute_qr("long-payload")
        assert ok is False
        assert "too long" in msg

    def test_reload_success(self):
        """reload() returns success with updated counts."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK RELOADED payloads=20 convos=8 sequences=3\r\n"
        ok, msg = bridge.reload()
        assert ok is True
        assert "RELOADED" in msg
        assert "payloads=20" in msg
        assert "sequences=3" in msg

    def test_reload_sends_correct_command(self):
        """reload() sends RELOAD command."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b"OK RELOADED payloads=10 convos=5 sequences=2\r\n"
        bridge.reload()
        sent = bridge._serial.write.call_args[0][0].decode()
        assert "RELOAD" in sent

    def test_reload_no_response(self):
        """reload() handles timeout."""
        bridge = self._make_bridge()
        bridge._serial.readline.return_value = b""
        ok, msg = bridge.reload()
        assert ok is False
        assert "No response" in msg


class TestHwFlipperSyncCommand:
    """Tests for hw flipper sync command dispatch."""

    def test_sync_subcommand_recognized(self):
        """hw flipper sync is a valid subcommand."""
        from pistudio.commands.hw import HwCommand

        cmd = HwCommand()
        ctx = MagicMock()
        ctx.session_dir = tempfile.mkdtemp()
        ctx.json_mode = False

        with patch("pistudio.commands.hw.flipper._flipper_sync") as mock_sync:
            from pistudio.commands.hw.flipper import handle_flipper

            handle_flipper(cmd, ctx, ["sync"])
            mock_sync.assert_called_once()

    def test_sync_results_subcommand_recognized(self):
        """hw flipper sync-results is a valid subcommand."""
        from pistudio.commands.hw import HwCommand

        cmd = HwCommand()
        ctx = MagicMock()

        with patch("pistudio.commands.hw.flipper._flipper_sync_results") as mock_sync:
            from pistudio.commands.hw.flipper import handle_flipper

            handle_flipper(cmd, ctx, ["sync-results"])
            mock_sync.assert_called_once()

    def test_remote_subcommand_recognized(self):
        """hw flipper remote is a valid subcommand."""
        from pistudio.commands.hw import HwCommand

        cmd = HwCommand()
        ctx = MagicMock()

        with patch("pistudio.commands.hw.flipper._handle_remote") as mock_remote:
            from pistudio.commands.hw.flipper import handle_flipper

            handle_flipper(cmd, ctx, ["remote"])
            mock_remote.assert_called_once()

    def test_sequence_subcommand_recognized(self):
        """hw flipper sequence is a valid subcommand."""
        from pistudio.commands.hw import HwCommand

        cmd = HwCommand()
        ctx = MagicMock()

        with patch("pistudio.commands.hw.flipper._handle_sequence") as mock_seq:
            from pistudio.commands.hw.flipper import handle_flipper

            handle_flipper(cmd, ctx, ["sequence"])
            mock_seq.assert_called_once()


class TestHwFlipperCompletion:
    """Tests for tab completion of new subcommands."""

    def test_flipper_completion_includes_sync(self):
        """Tab completion for 'hw flipper' includes sync, sync-results, remote."""
        from pistudio.commands.hw import HwCommand

        cmd = HwCommand()
        ctx = MagicMock()
        ctx.session_dir = tempfile.mkdtemp()

        completions = cmd.complete(ctx, ["flipper", ""])
        assert "sync" in completions
        assert "sync-results" in completions
        assert "remote" in completions

    def test_flipper_completion_prefix_match(self):
        """Tab completion prefix-matches for 'syn' -> sync, sync-results."""
        from pistudio.commands.hw import HwCommand

        cmd = HwCommand()
        ctx = MagicMock()
        ctx.session_dir = tempfile.mkdtemp()

        completions = cmd.complete(ctx, ["flipper", "syn"])
        assert "sync" in completions
        assert "sync-results" in completions
        assert "badusb" not in completions
