"""Persisted preferences, in one file the user and an agent can both edit.

Preferences had accumulated as one flat file per setting -- ``theme.txt`` was
the only one, but the pattern does not scale past it, and there was nowhere to
see what could be configured.  ``settings.toml`` is a single readable file:

    [ui]
    theme = "nord"
    banner = true

Reading uses stdlib ``tomllib``.  Writing is hand-rolled rather than pulling in
``tomli-w`` for a file this small; the writer covers the value types declared
below (string, bool, int) and nothing else, which is checked by the schema
rather than assumed.

Unknown keys in the file are preserved on write.  A newer studio writing a
setting this build does not know about must not lose it when an older build
saves.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DISCOVERABLE",
    "SETTINGS",
    "Setting",
    "Settings",
    "apply_at_startup",
    "choices_for",
    "detected_for",
    "settings_path",
    "theme_names",
]

logger = logging.getLogger(__name__)

_FILENAME = "settings.toml"


@dataclass(frozen=True, slots=True)
class Setting:
    """One configurable value.

    Attributes:
        key: Dotted path, ``"ui.theme"`` -- the section and name in the file.
        default: Value used when the file says nothing.
        help: One line, shown by ``settings list``.
        choices: Permitted values, validated on write and offered in
            completion.  Empty means any value of the right type.
    """

    key: str
    default: Any
    help: str
    choices: tuple[str, ...] = ()

    @property
    def section(self) -> str:
        return self.key.split(".", 1)[0]

    @property
    def name(self) -> str:
        return self.key.split(".", 1)[1]

    @property
    def type_name(self) -> str:
        return {bool: "bool", int: "int"}.get(type(self.default), "string")


def theme_names() -> tuple[str, ...]:
    """Theme choices, read from the registry so the two cannot drift.

    Resolved on demand rather than at import: themes are discovered by globbing
    ``ui/themes/``, so asking too early would freeze a partial list.
    """
    try:
        from pistudio.ui.theme import all_themes

        return tuple(sorted(all_themes()))
    except Exception:  # pragma: no cover - a broken theme must not break settings
        return ()


#: Every setting the studio reads.  Adding one here is the whole change:
#: ``settings list``, validation, completion and the file all follow.
SETTINGS: tuple[Setting, ...] = (
    Setting("ui.theme", "nord", "Colour theme"),
    Setting("ui.banner", True, "Show the logo when the interactive session starts"),
    Setting("ui.emoji", True, "Show device emoji and status icons"),
    Setting("output.mode", "rich", "Default output style", choices=("rich", "plain", "json")),
    Setting("safety.assume_yes", False, "Answer every confirmation with yes (equivalent to --yes)"),
    Setting("serve.host", "127.0.0.1", "Default interface for 'serve'"),
    Setting("serve.port", 8080, "Default port for 'serve'"),
    # A stored printer names the target; it does not turn printing on.  `--print`
    # still decides that, or every generated file would go to paper.
    Setting("print.printer", "", "Default printer for --print (blank uses the system default)"),
    Setting("print.media", "", "Default page or label size, e.g. A4 or Custom.62x100mm"),
    Setting("print.copies", 1, "Default number of copies"),
    # The printed width of a generated code.  Stored separately from print.*
    # because it is written into the FILE (the pHYs chunk), so it applies to
    # `barcode png`/`svg` whether or not anything is printed.
    Setting("barcode.size", "", "Default printed width for barcode png/svg, e.g. 55mm"),
    # UART defaults.  A serial console has no negotiation -- both ends must
    # already agree -- so these are the settings worth pinning per workbench.
    Setting("uart.port", "", "Default serial port (blank auto-selects the only USB-TTL adapter)"),
    Setting("uart.baud", 115200, "Default baud rate"),
    Setting(
        "uart.line_ending",
        "crlf",
        "How to terminate a payload; the wrong one leaves it unread",
        choices=("crlf", "lf", "cr", "none"),
    ),
    Setting("uart.char_delay_ms", 0, "Per-character delay; raise it for targets that drop pasted input"),
    Setting("uart.read_for", 2, "Seconds to listen for a reply after transmitting"),
)

_BY_KEY = {s.key: s for s in SETTINGS}


def settings_path(session_dir: str | Path) -> Path:
    """Where preferences live for *session_dir*."""
    return Path(session_dir) / _FILENAME


def _format_value(value: Any) -> str:
    """Render *value* as a TOML scalar."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class Settings:
    """Load, query and persist the studio's preferences."""

    def __init__(self, session_dir: str | Path) -> None:
        self.path = settings_path(session_dir)
        self._data: dict[str, dict[str, Any]] = self._read()

    def _read(self) -> dict[str, dict[str, Any]]:
        """Parse the file.  A malformed one is reported and treated as empty.

        Refusing to start because a preferences file has a typo in it would be
        the wrong trade: the studio works fine on defaults.
        """
        try:
            with self.path.open("rb") as fh:
                return tomllib.load(fh)
        except FileNotFoundError:
            return {}
        except (OSError, tomllib.TOMLDecodeError) as exc:
            logger.warning("Ignoring unreadable %s: %s", self.path, exc)
            return {}

    def get(self, key: str) -> Any:
        """Return the stored value for *key*, or its declared default."""
        spec = _BY_KEY.get(key)
        if spec is None:
            raise KeyError(key)
        section = self._data.get(spec.section)
        if not isinstance(section, dict) or spec.name not in section:
            return spec.default
        value = section[spec.name]
        # A hand-edited file can hold the wrong type; fall back rather than
        # hand a string to something expecting an int.
        if type(value) is not type(spec.default):
            logger.warning("%s in %s should be %s, got %r", key, self.path, spec.type_name, value)
            return spec.default
        return value

    def set(self, key: str, raw: str) -> Any:
        """Parse *raw* against *key*'s type, store it, and return the value.

        Raises:
            KeyError: No such setting.
            ValueError: The text does not parse as the setting's type, or is
                outside its declared choices.
        """
        spec = _BY_KEY.get(key)
        if spec is None:
            raise KeyError(key)

        value: Any
        if isinstance(spec.default, bool):
            lowered = raw.strip().lower()
            if lowered in ("true", "yes", "on", "1"):
                value = True
            elif lowered in ("false", "no", "off", "0"):
                value = False
            else:
                raise ValueError(f"{key} is a true/false setting; got {raw!r}")
        elif isinstance(spec.default, int):
            try:
                value = int(raw)
            except ValueError:
                raise ValueError(f"{key} is a whole number; got {raw!r}") from None
        else:
            value = raw
            # Discoverable settings offer what is attached but do not enforce
            # it: a printer that is switched off, or a cable to be plugged in
            # tomorrow, is still a legitimate thing to configure now.
            if key not in DISCOVERABLE:
                allowed = choices_for(key)
                if allowed and value not in allowed:
                    raise ValueError(f"{key} must be one of {', '.join(allowed)}; got {raw!r}")

        self._data.setdefault(spec.section, {})[spec.name] = value
        self.save()
        return value

    def unset(self, key: str) -> None:
        """Drop *key*, so it falls back to its default."""
        spec = _BY_KEY.get(key)
        if spec is None:
            raise KeyError(key)
        self._data.get(spec.section, {}).pop(spec.name, None)
        self.save()

    def is_set(self, key: str) -> bool:
        """Whether *key* is stored, as opposed to defaulted."""
        spec = _BY_KEY.get(key)
        if spec is None:
            return False
        return spec.name in self._data.get(spec.section, {})

    def save(self) -> None:
        """Write the file, preserving sections and keys this build does not know.

        Failures are logged, not raised: losing a preference is a nuisance, but
        it must not take down the command the user was actually running.
        """
        known = {s.section for s in SETTINGS}
        lines = [
            "# Prompt Injection Studio preferences.",
            "# Edit by hand or with the 'settings' command; unknown keys are kept.",
        ]
        for section in [*sorted(known), *sorted(set(self._data) - known)]:
            values = self._data.get(section)
            if not isinstance(values, dict) or not values:
                continue
            lines.append(f"\n[{section}]")
            for name, value in values.items():
                lines.append(f"{name} = {_format_value(value)}")

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not write %s: %s", self.path, exc)


