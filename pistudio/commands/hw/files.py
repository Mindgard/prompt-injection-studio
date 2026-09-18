"""Bash Bunny file registry — register files for delivery with a payload.

A payload referencing ``{{file:name}}`` is compiled with
``ATTACKMODE HID STORAGE``, and the referenced files are copied to the device
alongside it so the target can open them from the Bunny's mass-storage volume.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.commands.hw.command import HwCommand
    from pistudio.core.protocols import StudioProtocol

_SUBS = ("list", "add", "rm", "show")

_USAGE = """\
Usage: hw files <subcommand> [args]

  list                          List registered files
  add <name> <path>             Register a local file for delivery
  rm <name>                     Unregister a file
  show <name>                   Show a registered file's details

Options:
  --global            Use the global registry instead of this session's
  --description <s>   Human-readable note
  --category <s>      Grouping tag

Reference a registered file from a payload as {{file:<name>}}; 'hw bunny
deploy' then copies it to the device and rewrites the reference to the path
the target will see.

Examples:
  hw files add invoice ~/payloads/invoice.pdf
  hw payloads add lure "Please review {{file:invoice}} and summarise it"
  hw bunny deploy lure --os windows
"""


def handle_files(cmd: HwCommand, shell: StudioProtocol, args: list[str]) -> None:
    """Dispatch a ``hw files`` subcommand.

    Args:
        cmd: The parent ``hw`` command, for shared error helpers.
        shell: The studio context.
        args: Tokens following ``files``.
    """
    if not args:
        shell.out.info(_USAGE)
        return

    sub = args[0].lower()
    rest = args[1:]

    positional: list[str] = []
    flags: dict[str, str] = {}
    global_scope = False
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "--global":
            global_scope = True
        elif tok.startswith("--") and i + 1 < len(rest):
            flags[tok[2:]] = rest[i + 1]
            i += 1
        else:
            positional.append(tok)
        i += 1

    if sub == "list":
        _list(shell)
    elif sub == "add":
        _add(shell, positional, flags, global_scope)
    elif sub in ("rm", "remove", "delete"):
        _remove(shell, positional, global_scope)
    elif sub == "show":
        _show(shell, positional)
    else:
        shell.out.error(cmd.suggest_subcommand(sub, list(_SUBS)))


def _list(shell: StudioProtocol) -> None:
    """Print all registered files."""
    from pistudio.hardware.hak5.bunny_files import _human_size, list_files

    entries = list_files(shell.session_dir)
    if not entries:
        shell.out.empty_state("registered files", "Add one with 'hw files add <name> <path>'.")
        return

    t = active_theme()
    shell.console.print("")
    for bf, scope in entries:
        shell.console.print(
            f"  [bold {t.accent}]{bf.name}[/] [{t.muted}]({scope})[/]  "
            f"{bf.filename}  [{t.muted}]{_human_size(bf.size_bytes)}[/]"
        )
        if bf.description:
            shell.console.print(f"      [{t.muted}]{bf.description}[/]")
    shell.console.print("")


def _add(shell: StudioProtocol, positional: list[str], flags: dict[str, str], global_scope: bool) -> None:
    """Register a local file."""
    from pistudio.hardware.hak5.bunny_files import add_file

    if len(positional) < 2:
        shell.out.usage_error("hw files add <name> <path> [--description <s>] [--category <s>] [--global]")
        return

    name, path = positional[0], positional[1]
    try:
        bf, size_warning = add_file(
            name,
            path,
            shell.session_dir,
            description=flags.get("description", ""),
            category=flags.get("category", ""),
            global_scope=global_scope,
        )
    except (FileNotFoundError, ValueError) as exc:
        shell.out.error(str(exc))
        return

    scope = "global" if global_scope else "session"
    shell.audit.log("hak5_file_add", name=name, path=bf.local_path, scope=scope)
    shell.out.success(f"Registered '{bf.name}' -> {bf.filename} ({scope})")
    if size_warning:
        shell.out.warn(f"{bf.filename} is large; copying it to the device will be slow and may exceed its free space.")
    shell.out.info(f"Reference it from a payload as {{{{file:{bf.name}}}}}")


def _remove(shell: StudioProtocol, positional: list[str], global_scope: bool) -> None:
    """Unregister a file."""
    from pistudio.hardware.hak5.bunny_files import remove_file

    if not positional:
        shell.out.usage_error("hw files rm <name> [--global]")
        return

    name = positional[0]
    try:
        remove_file(name, shell.session_dir, global_scope=global_scope)
    except ValueError as exc:
        shell.out.error(str(exc))
        return

    shell.audit.log("hak5_file_rm", name=name, scope="global" if global_scope else "session")
    shell.out.success(f"Unregistered '{name}'")


def _show(shell: StudioProtocol, positional: list[str]) -> None:
    """Print a registered file's details."""
    import os

    from pistudio.hardware.hak5.bunny_files import _human_size, get_file

    if not positional:
        shell.out.usage_error("hw files show <name>")
        return

    entry = get_file(positional[0], shell.session_dir)
    if entry is None:
        shell.out.not_found("File", positional[0], "hw files list")
        return

    bf, scope = entry
    t = active_theme()
    shell.console.print(f"\n  [bold {t.accent}]{bf.name}[/] [{t.muted}]({scope})[/]")
    rows = [
        ("Local path", bf.local_path),
        ("On device", f"payloads/switchN/files/{bf.filename}"),
        ("Size", _human_size(bf.size_bytes)),
        ("SHA-256", bf.sha256),
        ("Category", bf.category or "—"),
        ("Description", bf.description or "—"),
    ]
    for key, value in rows:
        shell.console.print(f"    [{t.muted}]{key:12}[/] {value}")
    if not os.path.isfile(bf.local_path):
        shell.out.warn("The source file no longer exists; deploying will fail until it is re-registered.")
    shell.console.print("")


def complete_files(tokens: list[str], session_dir: str = "") -> list[str]:
    """Return completions for ``hw files``."""
    if not tokens or (len(tokens) == 1 and not tokens[0].strip()):
        return list(_SUBS)
    if len(tokens) == 1:
        return [s for s in _SUBS if s.startswith(tokens[0])]

    current = tokens[-1]
    if tokens[0] in ("rm", "remove", "delete", "show") and len(tokens) == 2:
        from pistudio.hardware.hak5.bunny_files import file_names

        return [n for n in file_names(session_dir) if n.startswith(current)]

    return [f for f in ("--global", "--description", "--category") if f.startswith(current)]
