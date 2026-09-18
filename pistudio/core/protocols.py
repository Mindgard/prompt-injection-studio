"""The runtime interface commands and hardware modules depend on.

``StudioProtocol`` captures the narrow surface that ported code touches, so
those modules stay decoupled from the concrete :class:`~pistudio.core.studio.Studio`.
"""

from __future__ import annotations

from typing import Any, Protocol

__all__ = ["OutputProtocol", "StudioProtocol"]


class OutputProtocol(Protocol):
    """Message-rendering interface used for all user-facing output.

    Kept in step with :class:`~pistudio.ui.output.ShellOutput` by
    ``tests/test_output_contract.py``.  It had drifted: ``waiting`` and
    ``result`` were missing, and ``empty_state``'s ``hint`` carried a default
    the concrete class does not have, so a protocol-conformant call raised
    ``TypeError``.
    """

    json_mode: bool
    plain_mode: bool

    def success(self, msg: str, data: dict[str, Any] | None = ...) -> None: ...
    def error(self, msg: str) -> None: ...
    def warn(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def waiting(self, msg: str) -> None: ...
    def plain(self, msg: str) -> None: ...
    def empty_state(self, thing: str, hint: str) -> None: ...
    def not_found(self, thing: str, name: str, suggestion: str = ...) -> None: ...
    def usage_error(self, usage: str) -> None: ...
    def failed(self, action: str, error: str) -> None: ...
    def table(self, columns: list[str], rows: list[list[str]], **kwargs: Any) -> None: ...
    def result(self, data: Any, table_fn: Any = ...) -> None: ...


class StudioProtocol(Protocol):
    """What every command receives as its first argument."""

    out: Any
    console: Any
    err_console: Any
    audit: Any
    target: Any
    session: Any
    # Set by the REPL to the entered context, so completion knows which
    # subcommands are first-class.  Declared here because ``ui/completer.py``
    # reads it and was reaching for ``getattr(shell, ..., None)`` to do so.
    namespace_context: str | None
    assume_yes: bool
    #: Loaded preferences, or None before the CLI attaches them.
    settings: Any

    @property
    def session_dir(self) -> str: ...

    # Properties on Studio, so that setting one also updates ``out``.
    @property
    def json_mode(self) -> bool: ...

    @property
    def plain_mode(self) -> bool: ...

    @property
    def exit_code(self) -> int: ...

    def print_raw(self, text: str) -> None: ...
    def spinner(self, message: str) -> Any: ...
    def confirm(self, question: str) -> bool: ...
    def confirm_phrase(self, question: str, phrase: str) -> bool: ...
    def ask(self, question: str) -> str | None: ...
    def pause(self, message: str = ...) -> bool: ...
