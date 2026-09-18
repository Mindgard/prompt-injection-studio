"""Extended format writers — code, audio, image, 3D, and stub delegates."""

import os

from pistudio.files.formats.writers_stdlib import _check_dep

# The binary STL header is a fixed-width field in the format itself.
STL_HEADER_BYTES = 80

# ── Tier A: Code assistant attack surface (stdlib) ───────────────


def write_py(text: str, path: str) -> None:
    """Write Python file with prompt in docstring and comments."""
    with open(path, "w", encoding="utf-8") as f:
        f.write('"""')
        f.write(text)
        f.write('"""\n\n')
        for line in text.splitlines():
            f.write(f"# {line}\n")


def write_js(text: str, path: str) -> None:
    """Write JavaScript file with prompt in block comment."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("/*\n")
        for line in text.splitlines():
            f.write(f" * {line}\n")
        f.write(" */\n")


def write_toml(text: str, path: str) -> None:
    """Write TOML file with prompt as a config value."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("[default]\n")
        f.write(f'content = "{escaped}"\n')
        f.write('type = "message"\n')


def write_dockerfile(text: str, path: str) -> None:
    """Write Dockerfile with prompt in comment lines."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("FROM scratch\n")
        for line in text.splitlines():
            f.write(f"# {line}\n")
        f.write('LABEL description="payload"\n')


def write_sql(text: str, path: str) -> None:
    """Write SQL file with prompt in comment and INSERT statement."""
    escaped = text.replace("'", "''")
    with open(path, "w", encoding="utf-8") as f:
        for line in text.splitlines():
            f.write(f"-- {line}\n")
        f.write("\n")
        f.write("INSERT INTO messages (content, role) VALUES (\n")
        f.write(f"  '{escaped}',\n")
        f.write("  'user'\n")
        f.write(");\n")


def write_sh(text: str, path: str) -> None:
    """Write shell script with prompt in comments."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\n")
        for line in text.splitlines():
            f.write(f"# {line}\n")


def write_makefile(text: str, path: str) -> None:
    """Write Makefile with prompt in comments."""
    with open(path, "w", encoding="utf-8") as f:
        for line in text.splitlines():
            f.write(f"# {line}\n")
        f.write("\n.PHONY: all\nall:\n\t@echo payload\n")


# ── Tier A: RAG & document pipeline (stdlib) ────────────────────


def write_jsonl(text: str, path: str) -> None:
    """Write JSONL file with prompt as content field."""
    import json

    record = {"content": text, "role": "user", "type": "message"}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_log(text: str, path: str) -> None:
    """Write fake log file with prompt embedded in log entries."""
    import datetime

    ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"[{ts}] INFO  app.main - Application started\n")
        f.write(f"[{ts}] INFO  app.main - Processing request\n")
        for line in text.splitlines():
            f.write(f"[{ts}] DEBUG app.handler - {line}\n")
        f.write(f"[{ts}] INFO  app.main - Request completed\n")


