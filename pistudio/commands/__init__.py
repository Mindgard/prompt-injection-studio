"""Command registry.

Commands register themselves here so the CLI dispatcher and the REPL's
tab-completer can find them by name or alias.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pistudio.core.command import Command

__all__ = [
    "all_commands",
    "get_nested_command",
    "get_command",
    "register",
    "register_all_commands",
    "visible_command_names",
]

_registry: dict[str, Command] = {}


def register(cmd: Command) -> None:
    """Register *cmd* under its name and every alias."""
    _registry[cmd.name] = cmd
    for alias in cmd.aliases:
        _registry[alias] = cmd


def get_command(name: str) -> Command | None:
    """Look up a command by name or alias."""
    return _registry.get(name)


def all_commands() -> list[Command]:
    """Return every registered command, de-duplicated and sorted by name."""
    return sorted(set(_registry.values()), key=lambda c: c.name)


def visible_command_names() -> list[str]:
    """Return canonical names of commands shown in help and completion."""
    return [c.name for c in all_commands() if not c.dev]


def get_nested_command(path: list[str]) -> Command | None:
    """Resolve a command by its REPL context path.

    Every command is top-level, so a context is one level deep and this is a
    registry lookup.  Kept as its own function because the REPL asks about
    paths, not names, and a deeper hierarchy would be resolved here.
    """
    if len(path) != 1:
        return None
    return get_command(path[0])


def register_all_commands() -> None:
    """Import and register the built-in commands.  Idempotent."""
    if _registry:
        return

    from pistudio.commands.audio_cmd import AudioCommand
    from pistudio.commands.barcode_cmd import BarcodeCommand
    from pistudio.commands.encode_cmd import EncodeCommand
    from pistudio.commands.files import EmbedCommand
    from pistudio.commands.hw.command import HwCommand
    from pistudio.commands.payloads import PayloadsCommand
    from pistudio.commands.serve import ServeCommand
    from pistudio.commands.settings_cmd import SettingsCommand
    from pistudio.commands.theme import ThemeCommand
    from pistudio.commands.tutorial import TutorialCommand

    for cmd in (
        ServeCommand(),
        EmbedCommand(),
        AudioCommand(),
        BarcodeCommand(),
        EncodeCommand(),
        HwCommand(),
        PayloadsCommand(),
        SettingsCommand(),
        ThemeCommand(),
        TutorialCommand(),
    ):
        register(cmd)
