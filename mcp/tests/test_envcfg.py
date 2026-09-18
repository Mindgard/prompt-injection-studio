"""Config parsing must fail soft on junk and closed on bad booleans.

An MCP server that raises during import shows up in the client as an opaque
"server failed to start", with the traceback in a log the user may never read.
So a malformed number warns and falls back. Booleans go the other way: a typo
in a security opt-in must not enable it.
"""

from __future__ import annotations

import pytest

from pistudio_mcp import envcfg


class TestTruthy:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " on "])
    def test_affirmative_values(self, value):
        assert envcfg.truthy(value) is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "", None, "maybe", "2", "y"])
    def test_everything_else_is_false(self, value):
        """A security opt-in must fail closed on anything unrecognized."""
        assert envcfg.truthy(value) is False

    def test_flag_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("PISTUDIO_TEST_FLAG", "yes")
        assert envcfg.flag("PISTUDIO_TEST_FLAG") is True

    def test_an_absent_flag_is_false(self, monkeypatch):
        monkeypatch.delenv("PISTUDIO_TEST_FLAG", raising=False)
        assert envcfg.flag("PISTUDIO_TEST_FLAG") is False


class TestNumber:
    def test_an_unset_variable_uses_the_default(self, monkeypatch):
        monkeypatch.delenv("PISTUDIO_TEST_NUM", raising=False)
        assert envcfg.number("PISTUDIO_TEST_NUM", 42.0) == 42.0

    def test_an_empty_variable_uses_the_default(self, monkeypatch):
        monkeypatch.setenv("PISTUDIO_TEST_NUM", "   ")
        assert envcfg.number("PISTUDIO_TEST_NUM", 42.0) == 42.0

    def test_a_valid_value_is_parsed(self, monkeypatch):
        monkeypatch.setenv("PISTUDIO_TEST_NUM", "7.5")
        assert envcfg.number("PISTUDIO_TEST_NUM", 42.0) == 7.5

    def test_junk_warns_and_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("PISTUDIO_TEST_NUM", "not-a-number")

        with caplog.at_level("WARNING"):
            assert envcfg.number("PISTUDIO_TEST_NUM", 42.0) == 42.0

        assert "not a number" in caplog.text

    def test_a_value_below_the_minimum_is_clamped(self, monkeypatch, caplog):
        monkeypatch.setenv("PISTUDIO_TEST_NUM", "-5")

        with caplog.at_level("WARNING"):
            assert envcfg.number("PISTUDIO_TEST_NUM", 42.0, minimum=1.0) == 1.0

        assert "below the minimum" in caplog.text


class TestInteger:
    def test_a_valid_value_is_parsed(self, monkeypatch):
        monkeypatch.setenv("PISTUDIO_TEST_INT", "9")
        assert envcfg.integer("PISTUDIO_TEST_INT", 3) == 9

    def test_a_float_is_truncated(self, monkeypatch):
        monkeypatch.setenv("PISTUDIO_TEST_INT", "9.7")
        assert envcfg.integer("PISTUDIO_TEST_INT", 3) == 9

    def test_junk_falls_back(self, monkeypatch):
        monkeypatch.setenv("PISTUDIO_TEST_INT", "nope")
        assert envcfg.integer("PISTUDIO_TEST_INT", 3) == 3

    def test_zero_is_reachable_when_the_minimum_allows_it(self, monkeypatch):
        """The action budget uses 0 to mean "disabled"."""
        monkeypatch.setenv("PISTUDIO_TEST_INT", "0")
        assert envcfg.integer("PISTUDIO_TEST_INT", 20, minimum=0) == 0
