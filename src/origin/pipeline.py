"""The analysis run from a file to a verdict. Sections 4 and 12 of the specification.

This is the only place where ingest, the four detectors, pre-filtering, the
commonality filter, fusion, the legal layer and calibration meet in a single
sentence. None of those modules calls another - the order lives here and
nowhere else.

**Shape: an asynchronous iterator of events.** `run` is a generator of
`StreamEvent`, exactly the same kind of producer as `api.mock.run`, so
`JobStore.start` takes it without an adapter. The result does not come back
through `return` but through `on_result`: the pipeline knows the `AnalyzeResult`
contract, it does not know the job store, and the store gets the result exactly
at the moment it is ready - before the `verdict` event, so that a frontend which
fetches `/result` immediately on that event does not still get the previous
version.

**Two execution levels (section 4).** Level 1 is ingest, fingerprint, harmony,
pre-filtering, commonality and fusion - it ends with the partial verdict. Level
2 is lyrics and melody, a second fusion and the final verdict. Level 2 **raises**
the verdict and never takes it away: a failure of a level 2 detector leaves the
class from level 1.

**Every detector is computed in a worker thread** (`asyncio.to_thread`). Without
that the event loop would sit on computing chromagrams and the whole SSE stream
would reach the browser in a single batch at the end - that is, the promise
"a verdict in five seconds, evidence over the next thirty" would disappear into
a buffer. The background task itself is created by `JobStore.start`, so there is
no reason to multiply `create_task` here.

**A second fence around the detectors.** `base.run_guarded` catches an exception
inside a detector, but it will not catch one thrown from `run` itself (a
patched method, an import error, a missing model escaping other than through the
contract). Here is the outer fence: any exception from any detector turns into a
`failed` envelope and the run carries on.

**What this module does not pretend today.** The heavy models are not in the
environment, so detectors D and C return a `failed` envelope with the reason
`model_unavailable` - that is a normal mode of operation, not a failure. There
is no calibration either, so `probability_status` says `uncalibrated`
everywhere, and the number in the `probability` field is the **raw score of the
detector** that decided the class, not a probability from a model.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any

from origin import (
    calibration,
    candidates as manifest,
    commonality,
    config,
    fusion,
    ingest,
    legal,
    shortlist,
)
from origin.contracts import (
    Alignment,
    AnalyzeResult,
    Candidate,
    Commonality,
    DetectorEnvelope,
    DetectorResult,
    DetectorStatus,
    Evidence,
    FingerprintResult,
    HarmonicResult,
    LyricsResult,
    MelodicResult,
    QueryInfo,
    RankingEntry,
    RightsLayer,
    StageStatus,
    StreamEvent,
    VerdictClass,
)
from origin.detectors import base, fingerprint, harmonic, lyrics, melodic, registry
from origin.detectors.fingerprint import FingerprintDetector
from origin.detectors.harmonic import HarmonicDetector
from origin.detectors.lyrics import LyricsDetector
from origin.detectors.melodic import MelodicDetector

__all__ = [
    "DETECTORS",
    "corpus_path",
    "load_corpus",
    "prewarm",
    "prewarm_set",
    "run",
    "run_sync",
]

# --- the detector registry --------------------------------------------------
#
# Section 7.0 and the decision from the brief addendum: the registry is empty by
# design and the full set is wired in by ONE place, this one. No detector module
# registers itself, because then the contents of the registry would depend on
# what somebody happened to import.
DETECTORS: dict[str, base.Detector] = {
    "fingerprint": registry.register("fingerprint", FingerprintDetector()),
    "harmonic": registry.register("harmonic", HarmonicDetector()),
    "lyrics": registry.register("lyrics", LyricsDetector()),
    "melodic": registry.register("melodic", MelodicDetector()),
}

#: Level 1 detectors, in the order of section 4.
LEVEL_1 = ("fingerprint", "harmonic")
#: Level 2 detectors, in the order of section 4. Lyrics before melody, because
#: it is the lyrics pass that starts the source separation the melody uses.
LEVEL_2 = ("lyrics", "melodic")

CORPUS_ENV = "ORIGIN_CORPUS"
DEFAULT_CORPUS_PATH = "data/corpus/idf.json"

#: The reason given to a candidate with no audio file on disk. The detectors
#: name it in their own way ("no level 0 fingerprint", "no such file"), because
#: each of them sees a different symptom. The cause is one, and the pipeline
#: names it once, so that the frontend has something to recognise rather than
#: parsing exception text.
AUDIO_MISSING_REASON = "audio_missing"

#: Classes whose raw number comes from the acoustic fingerprint (section 9.1
#: rules 1-3). The rest take it from the harmony or from the lyrics - see
#: `_raw_probability`.
_FINGERPRINT_CLASSES: tuple[VerdictClass, ...] = ("EXACT", "MODIFIED", "EXCERPT_PHONOGRAM")

#: Envelope status (section 7.0) mapped onto stream stage status (section 12).
#: `not_applicable` has no counterpart in the stage vocabulary, because the
#: stage did happen - the reason travels in `detail`, not in the status.
_STAGE_STATUS: dict[DetectorStatus, StageStatus] = {
    "ok": "done",
    "not_applicable": "done",
    "gated": "gated",
    "failed": "failed",
}


# --- the commonality corpus -------------------------------------------------


def corpus_path() -> Path:
    """Path of the IDF corpus. Read on every call, because tests move it."""
    return Path(os.environ.get(CORPUS_ENV, DEFAULT_CORPUS_PATH))


# The corpus is two megabytes of JSON. Loaded on every request it would eat the
# level 1 budget on parsing alone, so it stays in process memory. The key is the
# path together with the modification time: a rebuilt corpus invalidates its
# entry on its own, without restarting the API.
_CORPUS_CACHE: dict[tuple[str, float], commonality.Corpus] = {}


def load_corpus() -> commonality.Corpus:
    """The IDF corpus from disk, or an empty corpus.

    An empty corpus is a **valid state**, not a failure: `should_degrade` with
    size zero degrades nothing, so a missing corpus takes away the system's
    ability to say "this is a genre convention" but does not bring the analysis
    down.
    """
    file = corpus_path()
    try:
        key = (str(file.resolve()), file.stat().st_mtime)
    except OSError:
        return commonality.Corpus(0, {})
    stored = _CORPUS_CACHE.get(key)
    if stored is not None:
        return stored
    try:
        corpus = commonality.Corpus.load(file)
    except (OSError, ValueError):
        return commonality.Corpus(0, {})
    _CORPUS_CACHE[key] = corpus
    return corpus


# --- level 0: warming the cache ---------------------------------------------


def prewarm(candidate_list: Sequence[Candidate]) -> dict[str, dict[str, str]]:
    """Computes candidate representations up front. Level 0 from section 4.

    Called **once at API startup** (lifespan), never on a request: the
    five-second budget of level 1 holds only with a warm cache. Returns a map
    detector -> {candidate id: reason} for those that could not be computed;
    empty dictionaries mean the cache is warm throughout.
    """
    return {
        "fingerprint": fingerprint.prewarm(candidate_list),
        "harmonic": harmonic.prewarm(candidate_list),
        "melodic": _prewarm_melodic(candidate_list),
    }


def _prewarm_melodic(candidate_list: Sequence[Candidate]) -> dict[str, str]:
    """Candidate melodies into the cache. Level 0, the same as the other two.

    `melodic.representation` calls itself a level 0 artifact and says outright
    that without a warm cache level 2 does not fit any budget - and until now
    nothing warmed it, so the first analysis of a set paid for transcribing
    every shortlisted candidate on the request path (24.5 s cold against 17.8 s
    warm on the measured run). This is that missing warm-up.

    Sequentially, unlike the fingerprint: basic-pitch holds an ONNX session per
    thread and the models already sit near the container's memory limit, so a
    thread pool here would buy seconds at the price of the ceiling. Without the
    model the whole thing is one dictionary and not a single file is decoded -
    a missing heavy model is a normal state of this system, not a failure.
    """
    if not candidate_list:
        return {}
    if not melodic.model_available():
        return {candidate.id: "model_unavailable" for candidate in candidate_list}
    errors: dict[str, str] = {}
    for candidate in candidate_list:
        try:
            melodic.representation(candidate.audio_path)
        except Exception as error:  # noqa: BLE001 - no audio means no representation
            errors[candidate.id] = f"{type(error).__name__}: {error}"
    return errors


def prewarm_set(set_id: str = "demo_01") -> dict[str, dict[str, str]]:
    """Warming the cache for a whole set from the manifest. A missing manifest is not an error."""
    try:
        candidate_list = manifest.load_set(set_id).candidates
    except (FileNotFoundError, KeyError, ValueError):
        return {"fingerprint": {}, "harmonic": {}}
    return prewarm(candidate_list)


# --- helpers on envelopes ---------------------------------------------------


def _result(envelope: DetectorEnvelope | None, candidate_id: str) -> DetectorResult | None:
    """The detector result for a candidate, or None. None means "no measurement"."""
    if envelope is None:
        return None
    for result in envelope.results:
        if result.candidate_id == candidate_id:
            return result
    return None


def _ok_result(envelope: DetectorEnvelope | None, candidate_id: str) -> Any:
    """A result that actually measured something. Every other status reads as an absence.

    Fusion accepts None and handles it explicitly (section 9.1), so handing it a
    result with status `gated` would be handing it a number that does not exist.
    """
    if envelope is None or envelope.status != "ok":
        return None
    result = _result(envelope, candidate_id)
    return result if result is not None and result.status == "ok" else None


def _number(result: Any, field: str) -> float | None:
    value = getattr(result, field, None) if result is not None else None
    return None if value is None else float(value)


def _highest(envelope: DetectorEnvelope | None, field: str) -> float | None:
    """The highest value of a field among the `ok` results. For the stage header on screen E2."""
    if envelope is None or envelope.status != "ok":
        return None
    values = [
        float(getattr(r, field))
        for r in envelope.results
        if r.status == "ok" and getattr(r, field, None) is not None
    ]
    return max(values) if values else None


def _merge(base_envelope: DetectorEnvelope, new: DetectorEnvelope) -> DetectorEnvelope:
    """Overwrites the base results with the new ones, by candidate identifier.

    Used for the second fingerprint pass after the transformation grid: the new
    result concerns the same candidate and is strictly better informed, because
    it was produced knowing what the harmony said.
    """
    if new.status != "ok":
        return base_envelope
    replacements = {r.candidate_id: r for r in new.results}
    if not replacements:
        return base_envelope
    return DetectorEnvelope(
        detector=base_envelope.detector,
        status=base_envelope.status if base_envelope.status == "ok" else "ok",
        reason=base_envelope.reason,
        results=[replacements.pop(r.candidate_id, r) for r in base_envelope.results]
        + list(replacements.values()),
    )


async def _envelope(name: str, call: Callable[[], DetectorEnvelope]) -> DetectorEnvelope:
    """The second fence. The detector is computed in a worker thread, an exception becomes an envelope.

    `base.run_guarded` sits inside the detector and will not catch an exception
    thrown from `run` itself - and that is exactly where a patched method, a
    missing dependency or a bug in the gate lands. Section 9.1 requires fusion
    to receive an envelope one way or another.
    """
    try:
        return await asyncio.to_thread(call)
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001 - the reason lands in the envelope, not in a log
        return base.empty_envelope(name, "failed", f"{type(error).__name__}: {error}")


# --- candidate audio --------------------------------------------------------


def _candidate_file(candidate: Candidate) -> Path:
    """The manifest path relative to the working directory, and second to the repository."""
    path = Path(candidate.audio_path)
    if path.is_absolute() or path.exists():
        return path
    from_root = manifest.REPO_ROOT / path
    return from_root if from_root.exists() else path


def _has_audio(candidate: Candidate) -> bool:
    return _candidate_file(candidate).is_file()


def _reason(candidate: Candidate, status: DetectorStatus, reason: str | None) -> str | None:
    """The reason as seen by the frontend. A missing file has one name here.

    The detectors describe the symptom they see at home, and each sees a
    different one: the fingerprint talks about a missing level 0 artifact, the
    harmony about a failed decode. When the file simply is not there, the cause
    is one and it has one name.
    """
    if status != "ok" and not _has_audio(candidate):
        return AUDIO_MISSING_REASON
    return reason


def _evidence(envelope: DetectorEnvelope | None, candidate: Candidate) -> Evidence:
    """A summary of the envelope next to a ranking entry (section 12).

    The envelope status takes precedence: when the whole run did not happen, the
    result for an individual candidate means nothing.
    """
    if envelope is None:
        return Evidence(status="not_applicable", reason="the detector was not run")
    if envelope.status != "ok":
        return Evidence(
            status=envelope.status,
            reason=_reason(candidate, envelope.status, envelope.reason),
        )
    result = _result(envelope, candidate.id)
    if result is None:
        return Evidence(status="not_applicable", reason="no result for this candidate")
    return Evidence(status=result.status, reason=_reason(candidate, result.status, result.reason))


def _without_audio(candidate_list: Sequence[Candidate]) -> list[str]:
    return [c.id for c in candidate_list if not _has_audio(c)]


# --- pre-filtering ----------------------------------------------------------


def _filterable(
    candidate_list: Sequence[Candidate],
    env_harmonic: DetectorEnvelope,
    env_fingerprint: DetectorEnvelope,
) -> list[Candidate]:
    """Candidates that can be pre-filtered at all, in descending order of knowledge.

    `shortlist.select` sorts by the harmonic descriptor and reaches for it
    through `harmonic.representation`, which for a candidate without audio
    raises inside the sort key. That is why only those the harmony really
    computed go to pre-filtering. When it computed nobody - because the whole
    detector fell over - the fingerprint remains, and when that is silent too,
    the whole set passes: better to pre-filter by the manifest order than to
    show nothing.
    """
    measurable = [c for c in candidate_list if _ok_result(env_harmonic, c.id) is not None]
    if measurable:
        return measurable
    with_fingerprint = [c for c in candidate_list if _ok_result(env_fingerprint, c.id) is not None]
    return with_fingerprint or list(candidate_list)


def _prefilter(
    clip: ingest.Clip,
    candidate_list: Sequence[Candidate],
    env_harmonic: DetectorEnvelope,
    env_fingerprint: DetectorEnvelope,
) -> list[Candidate]:
    filterable = _filterable(candidate_list, env_harmonic, env_fingerprint)
    if not filterable:
        return []
    try:
        return shortlist.select(clip, filterable, config.SHORTLIST_SIZE)
    except Exception:  # noqa: BLE001 - pre-filtering is an optimisation, not a condition of the analysis
        return list(filterable[: config.SHORTLIST_SIZE])


def _for_grid(
    candidate_list: Sequence[Candidate],
    env_fingerprint: DetectorEnvelope,
    env_harmonic: DetectorEnvelope,
) -> list[Candidate]:
    """Candidates for which the grid of 143 transformations is worth running (section 7.1).

    The condition is the same one the detector checks at home, and it is
    deliberately repeated here: without it the second pass would go over the
    whole set, and that is exactly the work section 7.1 tells us to avoid. The
    detector will filter this list once more, in its own way - this is a coarse
    sieve, not a decision.
    """
    harmonic_threshold = config.threshold("VERSION_QMAX")
    fingerprint_threshold = config.threshold("MODIFIED_PEAK_RATIO")
    selected: list[Candidate] = []
    for candidate in candidate_list:
        qmax = _number(_ok_result(env_harmonic, candidate.id), "qmax_score")
        if qmax is None or qmax < harmonic_threshold:
            continue
        peak = _number(_ok_result(env_fingerprint, candidate.id), "peak_ratio")
        if peak is not None and peak >= fingerprint_threshold:
            continue
        selected.append(candidate)
    return selected


# --- commonality, probability, ranking entry --------------------------------


def _commonality_of(
    harm: HarmonicResult | None, corpus: commonality.Corpus
) -> tuple[list[tuple[str, ...]], Commonality]:
    """The patterns matched by the harmony and what the corpus says about them (section 8).

    The patterns come from `HarmonicResult.chord_sequence`, that is from the
    segment that ACTUALLY lay on the alignment path. The query's whole
    progression would be a claim about something we did not match.

    `corpus_frequency` is the frequency of the **most common** of the matched
    patterns. The sentence on screen E3 reads "this motif occurs in N tracks of
    the corpus" and is meant to answer whether the match stands on something
    well-worn - and it does when even one of the patterns is well-worn.
    """
    sequence = list(getattr(harm, "chord_sequence", []) or [])
    patterns = commonality.chord_ngrams(sequence) if sequence else []
    if not patterns:
        return [], Commonality(corpus_size=corpus.size or None)
    return patterns, Commonality(
        mean_idf=commonality.mean_idf(patterns, corpus),
        corpus_frequency=max(corpus.document_frequency(p) for p in patterns),
        corpus_size=corpus.size or None,
    )


def _raw_probability(
    verdict_class: VerdictClass,
    fp: FingerprintResult | None,
    harm: HarmonicResult | None,
    mel: MelodicResult | None,
    lyr: LyricsResult | None,
) -> float | None:
    """The raw score of the detector that decided the class. This is NOT calibration.

    Section 10.5 requires the UI to tell a number from a model apart from a raw
    one, and `calibration.is_available` today says `False` for every class,
    because there is no model. Instead of pretending to a probability we report
    the measurement that won in the 9.1 tree: `peak_ratio` for the fingerprint
    classes, `qmax_score` for the harmonic classes, `jaccard` for the lyrics
    class.

    `EXCERPT_WORK` is decided by the length of the common interval run, which
    is a count and not a score in 0-1. It is reported as that run measured
    against the length the class requires (`EXCERPT_WORK_MIN_RUN`), capped at
    1.0: a run at the threshold reads 1.0, a longer one no more than that. This
    is emphatically not a probability, which is what `uncalibrated` says, but it
    is a number, and without one the class had no place in the ranking at all -
    a recognised melodic borrowing sank below every unrelated NONE.

    `NONE` gets the strongest measurement there was - not in order to claim
    anything, but so that the ranking has something to order entries that all
    fell through with. `COMMON` takes the harmony, because only work-layer
    classes are degraded and those are exactly the ones it decides.
    """
    peak = _number(fp, "peak_ratio")
    qmax = _number(harm, "qmax_score")
    if verdict_class in _FINGERPRINT_CLASSES:
        return peak
    if verdict_class in ("VERSION", "COMMON"):
        return qmax
    if verdict_class == "LYRICS":
        return _number(lyr, "jaccard")
    if verdict_class == "EXCERPT_WORK":
        run = _number(mel, "longest_common_run") or 0.0
        longest = max(run, config.threshold("EXCERPT_WORK_MIN_RUN"))
        return min(1.0, run / longest) if longest else 0.0
    measured = [x for x in (peak, qmax) if x is not None]
    return max(measured) if measured else None


def _layer(verdict: fusion.Verdict) -> RightsLayer | None:
    """An empty string from fusion means "no layer" and on the wire it has to be null."""
    return verdict.verdict_layer or None  # type: ignore[return-value]


def _alignment(fp: FingerprintResult | None, harm: HarmonicResult | None) -> Alignment | None:
    """Where and how the query was aligned to the candidate. All four fields missing means no block."""
    block = Alignment(
        query_span=getattr(fp, "query_span", None),
        candidate_span=getattr(fp, "candidate_span", None),
        transposition=getattr(harm, "transposition", None),
        tempo_ratio=getattr(harm, "tempo_ratio", None),
    )
    if block.model_dump(exclude_none=True):
        return block
    return None


def _entry(
    candidate: Candidate,
    envelopes: dict[str, DetectorEnvelope],
    corpus: commonality.Corpus,
) -> tuple[RankingEntry, float | None]:
    """One ranking entry together with the number that will order it.

    The legal block is computed at both levels even though section 4 mentions it
    at level 2. `legal.assess` is a pure function over already computed results
    and costs nothing - whereas an entry without a legal block at level 1 would
    force screen E6 to wait for level 2 to show a licence status that is copied
    straight from the manifest.
    """
    fp = _ok_result(envelopes.get("fingerprint"), candidate.id)
    harm = _ok_result(envelopes.get("harmonic"), candidate.id)
    mel = _ok_result(envelopes.get("melodic"), candidate.id)
    lyr = _ok_result(envelopes.get("lyrics"), candidate.id)

    _, commonality_block = _commonality_of(harm, corpus)
    # `mean_idf` travels as None, never as 0.0: None is the commonality filter
    # having nothing to say (the matched segment yielded no chord n-grams),
    # while 0.0 is below every threshold and would degrade the class to COMMON.
    # `commonality.mean_idf`'s own docstring says such a match must not go
    # through the filter at all.
    verdict = fusion.decide(fp, harm, mel, lyr, commonality_block.mean_idf, corpus)
    verdict_class: VerdictClass = verdict.verdict_class  # type: ignore[assignment]
    probability = _raw_probability(verdict_class, fp, harm, mel, lyr)

    return (
        RankingEntry(
            rank=0,  # the number is assigned by `_ranking` after ordering
            candidate=candidate,
            verdict_class=verdict_class,
            verdict_layer=_layer(verdict),
            probability=probability,
            probability_status=calibration.probability_status(verdict_class),
            evidence={
                name: _evidence(envelopes.get(name), candidate)
                for name in envelopes
            },
            alignment=_alignment(fp, harm),
            commonality=commonality_block,
            legal=legal.assess(verdict, fp, candidate),
            explanation=" ".join(f"{r}." for r in verdict.reasons),
        ),
        probability,
    )


def _ranking(
    candidate_list: Sequence[Candidate],
    envelopes: dict[str, DetectorEnvelope],
    corpus: commonality.Corpus,
) -> list[RankingEntry]:
    """Entries ordered by the rule from 9.3: probability, chronology on a tie."""
    entries = {}
    to_rank = []
    for candidate in candidate_list:
        entry, probability = _entry(candidate, envelopes, corpus)
        entries[candidate.id] = entry
        to_rank.append(
            fusion.RankItem(
                candidate.id, probability, candidate.published, entry.verdict_class
            )
        )
    ranked = []
    for number, item in enumerate(fusion.rank(to_rank), start=1):
        entry = entries[item.candidate_id]
        entry.rank = number
        ranked.append(entry)
    return ranked


def _analysis_result(
    clip: ingest.Clip | None,
    ranking: list[RankingEntry],
    level: int,
) -> AnalyzeResult:
    """The result after a given level. The `calibration` block stays empty, because there is no model.

    Section 12 shows the model version and the precision at the threshold in
    that block. The absence of the object means exactly what it means in section
    10: there is no model, and the numbers next to the entries are raw. Writing
    anything here would be faking calibration.
    """
    return AnalyzeResult(
        status="partial" if level == 1 else "final",
        completed_levels=[1] if level == 1 else [1, 2],
        query=QueryInfo(duration=clip.duration if clip is not None else 0.0),
        ranking=ranking,
        calibration=None,
    )


def _verdict_event(
    ranking: list[RankingEntry], level: int, previous: RankingEntry | None
) -> StreamEvent:
    """The verdict carries the ranking leader at that level. An empty ranking is an explicit NONE."""
    top = ranking[0] if ranking else None
    detail: dict[str, Any] = {
        "class": top.verdict_class if top else "NONE",
        "probability": top.probability if top else None,
        "probability_status": (
            top.probability_status if top else calibration.probability_status("NONE")
        ),
        "candidate_id": top.candidate.id if top else None,
    }
    if level == 2:
        # The frontend animates the upgrade of the verdict, so it has to know what from.
        detail["previous_class"] = previous.verdict_class if previous else "NONE"
        detail["previous_probability"] = previous.probability if previous else None
    return StreamEvent(
        stage="verdict",
        level=level,
        status="partial" if level == 1 else "final",
        detail=detail,
    )


def _envelope_detail(envelope: DetectorEnvelope, **fields: Any) -> dict[str, Any]:
    """The stage header plus the full set of results for screens E4-E5.

    Screen E2 reads individual numbers from `detail` and deliberately ignores
    `envelope` - that is material for the evidence screens, not a header for the
    stage list.
    """
    detail: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
    if envelope.reason:
        detail["reason"] = envelope.reason
    detail["envelope"] = envelope.model_dump(mode="json")
    return detail


# --- the run ----------------------------------------------------------------


async def run(
    source: str,
    candidate_set: str = "demo_01",
    *,
    candidates: Sequence[Candidate] | None = None,
    on_result: Callable[[AnalyzeResult], None] | None = None,
) -> AsyncIterator[StreamEvent]:
    """The whole analysis run as a stream of events. Sections 4 and 12.

    `source` is a path on disk or an address; `candidate_set` names the
    manifest, and `candidates` allows skipping it and passing the set directly
    (tests, one-off runs). `on_result` receives the partial result after level 1
    and the final one after level 2, **before** the corresponding `verdict`
    event.
    """
    store_result = on_result or (lambda _: None)
    candidate_list = (
        list(candidates)
        if candidates is not None
        else list(manifest.load_set(candidate_set).candidates)
    )
    corpus = load_corpus()

    # --- ingest -------------------------------------------------------------
    yield StreamEvent(stage="ingest", level=1, status="running", detail={"source": source})
    try:
        clip = await asyncio.to_thread(ingest.load_clip, source)
    except Exception as error:  # noqa: BLE001 - material that cannot be loaded
        # The only failure that ends the run. Without input material there is
        # nothing to compare with what, so every subsequent stage would be
        # pretending to work.
        reason = f"{type(error).__name__}: {error}"
        yield StreamEvent(stage="ingest", level=1, status="failed", detail={"reason": reason})
        store_result(AnalyzeResult(status="failed", completed_levels=[], query=QueryInfo(duration=0.0)))
        yield StreamEvent(
            stage="verdict", level=1, status="failed",
            detail={"class": "NONE", "reason": reason},
        )
        return

    yield StreamEvent(
        stage="ingest", level=1, status="done",
        detail={
            "duration": clip.duration,
            "windows": len(clip.windows),
            "sha256": clip.sha256,
            "candidates": len(candidate_list),
            "audio_missing": _without_audio(candidate_list),
        },
    )

    # --- level 1: fingerprint -----------------------------------------------
    yield StreamEvent(stage="fingerprint", level=1, status="running", detail={})
    env_fingerprint = await _envelope(
        "fingerprint", lambda: DETECTORS["fingerprint"].run(clip, candidate_list)
    )
    yield StreamEvent(
        stage="fingerprint", level=1, status=_STAGE_STATUS[env_fingerprint.status],
        detail=_envelope_detail(env_fingerprint, hashes=_highest(env_fingerprint, "matched_hashes")),
    )

    # --- level 1: harmony ---------------------------------------------------
    yield StreamEvent(stage="harmonic", level=1, status="running", detail={})
    env_harmonic = await _envelope(
        "harmonic", lambda: DETECTORS["harmonic"].run(clip, candidate_list)
    )
    yield StreamEvent(
        stage="harmonic", level=1, status=_STAGE_STATUS[env_harmonic.status],
        detail=_envelope_detail(env_harmonic, best_qmax=_highest(env_harmonic, "qmax_score")),
    )

    # --- level 1: the transformation grid, conditionally --------------------
    #
    # Section 7.1 starts the grid of 143 transformations only when the
    # fingerprint is silent while the harmony says "this is that track". The
    # condition needs the harmony's result, so the second fingerprint pass comes
    # AFTER it and only for the candidates that satisfy it. Without this the
    # condition would have no way to exist: the first fingerprint pass gets an
    # empty context, because the harmony does not exist yet.
    for_grid = _for_grid(candidate_list, env_fingerprint, env_harmonic)
    if for_grid:
        context = base.Context(envelopes={"harmonic": env_harmonic})
        yield StreamEvent(
            stage="fingerprint", level=1, status="running",
            detail={"phase": "transform_grid", "candidates": [c.id for c in for_grid]},
        )
        grid = await _envelope(
            "fingerprint",
            lambda: DETECTORS["fingerprint"].run(clip, for_grid, context),
        )
        env_fingerprint = _merge(env_fingerprint, grid)
        yield StreamEvent(
            stage="fingerprint", level=1, status=_STAGE_STATUS[env_fingerprint.status],
            detail=_envelope_detail(
                env_fingerprint,
                phase="transform_grid",
                hashes=_highest(env_fingerprint, "matched_hashes"),
            ),
        )

    # --- level 1: pre-filtering ---------------------------------------------
    shortlisted = await asyncio.to_thread(
        _prefilter, clip, candidate_list, env_harmonic, env_fingerprint
    )
    yield StreamEvent(
        stage="shortlist", level=1, status="done",
        detail={"from": len(candidate_list), "to": len(shortlisted), "corpus": corpus.size},
    )

    # --- level 1: commonality and fusion ------------------------------------
    envelopes_1 = {"fingerprint": env_fingerprint, "harmonic": env_harmonic}
    ranking_1 = _ranking(shortlisted, envelopes_1, corpus)
    top_1 = ranking_1[0] if ranking_1 else None
    top_commonality = (top_1.commonality if top_1 else None) or Commonality()
    yield StreamEvent(
        stage="commonality", level=1, status="done",
        detail={
            "mean_idf": top_commonality.mean_idf,
            "corpus_frequency": top_commonality.corpus_frequency,
            "corpus_size": corpus.size,
        },
    )

    store_result(_analysis_result(clip, ranking_1, 1))
    yield _verdict_event(ranking_1, 1, None)

    # --- level 2: lyrics ----------------------------------------------------
    #
    # From here on the detectors receive ONLY the shortlist. The overriding rule
    # of section 4: source separation and transcription never run over the whole
    # candidate set, because on the target hardware that simply does not add up.
    yield StreamEvent(stage="transcript", level=2, status="running", detail={})
    # Section 7.4 step 1: the separation is computed ONCE, here, by detector D,
    # and handed to detector C below. One sink per run - it is mutable and
    # belongs to this query alone.
    separation = lyrics.SeparationSink()
    env_lyrics = await _envelope(
        "lyrics",
        lambda: DETECTORS["lyrics"].run(clip, shortlisted, separation_sink=separation),
    )
    if separation.vocals is not None:
        # The sink, not the results: when the gate rejects the transcript after
        # demucs has already run - exactly the case section 7.4 exists for - the
        # envelope carries only `skipped` results with `used_separation=False`,
        # while the vocal track is right here and the melody below is about to
        # use it. We put the event before the transcript, because that was the
        # order of causes, not the order of reading.
        yield StreamEvent(
            stage="separation", level=2, status="done",
            detail={"model": "htdemucs", "stems": ["vocals", "other"]},
        )
    yield StreamEvent(
        stage="transcript", level=2, status=_STAGE_STATUS[env_lyrics.status],
        detail=_envelope_detail(
            env_lyrics,
            # The gate rejected the transcript even after separation, so the
            # next step is the melody. Section 12: `gated` with a `next` field is
            # content.
            next="melodic" if env_lyrics.status == "gated" else None,
            language=_language(env_lyrics),
            asr_confidence=_highest(env_lyrics, "asr_confidence"),
        ),
    )

    # --- level 2: melody ----------------------------------------------------
    #
    # The vocal track from detector D, when there was one. When there was not -
    # that is, when the gate passed on the first pass and demucs never ran -
    # the melody is transcribed from the full mix rather than paying 391 s to
    # separate it a second time here. That is a worse input, so the result says
    # so: `used_separation` is false on every result of such a run, and both
    # the report and the interface can read the distance in that light.
    query_vocals = (
        None
        if separation.vocals is None
        else {MelodicDetector.QUERY: separation.vocals}
    )
    yield StreamEvent(stage="melodic", level=2, status="running", detail={})
    env_melodic = await _envelope(
        "melodic",
        lambda: DETECTORS["melodic"].run(
            clip, shortlisted, separated_vocals=query_vocals
        ),
    )
    yield StreamEvent(
        stage="melodic", level=2, status=_STAGE_STATUS[env_melodic.status],
        detail=_envelope_detail(
            env_melodic,
            longest_common_run=_highest(env_melodic, "longest_common_run"),
        ),
    )

    # --- level 2: fusion again ----------------------------------------------
    envelopes_2 = {**envelopes_1, "melodic": env_melodic, "lyrics": env_lyrics}
    ranking_2 = _ranking(shortlisted, envelopes_2, corpus)
    store_result(_analysis_result(clip, ranking_2, 2))
    yield _verdict_event(ranking_2, 2, top_1)


def _language(envelope: DetectorEnvelope) -> str | None:
    if envelope.status != "ok":
        return None
    for result in envelope.results:
        language = getattr(result, "language", None)
        if language:
            return str(language)
    return None


def run_sync(
    source: str,
    candidate_set: str = "demo_01",
    emit: Callable[[StreamEvent], None] | None = None,
    *,
    candidates: Sequence[Candidate] | None = None,
) -> AnalyzeResult:
    """The same run for a caller without an event loop. Returns the final result.

    The only synchronous clients are tests and one-off runs from the command
    line; the API takes `run` without an intermediary. Events go to `emit` in the
    same order in which the SSE stream would deliver them.
    """
    emit_event = emit or (lambda _: None)
    results: list[AnalyzeResult] = []

    async def _consume() -> None:
        async for event in run(
            source, candidate_set, candidates=candidates, on_result=results.append
        ):
            emit_event(event)

    asyncio.run(_consume())
    # The run stores a result even when ingest failed, so an empty list would
    # mean the generator never reached any `store_result` - that is, a bug here
    # rather than in the material. A silent `None` would hide it from the caller.
    if not results:
        raise RuntimeError("the run produced no result at all")
    return results[-1]
