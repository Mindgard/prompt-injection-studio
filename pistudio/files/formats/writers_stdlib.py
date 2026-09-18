"""Stdlib-only format writers — no third-party dependencies required."""

import csv


def write_txt(text: str, path: str) -> None:
    """Write plain text file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_md(text: str, path: str) -> None:
    """Write Markdown file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_csv(text: str, path: str) -> None:
    """Write CSV with the prompt in cell A1."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["prompt"])
        writer.writerow([text])


def write_html(text: str, path: str) -> None:
    """Write minimal HTML document containing the prompt."""
    from html import escape

    escaped = escape(text)
    html = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        '<head><meta charset="utf-8"><title>Payload</title></head>\n'
        "<body>\n"
        f"<p>{escaped}</p>\n"
        "</body>\n"
        "</html>\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def write_svg(text: str, path: str) -> None:
    """Write SVG with the prompt as a text element."""
    from xml.sax.saxutils import escape as xml_escape

    escaped = xml_escape(text)
    # Wrap long text — estimate ~60 chars per line at 12px font
    lines = []
    for paragraph in escaped.splitlines():
        while len(paragraph) > 60:
            # Find a space to break at
            idx = paragraph.rfind(" ", 0, 60)
            if idx == -1:
                idx = 60
            lines.append(paragraph[:idx])
            paragraph = paragraph[idx:].lstrip()
        lines.append(paragraph)

    tspans = "\n".join(f'    <tspan x="10" dy="1.2em">{line}</tspan>' for line in lines)
    height = max(40, 20 + len(lines) * 16)
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="{height}">\n'
        f'  <text x="10" y="20" font-family="monospace" font-size="12" fill="#000">\n'
        f"{tspans}\n"
        "  </text>\n"
        "</svg>\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


def _check_dep(package: str, pip_name: str, group: str = "embed") -> None:
    """Raise ImportError with install hint if *package* is not available.

    Only for pip-installable formats.  Formats provisioned into their own venv
    (see ``RUNTIME_PROVISIONED``) never route here -- their writers are stubs
    that raise their own errors naming the setup command.
    """
    try:
        __import__(package)
    except ImportError as exc:
        hint = f"pip install prompt-injection-studio[{group}]"
        raise ImportError(f"{pip_name} is required for this format. Install with: {hint}") from exc


def write_pdf(text: str, path: str) -> None:
    """Write PDF document containing the prompt text."""
    _check_dep("fpdf", "fpdf2")
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Courier", size=10)
    # multi_cell handles word-wrapping
    pdf.multi_cell(0, 5, text)
    pdf.output(path)


def write_docx(text: str, path: str) -> None:
    """Write DOCX document containing the prompt text."""
    _check_dep("docx", "python-docx")
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)


def write_xlsx(text: str, path: str) -> None:
    """Write XLSX spreadsheet with the prompt in cell A1."""
    _check_dep("openpyxl", "openpyxl")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Payload"
    ws["A1"] = text
    wb.save(path)


def write_png(text: str, path: str) -> None:
    """Render prompt as visible text on a PNG image."""
    from pistudio.files.render_image import render_text_image

    render_text_image(text, path, fmt="png")


def write_jpg(text: str, path: str) -> None:
    """Render prompt as visible text on a JPEG image."""
    from pistudio.files.render_image import render_text_image

    render_text_image(text, path, fmt="jpeg")


def write_pptx(text: str, path: str) -> None:
    """Write PPTX presentation with the prompt on a slide."""
    _check_dep("pptx", "python-pptx")
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(6.5))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(12)
    p.font.name = "Courier New"
    prs.save(path)


def write_tiff(text: str, path: str) -> None:
    """Render prompt as visible text on a TIFF image."""
    _check_dep("PIL", "Pillow")
    from pistudio.files.render_image import render_text_image

    render_text_image(text, path, fmt="tiff")


def write_json(text: str, path: str) -> None:
    """Write JSON document with the prompt as a field value."""
    import json

    data = {"content": text, "role": "user", "type": "message"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_xml(text: str, path: str) -> None:
    """Write XML document with the prompt as element text."""
    from xml.sax.saxutils import escape as xml_escape

    escaped = xml_escape(text)
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<document>\n  <content>{escaped}</content>\n</document>\n'
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)


def write_yaml(text: str, path: str) -> None:
    """Write YAML document with the prompt as a field value."""
    # Emit raw YAML to avoid needing pyyaml.
    # Use block scalar (|) to safely represent multi-line text.
    with open(path, "w", encoding="utf-8") as f:
        f.write("content: |\n")
        for line in text.splitlines():
            f.write(f"  {line}\n")
        f.write("role: user\n")
        f.write("type: message\n")


def write_eml(text: str, path: str) -> None:
    """Write EML email file with the prompt in the body."""
    from email.mime.text import MIMEText

    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = "Important Update"
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    with open(path, "w", encoding="utf-8") as f:
        f.write(msg.as_string())


def write_ics(text: str, path: str) -> None:
    """Write ICS calendar invite with the prompt in the description."""
    import datetime

    now = datetime.datetime.now(datetime.UTC)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    start = (now + datetime.timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ")
    end = (now + datetime.timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")
    # Fold long description lines per RFC 5545
    desc_escaped = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Prompt Injection Studio//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART:{start}\r\n"
        f"DTEND:{end}\r\n"
        f"DTSTAMP:{stamp}\r\n"
        "SUMMARY:Meeting\r\n"
        f"DESCRIPTION:{desc_escaped}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(ics)


def write_vcf(text: str, path: str) -> None:
    """Write VCF vCard with the prompt in the NOTE field."""
    note_escaped = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    vcf = (
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        "FN:John Doe\r\n"
        "N:Doe;John;;;\r\n"
        "EMAIL:john.doe@example.com\r\n"
        f"NOTE:{note_escaped}\r\n"
        "END:VCARD\r\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(vcf)


def write_rtf(text: str, path: str) -> None:
    """Write RTF document containing the prompt text."""
    # Escape RTF special chars and encode non-ASCII as Unicode escapes
    escaped = []
    for ch in text:
        if ch == "\\":
            escaped.append("\\\\")
        elif ch == "{":
            escaped.append("\\{")
        elif ch == "}":
            escaped.append("\\}")
        elif ch == "\n":
            escaped.append("\\par\n")
        elif ord(ch) > 127:
            escaped.append(f"\\u{ord(ch)}?")
        else:
            escaped.append(ch)
    body = "".join(escaped)
    rtf = f"{{\\rtf1\\ansi\\deff0{{\\fonttbl{{\\f0\\fmodern Courier New;}}}}\\f0\\fs20 {body}}}"
    with open(path, "w", encoding="ascii", errors="replace") as f:
        f.write(rtf)


def write_ini(text: str, path: str) -> None:
    """Write INI config file with the prompt as a value."""
    # Multi-line values: indent continuation lines
    lines = text.splitlines()
    value = lines[0] if lines else ""
    if len(lines) > 1:
        value += "\n" + "\n".join("  " + line for line in lines[1:])
    with open(path, "w", encoding="utf-8") as f:
        f.write("[default]\n")
        f.write(f"content = {value}\n")
        f.write("type = message\n")


def write_env(text: str, path: str) -> None:
    """Write .env file with the prompt as an environment variable."""
    # Quote the value and escape internal quotes/newlines
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'CONTENT="{escaped}"\n')
        f.write("TYPE=message\n")


def write_epub(text: str, path: str) -> None:
    """Write EPUB e-book with the prompt as chapter content."""
    import zipfile
    from html import escape

    escaped = escape(text)
    container_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        "  <rootfiles>\n"
        '    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>\n"
    )
    content_opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "    <dc:title>Payload</dc:title>\n"
        '    <dc:identifier id="uid">urn:uuid:00000000-0000-0000-0000-000000000000</dc:identifier>\n'
        "    <dc:language>en</dc:language>\n"
        "  </metadata>\n"
        "  <manifest>\n"
        '    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>\n'
        "  </manifest>\n"
        "  <spine>\n"
        '    <itemref idref="ch1"/>\n'
        "  </spine>\n"
        "</package>\n"
    )
    chapter_xhtml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        "<head><title>Chapter 1</title></head>\n"
        "<body>\n"
        f"<p>{escaped}</p>\n"
        "</body>\n"
        "</html>\n"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("content.opf", content_opf)
        zf.writestr("chapter1.xhtml", chapter_xhtml)


def write_odt(text: str, path: str) -> None:
    """Write ODT (OpenDocument Text) with the prompt as paragraph content."""
    import zipfile
    from xml.sax.saxutils import escape as xml_escape

    escaped = xml_escape(text)
    # Build paragraph elements for each line
    paras = (
        "\n".join(f'<text:p text:style-name="Standard">{line}</text:p>' for line in escaped.splitlines())
        or f'<text:p text:style-name="Standard">{escaped}</text:p>'
    )

    manifest_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">\n'
        '  <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.text" manifest:full-path="/"/>\n'
        '  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>\n'
        "</manifest:manifest>\n"
    )
    content_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<office:document-content"
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' office:version="1.2">\n'
        "<office:body>\n"
        "<office:text>\n"
        f"{paras}\n"
        "</office:text>\n"
        "</office:body>\n"
        "</office:document-content>\n"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zf.writestr("META-INF/manifest.xml", manifest_xml)
        zf.writestr("content.xml", content_xml)


def write_wav(text: str, path: str) -> None:
    """Write WAV audio file with the prompt embedded in a metadata chunk.

    Creates a short silent audio file and appends the prompt text as a
    LIST/INFO chunk (ICMT -- comment field).  Speech-to-text and audio
    processing pipelines that read WAV metadata will see the prompt.
    """
    import struct
    import wave

    # Write a short silent WAV first
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        # 0.1 seconds of silence
        wf.writeframes(b"\x00\x00" * 4410)

    # Append a LIST/INFO chunk with the comment
    comment = text.encode("utf-8")
    # ICMT sub-chunk
    icmt = b"ICMT" + struct.pack("<I", len(comment) + 1) + comment + b"\x00"
    if len(icmt) % 2:
        icmt += b"\x00"
    # LIST chunk
    info_data = b"INFO" + icmt
    list_chunk = b"LIST" + struct.pack("<I", len(info_data)) + info_data

    # Read existing file, insert LIST chunk before final size
    with open(path, "rb") as f:
        raw = f.read()
    # Update RIFF size
    new_size = len(raw) - 8 + len(list_chunk)
    raw = raw[:4] + struct.pack("<I", new_size) + raw[8:]
    with open(path, "wb") as f:
        f.write(raw + list_chunk)
