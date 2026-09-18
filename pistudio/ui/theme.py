"""Theme system — dataclass, registry, auto-discovery, persistence.

Theme definitions live in individual files under ``themes/``.  Each file
calls ``register_theme(Theme(...))`` at import time.  This module provides
the ``Theme`` dataclass, the registry API, and the auto-discovery loader.

See ``docs/THEMES.md`` for the full guide on adding a new theme.
"""

__all__ = [
    "Theme",
    "build_logo",
    "contrast_ratio",
    "register_theme",
    "get_theme",
    "all_themes",
    "active_theme",
    "set_active_theme",
    "load_builtin_themes",
    "load_theme_preference",
    "save_theme_preference",
]

from dataclasses import dataclass, field

# The banner art, written once.  Each theme supplies only its colours: the
# art used to be pasted into all seven theme files with the hex codes swapped,
# so changing it meant seven edits that could disagree.
#
# Rows are (left, right) halves so a theme can run a gradient across the word
# the way the originals did.
_LOGO_ROWS: tuple[tuple[str, str], ...] = (
    ("██████╗ ██████╗ ", " ███████╗████████╗██╗   ██╗██████╗ ██╗ ██████╗ "),
    ("██╔══██╗██║", "     ██╔════╝╚══██╔══╝██║   ██║██╔══██╗██║██╔═══██╗"),
    ("██████╔╝██║", "     ███████╗   ██║   ██║   ██║██║  ██║██║██║   ██║"),
    ("██╔═══╝ ██║", "     ╚════██║   ██║   ██║   ██║██║  ██║██║██║   ██║"),
    ("██║     ██║", "     ███████║   ██║   ╚██████╔╝██████╔╝██║╚██████╔╝"),
    ("╚═╝     ╚═╝", "     ╚══════╝   ╚═╝    ╚═════╝ ╚═════╝ ╚═╝ ╚═════╝ "),
)

_LOGO_PAD = "  "


def build_logo(left: list[str] | tuple[str, ...], right: list[str] | tuple[str, ...] | None = None) -> str:
    """Render the banner art in a theme's colours.

    Args:
        left: One Rich style per row for the left half.  A shorter sequence is
            cycled, so a single-colour theme passes one entry.
        right: Styles for the right half.  Defaults to *left*, which is what a
            monochrome theme wants.

    Returns:
        A Rich markup string, ready to print.
    """
    right = right or left
    lines = []
    for index, (head, tail) in enumerate(_LOGO_ROWS):
        a = left[index % len(left)]
        b = right[index % len(right)]
        lines.append(f"{_LOGO_PAD}[{a}]{head}[/][{b}]{tail}[/]")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class Theme:
    """A complete shell color scheme + branding.

    Every field is documented in ``docs/THEMES.md``.  The required fields
    define the semantic color palette; optional fields control the
    toolbar, prompt, logo, and banner decorations.

    Frozen so themes are immutable after construction.
    """

    name: str
    description: str

    # Primary palette (used by output.py, banner.py, prompt.py, etc.)
    accent: str  # primary accent (logo, headings)
    secondary: str  # secondary accent (subtitles, labels)
    success: str  # success messages
    error: str  # error messages
    info: str  # info messages
    warning: str  # warning/waiting messages
    muted: str  # dim/muted text
    text: str  # default text
    border: str  # table/panel borders

    # Toolbar
    toolbar_bg: str = "#1e1e2e"
    toolbar_dim: str = "#8484a2"
    toolbar_text: str = "#a0a0c0"

    # Prompt
    prompt_emojis: tuple[str, ...] = ("❯",)
    prompt_color: str = "#ff6ac1"
    prompt_separator: str = "❯"
    prompt_separator_color: str = "#8b7fad"

    # Logo — Rich markup string (multi-line)
    logo: str = ""

    # Banner extras
    subtitle_left: str = "░▒▓"
    subtitle_right: str = "▓▒░"

    # Goodbye message shown on exit
    goodbye_message: str = "🌅 Goodbye!"

    # Completion dropdown styles (prompt_toolkit style strings)
    # Colors chosen for high contrast against dark dropdown background
    completion_bg: str = "#1a1a2e"  # Dark background for dropdown menu
    completion_bg_selected: str = "#3c3c4c"  # Slightly lighter for selected item
    completion_command: str = "#ff79c6"  # Top-level commands (bright pink)
    completion_subcommand: str = "#8be9fd"  # Subcommands (bright cyan)
    completion_flag: str = "#50fa7b"  # Flags like --output (bright green)
    completion_argument: str = "#f1fa8c"  # Arguments/values (bright yellow)
    completion_path: str = "#bd93f9"  # File paths (bright purple)
    completion_meta: str = "#f8f8f2"  # Description text (light grey/white)

    # Error voice — theme-specific phrasing for error messages
    error_voice: dict[str, str] = field(
        default_factory=lambda: {
            "not_found": "{thing} '{name}' not found.",
            "usage": "Usage: {usage}",
            "failed": "Failed to {action}: {error}",
            "empty_prefix": "No {thing} yet.",
            "try_instead": "Try: {suggestion}",
            "blocked": "Blocked: {reason}",
        }
    )


