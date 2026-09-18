"""Embed file generation and tab completion helpers.

Extracted from the EmbedCommand class to keep file sizes manageable.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol
    from pistudio.files.formats.types import FileFormat


def generate_file(  # noqa: C901
    shell: StudioProtocol,
    fmt: FileFormat,
    args: list[str],
    slow_formats: set[str],
) -> str | None:
    """Generate a single payload file in *fmt*.

    Returns:
        The path written, or None if generation was cancelled or failed.
    """
    from pistudio.commands.encode_apply import apply_encoding
    from pistudio.commands.files import _resolve_carrier_path as resolve_carrier_path
    from pistudio.commands.files_adversarial import write_adversarial_audio
    from pistudio.commands.files_anamorph import write_anamorph
    from pistudio.commands.files_audio import write_audio, write_metadata_image
    from pistudio.commands.files_prompt import prompt_output_path, resolve_prompt
    from pistudio.commands.flags import extract_flag, slugify, strip_flag
    from pistudio.commands.format_flags import explain_unsupported, unsupported_flags

    # Checked before anything is parsed or written: a flag that reaches no
    # code path should stop the command, not be dropped on the floor.
    wrong = unsupported_flags(fmt.name, args)
    if wrong:
        shell.out.error(explain_unsupported(fmt.name, wrong))
        return

    t = active_theme()
    metadata_mode = "--metadata" in args
    args = [a for a in args if a != "--metadata"]

    # Extract --url flag for hosting on inject server
    host_url = "--url" in args
    args = [a for a in args if a != "--url"]

    # Extract anamorph-specific flags
    decoy_path = extract_flag(args, "--decoy")
    args = strip_flag(args, "--decoy")
    algorithm = extract_flag(args, "--algorithm") or "nearest"
    args = strip_flag(args, "--algorithm")
    lam_str = extract_flag(args, "--lambda")
    args = strip_flag(args, "--lambda")
    target_size_str = extract_flag(args, "--target-size")
    args = strip_flag(args, "--target-size")

    # Extract cert-specific flags
    cert_field = extract_flag(args, "--cert-field")
    args = strip_flag(args, "--cert-field")
    cert_cn = extract_flag(args, "--cn")
    args = strip_flag(args, "--cn")
    cert_days = extract_flag(args, "--days")
    args = strip_flag(args, "--days")
    cert_key_size = extract_flag(args, "--key-size")
    args = strip_flag(args, "--key-size")

    # Extract audio-specific flags
    carrier_path = resolve_carrier_path(extract_flag(args, "--carrier"))
    args = strip_flag(args, "--carrier")
    engine = extract_flag(args, "--engine") or "edge"
    args = strip_flag(args, "--engine")
    voice = extract_flag(args, "--voice")
    args = strip_flag(args, "--voice")
    rate = extract_flag(args, "--rate")
    args = strip_flag(args, "--rate")
    volume_str = extract_flag(args, "--volume")
    args = strip_flag(args, "--volume")
    freq_str = extract_flag(args, "--freq")
    args = strip_flag(args, "--freq")
    encrypt = "--encrypt" in args
    args = [a for a in args if a != "--encrypt"]
    key = extract_flag(args, "--key")
    args = strip_flag(args, "--key")
    model = extract_flag(args, "--model") or "whisper"
    args = strip_flag(args, "--model")

    encode_chain = extract_flag(args, "--encode")
    args = strip_flag(args, "--encode")

    # Resolve output path
    output_path = extract_flag(args, "--output")
    args = strip_flag(args, "--output")

    # Resolve prompt text
    prompt_text = resolve_prompt(shell, args)
    if prompt_text is None:
        return

    # Encode before any format branch runs, so every carrier -- files, audio,
    # anamorph, image metadata -- receives the transformed payload.
    if encode_chain:
        encoded = apply_encoding(shell, prompt_text, encode_chain)
        if encoded is None:
            return
        prompt_text = encoded

    # Determine output path
    if not output_path:
        slug = slugify(prompt_text[:40])
        default_name = f"payload-{slug}{fmt.extension}"
        output_path = prompt_output_path(shell, default_name, fmt)
        if output_path is None:
            return

    output_path = os.path.abspath(os.path.expanduser(output_path))

    # For human-readable formats, offer to display first
    if fmt.human_readable and not shell.json_mode:
        shell.console.print(f"\n  [{t.secondary}]Prompt text:[/]")
        for line in prompt_text.splitlines():
            shell.console.print(f"    {line}")
        shell.console.print()

    # Handle metadata mode for images
    if metadata_mode and fmt.supports_metadata:
        write_metadata_image(shell, prompt_text, output_path, fmt)
        return
    elif metadata_mode and not fmt.supports_metadata:
        shell.out.error(f"--metadata is not supported for {fmt.name} format.")
        return

    # Handle anamorph format specially
    if fmt.name == "anamorph":
        write_anamorph(shell, prompt_text, output_path, decoy_path, algorithm, lam_str, target_size_str)
        return

    # The cert writer defaults every option, so it only needs the special case
    # when an override is actually given.
    if fmt.name == "cert" and any((cert_field, cert_cn, cert_days, cert_key_size)):
        from pistudio.commands.files_cert import write_cert_with_options

        write_cert_with_options(shell, prompt_text, output_path, cert_field, cert_cn, cert_days, cert_key_size)
        return

    # Handle audio formats specially
    if fmt.name in ("tts-wav", "tts-whisper", "tts-concat", "ultrasonic", "audio-stego", "spectro-text"):
        write_audio(
            shell,
            fmt.name,
            prompt_text,
            output_path,
            engine=engine,
            voice=voice,
            rate=rate,
            carrier_path=carrier_path,
            volume_str=volume_str,
            freq_str=freq_str,
            encrypt=encrypt,
            key=key,
        )
        return

    # Handle adversarial-audio format specially
    if fmt.name == "adversarial-audio":
        write_adversarial_audio(shell, prompt_text, output_path, carrier_path, model)
        return output_path

    # Write the file (with spinner for slow formats)
    try:
        if fmt.name in slow_formats:
            with shell.spinner(f"Generating {fmt.description}..."):
                fmt.writer(prompt_text, output_path)
        else:
            fmt.writer(prompt_text, output_path)
    except ImportError as e:
        shell.out.error(str(e))
        return
    except Exception as e:
        shell.out.error(f"Failed to write {fmt.name} file: {e}")
        return

    shell.out.success(f"Payload written to: {output_path}")
    shell.audit.log("embed_generate", format=fmt.name, path=output_path)
    # Host on inject server if --url flag was provided
    hosted_url = None
    if host_url:
        hosted_url = host_file_on_server(shell, output_path, fmt)

    if shell.json_mode:
        result = {
            "format": fmt.name,
            "path": output_path,
            "metadata_mode": metadata_mode,
        }
        if hosted_url:
            result["url"] = hosted_url
        shell.print_raw(json.dumps(result, indent=2))

    return output_path


def host_file_on_server(shell: StudioProtocol, file_path: str, fmt: FileFormat) -> str | None:
    """Host a generated file on the inject server.

    Auto-starts the server if not running.
    Returns the hosted URL, or None if hosting failed.
    """
    import mimetypes

    from pistudio.serve.registry import get_registry
    from pistudio.serve.server import PayloadServer, get_server_status

    t = active_theme()

    # Check if server is running, auto-start if not
    status = get_server_status()
    if status is None:
        try:
            server = PayloadServer(host="127.0.0.1", port=8080, tls=False)
            server.start()
            shell.console.print(f"  [{t.success}]\u2713[/] Auto-started inject server at {server.url}")
            status = get_server_status()
        except Exception as e:
            shell.out.error(f"Failed to auto-start inject server: {e}")
            return None

    server_url = status[1]

    try:
        with open(file_path, "rb") as f:
            content = f.read()
    except Exception as e:
        shell.out.error(f"Failed to read file for hosting: {e}")
        return None

    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = getattr(fmt, "mime_type", "application/octet-stream")

    filename = os.path.basename(file_path)

    try:
        registry = get_registry()
        hosted = registry.add_file(
            content=content,
            filename=filename,
            content_type=content_type,
            name=fmt.name,
        )
        hosted_url = f"{server_url}/p/{hosted.slug}"
        shell.console.print(f"  [{t.success}]\u2713[/] Hosted at: [{t.accent}]{hosted_url}[/]")
        shell.audit.log("embed_host", slug=hosted.slug, url=hosted_url)
        return hosted_url
    except Exception as e:
        shell.out.error(f"Failed to host file: {e}")
        return None


def complete_embed(shell: StudioProtocol, tokens: list[str]) -> list[str]:
    """Return tab-completion candidates for ``embed``."""
    from pistudio.files.formats import file_format_names

    formats = file_format_names()
    top_subs = ["all", "list", "formats"] + formats

    if not tokens or (len(tokens) == 1 and not tokens[0].strip()):
        return top_subs

    if len(tokens) == 1:
        return [s for s in top_subs if s.startswith(tokens[0])]

    first = tokens[0].lower()
    if first == "all":
        flags = ["--payload", "--edit", "--generate", "--output-dir", "--documented-only"]
        if len(tokens) >= 2:
            current = tokens[-1]
            used = set(tokens[1:])
            available = [f for f in flags if f not in used]
            if tokens[-2] == "--payload":
                from pistudio.hardware.payloads import list_payloads

                try:
                    payloads = list_payloads(shell.session_dir)
                    names = [p.name for p, _ in payloads]
                    return [n for n in names if n.startswith(current)]
                except Exception:
                    return []
            return [f for f in available if f.startswith(current)]
        return flags

    if first in formats:
        flags = ["--payload", "--edit", "--generate", "--output", "--url", "--metadata"]
        if first == "anamorph":
            flags.extend(["--decoy", "--algorithm", "--lambda", "--target-size"])
            anamorph_subs = ["setup", "uninstall", "status"]
            if len(tokens) == 2:
                current = tokens[1]
                all_opts = flags + anamorph_subs
                return [o for o in all_opts if o.startswith(current)]
        if first == "cert":
            flags.extend(["--cert-field", "--cn", "--days", "--key-size"])
            if tokens[-2] == "--cert-field":
                from pistudio.commands.files_cert import cert_field_names

                return [f for f in cert_field_names() if f.startswith(tokens[-1])]
            if tokens[-2] == "--days":
                return [d for d in ("1", "30", "365", "3650") if d.startswith(tokens[-1])]
            if tokens[-2] == "--key-size":
                return [k for k in ("2048", "3072", "4096") if k.startswith(tokens[-1])]

        if len(tokens) >= 2:
            current = tokens[-1]
            used = set(tokens[1:])
            available = [f for f in flags if f not in used]

            if tokens[-2] == "--payload":
                from pistudio.hardware.payloads import list_payloads

                try:
                    payloads = list_payloads(shell.session_dir)
                    names = [p.name for p, _ in payloads]
                    return [n for n in names if n.startswith(current)]
                except Exception:
                    return []

            if tokens[-2] == "--algorithm":
                algs = ["nearest", "bicubic", "bilinear"]
                return [a for a in algs if a.startswith(current)]

            if tokens[-2] == "--engine":
                engines = ["edge", "gtts", "pyttsx3", "openai"]
                return [e for e in engines if e.startswith(current)]

            if tokens[-2] == "--model":
                models = ["whisper", "deepspeech"]
                return [m for m in models if m.startswith(current)]

            if tokens[-2] == "--error-level":
                levels = ["L", "M", "Q", "H"]
                return [lev for lev in levels if lev.startswith(current.upper())]

            return [f for f in available if f.startswith(current)]

    return []
