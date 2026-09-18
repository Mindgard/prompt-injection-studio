"""Interactive session behaviour.

``_dispatch`` is tested directly rather than through prompt_toolkit, which
needs a terminal.  It returns the new context, so navigation is a pure
function of (context, line).
"""

from __future__ import annotations

import pytest

from pistudio.commands import get_nested_command, register_all_commands
from pistudio.repl import _dispatch

register_all_commands()


class TestContextNavigation:
    def test_bare_namespace_enters_context(self, studio):
        assert _dispatch(studio, [], "hw") == ["hw"]

    def test_back_leaves_one_level(self, studio):
        assert _dispatch(studio, ["hw"], "back") == []

    def test_back_at_root_is_harmless(self, studio):
        assert _dispatch(studio, [], "back") == []

    @pytest.mark.parametrize("word", ["/", "~"])
    def test_slash_returns_to_root(self, studio, word):
        assert _dispatch(studio, ["hw"], word) == []

    def test_non_namespace_command_does_not_descend(self, studio):
        """`theme` runs, it is not a context."""
        assert _dispatch(studio, [], "theme") == []

    def test_unknown_command_reports_and_keeps_context(self, studio):
        context = _dispatch(studio, ["hw"], "definitely-not-a-command")
        assert context == ["hw"]


class TestContextualExecution:
    def test_command_runs_without_prefix_in_context(self, studio):
        """`list` inside `payloads` needs no `payloads` prefix."""
        _dispatch(studio, ["payloads"], "list")
        assert "ignore-instructions" in studio.buf.getvalue()

    def test_same_command_works_with_full_path_at_root(self, studio):
        _dispatch(studio, [], "payloads list")
        assert "ignore-instructions" in studio.buf.getvalue()

    def test_subcommand_needs_no_prefix_in_context(self, studio, monkeypatch):
        """`devices` inside `hw` resolves to `hw devices`."""
        monkeypatch.setattr("pistudio.hardware.hak5.device.find_bunny_volumes", lambda: ["/Volumes/BashBunny"])
        for target in (
            "pistudio.hardware.hak5.device.find_ducky_volumes",
            "pistudio.hardware.flipper.device.find_flipper_volumes",
            "pistudio.hardware.flipper.serial_console.find_flipper_serial_ports",
            "pistudio.hardware.hak5.serial_console.find_bunny_serial_ports",
        ):
            monkeypatch.setattr(target, lambda: [])

        _dispatch(studio, ["hw"], "devices")
        assert "BashBunny" in studio.buf.getvalue()


class TestHelp:
    def test_root_help_lists_commands(self, studio):
        _dispatch(studio, [], "help")
        out = studio.buf.getvalue()
        assert "serve" in out
        assert "hw" in out

    def test_context_help_lists_subcommands(self, studio):
        _dispatch(studio, ["hw"], "help")
        out = studio.buf.getvalue()
        assert "flipper" in out
        assert "ubertooth" in out


class TestEveryCommandIsTopLevel:
    """There is no wrapper verb; each command is reached by its own name."""

    def test_hw_is_a_top_level_command(self):
        from pistudio.commands import get_command

        cmd = get_command("hw")
        assert cmd is not None
        assert cmd.namespace is True

    def test_the_inject_verb_is_gone(self):
        from pistudio.commands import get_command

        for name in ("inject", "pi", "prompt-inject", "studio"):
            assert get_command(name) is None, f"'{name}' still resolves"

    def test_hw_resolves_by_path(self):
        cmd = get_nested_command(["hw"])
        assert cmd is not None
        assert cmd.name == "hw"

    def test_unknown_path_resolves_to_none(self):
        assert get_nested_command(["nope"]) is None
        assert get_nested_command([]) is None
        # Contexts are one level deep now.
        assert get_nested_command(["hw", "flipper"]) is None


