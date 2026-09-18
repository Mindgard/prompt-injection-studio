"""Barcode generation for prompt injection payloads.

Provides functions to generate 1D and 2D barcodes containing prompt text or encoded data,
with support for PNG, SVG, and terminal rendering.

Libraries:
- python-barcode: Simple 1D barcodes (Code 128, Code 39)
- treepoem: Advanced 2D barcodes (DataMatrix, PDF417, Aztec, QR) - requires Ghostscript
"""

import io
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


# ── Barcode type definitions ─────────────────────────────────────────────


def _validate_code39(text: str) -> tuple[bool, str]:
    """Validate Code 39 input (A-Z, 0-9, -.$/+% space)."""
    valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-. $/+%")
    upper = text.upper()
    invalid = [c for c in upper if c not in valid_chars]
    if invalid:
        return False, f"only supports A-Z, 0-9, and -.$/+% characters, found invalid: {''.join(set(invalid))}"
    return True, ""


# Barcode type registry: type_code -> (display_name, description, validator, library)
# Validator is a callable (text) -> (valid, error_msg) or None for no validation
# Library is "barcode" for python-barcode or "treepoem" for treepoem
# Note: Digit-only types (EAN, UPC, ISBN, ISSN) excluded as not useful for prompt injection
BARCODE_TYPES: dict[str, tuple[str, str, Callable[[str], tuple[bool, str]] | None, str]] = {
    # QR codes (segno - no external dependencies)
    "qr": ("QR Code", "2D matrix, widely supported (default)", None, "segno"),
    # 1D barcodes (python-barcode)
    "code128": ("Code 128", "1D alphanumeric, variable length", None, "barcode"),
    "code39": ("Code 39", "1D A-Z, 0-9, -.$/+%", _validate_code39, "barcode"),
    # 2D barcodes (treepoem - requires Ghostscript)
    "datamatrix": ("Data Matrix", "2D matrix, high density", None, "treepoem"),
    "pdf417": ("PDF417", "2D stacked, high capacity", None, "treepoem"),
    "azteccode": ("Aztec Code", "2D matrix, compact", None, "treepoem"),
}


# ── Dependency checks ────────────────────────────────────────────────────


def _check_barcode() -> None:
    """Raise ImportError with install hint if python-barcode is not available."""
    try:
        import barcode  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "python-barcode is required for barcode generation. Install with: pip install prompt-injection-studio[barcode]"
        ) from exc


def _check_treepoem() -> None:
    """Raise ImportError with install hint if treepoem is not available."""
    try:
        import treepoem  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "treepoem is required for 2D barcode generation. Install with: pip install prompt-injection-studio[barcode]"
        ) from exc


def _check_segno() -> None:
    """Raise ImportError with install hint if segno is not available."""
    try:
        import segno  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "segno is required for QR code generation. Install with: pip install prompt-injection-studio[qr]"
        ) from exc


def _check_ghostscript() -> None:
    """Check if Ghostscript is available on the system.

    Raises:
        RuntimeError: If Ghostscript is not found, with platform-specific install instructions.
    """
    import platform
    import shutil

    # Check for gs (Unix) or gswin64c/gswin32c (Windows)
    gs_commands = ["gs", "gswin64c", "gswin32c"]
    found = any(shutil.which(cmd) for cmd in gs_commands)

    if not found:
        system = platform.system().lower()
        if system == "darwin":
            install_hint = (
                "Ghostscript is required for 2D barcodes but was not found.\n\n"
                "Install on macOS with Homebrew:\n"
                "  brew install ghostscript\n\n"
                "Or download from: https://ghostscript.com/releases/gsdnld.html"
            )
        elif system == "linux":
            install_hint = (
                "Ghostscript is required for 2D barcodes but was not found.\n\n"
                "Install on Ubuntu/Debian:\n"
                "  sudo apt-get install ghostscript\n\n"
                "Install on Fedora/RHEL:\n"
                "  sudo dnf install ghostscript\n\n"
                "Install on Arch:\n"
                "  sudo pacman -S ghostscript"
            )
        elif system == "windows":
            install_hint = (
                "Ghostscript is required for 2D barcodes but was not found.\n\n"
                "Download and install from:\n"
                "  https://ghostscript.com/releases/gsdnld.html\n\n"
                "Make sure to add Ghostscript to your PATH during installation."
            )
        else:
            install_hint = (
                "Ghostscript is required for 2D barcodes but was not found.\n\n"
                "Download from: https://ghostscript.com/releases/gsdnld.html"
            )
        raise RuntimeError(install_hint)