def write_tex(text: str, path: str) -> None:
    """Write LaTeX document with prompt in body."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("\\documentclass{article}\n")
        f.write("\\begin{document}\n")
        f.write(text)
        f.write("\n\\end{document}\n")


# ── Tier A: Audio (optional dep) ────────────────────────────────


def write_mp3(text: str, path: str) -> None:
    """Write MP3 file with prompt in ID3v2 comment and lyrics tags."""
    _check_dep("mutagen", "mutagen", group="embed-audio")
    import mutagen.id3

    # Create a minimal valid MP3 frame (silent, 128kbps, 44100Hz, mono)
    # MPEG1 Layer3 frame header: 0xFFFB9004
    header = b"\xff\xfb\x90\x04"
    # Frame size for 128kbps @ 44100Hz = 417 bytes (including header)
    frame = header + b"\x00" * 413
    # Write a few frames for a valid MP3
    with open(path, "wb") as f:
        for _ in range(10):
            f.write(frame)

    # Add ID3 tags
    tags = mutagen.id3.ID3()
    tags.add(mutagen.id3.COMM(encoding=3, lang="eng", desc="", text=[text]))
    tags.add(mutagen.id3.USLT(encoding=3, lang="eng", desc="", text=text))
    tags.add(mutagen.id3.TIT2(encoding=3, text=["Payload"]))
    tags.save(path)


# ── Tier A: Vision / multimodal (Pillow from [embed]) ──────────


def write_webp(text: str, path: str) -> None:
    """Render prompt as visible text on a WebP image."""
    from pistudio.files.render_image import render_text_image

    _check_dep("PIL", "Pillow")
    # Render as PNG first, then convert
    import tempfile

    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        render_text_image(text, tmp_path, fmt="png")
        img = Image.open(tmp_path)
        img.save(path, format="WEBP", quality=95)
    finally:
        os.unlink(tmp_path)


def write_gif(text: str, path: str) -> None:
    """Render prompt as visible text on a single-frame GIF."""
    from pistudio.files.render_image import render_text_image

    _check_dep("PIL", "Pillow")
    import tempfile

    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        render_text_image(text, tmp_path, fmt="png")
        img = Image.open(tmp_path).convert("P")
        img.save(path, format="GIF")
    finally:
        os.unlink(tmp_path)


def write_bmp(text: str, path: str) -> None:
    """Render prompt as visible text on a BMP image."""
    from pistudio.files.render_image import render_text_image

    _check_dep("PIL", "Pillow")
    import tempfile

    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        render_text_image(text, tmp_path, fmt="png")
        img = Image.open(tmp_path)
        img.save(path, format="BMP")
    finally:
        os.unlink(tmp_path)


# ── Tier A: Jupyter notebooks (optional dep) ────────────────────


def write_ipynb(text: str, path: str) -> None:
    """Write Jupyter notebook with prompt in a markdown cell."""
    _check_dep("nbformat", "nbformat", group="embed-notebook")
    import nbformat

    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_markdown_cell(text))
    nb.cells.append(nbformat.v4.new_code_cell(f"# {text[:80]}"))
    with open(path, "w", encoding="utf-8") as f:
        nbformat.write(nb, f)


# ── Tier B: Additional code languages (stdlib) ──────────────────


def write_ts(text: str, path: str) -> None:
    """Write TypeScript file with prompt in block comment."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("/*\n")
        for line in text.splitlines():
            f.write(f" * {line}\n")
        f.write(" */\n")


def write_java(text: str, path: str) -> None:
    """Write Java file with prompt in Javadoc comment."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("/**\n")
        for line in text.splitlines():
            f.write(f" * {line}\n")
        f.write(" */\n")
        f.write("public class Payload {\n")
        f.write("    // auto-generated\n")
        f.write("}\n")


def write_go(text: str, path: str) -> None:
    """Write Go file with prompt in line comments."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("package main\n\n")
        for line in text.splitlines():
            f.write(f"// {line}\n")


def write_rb(text: str, path: str) -> None:
    """Write Ruby file with prompt in comments."""
    with open(path, "w", encoding="utf-8") as f:
        for line in text.splitlines():
            f.write(f"# {line}\n")


def write_rs(text: str, path: str) -> None:
    """Write Rust file with prompt in line comments."""
    with open(path, "w", encoding="utf-8") as f:
        for line in text.splitlines():
            f.write(f"// {line}\n")


def write_c(text: str, path: str) -> None:
    """Write C file with prompt in block comment."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("/*\n")
        for line in text.splitlines():
            f.write(f" * {line}\n")
        f.write(" */\n")


# ── Tier B: Additional scripting / config (stdlib) ──────────────


def write_bat(text: str, path: str) -> None:
    """Write Windows batch file with prompt in REM comments."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        for line in text.splitlines():
            f.write(f"REM {line}\n")


def write_ps1(text: str, path: str) -> None:
    """Write PowerShell script with prompt in comments."""
    with open(path, "w", encoding="utf-8") as f:
        for line in text.splitlines():
            f.write(f"# {line}\n")


# ── Tier B: Academic (stdlib) ───────────────────────────────────


