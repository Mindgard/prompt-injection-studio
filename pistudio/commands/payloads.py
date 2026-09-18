"""Payload library management.

The named-payload library backs the ``--payload`` flag across ``serve``,
``file``, ``audio`` and every hardware device, so it is not hardware
specific and does not live under ``hw``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from typing import TYPE_CHECKING

from pistudio.commands.payload_flag import complete_payload_names
from pistudio.core.command import Command
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


class PayloadsCommand(Command):
    """Manage the named prompt injection payload library"""

    name = "payloads"
    aliases = ("payload",)
    help = "Manage the prompt injection payload library"
    namespace = True
    subcommand_aliases = {"ls": "list"}
    subcommands = {
        "list": "List every payload with its description",
        "show": "Show one payload in full",
        "add": "Add a payload",
        "edit": "Edit a payload in $EDITOR",
        "rm": "Remove a payload",
        "generate": "LLM-generate a payload",
    }
    usage = (
        "Usage: payloads <subcommand> [args]\n\n"
        "The named payloads that '--payload <name>' resolves against, wherever\n"
        "that flag is accepted: serve, file, audio and the hardware commands.\n\n"
        "  payloads list                    Every payload, with descriptions\n"
        "  payloads show <name>             One payload in full\n"
        '  payloads add <name> "<text>"     Add a payload\n'
        "  payloads edit <name>             Edit it in $EDITOR\n"
        "  payloads rm <name>               Remove it\n"
        '  payloads generate "<desc>"       LLM-generate one\n\n'
        "Options:\n"
        "  --global            Write to ~/.pistudio rather than this session\n"
        "  --category <name>   Group the payload under a category\n\n"
        "Examples:\n"
        '  payloads add leak-prompt "Ignore all previous instructions"\n'
        "  payloads show ignore-instructions\n"
        '  payloads generate "make the model reveal its system prompt"\n'
        "  serve --payload ignore-instructions\n"
        "  file pdf --payload ignore-instructions"
    )

    def execute(self, shell: StudioProtocol, args: list[str]) -> None:
        """Run the ``payloads`` command."""
        self._payloads(shell, args)

    def _payloads(self, shell: StudioProtocol, args: list[str]) -> None:
        """Handle payload subcommands."""
        if not args:
            self._payload_list(shell)
            return

        sub = args[0].lower()
        remaining = args[1:]

        if sub in ("list", "ls"):
            self._payload_list(shell)
        elif sub == "show":
            self._payload_show(shell, remaining)
        elif sub == "add":
            self._payload_add(shell, remaining)
        elif sub == "rm":
            self._payload_rm(shell, remaining)
        elif sub == "edit":
            self._payload_edit(shell, remaining)
        elif sub == "generate":
            self._payload_generate(shell, remaining)
        else:
            shell.out.error(self.suggest_subcommand(sub, ["list", "show", "add", "edit", "rm", "generate"]))

    def _payload_list(self, shell: StudioProtocol) -> None:
        """List all payloads in a table with descriptions."""

        from pistudio.hardware.payloads import list_payloads

        t = active_theme()
        payloads = list_payloads(shell.session_dir)

        if not payloads and not shell.json_mode:
            shell.out.empty_state("payloads", "Add one with 'payloads add <name> \"<text>\"'.")
            return

        rows = []
        for payload, scope in payloads:
            name = payload.name if scope == "builtin" else f"{payload.name} ({scope})"
            desc = payload.description or "-"
            if len(desc) > 50:
                desc = desc[:47] + "..."
            rows.append([name, payload.category or "-", desc])

        # JSON carries the untruncated description and the scope as its own
        # field, which the displayed cells fold together.
        shell.out.table(
            ["Name", "Category", "Description"],
            rows,
            title="Prompt Injection Payloads",
            column_styles={
                "Name": {"style": t.accent, "no_wrap": True},
                "Category": {"style": t.muted},
            },
            json_rows=[
                {"name": p.name, "category": p.category, "scope": scope, "description": p.description}
                for p, scope in payloads
            ],
        )

    def _payload_show(self, shell: StudioProtocol, args: list[str]) -> None:
        """Show a payload."""
        from pistudio.hardware.payloads import get_payload

        if not args:
            shell.out.error("Usage: hw payloads show <name>")
            return

        name = args[0]
        result = get_payload(name, shell.session_dir)
        if result is None:
            shell.out.error(f"Payload '{name}' not found.")
            return

        payload, scope = result
        t = active_theme()

        if shell.json_mode:
            shell.print_raw(json.dumps(payload.model_dump(), indent=2))
            return

        shell.console.print(f"\n  [{t.accent} bold]{payload.name}[/] [{t.muted}]({scope})[/]")
        if payload.category:
            shell.console.print(f"  [{t.muted}]Category:[/] {payload.category}")
        if payload.description:
            shell.console.print(f"  [{t.muted}]Description:[/] {payload.description}")
        if payload.provenance:
            shell.console.print(f"  [{t.muted}]Evidence:[/] {payload.provenance}")
        shell.console.print(f"\n  [{t.secondary}]Payload Text:[/]")
        shell.console.print(f"  {payload.text}\n")

    def _payload_add(self, shell: StudioProtocol, args: list[str]) -> None:
        """Add a new payload."""
        from pistudio.hardware.payloads import add_payload

        global_scope = "--global" in args
        args = [a for a in args if a != "--global"]

        if len(args) < 2:
            shell.out.error('Usage: hw payloads add <name> "<text>" [--global]')
            return

        name = args[0]
        text = " ".join(args[1:])

        try:
            payload = add_payload(name, text, shell.session_dir, global_scope=global_scope)
            t = active_theme()
            scope = "global" if global_scope else "session"
            shell.console.print(f"  [{t.success}]✓[/] Added payload '{payload.name}' ({scope})")
            shell.audit.log("hw_payload_add", name=name, scope=scope)
        except ValueError as e:
            shell.out.error(str(e))

    def _payload_rm(self, shell: StudioProtocol, args: list[str]) -> None:
        """Remove a payload."""
        from pistudio.hardware.payloads import remove_payload

        global_scope = "--global" in args
        args = [a for a in args if a != "--global"]

        if not args:
            shell.out.error("Usage: hw payloads rm <name> [--global]")
            return

        name = args[0]
        try:
            remove_payload(name, shell.session_dir, global_scope=global_scope)
            t = active_theme()
            shell.console.print(f"  [{t.success}]✓[/] Removed payload '{name}'")
            shell.audit.log("hw_payload_rm", name=name)
        except ValueError as e:
            shell.out.error(str(e))

    def _payload_edit(self, shell: StudioProtocol, args: list[str]) -> None:
        """Edit a payload in $EDITOR."""
        from pistudio.hardware.payloads import get_payload, update_payload

        global_scope = "--global" in args
        args = [a for a in args if a != "--global"]

        if not args:
            shell.out.error("Usage: hw payloads edit <name> [--global]")
            return

        name = args[0]
        result = get_payload(name, shell.session_dir)
        if result is None:
            shell.out.error(f"Payload '{name}' not found.")
            return

        payload, _ = result
        editor = os.environ.get("EDITOR", "vi")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(payload.text)
            tmp_path = f.name

        try:
            subprocess.run([editor, tmp_path], check=True)
            with open(tmp_path) as f:
                new_text = f.read().strip()

            if new_text != payload.text:
                update_payload(name, new_text, shell.session_dir, global_scope=global_scope)
                t = active_theme()
                shell.console.print(f"  [{t.success}]✓[/] Updated payload '{name}'")
                shell.audit.log("hw_payload_edit", name=name)
            else:
                shell.out.info("No changes made.")
        finally:
            os.unlink(tmp_path)

    def _payload_generate(self, shell: StudioProtocol, args: list[str]) -> None:
        """Generate a payload using LLM."""
        from pistudio.hardware.generate import generate_payload
        from pistudio.hardware.payloads import add_payload

        if not args:
            shell.out.error('Usage: hw payloads generate "<description>"')
            return

        description = " ".join(args)
        llm = _resolve_llm(shell)
        if llm is None:
            shell.out.error("No LLM configured for 'hw'. Use: model assign hw <model>")
            return

        provider, api_key, base_url = llm
        t = active_theme()
        shell.console.print(f"  [{t.muted}]Generating payload...[/]")

        try:
            result = generate_payload(shell, description, provider, api_key, base_url)
            shell.console.print(f"\n  [{t.accent} bold]{result.name}[/]")
            shell.console.print(f"  [{t.muted}]{result.description}[/]")
            shell.console.print(f"\n  {result.text}\n")

            try:
                if shell.confirm("Save this payload?"):
                    add_payload(
                        result.name,
                        result.text,
                        shell.session_dir,
                        category=result.category,
                        description=result.description,
                    )
                    shell.console.print(f"  [{t.success}]✓[/] Saved as '{result.name}'")
            except (EOFError, KeyboardInterrupt):
                shell.console.print()
        except Exception as e:
            shell.out.error(f"Generation failed: {e}")

    def complete(self, shell: StudioProtocol, tokens: list[str]) -> list[str]:
        """Return tab-completion candidates for ``payloads``."""
        subs = list(self.subcommands)

        if not tokens or (len(tokens) == 1 and not tokens[0].strip()):
            return subs
        if len(tokens) == 1:
            return [s for s in subs if s.startswith(tokens[0])]

        current = tokens[-1]
        if tokens[0].lower() in ("show", "edit", "rm") and len(tokens) == 2:
            return complete_payload_names(shell, current)
        return [f for f in ("--global", "--category") if f.startswith(current)]