def _get_barcode_library(barcode_type: str) -> str:
    """Get the library name for a barcode type."""
    if barcode_type not in BARCODE_TYPES:
        return "unknown"
    return BARCODE_TYPES[barcode_type][3]


#: Device resolution to declare in generated images, in dots per inch.  Label
#: printers in the Brother QL family raster at 300dpi, and an office laser is a
#: multiple of it, so a 300dpi symbol lands on a whole number of device dots on
#: both.
PRINT_DPI = 300

#: Device pixels per module below which a printed symbol stops scanning
#: reliably.  Four is the floor quoted for camera scanners; under it the
#: printer's own dithering starts merging adjacent modules.
_MIN_PIXELS_PER_MODULE = 4


def _mm_to_pixels(mm: float, dpi: int = PRINT_DPI) -> int:
    """Convert *mm* to whole device pixels at *dpi*."""
    return round(mm / 25.4 * dpi)


def scale_for_size(modules: int, size_mm: float, dpi: int = PRINT_DPI) -> tuple[int, int]:
    """Return the per-module scale that renders *modules* across *size_mm*.

    A matrix symbol's printed size is the product of its module count and the
    pixels per module, so hitting a physical target means solving for the
    scale rather than setting one.  The result is floored to a whole number of
    pixels: a fractional scale would make segno resample, giving modules of
    uneven width that scanners read as a damaged symbol.

    Args:
        modules: Width of the symbol in modules, quiet zone included.
        size_mm: Target printed width in millimetres.
        dpi: Device resolution the image will declare.

    Returns:
        A tuple of (scale, dpi) ready to hand to ``segno.save``.

    Raises:
        ValueError: If *size_mm* is not positive, or is too small to give
            *modules* enough pixels each to scan.
    """
    if size_mm <= 0:
        raise ValueError(f"--size must be a positive measurement, got {size_mm}mm")

    target_px = _mm_to_pixels(size_mm, dpi)
    scale = target_px // modules

    if scale < _MIN_PIXELS_PER_MODULE:
        # Report in the units the user typed, and name the two ways out: a
        # bigger label, or a smaller symbol.  Rounded *up* to the next whole
        # millimetre: the exact minimum here is a fraction, and rounding to
        # nearest would name a size that fails this same check.
        import math

        needed_mm = math.ceil(modules * _MIN_PIXELS_PER_MODULE / dpi * 25.4)
        raise ValueError(
            f"{size_mm:g}mm is too small for this payload: {modules} modules would get "
            f"{scale} pixel(s) each at {dpi}dpi, below the {_MIN_PIXELS_PER_MODULE} needed to scan.\n"
            f"  Use --size {needed_mm}mm or larger, or shorten the payload "
            f"(--error-level L holds more in the same symbol)."
        )

    return scale, dpi


def _make_qr(text: str, error_level: str = "M", micro: bool = False):
    """Build a segno QR symbol, shared by the terminal, PNG and SVG writers.

    Args:
        text: The text to encode.
        error_level: Error correction level L/M/Q/H (default "M").
        micro: Emit a Micro QR code instead of a standard one.

    Returns:
        A ``segno.QRCode``.

    Raises:
        ImportError: If segno is not installed.
        ValueError: If *text* does not fit a Micro QR symbol.
    """
    _check_segno()
    import segno

    err = error_level.upper()
    if err not in ("L", "M", "Q", "H"):
        err = "M"

    if not micro:
        return segno.make(text, error=err, micro=False)

    # Micro QR tops out around 35 alphanumeric characters, and segno's own
    # error names the internal version rather than the flag the user passed.
    try:
        return segno.make(text, error=err, micro=True)
    except Exception as exc:
        raise ValueError(
            f"payload of {len(text)} chars is too long for a Micro QR code; drop --micro to use a standard QR"
        ) from exc


