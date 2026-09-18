"""Adversarial audio venv management — setup, uninstall, status."""

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


def adversarial_audio_setup(shell: StudioProtocol) -> None:
    """Set up the adversarial-audio venv with user confirmation."""
    from pistudio.files.adversarial_audio import (
        ART_CREDIT,
        ART_DOCS,
        ART_REPO,
        _default_venv_dir,
        _find_venv_python,
    )

    t = active_theme()

    # Check if already installed
    if _find_venv_python() is not None:
        shell.out.info("Adversarial audio venv is already installed and available.")
        adversarial_audio_status(shell)
        return

    # Show info
    shell.console.print()
    shell.console.print(f"  [{t.secondary} bold]Adversarial Audio — White-box ASR Attacks[/]")
    shell.console.print()
    shell.console.print(f"  [{t.muted}]Using the {ART_CREDIT}[/]")
    shell.console.print(f"  [{t.muted}]Repo: {ART_REPO}[/]")
    shell.console.print(f"  [{t.muted}]Docs: {ART_DOCS}[/]")
    shell.console.print()
    shell.console.print(
        "  Generates audio that sounds like one thing but is transcribed\n"
        "  as a target phrase by ASR models (Whisper, DeepSpeech)."
    )
    shell.console.print()
    shell.console.print(f"  [{t.error} bold]⚠  This install is large (~2–3 GB)[/]")
    shell.console.print(f"  [{t.muted}]   Includes: PyTorch, ART, NumPy, SciPy[/]")
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

    # Step 1: Find Python
    shell.console.print()
    python_bin = find_python_for_venv()
    if python_bin is None:
        shell.out.error("Python 3.12+ not found. Please ensure Python is installed.")
        return

    shell.out.info(f"Using Python: {python_bin}")

    venv_dir = _default_venv_dir()

    # Step 2: Create venv
    try:
        with shell.spinner("Creating isolated venv..."):
            result = subprocess.run(
                [python_bin, "-m", "venv", venv_dir],
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

    # Step 3: Install dependencies
    pip_path = os.path.join(venv_dir, "bin", "pip")
    try:
        with shell.spinner("Installing ART + PyTorch (this may take several minutes)..."):
            result = subprocess.run(
                [pip_path, "install", "adversarial-robustness-toolbox[pytorch]", "scipy"],
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
            "Installation timed out (10 min limit). Try manually:\n"
            f"  {pip_path} install adversarial-robustness-toolbox[pytorch] scipy"
        )
        return

    # Verify
    if _find_venv_python() is not None:
        shell.console.print()
        shell.out.success("Adversarial audio venv installed successfully!")
        shell.console.print()
        shell.console.print(f"  [{t.secondary}]Usage:[/]")
        shell.console.print('    audio adversarial-audio "target phrase" --carrier input.wav')
        shell.console.print()
        shell.console.print(f"  [{t.secondary}]To remove later:[/]")
        shell.console.print("    audio adversarial-audio uninstall")
        shell.console.print()
        shell.audit.log("adversarial_audio_setup", venv=venv_dir)
    else:
        shell.out.error("Installation completed but venv verification failed.")


def adversarial_audio_uninstall(shell: StudioProtocol) -> None:
    """Remove the adversarial-audio venv."""
    import shutil

    from pistudio.files.adversarial_audio import _default_venv_dir, _find_venv_python

    t = active_theme()
    venv_dir = _default_venv_dir()

    if _find_venv_python() is None:
        shell.out.info("Adversarial audio venv is not currently installed.")
        return

    # Calculate size
    total = 0
    for dirpath, _, filenames in os.walk(venv_dir):
        for f in filenames:
            with contextlib.suppress(OSError):
                total += os.path.getsize(os.path.join(dirpath, f))
    size_mb = total / (1024 * 1024)

    shell.console.print()
    shell.console.print(f"  [{t.secondary} bold]Remove adversarial-audio venv?[/]")
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
        shell.out.success("Adversarial audio venv removed.")
        shell.audit.log("adversarial_audio_uninstall", venv=venv_dir)
    except Exception as e:
        shell.out.error(f"Failed to remove venv: {e}")


def adversarial_audio_status(shell: StudioProtocol) -> None:
    """Show adversarial-audio installation status."""
    from pistudio.files.adversarial_audio import ART_CREDIT, ART_DOCS, ART_REPO, get_venv_status

    t = active_theme()
    status = get_venv_status()

    shell.console.print()
    shell.console.print(f"  [{t.secondary} bold]Adversarial Audio Status[/]")
    shell.console.print()

    if status["installed"]:
        shell.console.print(f"  [{t.accent}]●[/] Installed and available")
        shell.console.print(f"  [{t.muted}]  Python:   {status['python_version']}[/]")
        shell.console.print(f"  [{t.muted}]  Venv:     {status['venv_path']}[/]")
        shell.console.print(f"  [{t.muted}]  Size:     {status['size_mb']:.0f} MB[/]")
    else:
        from pistudio.files.formats import RUNTIME_PROVISIONED

        shell.console.print(f"  [{t.error}]●[/] Not installed")
        shell.console.print(f"  [{t.muted}]  Run: {RUNTIME_PROVISIONED['embed-adversarial-audio']}[/]")

    shell.console.print()
    shell.console.print(f"  [{t.muted}]Using the {ART_CREDIT}[/]")
    shell.console.print(f"  [{t.muted}]Repo: {ART_REPO}[/]")
    shell.console.print(f"  [{t.muted}]Docs: {ART_DOCS}[/]")
    shell.console.print()


def write_adversarial_audio(
    shell: StudioProtocol,
    text: str,
    path: str,
    carrier_path: str | None,
    model: str,
) -> None:
    """Handle adversarial-audio format with its special flags."""
    from pistudio.files.adversarial_audio import write_adversarial_audio as _write_adv

    try:
        with shell.spinner("Generating adversarial audio...") as status:
            status.update(f"Running {model} attack...")
            result = _write_adv(
                text,
                path,
                carrier_path=carrier_path,
                model=model,
            )
    except (ImportError, ValueError, FileNotFoundError, RuntimeError) as e:
        shell.out.error(str(e))
        return
    except Exception as e:
        shell.out.error(f"Failed to generate adversarial audio: {e}")
        return

    shell.out.success(f"Adversarial audio written to: {path}")
    if result.get("note"):
        shell.out.info(f"  {result['note']}")
    shell.audit.log("embed_generate", format="adversarial-audio", path=path, model=model)


def find_python_for_venv() -> str | None:
    """Find a suitable Python binary for creating venvs."""
    import sys

    # Try the current Python first
    if sys.executable:
        return sys.executable

    # Try common names
    for name in ("python3", "python"):
        for p in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(p, name)
            if os.path.isfile(candidate):
                return candidate

    return None
