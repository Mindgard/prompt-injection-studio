"""Interactive session.

A payload server started with ``serve`` is an in-process singleton, so
running the studio as one-shot CLI calls loses it between steps.  The REPL
keeps it alive across a whole session, which is what makes multi-step work
(host a payload, then deliver it over hardware) practical.

Commands that declare ``namespace = True`` can be entered as a context, so
``hw`` gives an ``hw>`` prompt where ``devices`` works without repeating the
prefix.  ``back`` leaves one level, ``/`` or ``exit`` returns to the root.

Deliberately minimal otherwise: no escape prefixes, aliases, background jobs
or hooks — those belong to the shell this was extracted from.
"""

from __future__ import annotations

import shlex

from pistudio.core.protocols import StudioProtocol

__all__ = ["run_repl"]

_TAGLINE = """\
First time here? Run 'tutorial'.  'help' (or '?') lists commands, 'exit' leaves.
For authorised testing only.
"""

# The shared logo is 65 columns including its two-space pad; below this the
# art wraps into noise, so the plain heading reads better.  Measured from the
# art rather than guessed, so it stays right if the art changes.
_LOGO_MIN_WIDTH = 68

_EXIT_WORDS = frozenset({"exit", "quit", ":q"})
# `?` is what people type first in an unfamiliar prompt, and the nested flipper
# console already accepted it.
_HELP_WORDS = frozenset({"help", "?"})
_LIST_WORDS = frozenset({"ls", "dir"})
_UP_WORDS = frozenset({"back", "..", "up"})
_ROOT_WORDS = frozenset({"/", "~"})


def _print_banner(studio: StudioProtocol, version: str) -> None:
    """Draw the themed logo above the tagline.

    Every theme has carried a six-line ASCII logo since the shell this was
    extracted from, and none of them was ever rendered -- the REPL printed a
    plain text line instead.  Shown only here: a banner on ``pistudio --json
    payloads list`` would be noise in front of the data.

    Falls back to the plain heading when there is no logo to draw, when colour
    is off (``--plain``, ``NO_COLOR``, ``TERM=dumb``), or when the terminal is
    too narrow for the art to survive wrapping.
    """
    t = _theme()
    logo = getattr(t, "logo", "")
    width = getattr(studio.console, "width", 80)
    plain = studio.plain_mode or studio.json_mode or getattr(studio.console, "no_color", False)

    settings = getattr(studio, "settings", None)
    wanted = settings.get("ui.banner") if settings is not None else True

    if logo and wanted and not plain and width >= _LOGO_MIN_WIDTH:
        studio.console.print()
        studio.console.print(logo, highlight=False)
        subtitle = (
            f"  [{t.muted}]{t.subtitle_left}[/] [{t.secondary}]Prompt Injection Studio {version}[/]"
            f" [{t.muted}]{t.subtitle_right}[/]\n"
        )
        # highlight=False throughout: Rich's auto-highlighter renders the
        # version as a number literal and the quoted words in the tagline as
        # strings, which fights the theme.
        studio.console.print(subtitle, highlight=False)
    else:
        studio.console.print(f"Prompt Injection Studio {version}", highlight=False)
    studio.console.print(_TAGLINE, highlight=False)


def _theme():
    from pistudio.ui.theme import active_theme

    return active_theme()


def for_context(text: str, context: list[str]) -> str:
    """Strip the prefix *context* already implies from usage *text*.

    Usage strings are written for the command line (``file pdf ...``), but
    inside a ``file>`` context that prefix is redundant and reads as a second
    command to type.  Longest prefix first, so a nested context is removed
    before its parent.
    """
    if not context:
        return text
    for depth in range(len(context), 0, -1):
        prefix = " ".join(context[:depth]) + " "
        text = text.replace(prefix, "")
    return text


def _resolve_context(context: list[str]):
    """Return the Command owning the deepest entered context, or None."""
    from pistudio.commands import get_nested_command

    return get_nested_command(context)


def examples_from(usage: str, limit: int = 4) -> list[str]:
    """Pull the ``Examples:`` block out of *usage*.

    The block ends at the first blank line or unindented paragraph, so the
    safety notes that follow it in several commands are not mistaken for
    commands to run.
    """
    lines = usage.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "Examples:")
    except StopIteration:
        return []

    found: list[str] = []
    for line in lines[start + 1 :]:
        if not line.strip():
            break
        if not line.startswith(" "):
            break
        found.append(line.strip())
        if len(found) >= limit:
            break
    return found


def _print_examples(studio: StudioProtocol, cmd, context: list[str]) -> None:
    """Show runnable examples, rewritten for the level the user is at.

    A help screen that lists ``hw flipper deploy-all x`` while the prompt says
    ``hw>`` is showing something that will not run: typing it there resolves to
    ``hw hw flipper ...``.  ``for_context`` strips the prefix the context
    already supplies, so every line can be pasted as-is.
    """
    examples = examples_from(cmd.usage or "")
    if not examples:
        return
    t = _theme()
    studio.console.print(f"\n  [bold {t.accent}]Try[/]")
    for example in examples:
        studio.console.print(f"    [{t.secondary}]{for_context(example, context)}[/]")


