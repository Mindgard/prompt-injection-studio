"""Tests for QR codes under the consolidated ``inject barcode`` command.

QR used to be reachable four ways — ``inject qr``, ``inject qr-png``,
``inject file qr`` and ``inject barcode --type qr`` — across two separate
implementations with different flag names.  These tests pin the single
surface that replaced them, and in particular that the options which only
existed on the old ``file qr`` path (border, micro, dark/light) survived
the move.
"""

import re

import pytest

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _out(studio) -> str:
    """Console output with colour escapes and line wrapping removed."""
    return " ".join(_ANSI.sub("", studio.buf.getvalue()).split())


def _has_segno() -> bool:
    try:
        import segno  # noqa: F401  (probe: skip tests when absent)

        return True
    except ImportError:
        return False


segno_only = pytest.mark.skipif(not _has_segno(), reason="segno not installed")


# ── Options carried over from the old `file qr` path ──────────────


class TestQROptionsSurvivedTheMove:
    """Each option here existed only on the deleted implementation."""

    @segno_only
    def test_border_is_honoured(self, tmp_path):
        from PIL import Image

        from pistudio.files.barcode import write_barcode_png

        narrow = tmp_path / "narrow.png"
        wide = tmp_path / "wide.png"
        write_barcode_png("payload", str(narrow), scale=4, border=1)
        write_barcode_png("payload", str(wide), scale=4, border=8)
        assert Image.open(wide).size[0] > Image.open(narrow).size[0]

    @segno_only
    def test_micro_produces_a_micro_symbol(self, tmp_path):
        """A silent fallback to a standard QR would make --micro a lie."""
        zxingcpp = pytest.importorskip("zxingcpp")
        from PIL import Image

        from pistudio.files.barcode import write_barcode_png

        out = tmp_path / "micro.png"
        write_barcode_png("SHORT", str(out), scale=8, micro=True)
        formats = [str(r.format) for r in zxingcpp.read_barcodes(Image.open(out))]
        assert any("Micro" in f for f in formats), formats

    @segno_only
    def test_micro_rejects_an_oversized_payload_with_a_usable_message(self):
        from pistudio.files.barcode import render_barcode_terminal

        with pytest.raises(ValueError, match="too long for a Micro QR"):
            render_barcode_terminal("x" * 200, micro=True)

    @segno_only
    def test_dark_and_light_are_honoured(self, tmp_path):
        from PIL import Image

        from pistudio.files.barcode import write_barcode_png

        out = tmp_path / "coloured.png"
        write_barcode_png("payload", str(out), scale=4, dark="red", light="white")
        colours = {c for _, c in Image.open(out).convert("RGB").getcolors(maxcolors=100000)}
        assert (255, 0, 0) in colours

    @segno_only
    def test_svg_accepts_the_same_options(self, tmp_path):
        from pistudio.files.barcode import write_barcode_svg

        out = tmp_path / "q.svg"
        write_barcode_svg("payload", str(out), scale=5, border=3, dark="darkblue", error_level="H")
        assert "<svg" in out.read_text()


# ── Command surface ───────────────────────────────────────────────


class TestBarcodeCommandDispatch:
    @segno_only
    def test_bare_payload_renders_in_the_terminal(self, studio):
        from pistudio.commands import get_command

        get_command("barcode").execute(studio, ["hello"])
        assert studio.exit_code == 0

    def test_list_shows_every_type(self, studio):
        from pistudio.commands import get_command
        from pistudio.files.barcode import BARCODE_TYPES

        get_command("barcode").execute(studio, ["list"])
        assert studio.exit_code == 0
        for name in BARCODE_TYPES:
            assert name in _out(studio)

    def test_unknown_type_names_the_list_command(self, studio):
        from pistudio.commands import get_command

        get_command("barcode").execute(studio, ["x", "--type", "nope"])
        assert "barcode list" in _out(studio)

    def test_payload_is_required(self, studio):
        from pistudio.commands import get_command

        get_command("barcode").execute(studio, [])
        # With no arguments at all the command prints its usage.
        assert "Usage: barcode" in _out(studio)

    def test_flag_needing_a_value_says_so(self, studio):
        from pistudio.commands import get_command

        get_command("barcode").execute(studio, ["hi", "--type"])
        assert "--type needs a value" in _out(studio)


