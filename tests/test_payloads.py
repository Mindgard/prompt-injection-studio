"""The built-in payload library must stay honest about its own evidence.

Two properties matter here, and neither is enforced by anything else.

The first is carrier fit. The narrowest carriers are unforgiving -- an SSID is
32 octets and a BLE advertising name about 29 -- and a payload that no longer
fits one is not a failing test somewhere downstream, it is a payload that
silently stops being deployable on the channel it was written for. The
``ble-micro`` family exists solely to fit those fields, so its members are
pinned against the real ``CarrierField.fits`` rather than a copied constant.

The second is provenance. Every mechanism in this library has a published
success rate that disagrees with what we measured against a current model:
structural mimicry is published at 96% ISR and measured 0/110. A payload that
carries only a description implies the published number; one that carries its
provenance states both. So the evidence-bearing categories are required to
have provenance, and the control is required to say that it is a control --
an entry that quietly lost its provenance string is the failure this catches.
"""

from __future__ import annotations

import pytest

from pistudio.carriers import get_carrier
from pistudio.hardware.payloads import BUILTIN_PAYLOADS, Payload

# Categories added to reflect the mechanisms with the strongest published
# support. Each rests on a specific citation, so each must carry provenance.
EVIDENCE_CATEGORIES = ("structural", "human-directed", "authority-shed", "authority")

# The narrowest fields any payload is expected to reach, with the carrier and
# field names the library resolves them by.
NARROW_FIELDS = (("ble", "adv_name"), ("wifi", "ssid"))


def _by_name() -> dict[str, Payload]:
    return {p.name: p for p in BUILTIN_PAYLOADS}


class TestCategories:
    """The new mechanisms are actually present."""

    @pytest.mark.parametrize("category", EVIDENCE_CATEGORIES)
    def test_category_is_represented(self, category):
        assert any(p.category == category for p in BUILTIN_PAYLOADS), (
            f"no built-in payload in category {category!r}; the library no longer covers a mechanism it claims to"
        )

    def test_authority_is_distinct_from_impersonation(self):
        """Forged in-context authority is not DAN-style role play.

        They measure very differently under intent-aware defence, so collapsing
        them into one category would lose the distinction the split exists for.
        """
        cats = {p.category for p in BUILTIN_PAYLOADS}
        assert {"authority", "impersonation"} <= cats

    def test_names_are_unique(self):
        names = [p.name for p in BUILTIN_PAYLOADS]
        dupes = {n for n in names if names.count(n) > 1}
        assert not dupes, f"duplicate built-in payload names: {sorted(dupes)}"


class TestProvenance:
    """Payloads resting on published evidence must cite it."""

    def test_evidence_categories_have_provenance(self):
        missing = [p.name for p in BUILTIN_PAYLOADS if p.category in EVIDENCE_CATEGORIES and not p.provenance.strip()]
        assert not missing, (
            f"payloads in evidence-bearing categories with no provenance: {missing}. "
            "An uncited payload implies its published rate is the measured one."
        )

    def test_provenance_records_both_published_and_measured(self):
        """A provenance string that gives only the published rate overstates.

        Every mechanism here was measured at zero against ``claude-haiku-4-5``.
        Citing the paper without that result is the specific dishonesty the
        field was added to prevent.
        """
        for payload in BUILTIN_PAYLOADS:
            if payload.category not in EVIDENCE_CATEGORIES:
                continue
            assert "measured" in payload.provenance.lower(), (
                f"{payload.name} cites published evidence but no measured result"
            )

    def test_control_declares_itself_a_control(self):
        """``instruction-override`` is the 0.00 ISR baseline, not a candidate.

        It is deliberately retained -- it is what makes the other rates
        meaningful -- so it must read as a control rather than as a payload
        someone should reach for.
        """
        control = _by_name()["ignore-instructions"]
        assert control.category == "instruction-override"
        assert "CONTROL" in control.description
        assert "0.00" in control.provenance


class TestNarrowCarrierFit:
    """Short payloads must keep fitting the fields they were written for."""

    def test_ble_micro_family_fits_the_advertising_name(self):
        adv = get_carrier("ble").get_field("adv_name")
        too_long = [
            (p.name, len(p.text.encode()))
            for p in BUILTIN_PAYLOADS
            if p.category == "ble-micro" and not adv.fits(p.text)
        ]
        # Two ble-micro entries are documented as ADV+SCAN_RSP (56-57B), which
        # exceeds a bare advertising name; they are named rather than silently
        # excluded by a length threshold, so a new overlong entry still fails.
        allowed = {"ble-system-override", "ble-prompt-leak", "ble-exfil-short"}
        unexpected = [entry for entry in too_long if entry[0] not in allowed]
        assert not unexpected, f"no longer fits adv_name ({adv.max_length}B): {unexpected}"

    def test_the_micro_structural_payload_reaches_every_carrier(self):
        """``structural-verdict`` is the one 96%-ISR shape narrow enough to fit.

        Its value is that it reaches the tightest channels, so if an edit grows
        it past 29 bytes the library loses its only micro-sized structural
        entry and that should not pass quietly.
        """
        payload = _by_name()["structural-verdict"]
        for carrier_name, field_name in NARROW_FIELDS:
            field = get_carrier(carrier_name).get_field(field_name)
            assert field.fits(payload.text), (
                f"structural-verdict ({len(payload.text.encode())}B) no longer fits "
                f"{carrier_name}.{field_name} ({field.max_length}B)"
            )

    def test_composite_fits_an_ssid(self):
        """The composite exists to stack two mechanisms inside 32 octets."""
        payload = _by_name()["composite-auth-conceal"]
        ssid = get_carrier("wifi").get_field("ssid")
        assert ssid.fits(payload.text), (
            f"composite-auth-conceal is {len(payload.text.encode())}B, SSID cap is "
            f"{ssid.max_length}B -- it no longer earns its place"
        )

    def test_documented_byte_counts_match_the_text(self):
        """Descriptions quote byte counts; drift makes them misinformation.

        The counts are how an operator picks a payload for a channel without
        measuring, so a stale one sends them to a carrier it cannot fit.
        """
        import re

        mismatches = []
        for payload in BUILTIN_PAYLOADS:
            match = re.search(r"\((\d+)B\)", payload.description)
            if not match:
                continue
            claimed = int(match.group(1))
            actual = len(payload.text.encode())
            if claimed != actual:
                mismatches.append(f"{payload.name}: says {claimed}B, is {actual}B")
        assert not mismatches, "byte counts in descriptions are stale: " + "; ".join(mismatches)
