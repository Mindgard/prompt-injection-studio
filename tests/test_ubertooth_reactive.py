"""Tests for reactive trigger match logic."""

from pistudio.hardware.ubertooth.reactive import ReactiveTrigger


class TestReactiveTriggerMatch:
    def test_matches_by_name_pattern(self):
        trigger = ReactiveTrigger(watch_pattern="Echo|Alexa")
        assert trigger.matches({"addr": "00:00:00:00:00:00", "name": "Echo Dot"})
        assert not trigger.matches({"addr": "00:00:00:00:00:00", "name": "Keyboard"})

    def test_matches_by_oui(self):
        trigger = ReactiveTrigger(watch_oui="44:07:0B")
        assert trigger.matches({"addr": "44:07:0B:AA:BB:CC", "name": ""})
        assert not trigger.matches({"addr": "DE:AD:BE:EF:00:01", "name": ""})

    def test_no_criteria_matches_nothing(self):
        trigger = ReactiveTrigger()
        assert not trigger.matches({"addr": "00:00:00:00:00:00", "name": "Anything"})
