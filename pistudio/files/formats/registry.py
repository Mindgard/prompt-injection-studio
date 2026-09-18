"""Format registry mapping names to FileFormat descriptors, plus lookup helpers."""

from pistudio.files.formats.types import FileFormat
from pistudio.files.formats.writers_ext import (
    write_dockerfile,
    write_js,
    write_jsonl,
    write_log,
    write_makefile,
    write_py,
    write_sh,
    write_sql,
    write_tex,
    write_toml,
)
from pistudio.files.formats.writers_stdlib import (
    write_csv,
    write_docx,
    write_eml,
    write_env,
    write_epub,
    write_html,
    write_ics,
    write_ini,
    write_jpg,
    write_json,
    write_md,
    write_odt,
    write_pdf,
    write_png,
    write_pptx,
    write_rtf,
    write_svg,
    write_tiff,
    write_txt,
    write_vcf,
    write_wav,
    write_xlsx,
    write_xml,
    write_yaml,
)

FORMAT_REGISTRY: dict[str, FileFormat] = {
    # ── Text / markup (stdlib) ──
    "txt": FileFormat(
        "txt",
        ".txt",
        "Plain text file",
        "",
        write_txt,
        True,
        False,
        category="Text & Markup",
        threat_level="documented",
    ),
    "md": FileFormat(
        "md", ".md", "Markdown file", "", write_md, True, False, category="Text & Markup", threat_level="documented"
    ),
    "csv": FileFormat(
        "csv",
        ".csv",
        "CSV spreadsheet",
        "",
        write_csv,
        True,
        False,
        category="Text & Markup",
        threat_level="documented",
    ),
    "html": FileFormat(
        "html",
        ".html",
        "HTML document",
        "",
        write_html,
        True,
        False,
        category="Text & Markup",
        threat_level="documented",
    ),
    "svg": FileFormat(
        "svg",
        ".svg",
        "SVG image (text element)",
        "",
        write_svg,
        True,
        False,
        category="Text & Markup",
        threat_level="documented",
    ),
    "rtf": FileFormat(
        "rtf", ".rtf", "Rich Text Format", "", write_rtf, False, False, category="Documents", threat_level="documented"
    ),
    # ── Structured data (stdlib) ──
    "json": FileFormat(
        "json",
        ".json",
        "JSON document",
        "",
        write_json,
        True,
        False,
        category="Structured Data",
        threat_level="documented",
    ),
    "xml": FileFormat(
        "xml", ".xml", "XML document", "", write_xml, True, False, category="Structured Data", threat_level="documented"
    ),
    "yaml": FileFormat(
        "yaml",
        ".yaml",
        "YAML document",
        "",
        write_yaml,
        True,
        False,
        category="Structured Data",
        threat_level="documented",
    ),
    "ini": FileFormat(
        "ini",
        ".ini",
        "INI config file",
        "",
        write_ini,
        True,
        False,
        category="Structured Data",
        threat_level="documented",
    ),
    "env": FileFormat(
        "env",
        ".env",
        "Environment variables file",
        "",
        write_env,
        True,
        False,
        category="Structured Data",
        threat_level="documented",
    ),
    # ── Messaging / calendar (stdlib) ──
    "eml": FileFormat(
        "eml",
        ".eml",
        "Email message (EML)",
        "",
        write_eml,
        True,
        False,
        category="Messaging",
        threat_level="documented",
    ),
    "ics": FileFormat(
        "ics",
        ".ics",
        "Calendar invite (iCal)",
        "",
        write_ics,
        True,
        False,
        category="Messaging",
        threat_level="documented",
    ),
    "vcf": FileFormat(
        "vcf", ".vcf", "vCard contact", "", write_vcf, True, False, category="Messaging", threat_level="documented"
    ),
    # ── Archive-based documents (stdlib) ──
    "epub": FileFormat(
        "epub", ".epub", "EPUB e-book", "", write_epub, False, False, category="Documents", threat_level="documented"
    ),
    "odt": FileFormat(
        "odt", ".odt", "OpenDocument text", "", write_odt, False, False, category="Documents", threat_level="documented"
    ),
    # ── Binary documents (optional deps) ──
    "pdf": FileFormat(
        "pdf",
        ".pdf",
        "PDF document",
        "fpdf2",
        write_pdf,
        False,
        False,
        group="embed",
        category="Documents",
        threat_level="documented",
    ),
    "docx": FileFormat(
        "docx",
        ".docx",
        "Word document",
        "python-docx",
        write_docx,
        False,
        False,
        group="embed",
        category="Documents",
        threat_level="documented",
    ),
    "xlsx": FileFormat(
        "xlsx",
        ".xlsx",
        "Excel spreadsheet",
        "openpyxl",
        write_xlsx,
        False,
        False,
        group="embed",
        category="Documents",
        threat_level="documented",
    ),
    "pptx": FileFormat(
        "pptx",
        ".pptx",
        "PowerPoint presentation",
        "python-pptx",
        write_pptx,
        False,
        False,
        group="embed",
        category="Documents",
        threat_level="documented",
    ),
    # ── Images (optional deps) ──
    "png": FileFormat(
        "png",
        ".png",
        "PNG image (rendered text)",
        "Pillow",
        write_png,
        False,
        True,
        group="embed",
        category="Images",
        threat_level="documented",
    ),
    "jpg": FileFormat(
        "jpg",
        ".jpg",
        "JPEG image (rendered text)",
        "Pillow",
        write_jpg,
        False,
        True,
        group="embed",
        category="Images",
        threat_level="documented",
    ),
    "tiff": FileFormat(
        "tiff",
        ".tiff",
        "TIFF image (rendered text)",
        "Pillow",
        write_tiff,
        False,
        True,
        group="embed",
        category="Images",
        threat_level="documented",
    ),
    # ── Audio (stdlib) ──
    "wav": FileFormat(
        "wav",
        ".wav",
        "WAV audio (metadata comment)",
        "",
        write_wav,
        False,
        False,
        category="Audio",
        threat_level="documented",
        audio=True,
    ),
    # ── Tier A: Code assistant attack surface (stdlib) ──
    "py": FileFormat(
        "py",
        ".py",
        "Python file (docstring + comments)",
        "",
        write_py,
        True,
        False,
        category="Code",
        threat_level="documented",
    ),
    "js": FileFormat(
        "js",
        ".js",
        "JavaScript file (block comment)",
        "",
        write_js,
        True,
        False,
        category="Code",
        threat_level="documented",
    ),
    "toml": FileFormat(
        "toml",
        ".toml",
        "TOML config file",
        "",
        write_toml,
        True,
        False,
        category="Structured Data",
        threat_level="documented",
    ),
    "dockerfile": FileFormat(
        "dockerfile",
        "Dockerfile",
        "Dockerfile (comment lines)",
        "",
        write_dockerfile,
        True,
        False,
        category="Code",
        threat_level="documented",
    ),
    "sql": FileFormat(
        "sql",
        ".sql",
        "SQL file (comment + INSERT)",
        "",
        write_sql,
        True,
        False,
        category="Code",
        threat_level="documented",
    ),
    "sh": FileFormat(
        "sh", ".sh", "Shell script (comments)", "", write_sh, True, False, category="Code", threat_level="documented"
    ),
    "makefile": FileFormat(
        "makefile",
        "Makefile",
        "Makefile (comments)",
        "",
        write_makefile,
        True,
        False,
        category="Code",
        threat_level="documented",
    ),
    # ── Tier A: RAG & document pipeline (stdlib) ──
    "jsonl": FileFormat(
        "jsonl",
        ".jsonl",
        "JSONL data file",
        "",
        write_jsonl,
        True,
        False,
        category="Structured Data",
        threat_level="documented",
    ),
    "log": FileFormat(
        "log",
        ".log",
        "Log file (embedded entries)",
        "",
        write_log,
        True,
        False,
        category="Structured Data",
        threat_level="documented",
    ),
    "tex": FileFormat(
        "tex", ".tex", "LaTeX document", "", write_tex, True, False, category="Documents", threat_level="documented"
    ),
}