class TestFlagDimensionsAreEnforced:
    """A flag that silently does nothing is worse than one that errors."""

    def test_linear_flag_on_a_qr_code_is_rejected(self, studio):
        from pistudio.commands import get_command

        get_command("barcode").execute(studio, ["hi", "--no-text"])
        assert "--no-text" in _out(studio)
        assert "does not apply" in _out(studio)

    def test_matrix_flag_on_a_1d_code_is_rejected(self, studio):
        from pistudio.commands import get_command

        get_command("barcode").execute(studio, ["HI", "--type", "code128", "--dark", "red"])
        assert "--dark" in _out(studio)
        assert "does not apply" in _out(studio)

    def test_micro_is_qr_only(self, studio):
        from pistudio.commands import get_command

        get_command("barcode").execute(studio, ["HI", "--type", "datamatrix", "--micro"])
        assert "--micro applies to 'qr' only" in _out(studio)


class TestDefaultOutputPath:
    """Without --output the filename is derived; nothing covered this before.

    A refactor silently broke it (the derived name was computed and then
    discarded) and the whole suite still passed, because every other test
    passes --output explicitly.
    """

    @segno_only
    def test_png_writes_a_derived_filename(self, studio, tmp_path, monkeypatch):
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        get_command("barcode").execute(studio, ["png", "hello"])
        assert (tmp_path / "barcode-qr.png").is_file()

    @segno_only
    def test_svg_writes_a_derived_filename(self, studio, tmp_path, monkeypatch):
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        get_command("barcode").execute(studio, ["svg", "hello"])
        assert (tmp_path / "barcode-qr.svg").is_file()

    @segno_only
    def test_output_flag_overrides_the_default(self, studio, tmp_path, monkeypatch):
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        get_command("barcode").execute(studio, ["png", "hello", "--output", "custom.png"])
        assert (tmp_path / "custom.png").is_file()


class TestCompletion:
    def test_destinations_complete(self, studio):
        from pistudio.commands.barcode_cmd import BarcodeCommand

        results = [getattr(r, "text", r) for r in BarcodeCommand().complete(studio, [""])]
        assert {"png", "svg", "list"} <= set(results)

    def test_type_values_complete(self, studio):
        from pistudio.commands.barcode_cmd import BarcodeCommand

        results = BarcodeCommand().complete(studio, ["--type", ""])
        assert "qr" in results
        assert "code128" in results

    def test_error_level_values_complete(self, studio):
        from pistudio.commands.barcode_cmd import BarcodeCommand

        results = BarcodeCommand().complete(studio, ["--error-level", ""])
        assert {"L", "M", "Q", "H"} <= set(results)

    def test_file_only_flags_appear_for_png(self, studio):
        from pistudio.commands.barcode_cmd import BarcodeCommand

        results = BarcodeCommand().complete(studio, ["png", "hi", "--"])
        assert "--output" in results
        assert "--print" in results

    def test_file_only_flags_absent_in_the_terminal(self, studio):
        from pistudio.commands.barcode_cmd import BarcodeCommand

        results = BarcodeCommand().complete(studio, ["hi", "--"])
        assert "--output" not in results


class TestRemovedSurfacesAreGone:
    """The point of the consolidation: exactly one way to make a QR code."""

    @pytest.mark.parametrize("name", ["qr", "qr-png", "qr-svg"])
    def test_qr_is_no_longer_a_file_format(self, name):
        from pistudio.files.formats import FORMAT_REGISTRY

        assert name not in FORMAT_REGISTRY

    @pytest.mark.parametrize("sub", ["qr", "qr-png", "qr-svg", "barcode-png", "barcode-svg"])
    def test_old_subcommands_are_not_dispatched(self, sub):
        from pistudio.commands import get_command, register_all_commands

        register_all_commands()
        assert get_command(sub) is None

    def test_the_qrcode_module_is_deleted(self):
        with pytest.raises(ImportError):
            import pistudio.files.qrcode  # noqa: F401
