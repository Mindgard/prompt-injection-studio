"""The Studio context object passed to every command.

Deliberately duck-type-compatible with the shell object this package was
extracted from, over the narrow surface the ported trees touch: ``out``,
``console``, ``_session_dir`` and ``target``.  Keeping that shape is what
lets ~13k lines of ported code run without body edits.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from pistudio.ui.output import ShellOutput

__all__ = ["AuditLog", "Studio", "TargetContext", "default_session_dir"]

logger = logging.getLogger(__name__)


class AuditLog:
    """Append-only JSONL record of actions taken.

    Payload generation and hardware deployment are logged so a tester can
    reconstruct what was delivered where — useful for both engagement
    reporting and undoing a demo.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def log(self, action: str, **fields: Any) -> None:
        """Append an *action* entry.  Failures are logged, never raised."""
        entry = {"ts": datetime.now(UTC).isoformat(), "action": action, **fields}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            logger.debug("Could not write audit entry %r", action, exc_info=True)


@dataclass
class TargetContext:
    """Optional metadata about the system under test.

    Read only when generating payloads with an LLM, to give the model
    context about what it is writing a payload for.
    """

    url: str = ""
    preset: str = ""
    model_name: str = ""
    system_prompt: str = ""


def default_session_dir() -> str:
    """Return the default state directory, honouring ``PISTUDIO_HOME``."""
    return os.environ.get("PISTUDIO_HOME") or str(Path.home() / ".pistudio")


