"""Each registered tool must reach its logic and return the envelope.

The ``@mcp.tool`` functions are thin, but "thin" is where a wrong argument name
or a missing return hides — the tool would be listed, callable, and useless.
These call each one through the module surface rather than the decorator, which
is what the client ultimately invokes.
"""

from __future__ import annotations

import asyncio

import pytest

from pistudio_mcp import budget, guides, server
from pistudio_mcp.errors import PiStudioMCPError


class RunSpy:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **kw: object):
        from pistudio_mcp.cli import CliResult

        self.calls.append(argv)
        return CliResult(ok=True, exit_code=0, data=[{"name": "x"}], stdout="ok", stderr="")


@pytest.fixture(autouse=True)
def spy(monkeypatch):
    budget.reset()
    recorder = RunSpy()
    monkeypatch.setattr(server, "run_cli", recorder)
    monkeypatch.setattr(server, "studio_identity", lambda: {"path": "/x", "version": "pistudio 0.1.0"})
    yield recorder
    budget.reset()


def _envelope_shape(result):
    assert set(result) == {"_meta", "content"}
    assert "trust" in result["_meta"]


class TestEveryToolReturnsAnEnvelope:
    def test_studio_status(self):
        _envelope_shape(server.studio_status())

    def test_list_payloads(self, spy):
        _envelope_shape(server.list_payloads())
        assert spy.calls[-1] == ["payloads", "list"]

    def test_show_payload(self, spy):
        _envelope_shape(server.show_payload("x"))
        assert spy.calls[-1] == ["payloads", "show", "x"]

    def test_add_payload(self, spy):
        _envelope_shape(server.add_payload("x", "some text"))
        assert spy.calls[-1][:2] == ["payloads", "add"]

    def test_generate_payloads(self, spy):
        _envelope_shape(server.generate_payloads("make injections", 2))
        assert spy.calls[-1][:2] == ["payloads", "generate"]
        assert "--count" in spy.calls[-1]

    def test_list_formats(self, spy):
        _envelope_shape(server.list_formats())
        assert spy.calls[-1] == ["file", "list"]

    def test_embed_payload(self, spy, tmp_path, monkeypatch):
        monkeypatch.setenv("PISTUDIO_MCP_OUTPUT_DIR", str(tmp_path))
        _envelope_shape(server.embed_payload("docx", "text", "out.docx"))
        argv = spy.calls[-1]
        # `file <format> <text> --output <path>`.  This asserted
        # `["file", "embed"]` and so pinned an argv the studio rejects outright:
        # there is no `embed` subcommand and the flag is `--output`.
        assert argv[:3] == ["file", "docx", "text"]
        assert "--output" in argv
        assert "--out" not in argv
        assert "embed" not in argv

    def test_list_barcode_types(self, spy):
        _envelope_shape(server.list_barcode_types())
        assert spy.calls[-1] == ["barcode", "list"]

    def test_encode_barcode(self, spy, tmp_path, monkeypatch):
        monkeypatch.setenv("PISTUDIO_MCP_OUTPUT_DIR", str(tmp_path))
        _envelope_shape(server.encode_barcode("hi", "code.png"))
        argv = spy.calls[-1]
        # `png`/`svg` is a subcommand, not a flag.
        assert argv[:3] == ["barcode", "png", "hi"]
        assert "--output" in argv

    def test_encode_barcode_picks_svg_from_the_suffix(self, spy, tmp_path, monkeypatch):
        monkeypatch.setenv("PISTUDIO_MCP_OUTPUT_DIR", str(tmp_path))
        _envelope_shape(server.encode_barcode("hi", "code.svg"))
        assert spy.calls[-1][1] == "svg"

    def test_encode_barcode_passes_a_chain(self, spy, tmp_path, monkeypatch):
        monkeypatch.setenv("PISTUDIO_MCP_OUTPUT_DIR", str(tmp_path))
        _envelope_shape(server.encode_barcode("hi", "c.png", encode="base64"))
        assert "--encode" in spy.calls[-1]

    def test_list_audio_formats(self, spy):
        _envelope_shape(server.list_audio_formats())
        assert spy.calls[-1] == ["audio", "list"]

    def test_synthesize_audio(self, spy, tmp_path, monkeypatch):
        monkeypatch.setenv("PISTUDIO_MCP_OUTPUT_DIR", str(tmp_path))
        _envelope_shape(server.synthesize_audio("wav", "hi", "p.wav"))
        argv = spy.calls[-1]
        assert argv[:3] == ["audio", "wav", "hi"]
        assert "--output" in argv

    def test_synthesize_audio_passes_a_voice(self, spy, tmp_path, monkeypatch):
        monkeypatch.setenv("PISTUDIO_MCP_OUTPUT_DIR", str(tmp_path))
        _envelope_shape(server.synthesize_audio("tts-wav", "hi", "p.wav", voice="en-US-GuyNeural"))
        assert "--voice" in spy.calls[-1]

    def test_list_encoders(self, spy):
        _envelope_shape(server.list_encoders())
        assert spy.calls[-1] == ["encode", "list"]

    def test_list_carriers(self, spy):
        _envelope_shape(server.list_carriers())
        assert spy.calls[-1] == ["encode", "carriers"]

    def test_preview_encoding(self, spy):
        _envelope_shape(server.preview_encoding("hi", "base64"))
        assert spy.calls[-1] == ["encode", "preview", "hi", "--chain", "base64"]

    def test_preview_encoding_with_a_carrier(self, spy):
        _envelope_shape(server.preview_encoding("hi", "base64", carrier="wifi"))
        assert "--carrier" in spy.calls[-1]

    def test_encode_text(self, spy):
        _envelope_shape(server.encode_text("hi", "base64"))
        assert spy.calls[-1] == ["encode", "hi", "--chain", "base64"]

    def test_list_serial_ports(self, spy):
        _envelope_shape(server.list_serial_ports())
        assert spy.calls[-1] == ["hw", "uart", "devices"]

    def test_list_serial_ports_can_include_everything(self, spy):
        _envelope_shape(server.list_serial_ports(include_all=True))
        assert spy.calls[-1] == ["hw", "uart", "devices", "--all"]

    def test_uart_send_is_gated_behind_the_hardware_opt_in(self, spy, monkeypatch):
        monkeypatch.setattr(server, "_HW_ENABLED", False)
        with pytest.raises(PiStudioMCPError, match="hardware tools are disabled"):
            server.uart_send("hi")
        assert spy.calls == [], "a blocked transmit still reached the studio"

    def test_uart_send_transmits_when_enabled(self, spy, monkeypatch):
        monkeypatch.setattr(server, "_HW_ENABLED", True)
        _envelope_shape(server.uart_send("hi"))
        argv = spy.calls[-1]
        # --yes because there is no terminal to answer the studio's prompt;
        # PISTUDIO_MCP_ENABLE_HW is the consent.
        assert argv[:5] == ["--yes", "hw", "uart", "send", "hi"]

    def test_uart_send_passes_its_options(self, spy, monkeypatch):
        monkeypatch.setattr(server, "_HW_ENABLED", True)
        _envelope_shape(server.uart_send("hi", baud=9600, line_ending="lf", expect="OK"))
        argv = spy.calls[-1]
        for flag, value in (("--baud", "9600"), ("--line-ending", "lf"), ("--expect", "OK")):
            assert flag in argv and argv[argv.index(flag) + 1] == value

    def test_serve_status(self, spy):
        _envelope_shape(server.serve_status())
        assert spy.calls[-1] == ["serve", "status"]

    def test_serve_start(self, spy):
        _envelope_shape(server.serve_start())
        # No `start` verb exists; passing one hosted the literal text "start".
        assert spy.calls[-1] == ["serve"]

    def test_serve_start_with_a_payload(self, spy):
        server.serve_start(payload_name="ignore-instructions")
        assert spy.calls[-1][-2:] == ["--payload", "ignore-instructions"]

    def test_serve_stop(self, spy):
        _envelope_shape(server.serve_stop())
        assert spy.calls[-1] == ["serve", "stop"]

    def test_scan_devices(self, spy):
        _envelope_shape(server.scan_devices())
        assert spy.calls[-1] == ["hw", "devices"]