def apply_at_startup(session_dir: str | Path) -> Settings:
    """Load preferences and apply the ones that change global state.

    Called once before a command runs.  Only the theme is global; the rest are
    read at their point of use so a command-line flag can still override them.

    Migrates a pre-existing ``theme.txt`` on first run, so upgrading does not
    silently reset someone's theme.
    """
    settings = Settings(session_dir)

    legacy = Path(session_dir) / "theme.txt"
    if not settings.is_set("ui.theme") and legacy.exists():
        try:
            name = legacy.read_text(encoding="utf-8").strip()
        except OSError:
            name = ""
        if name in theme_names():
            settings.set("ui.theme", name)
            logger.debug("Migrated theme preference from %s", legacy)

    from pistudio.ui.theme import set_active_theme

    try:
        set_active_theme(settings.get("ui.theme"))
    except KeyError:
        logger.warning("Stored theme %r is not installed; using the default", settings.get("ui.theme"))
    return settings


def _printer_names() -> tuple[str, ...]:
    """Printers CUPS can see, default first."""
    try:
        from pistudio.printing import list_printers

        found = list_printers()
    except Exception:  # pragma: no cover - no CUPS is a normal state
        return ()
    return tuple(p.name for p in sorted(found, key=lambda p: not p.is_default))


def _serial_port_names() -> tuple[str, ...]:
    """USB-TTL adapters the host can see.

    Bridges only: a Flipper also presents a serial port, but ``hw flipper``
    speaks its protocol and offering it here would invite someone to point
    ``uart`` at a device the studio already drives properly.
    """
    try:
        from pistudio.hardware.uart.device import find_serial_ports

        return tuple(p.device for p in find_serial_ports(bridges_only=True))
    except Exception:  # pragma: no cover - no pyserial is a normal state
        return ()


#: Settings whose value is a name the host can enumerate.  Completion offers
#: what is attached, ``settings`` shows it, and ``settings detect`` fills it in
#: -- so configuring a workbench does not mean copying paths out of ``lpstat``
#: or ``ls /dev``.
DISCOVERABLE: dict[str, tuple[str, object]] = {
    "print.printer": ("printer", _printer_names),
    "uart.port": ("serial port", _serial_port_names),
}


def detected_for(key: str) -> tuple[str, ...]:
    """What the host currently offers for *key*, best candidate first."""
    entry = DISCOVERABLE.get(key)
    if entry is None:
        return ()
    _, probe = entry
    return probe()  # type: ignore[operator]


def choices_for(key: str) -> tuple[str, ...]:
    """Permitted values for *key*, including those known only at runtime."""
    if key == "ui.theme":
        return theme_names()
    if key in DISCOVERABLE:
        # Offered, not enforced: a printer or cable that is currently
        # unplugged is still a legitimate thing to configure.
        return detected_for(key)
    spec = _BY_KEY.get(key)
    return spec.choices if spec else ()
