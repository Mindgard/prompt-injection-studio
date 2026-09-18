"""Guardrails keeping the hardware docs honest.

docs/hak5.md once documented roughly thirty subcommands against a CLI that had
four, so the entire quick start failed on its first step. These tests fail when
a doc names a command or flag the code does not provide.
"""

import inspect
import pathlib
import re

import pytest

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"

# Subcommands of the shared namespaces, taken from the dispatch in command.py.
PAYLOAD_SUBS = {"list", "show", "add", "edit", "rm", "generate"}

# An *invocation* of a command, as opposed to the word in a sentence. Anchored
# to a line start (indented example blocks) or a backtick, because these used
# to match `\binject audio (...)` -- a verb removed long ago, so they matched
# nothing and passed vacuously while guarding nothing.
_AUDIO_INVOCATION = re.compile(r"(?:^\s*|`)audio ([a-z][\w-]*)", re.MULTILINE)
_FILE_INVOCATION = re.compile(r"(?:^\s*|`)file ([a-z][\w-]*)", re.MULTILINE)


def _doc(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def _audio_verbs() -> set[str]:
    """``audio`` subcommands that are actions rather than formats.

    Derived from the command rather than hardcoded, so adding a verb like
    ``verify`` does not make this test start reporting it as a missing format.
    """
    from pistudio.commands import get_command, register_all_commands
    from pistudio.files.formats import FORMAT_REGISTRY

    register_all_commands()
    audio = get_command("audio")
    subs = set(audio.subcommands or {}) if audio else set()
    return {s for s in subs if s not in FORMAT_REGISTRY} | {"adversarial"}


class TestHak5DocMatchesCode:
    def test_every_documented_device_subcommand_exists(self):
        from pistudio.commands.hw.files import _SUBS as FILE_SUBS
        from pistudio.commands.hw.hak5 import _SUBS as HAK5_SUBS

        valid = {
            "payloads": PAYLOAD_SUBS,
            "files": set(FILE_SUBS),
            "bunny": set(HAK5_SUBS),
            "ducky": set(HAK5_SUBS) - {"tty"},
        }
        doc = _doc("hak5.md")

        unknown = []
        for namespace, sub in re.findall(r"\bhw (payloads|files|bunny|ducky) ([a-z][\w-]*)", doc):
            if sub not in valid[namespace]:
                unknown.append(f"hw {namespace} {sub}")

        # The doc states that these do not exist; that sentence is the point.
        allowed_negatives = {"hw bunny add", "hw ducky list"}
        assert set(unknown) <= allowed_negatives, f"documented but not implemented: {sorted(set(unknown))}"

    def test_every_documented_compile_flag_is_honoured(self):
        """A parsed-then-ignored flag is worse than an unimplemented one."""
        from pistudio.commands.hw.hak5 import _compile_options

        opts = _compile_options(
            {
                "start-delay": "2000",
                "default-delay": "20",
                "preamble": "Q GUI r",
                "switch": "2",
                "os": "linux",
                "layout": "us",
            }
        )
        assert opts.ducky_payload["start_delay"] == 2000
        assert opts.ducky_payload["default_delay"] == 20
        assert opts.bunny_payload["preamble"] == "Q GUI r"
        assert opts.switch == 2
        assert opts.os_target == "linux"
        assert opts.layout == "us"

    def test_documented_layouts_match_the_keymaps(self):
        from pistudio.hardware.hak5.keymaps import LAYOUTS

        doc = _doc("hak5.md")
        for layout in LAYOUTS:
            assert f"`{layout}`" in doc, f"layout {layout} is available but undocumented"

    def test_documented_os_targets_are_the_supported_ones(self):
        from pistudio.hardware.hak5.compiler_bunny import _OS_PATH_TEMPLATES

        doc = _doc("hak5.md")
        for os_target in _OS_PATH_TEMPLATES:
            assert f"`{os_target}`" in doc, f"{os_target} is supported but undocumented"


class TestFlipperDocMatchesCode:
    """docs/flipper.md documented a Sub-GHz vector and missed half the CLI.

    It covered BadUSB, NFC, Bluetooth and Sub-GHz while ``sync``,
    ``sync-results``, ``remote`` and the whole ``sequence`` family went
    unmentioned, and it pointed at a FLIPPER_GUIDE.md that was never in the
    tree.
    """

    def _real_subcommands(self) -> set[str]:
        from pistudio.commands.hw import flipper as flipper_mod

        src = inspect.getsource(flipper_mod.handle_flipper)
        return set(re.findall(r'"([a-z][\w-]*)": lambda', src))

    def test_every_documented_subcommand_exists(self):
        documented = set(re.findall(r"\bhw flipper ([a-z][\w-]*)", _doc("flipper.md")))

        unknown = documented - self._real_subcommands()
        assert not unknown, f"documented but not implemented: {sorted(unknown)}"

    def test_every_subcommand_is_documented(self):
        doc = _doc("flipper.md")

        missing = [sub for sub in self._real_subcommands() if f"hw flipper {sub}" not in doc]
        assert not missing, f"implemented but undocumented: {sorted(missing)}"

    def test_the_completion_list_matches_the_dispatch(self):
        """A subcommand offered by tab completion but not routed is a dead end."""
        from pistudio.commands.hw import flipper as flipper_mod

        src = inspect.getsource(flipper_mod.complete_flipper)
        completed = set(re.findall(r'^\s+"([a-z][\w-]*)",', src, re.MULTILINE))

        assert completed <= self._real_subcommands(), (
            f"offered by completion but not routed: {sorted(completed - self._real_subcommands())}"
        )

    def test_documented_card_types_match_the_encoder(self):
        from pistudio.hardware.flipper.nfc import SUPPORTED_CARD_TYPES

        doc = _doc("flipper.md")
        for card_type in SUPPORTED_CARD_TYPES:
            assert f"`{card_type}`" in doc, f"{card_type} is supported but undocumented"

    def test_documented_card_capacities_are_accurate(self):
        """A capacity that overstates the card sends the operator to a failure."""
        from pistudio.hardware.flipper.nfc import SUPPORTED_CARD_TYPES, get_max_payload_size

        doc = _doc("flipper.md")
        for card_type in SUPPORTED_CARD_TYPES:
            assert f"{get_max_payload_size(card_type)} bytes" in doc, f"{card_type} capacity is documented inaccurately"

    def test_documented_sequence_protocols_match_the_validator(self):
        from pistudio.hardware.flipper.sequence import VALID_PROTOCOLS

        doc = _doc("flipper.md")
        for protocol in VALID_PROTOCOLS:
            assert f"`{protocol}`" in doc, f"{protocol} is accepted but undocumented"

    def test_subghz_is_gone_from_the_doc(self):
        """It was removed from the FAP; documenting it advertises a dead vector."""
        doc = _doc("flipper.md").lower()

        assert "hw flipper subghz" not in doc
        assert ".sub" not in doc

    def test_referenced_guides_exist(self):
        """The help text and this doc both pointed at a file that never existed."""
        from pistudio.commands.hw.flipper import FLIPPER_HELP

        for name in re.findall(r"\(([A-Za-z_]+\.md)\)", _doc("flipper.md")):
            assert (DOCS / name).is_file(), f"flipper.md links to a missing doc: {name}"

        for name in re.findall(r"docs/([A-Za-z_]+\.md)", FLIPPER_HELP):
            assert (DOCS / name).is_file(), f"flipper help names a missing doc: {name}"

    def test_every_bridge_command_is_documented(self):
        """bridge.py cited a .c file that exists in no repo, so the wire
        protocol had no definition anywhere. An undocumented command cannot be
        checked against the firmware when it becomes available."""
        from pistudio.hardware.flipper import bridge as bridge_mod

        src = inspect.getsource(bridge_mod)
        # Verbs are the first word of each literal sent over the wire.
        sent = set(re.findall(r'_send(?:_recv)?\(f?"([A-Z]+)', src))
        doc = _doc("flipper-bridge-protocol.md")

        missing = sorted(verb for verb in sent if f"`{verb}" not in doc)
        assert not missing, f"sent on the wire but undocumented: {missing}"

    def test_the_documented_baud_rate_matches_the_code(self):
        from pistudio.hardware.flipper.bridge import _BAUD_RATE

        assert str(_BAUD_RATE) in _doc("flipper-bridge-protocol.md")

    def test_documented_flags_are_parsed(self):
        """A flag in the table that no handler reads is a phantom feature."""
        from pistudio.commands.hw import flipper as flipper_mod
        from pistudio.commands.hw import flipper_remote, flipper_sync

        sources = "".join(inspect.getsource(mod) for mod in (flipper_mod, flipper_remote, flipper_sync))
        documented = set(re.findall(r"\| `(--[a-z-]+)`", _doc("flipper.md")))

        unparsed = sorted(flag for flag in documented if f'"{flag}"' not in sources)
        assert not unparsed, f"documented but never parsed: {unparsed}"


class TestServeDocMatchesCode:
    def test_the_exposure_flags_are_documented_as_prompting(self):
        """--host and --ngrok now confirm; the docs must not imply otherwise."""
        from pistudio.commands.serve import _confirm_exposure

        source = inspect.getsource(_confirm_exposure)
        assert "public internet" in source
        assert "shell.confirm" in source


class TestStudioDocMatchesCode:
    """docs/STUDIO.md named three audio formats that never existed.

    ``tts-mp3``, ``stego`` and ``spectrogram`` were documented with usage
    examples and flag tables; the real names are ``tts-wav``,
    ``audio-stego`` and ``spectro-text``.
    """

    def test_every_documented_audio_format_exists(self):
        from pistudio.files.formats import FORMAT_REGISTRY

        doc = _doc("STUDIO.md")
        named = set(re.findall(_AUDIO_INVOCATION, doc)) - _audio_verbs()
        unknown = sorted(n for n in named if n not in FORMAT_REGISTRY)
        assert not unknown, f"documented but not implemented: {unknown}"

    def test_every_audio_format_is_routed_to_the_audio_command(self):
        """A documented `inject audio <fmt>` must actually route there."""
        from pistudio.files.formats import FORMAT_REGISTRY

        doc = _doc("STUDIO.md")
        named = set(re.findall(_AUDIO_INVOCATION, doc)) - _audio_verbs()
        misrouted = sorted(n for n in named if n in FORMAT_REGISTRY and not FORMAT_REGISTRY[n].audio)
        assert not misrouted, f"documented under `inject audio` but routed to `inject file`: {misrouted}"

    def test_no_audio_format_is_documented_under_inject_file(self):
        from pistudio.files.formats import FORMAT_REGISTRY

        doc = _doc("STUDIO.md")
        named = set(re.findall(_FILE_INVOCATION, doc))
        wrong = sorted(n for n in named if n in FORMAT_REGISTRY and FORMAT_REGISTRY[n].audio)
        assert not wrong, f"audio formats documented under `inject file`: {wrong}"

    def test_documented_stdlib_formats_match_the_registry(self):
        """The list drifted to include wav, which is now an audio format."""
        from pistudio.files.formats import FORMAT_REGISTRY, file_format_names

        doc = _doc("STUDIO.md")
        match = re.search(r"\*\*Always available \(stdlib, \d+ formats\):\*\*(.+?)\n\n", doc, re.S)
        assert match, "the stdlib format list is missing from STUDIO.md"

        listed = {x.strip() for x in match.group(1).replace("\n", " ").split(",") if x.strip()}
        real = {n for n in file_format_names() if not FORMAT_REGISTRY[n].requires}
        assert listed == real, f"doc-only: {sorted(listed - real)}, missing: {sorted(real - listed)}"


class TestReferencedDocsExist:
    @pytest.mark.parametrize("source", ["hak5.md", "flipper.md"])
    def test_relative_doc_links_resolve(self, source):
        """Broken cross-references sent readers to files that never existed."""
        for target in re.findall(r"\]\((?!https?:)([\w./-]+\.md)\)", _doc(source)):
            resolved = (DOCS / target).resolve()
            assert resolved.is_file(), f"{source} links to missing {target}"

    def test_hw_usage_references_real_docs(self):
        from pistudio.commands.hw.command import HwCommand

        for target in re.findall(r"docs/([\w.-]+\.md)", HwCommand.usage):
            assert (DOCS / target).is_file(), f"hw usage references missing docs/{target}"


class TestStateIsolation:
    """The autouse _isolate_state fixture must actually isolate.

    The three registries resolved their global paths with expanduser("~") at
    import time, so PISTUDIO_HOME had no effect and every list_* call read the
    developer's real ~/.pistudio. CI passed only because CI has an empty home,
    which made results depend on the machine.
    """

    def test_registry_paths_follow_pistudio_home(self, tmp_path, monkeypatch):
        from pistudio.hardware.hak5.bunny_files import _global_files_file
        from pistudio.hardware.payloads import _global_payloads_file

        monkeypatch.setenv("PISTUDIO_HOME", str(tmp_path / "elsewhere"))
        for resolve in (_global_files_file, _global_payloads_file):
            assert str(tmp_path / "elsewhere") in resolve(), f"{resolve.__name__} ignores PISTUDIO_HOME"

    def test_no_registry_path_points_at_the_real_home(self):
        """Under the autouse fixture, nothing may resolve to the real home."""
        import os

        from pistudio.hardware.hak5.bunny_files import _global_files_file
        from pistudio.hardware.payloads import _global_payloads_file

        real_home = os.path.join(os.path.expanduser("~"), ".pistudio")
        for resolve in (_global_files_file, _global_payloads_file):
            assert not resolve().startswith(real_home), f"{resolve.__name__} reads the real home"

    def test_global_scope_writes_are_contained(self, tmp_path):
        """A --global write must land under the fixture's directory."""
        from pistudio.hardware.hak5.bunny_files import _global_files_file, add_file

        source = tmp_path / "doc.txt"
        source.write_text("x")
        add_file("contained", str(source), str(tmp_path / "session"), global_scope=True)

        written = pathlib.Path(_global_files_file())
        assert written.is_file()
        assert str(pathlib.Path.home() / ".pistudio") not in str(written)
