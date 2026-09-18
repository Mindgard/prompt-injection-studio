"""One declaration per flag, for every consumer of it.

A flag used to be written down in up to three unlinked places: prose in
``Command.usage``, an entry in ``Command.flag_descriptions``, and the
``extract_flag`` calls in the body that actually read it.  Nothing kept them in
step, so they drifted -- ``audio`` advertised ``--payload`` while ``audio live``
never parsed it, and ``file`` parsed nine flags (``--encode``, ``--voice``,
``--carrier`` …) that appeared in neither its usage nor its completion.  Those
were working features nobody could discover.

The codebase had already reached for this abstraction three times, each
covering one facet: ``format_flags.FLAG_SCOPES`` (which formats a flag applies
to), ``barcode_cmd``'s ``_MATRIX_FLAGS``/``_LINEAR_FLAGS`` plus a ``seen`` list
(the same idea again), and ``flag_descriptions`` (completion text).  This
module is those three consolidated, not a fourth mechanism -- a ``Flag`` knows
its own name, help, value shape and scope, and every consumer derives from it.

Deliberately not argparse or Click: the studio hands each command the argv
remainder verbatim so its ~120 flags stay declared in one place rather than
being mirrored into a parser definition.  This keeps that property and adds the
single source of truth the hand-rolled version was missing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = [
    "ALL_SCOPES",
    "Flag",
    "FlagError",
    "ParsedFlags",
    "format_options_block",
    "parse_flags",
]

# A flag that applies wherever its command does.  Listed as a sentinel rather
# than enumerating every format, which would drift the moment one is added.
ALL_SCOPES: tuple[str, ...] = ("*",)


class FlagError(Exception):
    """A flag was misused.  The message is written for the person who typed it."""


@dataclass(frozen=True, slots=True)
class Flag:
    """One command-line option, described once.

    Attributes:
        name: The long spelling, including dashes (``"--output"``).
        short: Optional single-dash alias (``"-o"``).
        value: Metavar for the value this flag takes (``"path"``).  ``None``
            makes it a boolean, which consumes no following token.
        help: One line, shown in usage, completion, and ``--help``.
        choices: Permitted values.  Validated centrally, and offered as
            completions.
        scope: Names of the modes/formats this flag reaches, or ``ALL_SCOPES``.
            Replaces the three ad-hoc scope tables.
        scope_label: Human phrase for *scope*, used in the rejection message
            ("applies to the TTS formats").
        completes: ``"path"`` to complete filenames, ``"payload"`` for payload
            names, ``"choices"`` to offer *choices*, or ``""`` for nothing.
        repeatable: Whether repeating the flag accumulates rather than
            overwrites.
    """

    name: str
    short: str | None = None
    value: str | None = None
    help: str = ""
    choices: tuple[str, ...] = ()
    scope: tuple[str, ...] = ALL_SCOPES
    scope_label: str = ""
    completes: str = ""
    repeatable: bool = False

    def __post_init__(self) -> None:
        if not self.name.startswith("--"):
            raise ValueError(f"flag names are long-form: {self.name!r}")
        if self.short is not None and not self.short.startswith("-"):
            raise ValueError(f"short flags start with a dash: {self.short!r}")

    @property
    def is_boolean(self) -> bool:
        """True when the flag is a switch that takes no value."""
        return self.value is None

    @property
    def spellings(self) -> tuple[str, ...]:
        """Every token that selects this flag."""
        return (self.name, self.short) if self.short else (self.name,)

    def applies_to(self, mode: str) -> bool:
        """Whether this flag is meaningful for *mode* (a format or subcommand)."""
        return self.scope == ALL_SCOPES or mode in self.scope

    @property
    def usage_term(self) -> str:
        """The left column of the usage ``Options:`` block.

        ``--output, -o <path>`` rather than ``--output -o <path>``: without the
        comma the short form reads as a second argument.
        """
        term = f"{self.name}, {self.short}" if self.short else self.name
        return f"{term} <{self.value}>" if self.value else term


@dataclass
class ParsedFlags:
    """The result of parsing an argv remainder against a flag spec."""

    values: dict[str, str | bool | list[str]] = field(default_factory=dict)
    positional: list[str] = field(default_factory=list)
    #: Long names the user actually typed, so a command can tell "not given"
    #: from "given the default" -- what barcode's ``seen`` list was for.
    given: set[str] = field(default_factory=set)

    def get(self, name: str, default: object = None) -> object:
        """Return the value for long-form *name*, or *default*."""
        return self.values.get(name, default)

    def text(self, name: str, default: str | None = None) -> str | None:
        """Return a string-valued flag."""
        got = self.values.get(name, default)
        return got if isinstance(got, str) else default

    def flag(self, name: str) -> bool:
        """Return a boolean-valued flag."""
        return bool(self.values.get(name, False))

    def integer(self, name: str, default: int) -> int:
        """Return an int-valued flag, raising ``FlagError`` on a bad value.

        One contract for every numeric flag.  There used to be four functions
        called ``_int_flag``: one raised, three printed and returned ``None``,
        and ``printing_flags`` called bare ``int()`` so ``--copies abc`` came
        back as an uncaught ``ValueError``.
        """
        raw = self.values.get(name)
        if raw is None or isinstance(raw, bool):
            return default
        try:
            return int(str(raw))
        except ValueError:
            raise FlagError(f"{name} must be a whole number, got {str(raw)!r}") from None

    def number(self, name: str, default: float) -> float:
        """Return a float-valued flag, raising ``FlagError`` on a bad value."""
        raw = self.values.get(name)
        if raw is None or isinstance(raw, bool):
            return default
        try:
            return float(str(raw))
        except ValueError:
            raise FlagError(f"{name} must be a number, got {str(raw)!r}") from None


def _resolve(spec: tuple[Flag, ...], token: str) -> Flag | None:
    for flag in spec:
        if token in flag.spellings:
            return flag
    return None


def parse_flags(
    spec: tuple[Flag, ...],
    args: list[str],
    *,
    mode: str = "",
    mode_label: str = "",
) -> ParsedFlags:
    """Parse *args* against *spec*.

    Args:
        spec: The flags this command accepts.
        args: The argv remainder, verbatim.
        mode: The format or subcommand in play, used to reject a flag that
            exists but does not apply here.  Empty disables the check.
        mode_label: How to name *mode* in the rejection message, when the
            internal scope name would mean nothing to the reader.

    Returns:
        A :class:`ParsedFlags` holding values, positionals and what was given.

    Raises:
        FlagError: On an unknown flag, a missing value, a value outside
            ``choices``, or a flag outside its scope.  The caller reports it
            via ``shell.out.error`` -- parsing does not print.

    Supports ``--flag=value`` and a bare ``--`` terminator, neither of which
    the ``extract_flag``/``strip_flag`` pair could express.
    """
    result = ParsedFlags()
    known = [f.name for f in spec] + [f.short for f in spec if f.short]

    i = 0
    while i < len(args):
        token = args[i]

        # Everything after `--` is positional, so a payload may begin with a
        # dash without being mistaken for a flag.
        if token == "--":
            result.positional.extend(args[i + 1 :])
            break

        if not token.startswith("-") or token == "-":
            result.positional.append(token)
            i += 1
            continue

        inline: str | None = None
        if token.startswith("--") and "=" in token:
            token, inline = token.split("=", 1)

        flag = _resolve(spec, token)
        if flag is None:
            raise FlagError(_unknown(token, known))

        if mode and not flag.applies_to(mode):
            where = flag.scope_label or ", ".join(flag.scope)
            raise FlagError(f"{flag.name} does not apply to {mode_label or mode}; it applies to {where}.")

        result.given.add(flag.name)

        if flag.is_boolean:
            if inline is not None:
                raise FlagError(f"{flag.name} is a switch and takes no value.")
            result.values[flag.name] = True
            i += 1
            continue

        if inline is not None:
            value = inline
            i += 1
        else:
            if i + 1 >= len(args):
                raise FlagError(f"{flag.name} needs a value (<{flag.value}>).")
            value = args[i + 1]
            i += 2

        if flag.choices and value not in flag.choices:
            raise FlagError(f"{flag.name} must be one of {', '.join(flag.choices)}; got {value!r}.")

        if flag.repeatable:
            bucket = result.values.setdefault(flag.name, [])
            if isinstance(bucket, list):
                bucket.append(value)
        else:
            result.values[flag.name] = value

    return result


def _unknown(token: str, known: Sequence[str | None]) -> str:
    """Build the error for an unrecognised flag, naming the closest match."""
    import difflib

    candidates = [k for k in known if k]
    matches = difflib.get_close_matches(token, candidates, n=1, cutoff=0.6)
    hint = f" Did you mean '{matches[0]}'?" if matches else ""
    return f"Unknown flag: {token}.{hint}"


def format_options_block(spec: tuple[Flag, ...], *, indent: str = "  ", gutter: int = 22) -> str:
    """Render *spec* as the ``Options:`` section of a usage string.

    Commands hand-wrote this block, which is why description columns landed on
    22, 23, 30, 32, 33 and 37 across the tree.  Deriving it means the usage text
    cannot omit a flag the command parses.
    """
    lines = []
    for flag in spec:
        term = flag.usage_term
        pad = " " * max(1, gutter - len(term))
        lines.append(f"{indent}{term}{pad}{flag.help}".rstrip())
    return "\n".join(lines)
