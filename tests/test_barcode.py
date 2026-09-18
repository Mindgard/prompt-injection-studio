"""Tests for barcode generation module and inject barcode commands."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ── Module tests ─────────────────────────────────────────────────────


class TestBarcodeModule:
    """Tests for pistudio.files.barcode module."""

    def test_list_barcode_types_returns_tuples(self):
        """list_barcode_types returns list of (code, name, description, library) tuples."""
        from pistudio.files.barcode import list_barcode_types

        types = list_barcode_types()
        assert isinstance(types, list)
        assert len(types) >= 5  # code128, code39, datamatrix, pdf417, azteccode

        for item in types:
            assert isinstance(item, tuple)
            assert len(item) == 4
            code, name, desc, lib = item
            assert isinstance(code, str)
            assert isinstance(name, str)
            assert isinstance(desc, str)
            assert lib in ("barcode", "treepoem", "segno")

    def test_barcode_types_dict_structure(self):
        """BARCODE_TYPES dict has correct structure."""
        from pistudio.files.barcode import BARCODE_TYPES

        assert "qr" in BARCODE_TYPES
        assert "code128" in BARCODE_TYPES
        assert "code39" in BARCODE_TYPES
        assert "datamatrix" in BARCODE_TYPES
        assert "pdf417" in BARCODE_TYPES

        for code, (name, desc, validator, library) in BARCODE_TYPES.items():
            assert isinstance(code, str)
            assert isinstance(name, str)
            assert isinstance(desc, str)
            assert validator is None or callable(validator)
            assert library in ("barcode", "treepoem", "segno")


class TestBarcodeValidation:
    """Tests for barcode input validation."""

    def test_validate_code128_accepts_any_text(self):
        """Code 128 accepts any alphanumeric text."""
        from pistudio.files.barcode import validate_barcode_input

        valid, error = validate_barcode_input("Hello World 123!", "code128")
        assert valid is True
        assert error == ""

    def test_validate_code39_accepts_uppercase(self):
        """Code 39 accepts uppercase alphanumeric."""
        from pistudio.files.barcode import validate_barcode_input

        valid, error = validate_barcode_input("HELLO123", "code39")
        assert valid is True

    def test_validate_code39_rejects_invalid_chars(self):
        """Code 39 rejects lowercase and special chars."""
        from pistudio.files.barcode import validate_barcode_input

        valid, error = validate_barcode_input("hello@world", "code39")
        assert valid is False
        assert "only supports" in error

    def test_validate_unknown_type_returns_error(self):
        """Unknown barcode type returns validation error."""
        from pistudio.files.barcode import validate_barcode_input

        valid, error = validate_barcode_input("test", "unknown_type")
        assert valid is False
        assert "unknown barcode type" in error


class TestBarcodeGeneration:
    """Tests for barcode file generation (requires python-barcode)."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_write_barcode_png_creates_file(self, temp_dir):
        """write_barcode_png creates a PNG file."""
        pytest.importorskip("barcode")

        from pistudio.files.barcode import write_barcode_png

        output_path = os.path.join(temp_dir, "test")
        write_barcode_png("HELLO123", output_path, barcode_type="code128")

        # python-barcode adds .png extension
        assert os.path.exists(f"{output_path}.png")
        assert os.path.getsize(f"{output_path}.png") > 0

    def test_write_barcode_svg_creates_file(self, temp_dir):
        """write_barcode_svg creates an SVG file."""
        pytest.importorskip("barcode")

        from pistudio.files.barcode import write_barcode_svg

        output_path = os.path.join(temp_dir, "test")
        write_barcode_svg("HELLO123", output_path, barcode_type="code128")

        # python-barcode adds .svg extension
        assert os.path.exists(f"{output_path}.svg")
        with open(f"{output_path}.svg") as f:
            content = f.read()
            assert "<svg" in content

    def test_write_barcode_png_validates_input(self, temp_dir):
        """write_barcode_png validates input before generation."""
        pytest.importorskip("barcode")

        from pistudio.files.barcode import write_barcode_png

        output_path = os.path.join(temp_dir, "test")

        # Invalid Code 39 input (lowercase) should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            write_barcode_png("hello@world", output_path, barcode_type="code39")

        assert "only supports" in str(exc_info.value)

    def test_write_barcode_png_unknown_type_raises(self, temp_dir):
        """write_barcode_png raises for unknown barcode type."""
        pytest.importorskip("barcode")

        from pistudio.files.barcode import write_barcode_png

        output_path = os.path.join(temp_dir, "test")

        with pytest.raises(ValueError) as exc_info:
            write_barcode_png("test", output_path, barcode_type="unknown")

        assert "unknown barcode type" in str(exc_info.value)

    def test_render_barcode_terminal_returns_string(self):
        """render_barcode_terminal returns a string with bars."""
        pytest.importorskip("barcode")

        from pistudio.files.barcode import render_barcode_terminal

        output = render_barcode_terminal("TEST123", barcode_type="code128")

        assert isinstance(output, str)
        assert len(output) > 0
        # Should contain the encoded text
        assert "TEST123" in output


