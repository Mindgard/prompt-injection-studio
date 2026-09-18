"""Command ABC for studio commands.

Plugins define commands by subclassing ``Command`` and implementing
``execute()``.  The shell's command registry (which lives in the shell
package, not here) is responsible for collecting and dispatching them.
"""

from __future__ import annotations

import difflib
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import TYPE_CHECKING

from pistudio.core.flags import Flag, format_options_block

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

__all__ = ["Command", "HELP_FLAGS", "wants_help"]

# ``help`` is included because inside a REPL context (``barcode>``) that is the
# natural way to ask, and the hw device handlers already accepted all three.
HELP_FLAGS = frozenset({"--help", "-h", "help"})


def wants_help(args: list[str]) -> bool:
    """Return True when *args* asks this command for its own usage.

    Only the *first* token counts.  Two constraints force that:

    Payload text is arbitrary.  This tool exists to carry attacker-controlled
    strings, so ``barcode "--help"`` is a real request to encode that text and
    ``payloads add x "ignore --help"`` is a real payload.  Scanning the whole
    argv would silently swallow both.

    Subcommands own their own help.  ``hw flipper --help`` must reach the
    flipper handler, which prints device-specific usage; answering it here
    would replace that with the generic ``hw`` page.  So a leading subcommand
    means the request is not ours to answer.
    """
    return bool(args) and args[0] in HELP_FLAGS


class Command(ABC):
    """Base class for all shell commands.

    Subclass attributes:
        name:        Canonical command name (e.g. ``"recon"``).
        aliases:     Alternative names the user can type (e.g. ``["rc"]``).
        help:        One-line description shown in the ``help`` table.
        usage:       Multi-line usage/examples shown by ``help <cmd>`` and
                     the ``--help`` / ``-h`` flag.  Use plain text with
                     leading two-space indent for alignment.
        file_args:   Flags (e.g. ``("--output",)``) whose next token
                     should tab-complete as a file path.
        flags:       Declarative :class:`~pistudio.core.flags.Flag` spec.  When
                     set, ``flag_descriptions`` and the usage ``Options:``
                     block derive from it, so what a command parses cannot
                     drift from what it documents and completes.
        flag_descriptions:
                     Flag -> description for the completion dropdown.  Derived
                     from ``flags``; assign it directly only in a command that
                     has not been migrated yet.
        dev:         If ``True``, completely hidden unless dev_features is on.
        namespace:   If ``True``, typing the command name alone enters a
                     namespace context where subcommands become first-class.
        subcommands: ``name -> help text`` mapping for completion/help when
                     ``namespace`` is ``True``.  Metadata only — does not
                     change how ``execute()`` receives arguments.  A command
                     whose subcommands come from a registry may override this
                     with a property so the two cannot drift apart.
    """

    name: str = ""
    aliases: tuple[str, ...] | list[str] = ()
    help: str = ""
    usage: str = ""
    file_args: tuple[str, ...] | list[str] = ()
    #: Declarative flag spec.  When non-empty, ``flag_descriptions`` and
    #: ``file_args`` are derived from it, so a flag cannot be parsed without
    #: also being documented and completed.  Empty means the command still
    #: hand-rolls its parsing; both styles coexist during migration.
    flags: tuple[Flag, ...] = ()
    dev: bool = False
    namespace: bool = False
    # Declared as a read-only Mapping so a command whose subcommands come from
    # a registry can assign the derived dict in ``__init__``.
    subcommands: Mapping[str, str] = {}
    #: ``alias -> canonical subcommand``.  Kept apart from :attr:`subcommands`
    #: so ``help`` lists each verb once: showing ``list`` and ``ls`` as separate
    #: entries would double the listing to say nothing new.  Aliases still
    #: complete, and ``help <alias>`` resolves through here.
    subcommand_aliases: Mapping[str, str] = {}

    @abstractmethod
    def execute(self, shell: StudioProtocol, args: list[str]) -> None:
        """Execute the command with the given *args*.

        Subclasses must implement this.
        """
        ...

    def complete(self, shell: StudioProtocol, tokens: list[str]) -> list[str]:
        """Return tab-completion candidates for the current token position.

        Override in subclasses to provide context-aware completions.
        The default returns an empty list (no suggestions).
        """
        return []

    def wants_path_completion(self, tokens: list[str]) -> bool:
        """Return True if the current token position should complete file paths.

        Override in subclasses for positional file args
        (e.g. ``target load <path>``).  For flag-based file args
        (e.g. ``--output <path>``), use ``file_args`` instead.
        """
        return False

    @property
    def flag_descriptions(self) -> dict[str, str]:
        """Flag -> description, for the completion dropdown.

        Derived from :attr:`flags` when a command declares one.  A subclass
        that still assigns ``flag_descriptions = {...}`` shadows this, so both
        styles work while commands are migrated one at a time.
        """
        return {f.name: f.help for f in self.flags} | {f.short: f.help for f in self.flags if f.short}

    @property
    def flag_names(self) -> tuple[str, ...]:
        """Every spelling this command accepts, for completion and validation."""
        return tuple(spelling for f in self.flags for spelling in f.spellings)

    def options_block(self) -> str:
        """The ``Options:`` section of this command's usage, rendered from spec."""
        return format_options_block(self.flags)

    def print_help(self, shell: StudioProtocol) -> None:
        """Print this command's usage.  Must never have side effects."""
        shell.out.info(self.usage or self.help)

    @staticmethod
    def suggest_subcommand(sub: str, valid: list[str]) -> str:
        """Return a 'did you mean?' error message for an unknown subcommand.

        Uses fuzzy matching to suggest the closest valid subcommand.
        """
        if not sub:
            return f"Missing subcommand. Use: {', '.join(valid)}"
        matches = difflib.get_close_matches(sub, valid, n=1, cutoff=0.5)
        hint = f" Did you mean '{matches[0]}'?" if matches else ""
        return f"Unknown subcommand: '{sub}'.{hint} Use: {', '.join(valid)}"
