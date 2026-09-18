"""Shared ``--print`` flag parsing and CUPS submission.

Any command that writes a file can accept the printing flags by calling
:func:`extract_print_flags` before its own parser runs and
:func:`send_to_printer` once the file exists.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

logger = logging.getLogger(__name__)


@dataclass
class PrintOptions:
    """Where and how to print a generated image."""

    enabled: bool = False
    printer: str = ""
    copies: int = 1
    media: str = ""
    #: Hand scaling to the printer instead of printing at the size the file
    #: declares.  Off by default: a file that carries its own physical size
    #: prints correctly without it, and fitting overrides that size.
    fit: bool = False


def extract_print_flags(args: list[str], shell: StudioProtocol | None = None) -> tuple[list[str], PrintOptions]:
    """Pull the printing flags out of *args*.

    Returns the remaining arguments and the parsed options, so each command's
    own flag parser needs no knowledge of printing.

    Args:
        args: The argument list to read from.
        shell: When given, unset options fall back to the stored ``print.*``
            settings.  A stored printer supplies the *target*; it deliberately
            does not enable printing, or every generated file would go to
            paper without anyone asking.

    Raises:
        FlagError: ``--copies`` was not a number.  This used to be a bare
            ``int()``, so ``--copies abc`` escaped as an uncaught ValueError.
    """
    from pistudio.core.flags import FlagError

    opts = PrintOptions()
    remaining: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--print":
            opts.enabled = True
            i += 1
        elif arg == "--fit":
            opts.fit = True
            i += 1
        elif arg == "--printer" and i + 1 < len(args):
            opts.enabled = True
            opts.printer = args[i + 1]
            i += 2
        elif arg == "--copies" and i + 1 < len(args):
            try:
                opts.copies = int(args[i + 1])
            except ValueError:
                raise FlagError(f"--copies must be a whole number, got {args[i + 1]!r}") from None
            i += 2
        elif arg == "--media" and i + 1 < len(args):
            opts.media = args[i + 1]
            i += 2
        else:
            remaining.append(arg)
            i += 1

    _apply_defaults(opts, shell)
    return remaining, opts


def _apply_defaults(opts: PrintOptions, shell: StudioProtocol | None) -> None:
    """Fill unset options from the stored ``print.*`` settings."""
    settings = getattr(shell, "settings", None) if shell is not None else None
    if settings is None:
        return
    if not opts.printer:
        opts.printer = settings.get("print.printer")
    if not opts.media:
        opts.media = settings.get("print.media")
    if opts.copies == 1:
        opts.copies = settings.get("print.copies")


def send_to_printer(shell: StudioProtocol, path: str, opts: PrintOptions) -> None:
    """Print *path* if *opts* asks for it, reporting success or failure.

    Codes print at the size the file declares.  A PNG generated with
    ``--size`` carries that measurement in its ``pHYs`` chunk, so the printer
    reproduces it without scaling; ``--fit`` hands sizing to the printer
    instead, for stock whose dimensions the file cannot know.
    """
    if not opts.enabled:
        return

    from pistudio.printing import PrintError, print_file

    try:
        job = print_file(
            path,
            printer=opts.printer or None,
            copies=opts.copies,
            media=opts.media,
            fit_to_page=opts.fit,
            title=f"pistudio {os.path.basename(path)}",
        )
    except PrintError as exc:
        shell.out.error(str(exc))
        return

    target = opts.printer or "the default printer"
    suffix = f" (job {job})" if job else ""
    shell.out.success(f"Sent to {target}{suffix}")
    shell.audit.log("print", path=path, printer=opts.printer or "default", copies=opts.copies)