def _print_root_help(studio: StudioProtocol) -> None:
    """List top-level commands."""
    from pistudio.commands import all_commands

    t = _theme()
    studio.console.print(f"\n  [bold {t.accent}]Commands[/]")
    for cmd in all_commands():
        if cmd.dev:
            continue
        studio.console.print(f"    [{t.secondary}]{cmd.name:<10}[/] [{t.muted}]{cmd.help}[/]")
    studio.console.print(f"\n  [bold {t.accent}]Try[/]")
    for example in ("tutorial", 'serve "Ignore all previous instructions"', "payloads list", "hw devices"):
        studio.console.print(f"    [{t.secondary}]{example}[/]")
    studio.console.print(
        f"\n  [{t.muted}]Enter a command with no arguments to open it as a context.\n"
        f"  'help <command>' for its usage, 'tutorial' for a guided walkthrough.[/]\n"
    )


def _print_context_help(studio: StudioProtocol, context: list[str]) -> None:
    """List the subcommands available in the current context."""
    cmd = _resolve_context(context)
    t = _theme()

    if cmd is None:
        _print_root_help(studio)
        return

    subs = getattr(cmd, "subcommands", None) or {}
    aliases = getattr(cmd, "subcommand_aliases", None) or {}
    studio.console.print(f"\n  [bold {t.accent}]{'/'.join(context)}[/] [{t.muted}]{cmd.help}[/]")
    if subs:
        # Aliases are shown beside the verb they stand for rather than as their
        # own rows, so the listing says each thing once.  Only ASCII aliases:
        # the emoji shortcuts are double-width, so padding computed with len()
        # misaligns every row after one, and they are already visible in the
        # description column.
        rows = []
        for name, help_text in subs.items():
            also = [a for a, target in aliases.items() if target == name and a.isascii()]
            rows.append((f"{name} ({', '.join(also)})" if also else name, help_text))
        pad = max(len(label) for label, _ in rows) + 2
        for label, help_text in rows:
            studio.console.print(f"    [{t.secondary}]{label.ljust(pad)}[/][{t.muted}]{help_text}[/]")
    else:
        studio.console.print(f"    [{t.muted}](see 'help {context[0]}' for full usage)[/]")
    _print_examples(studio, cmd, context)
    studio.console.print(f"\n  [{t.muted}]'back' up a level, '/' to the root, 'help <sub>' for detail.[/]\n")


def _print_subcommand_help(studio: StudioProtocol, parent, sub: str, context: list[str]) -> None:
    """Describe *sub* using its parent's declared help and usage text.

    Running the subcommand to make it print its own usage is what this used
    to do, and it was wrong: ``help add`` inside ``payloads>`` would open the
    interactive payload picker and block, and ``help serve`` would start a
    server.  Help must not have side effects.
    """
    t = _theme()
    description = (getattr(parent, "subcommands", None) or {}).get(sub, "")

    studio.console.print(f"\n  [bold {t.accent}]{parent.name} {sub}[/] [{t.muted}]{description}[/]")

    # Surface the lines of the parent's usage that mention this subcommand —
    # that is where its arguments and flags are actually written down.
    lines = [
        line.rstrip() for line in (parent.usage or "").splitlines() if _mentions_subcommand(line, parent.name, sub)
    ]
    if lines:
        studio.console.print()
        for line in lines:
            studio.console.print(f"  {for_context(line, context)}")

    # Examples that actually exercise this subcommand, so `help add` inside
    # `payloads>` shows `add ...` rather than the parent's whole example block.
    relevant = [e for e in examples_from(parent.usage or "", limit=50) if _mentions_subcommand(e, parent.name, sub)]
    if relevant:
        studio.console.print(f"\n  [bold {t.accent}]Try[/]")
        for example in relevant[:4]:
            studio.console.print(f"    [{t.secondary}]{for_context(example, context)}[/]")

    studio.console.print(f"\n  [{t.muted}]'help {parent.name}' for the whole command.[/]\n")


def _mentions_subcommand(line: str, parent: str, sub: str) -> bool:
    """Return True when *line* of usage text documents ``parent sub``."""
    stripped = line.strip()
    return stripped.startswith(f"{parent} {sub} ") or stripped.startswith(f"{sub} ")


def _enters_context(context: list[str], token: str) -> list[str] | None:
    """Return the new context if *token* opens one from *context*, else None.

    A bare command name opens a context when that command declares
    ``namespace = True``; from inside a context, a bare subcommand name does
    the same if the subcommand is itself a namespace.
    """
    from pistudio.commands import get_command, get_nested_command

    if not context:
        cmd = get_command(token)
        if cmd is not None and getattr(cmd, "namespace", False):
            return [cmd.name]
        return None

    # Inside a context: only descend into declared subcommands that are
    # themselves namespaces.
    parent = _resolve_context(context)
    subs = getattr(parent, "subcommands", None) or {}
    if token not in subs:
        return None
    sub_cmd = get_nested_command([*context, token])
    if sub_cmd is not None and getattr(sub_cmd, "namespace", False):
        return [*context, token]
    return None


