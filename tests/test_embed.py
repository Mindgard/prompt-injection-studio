"""Tests for the embed (payload file generation) feature.

Covers:
- Format registry
- Stdlib writers (txt, md, csv, html, svg)
- Non-stdlib writers with mocked deps (pdf, docx, xlsx)
- Image rendering helpers
- EmbedCommand smoke tests
"""

import csv
import importlib.util
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from pistudio.commands.flags import slugify


def _has_pillow() -> bool:
    """Pillow ships in the [embed] extra."""
    return importlib.util.find_spec("PIL") is not None


# ── Format registry tests ─────────────────────────────────────────


class TestFormatRegistry:
    def test_all_format_names(self):
        from pistudio.files.formats import all_format_names

        names = all_format_names()
        assert "txt" in names
        assert "pdf" in names
        assert "png" in names
        assert "jpg" in names
        assert "docx" in names
        assert "xlsx" in names
        assert names == sorted(names)

    def test_get_format_known(self):
        from pistudio.files.formats import get_format

        fmt = get_format("txt")
        assert fmt is not None
        assert fmt.name == "txt"
        assert fmt.extension == ".txt"
        assert fmt.human_readable is True
        assert fmt.requires == ""

    def test_get_format_case_insensitive(self):
        from pistudio.files.formats import get_format

        assert get_format("PDF") is not None
        assert get_format("Txt") is not None

    def test_get_format_unknown(self):
        from pistudio.files.formats import get_format

        assert get_format("exe") is None

    def test_is_format_available_stdlib(self):
        from pistudio.files.formats import get_format, is_format_available

        fmt = get_format("txt")
        assert is_format_available(fmt) is True

    def test_format_metadata_support(self):
        from pistudio.files.formats import get_format

        assert get_format("png").supports_metadata is True
        assert get_format("jpg").supports_metadata is True
        assert get_format("pdf").supports_metadata is False
        assert get_format("txt").supports_metadata is False


# ── Stdlib writer tests ───────────────────────────────────────────


