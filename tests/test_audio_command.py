"""Tests for the consolidated ``inject audio`` command.

Audio formats used to be split across two commands by an accident of
curation: ``inject audio`` carried a hardcoded tuple of seven signal
formats, while ``wav``/``mp3``/``flac``/``ogg``/``midi`` were reachable
only through ``inject file`` despite being filed under "Audio" in its
listing.  Routing is now a property of the format itself, and these tests
pin that the two commands partition the registry cleanly.
"""

import re

import pytest

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _out(studio) -> str:
    """Console output with colour escapes and line wrapping removed."""
    return " ".join(_ANSI.sub("", studio.buf.getvalue()).split())


# ── Routing ───────────────────────────────────────────────────────


class TestRoutingIsAPartition:
    """Every format belongs to exactly one of `inject file` / `inject audio`."""

    def test_every_format_is_routed_exactly_once(self):
        from pistudio.files.formats import FORMAT_REGISTRY, audio_format_names, file_format_names

        audio, files = set(audio_format_names()), set(file_format_names())
        assert not (audio & files), f"routed to both: {sorted(audio & files)}"
        assert audio | files == set(FORMAT_REGISTRY), "some format is routed to neither"

    def test_every_audio_category_format_is_routed_to_audio(self):
        """A new audio format filed under the Audio category must not be stranded."""
        from pistudio.files.formats import FORMAT_REGISTRY

        stranded = [f.name for f in FORMAT_REGISTRY.values() if f.category == "Audio" and not f.audio]
        assert not stranded, f"category=Audio but routed to `inject file`: {stranded}"

    def test_metadata_carriers_are_routed_to_audio(self):
        """These were the formats `inject audio` silently omitted before."""
        from pistudio.files.formats import audio_format_names

        for name in ("wav", "mp3", "flac", "ogg", "midi"):
            assert name in audio_format_names()

    def test_adversarial_audio_is_audio_despite_its_category(self):
        """It displays under 'Adversarial' beside anamorph, but is still audio."""
        from pistudio.files.formats import get_format

        fmt = get_format("adversarial-audio")
        assert fmt.category == "Adversarial"
        assert fmt.audio is True
        assert get_format("anamorph").audio is False


class TestCrossCommandGuidance:
    """Reaching for the wrong command should name the right one."""

    def test_file_names_the_audio_command(self, studio):
        from pistudio.commands import get_command

        get_command("file").execute(studio, ["tts-wav", "hello"])
        assert "audio tts-wav" in _out(studio)

    def test_file_names_the_audio_command_for_carriers(self, studio):
        from pistudio.commands import get_command

        get_command("file").execute(studio, ["mp3", "hello"])
        assert "audio mp3" in _out(studio)

    def test_audio_names_the_file_command(self, studio):
        from pistudio.commands import get_command

        get_command("audio").execute(studio, ["pdf", "hello"])
        assert "file pdf" in _out(studio)

    def test_unknown_audio_format_suggests_a_real_one(self, studio):
        from pistudio.commands import get_command

        get_command("audio").execute(studio, ["stego", "x"])
        assert "audio-stego" in _out(studio)


class TestListing:
    def test_audio_list_shows_both_attack_classes(self, studio):
        from pistudio.commands import get_command

        get_command("audio").execute(studio, ["list"])
        out = _out(studio)
        assert "listens" in out
        assert "parses" in out
        for name in ("tts-wav", "ultrasonic", "mp3", "midi"):
            assert name in out

    def test_file_list_omits_audio_formats(self, studio):
        from pistudio.commands import get_command
        from pistudio.files.formats import audio_format_names

        get_command("file").execute(studio, ["list"])
        out = _out(studio)
        for name in audio_format_names():
            assert f" {name} " not in out, f"{name} is listed by `inject file list`"

    def test_audio_list_json_mode(self, studio):
        import json

        from pistudio.commands.audio_cmd import AudioCommand
        from pistudio.files.formats import audio_format_names

        studio.json_mode = True
        AudioCommand().execute(studio, ["list"])
        data = json.loads(studio.buf.getvalue())
        assert {d["name"] for d in data} == set(audio_format_names())


