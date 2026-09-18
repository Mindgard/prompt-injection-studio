"""Prompt resolution for the embed command — five sourcing modes."""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import tempfile
from typing import TYPE_CHECKING

from pistudio.commands.flags import extract_flag, strip_flag
from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

logger = logging.getLogger(__name__)


def _resolve_llm(shell: StudioProtocol):
    """Resolve the LLM for payload generation.

    Returns:
        ``(provider, api_key, base_url)``, or ``None`` when unconfigured.
    """
    from pistudio.core.llm import resolve_model

    return resolve_model()


def _unknown_flag_message(flag: str) -> str:
    """Build the error for an unrecognised flag, suggesting a near match."""
    from pistudio.commands.flags import unknown_flag_message
    from pistudio.commands.format_flags import FLAG_SCOPES

    known = [*FLAG_SCOPES, "--payload", "--edit", "--generate", "--output", "--url", "--metadata"]
    return unknown_flag_message(flag, known)


def resolve_prompt(shell: StudioProtocol, args: list[str]) -> str | None:
    """Resolve the prompt text from args using one of four modes.

    Returns the prompt text string, or None if the user cancelled.
    """

    # Mode 1: --payload <name>
    payload_name = extract_flag(args, "--payload")
    if payload_name:
        return _resolve_from_payload(shell, payload_name)

    # Mode 2: --edit
    args_clean = strip_flag(args, "--payload")
    if "--edit" in args_clean:
        return _resolve_from_editor(shell)

    # Mode 3: --generate "<desc>"
    gen_desc = extract_flag(args_clean, "--generate")
    if gen_desc:
        return _resolve_from_llm(shell, gen_desc)
    # Also handle --generate as last flag with remaining args as description
    if "--generate" in args_clean:
        idx = args_clean.index("--generate")
        desc_parts = args_clean[idx + 1 :]
        args_clean = args_clean[:idx]
        if desc_parts:
            return _resolve_from_llm(shell, " ".join(desc_parts))
        shell.out.error('Usage: file <format> --generate "<description>"')
        return None

    # Mode 4: inline text (remaining positional args)
    unknown = [a for a in args_clean if a.startswith("--")]
    if unknown:
        # Dropping just the flag token left its value behind as payload text:
        # `file md "x" --prompt red-team-aggressive` silently produced the
        # payload "x red-team-aggressive".
        shell.out.error(_unknown_flag_message(unknown[0]))
        return None

    remaining = list(args_clean)
    if remaining:
        return " ".join(remaining)

    # Mode 5: interactive picker
    return _resolve_interactive(shell)


def _resolve_from_payload(shell: StudioProtocol, name: str) -> str | None:
    """Look up a named payload from the hak5 library."""
    from pistudio.hardware.payloads import get_payload

    result = get_payload(name, shell.session_dir)
    if result is None:
        shell.out.error(f"Payload '{name}' not found. Use 'ducky list' to see available payloads.")
        return None
    payload, _scope = result
    return payload.text


def _resolve_from_editor(shell: StudioProtocol) -> str | None:
    """Open $EDITOR and return the composed text."""
    from pistudio.ui.output import resolve_editor

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", prefix="payload-", delete=False, encoding="utf-8") as tmp:
        tmp.write("# Enter your prompt injection payload below.\n# Lines starting with # are stripped.\n\n")
        tmp_path = tmp.name

    try:
        editor = resolve_editor()
        subprocess.run([editor, tmp_path], check=True)
        with open(tmp_path, encoding="utf-8") as f:
            lines = f.readlines()
        text = "".join(line for line in lines if not line.startswith("#")).strip()
        if not text:
            shell.out.info("Empty prompt — cancelled.")
            return None
        return text
    except Exception as e:
        shell.out.error(f"Editor failed: {e}")
        return None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


def _resolve_from_llm(shell: StudioProtocol, description: str) -> str | None:
    """Use LLM to generate a prompt injection payload."""
    from pistudio.hardware.generate import generate_payload

    t = active_theme()
    resolved = _resolve_llm(shell)
    if resolved is None:
        shell.out.error("No LLM configured for 'hw' function. Use 'model add' to set one up.")
        return None

    provider, api_key, base_url = resolved
    shell.console.print(f"  [{t.muted}]Generating payload with {provider}...[/]")

    try:
        result = generate_payload(shell, description, provider, api_key, base_url)
    except Exception as e:
        shell.out.error(f"Generation failed: {e}")
        return None

    shell.console.print(f"\n  [{t.secondary} bold]Generated: {result.name}[/]")
    if result.description:
        shell.console.print(f"  [{t.muted}]{result.description}[/]")
    shell.console.print(f"\n  [{t.secondary}]Payload:[/]")
    for line in result.text.splitlines():
        shell.console.print(f"    {line}")
    shell.console.print()

    return result.text


def _resolve_interactive(shell: StudioProtocol) -> str | None:
    """Show available payloads and let the user pick one."""
    from pistudio.hardware.payloads import list_payloads

    t = active_theme()
    payloads = list_payloads(shell.session_dir)

    if not payloads:
        shell.out.error("No payloads available. Use 'ducky add' to create one, or pass inline text.")
        return None

    shell.console.print(f"\n  [{t.secondary} bold]Available Payloads[/]\n")
    for i, (p, _scope) in enumerate(payloads, 1):
        desc = f" — {p.description}" if p.description else ""
        shell.console.print(f"    [{t.accent}]{i:>3}[/]  {p.name}{desc}")
    shell.console.print()

    try:
        from prompt_toolkit import prompt as pt_prompt

        answer = pt_prompt("  Select payload number (or 'q' to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        shell.console.print()
        return None

    if answer.lower() in ("q", "quit", "cancel", ""):
        return None

    try:
        idx = int(answer) - 1
        if 0 <= idx < len(payloads):
            payload, _scope = payloads[idx]
            shell.console.print(f"  [{t.muted}]Using payload: {payload.name}[/]")
            return payload.text
        else:
            shell.out.error(f"Invalid selection: {answer}")
            return None
    except ValueError:
        shell.out.error(f"Invalid selection: {answer}")
        return None


def prompt_output_path(shell: StudioProtocol, default: str, fmt) -> str | None:
    """Prompt the user for an output path."""
    if shell.json_mode:
        return default

    try:
        from prompt_toolkit import prompt as pt_prompt

        answer = pt_prompt(f"  Save to [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        shell.console.print()
        return None

    return answer if answer else default