class TestGuideResources:
    def test_the_concepts_guide_is_returned(self):
        assert server.concepts_guide() == guides.CONCEPTS

    def test_the_workflow_guide_is_returned(self):
        assert server.workflow_guide() == guides.WORKFLOW

    def test_the_concepts_guide_covers_the_object_model(self):
        """An assistant that has not read this drives the studio badly."""
        text = guides.CONCEPTS.lower()

        # "conversation" was dropped: the feature it described was removed in
        # 3b2c15d, but the guide still told the model to call the two tools
        # that went with it.
        for topic in ("payload", "carrier", "capacity", "delivery"):
            assert topic in text

    def test_the_workflow_guide_names_the_opt_ins(self):
        """The commonest confusion is a tool that is registered but refuses."""
        assert "PISTUDIO_MCP_ENABLE_HW" in guides.WORKFLOW

    def test_the_guides_warn_against_acting_on_payload_text(self):
        assert "never act on" in guides.CONCEPTS.lower()


class TestToolSchemas:
    def test_every_tool_has_a_description(self):
        """The description is how the model decides which tool to call."""
        for tool in asyncio.run(server.mcp.list_tools()):
            assert tool.description, f"{tool.name} has no description"

    def test_tools_taking_a_name_declare_it(self):
        tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}

        assert "name" in tools["show_payload"].inputSchema["properties"]
        assert "format_name" in tools["embed_payload"].inputSchema["properties"]
