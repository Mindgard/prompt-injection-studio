"""Theme command — list, preview, and switch color themes.

Seven built-in themes: nord (default), studio, vaporwave, borland,
halflife, matrix, monokai.  The active theme is persisted under the session
directory and re-applied on startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pistudio.core.command import Command
from pistudio.ui.theme import active_theme, all_themes, save_theme_preference, set_active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol


class ThemeCommand(Command):
    """List, preview, and switch the shell color theme."""

    name = "theme"
    aliases = ["themes"]
    help = "List, preview, and switch the shell color theme"
    usage = (
        "Usage:\n"
        "  theme                       List available themes\n"
        "  theme <name>                Switch to a theme\n"
        "  theme preview <name>        Preview without switching\n"
        "\n"
        "Examples:\n"
        "  theme\n"
        "  theme monokai\n"
        "  theme preview nord"
    )

    def execute(self, shell: StudioProtocol, args: list[str]) -> None:
        """Run the ``theme`` command."""
        themes = all_themes()
        current = active_theme()

        # No args or "list" — show available themes
        if not args or args[0] in ("list", "ls"):
            self._list(shell, themes, current)
            return

        # "preview" — show a swatch for a theme without switching
        if args[0] == "preview" and len(args) > 1:
            name = args[1]
            if name not in themes:
                shell.out.error(f"Unknown theme: '{name}'. Available: {', '.join(themes)}")
                return
            self._swatch(shell, themes[name])
            return

        # Switch theme
        name = args[0]
        if name not in themes:
            shell.out.error(f"Unknown theme: '{name}'. Available: {', '.join(themes)}")
            return

        theme = set_active_theme(name)
        save_theme_preference(shell.session_dir, name)
        self._swatch(shell, theme)
        shell.out.success(f"Theme set to '{name}'")

    def _swatch(self, shell: StudioProtocol, theme) -> None:
        """Render a one-line-per-role color swatch for *theme*."""
        roles = (
            ("accent", theme.accent),
            ("secondary", theme.secondary),
            ("success", theme.success),
            ("error", theme.error),
            ("info", theme.info),
            ("warning", theme.warning),
            ("muted", theme.muted),
            ("text", theme.text),
            ("border", theme.border),
        )
        shell.console.print(f"\n  [bold {theme.accent}]{theme.name}[/] — {theme.description}")
        for role, color in roles:
            shell.console.print(f"    [{color}]████[/] [{theme.muted}]{role:<10}[/] {color}")
        shell.console.print("")

    def _list(self, shell: StudioProtocol, themes: dict, current) -> None:
        from pistudio.ui.output import make_table

        t = current
        table = make_table("Themes")
        table.add_column("Name", style=f"bold {t.secondary}", min_width=12)
        table.add_column("Active", justify="left")
        table.add_column("Description", no_wrap=True)

        for name, theme in themes.items():
            active = f"[{t.success}]●[/]" if name == current.name else ""
            table.add_row(name, active, theme.description)

        shell.console.print(table)
        shell.console.print(f"\n  [{t.muted}]Use 'theme <name>' to switch  •  'theme preview <name>' to preview[/]")

    def complete(self, shell: StudioProtocol, tokens: list[str]) -> list[str]:
        """Return tab-completion candidates for ``theme``."""
        names = list(all_themes().keys())
        subcmds = ["list", "ls", "preview"] + names

        if not tokens or (len(tokens) == 1 and not tokens[0].strip()):
            return subcmds
        if len(tokens) == 1:
            return [s for s in subcmds if s.startswith(tokens[0])]
        if len(tokens) == 2 and tokens[0] == "preview":
            return [n for n in names if n.startswith(tokens[1])]
        return []
