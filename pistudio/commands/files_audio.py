"""Audio, QR, and metadata image handlers for the embed command."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

logger = logging.getLogger(__name__)


def write_audio(
    shell: StudioProtocol,
    format_name: str,
    text: str,
    path: str,
    *,
    engine: str = "edge",
    voice: str | None = None,
    rate: str | None = None,
    carrier_path: str | None = None,
    volume_str: str | None = None,
    freq_str: str | None = None,
    encrypt: bool = False,
    key: str | None = None,
) -> None:
    """Handle audio prompt injection formats."""
    t = active_theme()

    # Parse volume
    volume = 0.05  # default for whisper
    if volume_str:
        try:
            volume = float(volume_str)
        except ValueError:
            shell.out.error(f"Invalid --volume value: '{volume_str}'. Expected a float (0.0-1.0)")
            return

    # Parse frequency
    freq = 18500  # default ultrasonic frequency
    if freq_str:
        try:
            freq = int(freq_str)
        except ValueError:
            shell.out.error(f"Invalid --freq value: '{freq_str}'. Expected an integer (Hz)")
            return

    try:
        if format_name == "tts-wav":
            from pistudio.files.audio import write_tts_wav

            with shell.spinner("Generating TTS audio..."):
                write_tts_wav(text, path, engine=engine, voice=voice, rate=rate)

        elif format_name == "tts-whisper":
            from pistudio.files.audio import write_tts_whisper

            with shell.spinner("Generating whisper audio..."):
                write_tts_whisper(
                    text,
                    path,
                    engine=engine,
                    voice=voice,
                    rate=rate,
                    carrier_path=carrier_path,
                    whisper_volume=volume,
                )

        elif format_name == "tts-concat":
            from pistudio.files.audio import write_tts_concat

            with shell.spinner("Generating multi-voice audio..."):
                write_tts_concat(text, path, engine=engine)

        elif format_name == "ultrasonic":
            from pistudio.files.audio import write_ultrasonic

            with shell.spinner("Encoding ultrasonic audio..."):
                write_ultrasonic(
                    text,
                    path,
                    freq_0=freq - 1000,
                    freq_1=freq + 500,
                    carrier_path=carrier_path,
                    encrypt=encrypt,
                    key=key,
                )
            if encrypt:
                shell.out.info(f"  [{t.muted}]Encrypted with AES-256[/]")

        elif format_name == "audio-stego":
            from pistudio.files.audio import write_audio_stego

            write_audio_stego(text, path, carrier_path=carrier_path)

        elif format_name == "spectro-text":
            from pistudio.files.audio import write_spectro_text

            with shell.spinner("Generating spectrogram watermark..."):
                write_spectro_text(text, path)

    except ImportError as e:
        shell.out.error(str(e))
        return
    except Exception as e:
        shell.out.error(f"Failed to generate audio: {e}")
        return

    shell.out.success(f"Audio payload written to: {path}")
    shell.audit.log("embed_generate", format=format_name, path=path)


def write_metadata_image(shell: StudioProtocol, text: str, path: str, fmt) -> None:
    """Write an image with the prompt embedded in metadata only."""
    try:
        from pistudio.files.render_image import write_metadata_image as _write_meta

        img_fmt = "jpeg" if fmt.name == "jpg" else "png"
        _write_meta(text, path, fmt=img_fmt)
    except ImportError as e:
        shell.out.error(str(e))
        return
    except Exception as e:
        shell.out.error(f"Failed to write metadata image: {e}")
        return

    shell.out.success(f"💉 Payload embedded in metadata: {path}")
    shell.audit.log("embed_generate", format=fmt.name, path=path, metadata=True)