def write_bib(text: str, path: str) -> None:
    """Write BibTeX entry with prompt in abstract field."""
    escaped = text.replace("{", "\\{").replace("}", "\\}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("@misc{payload,\n")
        f.write("  title = {Payload},\n")
        f.write("  author = {Unknown},\n")
        f.write("  year = {2025},\n")
        f.write(f"  abstract = {{{escaped}}},\n")
        f.write("}\n")


# ── Tier B: Audio (optional deps) ───────────────────────────────


def write_flac(text: str, path: str) -> None:
    """Write FLAC file with prompt in Vorbis comment tag."""
    _check_dep("mutagen", "mutagen", group="embed-audio")
    import struct

    import mutagen.flac

    # Create a minimal FLAC file: header + empty STREAMINFO block
    # fLaC marker + STREAMINFO metadata block (last=1, type=0, length=34)
    streaminfo = (
        b"\x80\x00\x00\x22"  # last block, type 0, length 34
        + b"\x10\x00"  # min block size 4096
        + b"\x10\x00"  # max block size 4096
        + b"\x00\x00\x00"  # min frame size
        + b"\x00\x00\x00"  # max frame size
        + struct.pack(">I", (44100 << 12) | (0 << 9) | (15 << 4) | 0)  # sample rate, channels, bps
        + b"\x00\x00\x00\x00"  # total samples (upper)
        + b"\x00" * 16  # MD5 signature
    )
    with open(path, "wb") as f:
        f.write(b"fLaC" + streaminfo)

    flac = mutagen.flac.FLAC(path)
    flac["comment"] = [text]
    flac["description"] = [text]
    flac.save()


def write_ogg(text: str, path: str) -> None:
    """Write OGG file with prompt in Vorbis comment tag."""
    _check_dep("mutagen", "mutagen", group="embed-audio")

    # OGG Vorbis requires a valid stream; create a minimal one via mutagen
    # Since creating a valid OGG from scratch is complex, we write the
    # prompt into a simple Ogg container with a comment packet.
    # Fallback: write raw bytes with an Ogg page header + Vorbis comment
    import struct

    # Minimal approach: create a file that mutagen can tag
    # We'll use a raw Vorbis-comment-only approach
    with open(path, "wb") as f:
        # OGG page header
        f.write(b"OggS")  # capture pattern
        f.write(b"\x00")  # version
        f.write(b"\x02")  # header type (beginning of stream)
        f.write(b"\x00" * 8)  # granule position
        f.write(struct.pack("<I", 1))  # serial number
        f.write(struct.pack("<I", 0))  # page sequence
        f.write(struct.pack("<I", 0))  # checksum (placeholder)
        # Vorbis identification header
        vorbis_id = (
            b"\x01vorbis"
            + struct.pack("<I", 0)  # version
            + b"\x01"  # channels
            + struct.pack("<I", 44100)  # sample rate
            + struct.pack("<i", 0)  # bitrate max
            + struct.pack("<i", 128000)  # bitrate nominal
            + struct.pack("<i", 0)  # bitrate min
            + b"\xb8"  # blocksize
            + b"\x01"  # framing
        )
        f.write(b"\x01")  # segment count
        f.write(bytes([len(vorbis_id)]))  # segment table
        f.write(vorbis_id)

    # Embed the text as a simple comment in the file metadata
    comment = text.encode("utf-8")
    with open(path, "ab") as f:
        f.write(b"\n# COMMENT: ")
        f.write(comment)


def write_midi(text: str, path: str) -> None:
    """Write MIDI file with prompt as a text event."""
    _check_dep("mido", "mido", group="embed-audio")
    import mido

    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("text", text=text, time=0))
    track.append(mido.MetaMessage("track_name", name="Payload", time=0))
    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(path)


# ── Tier B: OBJ 3D model (stdlib) ──────────────────────────────


def write_obj(text: str, path: str) -> None:
    """Write Wavefront OBJ file with prompt as comment."""
    with open(path, "w", encoding="utf-8") as f:
        for line in text.splitlines():
            f.write(f"# {line}\n")
        f.write("# Minimal geometry\n")
        f.write("v 0.0 0.0 0.0\n")
        f.write("v 1.0 0.0 0.0\n")
        f.write("v 0.0 1.0 0.0\n")
        f.write("f 1 2 3\n")


# ── Tier B: Video (optional dep) ────────────────────────────────


def write_mp4(text: str, path: str) -> None:
    """Write MP4 video with prompt as subtitle track and metadata."""
    _check_dep("moviepy", "moviepy", group="embed-video")
    from moviepy import ColorClip, CompositeVideoClip, TextClip

    # Create a short video with the text rendered as subtitle
    bg = ColorClip(size=(640, 480), color=(0, 0, 0), duration=2.0)
    try:
        txt_clip = TextClip(
            text=text[:200],
            font_size=16,
            color="white",
            size=(600, None),
            method="caption",
            duration=2.0,
        )
        video = CompositeVideoClip([bg, txt_clip.with_position("center")])
    except Exception:
        # Fallback if text rendering fails (no fonts available)
        video = bg
    video.write_videofile(path, fps=1, codec="libx264", audio=False, logger=None)


# ── Tier B: Font (optional dep) ─────────────────────────────────


def write_ttf(text: str, path: str) -> None:
    """Write minimal TrueType font with prompt in name table."""
    _check_dep("fontTools", "fonttools", group="embed-extra")
    from fontTools.fontBuilder import FontBuilder
    from fontTools.ttLib.tables._g_l_y_f import Glyph

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "space"])
    fb.setupCharacterMap({0x20: "space"})
    # Create proper empty Glyph objects
    empty = Glyph()
    empty.numberOfContours = 0
    fb.setupGlyf({".notdef": empty, "space": empty})
    fb.setupHorizontalMetrics({"space": (500, 0), ".notdef": (500, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable(
        {
            "familyName": "Payload",
            "styleName": "Regular",
            # Embed prompt in description and license fields
            10: text,  # description
            13: text,  # license description
        }
    )
    fb.setupOS2()
    fb.setupPost()
    fb.setupHead(unitsPerEm=1000)
    fb.font.save(path)


# ── Tier B: STL 3D model (optional dep) ─────────────────────────


def write_stl(text: str, path: str) -> None:
    """Write binary STL file with the prompt in its 80-byte ASCII header.

    Raises:
        ValueError: If the prompt exceeds the 80 bytes the format allows.
            Silently keeping the first 80 would deliver a truncated payload
            while reporting success.
    """
    _check_dep("numpy", "numpy", group="embed-extra")
    import struct

    import numpy as np

    # The binary STL header is fixed at 80 bytes by the format.
    encoded = text.encode("ascii", errors="replace")
    if len(encoded) > STL_HEADER_BYTES:
        raise ValueError(
            f"Payload too long for an STL header: {len(encoded)} bytes, "
            f"maximum is {STL_HEADER_BYTES}. Shorten it or use another format."
        )
    header = encoded.ljust(STL_HEADER_BYTES, b"\x00")
    # Minimal triangle
    triangle = np.zeros(50, dtype=np.uint8)  # normal(12) + v1(12) + v2(12) + v3(12) + attr(2) = 50
    with open(path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", 1))  # 1 triangle
        f.write(bytes(triangle))


# ── Audio prompt injection stubs (actual logic in embed/audio.py) ──


def _write_tts_wav_stub(text: str, path: str) -> None:
    """Stub writer for tts-wav format -- delegates to audio.write_tts_wav."""
    from pistudio.files.audio import write_tts_wav

    write_tts_wav(text, path)


def _write_tts_whisper_stub(text: str, path: str) -> None:
    """Stub writer for tts-whisper format -- delegates to audio.write_tts_whisper."""
    from pistudio.files.audio import write_tts_whisper

    write_tts_whisper(text, path)


def _write_tts_concat_stub(text: str, path: str) -> None:
    """Stub writer for tts-concat format -- delegates to audio.write_tts_concat."""
    from pistudio.files.audio import write_tts_concat

    write_tts_concat(text, path)


def _write_ultrasonic_stub(text: str, path: str) -> None:
    """Stub writer for ultrasonic format -- delegates to audio.write_ultrasonic."""
    from pistudio.files.audio import write_ultrasonic

    write_ultrasonic(text, path)


def _write_audio_stego_stub(text: str, path: str) -> None:
    """Stub writer for audio-stego format -- delegates to audio.write_audio_stego."""
    from pistudio.files.audio import write_audio_stego

    write_audio_stego(text, path)


def _write_spectro_text_stub(text: str, path: str) -> None:
    """Stub writer for spectro-text format -- delegates to audio.write_spectro_text."""
    from pistudio.files.audio import write_spectro_text

    write_spectro_text(text, path)


def _write_adversarial_audio_stub(text: str, path: str) -> None:
    """Stub writer for adversarial-audio format.

    The real implementation requires extra keyword arguments (carrier_path, model).
    The embed command calls write_adversarial_audio() directly; this stub provides
    a helpful error if called without the required flags.
    """
    raise RuntimeError(
        "The adversarial-audio format requires --carrier <audio>. "
        'Use: audio adversarial-audio "target phrase" --carrier input.wav'
    )


# ── Anamorpher stub (actual logic in embed/anamorpher.py) ────────


def _write_anamorph_stub(text: str, path: str) -> None:
    """Stub writer for the anamorph format.

    The real implementation lives in ``pistudio.files.anamorpher``
    and requires extra keyword arguments (``decoy_path``, ``algorithm``,
    etc.).  The embed command calls ``write_anamorph()`` directly when
    the format is ``anamorph``; this stub exists only so the registry
    entry has a valid callable and provides a helpful error if called
    without the required flags.
    """
    raise RuntimeError(
        'The anamorph format requires --decoy <image>. Use: file anamorph "prompt text" --decoy cover.png'
    )


def write_cert(text: str, path: str) -> None:
    """Write a self-signed X.509 certificate carrying *text* in a SAN.

    Unlike the other parameterised formats, every option has a working default
    -- the payload rides in a SAN dNSName, which has no RFC 5280 length bound
    -- so this honours the plain ``(text, path)`` writer signature and needs no
    stub. The ``file`` command passes overrides when the cert flags are given.

    The certificate is self-signed and written locally; nothing is transmitted
    and nothing should trust it.
    """
    from pistudio.carriers.certs import generate

    generate(text, path)