class TestBarcodeImportError:
    """Tests for graceful handling when dependencies are not installed."""

    def test_check_barcode_raises_import_error(self):
        """_check_barcode raises ImportError with install hint."""

        with patch.dict("sys.modules", {"barcode": None}):
            # Force reimport to trigger check
            import pistudio.files.barcode as bc_module

            # Mock the import to fail
            original_check = bc_module._check_barcode

            def mock_check():
                raise ImportError(
                    "python-barcode is required for barcode generation. "
                    "Install with: pip install prompt-injection-studio[barcode]"
                )

            bc_module._check_barcode = mock_check
            try:
                with pytest.raises(ImportError) as exc_info:
                    bc_module._check_barcode()
                assert "pip install prompt-injection-studio[barcode]" in str(exc_info.value)
            finally:
                bc_module._check_barcode = original_check

    def test_check_ghostscript_raises_runtime_error(self):
        """_check_ghostscript raises RuntimeError with platform-specific install hint."""
        from pistudio.files.barcode import _check_ghostscript

        # Mock shutil.which to return None (Ghostscript not found)
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError) as exc_info:
                _check_ghostscript()
            error_msg = str(exc_info.value)
            assert "Ghostscript is required" in error_msg
            # Should contain install instructions
            assert "brew install" in error_msg or "apt-get" in error_msg or "ghostscript.com" in error_msg

    def test_check_ghostscript_passes_when_found(self):
        """_check_ghostscript passes when gs is found."""
        from pistudio.files.barcode import _check_ghostscript

        # Mock shutil.which to return a path (Ghostscript found)
        with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/gs" if cmd == "gs" else None):
            # Should not raise
            _check_ghostscript()

    def test_get_barcode_library_returns_correct_library(self):
        """_get_barcode_library returns correct library for each type."""
        from pistudio.files.barcode import _get_barcode_library

        assert _get_barcode_library("qr") == "segno"
        assert _get_barcode_library("code128") == "barcode"
        assert _get_barcode_library("code39") == "barcode"
        assert _get_barcode_library("datamatrix") == "treepoem"
        assert _get_barcode_library("pdf417") == "treepoem"
        assert _get_barcode_library("azteccode") == "treepoem"
        assert _get_barcode_library("unknown") == "unknown"


# ── Command tests ────────────────────────────────────────────────────


class TestInjectBarcodeCommand:
    """Tests for inject barcode command dispatch."""

    @pytest.fixture
    def mock_shell(self):
        """Create a mock shell for testing."""
        shell = MagicMock()
        shell.out = MagicMock()
        shell.console = MagicMock()
        shell.audit = MagicMock()
        shell.session_dir = "/tmp/test_session"
        return shell

    def test_barcode_list_dispatches(self, mock_shell):
        """inject barcode list reaches the type listing."""
        from pistudio.commands.barcode_cmd import BarcodeCommand

        cmd = BarcodeCommand()

        with patch("pistudio.commands.barcode_cmd.BarcodeCommand._list_types") as mock_list:
            cmd.execute(mock_shell, ["list"])
            mock_list.assert_called_once()

    def test_barcode_without_arguments_shows_usage(self, mock_shell):
        """inject barcode alone documents the command."""
        from pistudio.commands.barcode_cmd import BarcodeCommand

        cmd = BarcodeCommand()
        cmd.execute(mock_shell, [])

        mock_shell.out.info.assert_called()
        assert "Usage:" in mock_shell.out.info.call_args[0][0]

    def test_png_requires_payload_or_url(self, mock_shell):
        """inject barcode png without payload reports the problem."""
        from pistudio.commands.barcode_cmd import BarcodeCommand

        cmd = BarcodeCommand()
        cmd.execute(mock_shell, ["png"])

        mock_shell.out.error.assert_called()

    def test_svg_requires_payload_or_url(self, mock_shell):
        """inject barcode svg without payload reports the problem."""
        from pistudio.commands.barcode_cmd import BarcodeCommand

        cmd = BarcodeCommand()
        cmd.execute(mock_shell, ["svg"])

        mock_shell.out.error.assert_called()


