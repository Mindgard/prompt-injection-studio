"""Shared test fixtures.

``_make_shell`` and ``_exec`` keep the signatures the ported tests were
written against, so test bodies work unchanged.  They build a real
:class:`~pistudio.core.studio.Studio` writing into a StringIO console, which
is cheap enough not to need a mock.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import re
import shutil

import pytest
from rich.console import Console

from pistudio.commands import get_command, register_all_commands
from pistudio.core.studio import Studio, TargetContext
from pistudio.ui.output import ShellOutput

register_all_commands()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI colour escapes so output can be asserted on."""
    return _ANSI.sub("", text)


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace, so wrapped table output can be matched."""
    return " ".join(text.split())


def _make_shell(
    json_mode: bool = False,
    plain_mode: bool = False,
    tmp_path=None,
    target: TargetContext | None = None,
) -> tuple[Studio, io.StringIO]:
    """Build a Studio whose console writes to a buffer.

    Returns:
        ``(studio, buffer)`` — read ``buffer.getvalue()`` to assert on output.
    """
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=120, legacy_windows=False)
    # The modes go to the Studio, not just to the ShellOutput built afterwards:
    # commands branch on ``shell.json_mode``, so setting it only on ``out`` left
    # every JSON code path unreachable from a test.
    studio = Studio(
        session_dir=str(tmp_path) if tmp_path is not None else None,
        console=console,
        target=target or TargetContext(),
        json_mode=json_mode,
        plain_mode=plain_mode,
    )
    studio.out = ShellOutput(console, json_mode=json_mode, plain_mode=plain_mode, shell=studio)
    return studio, buf


def _exec(
    cmd_name: str,
    args: list[str],
    json_mode: bool = False,
    shell: Studio | None = None,
    buf: io.StringIO | None = None,
) -> tuple[Studio, io.StringIO]:
    """Run a registered command directly, bypassing the CLI and REPL."""
    if shell is None:
        shell, buf = _make_shell(json_mode=json_mode)
    cmd = get_command(cmd_name)
    if cmd is None:
        raise AssertionError(f"No command registered as {cmd_name!r}")
    cmd.execute(shell, args)
    assert buf is not None
    return shell, buf


@pytest.fixture
def studio(tmp_path):
    """A Studio rooted in a temp dir, with its output buffer on ``.buf``."""
    s, buf = _make_shell(tmp_path=tmp_path)
    s.buf = buf
    return s


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Keep tests out of the real ``~/.pistudio`` and off real credentials.

    A developer with PISTUDIO_LLM_* exported should get the same results as
    CI, so those are cleared unless a test sets them.
    """
    monkeypatch.setenv("PISTUDIO_HOME", str(tmp_path / "home"))
    for var in (
        "PISTUDIO_LLM_PROVIDER",
        "PISTUDIO_LLM_MODEL",
        "PISTUDIO_LLM_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


# Build artefacts and caches are the tooling's business, not a test's.
_ALLOWED_IN_REPO_ROOT = frozenset({".pytest_cache", ".ruff_cache", "__pycache__", ".coverage", "dist", "build"})

# Repo root contents captured at setup, so the report hook can diff against it.
_REPO_ROOT_BEFORE: pytest.StashKey[set[str]] = pytest.StashKey()


def _sweep_repo_root(before: set[str]) -> list[str]:
    """Remove anything a test added to the repo root; return what was removed."""
    created = {p.name for p in _REPO_ROOT.iterdir()} - before - _ALLOWED_IN_REPO_ROOT
    for name in created:
        stray = _REPO_ROOT / name
        if stray.is_dir():
            shutil.rmtree(stray, ignore_errors=True)
        else:
            stray.unlink(missing_ok=True)
    return sorted(created)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Fail a test that writes into the repository working tree, and clean up.

    A ``MagicMock`` shell whose ``session_dir`` was never set stringifies into
    a path, so ``os.path.join(shell.session_dir, ...)`` quietly created
    ``MagicMock/mock.session_dir/<id>/`` in the repo root — 25 of those got
    committed before anyone noticed.  A .gitignore entry would only hide them.

    This runs as a report hook rather than a fixture because a fixture tears
    down after the call phase has already been recorded, so it can only add an
    error beside a passing test.  Rewriting the call report puts the failure on
    the test that caused it.  Cleaning up matters as much as reporting: leaving
    the directory is how they reached a commit in the first place.
    """
    outcome = yield
    if call.when != "call":
        return

    removed = _sweep_repo_root(item.stash[_REPO_ROOT_BEFORE])
    if not removed:
        return

    report = outcome.get_result()
    if report.passed:
        report.outcome = "failed"
        report.longrepr = (
            f"test wrote into the repo root: {removed} (removed). "
            "Use the 'studio' fixture or tmp_path; a MagicMock session_dir becomes a real directory."
        )


def pytest_runtest_setup(item):
    """Record the repo root contents so the report hook can diff against it."""
    item.stash[_REPO_ROOT_BEFORE] = {p.name for p in _REPO_ROOT.iterdir()}


@pytest.fixture(autouse=True)
def _reset_payload_server():
    """Stop any server a test left running, so ports do not leak between tests."""
    yield
    from pistudio.serve.registry import reset_registry
    from pistudio.serve.server import _active_server

    if _active_server is not None:
        with contextlib.suppress(OSError, RuntimeError):
            _active_server.stop()
    reset_registry()
