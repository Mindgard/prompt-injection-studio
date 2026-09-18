"""Send generated payloads to a printer via CUPS.

Printing a payload turns it into something you can leave on a desk, stick to
a device, or hand to someone — a QR code a phone camera will read into an
agent, or a document a scanning pipeline will ingest.

CUPS is used rather than a vendor SDK so the same code drives an office
laser and a label printer such as the Brother QL series.  ``lp`` already
knows how to rasterise PNG, PDF, PostScript and plain text; formats it
cannot interpret are refused rather than spooled as garbage.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

__all__ = [
    "PRINTABLE_EXTENSIONS",
    "PrintError",
    "PrinterInfo",
    "default_printer",
    "is_printable",
    "list_printers",
    "print_file",
]

logger = logging.getLogger(__name__)

# Extensions CUPS can rasterise without help.  Anything else (audio, video,
# archives, binary carriers) is refused — spooling it would waste a page and
# confuse the user rather than fail cleanly.
PRINTABLE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tiff",
        ".pdf",
        ".ps",
        ".txt",
        ".md",
        ".csv",
        ".html",
        ".htm",
        ".xml",
        ".json",
        ".yaml",
        ".yml",
        ".log",
        ".ini",
        ".toml",
        ".tex",
        ".svg",
    }
)

_TIMEOUT = 30


class PrintError(RuntimeError):
    """Raised when a print job cannot be submitted."""


@dataclass(frozen=True)
class PrinterInfo:
    """A CUPS print destination."""

    name: str
    is_default: bool = False
    status: str = ""


def _require_cups() -> str:
    """Return the path to ``lp``, or raise if CUPS is unavailable."""
    lp = shutil.which("lp")
    if lp is None:
        raise PrintError(
            "No CUPS printing system found ('lp' is not on PATH).\n"
            "  macOS and most Linux desktops ship CUPS; on a server try "
            "installing the 'cups-client' package."
        )
    return lp


def list_printers() -> list[PrinterInfo]:
    """Return the configured CUPS destinations.

    Returns an empty list when CUPS is present but has no printers, and also
    when CUPS is missing — callers report that through :func:`default_printer`.
    """
    if shutil.which("lpstat") is None:
        return []

    try:
        result = subprocess.run(
            ["lpstat", "-p", "-d"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("lpstat failed", exc_info=True)
        return []

    default_name = ""
    names: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        if line.startswith("printer "):
            parts = line.split(maxsplit=2)
            if len(parts) >= 2:
                names.append((parts[1], parts[2] if len(parts) > 2 else ""))
        elif line.startswith("system default destination:"):
            default_name = line.split(":", 1)[1].strip()

    return [PrinterInfo(name=n, is_default=(n == default_name), status=s.strip()) for n, s in names]


def default_printer() -> str | None:
    """Return the default printer name, or None if nothing is configured."""
    for p in list_printers():
        if p.is_default:
            return p.name
    printers = list_printers()
    return printers[0].name if printers else None


def is_printable(path: str) -> bool:
    """Return True if CUPS can be expected to render *path*."""
    import os

    return os.path.splitext(path)[1].lower() in PRINTABLE_EXTENSIONS


def print_file(
    path: str,
    printer: str | None = None,
    copies: int = 1,
    media: str = "",
    fit_to_page: bool = False,
    title: str = "",
) -> str:
    """Submit *path* to a printer and return the CUPS job id.

    Args:
        path: File to print.
        printer: Destination name.  The CUPS default is used when omitted.
        copies: Number of copies.
        media: Media/page size, e.g. ``A4`` or ``Custom.62x100mm`` for
            label stock.  Without it the job inherits the queue default,
            which on a label printer may be a much smaller die-cut size than
            the roll actually loaded.
        fit_to_page: Scale the image to fill the media.  Leave off for an
            image that declares its own physical size — fitting overrides
            that measurement.
        title: Job title shown in the print queue.

    Returns:
        The job id reported by CUPS, or an empty string if it did not give one.

    Raises:
        PrintError: If the file is missing, not printable, or the job is
            rejected.
    """
    import os

    lp = _require_cups()

    if not os.path.isfile(path):
        raise PrintError(f"Nothing to print — {path} does not exist.")

    if not is_printable(path):
        ext = os.path.splitext(path)[1] or "(no extension)"
        raise PrintError(
            f"Cannot print {ext} files — CUPS has no renderer for them.\n"
            f"  Printable: {', '.join(sorted(PRINTABLE_EXTENSIONS))}"
        )

    if copies < 1:
        raise PrintError(f"copies must be at least 1, got {copies}")

    target = printer or default_printer()
    if target is None:
        raise PrintError(
            "No printer configured.\n  Add one in your system settings, or run 'lpstat -p' to check what CUPS can see."
        )

    cmd = [lp, "-d", target]
    if copies > 1:
        cmd += ["-n", str(copies)]
    if media:
        cmd += ["-o", f"media={media}"]
    # `scaling` is a percentage of the *page*, not of natural size, so the
    # scaling=100 that used to be sent here meant "fill the media" -- and on a
    # queue defaulting to a small die-cut label that shrank every code.  To
    # honour the size an image declares in its pHYs chunk, send no scaling
    # option at all and let CUPS read the file's own resolution.
    if fit_to_page:
        cmd += ["-o", "fit-to-page"]
    if title:
        cmd += ["-t", title]
    cmd.append(path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        raise PrintError(f"Print command timed out after {_TIMEOUT}s") from exc
    except OSError as exc:
        raise PrintError(f"Could not run lp: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise PrintError(f"Printer '{target}' rejected the job: {detail or 'unknown error'}")

    # lp prints e.g. "request id is Brother-42 (1 file(s))"
    out = result.stdout.strip()
    job_id = ""
    if "request id is" in out:
        job_id = out.split("request id is", 1)[1].strip().split()[0]
    return job_id
