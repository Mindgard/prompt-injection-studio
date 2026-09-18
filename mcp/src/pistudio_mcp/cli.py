"""Subprocess driver for the ``pistudio`` CLI.

Every capability is reached by running ``pistudio --json <command> <args...>``
and parsing the result — the studio owns the payload library, the format
writers, the payload server, and hardware delivery. This module locates the
binary, runs one command, and normalizes the output.

**Why argv and not a command string.** The studio's entry point takes a real
argv list (``pistudio payloads show <name>``), so arguments are handed to
``argparse`` as discrete list elements and no shell — OS or otherwise — ever
parses them. That removes the load-bearing assumption a ``-c "<command>"``
interface would need: there is no second POSIX parser downstream, so quoting is
not what makes a value safe, and a payload containing ``;`` or ``$(...)`` is
just a string. Validation still matters for option-injection (a value read as a
flag) and for paths, which :mod:`pistudio_mcp.security` handles.

Output shape: with ``--json`` the studio prints one JSON value — an object or a
top-level array, depending on the command — on stdout. Errors go to stderr as
plain text with a non-zero exit code. Some commands ignore ``--json`` and emit
Rich-formatted text; those are not wrapped as structured tools.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pistudio_mcp import envcfg, security
from pistudio_mcp.errors import PiStudioMCPError

_log = logging.getLogger("pistudio_mcp")

DEFAULT_TIMEOUT = 120.0

# ── resource bounds (DoS containment) ──────────────────────────────
_MAX_CONCURRENCY = envcfg.integer("PISTUDIO_MCP_MAX_CONCURRENCY", 4)
_ACQUIRE_TIMEOUT = 60.0
# Hard ceiling on any per-call timeout, so a caller cannot pin a process open.
# Generous because generating a payload calls an LLM and embedding into some
# carriers (adversarial audio, anamorphic images) is genuinely slow.
_MAX_TIMEOUT = envcfg.number("PISTUDIO_MCP_MAX_TIMEOUT", 900.0, minimum=1.0)
_MAX_OUTPUT_CHARS = envcfg.integer("PISTUDIO_MCP_MAX_OUTPUT_CHARS", 100_000)

_semaphore = threading.BoundedSemaphore(_MAX_CONCURRENCY)


def _clamp_timeout(timeout: float) -> float:
    return max(1.0, min(float(timeout), _MAX_TIMEOUT))


def _truncate(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return text[:_MAX_OUTPUT_CHARS] + f"\n...[truncated {len(text) - _MAX_OUTPUT_CHARS} chars]"


def studio_bin() -> str:
    """Resolve the ``pistudio`` executable (``PISTUDIO_BIN`` or PATH).

    Warns if the binary is group/other-writable: an attacker who can rewrite it
    gains code execution when the server runs it.
    """
    override = os.environ.get("PISTUDIO_BIN")
    if override:
        if not os.path.isfile(override):
            raise PiStudioMCPError(f"PISTUDIO_BIN does not point to a file: {override!r}")
        path = override
    else:
        found = shutil.which("pistudio")
        if not found:
            raise PiStudioMCPError(
                "pistudio not found. Install it and put it on PATH, or set PISTUDIO_BIN "
                "to the absolute path of the binary."
            )
        path = found
    try:
        if os.stat(path).st_mode & 0o022:
            _log.warning("pistudio binary %s is group/other-writable — tampering risk.", path)
    except OSError:
        pass
    return path


def studio_identity() -> dict[str, str | None]:
    """Which ``pistudio`` this server is driving, and its version.

    Surfaced in ``studio_status`` because the commonest setup mistake is
    otherwise invisible: resolving via ``PATH`` can pick up a stale wheel or a
    leftover shim, and a different build exposes a different command set. The
    server starts fine and individual tools then fail with "invalid choice",
    which reads like a server bug rather than the wrong binary.

    Never raises: this is diagnostic context, and failing to collect it must not
    be the reason ``studio_status`` fails.
    """
    try:
        path = studio_bin()
    except PiStudioMCPError as e:
        return {"path": None, "version": None, "error": str(e)}
    try:
        result = run_cli(["--version"], json_output=False, timeout=30.0)
        first = next((ln.strip() for ln in result.stdout.splitlines() if ln.strip()), None)
        return {"path": path, "version": security.redact_text(first) if first else None}
    except Exception as e:  # a broken binary is exactly what this is meant to reveal
        return {"path": path, "version": None, "error": security.redact_text(str(e))}


# Environment variables (and prefixes) the studio subprocess may see. Everything
# else is dropped so unrelated secrets (cloud credentials, other API keys) are
# never handed to it. Opt out with PISTUDIO_MCP_FULL_ENV=1.
#
# PISTUDIO_LLM_* is allowed through: `payloads generate`
# call a model, and without its provider config those tools cannot work at all.
_ENV_ALLOW_EXACT = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "TERM",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "TZ",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)
_ENV_ALLOW_PREFIX = ("PISTUDIO_", "LC_")

# Credentials for physical devices, dropped unless hardware tools are enabled:
# with hardware off there is no reason for the child to hold a device password,
# and handing it over anyway widens the blast radius of any bug for no benefit.
#
# Every device the studio currently ships is driven over USB or serial and
# needs no credential, so this is empty. It stays as the registration point
# for network-attached hardware: because the allowlist above is default-deny,
# a variable added here is scrubbed unless hardware tools are explicitly on.
_DEVICE_CREDENTIAL_VARS: tuple[str, ...] = ()

_ENABLE_HW_ENV = "PISTUDIO_MCP_ENABLE_HW"


def child_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build the environment for a studio subprocess.

    Two things are scrubbed:

    * everything outside the allowlist, unless ``PISTUDIO_MCP_FULL_ENV=1``;
    * device credentials, unless hardware tools are enabled.

    ``NGROK_AUTHTOKEN`` is deliberately *not* in the allowlist. Publishing
    payloads to the public internet should be a decision the operator makes
    explicitly per session, not something the server inherits from a shell
    profile it happens to have been launched from — so the token must be passed
    through ``serve_start``'s own argument, where it is visible in the call.
    """
    source = {**os.environ, **(extra_env or {})}
    hardware = envcfg.truthy(source.get(_ENABLE_HW_ENV))
    if envcfg.truthy(source.get("PISTUDIO_MCP_FULL_ENV")):
        env = dict(source)
    else:
        allowed = set(_ENV_ALLOW_EXACT)
        if hardware:
            # Only reachable once hardware tools are on; a device command cannot
            # authenticate without them.
            allowed |= set(_DEVICE_CREDENTIAL_VARS)
        env = {k: v for k, v in source.items() if k in allowed or k.startswith(_ENV_ALLOW_PREFIX)}
    if not hardware:
        for var in _DEVICE_CREDENTIAL_VARS:
            env.pop(var, None)
    return env