class TestUsageMatchesHowYouInvoke:
    """Help must name the command the way the user actually types it.

    `inject file` and `inject embed` used to dispatch to the same handler
    whose usage text was written as `embed <format> ...` — so typing the
    documented name showed instructions for a hidden alias.
    """

    def test_file_usage_does_not_advertise_embed(self):
        from pistudio.commands.files import EmbedCommand

        usage = EmbedCommand().usage
        assert "file <format>" in usage
        # "embed in metadata" is the verb, not a command name.
        for line in usage.splitlines():
            stripped = line.strip()
            assert not stripped.startswith("embed "), f"usage still tells the user to type: {stripped}"

    def test_embed_is_no_longer_an_accepted_command(self):
        from pistudio.commands import get_command

        assert get_command("embed") is None
        assert get_command("file") is not None

    def test_usage_is_stripped_to_the_active_context(self):
        from pistudio.repl import for_context

        text = 'file pdf "..."\nfile list'
        assert for_context(text, ["file"]) == 'pdf "..."\nlist'

    def test_deeper_context_strips_the_longer_prefix_first(self):
        from pistudio.repl import for_context

        assert for_context("hw flipper deploy", ["hw", "flipper"]) == "deploy"

    def test_root_context_leaves_usage_alone(self):
        from pistudio.repl import for_context

        assert for_context("file list", []) == "file list"

    def test_help_for_a_subcommand_resolves_in_context(self, studio):
        """`help list` inside `file>` shows the subcommand's output, not an error."""
        _dispatch(studio, ["file"], "help list")
        out = studio.buf.getvalue()
        assert "No help for" not in out

    def test_generated_filenames_do_not_say_embed(self, studio, tmp_path):
        """The default output name is user-visible."""
        import os

        from pistudio.commands import get_command

        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            get_command("file").execute(studio, ["md", "hello world", "--output", "x.md"])
        finally:
            os.chdir(cwd)
        assert not any(f.name.startswith("embed-") for f in tmp_path.iterdir())


class TestAudioNamesMatchFormats:
    """`audio` is a curated view over the audio file formats, not a rename.

    The old mapping renamed three formats and pointed two at formats that did
    not exist, so `inject audio tts-mp3` and `inject audio spectrogram` were
    advertised in the help but failed with "Unknown format".
    """

    def test_every_audio_subcommand_is_a_real_format(self):
        from pistudio.files.formats import FORMAT_REGISTRY, audio_format_names

        for name in audio_format_names():
            assert name in FORMAT_REGISTRY, f"'inject audio {name}' maps to no such format"

    def test_audio_names_are_not_renamed(self):
        """A rename makes the two commands describe one thing in two ways."""
        from pistudio.files.formats import audio_format_names, get_format

        for name in audio_format_names():
            assert get_format(name).name == name

    def test_usage_lists_exactly_the_supported_formats(self):
        from pistudio.commands.audio_cmd import AudioCommand
        from pistudio.files.formats import audio_format_names

        usage = AudioCommand().usage
        for name in audio_format_names():
            assert name in usage, f"{name} is routed to `inject audio` but undocumented in its usage"
        # Names removed because they never existed as formats.
        for gone in ("tts-mp3", "spectrogram"):
            assert f"  {gone} " not in usage

    def test_completion_derives_from_the_same_list(self, studio):
        """Formats come from the registry; only the verbs are added by hand."""
        from pistudio.commands.audio_cmd import AudioCommand
        from pistudio.files.formats import audio_format_names

        completions = AudioCommand().complete(studio, [""])
        assert set(completions) == {*audio_format_names(), "live", "verify", "list"}
        assert set(audio_format_names()) < set(completions)

    def test_audio_formats_are_not_offered_by_inject_file(self, studio):
        """The two commands partition the registry; nothing appears in both."""
        from pistudio.commands.files import EmbedCommand
        from pistudio.files.formats import audio_format_names

        offered = set(EmbedCommand().complete(studio, [""]))
        assert not (offered & set(audio_format_names()))

    def test_removed_names_suggest_the_real_one(self, studio):
        """Dropping an alias should teach the correct name, not just fail."""
        from pistudio.commands import get_command

        get_command("audio").execute(studio, ["stego", "x"])
        out = studio.buf.getvalue()
        assert "audio-stego" in out

    def test_audio_format_runs_through_to_the_writer(self, studio, tmp_path):
        from pistudio.commands import get_command

        out = tmp_path / "s.png"
        get_command("audio").execute(studio, ["spectro-text", "test", "--output", str(out)])
        assert out.exists(), "spectro-text was one of the broken mappings"
