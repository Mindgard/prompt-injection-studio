"""The optional-dependency contract.

A base install must stay usable: listing formats works, available formats
generate, and unavailable ones fail with an install hint rather than a bare
ImportError.  These tests simulate missing extras rather than requiring a
second venv.
"""

from __future__ import annotations

import builtins
import re

import pytest

from pistudio.files.formats import (
    FORMAT_REGISTRY,
    RUNTIME_PROVISIONED,
    all_format_names,
    get_format,
    is_format_available,
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _out(studio) -> str:
    """Console output with colour escapes and line wrapping removed."""
    return " ".join(_ANSI.sub("", studio.buf.getvalue()).split())


@pytest.fixture
def without_modules(monkeypatch):
    """Make the named top-level modules un-importable for the duration of a test."""

    def _apply(*names: str) -> None:
        blocked = set(names)
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.split(".")[0] in blocked:
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

    return _apply


def test_every_format_group_is_a_declared_extra():
    """Each format's pip extra must exist in pyproject, or users cannot install it."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    extras = set(tomllib.loads(pyproject.read_text())["project"]["optional-dependencies"])

    for name, fmt in FORMAT_REGISTRY.items():
        if fmt.requires and fmt.group and fmt.group not in RUNTIME_PROVISIONED:
            assert fmt.group in extras, f"format {name!r} needs undeclared extra {fmt.group!r}"


# ── The runtime-provisioned contract ─────────────────────────────
#
# Two formats are installed into their own venv, not by pip.  Telling a user
# to `pip install` them is worse than useless: the extra does not exist, and
# for anamorpher the resolver hard-fails (numpy<2.0 vs opencv's numpy>=2).


def test_runtime_provisioned_groups_are_not_extras():
    """The mapping's reason to exist: pip cannot install these."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    extras = set(tomllib.loads(pyproject.read_text())["project"]["optional-dependencies"])
    overlap = set(RUNTIME_PROVISIONED) & extras
    assert not overlap, f"runtime-provisioned groups declared as extras: {sorted(overlap)}"


def test_every_runtime_provisioned_group_is_used_by_a_format():
    """A stale key would be a hint nothing can ever print."""
    groups = {f.group for f in FORMAT_REGISTRY.values()}
    unused = set(RUNTIME_PROVISIONED) - groups
    assert not unused, f"no format uses these groups: {sorted(unused)}"


def test_runtime_provisioned_setup_commands_are_real():
    """Each setup command must name a live command, format, and subcommand."""
    from pistudio.commands import get_command

    for group, command in RUNTIME_PROVISIONED.items():
        cmd_name, fmt_name, verb = command.split()
        assert get_command(cmd_name) is not None, f"{group}: no command {cmd_name!r}"
        assert get_format(fmt_name) is not None, f"{group}: no format {fmt_name!r}"
        assert verb == "setup"


def test_file_list_offers_setup_not_pip_for_anamorph(studio, monkeypatch):
    """The bug: `pip install git+...anamorpher.git` conflicts and would not help."""
    from pistudio.commands import get_command

    monkeypatch.setattr("pistudio.files.anamorpher._find_venv_python", lambda: None)
    get_command("file").execute(studio, ["list"])
    out = _out(studio)
    assert "file anamorph setup" in out
    assert "git+https://github.com/trailofbits/anamorpher.git" not in out


def test_audio_list_offers_setup_not_pip_for_adversarial_audio(studio, monkeypatch):
    """`pip install prompt-injection-studio[embed-adversarial-audio]` is a no-op."""
    from pistudio.commands import get_command

    monkeypatch.setattr("pistudio.files.adversarial_audio._find_venv_python", lambda: None)
    get_command("audio").execute(studio, ["list"])
    out = _out(studio)
    assert "audio adversarial-audio setup" in out


def test_no_renderer_prints_pip_install_for_runtime_provisioned_group(studio, monkeypatch):
    """Guards both renderers, and any third added later."""
    from pistudio.commands import get_command

    monkeypatch.setattr("pistudio.files.anamorpher._find_venv_python", lambda: None)
    monkeypatch.setattr("pistudio.files.adversarial_audio._find_venv_python", lambda: None)
    for name in ("file", "audio"):
        get_command(name).execute(studio, ["list"])
    out = _out(studio)
    for group in RUNTIME_PROVISIONED:
        assert f"prompt-injection-studio[{group}]" not in out


def test_pip_installable_formats_still_get_the_pip_hint(studio, monkeypatch, without_modules):
    """The setup-command branch must not swallow the ordinary extras hint."""
    from pistudio.commands import get_command

    without_modules("moviepy")
    monkeypatch.setattr("pistudio.files.anamorpher._find_venv_python", lambda: None)
    get_command("file").execute(studio, ["list"])
    assert "pip install prompt-injection-studio[embed-video]" in _out(studio)


def test_stdlib_formats_need_no_extras():
    """Formats with no third-party requirement are always available."""
    stdlib = [n for n, f in FORMAT_REGISTRY.items() if not f.requires]
    assert stdlib, "expected at least one stdlib-only format"
    for name in stdlib:
        assert is_format_available(get_format(name))


def test_format_listing_survives_missing_deps(without_modules):
    """`file list` must not crash when heavy dependencies are absent."""
    without_modules("numpy", "PIL", "treepoem", "fpdf", "docx", "pptx", "openpyxl")
    names = all_format_names()
    assert "txt" in names
    assert "md" in names


def test_unavailable_format_raises_install_hint(without_modules):
    """A missing dependency yields an actionable message naming the extra."""
    fmt = get_format("pdf")
    without_modules("fpdf")
    with pytest.raises(ImportError, match=r"prompt-injection-studio\[embed\]"):
        fmt.writer("payload text", "/tmp/should-not-be-written.pdf")


def test_install_hints_name_this_package():
    """No install hint should still point at the package this was extracted from."""
    import pathlib

    root = pathlib.Path(__file__).parent.parent / "pistudio"
    offenders = [
        p.relative_to(root)
        for p in root.rglob("*.py")
        if "mindgard-shell[" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, f"stale install hints in: {offenders}"
