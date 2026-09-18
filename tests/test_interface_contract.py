"""Invariants the CLI, REPL and MCP surfaces all depend on.

The existing guardrails in ``test_help_and_completion.py`` check coherence in
one direction: every flag a command *completes* must be documented.  Nothing
checked the reverse, so a flag could be parsed while appearing in no usage
text, no completion and no help.  Nine of ``file``'s flags were in that state,
including a working ``--encode`` discoverable only by reading the source.

The gaps that produced these tests, all reproduced against the real binary:

- ``--json`` emitted output Rich had hard-wrapped at the console width, so a
  long payload came back as unparseable JSON.  The MCP server parses exactly
  this stdout.
- ``--help`` failed on all seven top-level commands, each with a different
  wrong error.
- Ten destructive hardware paths called ``shell.session.prompt`` directly.
  ``session`` is set only by the REPL, so on the command line they raised
  ``AttributeError`` -- which ``cli.py`` does not catch -- on BLE transmit
  and BadUSB deploy.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "pistudio"


@pytest.fixture(autouse=True)
def _registered():
    from pistudio.commands import register_all_commands

    register_all_commands()


def _commands():
    from pistudio.commands import all_commands

    return all_commands()


def _names():
    return sorted(c.name for c in _commands())


class TestHelpIsUniversal:
    """`--help` is answered by the dispatcher, so no command can forget it."""

    @pytest.mark.parametrize("name", _names())
    def test_help_flag_prints_usage_and_exits_zero(self, name, capsys):
        from pistudio.cli import main

        code = main([name, "--help"])
        out = _ANSI.sub("", capsys.readouterr().out)

        assert code == 0, f"{name} --help exited {code}"
        assert "Usage" in out, f"{name} --help printed no usage: {out[:200]!r}"

    @pytest.mark.parametrize("name", _names())
    def test_short_help_matches_long_help(self, name, capsys):
        from pistudio.cli import main

        main([name, "--help"])
        long_form = capsys.readouterr().out
        main([name, "-h"])
        assert capsys.readouterr().out == long_form

    @pytest.mark.parametrize("name", _names())
    def test_help_never_reports_an_error(self, name, capsys):
        """Every command used to fail differently: "Unknown format: '--help'"."""
        from pistudio.cli import main

        main([name, "--help"])
        captured = capsys.readouterr()
        combined = _ANSI.sub("", captured.out + captured.err).lower()
        for marker in ("unknown format", "unknown subcommand", "unknown flag", "unknown theme", "no text given"):
            assert marker not in combined, f"{name} --help reported: {marker}"

    def test_help_does_not_shadow_a_subcommands_own_help(self, capsys):
        """`hw flipper --help` must reach flipper, not print the hw page."""
        from pistudio.cli import main

        main(["hw", "flipper", "--help"])
        assert "hw flipper" in _ANSI.sub("", capsys.readouterr().out)

    def test_a_payload_may_contain_the_help_flag(self, studio, tmp_path, monkeypatch):
        """Payload text is arbitrary; only a *leading* --help asks for usage."""
        from pistudio.commands import get_command

        monkeypatch.chdir(tmp_path)
        out = tmp_path / "p.md"
        get_command("file").execute(studio, ["md", "ignore --help please", "--output", str(out)])
        assert out.is_file(), "a payload containing --help was swallowed as a help request"
        assert "--help" in out.read_text()


class TestRootNavigation:
    """The REPL borrows shell navigation, so `ls` should mean what it does there."""

    @pytest.mark.parametrize("word", ["ls", "dir"])
    def test_it_lists_the_commands_at_the_root(self, studio, word):
        from pistudio.repl import _dispatch

        _dispatch(studio, [], word)
        out = _ANSI.sub("", studio.buf.getvalue())
        assert "Commands" in out
        assert "payloads" in out

    def test_it_does_not_shadow_a_context_alias(self, studio):
        """Inside `payloads>`, `ls` is that command's own `list` alias."""
        from pistudio.repl import _dispatch

        _dispatch(studio, ["payloads"], "ls")
        out = _ANSI.sub("", studio.buf.getvalue())
        assert "ignore-instructions" in out, "payloads> ls stopped listing payloads"


