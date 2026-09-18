"""Tests for the guardrail that keeps tests from writing into the repo root.

A ``MagicMock`` shell whose ``session_dir`` was never set stringifies into a
path, so ``os.path.join(shell.session_dir, ...)`` creates a real
``MagicMock/mock.session_dir/<id>/`` directory. Twenty-five of those were
committed before anyone noticed. These run pytest in a subprocess because the
guardrail is a report hook — it cannot be exercised from inside a test it is
itself reporting on.
"""

import subprocess
import sys
import textwrap

import pytest

_LEAKY_TEST = """
    from unittest.mock import MagicMock

    from pistudio.hardware.payloads import add_payload


    def test_writes_into_the_repo_root():
        shell = MagicMock()
        add_payload("probe", "text", shell.session_dir)
"""

_CLEAN_TEST = """
    def test_writes_nothing(tmp_path):
        (tmp_path / "fine.txt").write_text("inside tmp_path")
"""

_FAILING_TEST = """
    def test_fails_on_its_own_terms():
        assert 1 == 2, "ordinary assertion"
"""


def _run_pytest(body: str, repo_root) -> subprocess.CompletedProcess:
    """Run a one-off test file against the real conftest, from the repo root."""
    test_file = repo_root / "tests" / f"test_generated_{abs(hash(body))}.py"
    test_file.write_text(textwrap.dedent(body))
    try:
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "no:randomly"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        test_file.unlink(missing_ok=True)


@pytest.fixture
def repo_root():
    import pathlib

    return pathlib.Path(__file__).resolve().parent.parent


class TestRepoPollutionIsCaught:
    def test_a_leaking_test_fails(self, repo_root):
        result = _run_pytest(_LEAKY_TEST, repo_root)

        assert result.returncode != 0, "a test that polluted the repo root passed"
        assert "wrote into the repo root" in result.stdout

    def test_the_stray_directory_is_removed(self, repo_root):
        """Failing without cleaning is how they reached a commit."""
        _run_pytest(_LEAKY_TEST, repo_root)

        assert not (repo_root / "MagicMock").exists()

    def test_the_message_names_the_remedy(self, repo_root):
        result = _run_pytest(_LEAKY_TEST, repo_root)

        assert "tmp_path" in result.stdout


class TestGuardrailDoesNotInterfere:
    def test_a_clean_test_still_passes(self, repo_root):
        result = _run_pytest(_CLEAN_TEST, repo_root)

        assert result.returncode == 0, result.stdout

    def test_an_ordinary_failure_keeps_its_own_message(self, repo_root):
        """The hook rewrites passing reports only; a real failure is untouched."""
        result = _run_pytest(_FAILING_TEST, repo_root)

        assert result.returncode != 0
        assert "ordinary assertion" in result.stdout
        assert "wrote into the repo root" not in result.stdout