class Studio:
    """Runtime context: output, console, state directory and target metadata."""

    def __init__(
        self,
        session_dir: str | Path | None = None,
        out: ShellOutput | None = None,
        console: Console | None = None,
        target: TargetContext | None = None,
        json_mode: bool = False,
        plain_mode: bool = False,
        assume_yes: bool = False,
    ) -> None:
        """Create a studio context.

        Args:
            session_dir: Where payloads, prompts and preferences are stored.
                Defaults to ``$PISTUDIO_HOME`` or ``~/.pistudio``.
            out: Output helper.  Built from *console* when omitted.
            console: Rich console.  A default one is created when omitted.
            target: Metadata about the system under test.
            json_mode: Emit machine-readable JSON.
            plain_mode: Emit grep-friendly prefixed text with no colour.
            assume_yes: Answer every confirmation with yes.  Makes destructive
                operations scriptable; nothing else consults it.
        """
        self._session_dir = str(session_dir if session_dir is not None else default_session_dir())
        Path(self._session_dir).mkdir(parents=True, exist_ok=True)

        self.console = console or Console(no_color=plain_mode)
        # Diagnostics go to stderr so that `pistudio --json ... > out.json`
        # produces a file holding only data.  When a console is injected (tests,
        # background jobs) both streams stay on it, so a single captured buffer
        # still sees everything.
        self.err_console = self.console if console is not None else Console(stderr=True, no_color=plain_mode)
        # ShellOutput writes back to _last_exit_code so that commands which
        # report failure via out.error() and return normally still exit non-zero.
        self._last_exit_code = 0
        self.out = out or ShellOutput(
            self.console,
            json_mode=json_mode,
            plain_mode=plain_mode,
            shell=self,
            auto_detect_ascii=True,
            err_console=self.err_console,
        )
        self.target = target or TargetContext()
        self._json_mode = json_mode
        self._plain_mode = plain_mode
        self.assume_yes = assume_yes
        self.audit = AuditLog(Path(self._session_dir) / "audit.log")

        # Set by the REPL: the prompt session (for confirmations) and the
        # active command namespace.
        self.session: Any = None
        self.namespace_context: str | None = None
        # Persisted preferences, attached by the CLI once they are loaded.
        # None when a Studio is built directly (tests, library use), which
        # every reader treats as "fall back to the built-in defaults".
        self.settings: Any = None

    @property
    def session_dir(self) -> str:
        """The directory holding persisted studio state."""
        return self._session_dir

    # ``json_mode``/``plain_mode`` are properties so that setting one on the
    # Studio also sets it on ``out``.  They were independent attributes, and
    # code that flipped ``shell.json_mode`` after construction left ``out``
    # still rendering Rich tables into what a caller was about to parse.
    @property
    def json_mode(self) -> bool:
        """Whether output should be machine-readable JSON."""
        return self._json_mode

    @json_mode.setter
    def json_mode(self, value: bool) -> None:
        self._json_mode = value
        if self.out is not None:
            self.out.json_mode = value

    @property
    def plain_mode(self) -> bool:
        """Whether output should be grep-friendly plain text."""
        return self._plain_mode

    @plain_mode.setter
    def plain_mode(self, value: bool) -> None:
        self._plain_mode = value
        if self.out is not None:
            self.out.plain_mode = value

    @property
    def exit_code(self) -> int:
        """``1`` if any command reported an error, else ``0``."""
        return self._last_exit_code

    def print_raw(self, text: str) -> None:
        """Write *text* verbatim, with no markup interpretation or wrapping."""
        self.console.print(text, highlight=False, markup=False, soft_wrap=True)

    @contextmanager
    def spinner(self, message: str) -> Any:
        """Show a progress spinner for a long-running step.

        Yields a Rich status object whose ``update()`` refreshes the message.
        Suppressed in JSON and plain modes so machine-readable output stays
        parseable.
        """
        if self.json_mode or self.plain_mode:
            yield _NullStatus()
            return
        with self.console.status(message, spinner="dots") as status:
            yield status

    def _can_prompt(self) -> bool:
        """Whether there is a usable input channel for an interactive question.

        The REPL's ``PromptSession`` owns its own terminal handle and works
        when ``sys.stdin`` is not a TTY, so the session is checked *first*.
        Testing ``isatty()`` up front discarded a live channel: inside the
        interactive session ``hw flipper remote`` opened its console and then
        read ``None`` on the first line, exiting immediately.

        Only the bare ``input()`` fallback needs a terminal.
        """
        import sys

        if self.json_mode:
            return False
        if self.session is not None:
            return True
        return sys.stdin.isatty()

    def confirm(self, question: str) -> bool:
        """Ask *question* and return True only on an explicit yes.

        Uses the REPL's prompt session when there is one, otherwise falls back
        to ``input()``.  Treats EOF and Ctrl+C as "no".

        Non-interactive callers never get a prompt they cannot answer:

        - ``--yes`` returns True without asking, which is what makes a
          destructive operation scriptable at all.
        - Without a terminal (a pipe, CI) or in ``--json`` mode, returns False
          and says why.  Blocking on input that will never arrive, or writing a
          bare prompt into a JSON stream, are both worse than declining.

        Every confirmation goes through here rather than reaching for
        ``session.prompt`` directly: ``session`` is set only by the REPL, so a
        direct call raised ``AttributeError: 'NoneType' has no attribute
        'prompt'`` on the command line -- an unhandled traceback on exactly the
        BLE-transmit and BadUSB-deploy paths where the prompt is the safety
        control.
        """
        if self.assume_yes:
            return True
        if not self._can_prompt():
            self.out.error(f"{question} needs confirmation. Re-run with --yes to proceed non-interactively.")
            return False
        try:
            if self.session is not None:
                answer = self.session.prompt(f"  {question} (y/N) ")
            else:
                answer = input(f"  {question} (y/N) ")
        except (EOFError, KeyboardInterrupt):
            return False
        return answer.strip().lower() in ("y", "yes")

    def confirm_phrase(self, question: str, phrase: str) -> bool:
        """Require *phrase* to be typed exactly.  For the irreversible cases.

        ``--yes`` satisfies this too: a caller that has already accepted the
        blast radius on the command line should not be forced into a terminal.
        """
        if self.assume_yes:
            return True
        if not self._can_prompt():
            self.out.error(f"{question} needs confirmation. Re-run with --yes to proceed non-interactively.")
            return False
        try:
            ask = self.session.prompt if self.session is not None else input
            answer = ask(f"  {question} Type '{phrase}' to proceed: ")
        except (EOFError, KeyboardInterrupt):
            return False
        return answer.strip() == phrase

    def ask(self, question: str) -> str | None:
        """Read one free-text answer, or None when there is nobody to ask.

        For genuine input -- picking a serial port, driving a nested console --
        rather than a yes/no decision.  ``--yes`` deliberately does *not* answer
        these: there is no safe default value to invent, so a non-interactive
        caller gets None and the command reports what it needed.
        """
        if not self._can_prompt():
            return None
        try:
            ask = self.session.prompt if self.session is not None else input
            return ask(f"  {question} ")
        except (EOFError, KeyboardInterrupt):
            return None

    def pause(self, message: str = "Press Enter to continue, or 'q' to quit") -> bool:
        """Wait for the user between steps of a guided flow.

        Returns:
            True to carry on, False if the user asked to stop.  Without a
            terminal (a pipe, or CI) this returns True immediately rather
            than blocking on input that will never arrive.
        """
        if not self._can_prompt():
            return True
        ask = self.session.prompt if self.session is not None else input
        try:
            answer = ask(f"  {message} ")
        except (EOFError, KeyboardInterrupt):
            return False
        return answer.strip().lower() not in ("q", "quit", "exit", "n", "no")


class _NullStatus:
    """No-op stand-in for a Rich status when spinners are suppressed."""

    def update(self, *args: Any, **kwargs: Any) -> None:
        """Ignore status updates."""
