"""The top-level command surface.

There used to be an ``inject`` verb wrapping serve/file/audio/barcode/hw,
which carried no information — everything in the tool is injection — and
cost a word on every invocation.  Payload management was reachable both as
``inject payloads`` and ``hw payloads``.  These tests pin the flat surface
that replaced both.
"""

import re

import pytest

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

EXPECTED = {
    "serve",
    "file",
    "audio",
    "barcode",
    "encode",
    "hw",
    "payloads",
    # `settings` is the one place preferences are listed and changed; `theme`
    # stays because switching theme is frequent enough to deserve a verb, and
    # it writes through to `ui.theme`.
    "settings",
    "theme",
    "tutorial",
}


def _out(studio) -> str:
    """Console output with colour escapes and line wrapping removed."""
    return " ".join(_ANSI.sub("", studio.buf.getvalue()).split())


@pytest.fixture(autouse=True)
def _registered():
    from pistudio.commands import register_all_commands

    register_all_commands()


class TestTheInjectVerbIsGone:
    @pytest.mark.parametrize("name", ["inject", "pi", "prompt-inject", "studio"])
    def test_name_does_not_resolve(self, name):
        from pistudio.commands import get_command

        assert get_command(name) is None

    @pytest.mark.parametrize("name", ["inject", "pi", "prompt-inject", "studio"])
    def test_name_is_not_a_cli_choice(self, name):
        from pistudio.cli import _command_names

        assert name not in _command_names()

    def test_the_router_module_is_deleted(self):
        with pytest.raises(ImportError):
            import pistudio.commands.studio  # noqa: F401

    def test_no_usage_string_tells_you_to_type_inject(self):
        """Help that names a removed command is worse than no help.

        Matches anywhere in the line, not just at the start: the first
        version of this test only checked line starts and so missed
        ``Usage: inject file <format>``.
        """
        from pistudio.commands import all_commands

        pattern = re.compile(r"\binject\s+(serve|file|audio|barcode|hw|payloads|theme|tutorial)\b")
        for cmd in all_commands():
            for line in (cmd.usage or "").splitlines():
                assert not pattern.search(line), f"{cmd.name} usage says: {line.strip()}"

    def test_no_error_message_tells_you_to_type_inject(self, studio):
        """Cross-command guidance must name the command that exists."""
        from pistudio.commands import get_command

        get_command("file").execute(studio, ["tts-wav", "x"])
        out = _out(studio)
        assert "audio tts-wav" in out
        assert "inject audio" not in out


class TestEveryCapabilityIsTopLevel:
    def test_the_expected_commands_are_registered(self):
        from pistudio.commands import all_commands

        assert {c.name for c in all_commands()} == EXPECTED

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_each_is_reachable_from_the_cli(self, name):
        from pistudio.cli import _command_names

        assert name in _command_names()

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_each_is_visible_in_help(self, name):
        """A command nobody can discover may as well not exist."""
        from pistudio.commands import visible_command_names

        assert name in visible_command_names()

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_each_documents_itself(self, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        assert cmd.help, f"{name} has no one-line help"
        assert cmd.usage, f"{name} has no usage text"


class TestContextsAreOneLevelDeep:
    def test_namespaces_resolve_as_contexts(self):
        from pistudio.commands import get_command, get_nested_command

        for name in EXPECTED:
            if get_command(name).namespace:
                assert get_nested_command([name]) is not None

    def test_no_two_level_path_resolves(self):
        from pistudio.commands import get_nested_command

        assert get_nested_command(["hw", "flipper"]) is None
        assert get_nested_command(["file", "list"]) is None


class TestThePromptCommandIsGone:
    """`prompt` duplicated `payloads` and half of it was never implemented.

    ``--prompt <nick>`` and ``--payload <name>`` both resolved a name to text
    and used it as payload content, and the seven ``category="system"``
    prompts described attacker tooling behaviour that no code path ever
    applied to an LLM call — ``core/llm.py`` has no system-prompt handling.
    """

    @pytest.mark.parametrize("name", ["prompt", "prompts"])
    def test_the_command_does_not_resolve(self, name):
        from pistudio.commands import get_command

        assert get_command(name) is None

    def test_the_modules_are_deleted(self):
        for module in (
            "pistudio.commands.prompt_cmd",
            "pistudio.commands.prompt_cmd_helpers",
            "pistudio.prompts.registry",
        ):
            with pytest.raises(ImportError):
                __import__(module)

    def test_the_prompt_flag_is_rejected(self, studio, tmp_path, monkeypatch):
        """--payload is the one way to name stored text."""
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        get_command("file").execute(studio, ["md", "x", "--prompt", "red-team-aggressive"])
        assert "Unknown flag: --prompt" in _out(studio)

    def test_an_unknown_flags_value_never_becomes_payload_text(self, studio, tmp_path, monkeypatch):
        """Dropping the flag token left its value behind in the payload.

        `file md "x" --prompt red-team-aggressive` wrote the payload
        "x red-team-aggressive" — the flag's argument silently became content.
        """
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        out = tmp_path / "leak.md"
        get_command("file").execute(studio, ["md", "x", "--prompt", "some-name", "--output", str(out)])
        assert not out.exists(), "a file was written despite an unrecognised flag"

    def test_a_typo_in_a_known_flag_is_caught(self, studio, tmp_path, monkeypatch):
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        get_command("file").execute(studio, ["md", "x", "--voise", "Guy"])
        assert "Unknown flag: --voise" in _out(studio)

    def test_payload_flag_still_resolves_stored_text(self, studio, tmp_path, monkeypatch):
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        out = tmp_path / "p.md"
        get_command("file").execute(studio, ["md", "--payload", "ignore-instructions", "--output", str(out)])
        assert out.is_file()
        assert "maintenance mode" in out.read_text()

    def test_no_completion_offers_the_prompt_flag(self, studio):
        from pistudio.commands import all_commands

        for cmd in all_commands():
            offered = {getattr(c, "text", c) for c in cmd.complete(studio, [""])}
            assert "--prompt" not in offered, f"{cmd.name} still completes --prompt"

    def test_the_ported_jailbreak_wording_is_vendor_neutral(self):
        """The prompt registry's phrasing was better than the payload's."""
        from pistudio.hardware.payloads import BUILTIN_PAYLOADS

        text = next(p.text for p in BUILTIN_PAYLOADS if p.name == "role-override")
        assert "safety policies" in text
        assert "OpenAI policy" not in text


class TestPayloadLibraryMovedOutOfHw:
    """It backs --payload in serve/file/audio too, so it is not hw-specific."""

    def test_payloads_is_not_an_hw_subcommand(self):
        from pistudio.commands import get_command

        hw = get_command("hw")
        assert "payloads" not in hw.subcommands

    def test_hw_points_at_the_top_level_command(self, studio):
        from pistudio.commands import get_command

        get_command("hw").execute(studio, ["payloads", "list"])
        out = _out(studio)
        assert "moved out of hw" in out
        assert "payloads list" in out

    def test_the_library_still_backs_the_payload_flag(self, studio):
        """Removing the duplicate command must not touch --payload."""
        from pistudio.hardware.payloads import payload_names

        assert "ignore-instructions" in payload_names(studio.session_dir)

    def test_payloads_list_works_standalone(self, studio):
        from pistudio.commands import get_command

        get_command("payloads").execute(studio, ["list"])
        assert "ignore-instructions" in _out(studio)
