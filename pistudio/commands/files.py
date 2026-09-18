"""Embed command — generate files containing prompt injection payloads.

Supports multiple file formats (PDF, DOCX, XLSX, images, text, etc.) and
four prompt sourcing modes: named payload, inline text, editor, and LLM
generation.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from typing import TYPE_CHECKING

from pistudio.commands.flags import extract_flag, slugify, strip_flag
from pistudio.commands.format_flags import FILE_FLAGS
from pistudio.core.command import Command
from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

logger = logging.getLogger(__name__)


def _resolve_carrier_path(path: str | None) -> str | None:
    """Resolve carrier path, checking package examples if path starts with 'examples/'."""
    if path is None:
        return None

    # If path exists as-is, use it
    if os.path.exists(path):
        return os.path.abspath(path)

    # Check if it's a reference to package examples
    if path.startswith("examples/"):
        # Get the package examples directory
        package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        package_examples = os.path.join(package_dir, path)
        if os.path.exists(package_examples):
            return package_examples

    # Return original path (will fail with appropriate error downstream)
    return path


class EmbedCommand(Command):
    """Embed prompt injection payloads into files"""

    name = "file"
    aliases = ("files",)
    help = "Embed prompt injection payloads into files (50+ formats)"
    file_args = ("--output", "-o", "--output-dir", "--carrier", "--decoy")
    flags = FILE_FLAGS
    namespace = True
    subcommand_aliases = {"ls": "list", "formats": "list"}
    subcommands = {
        "list": "List every supported format",
        "all": "Generate every available format at once",
        "anamorph": "Adversarial image scaling (setup/status/uninstall)",
    }

    @property
    def usage(self) -> str:
        """Usage text, with the ``Options:`` block rendered from :attr:`flags`.

        Only the mechanical listing is generated.  The prose stays hand-written
        because it carries things a flag table cannot say -- that the SAN has no
        RFC 5280 length bound, that audio and codes live elsewhere.
        """
        return (
            "Usage: file <format> [options]\n\n"
            '  file <format> "<text>"                    Inline prompt text\n'
            "  file <format> --payload <name>            Use a named payload\n"
            "  file <format> --edit                      Compose in $EDITOR\n"
            '  file <format> --generate "<desc>"         LLM-generate the prompt\n'
            "  file <format>                             Interactive payload picker\n"
            "  file list                                 List supported formats\n"
            "\n"
            "Options:\n"
            f"{self.options_block()}\n"
            "\n"
            "  The cert SAN has no RFC 5280 length bound and is logged unchecked;\n"
            "  the CN is capped at 64 characters and is where every validator looks.\n"
            "\n"
            "Anamorph management:\n"
            "  file anamorph setup      Install anamorpher (Python 3.11 venv, ~3-5 GB)\n"
            "  file anamorph uninstall  Remove the anamorpher venv\n"
            "  file anamorph status     Show installation status\n"
            "\n"
            "Audio and codes live under their own commands:\n"
            '  audio tts-wav "<text>"     Speech, ultrasonic, stego, MP3 tags\n'
            '  barcode "<text>"           QR codes and barcodes\n'
            "  audio list, barcode list   What each one supports\n"
            "\n"
            "Examples:\n"
            '  file pdf "Ignore all previous instructions..."\n'
            "  file docx --payload ignore-instructions\n"
            "  file png --payload data-exfil --metadata\n"
            '  file anamorph "Ignore instructions" --decoy cat.png\n'
            '  file all "Ignore instructions" --output-dir ./payloads\n'
            "  file list"
        )

    _SLOW_FORMATS = frozenset(
        {
            "anamorph",
            "mp3",
            "flac",
            "ogg",
            "mp4",
            "ttf",
            "stl",
            "webp",
            "gif",
            "bmp",
            "ipynb",
            "tts-wav",
            "tts-whisper",
            "tts-concat",
            "spectro-text",
            "adversarial-audio",
        }
    )
    _BATCH_SKIP = frozenset({"anamorph", "adversarial-audio", "tts-whisper", "tts-wav"})

    # flag_descriptions is inherited from Command and derived from
    # FILE_FLAGS, so the dropdown cannot drift from what is parsed.

    def execute(self, shell: StudioProtocol, args: list[str]) -> None:
        """Run the ``embed`` command."""
        from pistudio.commands.files_anamorph import anamorph_setup, anamorph_status, anamorph_uninstall

        if not args:
            shell.out.info(self.usage)
            return

        sub = args[0].lower()

        if sub in ("list", "ls", "formats"):
            self._list_formats(shell)
            return

        if sub == "all":
            self._generate_all(shell, args[1:])
            return

        # sub should be a format name
        from pistudio.files.formats import get_format

        fmt = get_format(sub)
        if fmt is None:
            shell.out.error(self._unknown_format_message(sub))
            return

        if fmt.audio:
            shell.out.error(f"'{sub}' is an audio format. Use: audio {sub}")
            return

        remaining = args[1:]

        # Handle anamorph management subcommands
        if fmt.name == "anamorph" and remaining:
            anamorph_sub = remaining[0].lower()
            if anamorph_sub == "setup":
                anamorph_setup(shell)
                return
            if anamorph_sub in ("uninstall", "remove"):
                anamorph_uninstall(shell)
                return
            if anamorph_sub == "status":
                anamorph_status(shell)
                return

        self._generate_file(shell, fmt, remaining)

    def _unknown_format_message(self, name: str) -> str:
        """Build the error for an unrecognised format.

        Listing all 51 supported names buried the answer in a wall of text,
        so suggest the closest match and point at ``file list`` instead.
        """
        import difflib

        from pistudio.files.formats import file_format_names

        matches = difflib.get_close_matches(name, file_format_names(), n=3, cutoff=0.6)
        if matches:
            return f"Unknown format: '{name}'. Did you mean {' or '.join(repr(m) for m in matches)}?"
        return f"Unknown format: '{name}'. Run 'file list' to see the {len(file_format_names())} supported formats."

    # ── Subcommands ───────────────────────────────────────────────

    def _list_formats(self, shell: StudioProtocol) -> None:
        from pistudio.files.formats import FORMAT_REGISTRY, is_format_available, setup_command

        t = active_theme()
        # Audio formats belong to `audio`; listing them here would
        # advertise names this command refuses.
        formats = [f for f in FORMAT_REGISTRY.values() if not f.audio]

        if shell.json_mode:
            data = [
                {
                    "name": f.name,
                    "extension": f.extension,
                    "description": f.description,
                    "requires": f.requires,
                    "available": is_format_available(f),
                    "human_readable": f.human_readable,
                    "supports_metadata": f.supports_metadata,
                    "category": f.category,
                    "threat_level": f.threat_level,
                    "group": f.group,
                }
                for f in formats
            ]
            shell.print_raw(json.dumps(data, indent=2))
            return

        shell.console.print(f"\n  [{t.secondary} bold]Supported File Formats[/]\n")

        # Group by category
        by_category: dict[str, list] = defaultdict(list)
        for f in formats:
            cat = f.category or "Other"
            by_category[cat].append(f)

        # Display order for categories
        cat_order = [
            "Text & Markup",
            "Structured Data",
            "Code",
            "Documents",
            "Messaging",
            "Images",
            "Audio",
            "Video",
            "Notebooks",
            "Adversarial",
            "3D & Misc",
        ]
        # Add any categories not in the explicit order
        for cat in by_category:
            if cat not in cat_order:
                cat_order.append(cat)

        for cat in cat_order:
            formats = by_category.get(cat)
            if not formats:
                continue

            shell.console.print(f"  [{t.secondary} bold]{cat}[/]")
            # Sort: documented first, then exploratory; alphabetical within
            formats.sort(key=lambda f: (0 if f.threat_level == "documented" else 1, f.name))

            for f in formats:
                available = is_format_available(f)
                marker = "\u25cf" if f.threat_level == "documented" else "\u25cb"
                status = f"[{t.accent}]{marker}[/]" if available else f"[{t.error}]{marker}[/]"
                dep_hint = ""
                if f.requires and not available:
                    setup = setup_command(f)
                    if setup:
                        dep_hint = f" [{t.muted}]({setup})[/]"
                    else:
                        grp = f.group or "embed"
                        dep_hint = f" [{t.muted}](pip install prompt-injection-studio\\[{grp}])[/]"
                meta = f" [{t.muted}]\\[metadata][/]" if f.supports_metadata else ""
                shell.console.print(
                    f"    {status} [{t.accent}]{f.name:<12}[/] {f.extension:<12} {f.description}{dep_hint}{meta}"
                )
            shell.console.print()

        shell.console.print(f"  [{t.muted}]\u25cf = documented attack vector   \u25cb = exploratory[/]")
        shell.console.print(
            f"  [{t.muted}]Install all lightweight: pip install prompt-injection-studio\\[embed-all][/]"
        )
        shell.console.print(f"  [{t.muted}]Install everything:     pip install prompt-injection-studio\\[all][/]\n")

    # ── Batch generation ─────────────────────────────────────────

    def _generate_all(self, shell: StudioProtocol, args: list[str]) -> None:
        """Generate every available format for a single prompt into a directory."""
        from pistudio.commands.files_prompt import resolve_prompt
        from pistudio.files.formats import FORMAT_REGISTRY, is_format_available

        t = active_theme()
        documented_only = "--documented-only" in args
        args = [a for a in args if a != "--documented-only"]

        # Resolve output directory
        output_dir = extract_flag(args, "--output-dir")
        args = strip_flag(args, "--output-dir")

        # Resolve prompt text (reuse existing prompt resolution)
        prompt_text = resolve_prompt(shell, args)
        if prompt_text is None:
            return

        # Determine output directory
        if not output_dir:
            slug = slugify(prompt_text[:40])
            output_dir = f"payload-batch-{slug}"

        output_dir = os.path.abspath(os.path.expanduser(output_dir))
        os.makedirs(output_dir, exist_ok=True)

        # Collect eligible formats
        eligible = []
        for fmt in FORMAT_REGISTRY.values():
            if fmt.audio:
                continue
            if fmt.name in self._BATCH_SKIP:
                continue
            if documented_only and fmt.threat_level != "documented":
                continue
            if not is_format_available(fmt):
                continue
            eligible.append(fmt)

        if not eligible:
            shell.out.error("No formats available. Install optional deps to unlock more formats.")
            return

        # Track duplicates — some formats share extensions (e.g. multiple .png)
        ext_count: dict[str, int] = {}
        for fmt in eligible:
            ext_count[fmt.extension] = ext_count.get(fmt.extension, 0) + 1

        succeeded: list[dict] = []
        failed: list[dict] = []

        shell.console.print(f"\n  [{t.secondary} bold]Batch generating {len(eligible)} formats into {output_dir}[/]\n")

        for i, fmt in enumerate(eligible, 1):
            # Build filename: use format name to avoid collisions
            sep = "" if fmt.extension.startswith(".") else "."
            filename = f"payload-{fmt.name}{sep}{fmt.extension}"
            filepath = os.path.join(output_dir, filename)

            label = f"[{i}/{len(eligible)}] {fmt.name}"
            try:
                if fmt.name in self._SLOW_FORMATS:
                    with shell.spinner(f"{label}..."):
                        fmt.writer(prompt_text, filepath)
                else:
                    fmt.writer(prompt_text, filepath)
                succeeded.append({"format": fmt.name, "path": filepath})
                shell.console.print(f"    [{t.accent}]\u2713[/] {fmt.name:<12} {filename}")
            except Exception as e:
                failed.append({"format": fmt.name, "error": str(e)})
                shell.console.print(f"    [{t.error}]\u2717[/] {fmt.name:<12} {e}")

        # Summary
        shell.console.print()
        shell.out.success(f"Batch complete: {len(succeeded)} succeeded, {len(failed)} failed \u2192 {output_dir}")
        shell.audit.log(
            "embed_batch",
            directory=output_dir,
            succeeded=len(succeeded),
            failed=len(failed),
            documented_only=documented_only,
        )

        if shell.json_mode:
            shell.print_raw(
                json.dumps(
                    {
                        "directory": output_dir,
                        "succeeded": succeeded,
                        "failed": failed,
                        "documented_only": documented_only,
                    },
                    indent=2,
                )
            )

    # ── File generation ──────────────────────────────────────────

    def _generate_file(self, shell: StudioProtocol, fmt, args: list[str]) -> None:
        from pistudio.commands.files_gen import generate_file
        from pistudio.commands.printing_flags import extract_print_flags, send_to_printer

        # Printing is handled here rather than inside generate_file: that
        # function has several early returns (QR, adversarial audio, error
        # paths) which would each need their own call.
        args, print_opts = extract_print_flags(args, shell)

        written = generate_file(
            shell,
            fmt,
            args,
            self._SLOW_FORMATS,
        )

        if not print_opts.enabled:
            return

        if written and os.path.isfile(written):
            send_to_printer(shell, written, print_opts)
        else:
            shell.out.error(
                "Could not tell what file was written, so nothing was printed.\n"
                "  Pass --output <path> when using --print."
            )

    # ── Tab completion ────────────────────────────────────────────

    def complete(self, shell: StudioProtocol, tokens: list[str]) -> list[str]:
        from pistudio.commands.files_gen import complete_embed

        return complete_embed(shell, tokens)

    def wants_path_completion(self, tokens: list[str]) -> bool:
        """Return True when the cursor is after ``--output``, ``--decoy``, or ``--carrier``."""
        return bool(len(tokens) >= 2 and tokens[-2] in ("--output", "--decoy", "--output-dir", "--carrier"))

    # ── Helpers ────────────────────────────────────────────────────