def session_dir() -> str:
    """The studio state directory handed to the subprocess.

    A dedicated directory rather than the user's own ``~/.pistudio``, for the
    same reason the reference server relocates ``HOME``: the studio persists a
    payload library, and a server driven by a model should not be able to edit
    the library the user curates by hand in a terminal. ``payloads add`` through
    a tool call lands here instead.

    ``PISTUDIO_MCP_SHARE_SESSION=1`` uses the real one, for anyone who wants the
    library they already curated to be visible to the assistant.
    """
    if envcfg.flag("PISTUDIO_MCP_SHARE_SESSION"):
        return str(Path.home() / ".pistudio")
    path = Path.home() / ".pistudio" / "mcp-session"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError as e:  # inside the user's own home either way
        _log.debug("could not restrict %s: %s", path, e)
    return str(path)


@dataclass
class CliResult:
    ok: bool
    exit_code: int
    data: Any  # parsed JSON payload, or None
    stdout: str
    stderr: str

    def raise_for_error(self, argv: list[str]) -> Any:
        """Return ``data`` on success; raise a user-facing error otherwise.

        Both the command and the message are scrubbed before they reach the
        model: only the verb path is echoed, so payload text passed as an
        argument is not reflected back, and credential-shaped output is masked.
        """
        if self.ok:
            return self.data
        message = self.data.get("message") if isinstance(self.data, dict) else None
        message = message or (self.stderr.strip() or self.stdout.strip()) or "command failed"
        raise PiStudioMCPError(
            f"`{security.command_prefix(argv)}` failed (exit {self.exit_code}): {security.redact_text(str(message))}"
        )


