"""Output helpers — Rich tables, JSON and plain-text modes."""

import json
import os
from collections.abc import Callable
from typing import Any

__all__ = ["ShellOutput", "make_table", "resolve_editor"]

from rich import box
from rich.console import Console
from rich.markup import escape as _escape_markup
from rich.table import Table

from pistudio.ui.theme import active_theme


# ── Theme-aware color helpers ────────────────────────────────
# Existing ``from output import TEAL`` imports are resolved by the
# module-level ``__getattr__`` below.  Internal code uses the
def make_table(title: str = "", **kwargs: Any) -> Table:
    """Create a Rich table with theme-aware styling."""
    t = active_theme()
    return Table(
        title=f"[{t.secondary}]{title}[/]" if title else None,
        box=box.ROUNDED,
        border_style=t.border,
        header_style=f"bold {t.secondary}",
        title_style=t.secondary,
        **kwargs,
    )


class ShellOutput:
    """Tri-mode output helper: Rich, JSON, or plain text.

    All output goes through ``self.console`` so that thread-local
    console overrides (used by background jobs) capture it correctly.

    Output modes (mutually exclusive in practice):

    - **Rich** (default): Themed unicode icons + Rich markup.
    - **JSON** (``--json``): Machine-readable ``{"status": ..., "message": ...}``.
    - **Plain** (``--plain``): Grep-friendly prefixed text (``OK:``, ``ERROR:``,
      ``INFO:``, ``WARN:``, ``WAIT:``).  No colour, no markup.
    """

    def __init__(
        self,
        console: Console,
        json_mode: bool = False,
        plain_mode: bool = False,
        shell: Any = None,
        auto_detect_ascii: bool = False,
        err_console: Console | None = None,
    ):
        """Create a shell output helper bound to *console*.

        Args:
            err_console: Where diagnostics go.  Defaults to *console* so that
                tests capturing a single buffer keep seeing everything; the CLI
                passes a stderr console so ``pistudio --json ... > out.json``
                yields a file containing only data.
        """
        self.console = console
        self.err_console = err_console or console
        self.json_mode = json_mode
        self.plain_mode = plain_mode
        self._shell = shell
        self._ascii = False

        if auto_detect_ascii:
            term = os.environ.get("TERM", "")
            no_color = os.environ.get("NO_COLOR", "")
            if term == "dumb" or no_color:
                self._ascii = True

    def set_ascii_mode(self, enabled: bool) -> None:
        """Toggle ASCII icon fallbacks."""
        self._ascii = enabled

    def _icon(self, unicode: str, ascii: str) -> str:
        """Return the appropriate icon based on ascii_mode."""
        return ascii if self._ascii else unicode

    def _print(self, text: str) -> None:
        """Write plain text through the console (captured in background threads).

        ``soft_wrap`` is load-bearing, not cosmetic: without it Rich hard-wraps
        at the console width and inserts a newline inside whatever string
        happens to straddle the boundary.  For JSON that produces output which
        does not parse — a 400-character payload came back as seven lines and
        ``json.loads`` rejected it — and the MCP server reads exactly this
        stdout.  Machine-readable output must never be reflowed.
        """
        self.console.print(text, highlight=False, markup=False, soft_wrap=True)

    def _print_err(self, text: str) -> None:
        """Write a diagnostic to the error console, unwrapped."""
        self.err_console.print(text, highlight=False, markup=False, soft_wrap=True)

    def plain(self, msg: str) -> None:
        """Emit raw text with no status prefix or markup in any output mode."""
        self._print(msg)

    def table(
        self,
        columns: list[str],
        rows: list[list[str]],
        *,
        column_styles: dict[str, dict[str, Any]] | None = None,
        json_rows: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Render tabular data in rich, plain, or JSON form.

        One call covers all three modes.  Commands used to build a
        ``rich.table.Table`` directly after a hand-written ``if json_mode``
        branch, which is why ``--plain`` emitted box-drawing characters
        everywhere: the plain branch simply did not exist at those sites.

        Args:
            columns: Header labels, also the JSON keys when *json_rows* is
                omitted.
            rows: Cell text, one list per row.
            column_styles: Per-column Rich options (``style``, ``no_wrap``),
                keyed by header, so migrating a hand-built table does not
                change how it looks.
            json_rows: Richer structures for JSON mode, when the displayed
                cells are lossy (truncated text, a name with its scope folded
                in).  Falls back to zipping *columns* with *rows*.
        """
        if self.json_mode:
            payload = json_rows if json_rows is not None else [dict(zip(columns, row, strict=False)) for row in rows]
            self._print(json.dumps(payload, indent=2, default=str))
            return

        if self.plain_mode:
            # Tab-separated so `cut -f2` works; no title, no rules.
            if columns:
                self._print("\t".join(columns))
            for row in rows:
                self._print("\t".join(row))
            return

        title = kwargs.pop("title", "")
        table = make_table(title, **kwargs)
        for column in columns:
            table.add_column(column, **(column_styles or {}).get(column, {}))
        for row in rows:
            table.add_row(*row)
        self.console.print(table)

    def result(self, data: Any, table_fn: Callable[[Console, Any], None] | None = None) -> None:
        """Output structured data — as JSON or via a table-rendering function."""
        if self.json_mode:
            self._print(json.dumps(data, indent=2, default=str))
        elif table_fn:
            table_fn(self.console, data)
        else:
            self.console.print(data)

    def success(self, msg: str, data: dict[str, Any] | None = None) -> None:
        """Emit a success message (✓ / OK: / JSON {status: ok}).

        Also resets ``shell._last_exit_code = 0`` so that a successful
        command after a failed one clears the error state.
        """
        if self._shell is not None:
            self._shell._last_exit_code = 0
        if self.json_mode:
            payload = {"status": "ok", "message": msg}
            if data:
                payload.update(data)
            self._print(json.dumps(payload, default=str))
        elif self.plain_mode:
            self._print(f"OK: {msg}")
        else:
            icon = self._icon("\u2713", "[OK]")
            self.console.print(f"[{active_theme().success}]{icon}[/] {_escape_markup(msg)}")

    def error(self, msg: str) -> None:
        """Emit an error message (✗ / ERROR: / JSON {status: error}).

        Also sets ``shell._last_exit_code = 1`` (if a shell reference is
        available) so that commands which call ``shell.out.error()`` and
        return normally still propagate failure in ``-c`` / pipe mode.
        """
        if self._shell is not None:
            self._shell._last_exit_code = 1
        if self.json_mode:
            self._print_err(json.dumps({"status": "error", "message": msg}))
        elif self.plain_mode:
            self._print_err(f"ERROR: {msg}")
        else:
            icon = self._icon("\u2717", "[ERR]")
            self.err_console.print(f"[{active_theme().error}]{icon}[/] {_escape_markup(msg)}")

    def info(self, msg: str) -> None:
        """Emit an informational message (ℹ / INFO:).  Suppressed in JSON mode."""
        if self.json_mode:
            return  # suppress info in JSON mode
        if self.plain_mode:
            self._print(f"INFO: {msg}")
            return
        icon = self._icon("\u2139", "[i]")
        self.console.print(f"[{active_theme().info}]{icon}[/] {_escape_markup(msg)}")

    def warn(self, msg: str) -> None:
        """Emit a warning message (⚠ / WARN:).  Suppressed in JSON mode."""
        if self.json_mode:
            return
        if self.plain_mode:
            self._print_err(f"WARN: {msg}")
            return
        icon = self._icon("\u26a0", "[!]")
        self.err_console.print(f"[{active_theme().warning}]{icon}[/] {_escape_markup(msg)}")

    def waiting(self, msg: str) -> None:
        """Emit a 'please wait' message (⏳ / WAIT:).  Suppressed in JSON mode."""
        if self.json_mode:
            return
        if self.plain_mode:
            self._print(f"WAIT: {msg}")
            return
        self.console.print(f"[{active_theme().warning}]{self._icon('⏳', '[*]')}[/] {_escape_markup(msg)}")

    def empty_state(self, thing: str, hint: str) -> None:
        """Display an empty state message with an actionable hint.

        Suppressed in JSON mode. In plain mode, uses INFO: prefix.
        """
        if self.json_mode:
            return
        msg = f"No {thing} yet. {hint}"
        if self.plain_mode:
            self._print(f"INFO: {msg}")
            return
        t = active_theme()
        self.console.print(f"  [{t.muted}]{msg}[/]")

    def not_found(self, thing: str, name: str, suggestion: str = "") -> None:
        """Display a 'not found' error using the active theme's voice."""
        t = active_theme()
        msg = t.error_voice["not_found"].format(thing=thing, name=name)
        if suggestion:
            hint = t.error_voice["try_instead"].format(suggestion=suggestion)
            msg = f"{msg} {hint}"
        self.error(msg)

    def usage_error(self, usage: str) -> None:
        """Display a usage error using the active theme's voice."""
        t = active_theme()
        msg = t.error_voice["usage"].format(usage=usage)
        self.error(msg)

    def failed(self, action: str, error: str) -> None:
        """Display a failure error using the active theme's voice."""
        t = active_theme()
        msg = t.error_voice["failed"].format(action=action, error=error)
        self.error(msg)


# ── Shared utilities ──────────────────────────────────────────


def resolve_editor() -> str:
    """Return the user's preferred editor following Unix convention.

    Resolution order: ``$VISUAL`` → ``$EDITOR`` → ``vi``.
    """
    return os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