class TestFlagApplicability:
    """A flag that reaches no code path should stop the command."""

    def test_voice_is_rejected_for_pdf(self, studio):
        from pistudio.commands import get_command

        get_command("file").execute(studio, ["pdf", "x", "--voice", "Guy"])
        out = _out(studio)
        assert "--voice does not apply to 'pdf'" in out
        assert "TTS formats" in out

    def test_freq_is_rejected_for_tts(self, studio):
        from pistudio.commands import get_command

        get_command("audio").execute(studio, ["tts-wav", "x", "--freq", "19000"])
        assert "--freq does not apply to 'tts-wav'" in _out(studio)

    def test_decoy_is_rejected_for_audio(self, studio):
        from pistudio.commands import get_command

        get_command("audio").execute(studio, ["ultrasonic", "x", "--decoy", "cat.png"])
        assert "--decoy does not apply to 'ultrasonic'" in _out(studio)

    def test_several_wrong_flags_are_reported_together(self, studio):
        from pistudio.commands import get_command

        get_command("file").execute(studio, ["pdf", "x", "--voice", "Guy", "--freq", "19000"])
        out = _out(studio)
        assert "--voice" in out
        assert "--freq" in out

    def test_nothing_is_written_when_a_flag_is_rejected(self, studio, tmp_path, monkeypatch):
        """The check must run before generation, not after."""
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        out = tmp_path / "x.pdf"
        get_command("file").execute(studio, ["pdf", "x", "--voice", "Guy", "--output", str(out)])
        assert not out.exists()

    @pytest.mark.parametrize(
        ("fmt", "flag"),
        [
            ("tts-wav", "--engine"),
            ("tts-whisper", "--carrier"),
            ("ultrasonic", "--freq"),
            ("ultrasonic", "--encrypt"),
            ("audio-stego", "--carrier"),
            ("adversarial-audio", "--model"),
            ("anamorph", "--decoy"),
        ],
    )
    def test_applicable_flags_are_accepted(self, fmt, flag):
        """The table must not reject a combination the writer supports."""
        from pistudio.commands.format_flags import unsupported_flags

        assert unsupported_flags(fmt, [flag, "value"]) == []

    def test_general_flags_are_never_rejected(self):
        from pistudio.commands.format_flags import unsupported_flags

        general = ["--output", "out.pdf", "--payload", "p", "--edit", "--url", "--metadata"]
        assert unsupported_flags("pdf", general) == []


class TestCompletion:
    def test_formats_complete(self, studio):
        from pistudio.commands.audio_cmd import AudioCommand
        from pistudio.files.formats import audio_format_names

        results = AudioCommand().complete(studio, [""])
        assert set(results) == {*audio_format_names(), "live", "verify", "list"}

    def test_engine_values_complete(self, studio):
        from pistudio.commands.audio_cmd import AudioCommand

        results = AudioCommand().complete(studio, ["tts-wav", "--engine", ""])
        assert "edge" in results

    def test_flags_are_scoped_to_the_format(self, studio):
        from pistudio.commands.audio_cmd import AudioCommand

        tts = AudioCommand().complete(studio, ["tts-wav", "--"])
        ultra = AudioCommand().complete(studio, ["ultrasonic", "--"])
        assert "--voice" in tts and "--voice" not in ultra
        assert "--freq" in ultra and "--freq" not in tts

    def test_carrier_wants_a_path(self):
        from pistudio.commands.audio_cmd import AudioCommand

        cmd = AudioCommand()
        assert cmd.wants_path_completion(["tts-whisper", "--carrier", ""]) is True
        assert cmd.wants_path_completion(["tts-whisper", "--engine", ""]) is False


class TestReplContext:
    def test_audio_is_a_nestable_context(self):
        from pistudio.commands import get_nested_command, register_all_commands

        register_all_commands()
        cmd = get_nested_command(["audio"])
        assert cmd is not None
        assert cmd.name == "audio"

    def test_usage_documents_every_routed_format(self):
        from pistudio.commands.audio_cmd import AudioCommand
        from pistudio.files.formats import audio_format_names

        for name in audio_format_names():
            assert name in AudioCommand().usage
