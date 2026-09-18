"""The guided walkthrough.

The tutorial runs real commands rather than printing transcripts, so the
thing most worth testing is that every lesson's command still exists and
still works — a tutorial that drifts from the code is worse than none.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from conftest import _strip_ansi

from pistudio.commands import get_command, register_all_commands
from pistudio.commands.tutorial import TutorialCommand

register_all_commands()


@pytest.fixture(autouse=True)
def _never_block(monkeypatch, request):
    """Advance through every lesson without waiting on input.

    TestPauseHelper opts out — it is testing pause itself.
    """
    if request.cls is not None and request.cls.__name__ == "TestPauseHelper":
        return
    monkeypatch.setattr("pistudio.core.studio.Studio.pause", lambda self, message=None: True)


class TestRegistration:
    def test_registered_under_its_name_and_aliases(self):
        for name in ("tutorial", "tour", "guide"):
            cmd = get_command(name)
            assert cmd is not None, f"'{name}' is not registered"
            assert cmd.name == "tutorial"

    def test_visible_to_a_first_time_user(self):
        """A walkthrough nobody can find is useless."""
        from pistudio.commands import visible_command_names

        assert "tutorial" in visible_command_names()

    def test_reachable_from_the_command_line(self):
        from pistudio.cli import _command_names

        assert "tutorial" in _command_names()


def _looks_like_a_subcommand(token: str) -> bool:
    """Return True when *token* could name a subcommand rather than a payload."""
    return token.islower() and " " not in token and not token.startswith("-")


class TestLessonsStayValid:
    """Guards against the tutorial teaching commands that no longer work."""

    def test_every_lesson_has_a_title_and_body(self):
        for step in TutorialCommand()._steps():
            assert step.title.strip()
            assert step.body.strip()

    def test_every_named_command_exists(self):
        """A lesson claiming to run `inject payloads list` must be able to."""
        import shlex

        from pistudio.commands import get_nested_command

        # `help` is implemented by the REPL loop rather than the registry.
        repl_builtins = {"help"}
        for step in TutorialCommand()._steps():
            if not step.command:
                continue
            tokens = shlex.split(step.command)
            head = tokens[0]
            if head in repl_builtins:
                continue

            cmd = get_command(head) or get_nested_command([head])
            assert cmd is not None, f"lesson {step.title!r} runs unknown command {head!r}"

            # Validate the second word too — a typo past the first word is
            # exactly the drift this test exists to catch.  Some commands take
            # a payload there instead of a subcommand (barcode "<text>"), so a
            # word is only checked when it looks like one: lowercase, no spaces.
            subs = getattr(cmd, "subcommands", None) or {}
            if len(tokens) > 1 and subs and _looks_like_a_subcommand(tokens[1]):
                assert tokens[1] in subs, (
                    f"lesson {step.title!r} runs '{head} {tokens[1]}', which is not a subcommand of {head!r}"
                )

    def test_lessons_do_not_reference_a_numbered_lesson(self):
        """Hardcoded cross-references rot as soon as lessons are reordered."""
        import re

        for step in TutorialCommand()._steps():
            text = f"{step.body} {step.note}"
            assert not re.search(r"lesson \d", text, re.I), f"{step.title!r} hardcodes a lesson number"

    def test_covers_the_requested_commands(self):
        steps = TutorialCommand()._steps()
        blob = " ".join(f"{s.title} {s.body} {s.command} {s.note}" for s in steps)
        for topic in ("inject", "help", "theme"):
            assert topic in blob, f"the walkthrough never mentions {topic!r}"

    def test_does_not_teach_prompt_yet(self):
        """`prompt` is deliberately out of scope for now."""
        steps = TutorialCommand()._steps()
        for step in steps:
            assert "prompt list" not in step.command
            assert not step.command.startswith("prompt ")


class TestRunning:
    def test_full_run_reaches_the_end(self, studio):
        get_command("tutorial").execute(studio, [])
        assert "That's the tour" in _strip_ansi(studio.buf.getvalue())

    def test_full_run_executes_real_commands(self, studio):
        """Output should contain real payload names, not a canned transcript."""
        get_command("tutorial").execute(studio, [])
        out = _strip_ansi(studio.buf.getvalue())
        assert "ignore-instructions" in out, "the payload lesson did not really run"

    def test_list_shows_every_lesson(self, studio):
        get_command("tutorial").execute(studio, ["list"])
        out = _strip_ansi(studio.buf.getvalue())
        for i in range(1, len(TutorialCommand()._steps()) + 1):
            assert f"{i}." in out

    def test_single_lesson_runs_alone(self, studio):
        get_command("tutorial").execute(studio, ["3"])
        out = _strip_ansi(studio.buf.getvalue())
        assert "3/7" in out
        assert "1/7" not in out

    def test_quitting_says_how_to_resume(self, studio, monkeypatch):
        monkeypatch.setattr("pistudio.core.studio.Studio.pause", lambda self, message=None: False)
        get_command("tutorial").execute(studio, [])
        assert "tutorial 2" in _strip_ansi(studio.buf.getvalue())

    def test_a_failing_lesson_does_not_abort_the_tour(self, studio):
        """One broken command should not strand the user mid-walkthrough."""
        with patch.object(TutorialCommand, "_run", side_effect=RuntimeError("boom")):
            get_command("tutorial").execute(studio, [])
        out = _strip_ansi(studio.buf.getvalue())
        assert "could not run" in out
        assert "That's the tour" in out


class TestArgumentHandling:
    def test_out_of_range_lesson_is_reported(self, studio):
        get_command("tutorial").execute(studio, ["99"])
        assert "7 lessons" in _strip_ansi(studio.buf.getvalue())

    def test_non_numeric_argument_shows_usage(self, studio):
        get_command("tutorial").execute(studio, ["banana"])
        assert "Usage" in _strip_ansi(studio.buf.getvalue())

    def test_lesson_zero_is_rejected(self, studio):
        get_command("tutorial").execute(studio, ["0"])
        assert "7 lessons" in _strip_ansi(studio.buf.getvalue())


class TestPauseHelper:
    def test_returns_true_without_a_terminal(self, studio):
        """In a pipe or in CI it must not block on input that never comes."""
        assert studio.pause() is True

    def test_quit_words_stop_the_flow(self, studio, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        for word in ("q", "quit", "exit", "n"):
            monkeypatch.setattr("builtins.input", lambda _prompt, w=word: w)
            assert studio.pause() is False, f"{word!r} should stop the walkthrough"

    def test_enter_continues(self, studio, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "")
        assert studio.pause() is True

    def test_ctrl_c_stops_rather_than_raising(self, studio, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        def _interrupt(_prompt):
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", _interrupt)
        assert studio.pause() is False
