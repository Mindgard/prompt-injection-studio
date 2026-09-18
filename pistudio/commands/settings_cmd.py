"""The ``settings`` command — read and write persisted preferences.

Preferences used to be one flat file per value, with ``theme`` the only one
that had a command.  There was no way to see what could be configured, and
each new preference meant another bespoke read/write pair.

Everything here is derived from the schema in :mod:`pistudio.core.settings`:
the listing, the completion, the validation and the file.  Adding a preference
is one entry in ``SETTINGS`` and nothing else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pistudio.core.command import Command
from pistudio.core.settings import SETTINGS, Settings, choices_for, settings_path
from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol


class SettingsCommand(Command):
    """Show and change persisted preferences"""

    name = "settings"
    aliases = ("config", "set")
    help = "Show and change persisted preferences"
    namespace = True
    subcommand_aliases = {"ls": "list", "show": "list", "unset": "reset"}
    subcommands = {
        "list": "Show every setting, its value, and where that value came from",
        "get": "Print one setting's value",
        "set": "Change a setting and save it",
        "detect": "Fill in printer and serial port from what is attached",
        "reset": "Drop a setting, restoring its default",
        "path": "Print the settings file location",
        "edit": "Open the settings file in $EDITOR",
    }

    @property
    def usage(self) -> str:
        """Usage, with the settings table rendered from the schema."""
        rows = "".join(f"  {s.key:<22} {s.type_name:<7} {s.help}\n" for s in SETTINGS)
        return (
            "Usage: settings [subcommand] [args]\n\n"
            "Preferences persist to a TOML file you can also edit by hand.\n"
            "Run with no arguments to see everything.\n\n"
            "  settings                  Show every setting and its value\n"
            "  settings get <key>        Print one value\n"
            "  settings set <key> <val>  Change one and save it\n"
            "  settings detect           Fill in the printer and serial port\n"
            "  settings reset <key>      Restore the default\n"
            "  settings path             Where the file lives\n"
            "  settings edit             Open it in $EDITOR\n\n"
            "Settings:\n" + rows + "\n"
            "A command-line flag always wins over the stored value, so\n"
            "'--plain' still works when output.mode is 'rich'.\n\n"
            "print.printer and uart.port are discovered from the host: they\n"
            "tab-complete with what is attached, and 'settings detect' fills\n"
            "them in when there is only one candidate.\n\n"
            "Examples:\n"
            "  settings\n"
            "  settings detect\n"
            "  settings set ui.theme matrix\n"
            "  settings set ui.banner false\n"
            "  settings set serve.port 9090\n"
            "  settings get output.mode\n"
            "  settings reset ui.theme\n"
            "  settings path"
        )

    def execute(self, shell: StudioProtocol, args: list[str]) -> None:
        """Run the ``settings`` command."""
        if not args:
            self._list(shell)
            return

        sub = args[0].lower()
        sub = self.subcommand_aliases.get(sub, sub)
        rest = args[1:]

        if sub == "list":
            self._list(shell)
        elif sub == "get":
            self._get(shell, rest)
        elif sub == "set":
            self._set(shell, rest)
        elif sub == "detect":
            self._detect(shell)
        elif sub == "reset":
            self._reset(shell, rest)
        elif sub == "path":
            shell.out.plain(str(settings_path(shell.session_dir)))
        elif sub == "edit":
            self._edit(shell)
        else:
            shell.out.error(self.suggest_subcommand(sub, list(self.subcommands)))

    # ── Subcommands ───────────────────────────────────────────────

    def _list(self, shell: StudioProtocol) -> None:
        settings = Settings(shell.session_dir)
        t = active_theme()

        from pistudio.core.settings import DISCOVERABLE, detected_for

        rows = []
        detected_any = False
        for spec in SETTINGS:
            value = settings.get(spec.key)
            # Saying where a value came from is the difference between "this is
            # configured" and "this happens to be the default".
            origin = "set" if settings.is_set(spec.key) else "default"
            shown = _render(value)

            # An unset printer or port shows what is attached, so the listing
            # answers "what could I put here?" without a second command.
            if spec.key in DISCOVERABLE and not settings.is_set(spec.key):
                found = detected_for(spec.key)
                if found:
                    detected_any = True
                    origin = "detected"
                    shown = found[0] if len(found) == 1 else f"{len(found)} found"
            rows.append([spec.key, shown, origin, spec.help])

        shell.out.table(
            ["Setting", "Value", "Origin", "Description"],
            rows,
            title="Settings",
            column_styles={
                "Setting": {"style": t.accent, "no_wrap": True},
                "Value": {"no_wrap": True},
                "Origin": {"style": t.muted, "no_wrap": True},
                "Description": {"style": t.muted},
            },
            json_rows=[
                {
                    "key": s.key,
                    "value": settings.get(s.key),
                    "default": s.default,
                    "is_set": settings.is_set(s.key),
                    "type": s.type_name,
                    "description": s.help,
                }
                for s in SETTINGS
            ],
        )
        if shell.json_mode or shell.plain_mode:
            return
        shell.console.print(f"  [{t.muted}]{settings.path}[/]")
        shell.console.print(f"  [{t.muted}]Change one with: settings set <key> <value>[/]")
        if detected_any:
            shell.console.print(f"  [{t.muted}]'settings detect' fills in what is attached[/]")
        shell.console.print()

    def _get(self, shell: StudioProtocol, args: list[str]) -> None:
        if not args:
            shell.out.error("Usage: settings get <key>")
            return
        settings = Settings(shell.session_dir)
        try:
            # Printed bare, so `settings get serve.port` is usable in a script.
            shell.out.plain(_render(settings.get(args[0])))
        except KeyError:
            shell.out.error(_unknown_key(args[0]))

    def _set(self, shell: StudioProtocol, args: list[str]) -> None:
        if len(args) < 2:
            shell.out.error("Usage: settings set <key> <value>")
            return

        key, raw = args[0], " ".join(args[1:])
        settings = Settings(shell.session_dir)
        try:
            value = settings.set(key, raw)
        except KeyError:
            shell.out.error(_unknown_key(key))
            return
        except ValueError as exc:
            shell.out.error(str(exc))
            return

        shell.out.success(f"{key} = {_render(value)}")
        self._apply_now(shell, key, value)

    def _detect(self, shell: StudioProtocol) -> None:
        """Fill in the settings the host can discover for itself.

        Copying a device path out of ``lpstat`` or ``ls /dev`` is the least
        interesting part of setting up a workbench.  A single candidate is
        applied; several are listed, because guessing between two printers or
        two cables is how a payload reaches the wrong target.
        """
        from pistudio.core.settings import DISCOVERABLE, detected_for

        settings = Settings(shell.session_dir)
        t = active_theme()
        report: list[dict[str, object]] = []

        for key, (noun, _) in DISCOVERABLE.items():
            found = detected_for(key)
            current = settings.get(key)
            entry: dict[str, object] = {"key": key, "detected": list(found), "value": current}

            if not found:
                entry["action"] = "none found"
            elif settings.is_set(key) and current in found:
                entry["action"] = "already set"
            elif len(found) == 1:
                settings.set(key, found[0])
                entry["action"] = "set"
                entry["value"] = found[0]
            else:
                entry["action"] = "ambiguous"
            report.append(entry)

            if shell.json_mode:
                continue

            label = f"{noun:<12}"
            if entry["action"] == "set":
                shell.out.success(f"{key} = {found[0]}")
            elif entry["action"] == "already set":
                shell.console.print(f"  [{t.muted}]{label} already set to {current}[/]")
            elif entry["action"] == "ambiguous":
                shell.console.print(f"  [{t.warning}]{len(found)} {noun}s found — pick one:[/]")
                for candidate in found:
                    shell.console.print(f"    [{t.accent}]settings set {key} {candidate}[/]")
            else:
                shell.console.print(f"  [{t.muted}]no {noun} detected[/]")

        if shell.json_mode:
            shell.out.result(report)
            return
        shell.console.print(f"\n  [{t.muted}]Tab-complete the value: 'settings set <key> <TAB>'[/]\n")

    def _reset(self, shell: StudioProtocol, args: list[str]) -> None:
        if not args:
            shell.out.error("Usage: settings reset <key>")
            return
        key = args[0]
        settings = Settings(shell.session_dir)
        try:
            settings.unset(key)
        except KeyError:
            shell.out.error(_unknown_key(key))
            return
        shell.out.success(f"{key} restored to {_render(settings.get(key))}")
        self._apply_now(shell, key, settings.get(key))

    def _edit(self, shell: StudioProtocol) -> None:
        import subprocess

        from pistudio.ui.output import resolve_editor

        path = settings_path(shell.session_dir)
        if not path.exists():
            # Write the defaults first, so the editor opens something with
            # every key in it rather than an empty buffer.
            Settings(shell.session_dir).save()
        try:
            subprocess.run([resolve_editor(), str(path)], check=False)
        except OSError as exc:
            shell.out.error(f"Could not open {path}: {exc}")
            return
        shell.out.success(f"Saved {path}")

    @staticmethod
    def _apply_now(shell: StudioProtocol, key: str, value: object) -> None:
        """Make a change take effect in this session, not just the next one."""
        if key == "ui.theme" and isinstance(value, str):
            import contextlib

            from pistudio.ui.theme import set_active_theme

            # The value was validated against the registry on the way in, so a
            # KeyError here means the theme vanished mid-session; the stored
            # preference still stands for next time.
            with contextlib.suppress(KeyError):
                set_active_theme(value)
        elif key == "safety.assume_yes" and isinstance(value, bool):
            shell.assume_yes = value

    # ── Tab completion ────────────────────────────────────────────

    def complete(self, shell: StudioProtocol, tokens: list[str]) -> list[str]:
        """Complete subcommands, then setting keys, then their values."""
        if len(tokens) <= 1:
            return [*self.subcommands, *self.subcommand_aliases]

        sub = self.subcommand_aliases.get(tokens[0], tokens[0])
        if sub in ("get", "set", "reset") and len(tokens) == 2:
            return [s.key for s in SETTINGS]
        if sub == "set" and len(tokens) == 3:
            allowed = choices_for(tokens[1])
            if allowed:
                return list(allowed)
            spec = next((s for s in SETTINGS if s.key == tokens[1]), None)
            if spec is not None and isinstance(spec.default, bool):
                return ["true", "false"]
        return []


def _render(value: object) -> str:
    """Show a value the way the file spells it, so it can be pasted back."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _unknown_key(key: str) -> str:
    """Name the closest setting, as the rest of the tool does for a typo."""
    import difflib

    known = [s.key for s in SETTINGS]
    matches = difflib.get_close_matches(key, known, n=1, cutoff=0.5)
    hint = f" Did you mean '{matches[0]}'?" if matches else ""
    return f"Unknown setting: '{key}'.{hint} Run 'settings' to see them all."