class TestBarcodeListingIsComplete:
    def test_gs1_appears(self, studio):
        """GS1 is reached by a subcommand, so a --type-keyed listing omitted it."""
        from pistudio.commands import get_command

        get_command("barcode").execute(studio, ["list"])
        out = _ANSI.sub("", studio.buf.getvalue())
        assert "gs1" in out, "barcode list omits the GS1 mode"

    def test_every_listed_type_says_how_to_select_it(self, studio):
        from pistudio.commands import get_command

        studio.json_mode = True
        get_command("barcode").execute(studio, ["list"])
        rows = json.loads(_ANSI.sub("", studio.buf.getvalue()))
        assert {r["type"] for r in rows} >= {"qr", "code128", "gs1"}
        for row in rows:
            assert row["selector"] in ("--type", "subcommand"), row


class TestPrintingHasStoredDefaults:
    """A default printer supplies the target; it must not start printing."""

    @staticmethod
    def _with(tmp_path, **values):
        from pistudio.core.settings import Settings
        from pistudio.core.studio import Studio

        studio = Studio(session_dir=str(tmp_path))
        settings = Settings(studio.session_dir)
        for key, value in values.items():
            settings.set(key, value)
        studio.settings = settings
        return studio

    def test_a_stored_printer_does_not_enable_printing(self, tmp_path):
        from pistudio.commands.printing_flags import extract_print_flags

        studio = self._with(tmp_path, **{"print.printer": "Brother"})
        _, opts = extract_print_flags([], studio)
        assert opts.enabled is False, "a stored printer sent a file to paper unasked"
        assert opts.printer == "Brother"

    def test_the_stored_printer_is_used_when_printing(self, tmp_path):
        from pistudio.commands.printing_flags import extract_print_flags

        studio = self._with(tmp_path, **{"print.printer": "Brother", "print.media": "A4"})
        _, opts = extract_print_flags(["--print"], studio)
        assert (opts.enabled, opts.printer, opts.media) == (True, "Brother", "A4")

    def test_an_explicit_flag_beats_the_setting(self, tmp_path):
        from pistudio.commands.printing_flags import extract_print_flags

        studio = self._with(tmp_path, **{"print.printer": "Brother"})
        _, opts = extract_print_flags(["--printer", "Other"], studio)
        assert opts.printer == "Other"

    def test_a_bad_copies_value_is_reported(self, tmp_path):
        """This was a bare int(), so `--copies abc` escaped as a ValueError."""
        from pistudio.commands.printing_flags import extract_print_flags
        from pistudio.core.flags import FlagError

        with pytest.raises(FlagError, match="whole number"):
            extract_print_flags(["--copies", "abc"], self._with(tmp_path))


class TestTheBannerIsProductNeutral:
    def test_no_theme_logo_spells_the_vendor_name(self):
        """The art is shared, so this checks the one place it is defined."""
        from pistudio.ui.theme import all_themes, get_theme, load_builtin_themes

        load_builtin_themes()
        for name in all_themes():
            logo = get_theme(name).logo
            assert logo, f"{name} has no logo"
            # The art is block characters; the check is that the *source* rows
            # are the shared ones rather than a pasted vendor wordmark.
            assert "MINDGARD" not in logo.upper()

    def test_every_theme_uses_the_shared_art(self):
        import re

        from pistudio.ui.theme import all_themes, build_logo, get_theme, load_builtin_themes

        load_builtin_themes()
        shape = re.sub(r"\[[^\]]*\]", "", build_logo(("x",)))
        for name in all_themes():
            rendered = re.sub(r"\[[^\]]*\]", "", get_theme(name).logo)
            assert rendered == shape, f"{name} has diverged from the shared logo"


