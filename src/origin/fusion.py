"""Fusion of detector results and the decision tree. Sections 8.1, 9.1 and 9.3 of the specification.

This is the only place in the system where four independent measurements turn
into an evidentiary class. Three things are binding here:

1. **The order of the rules.** The seven rules of section 9.1 are checked in
   order and the first one satisfied wins. The tree is written out explicitly,
   one branch under another, because in legal use it must be possible to
   reconstruct why the system made a given decision. No weighted average: the
   detectors answer different questions, so averaging their scores destroys the
   information about the kind of match.
2. **A missing measurement is not a zero.** The contract (section 7.0) makes
   sure a result with a status other than ok carries no numbers, and
   span_length returns None when the span is unknown. The conditions "greater
   than a threshold" and "less than a threshold" must therefore reject None
   explicitly, instead of counting on an exception or on None behaving like
   zero. The exception is the guard in rule 4, described next to that rule.
3. **Degradation to COMMON only after the class has been chosen**, and only for
   the work-layer classes (section 8.1). A reupload of a track built on a
   common progression does not stop being a reupload.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cmp_to_key
from typing import Protocol, Sequence, runtime_checkable

from origin import config
from origin.contracts import (
    VERDICT_CLASSES,
    FingerprintResult,
    HarmonicResult,
    LyricsResult,
    MelodicResult,
)

# The leading rights layer for a class, in the notation of section 3. An empty
# string means "no layer" and applies to COMMON and NONE - those two classes
# speak about nobody's rights.
PHONOGRAM_LAYER = "phonogram"
WORK_LAYER = "work"
NO_LAYER = ""

# Section 8.1. The full set of classes the commonality filter is allowed to touch.
DEGRADABLE_CLASSES = frozenset({"VERSION", "LYRICS", "EXCERPT_WORK"})

# Section 9.3: two scores differing by less than this are "close", so the tie is
# settled by chronology, not by the third decimal place.
PROBABILITY_TIE = 0.02


# The order is binding and is the same one the tree is written out in inside decide.
_TREE_CLASSES = (
    "EXACT", "MODIFIED", "EXCERPT_PHONOGRAM", "VERSION", "EXCERPT_WORK", "LYRICS", "NONE",
)


def _check_class_names() -> None:
    """The classes used by the tree must exist in the contract, otherwise the verdict will fail validation.

    A name drift (EXCERPT instead of EXCERPT_PHONOGRAM) would only surface when
    the ranking is serialised, that is far from the place of the error.
    """
    used = set(_TREE_CLASSES) | DEGRADABLE_CLASSES | {"COMMON"}
    foreign = used - set(VERDICT_CLASSES)
    if foreign:
        raise RuntimeError(
            f"fusion uses classes outside the contract: {sorted(foreign)}; "
            f"only {sorted(VERDICT_CLASSES)} are allowed"
        )


def _threshold(name: str) -> float:
    """The threshold value. No threshold number may be written directly into a rule's condition.

    All the thresholds of the 9.1 tree live in config.THRESHOLDS, including the
    three that table 9.2 does not list (MODIFIED_QMAX, VERSION_SEMANTIC_SIM,
    EXCERPT_WORK_MAX_COVERAGE). An unknown name is an error, not a reason for a
    fallback value on the reader's side: such a value is a second source for
    the threshold, and that is exactly what the docstring of config.threshold
    warns about.
    """
    if name not in config.THRESHOLDS:
        raise KeyError(f"unknown decision threshold: {name}")
    return config.threshold(name)


def _above(value: float | None, threshold_name: str) -> bool:
    """Whether the measurement exceeds the threshold. None is not a claim about a measurement, so it exceeds nothing."""
    return value is not None and value > _threshold(threshold_name)


def _below(value: float | None, threshold_name: str) -> bool:
    """Whether the measurement is below the threshold. None does not satisfy this condition either.

    This is the place where a silent bug is easiest: span_length == None for an
    unknown span would pass "< 15 s" as true if the condition were written
    naively, and a result saying nothing about the length of the hit would get
    the class EXCERPT_PHONOGRAM.
    """
    return value is not None and value < _threshold(threshold_name)


def _at_least(value: int | None, threshold_name: str) -> bool:
    return value is not None and value >= _threshold(threshold_name)


@runtime_checkable
class Corpus(Protocol):
    """The commonality corpus from section 8. Fusion needs only its size from it."""

    size: int

    def idf(self, pattern: str) -> float: ...

    def document_frequency(self, pattern: str) -> int: ...


try:  # pragma: no cover - depends on the merge order of parallel tasks
    from origin.commonality import should_degrade
except ImportError:  # pragma: no cover
    def should_degrade(verdict_class: str, mean_idf: float | None, corpus: Corpus) -> bool:
        """A STUB for the time when origin.commonality does not exist yet. To be removed on integration.

        The signature and the semantics are the same as in the target module: a
        class outside the work layer never degrades, a missing corpus degrades
        nothing, and the threshold comes from the commonality percentile.
        """
        if verdict_class not in DEGRADABLE_CLASSES:
            return False
        if mean_idf is None or corpus is None:
            return False
        threshold = getattr(corpus, "common_idf_threshold", 0.0)
        return int(getattr(corpus, "size", 0) or 0) > 0 and float(mean_idf) < threshold


@dataclass
class Verdict:
    """The evidentiary class, the rights layer and the justification. Positional constructor in this order."""

    verdict_class: str
    verdict_layer: str
    reasons: list[str] = field(default_factory=list)


def _number(value: float | None) -> str:
    return "no measurement" if value is None else f"{value:.2f}"


def decide(
    fp: FingerprintResult | None,
    harm: HarmonicResult | None,
    mel: MelodicResult | None,
    lyr: LyricsResult | None,
    mean_idf: float | None,
    corpus: Corpus,
) -> Verdict:
    """The decision tree of section 9.1. The first rule satisfied wins.

    Every detector may be omitted (None) and every one may arrive with a status
    other than ok - that is a normal mode of operation, not a failure.

    `mean_idf` of None means the commonality filter abstains: there were no
    patterns to measure, so it says nothing about this match and nothing is
    degraded. That is not the same as a mean IDF of zero, which is the filter
    saying the patterns are as common as patterns get.
    """
    peak = fp.peak_ratio if fp is not None else None
    length = fp.span_length if fp is not None else None
    repetitions = fp.repetitions if fp is not None else 0
    transform = fp.transform if fp is not None else None
    qmax = harm.qmax_score if harm is not None else None
    coverage = harm.coverage if harm is not None else None
    run = mel.longest_common_run if mel is not None else 0
    jaccard = lyr.jaccard if lyr is not None else None
    semantics = lyr.semantic_sim if lyr is not None else None
    # A missing lyrics result reads the same as a status other than ok: we do
    # not know whether the texts agree. The distinction matters only in rule 6,
    # which requires a claim, and in rule 4, which must not be blocked by a lack
    # of knowledge.
    lyrics_computed = lyr is not None and lyr.status == "ok"

    # 1. EXACT: A.transform == null AND A.peak_ratio > 0.60 AND A.span_length > 15 s
    #
    # The condition on transform is an amendment to the source specification.
    # Without it rule 1 swallows rule 2: material sped up by 6% matched with a
    # peak_ratio of 0.80 over a 52.7 s segment, but only after the
    # transformation grid had stretched the query back. A match that exists
    # only after transforming the query is by definition not an identical
    # recording, so it belongs to MODIFIED, and rule 1 has to step aside for
    # it rather than win on the strength of the recovered peak.
    if (
        transform is None
        and _above(peak, "EXACT_PEAK_RATIO")
        and _above(length, "EXACT_MIN_SPAN_S")
    ):
        return _with_degradation(
            "EXACT",
            PHONOGRAM_LAYER,
            [
                f"the acoustic fingerprint matched strongly: peak_ratio {_number(peak)} "
                f"above the threshold {_threshold('EXACT_PEAK_RATIO'):.2f}",
                f"the matched segment lasts {_number(length)} s, more than the required "
                f"{_threshold('EXACT_MIN_SPAN_S'):.0f} s",
                "the match needed no transformation of the query, so this is the same "
                "recording and not a different performance",
            ],
            mean_idf,
            corpus,
        )

    # 2. MODIFIED: A.transform != null AND A.peak_ratio > 0.50 AND B.qmax > 0.50
    if (
        transform
        and _above(peak, "MODIFIED_PEAK_RATIO")
        and _above(qmax, "MODIFIED_QMAX")
    ):
        return _with_degradation(
            "MODIFIED",
            PHONOGRAM_LAYER,
            [
                f"the fingerprint matched once the transformation {_describe_transform(transform)} was taken into account",
                f"peak_ratio {_number(peak)} above the threshold {_threshold('MODIFIED_PEAK_RATIO'):.2f}",
                f"the harmonic progression agrees: qmax {_number(qmax)} above "
                f"{_threshold('MODIFIED_QMAX'):.2f}",
            ],
            mean_idf,
            corpus,
        )

    # 3. EXCERPT_PHONOGRAM: A.peak_ratio > 0.40 AND A.span_length < 15 s AND A.repetitions >= 2
    if (
        _above(peak, "EXCERPT_PEAK_RATIO")
        and _below(length, "EXACT_MIN_SPAN_S")
        and _at_least(repetitions, "EXCERPT_MIN_REPETITIONS")
    ):
        return _with_degradation(
            "EXCERPT_PHONOGRAM",
            PHONOGRAM_LAYER,
            [
                f"the fingerprint matched on a short segment: peak_ratio {_number(peak)} above "
                f"{_threshold('EXCERPT_PEAK_RATIO'):.2f}",
                f"the segment lasts {_number(length)} s, less than {_threshold('EXACT_MIN_SPAN_S'):.0f} s",
                f"the segment repeats {repetitions} times, which tells a loop apart from a random coincidence",
            ],
            mean_idf,
            corpus,
        )

    # 4. VERSION: A.peak_ratio < 0.40 AND B.qmax > 0.55 AND B.coverage > 0.50
    #    AND (D.semantic_sim > 0.70 OR D.status != "ok")
    #
    # The guard on peak_ratio is deliberately at 0.40, not at the 0.25 from the
    # source specification: at 0.25 a query with a peak_ratio between 0.25 and
    # 0.40 and a high qmax would satisfy no rule at all and fall through to
    # NONE, that is a weak fingerprint trace would hide a correctly recognised
    # cover.
    #
    # An unknown peak_ratio (no detector A, or a status other than ok) does NOT
    # block the guard. The guard is there to cut off unambiguous hits, and
    # where the fingerprint was not computed there is no unambiguous hit to cut
    # off. This is the only place in the tree where a missing measurement
    # passes a condition, because it is the only one where the condition is a
    # negation rather than a claim.
    no_unambiguous_fingerprint = peak is None or _below(peak, "VERSION_MAX_PEAK_RATIO")
    if (
        no_unambiguous_fingerprint
        and _above(qmax, "VERSION_QMAX")
        and _above(coverage, "VERSION_COVERAGE")
        and (_above(semantics, "VERSION_SEMANTIC_SIM") or not lyrics_computed)
    ):
        reasons = [
            f"the harmonic progression agrees over the whole length: qmax {_number(qmax)} above "
            f"{_threshold('VERSION_QMAX'):.2f}, coverage {_number(coverage)} above "
            f"{_threshold('VERSION_COVERAGE'):.2f}",
            f"the acoustic fingerprint does not match ({_number(peak)}), so this is a different recording of the same work",
        ]
        if lyrics_computed:
            reasons.append(f"the lyrics agree in meaning: semantic_sim {_number(semantics)}")
        else:
            reasons.append(
                "the lyrics result is unavailable (an instrumental recording, a rejected "
                "transcription or no run at all), which does not block recognising the performance"
            )
        return _with_degradation("VERSION", WORK_LAYER, reasons, mean_idf, corpus)

    # 5. EXCERPT_WORK: C.longest_common_run >= 8 AND B.coverage < 0.40
    if _at_least(run, "EXCERPT_WORK_MIN_RUN") and _below(
        coverage, "EXCERPT_WORK_MAX_COVERAGE"
    ):
        return _with_degradation(
            "EXCERPT_WORK",
            WORK_LAYER,
            [
                f"a common melodic sequence of length {run}, against the threshold "
                f"{_threshold('EXCERPT_WORK_MIN_RUN'):.0f}",
                f"the agreement covers a fragment, not the whole work: coverage {_number(coverage)} below "
                f"{_threshold('EXCERPT_WORK_MAX_COVERAGE'):.2f}",
                "this is a compositional borrowing, not a fingerprint hit",
            ],
            mean_idf,
            corpus,
        )

    # 6. LYRICS: B.qmax < 0.40 AND D.status == "ok" AND D.jaccard > 0.50
    if (
        _below(qmax, "LYRICS_MAX_QMAX")
        and lyrics_computed
        and _above(jaccard, "LYRICS_JACCARD")
    ):
        return _with_degradation(
            "LYRICS",
            WORK_LAYER,
            [
                f"textual agreement: jaccard {_number(jaccard)} above "
                f"{_threshold('LYRICS_JACCARD'):.2f}",
                f"the music differs: qmax {_number(qmax)} below {_threshold('LYRICS_MAX_QMAX'):.2f}",
                "the threshold of this class is entered by hand, there is no calibration data (section 10.4)",
            ],
            mean_idf,
            corpus,
        )

    # 7. NONE: in all remaining cases.
    return Verdict(
        "NONE",
        NO_LAYER,
        ["none of the measurements crossed the threshold of its class"],
    )


def _describe_transform(transform: dict[str, float]) -> str:
    parts = []
    tempo = transform.get("tempo_ratio")
    if tempo is not None:
        parts.append(f"tempo x{tempo:.2f}")
    semitones = transform.get("semitones")
    if semitones is not None:
        parts.append(f"transposition by {semitones:+.0f} semitones")
    return ", ".join(parts) if parts else "of a changed signal"


def _with_degradation(
    verdict_class: str,
    layer: str,
    reasons: list[str],
    mean_idf: float | None,
    corpus: Corpus,
) -> Verdict:
    """The commonality filter from section 8.1, applied AFTER the class has been chosen.

    The class membership check stays here even though should_degrade receives
    the class and checks it on its own side. This is Global Constraint 5 and
    the only safety catch protecting EXACT against a bug in the commonality
    module: with the duplicate check, a bad filter implementation can at worst
    fail to degrade something that should have been degraded, rather than turn
    a reupload into a genre convention.
    """
    if verdict_class not in DEGRADABLE_CLASSES:
        return Verdict(verdict_class, layer, reasons)
    # The filter abstains. A match whose segment yielded no patterns gives the
    # commonality corpus nothing to be commonly-known about, and a VERSION on a
    # two-chord loop is still a VERSION - not "a genre convention".
    if mean_idf is None:
        return Verdict(verdict_class, layer, reasons)
    if not should_degrade(verdict_class, mean_idf, corpus):
        return Verdict(verdict_class, layer, reasons)
    return Verdict(
        "COMMON",
        # COMMON concerns no rights layer (section 3), so the layer chosen by
        # the rule disappears together with the class.
        NO_LAYER,
        [
            *reasons,
            f"the match rests on patterns that are common in the corpus (mean idf "
            f"{_number(mean_idf)}), so the class {verdict_class} is degraded to COMMON",
            "this is a genre convention, not a signal of borrowing",
        ],
    )


@dataclass
class RankItem:
    """A ranking entry, limited to what the chronology rule from 9.3 needs.

    `verdict_class` is here for one reason: NONE has to sort below every class
    that claims something, whatever numbers the two carry. An empty class name
    means "not stated" and sorts on its probability alone.
    """

    candidate_id: str
    probability: float | None
    published: str | None = None
    verdict_class: str = ""


def _score(item: RankItem) -> float:
    """NONE lands at the end of the ranking, and so does a missing probability.

    A candidate we found nothing on cannot outrank one we recognised, so NONE
    goes to the bottom no matter what its strongest measurement was: a
    `peak_ratio` of 0.02 on an unrelated recording is not evidence of anything
    and must not stand above a class that names what it found. Everything else
    ranks on its raw probability, and a class without one lands next to NONE -
    at the end, without pretending to be a zero.
    """
    if item.verdict_class == "NONE" or item.probability is None:
        return float("-inf")
    return float(item.probability)


def _close(a: float, b: float) -> bool:
    if math.isinf(a) or math.isinf(b):
        return False
    return abs(a - b) < PROBABILITY_TIE


def _compare(a: RankItem, b: RankItem) -> int:
    score_a, score_b = _score(a), _score(b)
    # Section 9.3: chronology settles ties only, and only between candidates
    # that have a date. A missing date is not a late date - a candidate without
    # one simply does not take part in this rule and keeps its own score.
    if (
        _close(score_a, score_b)
        and a.published is not None
        and b.published is not None
        and a.published != b.published
    ):
        # Manifest dates are in ISO 8601, so lexicographic order is also
        # chronological order for the shortened form ("1975").
        return -1 if a.published < b.published else 1
    if score_a != score_b:
        return -1 if score_a > score_b else 1
    return 0


def rank(items: Sequence[RankItem]) -> list[RankItem]:
    """The ranking, descending by probability, with chronology as the tie-breaker.

    The relation "close score" is not transitive (0.80 is close to 0.815, and
    0.815 close to 0.83, though 0.80 and 0.83 are not), so the order is defined
    by a pairwise comparison rather than by a single sort key. Python's sort is
    stable, so indistinguishable entries keep their input order.
    """
    return sorted(items, key=cmp_to_key(_compare))


_check_class_names()
