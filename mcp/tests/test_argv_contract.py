"""Every tool's argv must be a command the studio actually accepts.

``test_tools.py`` mocks ``run_cli``, so it proves a tool is reachable and
returns an envelope — but it cannot prove the argv it builds means anything.
That gap was not theoretical: ``embed_payload`` emitted
``file embed <fmt> <text> --out <path>`` for as long as the tool existed. The
studio has no ``embed`` subcommand and spells the flag ``--output``, so every
call failed with ``Unknown format: 'embed'`` — and the mocked test asserted
``["file", "embed"]``, pinning the bug in place.

These tests run the real ``pistudio`` and assert the studio understood the
argv. They are the only thing here that can catch a rename on the CLI side,
which is the whole risk of a subprocess-coupled server living in a separate
package with its own test run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

# Errors the studio emits when it does not recognise what it was handed. A tool
# whose argv drifted produces one of these rather than doing its job.
_DRIFT_MARKERS = (
    "unknown format",
    "unknown subcommand",
    "unknown command",
    "unknown flag",
    "unknown theme",
    "missing subcommand",
)


def _studio_bin() -> str | None:
    return os.environ.get("PISTUDIO_BIN") or shutil.which("pistudio")


pytestmark = pytest.mark.skipif(
    _studio_bin() is None,
    reason="needs the pistudio binary on PATH to check argv against the real CLI",
)


def _run(argv: list[str], session_dir: str) -> subprocess.CompletedProcess[str]:
    """Run the studio the way the server does, and capture both streams."""
    # S603: the argv is written by these tests and the binary is resolved from
    # PISTUDIO_BIN/PATH, exactly as the server resolves it. No shell is used.
    return subprocess.run(  # noqa: S603
        [_studio_bin() or "pistudio", "--json", "--session-dir", session_dir, *argv],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _assert_understood(argv: list[str], session_dir: str) -> subprocess.CompletedProcess[str]:
    """Fail when the studio did not recognise *argv*.

    Deliberately not an exit-code assertion: a tool can legitimately fail for
    environmental reasons (no device attached, no LLM configured). What must
    never happen is the studio reporting that it does not know the command.
    """
    proc = _run(argv, session_dir)
    output = (proc.stdout + proc.stderr).strip()
    haystack = output.lower()
    for marker in _DRIFT_MARKERS:
        assert marker not in haystack, f"studio did not understand {argv!r}: {output[:300]}"
    return proc


class TestToolArgvIsRealCli:
    """One case per tool, using the argv the server builds."""

    def test_list_payloads(self, tmp_path):
        proc = _assert_understood(["payloads", "list"], str(tmp_path))
        assert json.loads(proc.stdout), "payloads list returned no JSON"

    def test_show_payload(self, tmp_path):
        _assert_understood(["payloads", "show", "ignore-instructions"], str(tmp_path))

    def test_add_payload(self, tmp_path):
        _assert_understood(["payloads", "add", "argv-contract", "some text"], str(tmp_path))

    def test_list_formats(self, tmp_path):
        proc = _assert_understood(["file", "list"], str(tmp_path))
        assert json.loads(proc.stdout), "file list returned no JSON"

    def test_embed_payload(self, tmp_path):
        """The regression that motivated this file."""
        out = tmp_path / "out.txt"
        proc = _assert_understood(["file", "txt", "hello", "--output", str(out)], str(tmp_path))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert out.is_file(), "embed_payload's argv did not produce a file"

    def test_serve_status(self, tmp_path):
        _assert_understood(["serve", "status"], str(tmp_path))

    def test_serve_stop(self, tmp_path):
        _assert_understood(["serve", "stop"], str(tmp_path))

    def test_scan_devices(self, tmp_path):
        _assert_understood(["hw", "devices"], str(tmp_path))

    def test_list_barcode_types(self, tmp_path):
        proc = _assert_understood(["barcode", "list"], str(tmp_path))
        assert json.loads(proc.stdout), "barcode list returned no JSON"

    def test_encode_barcode(self, tmp_path):
        out = tmp_path / "code.png"
        proc = _assert_understood(["barcode", "png", "hi", "--type", "qr", "--output", str(out)], str(tmp_path))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert out.is_file(), "encode_barcode's argv did not produce a file"

    def test_list_audio_formats(self, tmp_path):
        proc = _assert_understood(["audio", "list"], str(tmp_path))
        assert json.loads(proc.stdout), "audio list returned no JSON"

    def test_synthesize_audio(self, tmp_path):
        out = tmp_path / "p.wav"
        proc = _assert_understood(["audio", "wav", "hi", "--output", str(out)], str(tmp_path))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert out.is_file(), "synthesize_audio's argv did not produce a file"

    def test_list_encoders(self, tmp_path):
        proc = _assert_understood(["encode", "list"], str(tmp_path))
        assert json.loads(proc.stdout), "encode list returned no JSON"

    def test_list_carriers(self, tmp_path):
        proc = _assert_understood(["encode", "carriers"], str(tmp_path))
        assert json.loads(proc.stdout), "encode carriers returned no JSON"

    def test_preview_encoding(self, tmp_path):
        _assert_understood(["encode", "preview", "hello", "--chain", "base64", "--carrier", "wifi"], str(tmp_path))

    def test_encode_text(self, tmp_path):
        proc = _assert_understood(["encode", "hello", "--chain", "base64"], str(tmp_path))
        assert "aGVsbG8=" in proc.stdout, proc.stdout

    def test_list_serial_ports(self, tmp_path):
        proc = _assert_understood(["hw", "uart", "devices"], str(tmp_path))
        # An empty list is the right answer with no cable attached; what
        # matters is that the studio understood the argv.
        json.loads(proc.stdout or "[]")

    def test_uart_send_argv_is_understood(self, tmp_path):
        """Checks the argv parses, not that anything is on the other end.

        With no adapter attached this fails on port resolution, which is a
        different thing from the studio not recognising the command -- and
        ``_assert_understood`` draws exactly that line.
        """
        _assert_understood(
            ["--yes", "hw", "uart", "send", "hello", "--baud", "9600", "--line-ending", "lf"],
            str(tmp_path),
        )


class TestServerBuildsTheArgvTheseTestsCheck:
    """Tie the cases above to what the server actually emits.

    Without this, the contract tests could drift from the server the same way
    the server drifted from the CLI.
    """

    @staticmethod
    def _argv_for(monkeypatch, call) -> list[str]:
        from pistudio_mcp import budget, server
        from pistudio_mcp.cli import CliResult

        recorded: list[list[str]] = []

        def fake(argv: list[str], **kw: object):
            recorded.append(argv)
            return CliResult(ok=True, exit_code=0, data=[], stdout="ok", stderr="")

        budget.reset()
        monkeypatch.setattr(server, "run_cli", fake)
        try:
            call(server)
        finally:
            budget.reset()
        return recorded[-1]

    def test_embed_payload_argv_shape(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PISTUDIO_MCP_OUTPUT_DIR", str(tmp_path))
        argv = self._argv_for(monkeypatch, lambda s: s.embed_payload("txt", "hello", "out.txt"))
        assert argv[0] == "file"
        assert argv[1] == "txt", "the format must be the first token after 'file'"
        assert "--output" in argv

    def test_serve_start_argv_shape(self, monkeypatch):
        argv = self._argv_for(monkeypatch, lambda s: s.serve_start())
        # `serve` starts by falling through with no subcommand. A stray verb
        # here becomes the hosted payload text.
        assert argv == ["serve"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell quoting assumptions")
class TestJsonContract:
    """The server parses stdout as JSON, so the studio must emit only JSON."""

    def test_long_payload_stays_parseable(self, tmp_path):
        """Rich used to hard-wrap JSON at the console width, breaking parsing."""
        proc = _run(["payloads", "add", "long-one", "X" * 500], str(tmp_path))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        proc = _run(["payloads", "show", "long-one"], str(tmp_path))
        json.loads(proc.stdout)  # raises if the output was reflowed

    def test_errors_do_not_pollute_stdout(self, tmp_path):
        """Diagnostics belong on stderr so stdout holds only data."""
        proc = _run(["payloads", "show", "no-such-payload-here"], str(tmp_path))
        assert proc.stdout.strip() == "", f"error text reached stdout: {proc.stdout[:200]!r}"