class TestHelpDoesNotAdvertiseRemovedFeatures:
    """Help that names a deleted feature is worse than no help.

    Conversations were removed in 3b2c15d, but ``hw flipper``'s help went on
    offering ``--convo``, ``sync --convos-only`` and ``sync --payloads-only``
    for every release after: three flags no code parsed, in the one place a
    user looks to find out what a command accepts.
    """

    #: Names of features removed from the studio.  A hit in help text means
    #: the removal missed a page.
    GONE = ("convo", "conversation", "--payloads-only", "--convos-only")

    @pytest.mark.parametrize("term", GONE)
    def test_no_help_text_mentions_it(self, term):
        offenders = []
        for path in sorted((_PACKAGE / "commands").rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                # Only help/usage strings, which is where a user would read it.
                if term in line.lower() and '"' in line:
                    offenders.append(f"{path.name}:{number}")
        assert not offenders, f"help still mentions the removed {term!r}: {offenders}"

    def test_every_flag_in_a_help_string_is_parsed_somewhere(self):
        """A flag in help that no code reads is a promise the tool cannot keep.

        Parse sites are found structurally rather than by counting quoted
        occurrences: a help line spells the flag inside prose
        (``"  --style <numbered|...>  Flood style"``) while the parse call
        spells it as a bare literal, so the two never look alike.
        """
        flag = re.compile(r"--[a-z][a-z0-9-]{2,}")
        sources = {p: p.read_text(encoding="utf-8") for p in (_PACKAGE).rglob("*.py")}
        blob = "\n".join(sources.values())

        # A flag is parsed when it appears as a standalone string literal --
        # extract_flag(args, "--x"), "--x" in args, Flag("--x", ...) all match.
        parsed = set(re.findall(r"""["'](--[a-z][a-z0-9-]{2,})["']""", blob))

        documented: set[str] = set()
        for text in sources.values():
            for line in text.splitlines():
                stripped = line.strip()
                # A usage line: a quoted string opening with two spaces then a
                # flag, which is how every Options: block is written.
                if stripped.startswith(('"  --', "'  --")):
                    documented.update(flag.findall(stripped))

        unparsed = sorted(documented - parsed)
        assert not unparsed, f"help documents flags nothing parses: {unparsed}"


class TestDeviceEmojiAreConsistent:
    """Each animal shows its emoji wherever the device is named."""

    def test_every_device_declares_an_emoji(self):
        from pistudio.hardware.devices import DEVICES

        assert DEVICES
        blank = [d.name for d in DEVICES if not d.emoji]
        assert not blank, f"devices without an emoji: {blank}"

    def test_emoji_render_in_colour(self):
        """A codepoint with a text-presentation default needs U+FE0F.

        One device's emoji was written as a bare codepoint, which many
        terminals render as a monochrome glyph rather than the emoji. This
        guards every device added since.
        """
        import unicodedata

        from pistudio.hardware.devices import DEVICES

        for device in DEVICES:
            if unicodedata.east_asian_width(device.emoji[0]) not in ("W", "F"):
                assert "️" in device.emoji, f"{device.name}: {device.emoji!r} needs a variation selector"

    def test_the_hw_listing_shows_every_emoji(self):
        from pistudio.commands import get_command
        from pistudio.hardware.devices import DEVICES

        subs = get_command("hw").subcommands
        for device in DEVICES:
            assert device.emoji in subs.get(device.name, ""), f"hw help omits {device.name}'s emoji"

    def test_each_device_help_names_itself_with_its_emoji(self, studio):
        from pistudio.commands import get_command
        from pistudio.hardware.devices import DEVICES

        for device in DEVICES:
            studio.buf.truncate(0)
            studio.buf.seek(0)
            get_command("hw").execute(studio, [device.name, "--help"])
            out = _ANSI.sub("", studio.buf.getvalue())
            assert device.emoji in out, f"hw {device.name} --help omits its emoji"

    def test_an_emoji_reaches_the_same_handler_as_the_name(self):
        from pistudio.hardware.devices import DEVICES, device_by_name

        for device in DEVICES:
            assert device_by_name(device.emoji) is device, f"{device.emoji} does not resolve to {device.name}"


class TestHelpShowsRunnableExamples:
    """Help that shows a command you cannot paste is half an answer."""

    @pytest.mark.parametrize("name", _names())
    def test_every_command_documents_examples(self, name):
        from pistudio.commands import get_command
        from pistudio.repl import examples_from

        cmd = get_command(name)
        assert examples_from(cmd.usage or ""), f"{name} has no Examples: block"

    @pytest.mark.parametrize("name", _names())
    def test_examples_start_with_the_command(self, name):
        """An example that names a different command belongs in that one."""
        from pistudio.commands import get_command
        from pistudio.repl import examples_from

        cmd = get_command(name)
        known = {c.name for c in _commands()} | {a for c in _commands() for a in c.aliases}
        for example in examples_from(cmd.usage or "", limit=50):
            first = example.split()[0]
            assert first in known, f"{name} example does not start with a command: {example!r}"

    @pytest.mark.parametrize("name", sorted(c.name for c in _commands() if c.namespace))
    def test_context_help_offers_pasteable_examples(self, name, studio):
        """Inside `hw>`, an example must read `flipper ...`, not `hw flipper ...`.

        Typing the un-stripped form at that prompt resolves to `hw hw flipper`,
        so a help screen showing it is showing something that will not run.
        """
        from pistudio.repl import _print_context_help

        _print_context_help(studio, [name])
        out = _ANSI.sub("", studio.buf.getvalue())
        assert "Try" in out, f"{name} context help shows no examples"

        body = out.split("Try", 1)[1]
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        offered = [line for line in lines if not line.startswith("'")]
        assert offered, f"{name} context help lists no example lines"
        for line in offered:
            assert not line.startswith(f"{name} "), f"{name} example still carries its own prefix: {line!r}"

    def test_the_root_listing_offers_examples(self, studio):
        from pistudio.repl import _print_root_help

        _print_root_help(studio)
        assert "Try" in _ANSI.sub("", studio.buf.getvalue())


class TestJsonIsMachineReadable:
    """The MCP server parses this stdout, so it must be JSON and only JSON."""

    def test_a_long_message_is_not_reflowed(self, capsys):
        """Rich wrapped at the console width, inserting newlines mid-string."""
        from pistudio.cli import main

        main(["--json", "theme", "X" * 400])
        err = capsys.readouterr().err
        parsed = json.loads(err)
        assert parsed["status"] == "error"
        assert len(parsed["message"]) > 200

    def test_data_goes_to_stdout(self, capsys):
        from pistudio.cli import main

        main(["--json", "payloads", "list"])
        captured = capsys.readouterr()
        assert isinstance(json.loads(captured.out), list)

    def test_a_global_flag_works_after_the_subcommand(self, capsys):
        """argparse only saw these before the subcommand; REMAINDER ate the rest.

        So `payloads list --json` was accepted and silently ignored, printing a
        Rich table -- the worst outcome for a scripting interface.
        """
        from pistudio.cli import main

        main(["payloads", "list", "--json"])
        assert isinstance(json.loads(capsys.readouterr().out), list)

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["payloads", "list", "--json"], ["--json", "payloads", "list"]),
            (["--json", "payloads", "list"], ["--json", "payloads", "list"]),
            (["payloads", "add", "x", "--", "--json"], ["payloads", "add", "x", "--", "--json"]),
        ],
    )
    def test_hoisting_leaves_payload_text_alone(self, argv, expected):
        from pistudio.cli import _hoist_global_flags

        assert _hoist_global_flags(argv) == expected

    # Commands whose primary output is a table, in every mode.
    LISTINGS = [
        ["payloads", "list"],
        ["encode", "list"],
        ["encode", "carriers"],
        ["barcode", "list"],
        ["file", "list"],
    ]

    @pytest.mark.parametrize("argv", LISTINGS, ids=lambda a: " ".join(a))
    def test_a_listing_is_parseable_json(self, argv, capsys):
        from pistudio.cli import main

        main(["--json", *argv])
        assert isinstance(json.loads(capsys.readouterr().out), list)

    @pytest.mark.parametrize("argv", LISTINGS, ids=lambda a: " ".join(a))
    def test_a_listing_is_grep_friendly_in_plain_mode(self, argv, capsys):
        """`--plain` promised no box drawing and delivered a Rich table.

        Commands built ``rich.table.Table`` directly after a hand-written JSON
        branch, so the plain branch never existed at those sites.
        """
        from pistudio.cli import main

        main(["--plain", *argv])
        out = capsys.readouterr().out
        boxes = {c for c in "│┃╭━┏┡┩└┘├┤┬┴┼─" if c in out}
        assert not boxes, f"{' '.join(argv)} --plain drew a table with {sorted(boxes)}"
        # Rich renders the tab separators as runs of spaces when the stream is
        # not a terminal, so assert on the shape -- a header row followed by
        # data rows, each a single line -- rather than on the tab byte.
        lines = [line for line in out.splitlines() if line.strip()]
        assert len(lines) > 1, f"{' '.join(argv)} --plain produced no rows"
        assert all("  " in line or len(line.split()) == 1 for line in lines[:3])

    def test_errors_do_not_pollute_stdout(self, capsys):
        """`cmd --json > out.json` must not mix diagnostics into the data."""
        from pistudio.cli import main

        main(["--json", "theme", "no-such-theme"])
        captured = capsys.readouterr()
        assert captured.out.strip() == "", f"error reached stdout: {captured.out[:200]!r}"
        assert json.loads(captured.err)["status"] == "error"


