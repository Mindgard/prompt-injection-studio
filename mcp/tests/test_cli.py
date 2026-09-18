"""The subprocess boundary: argv construction, output parsing, env scrubbing.

These pin the rules that make the boundary safe. Nothing here needs a real
studio — the subprocess is mocked — except the contract test at the end, which
is skipped when no binary is available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from unittest.mock import patch

import pytest

from pistudio_mcp import cli
from pistudio_mcp.errors import PiStudioMCPError


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


REAL_BINARY = os.environ.get("PISTUDIO_BIN") or shutil.which("pistudio")


@pytest.fixture
def fake_binary(monkeypatch, tmp_path):
    """Point the driver at a file that exists, so studio_bin() resolves.

    Not autouse: it would override PISTUDIO_BIN for the contract tests below,
    which then ran against this stub and passed on a false assumption.
    """
    fake = tmp_path / "pistudio"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o700)
    monkeypatch.setenv("PISTUDIO_BIN", str(fake))
    monkeypatch.setenv("PISTUDIO_MCP_SHARE_SESSION", "0")
    return fake


class TestArgvConstruction:
    def test_arguments_are_passed_as_discrete_argv_elements(self, fake_binary):
        """The core safety property: no shell, and no joining into a string."""
        with patch("subprocess.run", return_value=_completed("{}")) as run:
            cli.run_cli(["payloads", "show", "my-payload"])

        args = run.call_args[0][0]
        assert args[-3:] == ["payloads", "show", "my-payload"]
        assert run.call_args.kwargs.get("shell") is not True

    def test_metacharacters_survive_verbatim(self, fake_binary):
        """A payload containing shell syntax is data, not a command."""
        payload = "; rm -rf / $(id) `whoami` | tee"
        with patch("subprocess.run", return_value=_completed("{}")) as run:
            cli.run_cli(["payloads", "add", "x", payload])

        assert run.call_args[0][0][-1] == payload

    def test_json_flag_is_added_before_the_subcommand(self, fake_binary):
        with patch("subprocess.run", return_value=_completed("{}")) as run:
            cli.run_cli(["payloads", "list"])

        args = run.call_args[0][0]
        assert "--json" in args
        assert args.index("--json") < args.index("payloads")

    def test_json_can_be_disabled(self, fake_binary):
        with patch("subprocess.run", return_value=_completed("")) as run:
            cli.run_cli(["--version"], json_output=False)

        assert "--json" not in run.call_args[0][0]

    def test_the_session_dir_is_always_pinned(self, fake_binary):
        """Without this the studio would use the user's own library."""
        with patch("subprocess.run", return_value=_completed("{}")) as run:
            cli.run_cli(["payloads", "list"])

        args = run.call_args[0][0]
        assert "--session-dir" in args


class TestSubprocessHardening:
    def test_stdin_is_never_readable(self, fake_binary):
        """Several studio commands prompt; DEVNULL makes EOF answer them "no"."""
        with patch("subprocess.run", return_value=_completed("{}")) as run:
            cli.run_cli(["payloads", "list"])

        assert run.call_args.kwargs["stdin"] is subprocess.DEVNULL

    def test_shell_is_never_used(self, fake_binary):
        with patch("subprocess.run", return_value=_completed("{}")) as run:
            cli.run_cli(["payloads", "list"])

        assert "shell" not in run.call_args.kwargs or run.call_args.kwargs["shell"] is False

    def test_a_timeout_is_always_set(self, fake_binary):
        with patch("subprocess.run", return_value=_completed("{}")) as run:
            cli.run_cli(["payloads", "list"])

        assert run.call_args.kwargs["timeout"] > 0

    def test_the_timeout_is_clamped(self, fake_binary, monkeypatch):
        monkeypatch.setenv("PISTUDIO_MCP_MAX_TIMEOUT", "10")
        with patch("subprocess.run", return_value=_completed("{}")) as run:
            cli.run_cli(["payloads", "list"], timeout=99999)

        # _MAX_TIMEOUT is read at import, so assert the clamp function itself.
        assert cli._clamp_timeout(99999) <= cli._MAX_TIMEOUT
        assert run.call_args.kwargs["timeout"] <= cli._MAX_TIMEOUT

    def test_a_timeout_raises_a_clear_error(self, fake_binary):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1.0)),
            pytest.raises(PiStudioMCPError, match="timed out"),
        ):
            cli.run_cli(["payloads", "list"])


