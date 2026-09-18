"""Read a payload back out of a file the writers produced.

Every writer in the registry embeds a payload into a carrier. Nothing
previously read one back, so a writer could stop embedding the payload — or
embed a mangled one — and the tests would still pass: they only checked that
the registry listed the format. The Flipper's NDEF encoder failed exactly this
way, printing success while writing a file the device could not load.

These decoders exist to make that class of failure visible. They are test
scaffolding rather than a user-facing feature, so they cover what the writers
produce, not the full generality of each format: the PDF reader understands
the PDFs this tool emits, not arbitrary ones.

Carriers fall into four groups, and "recoverable" means something different
for each:

``text``
    The payload is in the file's bytes (``.py``, ``.json``, ``.md``).
``archive``
    The payload is inside a zipped part (``.docx``, ``.epub``, ``.pptx``).
``stream``
    The payload is in a compressed object (``.pdf``).
``raster``
    The payload is drawn as pixels (``.png``, ``.jpg``). Bytes cannot be
    matched; the check is that text was actually rendered.
"""

import contextlib
import pathlib
import re
import struct
import zipfile
import zlib

# Formats whose bytes contain the payload directly.
TEXT_FORMATS = frozenset(
    {
        "bat",
        "bib",
        "c",
        "csv",
        "dockerfile",
        "env",
        "go",
        "html",
        "ics",
        "ini",
        "java",
        "js",
        "json",
        "jsonl",
        "log",
        "makefile",
        "md",
        "obj",
        "ps1",
        "py",
        "rb",
        "rs",
        "rtf",
        "sh",
        "sql",
        "svg",
        "tex",
        "toml",
        "ts",
        "txt",
        "vcf",
        "xml",
        "yaml",
    }
)

# Formats that are zip containers with the payload in one of the parts.
# ipynb is JSON on disk despite being a document format, so it is not here.
ARCHIVE_FORMATS = frozenset({"docx", "epub", "odt", "pptx", "xlsx"})

# Formats that rasterise the payload into pixels.
RASTER_FORMATS = frozenset({"bmp", "gif", "jpg", "png", "tiff", "webp"})

# Formats that encode the payload into a signal rather than into bytes or
# pixels: LSBs of PCM samples, an FSK tone pair, or a spectrogram image.
# Recovering these needs a demodulator, so they are checked by their own
# dedicated tests rather than the generic round trip.
SIGNAL_FORMATS = frozenset({"audio-stego", "ultrasonic", "spectro-text"})


class NotRecoverable(Exception):
    """The payload could not be read back out of the carrier."""


def extract_text(path: str) -> str:
    """Return the payload text embedded in *path*, chosen by extension.

    Args:
        path: File written by one of the registry's writers.

    Returns:
        The recovered text.

    Raises:
        NotRecoverable: If the carrier holds no readable text.
    """
    suffix = pathlib.Path(path).suffix.lstrip(".").lower()

    if suffix == "pdf":
        return extract_pdf(path)
    if suffix in ARCHIVE_FORMATS:
        return extract_archive(path)
    if suffix == "eml":
        return extract_eml(path)
    if suffix == "svg":
        return extract_svg(path)

    return pathlib.Path(path).read_bytes().decode("utf-8", errors="replace")


def extract_svg(path: str) -> str:
    """Return the text of an SVG, rejoining word-wrapped spans.

    The writer wraps at roughly 60 characters into separate ``<tspan>``
    elements, so the payload spans several of them and is not a contiguous
    substring of the markup.
    """
    from xml.sax.saxutils import unescape as xml_unescape

    raw = pathlib.Path(path).read_text(encoding="utf-8")
    spans = re.findall(r"<tspan[^>]*>(.*?)</tspan>", raw, re.S)
    if not spans:
        return raw
    return xml_unescape(" ".join(span.strip() for span in spans))


