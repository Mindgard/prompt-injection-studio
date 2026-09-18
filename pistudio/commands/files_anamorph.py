"""Anamorph venv management — setup, uninstall, status for the anamorpher tool."""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
from typing import TYPE_CHECKING

from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

logger = logging.getLogger(__name__)


def anamorph_setup(shell: StudioProtocol) -> None:
    """Set up the anamorpher venv with user confirmation."""
    from pistudio.files.anamorpher import (
        ANAMORPHER_BLOG,
        ANAMORPHER_CREDIT,
        ANAMORPHER_REPO,
        _default_venv_dir,
        _find_venv_python,
    )

    t = active_theme()

    # Check if already installed
    if _find_venv_python() is not None:
        shell.out.info("Anamorpher is already installed and available.")
        anamorph_status(shell)
        return

    # Show info and credit
    shell.console.print()
    shell.console.print(f"  [{t.secondary} bold]Anamorpher — Adversarial Image Scaling Attacks[/]")
    shell.console.print()
    shell.console.print(f"  [{t.muted}]{ANAMORPHER_CREDIT}[/]")
    shell.console.print(f"  [{t.muted}]Repo: {ANAMORPHER_REPO}[/]")
    shell.console.print(f"  [{t.muted}]Blog: {ANAMORPHER_BLOG}[/]")
    shell.console.print()
    shell.console.print(
        "  Anamorpher generates images that look like a decoy at full resolution\n"
        "  but reveal a hidden prompt injection payload when downscaled by AI\n"
        "  vision systems."
    )
    shell.console.print()
    shell.console.print(f"  [{t.error} bold]⚠  This install is large (~3–5 GB)[/]")
    shell.console.print(f"  [{t.muted}]   Includes: PyTorch, TensorFlow, OpenCV, NumPy, Flask[/]")
    shell.console.print(f"  [{t.muted}]   Requires: Python 3.11 (via pyenv) for numpy<2.0 compat[/]")
    shell.console.print(f"  [{t.muted}]   Location: {_default_venv_dir()}[/]")
    shell.console.print()

    # Get confirmation
    try:
        from prompt_toolkit import prompt as pt_prompt

        answer = pt_prompt("  Proceed with installation? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        shell.console.print()
        return

    if answer not in ("y", "yes"):
        shell.out.info("Installation cancelled.")
        return

    # Step 1: Find Python 3.11
    shell.console.print()
    python311 = find_python311()
    if python311 is None:
        shell.out.error(
            "Python 3.11 not found. Install it first:\n  pyenv install 3.11.12\n\nThen re-run: file anamorph setup"
        )
        return

    shell.out.info(f"Using Python: {python311}")

    venv_dir = _default_venv_dir()

    # Step 2: Create venv
    try:
        with shell.spinner("Creating isolated Python 3.11 venv..."):
            result = subprocess.run(
                [python311, "-m", "venv", venv_dir],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                shell.out.error(f"Failed to create venv:\n{result.stderr.strip()}")
                return
    except subprocess.TimeoutExpired:
        shell.out.error("Venv creation timed out.")
        return

    shell.out.info("Venv created.")

    # Step 3: Install anamorpher
    pip_path = os.path.join(venv_dir, "bin", "pip")
    try:
        with shell.spinner("Installing anamorpher from GitHub (this may take several minutes)..."):
            result = subprocess.run(
                [pip_path, "install", f"git+{ANAMORPHER_REPO}.git"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                shell.out.error(f"Installation failed:\n{stderr[-500:]}")
                return
    except subprocess.TimeoutExpired:
        shell.out.error(
            f"Installation timed out (10 min limit). Try manually:\n  {pip_path} install git+{ANAMORPHER_REPO}.git"
        )
        return

    # Verify
    if _find_venv_python() is not None:
        shell.console.print()
        shell.out.success("Anamorpher installed successfully!")
        shell.console.print()
        shell.console.print(f"  [{t.muted}]Credit: {ANAMORPHER_CREDIT} — {ANAMORPHER_REPO}[/]")
        shell.console.print()
        shell.console.print(f"  [{t.secondary}]Usage:[/]")
        shell.console.print('    file anamorph "Ignore instructions" --decoy photo.png')
        shell.console.print()
        shell.console.print(f"  [{t.secondary}]To remove later:[/]")
        shell.console.print("    file anamorph uninstall")
        shell.console.print()
        shell.audit.log("anamorph_setup", venv=venv_dir)
    else:
        shell.out.error("Installation completed but venv verification failed.")


def anamorph_uninstall(shell: StudioProtocol) -> None:
    """Remove the anamorpher venv."""
    import shutil

    from pistudio.files.anamorpher import _default_venv_dir, _find_venv_python

    t = active_theme()
    venv_dir = _default_venv_dir()

    if _find_venv_python() is None:
        shell.out.info("Anamorpher is not currently installed.")
        return

    # Calculate size
    total = 0
    for dirpath, _, filenames in os.walk(venv_dir):
        for f in filenames:
            with contextlib.suppress(OSError):
                total += os.path.getsize(os.path.join(dirpath, f))
    size_mb = total / (1024 * 1024)

    shell.console.print()
    shell.console.print(f"  [{t.secondary} bold]Remove anamorpher venv?[/]")
    shell.console.print(f"  [{t.muted}]Location: {venv_dir}[/]")
    shell.console.print(f"  [{t.muted}]Size:     {size_mb:.0f} MB[/]")
    shell.console.print()

    try:
        from prompt_toolkit import prompt as pt_prompt

        answer = pt_prompt("  Delete this venv? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        shell.console.print()
        return

    if answer not in ("y", "yes"):
        shell.out.info("Uninstall cancelled.")
        return

    try:
        shutil.rmtree(venv_dir)
        shell.out.success("Anamorpher venv removed.")
        shell.audit.log("anamorph_uninstall", venv=venv_dir)
    except Exception as e:
        shell.out.error(f"Failed to remove venv: {e}")


def anamorph_status(shell: StudioProtocol) -> None:
    """Show anamorpher installation status."""
    from pistudio.files.anamorpher import (
        ANAMORPHER_BLOG,
        ANAMORPHER_REPO,
        _find_venv_python,
    )

    t = active_theme()
    venv_python = _find_venv_python()

    shell.console.print()
    shell.console.print(f"  [{t.secondary} bold]Anamorpher Status[/]")
    shell.console.print()

    if venv_python:
        # Get Python version
        try:
            result = subprocess.run(
                [venv_python, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            py_ver = result.stdout.strip()
        except Exception:
            py_ver = "unknown"

        # Get venv size
        venv_dir = os.path.dirname(os.path.dirname(venv_python))
        total = 0
        for dirpath, _, filenames in os.walk(venv_dir):
            for f in filenames:
                with contextlib.suppress(OSError):
                    total += os.path.getsize(os.path.join(dirpath, f))
        size_mb = total / (1024 * 1024)

        shell.console.print(f"  [{t.accent}]●[/] Installed and available")
        shell.console.print(f"  [{t.muted}]  Python:   {py_ver}[/]")
        shell.console.print(f"  [{t.muted}]  Venv:     {venv_dir}[/]")
        shell.console.print(f"  [{t.muted}]  Size:     {size_mb:.0f} MB[/]")
    else:
        from pistudio.files.formats import RUNTIME_PROVISIONED

        shell.console.print(f"  [{t.error}]●[/] Not installed")
        shell.console.print(f"  [{t.muted}]  Run: {RUNTIME_PROVISIONED['embed-anamorpher']}[/]")

    shell.console.print()
    shell.console.print(f"  [{t.muted}]By Trail of Bits[/]")
    shell.console.print(f"  [{t.muted}]Repo: {ANAMORPHER_REPO}[/]")
    shell.console.print(f"  [{t.muted}]Blog: {ANAMORPHER_BLOG}[/]")
    shell.console.print()


def write_anamorph(
    shell: StudioProtocol,
    text: str,
    path: str,
    decoy_path: str | None,
    algorithm: str,
    lam_str: str | None,
    target_size_str: str | None,
) -> None:
    """Handle the anamorph format with its special flags and spinner."""
    from pistudio.files.anamorpher import (
        DEFAULT_LAMBDA,
        DEFAULT_TARGET_SIZE,
        _parse_target_size,
    )
    from pistudio.files.anamorpher import (
        write_anamorph as _write_anamorph,
    )

    # Parse lambda
    lam = DEFAULT_LAMBDA
    if lam_str:
        try:
            lam = float(lam_str)
        except ValueError:
            shell.out.error(f"Invalid --lambda value: '{lam_str}'. Expected a float (e.g. 0.25)")
            return

    # Parse target size
    target_size = DEFAULT_TARGET_SIZE
    if target_size_str:
        try:
            target_size = _parse_target_size(target_size_str)
        except ValueError as e:
            shell.out.error(str(e))
            return

    try:
        with shell.spinner("Generating adversarial image...") as status:
            status.update("Rendering target payload...")
            _write_anamorph(
                text,
                path,
                decoy_path=decoy_path,
                algorithm=algorithm,
                lam=lam,
                target_size=target_size,
            )
    except (ImportError, ValueError, FileNotFoundError, RuntimeError) as e:
        shell.out.error(str(e))
        return
    except Exception as e:
        shell.out.error(f"Failed to generate adversarial image: {e}")
        return

    shell.out.success(f"Adversarial image written to: {path}")
    shell.out.info(f"  Algorithm: {algorithm}, Lambda: {lam}, Target: {target_size[0]}x{target_size[1]}")
    shell.audit.log("embed_generate", format="anamorph", path=path, algorithm=algorithm)


def find_python311() -> str | None:
    """Find a Python 3.11 binary via pyenv or PATH.

    MED-09: Each candidate is verified by running ``--version`` to
    confirm it is genuinely Python 3.11, preventing PATH-poisoning
    attacks where a malicious binary is placed earlier in PATH.
    """
    import glob

    def _verify(candidate: str) -> bool:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "Python 3.11" in result.stdout
        except Exception:
            return False

    # Check pyenv versions first
    pyenv_root = os.environ.get("PYENV_ROOT", os.path.expanduser("~/.pyenv"))
    versions_dir = os.path.join(pyenv_root, "versions")
    if os.path.isdir(versions_dir):
        for pattern in ("3.11.*",):
            for version_dir in sorted(glob.glob(os.path.join(versions_dir, pattern)), reverse=True):
                candidate = os.path.join(version_dir, "bin", "python3")
                if os.path.isfile(candidate) and _verify(candidate):
                    return candidate

    # Check PATH
    for name in ("python3.11", "python3"):
        for p in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(p, name)
            if os.path.isfile(candidate) and _verify(candidate):
                return candidate

    return None