class TestChildEnvironment:
    def test_unrelated_secrets_are_dropped(self, fake_binary, monkeypatch):
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-not-pass")
        monkeypatch.setenv("OPENAI_API_KEY", "also-not")

        env = cli.child_env()

        assert "AWS_SECRET_ACCESS_KEY" not in env
        assert "OPENAI_API_KEY" not in env

    def test_the_studio_own_config_passes_through(self, fake_binary, monkeypatch):
        """`payloads generate` cannot work without its LLM provider config."""
        monkeypatch.setenv("PISTUDIO_LLM_PROVIDER", "anthropic")

        assert cli.child_env()["PISTUDIO_LLM_PROVIDER"] == "anthropic"

    # Every shipping device is driven over USB or serial and needs no
    # credential, so _DEVICE_CREDENTIAL_VARS is empty. These tests register a
    # synthetic one: the control has to keep working for the device that
    # reintroduces it, and an empty tuple would otherwise make them vacuous.
    _FAKE_CREDENTIAL = "DEVICE_PASSWORD"

    def test_device_credentials_are_dropped_when_hardware_is_off(self, fake_binary, monkeypatch):
        monkeypatch.setattr(cli, "_DEVICE_CREDENTIAL_VARS", (self._FAKE_CREDENTIAL,))
        monkeypatch.delenv("PISTUDIO_MCP_ENABLE_HW", raising=False)
        monkeypatch.setenv(self._FAKE_CREDENTIAL, "secret")

        assert self._FAKE_CREDENTIAL not in cli.child_env()

    def test_credentials_are_dropped_even_under_full_env(self, fake_binary, monkeypatch):
        """Isolates the credential drop from the allowlist.

        The allowlist already excludes an unknown variable, so the test above
        passes whether or not the explicit drop exists — the two controls cover
        each other and either could be deleted as redundant.
        PISTUDIO_MCP_FULL_ENV removes the allowlist, which is exactly when the
        drop has to carry the weight on its own: opting into a full environment
        must not silently opt into handing a device password to every
        subprocess.
        """
        monkeypatch.setattr(cli, "_DEVICE_CREDENTIAL_VARS", (self._FAKE_CREDENTIAL,))
        monkeypatch.setenv("PISTUDIO_MCP_FULL_ENV", "1")
        monkeypatch.delenv("PISTUDIO_MCP_ENABLE_HW", raising=False)
        monkeypatch.setenv(self._FAKE_CREDENTIAL, "secret")

        assert self._FAKE_CREDENTIAL not in cli.child_env()

    def test_device_credentials_pass_when_hardware_is_on(self, fake_binary, monkeypatch):
        monkeypatch.setattr(cli, "_DEVICE_CREDENTIAL_VARS", (self._FAKE_CREDENTIAL,))
        monkeypatch.setenv("PISTUDIO_MCP_ENABLE_HW", "1")
        monkeypatch.setenv(self._FAKE_CREDENTIAL, "secret")

        assert cli.child_env()[self._FAKE_CREDENTIAL] == "secret"

    def test_an_ngrok_token_is_never_inherited(self, fake_binary, monkeypatch):
        """Publishing must be an explicit per-call decision, not inherited."""
        monkeypatch.setenv("NGROK_AUTHTOKEN", "2abc_def")

        assert "NGROK_AUTHTOKEN" not in cli.child_env()

    def test_full_env_opt_in_passes_everything(self, fake_binary, monkeypatch):
        monkeypatch.setenv("PISTUDIO_MCP_FULL_ENV", "1")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "now-passes")

        assert cli.child_env()["AWS_SECRET_ACCESS_KEY"] == "now-passes"

    def test_a_typo_in_the_opt_in_fails_closed(self, fake_binary, monkeypatch):
        monkeypatch.setenv("PISTUDIO_MCP_FULL_ENV", "maybe")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-not-pass")

        assert "AWS_SECRET_ACCESS_KEY" not in cli.child_env()