def extract_eml(path: str) -> str:
    """Return the decoded body of an email, headers included.

    The writer base64-encodes the body per MIME, so the payload is not in the
    file's bytes even though the file is plain text.
    """
    import email
    import email.policy

    message = email.message_from_bytes(pathlib.Path(path).read_bytes(), policy=email.policy.default)
    parts = [str(message.get(header, "")) for header in ("Subject", "From", "To")]
    for part in message.walk():
        if part.get_content_maintype() == "text":
            parts.append(part.get_content())
    return "\n".join(parts)


def extract_archive(path: str) -> str:
    """Concatenate every text-bearing part of a zip container.

    OOXML and ODF spread content across parts, so the payload could be in
    ``word/document.xml``, ``content.xml``, or a notebook cell.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            return "\n".join(archive.read(name).decode("utf-8", errors="replace") for name in archive.namelist())
    except (zipfile.BadZipFile, OSError) as exc:
        raise NotRecoverable(f"{path} is not a readable archive: {exc}") from exc


def extract_pdf(path: str) -> str:
    """Return the text a PDF draws, rejoining separately-shown lines.

    Text is drawn with ``(...) Tj`` operators, one per laid-out line, so a
    wrapped payload is split across several and interleaved with positioning
    commands. Pulling the operands out and rejoining them reassembles it.

    Only handles the uncompressed and Flate-compressed streams this tool
    writes; it is not a general PDF parser.
    """
    raw = pathlib.Path(path).read_bytes()
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        body = match.group(1)
        # A stream may be stored uncompressed; then use the bytes as they are.
        with contextlib.suppress(zlib.error):
            body = zlib.decompress(body)
        chunks.append(body.decode("utf-8", errors="replace"))

    if not chunks:
        raise NotRecoverable(f"{path} contains no content streams")

    content = "\n".join(chunks)
    shown = re.findall(r"\((.*?)\)\s*Tj", content, re.S)
    if not shown:
        return content
    # \( \) \\ are escaped inside a PDF string literal.
    unescaped = [re.sub(r"\\([()\\])", r"\1", line) for line in shown]
    return " ".join(line.strip() for line in unescaped)


def extract_wav_stego(path: str, bits_per_sample: int = 1) -> str:
    """Recover text hidden in the least significant bits of a WAV.

    Mirrors ``pistudio.files.audio.write_audio_stego``: a four-byte
    big-endian length prefix followed by the UTF-8 payload.
    """
    from pistudio.files.audio import read_wav_samples

    samples = read_wav_samples(path)
    mask = (1 << bits_per_sample) - 1
    bits = "".join(format((s + 65536 if s < 0 else s) & mask, f"0{bits_per_sample}b") for s in samples)

    if len(bits) < 32:
        raise NotRecoverable(f"{path} is too short to hold a length prefix")

    (length,) = struct.unpack(">I", int(bits[:32], 2).to_bytes(4, "big"))
    body = bits[32 : 32 + length * 8]
    if len(body) < length * 8:
        raise NotRecoverable(f"{path} declares {length} bytes but holds fewer")

    payload = bytes(int(body[i : i + 8], 2) for i in range(0, len(body), 8))
    return payload.decode("utf-8", errors="replace")


def rendered_ink_ratio(path: str) -> float:
    """Return the fraction of pixels that differ from the image's background.

    A rasterised payload cannot be matched byte for byte, so the question is
    whether anything was drawn at all. A blank image means the payload never
    made it onto the canvas.
    """
    from PIL import Image

    with Image.open(path) as image:
        pixels = list(image.convert("L").getdata())

    if not pixels:
        raise NotRecoverable(f"{path} has no pixel data")

    # The renderer may use light-on-dark or dark-on-light, so measure against
    # whichever tone dominates rather than assuming a white page.
    background = max(set(pixels), key=pixels.count)
    return sum(1 for value in pixels if value != background) / len(pixels)


def contains_payload(path: str, payload: str) -> bool:
    """Return whether *payload* can be read back out of *path*."""
    try:
        return payload in extract_text(path)
    except NotRecoverable:
        return False