def _dispatch(studio: StudioProtocol, context: list[str], line: str) -> list[str]:
    """Run one input line.  Returns the (possibly changed) context."""
    from pistudio.commands import get_command

    try:
        tokens = shlex.split(line)
    except ValueError as exc:
        studio.out.error(f"Could not parse input: {exc}")
        return context
    if not tokens:
        return context

    head, rest = tokens[0], tokens[1:]

    if head in _ROOT_WORDS:
        return []
    if head in _UP_WORDS:
        return context[:-1]
    # Only at the root: inside a context `ls` is already the `list` alias for
    # that command, which is the more specific meaning and wins.  The REPL
    # borrows `cd`-style navigation (`..`, `/`, `~`), so `ls` for "what is
    # here" is the affordance a shell user reaches for next.
    if not context and head in _LIST_WORDS and not rest:
        _print_root_help(studio)
        return context
    if head in _HELP_WORDS:
        if not rest:
            _print_context_help(studio, context)
            return context

        # The current context is the narrower scope, so it wins: inside `hw>`,
        # `help files` describes `hw files`, not the top-level `file` command
        # that happens to answer to the alias `files`.
        parent = _resolve_context(context)
        if parent is not None:
            # An alias asks about the verb it stands for, so `help ls` inside
            # `payloads>` describes `list` rather than reporting no help.
            sub = (getattr(parent, "subcommand_aliases", None) or {}).get(rest[0], rest[0])
            if sub in (getattr(parent, "subcommands", None) or {}):
                _print_subcommand_help(studio, parent, sub, context)
                return context

        target = get_command(rest[0]) or _resolve_context([*context, rest[0]])
        if target is not None:
            studio.out.info(for_context(target.usage or target.help, context))
            return context

        studio.out.error(f"No help for '{rest[0]}'. Type 'help' to see what is available here.")
        return context

    # A bare namespace name descends a level rather than running anything.
    # Entering silently left the user at a `file>` prompt with no idea what it
    # accepts, so show the same listing `help` would.
    if not rest and (deeper := _enters_context(context, head)) is not None:
        _print_context_help(studio, deeper)
        return deeper

    # Otherwise run it. The command receives everything after its own name,
    # with the entered context prepended so `devices` inside inject/hw becomes
    # the `["hw", "devices"]` that HwCommand expects.
    if context:
        root_name = context[0]
        argv = [*context[1:], head, *rest]
    else:
        root_name = head
        argv = rest

    cmd = get_command(root_name)
    if cmd is None:
        studio.out.error(_unknown_command_message(root_name))
        return context

    # `--help` is answered by the dispatcher on both surfaces, so `barcode
    # --help` means the same thing typed here as it does on the command line.
    from pistudio.core.command import wants_help

    if wants_help(argv):
        studio.out.info(for_context(cmd.usage or cmd.help, context))
        return context

    cmd.execute(studio, argv)
    return context


def _unknown_command_message(name: str) -> str:
    """Build the error for an unrecognised command, suggesting a near match.

    Subcommands already got 'did you mean?' via ``Command.suggest_subcommand``
    while top-level typos got a bare pointer to ``help``, so ``serv`` was less
    helpful than ``payloads> shwo``.
    """
    import difflib

    from pistudio.commands import visible_command_names

    matches = difflib.get_close_matches(name, visible_command_names(), n=1, cutoff=0.6)
    hint = f" Did you mean '{matches[0]}'?" if matches else ""
    return f"Unknown command: '{name}'.{hint} Type 'help' for the command list."


def run_repl(studio: StudioProtocol | None = None) -> int:
    """Run the interactive loop until the user exits.

    Args:
        studio: Context to run in.  A default one is created when omitted.

    Returns:
        The process exit code.
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory

    from pistudio import __version__
    from pistudio.commands import register_all_commands
    from pistudio.ui.completer import ShellCompleter

    if studio is None:
        from pistudio.core.studio import Studio

        studio = Studio()

    register_all_commands()
    _print_banner(studio, __version__)

    session: PromptSession = PromptSession(
        history=FileHistory(f"{studio.session_dir}/history"),
        completer=ShellCompleter(studio),
        complete_while_typing=False,
    )
    # Commands reach for shell.session to confirm before writing to hardware.
    studio.session = session

    context: list[str] = []
    while True:
        studio.namespace_context = context[-1] if context else None
        prompt = f"{'/'.join(context)}> " if context else f"{_theme().prompt_separator} "

        try:
            line = session.prompt(prompt).strip()
        except KeyboardInterrupt:
            # Ctrl+C cancels the current line, it does not end the session.
            continue
        except EOFError:
            break

        if not line:
            continue
        if line in _EXIT_WORDS:
            # From inside a context, exit leaves the context first.
            if context:
                context = []
                continue
            break

        try:
            context = _dispatch(studio, context, line)
        except KeyboardInterrupt:
            studio.out.warn("Interrupted")
        except (OSError, RuntimeError, ValueError) as exc:
            studio.out.error(str(exc))

    studio.console.print(_theme().goodbye_message)
    return studio.exit_code