def _json_payload(stdout: str) -> Any:
    """Parse the studio's JSON output from *stdout*.

    Only stdout is consulted. Taking a payload from stderr as a fallback would
    let a log line that happens to look like JSON stand in for a real result,
    handing the model a fabricated success — and the studio writes its errors to
    stderr as plain text, so there is nothing to gain there.

    The whole stream is tried first because ``json.dumps(..., indent=2)`` spans
    lines; the per-line pass is the fallback for output with a trailing notice.
    """
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line and line[0] in "{[":
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def run_cli(
    argv: list[str],
    *,
    json_output: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
    extra_env: dict[str, str] | None = None,
    audit_context: dict[str, Any] | None = None,
) -> CliResult:
    """Run one studio command and return a normalized :class:`CliResult`.

    Args:
        argv: The command as a list, e.g. ``["payloads", "show", "my-payload"]``.
            Passed straight through to the studio's argv — never joined into a
            string, so no shell parses it.
        json_output: Add ``--json``. Off for ``--version``, which has no JSON form.
        timeout: Seconds before the subprocess is killed.
        extra_env: Extra environment for this call.
        audit_context: Validated identifiers to add to the audit record, e.g. the
            device a payload was deployed to. Never freeform values.
    """
    timeout = _clamp_timeout(timeout)
    flags = ["--json"] if json_output else []
    args = [studio_bin(), *flags, "--session-dir", session_dir(), *argv]
    if not _semaphore.acquire(timeout=_ACQUIRE_TIMEOUT):
        raise PiStudioMCPError(
            f"server busy: over {_MAX_CONCURRENCY} studio commands already in flight. "
            "Retry shortly, or raise PISTUDIO_MCP_MAX_CONCURRENCY."
        )
    started = time.monotonic()
    try:
        # S603: this is the module's purpose — an argv list, never shell=True, so
        # no OS shell parses tool input.
        #
        # stdin=DEVNULL is a security control, not tidiness. Several studio
        # commands prompt interactively: `payloads add` reads the payload body
        # from stdin, and every device-mutating command asks for confirmation.
        # With DEVNULL they hit EOF, which the studio treats as "no" — so a tool
        # call cannot answer its own confirmation prompt.
        proc = subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=child_env(extra_env),
            cwd=session_dir(),
        )
    except subprocess.TimeoutExpired as e:
        security.audit_command(
            argv, ok=False, exit_code=-1, duration_ms=(time.monotonic() - started) * 1000, context=audit_context
        )
        raise PiStudioMCPError(
            f"`{security.command_prefix(argv)}` timed out after {timeout:.0f}s. Generating a "
            "payload calls a model and embedding into some carriers is slow; raise the timeout "
            "or check the LLM provider is reachable."
        ) from e
    except FileNotFoundError as e:
        raise PiStudioMCPError(f"could not run pistudio: {e}") from e
    finally:
        _semaphore.release()

    data = _json_payload(proc.stdout) if json_output else None
    # The studio reports some failures as {"status": "error", "message": ...}.
    # Judging on the exit code alone would read one of those as a success and
    # hand the model an error object as though it were a result.
    status_error = isinstance(data, dict) and data.get("status") == "error"
    ok = proc.returncode == 0 and not status_error
    security.audit_command(
        argv,
        ok=ok,
        exit_code=proc.returncode,
        duration_ms=(time.monotonic() - started) * 1000,
        context=audit_context,
    )
    return CliResult(
        ok=ok,
        exit_code=proc.returncode,
        data=data,
        stdout=_truncate(proc.stdout),
        stderr=_truncate(proc.stderr),
    )