class TestConfirmationsSurviveNoTerminal:
    """A confirmation must decline, not crash, when there is nobody to ask."""

    def test_no_command_calls_session_prompt_directly(self):
        """``session`` is None outside the REPL, so a direct call crashes.

        An AST check rather than a grep: this is the invariant that kept
        ``hw ubertooth ble-adv`` from raising an unhandled ``AttributeError``
        on the command line.
        """
        # studio.py *implements* confirm/ask, and repl.py owns the
        # PromptSession it builds; everywhere else must go through them.
        allowed = {_PACKAGE / "core" / "studio.py", _PACKAGE / "repl.py"}
        offenders: list[str] = []
        for path in sorted(_PACKAGE.rglob("*.py")):
            if path in allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute) or node.attr != "prompt":
                    continue
                inner = node.value
                if isinstance(inner, ast.Attribute) and inner.attr == "session":
                    offenders.append(f"{path.relative_to(_PACKAGE.parent)}:{node.lineno}")
        assert not offenders, "use shell.confirm()/shell.ask() instead of session.prompt at: " + ", ".join(offenders)

    def test_confirm_declines_without_a_terminal(self, studio, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        assert studio.confirm("Transmit?") is False

    def test_confirm_explains_how_to_proceed(self, studio, monkeypatch):
        """A bare "no" is a dead end; naming --yes makes it a one-flag fix."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        studio.confirm("Transmit?")
        assert "--yes" in _ANSI.sub("", studio.buf.getvalue())

    def test_yes_flag_confirms_without_asking(self, tmp_path):
        from pistudio.core.studio import Studio

        assert Studio(session_dir=str(tmp_path), assume_yes=True).confirm("Transmit?") is True

    def test_yes_flag_satisfies_a_typed_phrase(self, tmp_path):
        from pistudio.core.studio import Studio

        studio = Studio(session_dir=str(tmp_path), assume_yes=True)
        assert studio.confirm_phrase("Wipe everything?", "CONFIRM") is True

    def test_ask_returns_none_without_a_terminal(self, studio, monkeypatch):
        """Free-text input has no safe default, so --yes must not invent one."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        studio.assume_yes = True
        assert studio.ask("Select port (1):") is None


class TestThePromptSessionIsUsedWhenThereIsOne:
    """A ``PromptSession`` owns its own terminal, so ``isatty`` must not gate it.

    Guarding on ``sys.stdin.isatty()`` *before* checking for a session threw
    away a live input channel.  Inside the interactive session
    ``hw flipper remote`` connected to the device, printed its banner, then
    read ``None`` on the first line and disconnected immediately.
    """

    @staticmethod
    def _repl_studio(tmp_path, answer: str):
        from unittest.mock import MagicMock

        from pistudio.core.studio import Studio

        studio = Studio(session_dir=str(tmp_path))
        studio.session = MagicMock()
        studio.session.prompt.return_value = answer
        return studio

    def test_ask_reads_through_the_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        assert self._repl_studio(tmp_path, "status").ask("flipper>") == "status"

    def test_confirm_reads_through_the_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        assert self._repl_studio(tmp_path, "y").confirm("Deploy?") is True

    def test_confirm_phrase_reads_through_the_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        assert self._repl_studio(tmp_path, "CONFIRM").confirm_phrase("Wipe?", "CONFIRM") is True

    def test_pause_reads_through_the_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        assert self._repl_studio(tmp_path, "").pause() is True

    def test_json_mode_still_refuses_even_with_a_session(self, tmp_path, monkeypatch):
        """A prompt written into a JSON stream corrupts it, session or not."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        studio = self._repl_studio(tmp_path, "y")
        studio.json_mode = True
        assert studio.ask("x") is None
        assert studio.confirm("x") is False

    def test_a_nested_console_loop_keeps_reading(self, tmp_path, monkeypatch):
        """The flipper console reads until the user exits, not until the first line."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        studio = self._repl_studio(tmp_path, "")
        studio.session.prompt.side_effect = ["status", "ping", "exit"]

        seen = []
        while (line := studio.ask("flipper>")) is not None:
            if line.strip() == "exit":
                break
            seen.append(line.strip())
        assert seen == ["status", "ping"]


class TestFlagSpecIsTheSourceOfTruth:
    """Where a command declares ``flags``, everything else derives from it."""

    @staticmethod
    def _spec_commands():
        return [c for c in _commands() if getattr(c, "flags", ())]

    def test_at_least_one_command_uses_the_spec(self):
        assert self._spec_commands(), "no command declares a flag spec"

    @pytest.mark.parametrize("name", sorted(c.name for c in _commands() if getattr(c, "flags", ())))
    def test_every_declared_flag_is_documented(self, name):
        """The reverse of the existing guardrail: parsed implies documented."""
        from pistudio.commands import get_command

        cmd = get_command(name)
        missing = sorted(f.name for f in cmd.flags if f.name not in (cmd.usage or ""))
        assert not missing, f"{name} parses but does not document: {missing}"

    @pytest.mark.parametrize("name", sorted(c.name for c in _commands() if getattr(c, "flags", ())))
    def test_every_declared_flag_has_help(self, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        blank = sorted(f.name for f in cmd.flags if not f.help)
        assert not blank, f"{name} has undescribed flags: {blank}"

    @pytest.mark.parametrize("name", sorted(c.name for c in _commands() if getattr(c, "flags", ())))
    def test_descriptions_derive_from_the_spec(self, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        for flag in cmd.flags:
            assert cmd.flag_descriptions.get(flag.name) == flag.help

    @pytest.mark.parametrize("name", sorted(c.name for c in _commands() if getattr(c, "flags", ())))
    def test_no_duplicate_spellings(self, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        spellings = [s for f in cmd.flags for s in f.spellings]
        assert len(spellings) == len(set(spellings)), f"{name} declares a flag twice"


class TestFlagParsing:
    """The shared parser, exercised directly."""

    @staticmethod
    def _spec():
        from pistudio.core.flags import Flag

        return (
            Flag("--output", short="-o", value="path", help="Where to write"),
            Flag("--count", value="n", help="How many"),
            Flag("--loud", help="Be noisy"),
            Flag("--level", value="L|M", choices=("L", "M"), help="Pick one"),
            Flag("--only-here", value="x", help="Scoped", scope=("png",), scope_label="png"),
        )

    def test_long_and_short_agree(self):
        from pistudio.core.flags import parse_flags

        assert parse_flags(self._spec(), ["-o", "a"]).text("--output") == "a"
        assert parse_flags(self._spec(), ["--output", "a"]).text("--output") == "a"

    def test_inline_equals_form(self):
        from pistudio.core.flags import parse_flags

        assert parse_flags(self._spec(), ["--output=a b"]).text("--output") == "a b"

    def test_double_dash_ends_options(self):
        """So a payload may begin with a dash."""
        from pistudio.core.flags import parse_flags

        parsed = parse_flags(self._spec(), ["--loud", "--", "--not-a-flag"])
        assert parsed.positional == ["--not-a-flag"]
        assert parsed.flag("--loud") is True

    def test_given_distinguishes_default_from_explicit(self):
        from pistudio.core.flags import parse_flags

        assert "--count" not in parse_flags(self._spec(), []).given
        assert "--count" in parse_flags(self._spec(), ["--count", "1"]).given

    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            (["--nope"], "Unknown flag: --nope"),
            (["--outpt", "x"], "Did you mean '--output'"),
            (["--output"], "--output needs a value"),
            (["--level", "Z"], "must be one of L, M"),
            (["--loud=1"], "takes no value"),
        ],
    )
    def test_errors_name_the_problem(self, args, expected):
        from pistudio.core.flags import FlagError, parse_flags

        with pytest.raises(FlagError) as exc:
            parse_flags(self._spec(), args)
        assert expected in str(exc.value)

    def test_scope_rejects_a_flag_that_does_not_apply(self):
        from pistudio.core.flags import FlagError, parse_flags

        parse_flags(self._spec(), ["--only-here", "x"], mode="png")  # fine
        with pytest.raises(FlagError, match="does not apply"):
            parse_flags(self._spec(), ["--only-here", "x"], mode="svg")

    def test_numeric_accessors_report_bad_values(self):
        from pistudio.core.flags import FlagError, parse_flags

        parsed = parse_flags(self._spec(), ["--count", "abc"])
        with pytest.raises(FlagError, match="whole number"):
            parsed.integer("--count", 0)


class TestSubcommandAliasesAreDeclared:
    """An alias nobody can discover may as well not exist."""

    # Aliases accepted only by handlers below the top level (the gs1 mode),
    # which have their own *_HELP text rather than a Command object to
    # declare against.
    # `uninstall`/`remove`/`delete` are management verbs on a nested mode
    # (`file anamorph`, `audio adversarial-audio`), not top-level subcommands.
    NESTED_ONLY = {"ais", "delete", "payload", "payloads", "uninstall", "remove"}

    def test_every_inline_alias_is_declared(self):
        """An alias nobody can complete or `help` may as well not exist."""
        pattern = re.compile(r"sub in \(([^)]*)\)")
        found: set[str] = set()
        for path in sorted((_PACKAGE / "commands").rglob("*.py")):
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                for raw in match.group(1).split(","):
                    token = raw.strip().strip("\"'")
                    if token and not token.startswith("-"):
                        found.add(token)

        declared = {sub for cmd in _commands() for sub in (cmd.subcommands or {})}
        declared |= {a for cmd in _commands() for a in (getattr(cmd, "subcommand_aliases", None) or {})}
        undeclared = found - declared - self.NESTED_ONLY - {"help"}
        assert not undeclared, f"undeclared subcommand aliases (declare them or drop them): {sorted(undeclared)}"

    @pytest.mark.parametrize("name", _names())
    def test_declared_aliases_point_at_real_subcommands(self, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        subs = cmd.subcommands or {}
        broken = {a: t for a, t in (getattr(cmd, "subcommand_aliases", None) or {}).items() if t not in subs}
        assert not broken, f"{name} aliases point at nothing: {broken}"

    @pytest.mark.parametrize("name", _names())
    def test_an_alias_never_shadows_a_subcommand(self, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        clash = set(getattr(cmd, "subcommand_aliases", None) or {}) & set(cmd.subcommands or {})
        assert not clash, f"{name} declares {clash} as both a subcommand and an alias"
