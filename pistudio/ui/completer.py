"""Dynamic tab completion for the interactive session."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from pistudio.commands import get_command, visible_command_names

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol


@dataclass
class CompletionItem:
    """A completion candidate with optional metadata for styling and description.

    Attributes:
        text: The completion text to insert.
        description: Short description shown in the completion dropdown.
        category: Category for styling: "command", "subcommand", "flag", "argument", "path".
    """

    text: str
    description: str = ""
    category: str = ""  # command, subcommand, flag, argument, path

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.text == other
        if isinstance(other, CompletionItem):
            return self.text == other.text and self.description == other.description and self.category == other.category
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.text, self.description, self.category))


def _get_completion_style(category: str) -> str:
    """Return prompt_toolkit style string for a completion category."""
    from pistudio.ui.theme import active_theme

    t = active_theme()
    styles = {
        "command": f"fg:{t.completion_command}",
        "subcommand": f"fg:{t.completion_subcommand}",
        "flag": f"fg:{t.completion_flag}",
        "argument": f"fg:{t.completion_argument}",
        "path": f"fg:{t.completion_path}",
    }
    return styles.get(category, "")


class ShellCompleter(Completer):
    """Context-aware completer that delegates to individual commands."""

    def __init__(self, shell: StudioProtocol):
        """Bind the completer to *shell* for command and context lookups."""
        self.shell = shell

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        """Yield completions for the current cursor position.

        Completion strategy:

        1. If the user is still typing the first token, complete command
           names and aliases.
        2. If the previous token is a file-expecting flag (declared in
           ``Command.file_args``), complete file paths.
        3. If the command declares ``wants_path_completion()`` for the
           current token position, complete file paths.
        4. Otherwise, delegate to the command's ``complete()`` method
           for context-aware subcommand/argument completions.
        """
        text = document.text_before_cursor
        tokens = text.split()

        ns_ctx = getattr(self.shell, "namespace_context", None)

        # If empty or still typing the first token, complete command names + aliases
        if not tokens or (len(tokens) == 1 and not text.endswith(" ")):
            prefix = tokens[0] if tokens else ""

            # Inside a namespace: prioritize subcommand names, then top-level
            if ns_ctx:
                ns_cmd = get_command(ns_ctx)
                if ns_cmd and getattr(ns_cmd, "subcommands", None):
                    for sub_name, sub_help in ns_cmd.subcommands.items():
                        if sub_name.startswith(prefix):
                            yield Completion(
                                sub_name,
                                start_position=-len(prefix),
                                display_meta=sub_help,
                                style=_get_completion_style("subcommand"),
                            )
                # Aliases complete too, labelled so the canonical name is
                # visible.  Before they were declared, `ls` and the emoji
                # shortcuts worked but appeared nowhere.
                for alias, target in (getattr(ns_cmd, "subcommand_aliases", None) or {}).items():
                    if alias.startswith(prefix):
                        yield Completion(
                            alias,
                            start_position=-len(prefix),
                            display_meta=f"alias for {target}",
                            style=_get_completion_style("subcommand"),
                        )
                # Also include "back" for exiting the namespace
                if "back".startswith(prefix):
                    yield Completion(
                        "back",
                        start_position=-len(prefix),
                        display_meta="Return to root",
                        style=_get_completion_style("command"),
                    )
            elif "ls".startswith(prefix):
                # At the root, `ls` lists the commands.  Offered only here:
                # inside a namespace it is that command's `list` alias.
                yield Completion(
                    "ls",
                    start_position=-len(prefix),
                    display_meta="List the commands",
                    style=_get_completion_style("command"),
                )

            vis_names = visible_command_names()
            # Skip subcommand names we already yielded above
            ns_subs = set()
            if ns_ctx:
                ns_cmd = get_command(ns_ctx)
                if ns_cmd and getattr(ns_cmd, "subcommands", None):
                    ns_subs = set(ns_cmd.subcommands)
            for name in vis_names:
                if name.startswith(prefix) and name not in ns_subs:
                    cmd = get_command(name)
                    desc = cmd.help if cmd else ""
                    yield Completion(
                        name,
                        start_position=-len(prefix),
                        display_meta=desc,
                        style=_get_completion_style("command"),
                    )
            return

        # Inside namespace: if first token isn't a top-level command, prepend
        # namespace so the command's completer works correctly.
        cmd_name = tokens[0]
        cmd = get_command(cmd_name)
        if cmd is None and ns_ctx:
            # Prepend namespace for delegation to the namespace command's completer
            cmd = get_command(ns_ctx)
            if cmd is not None:
                tokens = [ns_ctx] + tokens
                text = ns_ctx + " " + text
        if cmd is None:
            return

        # Build the sub-tokens the command sees (everything after cmd name)
        sub_tokens = tokens[1:]

        # Check if the previous token is a file-expecting flag (e.g. --output)
        if cmd.file_args and len(tokens) >= 2:
            prev_token = tokens[-1] if text.endswith(" ") else (tokens[-2] if len(tokens) >= 2 else "")
            if prev_token in cmd.file_args:
                prefix = "" if text.endswith(" ") else tokens[-1]
                yield from _complete_path_styled(prefix)
                return

        # Check if the command wants positional path completion (e.g. target load <path>)
        if cmd.wants_path_completion(sub_tokens if text.endswith(" ") else sub_tokens[:-1] if sub_tokens else []):
            prefix = "" if text.endswith(" ") else (tokens[-1] if len(tokens) > 1 else "")
            yield from _complete_path_styled(prefix)
            return

        # Pass remaining tokens for sub-completion
        # If text ends with space, append empty string so command knows user is starting new token
        if text.endswith(" "):
            sub_tokens = sub_tokens + [""]
        current_prefix = "" if text.endswith(" ") else (tokens[-1] if len(tokens) > 1 else "")

        candidates = cmd.complete(self.shell, sub_tokens)
        for candidate in candidates:
            # Handle both str and CompletionItem
            if isinstance(candidate, CompletionItem):
                if candidate.text.startswith(current_prefix):
                    yield Completion(
                        candidate.text,
                        start_position=-len(current_prefix),
                        display_meta=candidate.description,
                        style=_get_completion_style(candidate.category),
                    )
            elif isinstance(candidate, str) and candidate.startswith(current_prefix):
                # Infer category from text pattern
                if candidate.startswith("--"):
                    cat = "flag"
                    # Check for flag description
                    desc = cmd.flag_descriptions.get(candidate, "") if hasattr(cmd, "flag_descriptions") else ""
                elif candidate.startswith("-"):
                    cat = "flag"
                    desc = ""
                else:
                    cat = "subcommand"
                    desc = ""
                yield Completion(
                    candidate,
                    start_position=-len(current_prefix),
                    display_meta=desc,
                    style=_get_completion_style(cat),
                )


def _complete_path_styled(prefix: str):
    """Yield styled ``Completion`` objects for file/directory paths."""
    if not prefix:
        search_dir = "."
        partial = ""
    else:
        expanded = os.path.expanduser(prefix)
        if os.path.isdir(expanded):
            search_dir = expanded
            partial = ""
        else:
            search_dir = os.path.dirname(expanded) or "."
            partial = os.path.basename(expanded)

    try:
        entries = os.listdir(search_dir)
    except OSError:
        return

    style = _get_completion_style("path")
    for entry in sorted(entries):
        if entry.startswith(".") and not partial.startswith("."):
            continue
        if entry.lower().startswith(partial.lower()):
            full = os.path.join(search_dir, entry)
            completion_text = entry
            is_dir = os.path.isdir(full)

            if is_dir:
                completion_text += "/"

            yield Completion(
                completion_text,
                start_position=-len(partial),
                display_meta="directory" if is_dir else "file",
                style=style,
            )
