"""Pillow-based text→image rendering and metadata embedding for payload images.

Provides two modes:
- **Visible text** (default): renders the prompt as white monospace text on a
  dark background.  Useful for testing vision/OCR models.
- **Metadata embedding** (``--metadata``): writes the prompt into EXIF
  UserComment (JPEG) or PNG tEXt chunk.  Invisible to humans.
"""

import logging
import textwrap

logger = logging.getLogger(__name__)

_CHARS_PER_LINE = 72
_FONT_SIZE = 14
_PADDING = 16
_LINE_HEIGHT = 18
_BG_COLOR = (30, 30, 30)
_FG_COLOR = (220, 220, 220)


def _check_pillow() -> None:
    """Raise ImportError with install hint if Pillow is not available."""
    try:
        import PIL  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Pillow is required for image generation. Install with: pip install prompt-injection-studio[embed]"
        ) from exc


def render_text_image(
    text: str,
    path: str,
    fmt: str = "png",
    font_size: int = _FONT_SIZE,
) -> None:
    """Render *text* as a monospace-font image and save to *path*.

    Args:
        text: The prompt text to render.
        path: Output file path.
        fmt: Pillow format string (``"png"`` or ``"jpeg"``).
        font_size: Font size in pixels.
    """
    _check_pillow()
    from PIL import Image, ImageDraw, ImageFont

    # Word-wrap
    lines: list[str] = []
    for paragraph in text.splitlines():
        wrapped = textwrap.wrap(paragraph, width=_CHARS_PER_LINE) or [""]
        lines.extend(wrapped)

    # Calculate image dimensions
    line_height = int(font_size * 1.3)
    width = _PADDING * 2 + _CHARS_PER_LINE * int(font_size * 0.6)
    height = _PADDING * 2 + len(lines) * line_height
    # Minimum dimensions
    width = max(width, 400)
    height = max(height, 60)

    img = Image.new("RGB", (width, height), color=_BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Try to use a monospace font; fall back to default
    font: ImageFont.FreeTypeFont | None = None
    for name in ("DejaVuSansMono.ttf", "Courier New.ttf", "cour.ttf", "LiberationMono-Regular.ttf"):
        try:
            font = ImageFont.truetype(name, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    y = _PADDING
    for line in lines:
        draw.text((_PADDING, y), line, fill=_FG_COLOR, font=font)
        y += line_height

    fmt_lower = fmt.lower()
    if fmt_lower == "jpeg":
        img = img.convert("RGB")
        img.save(path, format="JPEG", quality=95)
    elif fmt_lower == "tiff":
        img.save(path, format="TIFF")
    else:
        img.save(path, format="PNG")


def embed_metadata(text: str, path: str, fmt: str = "png") -> None:
    """Write *text* into image metadata.

    For PNG: uses a tEXt chunk with key ``"prompt"``.
    For JPEG: uses EXIF UserComment field.

    The image at *path* must already exist (call :func:`render_text_image`
    first, or create a minimal 1×1 image).

    Args:
        text: The prompt text to embed.
        path: Path to an existing image file.
        fmt: ``"png"`` or ``"jpeg"``.
    """
    _check_pillow()
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    if fmt.lower() == "png":
        img = Image.open(path)
        meta = PngInfo()
        meta.add_text("prompt", text)
        img.save(path, format="PNG", pnginfo=meta)
    elif fmt.lower() == "jpeg":
        # EXIF UserComment via piexif if available, else fall back to
        # a simpler approach: re-save with Pillow's info dict
        try:
            import piexif

            img = Image.open(path)
            exif_dict = (
                piexif.load(img.info.get("exif", b""))
                if "exif" in img.info
                else {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
            )
            # UserComment tag
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = b"ASCII\x00\x00\x00" + text.encode("utf-8")
            exif_bytes = piexif.dump(exif_dict)
            img.save(path, format="JPEG", quality=95, exif=exif_bytes)
        except ImportError:
            # Without piexif, embed in JPEG comment segment manually
            img = Image.open(path)
            img.info["comment"] = text.encode("utf-8")
            img.save(path, format="JPEG", quality=95)
            logger.debug("piexif not available; embedded prompt in JPEG comment field")
    else:
        raise ValueError(f"Unsupported image format for metadata: {fmt}")


def write_metadata_image(text: str, path: str, fmt: str = "png") -> None:
    """Create a minimal image and embed *text* in its metadata.

    This is the ``--metadata`` code path: creates a small 1×1 white image
    and writes the prompt into metadata fields only (invisible).

    Args:
        text: The prompt text to embed.
        path: Output file path.
        fmt: ``"png"`` or ``"jpeg"``.
    """
    _check_pillow()
    from PIL import Image

    img = Image.new("RGB", (1, 1), color=(255, 255, 255))
    if fmt.lower() == "jpeg":
        img.save(path, format="JPEG", quality=95)
    else:
        img.save(path, format="PNG")

    embed_metadata(text, path, fmt=fmt)