# ── Theme Registry ────────────────────────────────────────────

# Vendor-neutral by default; "studio" carries the original palette.
_DEFAULT_THEME = "nord"

_themes: dict[str, Theme] = {}
_active: Theme | None = None


def register_theme(theme: Theme) -> None:
    """Register a theme by name."""
    _themes[theme.name] = theme


def get_theme(name: str) -> Theme | None:
    """Look up a theme by name."""
    return _themes.get(name)


def all_themes() -> dict[str, Theme]:
    """Return all registered themes."""
    load_builtin_themes()
    return dict(_themes)


def active_theme() -> Theme:
    """Return the currently active theme."""
    global _active
    if _active is None:
        load_builtin_themes()
        _active = _themes.get(_DEFAULT_THEME, next(iter(_themes.values())))
    return _active


def set_active_theme(name: str) -> Theme:
    """Set the active theme by name. Returns the theme."""
    global _active
    load_builtin_themes()
    theme = _themes.get(name)
    if theme is None:
        raise KeyError(f"Unknown theme: '{name}'. Available: {', '.join(_themes)}")
    _active = theme
    return theme


# ── Auto-discovery ────────────────────────────────────────────

_themes_loaded = False


def load_builtin_themes() -> None:
    """Import all ``*.py`` files in the ``themes/`` directory.

    Each theme file calls ``register_theme()`` at import time, so
    importing the module is sufficient to register it.  This function
    is idempotent — calling it multiple times is safe.
    """
    global _themes_loaded
    if _themes_loaded:
        return
    _themes_loaded = True

    import importlib
    import logging
    import pathlib

    logger = logging.getLogger(__name__)
    themes_dir = pathlib.Path(__file__).parent / "themes"

    for py_file in sorted(themes_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"pistudio.ui.themes.{py_file.stem}"
        try:
            importlib.import_module(module_name)
        except Exception:
            logger.debug("Failed to import theme module %s", module_name, exc_info=True)


# ── Persistence ───────────────────────────────────────────────

_PREF_FILENAME = "theme.txt"


def load_theme_preference(session_dir: str) -> str | None:
    """Apply and return the theme name persisted for *session_dir*.

    Args:
        session_dir: Directory holding the studio's persisted state.

    Returns:
        The applied theme name, or ``None`` if nothing valid was stored.
    """
    import pathlib

    try:
        name = (pathlib.Path(session_dir) / _PREF_FILENAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not name:
        return None
    try:
        set_active_theme(name)
    except KeyError:
        return None
    return name


def save_theme_preference(session_dir: str, name: str) -> None:
    """Persist *name* as the active theme for *session_dir*.

    Failures are non-fatal — theme persistence is a convenience, not a
    requirement for the studio to work.
    """
    import logging
    import pathlib

    try:
        d = pathlib.Path(session_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / _PREF_FILENAME).write_text(f"{name}\n", encoding="utf-8")
    except OSError:
        logging.getLogger(__name__).debug("Could not persist theme preference", exc_info=True)


def _relative_luminance(hex_color: str) -> float:
    """Compute relative luminance per WCAG 2.1 from a hex color string."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    def _linearize(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(color1: str, color2: str) -> float:
    """Compute WCAG 2.1 contrast ratio between two hex colors.

    Returns a value between 1.0 (identical) and 21.0 (black/white).
    """
    l1 = _relative_luminance(color1)
    l2 = _relative_luminance(color2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)
