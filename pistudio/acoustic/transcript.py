"""Did the payload survive into the transcript?

The first success oracle in the tool. Everything else generates and delivers;
this reads a persisted artifact and answers whether the payload arrived, in
what condition, and where it was cut.

Deliberately not exact-string matching. Transcription mangles text in
predictable ways -- case folding, punctuation loss, homophone substitution,
truncation -- and the interesting result is *which* of those happened, because
that says where in the pipeline the payload degraded. A boolean would throw
that away.

This module owns the verdict taxonomy. It is deliberately channel-independent
-- nothing in :data:`VERDICTS` mentions audio -- so an acoustic result and a
barcode result are scored on the same scale and are directly comparable.
:func:`score` is the shared entry point; ``tests/test_gs1_labels.py`` uses it
to score a decoded label.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Verdicts, worst to best.  Ordered so a run of results can be reduced with
# min()/max() and compared numerically.
VERDICTS = ("absent", "stripped", "truncated", "mutated", "verbatim")


@dataclass(frozen=True, slots=True)
class SurvivalVerdict:
    """What became of a payload between delivery and the sink."""

    verdict: str  # one of VERDICTS
    recovered: str  # the best-matching span found, "" when absent
    recovered_len: int
    original_len: int
    similarity: float  # 0.0-1.0 over normalised forms
    mutations: list[str] = field(default_factory=list)
    truncated_at: int | None = None

    @property
    def survived(self) -> bool:
        """Whether an LLM reading the sink would plausibly act on the payload."""
        return self.verdict in ("verbatim", "mutated", "truncated")


def normalise(text: str) -> str:
    """Reduce *text* to a form comparable across transcription pipelines.

    Case-folds, strips punctuation, collapses whitespace, and applies NFKC.
    Two payloads that differ only in ways ASR routinely alters normalise to the
    same string, which lets the scorer report "mutated" rather than "absent".
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    stripped = re.sub(r"[^\w\s]", " ", folded)
    return " ".join(stripped.split())


def _similarity(a: str, b: str) -> float:
    """Token-level overlap of two normalised strings, order-insensitive."""
    if not a and not b:
        return 1.0
    at, bt = a.split(), b.split()
    if not at or not bt:
        return 0.0
    # Multiset intersection: repeated words count only as often as they appear
    # in both, so padding a transcript cannot inflate the score.
    counts: dict[str, int] = {}
    for tok in at:
        counts[tok] = counts.get(tok, 0) + 1
    hits = 0
    for tok in bt:
        if counts.get(tok, 0) > 0:
            counts[tok] -= 1
            hits += 1
    return hits / max(len(at), len(bt))


def _detect_mutations(original: str, recovered: str) -> list[str]:
    """Name the transformations between *original* and *recovered*."""
    found: list[str] = []
    if original != recovered:
        if original.casefold() == recovered.casefold():
            found.append("case-folded")
        if re.sub(r"[^\w\s]", "", original) == re.sub(r"[^\w\s]", "", recovered):
            found.append("punctuation-stripped")
        if " ".join(original.split()) == " ".join(recovered.split()):
            found.append("whitespace-collapsed")
        if len(recovered) < len(original):
            found.append("shortened")
        if normalise(original) == normalise(recovered) and not found:
            found.append("normalised-equivalent")
    return found


def score(original: str, sink_text: str, *, threshold: float = 0.6) -> SurvivalVerdict:
    """Score whether *original* survived into *sink_text*.

    Args:
        original: The payload as delivered.
        sink_text: The artifact recovered from the sink -- a transcript, a log
            line, a scanned barcode's contents.
        threshold: Minimum normalised similarity to count as arrived at all.
            Below this the verdict is "absent".

    Returns:
        The verdict, with the recovered span and the mutations observed.
    """
    if not original:
        raise ValueError("original payload must not be empty")

    # Exact hit first: cheapest and the only route to "verbatim".
    if original in sink_text:
        return SurvivalVerdict("verbatim", original, len(original), len(original), 1.0)

    norm_original = normalise(original)
    norm_sink = normalise(sink_text)

    if norm_original and norm_original in norm_sink:
        return SurvivalVerdict(
            "mutated",
            norm_original,
            len(norm_original),
            len(original),
            1.0,
            _detect_mutations(original, norm_original) or ["normalised-equivalent"],
        )

    sim = _similarity(norm_original, norm_sink)

    # A prefix survived but the tail was cut.  Requires the prefix to be a
    # meaningful share of the payload: a few coincidentally-matching leading
    # characters are not a truncation, they are noise.  Without this floor,
    # reordered text scores "truncated" off a 7-character accident.
    truncated_at = _longest_surviving_prefix(norm_original, norm_sink)
    if truncated_at is not None and truncated_at / len(norm_original) >= threshold / 2:
        prefix = norm_original[:truncated_at]
        return SurvivalVerdict(
            "truncated",
            prefix,
            len(prefix),
            len(original),
            truncated_at / len(norm_original),
            ["truncated"],
            truncated_at=truncated_at,
        )

    if sim >= threshold:
        recovered = sink_text.strip()
        return SurvivalVerdict("mutated", recovered, len(recovered), len(original), sim, ["partial-match"])

    # Nothing recognisable.  "stripped" when the sink has content but not ours,
    # "absent" when there is nothing to have carried it.
    verdict = "stripped" if norm_sink else "absent"
    return SurvivalVerdict(verdict, "", 0, len(original), sim)


def _longest_surviving_prefix(needle: str, haystack: str) -> int | None:
    """Length of the longest prefix of *needle* present in *haystack*.

    Binary search rather than a linear walk: transcripts are long and payloads
    can be too, and this is called once per matrix cell.
    """
    if not needle or needle[:1] not in haystack:
        return None
    lo, hi = 1, len(needle)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if needle[:mid] in haystack:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    # A single surviving character is noise, not a truncated payload.
    return best if best >= 3 else None