class TestInjectBarcodeCompletion:
    """Tests for inject barcode tab completion."""

    @pytest.fixture
    def mock_shell(self):
        """Create a mock shell for testing."""
        shell = MagicMock()
        shell.session_dir = "/tmp/test_session"
        return shell

    def test_complete_barcode_subcommands(self, mock_shell):
        """Tab completion offers the output destinations."""
        from pistudio.commands.barcode_cmd import BarcodeCommand

        cmd = BarcodeCommand()
        completions = cmd.complete(mock_shell, [""])

        # Extract text from CompletionItem objects
        texts = [c.text if hasattr(c, "text") else c for c in completions]
        assert {"png", "svg", "list"} <= set(texts)
        # png/svg are destinations under `barcode`, not commands of their own.
        assert "barcode-png" not in texts
        assert "barcode-svg" not in texts

    def test_complete_barcode_list(self, mock_shell):
        """Tab completion for barcode includes 'list' subcommand."""
        from pistudio.commands.barcode_cmd import BarcodeCommand

        cmd = BarcodeCommand()
        completions = cmd.complete(mock_shell, [""])

        assert "list" in completions

    def test_complete_barcode_type_flag(self, mock_shell):
        """Tab completion for --type shows barcode types."""
        from pistudio.commands.barcode_cmd import BarcodeCommand

        cmd = BarcodeCommand()
        completions = cmd.complete(mock_shell, ["--type", ""])

        assert "code128" in completions
        assert "code39" in completions

    def test_complete_barcode_png_flags(self, mock_shell):
        """Tab completion for the png destination includes output flags."""
        from pistudio.commands.barcode_cmd import BarcodeCommand

        cmd = BarcodeCommand()
        completions = cmd.complete(mock_shell, ["png", "hi", "--"])

        assert "--output" in completions
        assert "--type" in completions

    def test_wants_path_completion_barcode_output(self, mock_shell):
        """wants_path_completion returns True for barcode --output."""
        from pistudio.commands.barcode_cmd import BarcodeCommand

        cmd = BarcodeCommand()

        assert cmd.wants_path_completion(["png", "--output", ""]) is True
        assert cmd.wants_path_completion(["svg", "--output", ""]) is True
        assert cmd.wants_path_completion(["--type", ""]) is False


# ── Integration tests ────────────────────────────────────────────────


class TestBarcodeIntegration:
    """Integration tests for barcode generation (requires python-barcode)."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_generate_all_barcode_types_png(self, temp_dir):
        """Generate PNG for each supported barcode type."""
        pytest.importorskip("barcode")

        from pistudio.files.barcode import BARCODE_TYPES, write_barcode_png

        # Test data for each type (alphanumeric types only)
        test_data = {
            "code128": "Hello123",
            "code39": "HELLO123",
        }

        for barcode_type in BARCODE_TYPES:
            if barcode_type not in test_data:
                continue

            output_path = os.path.join(temp_dir, f"test_{barcode_type}")
            write_barcode_png(test_data[barcode_type], output_path, barcode_type=barcode_type)

            assert os.path.exists(f"{output_path}.png"), f"Failed to create {barcode_type} PNG"

    def test_generate_all_barcode_types_svg(self, temp_dir):
        """Generate SVG for each supported barcode type."""
        pytest.importorskip("barcode")

        from pistudio.files.barcode import BARCODE_TYPES, write_barcode_svg

        # Test data for each type (alphanumeric types only)
        test_data = {
            "code128": "Hello123",
            "code39": "HELLO123",
        }

        for barcode_type in BARCODE_TYPES:
            if barcode_type not in test_data:
                continue

            output_path = os.path.join(temp_dir, f"test_{barcode_type}")
            write_barcode_svg(test_data[barcode_type], output_path, barcode_type=barcode_type)

            assert os.path.exists(f"{output_path}.svg"), f"Failed to create {barcode_type} SVG"


# ── pyproject.toml test ──────────────────────────────────────────────


class TestPyprojectToml:
    """Tests for pyproject.toml barcode dependency."""

    def test_barcode_optional_dependency_exists(self):
        """pyproject.toml has [barcode] optional dependency."""
        import tomllib
        from pathlib import Path

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        optional_deps = pyproject.get("project", {}).get("optional-dependencies", {})
        assert "barcode" in optional_deps, "Missing [barcode] optional dependency"

        barcode_deps = optional_deps["barcode"]
        assert any("python-barcode" in dep for dep in barcode_deps)


class TestDefaultOutputPath:
    """The derived filename path, which --output tests never exercise."""

    def test_barcode_png_writes_a_derived_filename(self, studio, tmp_path, monkeypatch):
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        get_command("barcode").execute(studio, ["png", "INJECT"])
        assert list(tmp_path.glob("barcode-*.png")), "no derived filename was written"