# Merged after FORMAT_REGISTRY is defined: registry_ext imports from this
# module, so the import cannot sit at the top.
from pistudio.files.formats.registry_ext import EXT_FORMATS  # noqa: E402

FORMAT_REGISTRY.update(EXT_FORMATS)


def get_format(name: str) -> FileFormat | None:
    """Look up a format by name (case-insensitive)."""
    return FORMAT_REGISTRY.get(name.lower())


def all_format_names() -> list[str]:
    """Return sorted list of all supported format names."""
    return sorted(FORMAT_REGISTRY.keys())


def audio_format_names() -> list[str]:
    """Return the formats routed to ``inject audio``, in registry order."""
    return [f.name for f in FORMAT_REGISTRY.values() if f.audio]


def file_format_names() -> list[str]:
    """Return the formats routed to ``inject file``, in registry order."""
    return [f.name for f in FORMAT_REGISTRY.values() if not f.audio]


# Two formats are provisioned at runtime into their own venvs rather than as
# pip extras: their deps (torch, opencv, numpy<2) are ABI-incompatible with
# this one.  `pip install prompt-injection-studio[<group>]` is not merely
# unhelpful for these -- the extra does not exist, and for anamorpher the
# resolver conflict is a real trap (it pins numpy<2.0; every available
# opencv-python wants numpy>=2).  Keyed by group so a renderer holding a
# FileFormat can ask without knowing which format it has.
RUNTIME_PROVISIONED: dict[str, str] = {
    "embed-anamorpher": "file anamorph setup",
    "embed-adversarial-audio": "audio adversarial-audio setup",
}


def setup_command(fmt: FileFormat) -> str | None:
    """Return the command that provisions *fmt*, or None if pip can install it.

    Counterpart to the venv probes in `is_format_available`: a format detected
    by venv presence cannot be installed by pip into this interpreter.
    """
    return RUNTIME_PROVISIONED.get(fmt.group)


def is_format_available(fmt: FileFormat) -> bool:
    """Return True if the format's dependencies are installed."""
    if not fmt.requires:
        return True
    pkg = fmt.requires.split()[0]
    # Map pip names to importable package names
    _import_map = {
        "fpdf2": "fpdf",
        "python-docx": "docx",
        "python-pptx": "pptx",
        "openpyxl": "openpyxl",
        "Pillow": "PIL",
        "mutagen": "mutagen",
        "mido": "mido",
        "nbformat": "nbformat",
        "moviepy": "moviepy",
        "fonttools": "fontTools",
        "numpy": "numpy",
        "scipy": "scipy",
        "edge-tts": "edge_tts",
        "anamorpher": "anamorpher",
        "segno": "segno",
    }
    # Anamorpher uses a subprocess venv — check for the venv, not the import
    if pkg == "anamorpher":
        from pistudio.files.anamorpher import _find_venv_python

        return _find_venv_python() is not None
    # Adversarial-audio uses a subprocess venv — check for the venv, not the import
    if pkg == "adversarial-audio":
        from pistudio.files.adversarial_audio import _find_venv_python as _find_adv_venv

        return _find_adv_venv() is not None
    import_name = _import_map.get(pkg, pkg)
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False
