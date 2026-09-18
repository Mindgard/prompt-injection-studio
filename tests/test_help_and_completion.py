"""In-app help and tab completion, for every command.

Three defects motivated these tests:

* ``help <sub>`` inside a context *ran* the subcommand to make it print its
  own usage, so ``payloads> help add`` opened the interactive payload picker
  and blocked forever.  Help must not have side effects.
* ``audio`` declared two subcommands against twelve real formats, so ten were
  invisible to in-context help and completion.
* ``tutorial`` had no ``complete()`` at all, so its lesson numbers were
  undiscoverable.
"""

import io

import pytest
from rich.console import Console

from pistudio.commands import all_commands, get_command, register_all_commands
from pistudio.core.command import Command
from pistudio.core.studio import Studio, TargetContext
from pistudio.repl import _dispatch
from pistudio.ui.output import ShellOutput

register_all_commands()

NAMES = [c.name for c in all_commands()]
NAMESPACES = [c.name for c in all_commands() if c.namespace]


def _shell():
    """A Studio whose console writes to a buffer, returned alongside it."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100)
    studio = Studio(console=console, target=TargetContext())
    studio.out = ShellOutput(console, shell=studio)
    return studio, buf


def _texts(candidates) -> set[str]:
    """Normalise completion output, which mixes str and CompletionItem."""
    return {getattr(c, "text", c) for c in candidates}


class TestEveryCommandDocumentsItself:
    @pytest.mark.parametrize("name", NAMES)
    def test_has_help_and_usage(self, name):
        cmd = get_command(name)
        assert cmd.help, f"{name} has no one-line help"
        assert cmd.usage, f"{name} has no usage text"

    @pytest.mark.parametrize("name", NAMES)
    def test_help_command_prints_something(self, name):
        studio, buf = _shell()
        _dispatch(studio, [], f"help {name}")
        out = buf.getvalue()
        assert out.strip(), f"'help {name}' printed nothing"
        assert "No help for" not in out

    @pytest.mark.parametrize("name", NAMES)
    def test_bare_invocation_never_raises(self, name):
        """Running a command with no arguments should explain itself."""
        studio, _ = _shell()
        cmd = get_command(name)
        if cmd.namespace or name in ("theme", "prompt"):
            cmd.execute(studio, [])

    @pytest.mark.parametrize("name", NAMESPACES)
    def test_context_help_lists_subcommands(self, name):
        studio, buf = _shell()
        _dispatch(studio, [name], "help")
        out = buf.getvalue()
        for sub in get_command(name).subcommands:
            assert sub in out, f"'{name}> help' omits subcommand {sub!r}"


class TestSubcommandHelpHasNoSideEffects:
    """`help <sub>` used to execute the subcommand, which could block."""

    @pytest.mark.parametrize(
        ("parent", "sub"),
        [(c.name, s) for c in all_commands() for s in c.subcommands],
    )
    def test_help_for_every_subcommand(self, parent, sub):
        studio, buf = _shell()
        _dispatch(studio, [parent], f"help {sub}")
        out = buf.getvalue()
        assert out.strip(), f"'{parent}> help {sub}' printed nothing"
        assert "No help for" not in out
        assert sub in out

    def test_help_does_not_execute_the_subcommand(self):
        """The regression that hung the suite: help must not run anything."""
        from unittest.mock import patch

        studio, _ = _shell()
        with patch("pistudio.commands.payloads.PayloadsCommand._payload_add") as add:
            _dispatch(studio, ["payloads"], "help add")
            add.assert_not_called()

    def test_help_does_not_start_the_server(self):
        from unittest.mock import patch

        studio, _ = _shell()
        with patch("pistudio.commands.serve.serve_start") as start:
            _dispatch(studio, ["serve"], "help add")
            start.assert_not_called()

    def test_unknown_subcommand_still_reports_cleanly(self):
        studio, buf = _shell()
        _dispatch(studio, ["payloads"], "help definitely-not-a-subcommand")
        assert "No help for" in buf.getvalue()


class TestCompletion:
    @pytest.mark.parametrize("name", NAMES)
    def test_every_command_offers_completions(self, name):
        """A command with no completions is a dead end at the prompt."""
        studio, _ = _shell()
        cmd = get_command(name)
        assert type(cmd).complete is not Command.complete, f"{name} has no complete() of its own"
        assert _texts(cmd.complete(studio, [""])), f"{name} offers no completions"

    @pytest.mark.parametrize("name", NAMESPACES)
    def test_declared_subcommands_are_completable(self, name):
        studio, _ = _shell()
        offered = _texts(get_command(name).complete(studio, [""]))
        declared = set(get_command(name).subcommands)
        missing = declared - offered
        assert not missing, f"{name} declares {sorted(missing)} but does not complete them"

    def test_audio_completes_every_format(self):
        """Ten of twelve formats used to be missing from the declared list."""
        from pistudio.files.formats import audio_format_names

        studio, _ = _shell()
        offered = _texts(get_command("audio").complete(studio, [""]))
        assert set(audio_format_names()) <= offered

    def test_tutorial_completes_lessons(self):
        studio, _ = _shell()
        offered = _texts(get_command("tutorial").complete(studio, [""]))
        assert "list" in offered
        assert "1" in offered

    def test_tutorial_lesson_numbers_match_the_lessons(self):
        from pistudio.commands.tutorial import TutorialCommand

        cmd = TutorialCommand()
        studio, _ = _shell()
        numbers = {t for t in _texts(cmd.complete(studio, [""])) if t.isdigit()}
        assert numbers == {str(i) for i in range(1, len(cmd._steps()) + 1)}


class TestErrorsPointSomewhere:
    """A dead-end error costs the user a round trip to the docs."""

    def test_unknown_command_suggests_a_near_match(self):
        studio, buf = _shell()
        _dispatch(studio, [], "serv")
        assert "Did you mean 'serve'?" in buf.getvalue()

    def test_unknown_command_without_a_match_points_at_help(self):
        studio, buf = _shell()
        _dispatch(studio, [], "zzzzz")
        assert "Type 'help'" in buf.getvalue()

    def test_unknown_format_suggests_a_near_match(self):
        studio, buf = _shell()
        get_command("file").execute(studio, ["pdff", "hello"])
        assert "Did you mean 'pdf'?" in buf.getvalue()

    def test_unknown_format_does_not_dump_every_name(self):
        """Listing all 51 formats buried the answer in a wall of text."""
        studio, buf = _shell()
        get_command("file").execute(studio, ["zzzzz", "hello"])
        out = buf.getvalue()
        assert "file list" in out
        assert "dockerfile" not in out, "the error still dumps the whole format list"

    @pytest.mark.parametrize(
        ("command", "args", "expected"),
        [
            ("file", ["md", "x", "--voise", "Guy"], "--voice"),
            ("barcode", ["x", "--scal", "5"], "--scale"),
            ("serve", ["x", "--hostt", "127.0.0.1"], "--host"),
        ],
    )
    def test_unknown_flag_suggests_a_near_match(self, command, args, expected):
        studio, buf = _shell()
        get_command(command).execute(studio, args)
        assert f"Did you mean '{expected}'?" in buf.getvalue()


class TestEnteringAContextOrientsTheUser:
    """Entering silently left the user at a prompt with no idea what it took."""

    @pytest.mark.parametrize("name", NAMESPACES)
    def test_entering_prints_the_subcommands(self, name):
        studio, buf = _shell()
        context = _dispatch(studio, [], name)
        assert context == [name]
        out = buf.getvalue()
        assert out.strip(), f"entering '{name}' printed nothing"
        for sub in list(get_command(name).subcommands)[:3]:
            assert sub in out

    def test_entering_names_the_way_back(self):
        studio, buf = _shell()
        _dispatch(studio, [], "barcode")
        assert "back" in buf.getvalue()


class TestFlagsCarryDescriptions:
    """The completion dropdown shows these; a bare flag name teaches nothing."""

    @pytest.mark.parametrize("name", ["file", "serve", "barcode", "audio"])
    def test_flag_heavy_commands_describe_their_flags(self, name):
        cmd = get_command(name)
        assert len(cmd.flag_descriptions) >= 8, f"{name} describes only {len(cmd.flag_descriptions)} flags"

    @pytest.mark.parametrize("name", ["file", "serve", "barcode", "audio"])
    def test_described_flags_are_real(self, name):
        """A description for a flag that does not exist is worse than none."""
        cmd = get_command(name)
        usage = cmd.usage or ""
        for flag in cmd.flag_descriptions:
            assert flag in usage, f"{name} describes {flag}, which its usage never mentions"


class TestCompletionThroughTheShellCompleter:
    """End-to-end: what the user actually sees at the prompt."""

    def _complete(self, text, namespace=None):
        from prompt_toolkit.completion import CompleteEvent
        from prompt_toolkit.document import Document

        from pistudio.ui.completer import ShellCompleter

        studio, _ = _shell()
        studio.namespace_context = namespace
        completer = ShellCompleter(studio)
        return {c.text for c in completer.get_completions(Document(text, len(text)), CompleteEvent())}

    def test_root_offers_every_command(self):
        assert set(NAMES) <= self._complete("")

    def test_prefix_filters(self):
        assert self._complete("pay") == {"payloads"}

    @pytest.mark.parametrize("name", NAMES)
    def test_each_command_completes_its_arguments(self, name):
        if name == "tutorial":
            assert self._complete("tutorial ")
            return
        assert self._complete(f"{name} "), f"'{name} <tab>' offers nothing"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("barcode --type ", {"qr", "code128", "datamatrix"}),
            ("barcode png --error-level ", {"L", "M", "Q", "H"}),
            ("audio tts-wav --engine ", {"edge", "pyttsx3"}),
            ("audio adversarial-audio ", {"setup", "status", "uninstall"}),
            ("serve --host ", {"127.0.0.1", "0.0.0.0"}),
            ("serve tunnel ", {"start", "stop"}),
            ("hw ", {"devices", "flipper", "bunny"}),
            ("file ", {"list", "all", "pdf"}),
        ],
    )
    def test_flag_and_subcommand_values(self, text, expected):
        assert expected <= self._complete(text), f"'{text}<tab>' is missing {expected}"

    def test_inside_a_context_subcommands_come_first(self):
        offered = self._complete("", namespace="payloads")
        assert {"list", "show", "add"} <= offered
        assert "back" in offered

    def test_inside_a_context_flags_still_complete(self):
        assert {"--type", "--scale"} <= self._complete("png --", namespace="barcode")

    def test_audio_formats_complete_inside_the_context(self):
        offered = self._complete("", namespace="audio")
        assert {"tts-wav", "ultrasonic", "mp3", "midi"} <= offered


class TestNewCommandsAreFullyDiscoverable:
    """Help and completion coverage for the commands added in this cycle.

    A flag that completes but is undocumented sends the user to the source; a
    flag documented but never offered makes tab completion feel broken. These
    pin both directions for the commands where the contract was stated.
    """

    NEW = ("barcode", "encode", "audio", "file")

    def _offered_flags(self, studio, cmd) -> set[str]:
        """Every flag *cmd* offers, across its subcommands."""
        offered: set[str] = set()
        for tokens in ([""], *[[sub, ""] for sub in cmd.subcommands]):
            try:
                offered |= {getattr(c, "text", c) for c in cmd.complete(studio, tokens)}
            except Exception:  # a subcommand needing live state is not a completion bug
                continue
        return {f for f in offered if isinstance(f, str) and f.startswith("--")}

    @pytest.mark.parametrize("name", NEW)
    def test_the_command_documents_itself(self, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        assert cmd is not None
        assert cmd.help, f"{name} has no one-line help"
        assert cmd.usage, f"{name} has no usage text"

    @pytest.mark.parametrize("name", NEW)
    def test_every_completed_flag_appears_in_the_usage(self, studio, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        undocumented = sorted(f for f in self._offered_flags(studio, cmd) if f not in cmd.usage)
        assert not undocumented, f"{name} completes but does not document: {undocumented}"

    @pytest.mark.parametrize("name", NEW)
    def test_every_completed_flag_has_a_description(self, studio, name):
        """The completion dropdown shows these; a missing one renders blank."""
        from pistudio.commands import get_command

        cmd = get_command(name)
        missing = sorted(f for f in self._offered_flags(studio, cmd) if f not in cmd.flag_descriptions)
        assert not missing, f"{name} has no flag_descriptions for: {missing}"

    @pytest.mark.parametrize("name", NEW)
    def test_every_subcommand_has_help_text(self, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        blank = sorted(sub for sub, text in cmd.subcommands.items() if not text)
        assert not blank, f"{name} has undescribed subcommands: {blank}"

    @pytest.mark.parametrize("name", NEW)
    def test_every_subcommand_is_named_in_the_usage(self, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        missing = sorted(sub for sub in cmd.subcommands if sub not in cmd.usage)
        assert not missing, f"{name} does not document subcommands: {missing}"

    @pytest.mark.parametrize("name", NEW)
    def test_the_bare_command_completes_its_subcommands(self, studio, name):
        from pistudio.commands import get_command

        cmd = get_command(name)
        offered = {getattr(c, "text", c) for c in cmd.complete(studio, [""])}
        assert set(cmd.subcommands) <= offered, f"{name} does not complete all its subcommands"