class TestOutputParsing:
    def test_an_indented_json_object_is_parsed(self, fake_binary):
        """`json.dumps(indent=2)` spans lines, so a per-line parse alone fails."""
        with patch("subprocess.run", return_value=_completed('{\n  "running": false\n}')):
            assert cli.run_cli(["serve", "status"]).data == {"running": False}

    def test_a_top_level_array_is_parsed(self, fake_binary):
        """`payloads list` returns an array, not an object."""
        with patch("subprocess.run", return_value=_completed('[{"name": "a"}]')):
            assert cli.run_cli(["payloads", "list"]).data == [{"name": "a"}]

    def test_stderr_is_never_used_as_a_payload(self, fake_binary):
        """A JSON-looking log line on stderr must not stand in for a result."""
        with patch("subprocess.run", return_value=_completed(stdout="", stderr='{"status": "ok"}')):
            assert cli.run_cli(["payloads", "list"]).data is None

    def test_unparseable_output_reads_as_no_data(self, fake_binary):
        with patch("subprocess.run", return_value=_completed("not json at all")):
            assert cli.run_cli(["payloads", "list"]).data is None

    def test_a_trailing_notice_after_json_is_tolerated(self, fake_binary):
        with patch("subprocess.run", return_value=_completed('{"a": 1}\nDone.')):
            assert cli.run_cli(["payloads", "list"]).data == {"a": 1}


class TestErrorReporting:
    def test_a_nonzero_exit_raises_with_the_verb_path_only(self, fake_binary):
        with patch("subprocess.run", return_value=_completed(stderr="boom", returncode=1)):
            result = cli.run_cli(["payloads", "add", "name", "the payload text"])

        with pytest.raises(PiStudioMCPError) as exc:
            result.raise_for_error(["payloads", "add", "name", "the payload text"])
        assert "payloads add name" in str(exc.value)
        assert "the payload text" not in str(exc.value)

    def test_a_credential_in_the_error_is_redacted(self, fake_binary):
        with patch("subprocess.run", return_value=_completed(stderr="password: hunter2000", returncode=1)):
            result = cli.run_cli(["hw", "flipper", "status"])

        with pytest.raises(PiStudioMCPError, match="redacted"):
            result.raise_for_error(["hw", "flipper", "status"])

    def test_a_missing_binary_is_reported_clearly(self, fake_binary, monkeypatch):
        monkeypatch.setenv("PISTUDIO_BIN", "/nonexistent/pistudio")

        with pytest.raises(PiStudioMCPError, match="PISTUDIO_BIN"):
            cli.studio_bin()

    def test_no_binary_anywhere_names_the_fix(self, fake_binary, monkeypatch):
        monkeypatch.delenv("PISTUDIO_BIN", raising=False)
        with patch("shutil.which", return_value=None), pytest.raises(PiStudioMCPError, match="PATH"):
            cli.studio_bin()


class TestStudioIdentity:
    def test_a_broken_binary_reports_rather_than_raises(self, fake_binary, monkeypatch):
        """Diagnosing the wrong-binary mistake must not itself fail."""
        monkeypatch.setenv("PISTUDIO_BIN", "/nonexistent/pistudio")

        identity = cli.studio_identity()

        assert identity["path"] is None
        assert identity["error"]


@pytest.mark.skipif(not REAL_BINARY, reason="no pistudio binary available")
class TestAgainstTheRealStudio:
    """Contract tests: the mocks above assume an output shape — verify it."""

    def test_payloads_list_returns_an_array_of_named_entries(self):
        result = cli.run_cli(["payloads", "list"])

        assert result.ok, result.stderr
        assert isinstance(result.data, list)
        assert all("name" in entry for entry in result.data)

    def test_serve_status_returns_an_object(self):
        result = cli.run_cli(["serve", "status"])

        assert result.ok, result.stderr
        assert isinstance(result.data, dict)
        assert "running" in result.data

    def test_an_unknown_command_exits_nonzero(self):
        result = cli.run_cli(["payloads", "no-such-subcommand"])

        assert not result.ok