# ── Public API ───────────────────────────────────────────────────────────


def list_barcode_types() -> list[tuple[str, str, str, str]]:
    """Return list of supported barcode types.

    Returns:
        List of (type_code, display_name, description, library) tuples.
    """
    return [(code, name, desc, lib) for code, (name, desc, _, lib) in BARCODE_TYPES.items()]


def validate_barcode_input(text: str, barcode_type: str) -> tuple[bool, str]:
    """Validate input text for a specific barcode type.

    Args:
        text: The text to encode.
        barcode_type: The barcode type code (e.g., "code128", "datamatrix").

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    if barcode_type not in BARCODE_TYPES:
        return False, f"unknown barcode type '{barcode_type}', use 'inject barcode list' to see available types"

    name, _, validator, _ = BARCODE_TYPES[barcode_type]
    if validator is None:
        return True, ""

    valid, error = validator(text)
    if not valid:
        return False, f"{name} {error}"
    return True, ""


def write_barcode_png(
    text: str,
    path: str,
    barcode_type: str = "qr",
    module_width: float = 0.2,
    module_height: float = 15.0,
    quiet_zone: float = 6.5,
    font_size: int = 10,
    text_distance: float = 5.0,
    write_text: bool = True,
    scale: int = 3,
    error_level: str = "M",
    border: int = 4,
    dark: str = "black",
    light: str = "white",
    micro: bool = False,
    size_mm: float | None = None,
) -> None:
    """Generate a barcode PNG image.

    Args:
        text: The text to encode in the barcode.
        path: Output file path for the PNG image.
        barcode_type: Barcode type (default "qr").
        module_width: Width of a single bar in mm (default 0.2, 1D only).
        module_height: Height of the bars in mm (default 15.0, 1D only).
        quiet_zone: Size of the quiet zone in mm (default 6.5, 1D only).
        font_size: Font size for the human-readable text (default 10, 1D only).
        text_distance: Distance between bars and text in mm (default 5.0, 1D only).
        write_text: Whether to include human-readable text (default True, 1D only).
        scale: Scale factor for 2D/QR barcodes (default 3).  Ignored when
            *size_mm* is given, which solves for the scale instead.
        error_level: QR error correction level L/M/Q/H (default "M", QR only).
        border: Quiet zone width in modules (default 4, QR only).
        dark: Colour of the dark modules (default "black", QR only).
        light: Colour of the light modules (default "white", QR only).
        micro: Emit a Micro QR code, for short payloads (default False, QR only).
        size_mm: Printed width to target in millimetres.  The image declares
            it via the PNG ``pHYs`` chunk, so the size survives into anything
            that reads the file -- CUPS, a word processor, a label tool.
            Without it the PNG carries no physical size and every consumer
            falls back to its own assumed resolution.

    Raises:
        ImportError: If required library is not installed.
        RuntimeError: If Ghostscript is not available (treepoem barcodes).
        ValueError: If the barcode type is unknown, input is invalid, or
            *size_mm* is too small for the payload to scan.
    """
    # Validate input
    valid, error = validate_barcode_input(text, barcode_type)
    if not valid:
        raise ValueError(error)

    library = _get_barcode_library(barcode_type)

    if library == "segno":
        # QR code via segno
        qr = _make_qr(text, error_level=error_level, micro=micro)

        # Ensure path has .png extension
        if not path.lower().endswith(".png"):
            path = f"{path}.png"

        save_opts: dict[str, object] = {"scale": scale, "border": border, "dark": dark, "light": light}
        if size_mm is not None:
            # symbol_size includes the quiet zone, which occupies label area
            # and so has to be part of what gets fitted.
            modules = qr.symbol_size(scale=1, border=border)[0]
            fitted, dpi = scale_for_size(modules, size_mm)
            save_opts["scale"] = fitted
            save_opts["dpi"] = dpi

        qr.save(path, **save_opts)
        logger.debug(f"Generated QR code PNG: {path} (size_mm={size_mm})")
    elif library == "treepoem":
        # 2D barcode via treepoem
        _check_treepoem()
        _check_ghostscript()
        import treepoem

        # Generate barcode image
        image = treepoem.generate_barcode(
            barcode_type=barcode_type,
            data=text,
        )

        # Scale up for better quality.  NEAREST keeps module edges hard --
        # an interpolating filter would blur them into greys that scanners
        # threshold inconsistently.
        from PIL import Image

        save_kwargs: dict[str, object] = {}
        if size_mm is not None:
            fitted, dpi = scale_for_size(image.width, size_mm)
            image = image.resize((image.width * fitted, image.height * fitted), Image.NEAREST)
            save_kwargs["dpi"] = (dpi, dpi)
        elif scale > 1:
            image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)

        # Ensure path has .png extension
        if not path.lower().endswith(".png"):
            path = f"{path}.png"
        image.save(path, **save_kwargs)
        logger.debug(f"Generated 2D barcode PNG: {path} (type={barcode_type}, size_mm={size_mm})")
    else:
        # 1D barcode via python-barcode
        _check_barcode()
        import barcode
        from barcode.writer import ImageWriter

        # Get barcode class
        try:
            barcode_class = barcode.get_barcode_class(barcode_type)
        except barcode.errors.BarcodeNotFoundError as exc:
            raise ValueError(f"unknown barcode type '{barcode_type}'") from exc

        # Create barcode with ImageWriter for PNG output
        writer = ImageWriter()
        bc = barcode_class(text, writer=writer)

        # python-barcode already lays out in millimetres, so a physical target
        # divides across the bars rather than solving for a pixel scale as the
        # matrix symbologies do.
        if size_mm is not None:
            if size_mm <= 0:
                raise ValueError(f"--size must be a positive measurement, got {size_mm}mm")
            bars = len(bc.build()[0])
            module_width = (size_mm - 2 * quiet_zone) / bars
            if module_width <= 0:
                raise ValueError(
                    f"{size_mm:g}mm leaves no room for {bars} bars once the "
                    f"{quiet_zone:g}mm quiet zones are taken off each side.\n"
                    f"  Use a wider --size, or lower --quiet-zone."
                )

        # Configure writer options
        options = {
            "module_width": module_width,
            "module_height": module_height,
            "quiet_zone": quiet_zone,
            "font_size": font_size,
            "text_distance": text_distance,
            "write_text": write_text,
            "dpi": PRINT_DPI,
        }

        # Save (python-barcode adds extension automatically, so strip it if present)
        if path.lower().endswith(".png"):
            path = path[:-4]
        bc.save(path, options=options)
        logger.debug(f"Generated 1D barcode PNG: {path}.png (type={barcode_type})")


def write_barcode_svg(
    text: str,
    path: str,
    barcode_type: str = "qr",
    module_width: float = 0.2,
    module_height: float = 15.0,
    quiet_zone: float = 6.5,
    font_size: int = 10,
    text_distance: float = 5.0,
    write_text: bool = True,
    scale: int = 3,
    error_level: str = "M",
    border: int = 4,
    dark: str = "black",
    light: str = "white",
    micro: bool = False,
    size_mm: float | None = None,
) -> None:
    """Generate a barcode SVG image.

    Args:
        text: The text to encode in the barcode.
        path: Output file path for the SVG image.
        barcode_type: Barcode type (default "qr").
        module_width: Width of a single bar in mm (default 0.2, 1D only).
        module_height: Height of the bars in mm (default 15.0, 1D only).
        quiet_zone: Size of the quiet zone in mm (default 6.5, 1D only).
        font_size: Font size for the human-readable text (default 10, 1D only).
        text_distance: Distance between bars and text in mm (default 5.0, 1D only).
        write_text: Whether to include human-readable text (default True, 1D only).
        scale: Scale factor for 2D/QR barcodes (default 3).
        error_level: QR error correction level L/M/Q/H (default "M", QR only).
        border: Quiet zone width in modules (default 4, QR only).
        dark: Colour of the dark modules (default "black", QR only).
        light: Colour of the light modules (default "white", QR only).
        micro: Emit a Micro QR code, for short payloads (default False, QR only).
        size_mm: Printed width to target in millimetres, written as an
            absolute ``width``/``height`` on the root element.  An SVG is
            resolution-independent, so this needs no minimum module size the
            way a raster image does.

    Raises:
        ImportError: If required library is not installed.
        RuntimeError: If Ghostscript is not available (treepoem barcodes).
        ValueError: If the barcode type is unknown, input is invalid, or
            *size_mm* is not positive.
    """
    # Validate input
    valid, error = validate_barcode_input(text, barcode_type)
    if not valid:
        raise ValueError(error)

    if size_mm is not None and size_mm <= 0:
        raise ValueError(f"--size must be a positive measurement, got {size_mm}mm")

    library = _get_barcode_library(barcode_type)

    if library == "segno":
        # QR code via segno - native SVG support
        qr = _make_qr(text, error_level=error_level, micro=micro)

        # Ensure path has .svg extension
        if not path.lower().endswith(".svg"):
            path = f"{path}.svg"

        svg_opts: dict[str, object] = {"scale": scale, "border": border, "dark": dark, "light": light}
        if size_mm is not None:
            # unit renders the size as a physical measurement; svgversion=1.1
            # keeps the viewBox that lets it scale within that box.
            svg_opts["unit"] = "mm"
            svg_opts["scale"] = size_mm / qr.symbol_size(scale=1, border=border)[0]
            svg_opts["svgversion"] = 1.1

        qr.save(path, **svg_opts)
        logger.debug(f"Generated QR code SVG: {path} (size_mm={size_mm})")
    elif library == "treepoem":
        # 2D barcode via treepoem - generate PNG then convert to SVG
        # treepoem doesn't support SVG directly, so we generate PNG
        # For true SVG, users should use the dedicated QR command with segno
        _check_treepoem()
        _check_ghostscript()
        import treepoem

        # Generate barcode image
        image = treepoem.generate_barcode(
            barcode_type=barcode_type,
            data=text,
        )

        # Scale up for better quality
        if scale > 1:
            new_size = (image.width * scale, image.height * scale)
            from PIL import Image

            image = image.resize(new_size, Image.NEAREST)

        # Convert to SVG by embedding PNG in SVG
        # This is a workaround since treepoem doesn't support SVG output
        import base64

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        png_data = base64.b64encode(buf.getvalue()).decode("ascii")

        svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{image.width}" height="{image.height}">
  <image width="{image.width}" height="{image.height}"
         xlink:href="data:image/png;base64,{png_data}"/>
</svg>'''

        # Ensure path has .svg extension
        if not path.lower().endswith(".svg"):
            path = f"{path}.svg"
        with open(path, "w") as f:
            f.write(svg_content)
        logger.debug(f"Generated 2D barcode SVG: {path} (type={barcode_type})")
    else:
        # 1D barcode via python-barcode
        _check_barcode()
        import barcode
        from barcode.writer import SVGWriter

        # Get barcode class
        try:
            barcode_class = barcode.get_barcode_class(barcode_type)
        except barcode.errors.BarcodeNotFoundError as exc:
            raise ValueError(f"unknown barcode type '{barcode_type}'") from exc

        # Create barcode with SVGWriter
        writer = SVGWriter()
        bc = barcode_class(text, writer=writer)

        # Configure writer options
        options = {
            "module_width": module_width,
            "module_height": module_height,
            "quiet_zone": quiet_zone,
            "font_size": font_size,
            "text_distance": text_distance,
            "write_text": write_text,
        }

        # Save (python-barcode adds extension automatically, so strip it if present)
        if path.lower().endswith(".svg"):
            path = path[:-4]
        bc.save(path, options=options)
        logger.debug(f"Generated 1D barcode SVG: {path}.svg (type={barcode_type})")


def render_barcode_terminal(
    text: str,
    barcode_type: str = "qr",
    height: int = 10,
    error_level: str = "M",
    border: int = 1,
    micro: bool = False,
) -> str:
    """Generate a barcode as a terminal-printable string using Unicode block characters.

    Args:
        text: The text to encode in the barcode.
        barcode_type: Barcode type (default "qr").
        height: Number of lines for the barcode height (default 10, 1D only).
        error_level: QR error correction level L/M/Q/H (default "M", QR only).
        border: Quiet zone width in modules (default 1, QR only).
        micro: Emit a Micro QR code, for short payloads (default False, QR only).

    Returns:
        A string containing the barcode rendered with Unicode block characters.

    Raises:
        ImportError: If required library is not installed.
        RuntimeError: If Ghostscript is not available (treepoem barcodes).
        ValueError: If the barcode type is unknown or input is invalid.
    """
    # Validate input
    valid, error = validate_barcode_input(text, barcode_type)
    if not valid:
        raise ValueError(error)

    library = _get_barcode_library(barcode_type)

    if library == "segno":
        # QR code via segno - use segno's terminal output
        qr = _make_qr(text, error_level=error_level, micro=micro)

        # Use segno's terminal output
        buf = io.StringIO()
        qr.terminal(out=buf, compact=True, border=border)
        return buf.getvalue()
    elif library == "treepoem":
        # 2D barcode via treepoem - render as ASCII art from image
        _check_treepoem()
        _check_ghostscript()
        import treepoem

        # Generate barcode image
        image = treepoem.generate_barcode(
            barcode_type=barcode_type,
            data=text,
        )

        # Convert to grayscale
        image = image.convert("L")

        # Render using Unicode half-block characters for 2x vertical resolution
        # ▀ (upper half), ▄ (lower half), █ (full block), ' ' (space)
        lines = []
        width, img_height = image.size
        pixels = list(image.getdata())

        # Process two rows at a time for half-block rendering
        for y in range(0, img_height, 2):
            line = "  "  # Quiet zone
            for x in range(width):
                top_idx = y * width + x
                bot_idx = (y + 1) * width + x if y + 1 < img_height else top_idx

                top_dark = pixels[top_idx] < 128
                bot_dark = pixels[bot_idx] < 128 if y + 1 < img_height else False

                if top_dark and bot_dark:
                    line += "█"
                elif top_dark:
                    line += "▀"
                elif bot_dark:
                    line += "▄"
                else:
                    line += " "
            line += "  "  # Quiet zone
            lines.append(line)

        # Add the encoded text below
        if lines:
            max_width = max(len(line) for line in lines)
            lines.append("")
            lines.append(text.center(max_width))

        return "\n".join(lines)

    # 1D barcode via python-barcode
    _check_barcode()
    import barcode

    # Get barcode class
    try:
        barcode_class = barcode.get_barcode_class(barcode_type)
    except barcode.errors.BarcodeNotFoundError as exc:
        raise ValueError(f"unknown barcode type '{barcode_type}'") from exc

    # Create barcode without writer to get raw encoding
    bc = barcode_class(text)

    # Get the binary encoding (list of 0s and 1s as string)
    # The build() method returns a list of module widths
    modules = bc.build()

    # Convert modules to binary string
    # Each module is a tuple of (bar_width, space_width) or similar
    # We need to render bars as █ and spaces as ' '
    binary = ""
    for module in modules:
        if isinstance(module, str):
            # Some barcodes return string of 0s and 1s
            binary += module
        elif isinstance(module, (list, tuple)):
            # Some return list of widths
            for i, width in enumerate(module):
                char = "█" if i % 2 == 0 else " "
                binary += char * int(width)

    if not binary and hasattr(bc, "code"):
        # Fallback: read the encoding off the barcode's code property.
        binary = bc.code

    # Build terminal output
    lines = []

    # Quiet zone
    quiet = "  "

    # Render the barcode bars
    bar_line = quiet
    for char in binary:
        if char in ("1", "█"):
            bar_line += "█"
        else:
            bar_line += " "
    bar_line += quiet

    # Repeat for height
    for _ in range(height):
        lines.append(bar_line)

    # Add the encoded text below
    text_line = text.center(len(bar_line))
    lines.append("")
    lines.append(text_line)

    return "\n".join(lines)