class TestStdlibWriters:
    def test_write_txt(self):
        from pistudio.files.formats import write_txt

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            write_txt("hello world", path)
            with open(path) as f:
                assert f.read() == "hello world"
        finally:
            os.unlink(path)

    def test_write_md(self):
        from pistudio.files.formats import write_md

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            path = f.name
        try:
            write_md("# Payload\nIgnore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "# Payload" in content
            assert "Ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_csv(self):
        from pistudio.files.formats import write_csv

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            write_csv("ignore all instructions", path)
            with open(path) as f:
                reader = csv.reader(f)
                rows = list(reader)
            assert rows[0] == ["prompt"]
            assert rows[1] == ["ignore all instructions"]
        finally:
            os.unlink(path)

    def test_write_html(self):
        from pistudio.files.formats import write_html

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            path = f.name
        try:
            write_html("test <script>alert(1)</script>", path)
            with open(path) as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
            assert "&lt;script&gt;" in content  # escaped
            assert "<script>" not in content  # not raw
        finally:
            os.unlink(path)

    def test_write_svg(self):
        from pistudio.files.formats import write_svg

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            path = f.name
        try:
            write_svg("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "<svg" in content
            assert "ignore instructions" in content
            assert "<text" in content
        finally:
            os.unlink(path)

    def test_write_svg_long_text_wraps(self):
        from pistudio.files.formats import write_svg

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            path = f.name
        try:
            long_text = "word " * 50  # ~250 chars
            write_svg(long_text, path)
            with open(path) as f:
                content = f.read()
            assert content.count("<tspan") > 1  # wrapped into multiple lines
        finally:
            os.unlink(path)


# ── New stdlib writer tests ───────────────────────────────────────


class TestJsonWriter:
    def test_write_json(self):
        from pistudio.files.formats import write_json

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            write_json("ignore instructions", path)
            with open(path) as f:
                data = json.loads(f.read())
            assert data["content"] == "ignore instructions"
            assert "role" in data
        finally:
            os.unlink(path)


class TestXmlWriter:
    def test_write_xml(self):
        from pistudio.files.formats import write_xml

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name
        try:
            write_xml("ignore <all> instructions", path)
            with open(path) as f:
                content = f.read()
            assert "<?xml" in content
            assert "<content>" in content
            assert "&lt;all&gt;" in content  # escaped
        finally:
            os.unlink(path)


class TestYamlWriter:
    def test_write_yaml(self):
        from pistudio.files.formats import write_yaml

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            path = f.name
        try:
            write_yaml("line one\nline two", path)
            with open(path) as f:
                content = f.read()
            assert "content: |" in content
            assert "  line one" in content
            assert "  line two" in content
            assert "role: user" in content
        finally:
            os.unlink(path)


class TestEmlWriter:
    def test_write_eml(self):
        import email

        from pistudio.files.formats import write_eml

        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as f:
            path = f.name
        try:
            write_eml("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "Subject: Important Update" in content
            assert "From:" in content
            # Body may be base64-encoded; parse with email module
            msg = email.message_from_string(content)
            body = msg.get_payload(decode=True).decode("utf-8")
            assert body == "ignore instructions"
        finally:
            os.unlink(path)


class TestIcsWriter:
    def test_write_ics(self):
        from pistudio.files.formats import write_ics

        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as f:
            path = f.name
        try:
            write_ics("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "BEGIN:VCALENDAR" in content
            assert "BEGIN:VEVENT" in content
            assert "DESCRIPTION:" in content
            assert "ignore instructions" in content
        finally:
            os.unlink(path)


class TestVcfWriter:
    def test_write_vcf(self):
        from pistudio.files.formats import write_vcf

        with tempfile.NamedTemporaryFile(suffix=".vcf", delete=False) as f:
            path = f.name
        try:
            write_vcf("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "BEGIN:VCARD" in content
            assert "NOTE:" in content
            assert "ignore instructions" in content
        finally:
            os.unlink(path)


class TestRtfWriter:
    def test_write_rtf(self):
        from pistudio.files.formats import write_rtf

        with tempfile.NamedTemporaryFile(suffix=".rtf", delete=False) as f:
            path = f.name
        try:
            write_rtf("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "{\\rtf1" in content
            assert "ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_rtf_special_chars(self):
        from pistudio.files.formats import write_rtf

        with tempfile.NamedTemporaryFile(suffix=".rtf", delete=False) as f:
            path = f.name
        try:
            write_rtf("test {braces} and \\backslash", path)
            with open(path) as f:
                content = f.read()
            assert "\\{braces\\}" in content
            assert "\\\\" in content
        finally:
            os.unlink(path)


class TestIniWriter:
    def test_write_ini(self):
        from pistudio.files.formats import write_ini

        with tempfile.NamedTemporaryFile(suffix=".ini", delete=False) as f:
            path = f.name
        try:
            write_ini("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "[default]" in content
            assert "content = ignore instructions" in content
        finally:
            os.unlink(path)


class TestEnvWriter:
    def test_write_env(self):
        from pistudio.files.formats import write_env

        with tempfile.NamedTemporaryFile(suffix=".env", delete=False) as f:
            path = f.name
        try:
            write_env("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert 'CONTENT="ignore instructions"' in content
            assert "TYPE=message" in content
        finally:
            os.unlink(path)

    def test_write_env_escapes_quotes(self):
        from pistudio.files.formats import write_env

        with tempfile.NamedTemporaryFile(suffix=".env", delete=False) as f:
            path = f.name
        try:
            write_env('say "hello"', path)
            with open(path) as f:
                content = f.read()
            assert '\\"hello\\"' in content
        finally:
            os.unlink(path)


class TestEpubWriter:
    def test_write_epub(self):
        import zipfile

        from pistudio.files.formats import write_epub

        with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as f:
            path = f.name
        try:
            write_epub("ignore instructions", path)
            assert os.path.exists(path)
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                assert "mimetype" in names
                assert "META-INF/container.xml" in names
                assert "chapter1.xhtml" in names
                chapter = zf.read("chapter1.xhtml").decode("utf-8")
                assert "ignore instructions" in chapter
        finally:
            os.unlink(path)


class TestOdtWriter:
    def test_write_odt(self):
        import zipfile

        from pistudio.files.formats import write_odt

        with tempfile.NamedTemporaryFile(suffix=".odt", delete=False) as f:
            path = f.name
        try:
            write_odt("ignore instructions", path)
            assert os.path.exists(path)
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                assert "mimetype" in names
                assert "content.xml" in names
                content = zf.read("content.xml").decode("utf-8")
                assert "ignore instructions" in content
        finally:
            os.unlink(path)


class TestWavWriter:
    def test_write_wav(self):
        from pistudio.files.formats import write_wav

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            write_wav("ignore instructions", path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
            # Verify it starts with RIFF header
            with open(path, "rb") as f:
                header = f.read(4)
            assert header == b"RIFF"
            # Verify the comment is embedded
            with open(path, "rb") as f:
                raw = f.read()
            assert b"ICMT" in raw
            assert b"ignore instructions" in raw
        finally:
            os.unlink(path)


# ── Non-stdlib writer tests (mocked) ─────────────────────────────


class TestPptxWriter:
    def test_write_pptx_missing_dep(self):
        from pistudio.files.formats import write_pptx

        with (
            patch("pistudio.files.formats.writers_stdlib._check_dep", side_effect=ImportError("python-pptx required")),
            pytest.raises(ImportError, match="python-pptx required"),
        ):
            write_pptx("test", "/tmp/test.pptx")

    def test_write_pptx_success(self):
        from pistudio.files.formats import write_pptx

        try:
            import pptx  # noqa: F401
        except ImportError:
            pytest.skip("python-pptx not installed")

        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            path = f.name
        try:
            write_pptx("test payload text", path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)


@pytest.mark.skipif(not _has_pillow(), reason="Pillow not installed")
class TestTiffWriter:
    def test_write_tiff(self):
        try:
            from pistudio.files.formats import write_tiff
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False) as f:
            path = f.name
        try:
            write_tiff("test prompt", path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
            from PIL import Image

            img = Image.open(path)
            assert img.format == "TIFF"
        finally:
            os.unlink(path)


class TestPdfWriter:
    def test_write_pdf_missing_dep(self):
        from pistudio.files.formats import write_pdf

        with patch.dict("sys.modules", {"fpdf": None}):
            with patch("builtins.__import__", side_effect=ImportError("no fpdf")):
                # _check_dep will fail
                pass
        # Direct test: mock the import check
        with patch("pistudio.files.formats.writers_stdlib._check_dep", side_effect=ImportError("fpdf2 required")):
            with pytest.raises(ImportError, match="fpdf2 required"):
                write_pdf("test", "/tmp/test.pdf")

    def test_write_pdf_success(self):
        from pistudio.files.formats import write_pdf

        try:
            import fpdf  # noqa: F401
        except ImportError:
            pytest.skip("fpdf2 not installed")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            write_pdf("test payload", path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)


class TestDocxWriter:
    def test_write_docx_missing_dep(self):
        from pistudio.files.formats import write_docx

        with (
            patch("pistudio.files.formats.writers_stdlib._check_dep", side_effect=ImportError("python-docx required")),
            pytest.raises(ImportError, match="python-docx required"),
        ):
            write_docx("test", "/tmp/test.docx")

    def test_write_docx_success(self):
        from pistudio.files.formats import write_docx

        try:
            import docx  # noqa: F401
        except ImportError:
            pytest.skip("python-docx not installed")

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            path = f.name
        try:
            write_docx("test payload text", path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)


class TestXlsxWriter:
    def test_write_xlsx_missing_dep(self):
        from pistudio.files.formats import write_xlsx

        with (
            patch("pistudio.files.formats.writers_stdlib._check_dep", side_effect=ImportError("openpyxl required")),
            pytest.raises(ImportError, match="openpyxl required"),
        ):
            write_xlsx("test", "/tmp/test.xlsx")

    def test_write_xlsx_success(self):
        from pistudio.files.formats import write_xlsx

        try:
            import openpyxl  # noqa: F401
        except ImportError:
            pytest.skip("openpyxl not installed")

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        try:
            write_xlsx("test payload text", path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
            # Verify content
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            assert ws["A1"].value == "test payload text"
        finally:
            os.unlink(path)


# ── Image rendering tests ─────────────────────────────────────────


@pytest.mark.skipif(not _has_pillow(), reason="Pillow not installed")
class TestImageRendering:
    def test_render_text_image_png(self):
        try:
            from pistudio.files.render_image import render_text_image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            render_text_image("test prompt injection", path, fmt="png")
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
            # Verify it's a valid PNG
            from PIL import Image

            img = Image.open(path)
            assert img.format == "PNG"
            assert img.size[0] >= 400
        finally:
            os.unlink(path)

    def test_render_text_image_jpeg(self):
        try:
            from pistudio.files.render_image import render_text_image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            path = f.name
        try:
            render_text_image("test prompt", path, fmt="jpeg")
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)

    def test_write_metadata_image_png(self):
        try:
            from pistudio.files.render_image import write_metadata_image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            write_metadata_image("secret payload", path, fmt="png")
            assert os.path.exists(path)
            # Verify metadata
            from PIL import Image

            img = Image.open(path)
            assert img.info.get("prompt") == "secret payload"
        finally:
            os.unlink(path)

    def test_render_long_text_wraps(self):
        try:
            from pistudio.files.render_image import render_text_image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            long_text = "word " * 100
            render_text_image(long_text, path, fmt="png")
            from PIL import Image

            img = Image.open(path)
            # Image should be tall enough for wrapped text
            assert img.size[1] > 60
        finally:
            os.unlink(path)

    def test_check_pillow_missing(self):
        from pistudio.files.render_image import _check_pillow

        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def mock_import(name, *args, **kwargs):
            if name == "PIL":
                raise ImportError("no PIL")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import), pytest.raises(ImportError, match="Pillow"):
            _check_pillow()


# ── EmbedCommand smoke tests ──────────────────────────────────────


def _make_shell():
    """Create a minimal mock shell for command testing."""
    shell = MagicMock()
    shell.json_mode = False
    shell.session_dir = "/tmp/test-session"
    shell.out = MagicMock()
    shell.console = MagicMock()
    shell.audit = MagicMock()
    return shell


class TestEmbedCommandSmoke:
    def test_no_args_shows_usage(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        cmd.execute(shell, [])
        shell.out.info.assert_called_once()
        assert "Usage" in shell.out.info.call_args[0][0]

    def test_unknown_format_error(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        cmd.execute(shell, ["exe"])
        shell.out.error.assert_called_once()
        assert "Unknown format" in shell.out.error.call_args[0][0]

    def test_list_formats(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        cmd.execute(shell, ["list"])
        shell.console.print.assert_called()
        # Should have printed format names
        all_output = " ".join(str(c) for c in shell.console.print.call_args_list)
        assert "txt" in all_output
        assert "pdf" in all_output

    def test_list_formats_json(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        shell.json_mode = True
        cmd.execute(shell, ["list"])
        shell.print_raw.assert_called_once()
        data = json.loads(shell.print_raw.call_args[0][0])
        assert isinstance(data, list)
        names = [d["name"] for d in data]
        assert "txt" in names
        assert "pdf" in names

    def test_inline_text_txt(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test.txt")
            cmd.execute(shell, ["txt", "hello world", "--output", out_path])
            assert os.path.exists(out_path)
            with open(out_path) as f:
                assert f.read() == "hello world"
            shell.out.success.assert_called()

    def test_payload_flag_resolves(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()

        mock_payload = MagicMock()
        mock_payload.text = "injected text"

        with patch("pistudio.commands.files_prompt._resolve_from_payload", return_value="injected text"):
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = os.path.join(tmpdir, "test.txt")
                cmd.execute(shell, ["txt", "--payload", "test-payload", "--output", out_path])
                assert os.path.exists(out_path)
                with open(out_path) as f:
                    assert f.read() == "injected text"

    def test_metadata_flag_unsupported_format(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        cmd.execute(shell, ["txt", "hello", "--metadata", "--output", "/tmp/test.txt"])
        shell.out.error.assert_called()
        assert "--metadata" in shell.out.error.call_args[0][0]

    def test_edit_mode(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()

        with patch("pistudio.commands.files_prompt._resolve_from_editor", return_value="edited text"):
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = os.path.join(tmpdir, "test.md")
                cmd.execute(shell, ["md", "--edit", "--output", out_path])
                assert os.path.exists(out_path)
                with open(out_path) as f:
                    assert f.read() == "edited text"

    def test_generate_mode_no_llm(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()

        with patch("pistudio.commands.files_prompt._resolve_llm", return_value=None):
            cmd.execute(shell, ["txt", "--generate", "make a payload", "--output", "/tmp/test.txt"])
            shell.out.error.assert_called()
            assert "No LLM" in shell.out.error.call_args[0][0]


class TestEmbedCommandCompletion:
    def test_complete_empty(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, [])
        assert "list" in result
        assert "txt" in result
        assert "pdf" in result

    def test_complete_partial_format(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["p"])
        assert "pdf" in result
        assert "png" in result

    def test_complete_flags_after_format(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["pdf", ""])
        assert "--payload" in result
        assert "--edit" in result
        assert "--generate" in result
        assert "--output" in result
        assert "--metadata" in result

    def test_complete_payload_names(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()

        mock_payloads = [
            (MagicMock(name="ignore-instructions"), "builtin"),
            (MagicMock(name="data-exfil"), "builtin"),
        ]
        mock_payloads[0][0].name = "ignore-instructions"
        mock_payloads[1][0].name = "data-exfil"

        with patch("pistudio.hardware.payloads.list_payloads", return_value=mock_payloads):
            result = cmd.complete(shell, ["pdf", "--payload", "ig"])
            assert "ignore-instructions" in result
            assert "data-exfil" not in result


class TestPromptResolution:
    def test_resolve_from_payload_found(self):
        from pistudio.commands.files_prompt import _resolve_from_payload

        shell = _make_shell()

        mock_payload = MagicMock()
        mock_payload.text = "payload text"

        with patch("pistudio.hardware.payloads.get_payload", return_value=(mock_payload, "builtin")):
            result = _resolve_from_payload(shell, "test")
            assert result == "payload text"

    def test_resolve_from_payload_not_found(self):
        from pistudio.commands.files_prompt import _resolve_from_payload

        shell = _make_shell()

        with patch("pistudio.hardware.payloads.get_payload", return_value=None):
            result = _resolve_from_payload(shell, "nonexistent")
            assert result is None
            shell.out.error.assert_called()

    def test_resolve_from_editor_success(self):
        from pistudio.commands.files_prompt import _resolve_from_editor

        shell = _make_shell()

        def fake_editor(args, **kwargs):
            # Write content to the temp file
            with open(args[1], "w") as f:
                f.write("# comment\nactual payload\n")

        with patch("pistudio.ui.output.resolve_editor", return_value="vi"):
            with patch("subprocess.run", side_effect=fake_editor):
                result = _resolve_from_editor(shell)
                assert result == "actual payload"

    def test_resolve_from_editor_empty(self):
        from pistudio.commands.files_prompt import _resolve_from_editor

        shell = _make_shell()

        def fake_editor(args, **kwargs):
            with open(args[1], "w") as f:
                f.write("# only comments\n")

        with patch("pistudio.ui.output.resolve_editor", return_value="vi"):
            with patch("subprocess.run", side_effect=fake_editor):
                result = _resolve_from_editor(shell)
                assert result is None

    def test_slugify(self):

        assert slugify("Hello World!") == "hello-world"
        assert slugify("") == "prompt"
        assert slugify("a" * 100) == "a" * 30
        assert slugify("Ignore all previous instructions") == "ignore-all-previous-instructio"


# ── FileFormat new fields tests ──────────────────────────────────


class TestFileFormatNewFields:
    def test_existing_formats_have_category(self):
        from pistudio.files.formats import FORMAT_REGISTRY

        for name, fmt in FORMAT_REGISTRY.items():
            assert fmt.category, f"Format '{name}' missing category"

    def test_existing_formats_have_threat_level(self):
        from pistudio.files.formats import FORMAT_REGISTRY

        for name, fmt in FORMAT_REGISTRY.items():
            assert fmt.threat_level in ("documented", "exploratory"), (
                f"Format '{name}' has invalid threat_level: {fmt.threat_level!r}"
            )

    def test_optional_dep_formats_have_group(self):
        from pistudio.files.formats import FORMAT_REGISTRY

        for name, fmt in FORMAT_REGISTRY.items():
            if fmt.requires:
                assert fmt.group, f"Format '{name}' requires '{fmt.requires}' but has no group"

    def test_anamorph_format_exists(self):
        from pistudio.files.formats import get_format

        fmt = get_format("anamorph")
        assert fmt is not None
        assert fmt.extension == ".png"
        assert fmt.category == "Adversarial"
        assert fmt.threat_level == "documented"
        assert fmt.group == "embed-anamorpher"

    def test_format_count(self):
        from pistudio.files.formats import FORMAT_REGISTRY

        # 24 original + 29 new + 1 anamorph = 54
        assert len(FORMAT_REGISTRY) >= 50


# ── Tier A: New stdlib writer tests ──────────────────────────────


class TestTierAStdlibWriters:
    def test_write_py(self):
        from pistudio.files.formats import write_py

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            path = f.name
        try:
            write_py("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert '"""ignore instructions"""' in content
            assert "# ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_js(self):
        from pistudio.files.formats import write_js

        with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
            path = f.name
        try:
            write_js("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "/*" in content
            assert " * ignore instructions" in content
            assert " */" in content
        finally:
            os.unlink(path)

    def test_write_toml(self):
        from pistudio.files.formats import write_toml

        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            path = f.name
        try:
            write_toml("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "[default]" in content
            assert "ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_dockerfile(self):
        from pistudio.files.formats import write_dockerfile

        with tempfile.NamedTemporaryFile(suffix="Dockerfile", delete=False) as f:
            path = f.name
        try:
            write_dockerfile("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "FROM scratch" in content
            assert "# ignore instructions" in content
            assert "LABEL" in content
        finally:
            os.unlink(path)

    def test_write_sql(self):
        from pistudio.files.formats import write_sql

        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as f:
            path = f.name
        try:
            write_sql("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "-- ignore instructions" in content
            assert "INSERT INTO" in content
        finally:
            os.unlink(path)

    def test_write_sql_escapes_quotes(self):
        from pistudio.files.formats import write_sql

        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as f:
            path = f.name
        try:
            write_sql("it's a test", path)
            with open(path) as f:
                content = f.read()
            assert "it''s a test" in content
        finally:
            os.unlink(path)

    def test_write_sh(self):
        from pistudio.files.formats import write_sh

        with tempfile.NamedTemporaryFile(suffix=".sh", delete=False) as f:
            path = f.name
        try:
            write_sh("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "#!/bin/bash" in content
            assert "# ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_makefile(self):
        from pistudio.files.formats import write_makefile

        with tempfile.NamedTemporaryFile(suffix="Makefile", delete=False) as f:
            path = f.name
        try:
            write_makefile("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "# ignore instructions" in content
            assert ".PHONY" in content
        finally:
            os.unlink(path)

    def test_write_jsonl(self):
        from pistudio.files.formats import write_jsonl

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            write_jsonl("ignore instructions", path)
            with open(path) as f:
                data = json.loads(f.readline())
            assert data["content"] == "ignore instructions"
            assert data["role"] == "user"
        finally:
            os.unlink(path)

    def test_write_log(self):
        from pistudio.files.formats import write_log

        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            path = f.name
        try:
            write_log("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "INFO" in content
            assert "ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_tex(self):
        from pistudio.files.formats import write_tex

        with tempfile.NamedTemporaryFile(suffix=".tex", delete=False) as f:
            path = f.name
        try:
            write_tex("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "\\documentclass{article}" in content
            assert "\\begin{document}" in content
            assert "ignore instructions" in content
        finally:
            os.unlink(path)


# ── Tier B: Stdlib writer tests ──────────────────────────────────


class TestTierBStdlibWriters:
    def test_write_ts(self):
        from pistudio.files.formats import write_ts

        with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
            path = f.name
        try:
            write_ts("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "/*" in content
            assert " * ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_java(self):
        from pistudio.files.formats import write_java

        with tempfile.NamedTemporaryFile(suffix=".java", delete=False) as f:
            path = f.name
        try:
            write_java("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "/**" in content
            assert "public class Payload" in content
        finally:
            os.unlink(path)

    def test_write_go(self):
        from pistudio.files.formats import write_go

        with tempfile.NamedTemporaryFile(suffix=".go", delete=False) as f:
            path = f.name
        try:
            write_go("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "package main" in content
            assert "// ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_rb(self):
        from pistudio.files.formats import write_rb

        with tempfile.NamedTemporaryFile(suffix=".rb", delete=False) as f:
            path = f.name
        try:
            write_rb("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "# ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_rs(self):
        from pistudio.files.formats import write_rs

        with tempfile.NamedTemporaryFile(suffix=".rs", delete=False) as f:
            path = f.name
        try:
            write_rs("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "// ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_c(self):
        from pistudio.files.formats import write_c

        with tempfile.NamedTemporaryFile(suffix=".c", delete=False) as f:
            path = f.name
        try:
            write_c("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "/*" in content
            assert " * ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_bat(self):
        from pistudio.files.formats import write_bat

        with tempfile.NamedTemporaryFile(suffix=".bat", delete=False) as f:
            path = f.name
        try:
            write_bat("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "@echo off" in content
            assert "REM ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_ps1(self):
        from pistudio.files.formats import write_ps1

        with tempfile.NamedTemporaryFile(suffix=".ps1", delete=False) as f:
            path = f.name
        try:
            write_ps1("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "# ignore instructions" in content
        finally:
            os.unlink(path)

    def test_write_bib(self):
        from pistudio.files.formats import write_bib

        with tempfile.NamedTemporaryFile(suffix=".bib", delete=False) as f:
            path = f.name
        try:
            write_bib("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "@misc{payload" in content
            assert "abstract = {ignore instructions}" in content
        finally:
            os.unlink(path)

    def test_write_obj(self):
        from pistudio.files.formats import write_obj

        with tempfile.NamedTemporaryFile(suffix=".obj", delete=False) as f:
            path = f.name
        try:
            write_obj("ignore instructions", path)
            with open(path) as f:
                content = f.read()
            assert "# ignore instructions" in content
            assert "v 0.0 0.0 0.0" in content
            assert "f 1 2 3" in content
        finally:
            os.unlink(path)


# ── Optional dep writer tests (missing dep) ──────────────────────


class TestOptionalDepWritersMissing:
    def test_write_mp3_missing_dep(self):
        from pistudio.files.formats import write_mp3

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("mutagen required")):
            with pytest.raises(ImportError, match="mutagen required"):
                write_mp3("test", "/tmp/test.mp3")

    def test_write_ipynb_missing_dep(self):
        from pistudio.files.formats import write_ipynb

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("nbformat required")):
            with pytest.raises(ImportError, match="nbformat required"):
                write_ipynb("test", "/tmp/test.ipynb")

    def test_write_midi_missing_dep(self):
        from pistudio.files.formats import write_midi

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("mido required")):
            with pytest.raises(ImportError, match="mido required"):
                write_midi("test", "/tmp/test.mid")

    def test_write_flac_missing_dep(self):
        from pistudio.files.formats import write_flac

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("mutagen required")):
            with pytest.raises(ImportError, match="mutagen required"):
                write_flac("test", "/tmp/test.flac")

    def test_write_ogg_missing_dep(self):
        from pistudio.files.formats import write_ogg

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("mutagen required")):
            with pytest.raises(ImportError, match="mutagen required"):
                write_ogg("test", "/tmp/test.ogg")

    def test_write_mp4_missing_dep(self):
        from pistudio.files.formats import write_mp4

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("moviepy required")):
            with pytest.raises(ImportError, match="moviepy required"):
                write_mp4("test", "/tmp/test.mp4")

    def test_write_ttf_missing_dep(self):
        from pistudio.files.formats import write_ttf

        with (
            patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("fonttools required")),
            pytest.raises(ImportError, match="fonttools required"),
        ):
            write_ttf("test", "/tmp/test.ttf")

    def test_write_stl_missing_dep(self):
        from pistudio.files.formats import write_stl

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("numpy required")):
            with pytest.raises(ImportError, match="numpy required"):
                write_stl("test", "/tmp/test.stl")

    def test_write_webp_missing_dep(self):
        from pistudio.files.formats import write_webp

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("Pillow required")):
            with pytest.raises(ImportError, match="Pillow required"):
                write_webp("test", "/tmp/test.webp")

    def test_write_gif_missing_dep(self):
        from pistudio.files.formats import write_gif

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("Pillow required")):
            with pytest.raises(ImportError, match="Pillow required"):
                write_gif("test", "/tmp/test.gif")

    def test_write_bmp_missing_dep(self):
        from pistudio.files.formats import write_bmp

        with patch("pistudio.files.formats.writers_ext._check_dep", side_effect=ImportError("Pillow required")):
            with pytest.raises(ImportError, match="Pillow required"):
                write_bmp("test", "/tmp/test.bmp")


# ── Optional dep writer tests (installed) ────────────────────────


class TestOptionalDepWritersInstalled:
    def test_write_webp(self):
        try:
            from PIL import Image  # noqa: F401

            from pistudio.files.formats import write_webp
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as f:
            path = f.name
        try:
            write_webp("test prompt", path)
            assert os.path.exists(path)
            img = Image.open(path)
            assert img.format == "WEBP"
        finally:
            os.unlink(path)

    def test_write_gif(self):
        try:
            from PIL import Image  # noqa: F401

            from pistudio.files.formats import write_gif
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
            path = f.name
        try:
            write_gif("test prompt", path)
            assert os.path.exists(path)
            img = Image.open(path)
            assert img.format == "GIF"
        finally:
            os.unlink(path)

    def test_write_bmp(self):
        try:
            from PIL import Image  # noqa: F401

            from pistudio.files.formats import write_bmp
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
            path = f.name
        try:
            write_bmp("test prompt", path)
            assert os.path.exists(path)
            img = Image.open(path)
            assert img.format == "BMP"
        finally:
            os.unlink(path)


# ── Anamorpher integration tests ─────────────────────────────────


class TestAnamorpherIntegration:
    def test_anamorph_stub_raises(self):
        from pistudio.files.formats import _write_anamorph_stub

        with pytest.raises(RuntimeError, match="--decoy"):
            _write_anamorph_stub("test", "/tmp/test.png")

    def test_parse_target_size_valid(self):
        from pistudio.files.anamorpher import _parse_target_size

        assert _parse_target_size("256x256") == (256, 256)
        assert _parse_target_size("512x384") == (512, 384)

    def test_parse_target_size_invalid(self):
        from pistudio.files.anamorpher import _parse_target_size

        with pytest.raises(ValueError, match="Invalid target size"):
            _parse_target_size("abc")
        with pytest.raises(ValueError, match="Invalid target size"):
            _parse_target_size("256")

    def test_write_anamorph_no_decoy(self):
        from pistudio.files.anamorpher import write_anamorph

        with pytest.raises(ValueError, match="--decoy is required"):
            write_anamorph("test", "/tmp/test.png")

    def test_write_anamorph_bad_algorithm(self):
        from pistudio.files.anamorpher import write_anamorph

        with pytest.raises(ValueError, match="Unknown algorithm"):
            write_anamorph("test", "/tmp/test.png", decoy_path="/tmp/fake.png", algorithm="invalid")

    def test_write_anamorph_missing_decoy_file(self):
        from pistudio.files.anamorpher import write_anamorph

        with pytest.raises(FileNotFoundError, match="Decoy image not found"):
            write_anamorph("test", "/tmp/test.png", decoy_path="/tmp/nonexistent.png")

    def test_anamorph_command_no_decoy(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        # Mock spinner as context manager
        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=MagicMock())
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        shell.spinner = MagicMock(return_value=spinner_ctx)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test.png")
            cmd.execute(shell, ["anamorph", "test payload", "--output", out_path])
            # Should error about missing --decoy
            shell.out.error.assert_called()
            assert "--decoy" in shell.out.error.call_args[0][0]

    def test_anamorph_command_bad_lambda(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()

        cmd.execute(shell, ["anamorph", "test", "--decoy", "img.png", "--lambda", "abc", "--output", "/tmp/t.png"])
        shell.out.error.assert_called()
        assert "--lambda" in shell.out.error.call_args[0][0]

    def test_anamorph_command_bad_target_size(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()

        cmd.execute(shell, ["anamorph", "test", "--decoy", "img.png", "--target-size", "bad", "--output", "/tmp/t.png"])
        shell.out.error.assert_called()
        assert "Invalid target size" in shell.out.error.call_args[0][0]


# ── Categorized list output tests ────────────────────────────────


class TestCategorizedList:
    def test_list_shows_categories(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        cmd.execute(shell, ["list"])
        all_output = " ".join(str(c) for c in shell.console.print.call_args_list)
        assert "Code" in all_output
        assert "Documents" in all_output
        assert "Images" in all_output
        assert "Adversarial" in all_output
        # Audio formats are listed by `inject audio list`, not here.
        assert "tts-wav" not in all_output
        assert "ultrasonic" not in all_output

    def test_list_shows_threat_markers(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        cmd.execute(shell, ["list"])
        all_output = " ".join(str(c) for c in shell.console.print.call_args_list)
        assert "\u25cf" in all_output  # documented marker
        assert "documented attack vector" in all_output

    def test_list_shows_install_hints(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        cmd.execute(shell, ["list"])
        all_output = " ".join(str(c) for c in shell.console.print.call_args_list)
        assert "embed-all" in all_output
        assert "[all]" in all_output

    def test_list_json_includes_new_fields(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        shell.json_mode = True
        cmd.execute(shell, ["list"])
        data = json.loads(shell.print_raw.call_args[0][0])
        # Check that new fields are present
        sample = data[0]
        assert "category" in sample
        assert "threat_level" in sample
        assert "group" in sample


# ── Anamorph-specific completion tests ───────────────────────────


class TestAnamorphCompletion:
    def test_complete_anamorph_flags(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["anamorph", ""])
        assert "--decoy" in result
        assert "--algorithm" in result
        assert "--lambda" in result
        assert "--target-size" in result

    def test_complete_algorithm_values(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["anamorph", "--algorithm", "n"])
        assert "nearest" in result
        assert "bicubic" not in result

    def test_non_anamorph_no_decoy_flag(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["pdf", ""])
        assert "--decoy" not in result
        assert "--algorithm" not in result

    def test_wants_path_completion_decoy(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        assert cmd.wants_path_completion(["anamorph", "--decoy", "img"]) is True
        assert cmd.wants_path_completion(["anamorph", "--output", "out"]) is True
        assert cmd.wants_path_completion(["anamorph", "--algorithm", "n"]) is False


# ── Batch generation (embed all) tests ────────────────────────────


class TestEmbedAll:
    def test_all_generates_files(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        # Mock spinner as context manager
        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=MagicMock())
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        shell.spinner = MagicMock(return_value=spinner_ctx)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "batch")
            cmd.execute(shell, ["all", "test payload", "--output-dir", out_dir])
            assert os.path.isdir(out_dir)
            # Should have generated at least the stdlib formats
            files = os.listdir(out_dir)
            assert len(files) >= 30  # at least stdlib formats
            # Check naming convention
            assert "payload-txt.txt" in files
            assert "payload-md.md" in files
            assert "payload-csv.csv" in files
            assert "payload-html.html" in files
            # Extensionless formats get a dot separator
            assert "payload-dockerfile.Dockerfile" in files
            assert "payload-makefile.Makefile" in files
            shell.out.success.assert_called()

    def test_all_skips_anamorph(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=MagicMock())
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        shell.spinner = MagicMock(return_value=spinner_ctx)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "batch")
            cmd.execute(shell, ["all", "test payload", "--output-dir", out_dir])
            files = os.listdir(out_dir)
            # anamorph should be skipped (needs --decoy)
            assert not any("anamorph" in f for f in files)

    def test_all_documented_only(self):
        from pistudio.commands.files import EmbedCommand
        from pistudio.files.formats import FORMAT_REGISTRY, is_format_available

        cmd = EmbedCommand()
        shell = _make_shell()
        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=MagicMock())
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        shell.spinner = MagicMock(return_value=spinner_ctx)

        # Count expected documented formats (available, non-audio, not skipped)
        expected = sum(
            1
            for f in FORMAT_REGISTRY.values()
            if f.threat_level == "documented"
            and not f.audio
            and f.name not in cmd._BATCH_SKIP
            and is_format_available(f)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "batch")
            cmd.execute(shell, ["all", "test", "--documented-only", "--output-dir", out_dir])
            files = os.listdir(out_dir)
            assert len(files) == expected

    def test_all_default_dir_name(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=MagicMock())
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        shell.spinner = MagicMock(return_value=spinner_ctx)

        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                cmd.execute(shell, ["all", "hello world"])
                # Should create payload-batch-hello-world/ in cwd
                expected_dir = os.path.join(tmpdir, "payload-batch-hello-world")
                assert os.path.isdir(expected_dir)
            finally:
                os.chdir(original_cwd)

    def test_all_json_mode(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        shell.json_mode = True
        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=MagicMock())
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        shell.spinner = MagicMock(return_value=spinner_ctx)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "batch")
            cmd.execute(shell, ["all", "test", "--output-dir", out_dir])
            shell.print_raw.assert_called_once()
            data = json.loads(shell.print_raw.call_args[0][0])
            assert "directory" in data
            assert "succeeded" in data
            assert "failed" in data
            assert "documented_only" in data
            assert isinstance(data["succeeded"], list)
            assert len(data["succeeded"]) > 0
            # Each entry should have format and path
            assert "format" in data["succeeded"][0]
            assert "path" in data["succeeded"][0]

    def test_all_no_prompt_returns(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()

        # No prompt text and mock interactive to return None
        with patch("pistudio.commands.files_prompt._resolve_interactive", return_value=None):
            cmd.execute(shell, ["all"])
            # Should not create any directory or call success
            shell.out.success.assert_not_called()

    def test_all_audit_logged(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=MagicMock())
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        shell.spinner = MagicMock(return_value=spinner_ctx)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "batch")
            cmd.execute(shell, ["all", "test", "--output-dir", out_dir])
            shell.audit.log.assert_called_once()
            call_kwargs = shell.audit.log.call_args
            assert call_kwargs[0][0] == "embed_batch"


class TestEmbedAllCompletion:
    def test_complete_all_flags(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["all", ""])
        assert "--output-dir" in result
        assert "--documented-only" in result
        assert "--payload" in result
        assert "--edit" in result
        assert "--generate" in result
        # Should NOT have single-format flags
        assert "--output" not in result
        assert "--metadata" not in result
        assert "--decoy" not in result

    def test_complete_all_in_top_level(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["a"])
        assert "all" in result
        assert "anamorph" in result

    def test_wants_path_completion_output_dir(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        assert cmd.wants_path_completion(["all", "--output-dir", "dir"]) is True


# ── Anamorph management subcommand tests ─────────────────────────


class TestAnamorphSetup:
    def test_setup_already_installed(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        with patch("pistudio.files.anamorpher._find_venv_python", return_value="/fake/python"):
            with patch("pistudio.commands.files_anamorph.anamorph_status"):  # avoid walking real venv
                cmd.execute(shell, ["anamorph", "setup"])
                shell.out.info.assert_called()
                # Should show status, not start install
                assert any("already installed" in str(c) for c in shell.out.info.call_args_list)

    def test_setup_cancelled(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        with patch("pistudio.files.anamorpher._find_venv_python", return_value=None):
            with patch("pistudio.commands.files_anamorph.anamorph_setup") as mock_setup:
                # Directly test routing
                cmd.execute(shell, ["anamorph", "setup"])
                mock_setup.assert_called_once_with(shell)

    def test_uninstall_not_installed(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        with patch("pistudio.files.anamorpher._find_venv_python", return_value=None):
            cmd.execute(shell, ["anamorph", "uninstall"])
            shell.out.info.assert_called()
            assert any("not currently installed" in str(c) for c in shell.out.info.call_args_list)

    def test_status_not_installed(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        with patch("pistudio.files.anamorpher._find_venv_python", return_value=None):
            cmd.execute(shell, ["anamorph", "status"])
            all_output = " ".join(str(c) for c in shell.console.print.call_args_list)
            assert "Not installed" in all_output

    def test_status_installed(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        with patch("pistudio.files.anamorpher._find_venv_python", return_value="/fake/venv/bin/python"):
            with patch("pistudio.commands.files_anamorph.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="Python 3.11.12", returncode=0)
                with patch("pistudio.commands.files_anamorph.os.walk", return_value=[]):
                    cmd.execute(shell, ["anamorph", "status"])
                    all_output = " ".join(str(c) for c in shell.console.print.call_args_list)
                    assert "Installed" in all_output
                    assert "Trail of Bits" in all_output

    def test_routing_remove_alias(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        with patch("pistudio.commands.files_anamorph.anamorph_uninstall") as mock_uninstall:
            cmd.execute(shell, ["anamorph", "remove"])
            mock_uninstall.assert_called_once_with(shell)

    def test_find_python311(self):
        from pistudio.commands.files_anamorph import find_python311

        # Should return None or a valid path (not crash)
        result = find_python311()
        if result is not None:
            assert "3.11" in result


class TestAnamorphCompletionManagement:
    def test_complete_anamorph_shows_subcommands(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["anamorph", ""])
        assert "setup" in result
        assert "uninstall" in result
        assert "status" in result
        # Also has flags
        assert "--decoy" in result

    def test_complete_anamorph_filters_subcommands(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["anamorph", "s"])
        assert "setup" in result
        assert "status" in result
        assert "uninstall" not in result

    def test_complete_anamorph_filters_un(self):
        from pistudio.commands.files import EmbedCommand

        cmd = EmbedCommand()
        shell = _make_shell()
        result = cmd.complete(shell, ["anamorph", "un"])
        assert "uninstall" in result
        assert "setup" not in result


class TestAnamorpherModuleHelpers:
    def test_project_root(self):
        from pistudio.files.anamorpher import _project_root

        root = _project_root()
        assert os.path.isdir(root)
        assert os.path.isfile(os.path.join(root, "pyproject.toml"))

    def test_default_venv_dir(self):
        from pistudio.files.anamorpher import _default_venv_dir

        venv_dir = _default_venv_dir()
        assert ".anamorpher-venv" in venv_dir

    def test_repo_and_blog_urls(self):
        from pistudio.files.anamorpher import ANAMORPHER_BLOG, ANAMORPHER_REPO

        assert "trailofbits" in ANAMORPHER_REPO
        assert "trailofbits" in ANAMORPHER_BLOG
        assert ANAMORPHER_REPO.startswith("https://")
        assert ANAMORPHER_BLOG.startswith("https://")


# ── _check_dep group hint tests ──────────────────────────────────


class TestCheckDepGroupHint:
    def test_check_dep_default_group(self):
        from pistudio.files.formats import _check_dep

        with pytest.raises(ImportError, match=r"prompt-injection-studio\[embed\]"):
            _check_dep("nonexistent_pkg_xyz", "nonexistent_pkg_xyz")

    def test_check_dep_custom_group(self):
        from pistudio.files.formats import _check_dep

        with pytest.raises(ImportError, match=r"prompt-injection-studio\[embed-audio\]"):
            _check_dep("nonexistent_pkg_xyz", "nonexistent_pkg_xyz", group="embed-audio")
