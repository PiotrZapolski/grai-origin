"""Stub mode. A complete response conforming to section 12, without computing anything.

This is not a convenience for the development period but an intermediate
product: the four teams building screens E1-E10 work exclusively on this module
until the engine stands.

**The stub writes down raw detector numbers only.** The evidentiary class, the
rights layer, the risk flags and the calibration status are **computed** from
them by the functions below, exactly from the 9.1 tree and tables 10.4 and
11.2. A hand-written class has already drifted from the tree once: a verdict of
EXCERPT_WORK with coverage 0.58 is unreachable in the tree, because rule 4
requires coverage above 0.50 and rule 5 below 0.40, and it is **the same
number**, given that detector B runs only at level 1. Computing the class
instead of writing it down eliminates that whole class of bugs.

The identity of the candidates (id, title, artist, date, licence) is a
**mirror of the manifest** `data/candidates/demo_01.json`, not an invented
list. A drift is caught by the test
`test_stub_does_not_invent_candidates`. The manifest is not read at runtime,
because the `data/` directory does not enter the API image (see
`.dockerignore`), and `candidates.load_set` looks for it relative to the
repository root - inside the container there is no such root and every request
would end in an error.

The delay between events is set by `ORIGIN_MOCK_DELAY` (seconds, 0 by default).
Tests want zero, a live demo runs at 0.4.
"""
import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from origin.api.jobs import JobStore
from origin.config import THRESHOLDS
from origin.contracts import (
    Alignment,
    AnalyzeResult,
    CalibrationInfo,
    Candidate,
    Commonality,
    DetectorEnvelope,
    DetectorStatus,
    Evidence,
    FingerprintResult,
    HarmonicResult,
    Legal,
    LyricsResult,
    MelodicResult,
    QueryInfo,
    RankingEntry,
    RightsLayer,
    StreamEvent,
    VerdictClass,
)

# Stub mode does not reach for the manifest on disk (see the module docstring),
# so it knows the sets by name. A set outside this list gets a 404, exactly as
# in real mode. Agreement with the contents of data/candidates is guarded by a
# test.
KNOWN_SETS = ("demo_01",)

CORPUS_SIZE = 4128

# Thresholds of the 9.1 tree. Everything that is in config.THRESHOLDS is taken
# from there - the stub must break together with the system rather than live a
# life of its own.
_THRESHOLD = {name: threshold.value for name, threshold in THRESHOLDS.items()}

# Two thresholds from section 9.1 that config does not name: qmax in the
# MODIFIED rule and the upper bound on coverage in the EXCERPT/work rule.
MODIFIED_QMAX = 0.50
EXCERPT_WORK_MAX_COVERAGE = 0.40

# The commonality filter threshold. In the end this is a percentile of the IDF
# distribution in the corpus (section 8, T11), which does not exist yet. The
# stub needs a single number.
COMMONALITY_IDF_THRESHOLD = 3.0

# Section 10.4: LYRICS and EXCERPT/work stay rule-based and EXPLICITLY
# uncalibrated, because the catalogue has no original-adaptation pairs and will
# not have any. COMMON and NONE have no model of their own, so they must not
# pass themselves off as calibrated either.
CALIBRATED_CLASSES: tuple[VerdictClass, ...] = (
    "EXACT", "MODIFIED", "VERSION", "EXCERPT_PHONOGRAM",
)

# Section 11.3 knows exactly two risk flags and both are in English.
FLAG_RECOGNIZABLE_EXCERPT = "recognizable_excerpt"
FLAG_POSSIBLE_PASTICHE = "possible_pastiche"


def delay_s() -> float:
    try:
        return float(os.environ.get("ORIGIN_MOCK_DELAY", "0"))
    except ValueError:
        return 0.0


async def _pause() -> None:
    seconds = delay_s()
    if seconds > 0:
        await asyncio.sleep(seconds)


# --------------------------------------------------------------------------
# Candidates: a mirror of the demo_01 manifest, not an invented list
# --------------------------------------------------------------------------

def _candidate(**fields: Any) -> Candidate:
    return Candidate(**fields)


CANDIDATES: dict[str, Candidate] = {
    "cand_01": _candidate(
        id="cand_01", name="Kashmir", artist="Led Zeppelin",
        shs_performance_id="18", source_url="https://youtube.com/watch?v=gEYqSorzOZs",
        audio_path="data/audio/cand_01.wav", published="1975-02-24", published_source="manual",
        license="all_rights_reserved", instrumental=False, language="en",
    ),
    "cand_02": _candidate(
        id="cand_02", name="Come with Me", artist="Puff Daddy and Jimmy Page",
        shs_performance_id="19", source_url="https://youtube.com/watch?v=vrSyrOaoAug",
        audio_path="data/audio/cand_02.wav", published="1998-05-18", published_source="manual",
        license="all_rights_reserved", instrumental=False, language="en",
    ),
    "cand_03": _candidate(
        id="cand_03", name="Hurt", artist="Nine Inch Nails",
        shs_performance_id="8968", source_url="https://youtube.com/watch?v=g0bZtf5MCzY",
        audio_path="data/audio/cand_03.wav", published="1994-03-08", published_source="manual",
        license="all_rights_reserved", instrumental=False, language="en",
    ),
    "cand_04": _candidate(
        id="cand_04", name="Hurt", artist="Johnny Cash",
        shs_performance_id="8969", source_url="https://youtube.com/watch?v=8AHCfZTRGiI",
        audio_path="data/audio/cand_04.wav", published="2002-11-05", published_source="manual",
        license="all_rights_reserved", instrumental=False, language="en",
    ),
    "cand_05": _candidate(
        id="cand_05", name="34 Ghosts IV", artist="Nine Inch Nails",
        shs_performance_id="840836", source_url="https://youtube.com/watch?v=XF_ceFugJjQ",
        audio_path="data/audio/cand_05.wav", published="2008-03-02", published_source="manual",
        license="cc-by-nc-sa-3.0", instrumental=True, language=None,
    ),
    "cand_06": _candidate(
        id="cand_06", name="Old Town Road", artist="Lil Nas X",
        shs_performance_id="840842", source_url="https://youtube.com/watch?v=9YpvNgCSaCU",
        audio_path="data/audio/cand_06.wav", published="2018-12-03", published_source="manual",
        license="all_rights_reserved", instrumental=False, language="en",
    ),
    "cand_07": _candidate(
        id="cand_07", name="Let It Be", artist="The Beatles",
        shs_performance_id="1894", source_url="https://youtube.com/watch?v=CGj85pVzRJs",
        audio_path="data/audio/cand_07.wav", published="1970-03-06", published_source="manual",
        license="all_rights_reserved", instrumental=False, language="en",
    ),
    "cand_08": _candidate(
        id="cand_08", name="No Woman, No Cry", artist="Bob Marley & The Wailers",
        shs_performance_id="4273", source_url="https://youtube.com/watch?v=j-ehW_9BsDc",
        audio_path="data/audio/cand_08.wav", published=None, published_source=None,
        license="all_rights_reserved", instrumental=False, language="en",
    ),
    "cand_09": _candidate(
        id="cand_09", name="Hurt", artist="2Cellos",
        shs_performance_id="170894", source_url="https://youtube.com/watch?v=ozNEdMcWZvQ",
        audio_path="data/audio/cand_09.wav", published=None, published_source=None,
        license="all_rights_reserved", instrumental=True, language=None,
    ),
    "cand_10": _candidate(
        id="cand_10", name="Code Monkey", artist="Jonathan Coulton",
        shs_performance_id="1658394", source_url="https://youtube.com/watch?v=6J-W3mn9N2w",
        audio_path="data/audio/cand_10.wav", published=None, published_source=None,
        license="cc-by-nc-3.0", instrumental=False, language="en",
    ),
}


def candidates() -> dict[str, Candidate]:
    """The stub catalogue as a dictionary. Used by the candidate audio endpoint of E4."""
    return dict(CANDIDATES)


def query_audio_path(set_id: str) -> str:
    """Where stub mode looks for the input material for screen E4.

    The stub downloads nothing, so the query has audio only when someone has
    placed that file in `data/audio/`. A missing file is a valid state:
    `waveform_url` then stays `null` and the screen says outright that the
    waveform does not come from a measurement. We do not generate substitute
    audio.
    """
    return f"data/audio/query_{set_id}.wav"


# --------------------------------------------------------------------------
# Raw detector numbers for one candidate
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Match:
    """Everything the detectors measured for one candidate. No class at all.

    The evidentiary class, the rights layer, the flags and the calibration
    status are computed from this rather than written down - see the module
    docstring.
    """

    candidate_id: str

    # Detector A, acoustic fingerprint. Level 1.
    matched_hashes: int = 0
    peak_ratio: float = 0.0
    query_span: tuple[float, float] | None = None
    candidate_span: tuple[float, float] | None = None
    offset: float | None = None
    repetitions: int = 0
    transform: dict[str, float] | None = None

    # Detector B, harmony. Level 1.
    qmax: float = 0.0
    coverage: float = 0.0
    transposition: int = 0
    tempo_ratio: float = 1.0
    chord_sequence: tuple[str, ...] = ()
    alignment_path: tuple[tuple[int, int], ...] = ()

    # Detector D, lyrics. Level 2.
    lyrics_status: DetectorStatus = "ok"
    lyrics_reason: str | None = None
    jaccard: float | None = None
    semantic_sim: float | None = None
    matched_spans: tuple[dict[str, Any], ...] = ()

    # Detector C, melody. Level 2.
    melodic_status: DetectorStatus = "ok"
    melodic_reason: str | None = None
    longest_common_run: int = 0
    ms_distance: float | None = None
    matched_ngrams: tuple[dict[str, Any], ...] = ()

    # The commonality filter, section 8.
    mean_idf: float = 0.0
    corpus_frequency: int = 0

    # The scores from 11.2, meaningful only for the EXCERPT classes.
    recognizability: float | None = None
    modification: float | None = None

    # Probability after level 1 and after level 2.
    probability_l1: float = 0.0
    probability_l2: float = 0.0

    @property
    def span_length(self) -> float:
        if self.query_span is None:
            return 0.0
        return self.query_span[1] - self.query_span[0]

    def candidate(self) -> Candidate:
        return CANDIDATES[self.candidate_id]

    def probability(self, level: int) -> float:
        return self.probability_l1 if level == 1 else self.probability_l2


@dataclass(frozen=True)
class Scenario:
    """One query and everything the stub says about it."""

    key: str
    description: str
    duration: float
    windows: int
    sha256: str
    hashes: int
    shortlist_from: int
    language: str
    transcript_words: int
    asr_confidence_at_gate: float
    asr_confidence_after_separation: float
    transcript: tuple[dict[str, Any], ...]
    matches: tuple[Match, ...]
    candidate_set: str = "demo_01"
    # Words recognised in the query address. Screen E1 has three example
    # buttons and has to be able to ask for a specific case from section 14.
    keywords: tuple[str, ...] = ()
    # The confidence gate from 7.3. A query without vocals does not go to
    # separation but straight to the melody detector - that is a different
    # decision, not the same failure.
    gate_reason: str = "asr_confidence"
    separation: bool = True

    def ranked(self, level: int) -> list[Match]:
        """The ranking descends by probability; a tie is settled by the identifier."""
        return sorted(self.matches,
                      key=lambda m: (-m.probability(level), m.candidate_id))


# --------------------------------------------------------------------------
# The decision tree of section 9.1. The first rule satisfied wins.
# --------------------------------------------------------------------------

def verdict_class_for(m: Match, level: int) -> VerdictClass:
    """The class for this candidate at this execution level.

    At level 1 detectors C and D did not run. That is neither their failure nor
    a zero: there simply is no result yet, so `D.status != "ok"` in rule 4 is
    true. That is exactly why the specification put that clause there
    (section 9.1).
    """
    if m.peak_ratio > _THRESHOLD["EXACT_PEAK_RATIO"] and m.span_length > _THRESHOLD["EXACT_MIN_SPAN_S"]:
        return "EXACT"
    if (m.transform is not None
            and m.peak_ratio > _THRESHOLD["MODIFIED_PEAK_RATIO"]
            and m.qmax > MODIFIED_QMAX):
        return "MODIFIED"
    if (m.peak_ratio > _THRESHOLD["EXCERPT_PEAK_RATIO"]
            and m.span_length < _THRESHOLD["EXACT_MIN_SPAN_S"]
            and m.repetitions >= _THRESHOLD["EXCERPT_MIN_REPETITIONS"]):
        return "EXCERPT_PHONOGRAM"

    lyrics_status = m.lyrics_status if level == 2 else None
    semantic = m.semantic_sim if level == 2 else None
    if (m.peak_ratio < _THRESHOLD["VERSION_MAX_PEAK_RATIO"]
            and m.qmax > _THRESHOLD["VERSION_QMAX"]
            and m.coverage > _THRESHOLD["VERSION_COVERAGE"]
            and ((semantic is not None and semantic > 0.70) or lyrics_status != "ok")):
        return _after_commonality_filter("VERSION", m)

    if (level == 2
            and m.melodic_status == "ok"
            and m.longest_common_run >= _THRESHOLD["EXCERPT_WORK_MIN_RUN"]
            and m.coverage < EXCERPT_WORK_MAX_COVERAGE):
        return _after_commonality_filter("EXCERPT_WORK", m)

    if (level == 2
            and m.qmax < _THRESHOLD["LYRICS_MAX_QMAX"]
            and m.lyrics_status == "ok"
            and (m.jaccard or 0.0) > _THRESHOLD["LYRICS_JACCARD"]):
        return _after_commonality_filter("LYRICS", m)

    return "NONE"


def _after_commonality_filter(verdict_class: VerdictClass, m: Match) -> VerdictClass:
    """Section 9.1: degradation concerns ONLY three classes.

    NONE cannot be degraded to COMMON, so the trap from demo case 5 has to win
    some rule first. A weak match with a low IDF is still NONE.
    """
    if verdict_class in ("VERSION", "LYRICS", "EXCERPT_WORK") and m.mean_idf < COMMONALITY_IDF_THRESHOLD:
        return "COMMON"
    return verdict_class


# --------------------------------------------------------------------------
# Rights layers, calibration and flags - also computed, not written down
# --------------------------------------------------------------------------

def leading_layer(verdict_class: VerdictClass) -> RightsLayer | None:
    """Section 11.1: one label next to the class badge. COMMON and NONE have none."""
    if verdict_class in ("EXACT", "MODIFIED", "EXCERPT_PHONOGRAM"):
        return "phonogram"
    if verdict_class in ("VERSION", "EXCERPT_WORK", "LYRICS"):
        return "work"
    return None


def rights_layers(verdict_class: VerdictClass) -> list[RightsLayer]:
    """The full set of layers for the legal panel. VERSION touches the work and the performance at once."""
    if verdict_class in ("EXACT", "MODIFIED", "EXCERPT_PHONOGRAM"):
        return ["phonogram"]
    if verdict_class == "VERSION":
        return ["work", "performance"]
    if verdict_class in ("EXCERPT_WORK", "LYRICS"):
        return ["work"]
    return []


def probability_status(verdict_class: VerdictClass, level: int) -> str:
    """Sections 10.4 and 10.5. Level 1 has no model, so it has no calibration.

    The number from level 1 comes from the decision tree, not from a model, and
    the classes LYRICS, EXCERPT/work, COMMON and NONE have no model at all and
    will not have one, because the catalogue has no training pairs for them.
    """
    if level == 1:
        return "uncalibrated"
    return "calibrated" if verdict_class in CALIBRATED_CLASSES else "uncalibrated"


def _is_open_license(candidate: Candidate) -> bool:
    return candidate.license.startswith(("cc", "public_domain"))


def risk_flags(verdict_class: VerdictClass, m: Match) -> list[str]:
    """Table 11.2. Four rows out of five say "no flag" and that is not a mistake.

    A flag is an exceptional signal, not an ornament attached to every result: a
    common element, inspiration and a candidate under an open licence get none.
    """
    candidate = m.candidate()
    if _is_open_license(candidate):
        return []
    if verdict_class not in ("EXCERPT_PHONOGRAM", "EXCERPT_WORK"):
        return []
    flags: list[str] = []
    if (m.recognizability or 0.0) >= 0.50:
        flags.append(FLAG_RECOGNIZABLE_EXCERPT)
    # "High modification with recognisability preserved is a borderline
    # situation and is to be flagged as such" - section 11.2, the paragraph on
    # the modification score.
    if (m.modification or 0.0) >= 0.40 and (m.recognizability or 0.0) >= 0.70:
        flags.append(FLAG_POSSIBLE_PASTICHE)
    return flags


def _license_name(identifier: str) -> str:
    """`cc-by-nc-sa-3.0` -> `CC BY-NC-SA 3.0`. The text is meant for the user's clipboard."""
    parts = identifier.split("-")
    if parts and parts[-1][:1].isdigit():
        version = f" {parts[-1]}"
        parts = parts[:-1]
    else:
        version = ""
    if len(parts) > 1:
        return f"{parts[0].upper()} {'-'.join(p.upper() for p in parts[1:])}{version}"
    return f"{identifier.upper()}{version}"


def attribution(candidate: Candidate) -> str | None:
    """Section 11.2: with an open licence the system generates a ready-made text."""
    if not _is_open_license(candidate):
        return None
    return f"{candidate.artist}, \"{candidate.name}\", {_license_name(candidate.license)}"


def legal_block(verdict_class: VerdictClass, m: Match) -> Legal:
    candidate = m.candidate()
    # The recognisability and modification scores are derived from A.peak_ratio
    # for the EXCERPT class (11.2). For other classes they mean nothing and stay
    # empty.
    excerpt = verdict_class in ("EXCERPT_PHONOGRAM", "EXCERPT_WORK")
    return Legal(
        rights_layer=rights_layers(verdict_class),
        risk_flags=risk_flags(verdict_class, m),
        recognizability=m.recognizability if excerpt else None,
        modification=m.modification if excerpt else None,
        license_status=candidate.license,
        required_attribution=attribution(candidate),
    )


# --------------------------------------------------------------------------
# Detector envelopes. Section 7.0.
# --------------------------------------------------------------------------

def fingerprint_envelope(s: Scenario) -> DetectorEnvelope:
    return DetectorEnvelope(
        detector="fingerprint",
        status="ok",
        results=[
            FingerprintResult(
                candidate_id=m.candidate_id,
                matched_hashes=m.matched_hashes,
                peak_ratio=m.peak_ratio,
                query_span=m.query_span,
                candidate_span=m.candidate_span,
                offset=m.offset,
                repetitions=m.repetitions,
                transform=m.transform,
            )
            for m in s.matches
        ],
    )


def harmonic_envelope(s: Scenario) -> DetectorEnvelope:
    return DetectorEnvelope(
        detector="harmonic",
        status="ok",
        results=[
            HarmonicResult(
                candidate_id=m.candidate_id,
                qmax_score=m.qmax,
                transposition=m.transposition,
                tempo_ratio=m.tempo_ratio,
                coverage=m.coverage,
                alignment_path=[list(pair) for pair in m.alignment_path],
                chord_sequence=list(m.chord_sequence),
            )
            for m in s.matches
        ],
    )


def lyrics_envelope_before_gate(s: Scenario) -> DetectorEnvelope:
    """The envelope at the moment the confidence gate rejected the transcript.

    A `gated` status on the envelope means the whole detector run was not
    computed, so **no** result may carry a number - the validator from the
    contracts enforces that. The bar "rejected by the confidence gate" on
    screen E5 stands on exactly this envelope.
    """
    return DetectorEnvelope(
        detector="lyrics",
        status="gated",
        reason="asr_confidence",
        results=[
            LyricsResult(candidate_id=m.candidate_id, status="gated",
                         reason="asr_confidence")
            for m in s.matches
        ],
    )


def lyrics_envelope(s: Scenario) -> DetectorEnvelope:
    """After source separation. The transcript passed the gate on the second attempt."""
    return DetectorEnvelope(
        detector="lyrics",
        status="ok",
        reason="the transcript was accepted only after source separation",
        results=[
            LyricsResult(
                candidate_id=m.candidate_id,
                status=m.lyrics_status,
                reason=m.lyrics_reason,
                jaccard=m.jaccard if m.lyrics_status == "ok" else None,
                semantic_sim=m.semantic_sim if m.lyrics_status == "ok" else None,
                matched_spans=[dict(x) for x in m.matched_spans]
                if m.lyrics_status == "ok" else [],
                asr_confidence=s.asr_confidence_after_separation
                if m.lyrics_status == "ok" else None,
                language=s.language if m.lyrics_status == "ok" else None,
                used_separation=m.lyrics_status == "ok",
            )
            for m in s.matches
        ],
    )


def melodic_envelope(s: Scenario) -> DetectorEnvelope:
    return DetectorEnvelope(
        detector="melodic",
        status="ok",
        results=[
            MelodicResult(
                candidate_id=m.candidate_id,
                status=m.melodic_status,
                reason=m.melodic_reason,
                matched_ngrams=[dict(x) for x in m.matched_ngrams]
                if m.melodic_status == "ok" else [],
                longest_common_run=m.longest_common_run if m.melodic_status == "ok" else 0,
                ms_distance=m.ms_distance if m.melodic_status == "ok" else None,
            )
            for m in s.matches
        ],
    )


# --------------------------------------------------------------------------
# The analysis result for a given level
# --------------------------------------------------------------------------

def _evidence(m: Match, level: int) -> dict[str, Evidence]:
    """Level 1 knows two detectors.

    A missing key means "not computed yet" and the frontend has to show that as
    waiting. Putting a zero here would mean "checked and there is no
    similarity", that is a lie in an evidentiary tool (section 7.0).
    """
    evidence = {"fingerprint": Evidence(status="ok"), "harmonic": Evidence(status="ok")}
    if level == 2:
        evidence["melodic"] = Evidence(status=m.melodic_status, reason=m.melodic_reason)
        evidence["lyrics"] = Evidence(status=m.lyrics_status, reason=m.lyrics_reason)
    return evidence


def _alignment(m: Match) -> Alignment | None:
    """A match based on lyrics alone has no time alignment."""
    if m.query_span is None and m.qmax < _THRESHOLD["LYRICS_MAX_QMAX"]:
        return None
    return Alignment(
        query_span=m.query_span,
        candidate_span=m.candidate_span,
        transposition=m.transposition,
        tempo_ratio=m.tempo_ratio,
    )


def ranking_entry(m: Match, rank: int, level: int) -> RankingEntry:
    verdict_class = verdict_class_for(m, level)
    return RankingEntry(
        rank=rank,
        candidate=m.candidate(),
        verdict_class=verdict_class,
        verdict_layer=leading_layer(verdict_class),
        probability=m.probability(level),
        probability_status=probability_status(verdict_class, level),
        evidence=_evidence(m, level),
        alignment=_alignment(m),
        commonality=Commonality(mean_idf=m.mean_idf, corpus_frequency=m.corpus_frequency,
                                corpus_size=CORPUS_SIZE),
        legal=legal_block(verdict_class, m),
    )


def result(s: Scenario, level: int) -> AnalyzeResult:
    """The result after level 1 (partial) or after level 2 (final)."""
    return AnalyzeResult(
        status="partial" if level == 1 else "final",
        completed_levels=[1] if level == 1 else [1, 2],
        query=QueryInfo(
            duration=s.duration,
            waveform_url=None,
            transcript=[dict(x) for x in s.transcript] if level == 2 else [],
        ),
        # Calibration does not exist at level 1: the number comes from the
        # decision tree, not from a model. Section 10.5 requires the UI to tell
        # that apart visually.
        calibration=None if level == 1 else CalibrationInfo(
            model_version="lr_v3", trained_on=500, precision_at_threshold=0.95),
        ranking=[ranking_entry(m, i, level)
                 for i, m in enumerate(s.ranked(level), start=1)],
    )


def partial_result(s: "Scenario | None" = None) -> AnalyzeResult:
    return result(s or DEFAULT_SCENARIO, 1)


def final_result(s: "Scenario | None" = None) -> AnalyzeResult:
    return result(s or DEFAULT_SCENARIO, 2)


# --------------------------------------------------------------------------
# The stream run
# --------------------------------------------------------------------------

def _verdict(s: Scenario, level: int) -> StreamEvent:
    """The verdict always carries the ranking leader at that level, never a written-down number."""
    top = s.ranked(level)[0]
    verdict_class = verdict_class_for(top, level)
    detail: dict[str, Any] = {
        "class": verdict_class,
        "probability": top.probability(level),
        "probability_status": probability_status(verdict_class, level),
        "candidate_id": top.candidate_id,
    }
    if level == 2:
        # The frontend animates the upgrade of the verdict, so it has to know
        # what it came from.
        previous = s.ranked(1)[0]
        detail["previous_class"] = verdict_class_for(previous, 1)
        detail["previous_probability"] = previous.probability(1)
    return StreamEvent(stage="verdict", level=level,
                       status="partial" if level == 1 else "final", detail=detail)


def level_1_events(s: Scenario) -> list[StreamEvent]:
    top = s.ranked(1)[0]
    return [
        StreamEvent(stage="ingest", level=1, status="done",
                    detail={"duration": s.duration, "windows": s.windows,
                            "sha256": s.sha256}),
        StreamEvent(stage="fingerprint", level=1, status="running", detail={}),
        StreamEvent(stage="fingerprint", level=1, status="done",
                    detail={"hashes": s.hashes,
                            "envelope": fingerprint_envelope(s).model_dump(mode="json")}),
        StreamEvent(stage="harmonic", level=1, status="running", detail={}),
        StreamEvent(stage="harmonic", level=1, status="done",
                    detail={"best_qmax": max(m.qmax for m in s.matches),
                            "envelope": harmonic_envelope(s).model_dump(mode="json")}),
        StreamEvent(stage="shortlist", level=1, status="done",
                    detail={"from": s.shortlist_from, "to": len(s.matches),
                            "corpus": CORPUS_SIZE}),
        StreamEvent(stage="commonality", level=1, status="done",
                    detail={"mean_idf": top.mean_idf,
                            "corpus_frequency": top.corpus_frequency,
                            "corpus_size": CORPUS_SIZE}),
        _verdict(s, 1),
    ]


def level_2_events(s: Scenario) -> list[StreamEvent]:
    # This is not a failure. The confidence gate rejected the transcript and
    # points at the next step itself - screen E2 shows it as the moment where
    # the system judges its own confidence. For a query without vocals the next
    # step is not separation but the melody straight away: separating silence
    # would achieve nothing.
    gate = StreamEvent(
        stage="transcript", level=2, status="gated",
        detail={"reason": s.gate_reason,
                "next": "separation" if s.separation else "melodic",
                "asr_confidence": s.asr_confidence_at_gate,
                "threshold": 0.5,
                "envelope": lyrics_envelope_before_gate(s).model_dump(mode="json")})
    after_gate: list[StreamEvent] = []
    if s.separation:
        after_gate = [
            StreamEvent(stage="separation", level=2, status="running",
                        detail={"model": "htdemucs", "stems": ["vocals", "other"]}),
            StreamEvent(stage="separation", level=2, status="done",
                        detail={"seconds": 12.8}),
            StreamEvent(stage="transcript", level=2, status="done",
                        detail={"words": s.transcript_words, "lang": s.language,
                                "asr_confidence": s.asr_confidence_after_separation,
                                "used_separation": True,
                                "envelope": lyrics_envelope(s).model_dump(mode="json")}),
        ]
    return [
        gate,
        *after_gate,
        StreamEvent(stage="melodic", level=2, status="running", detail={}),
        StreamEvent(stage="melodic", level=2, status="done",
                    detail={"longest_common_run": max(m.longest_common_run
                                                      for m in s.matches),
                            "envelope": melodic_envelope(s).model_dump(mode="json")}),
        _verdict(s, 2),
    ]


async def run(store: JobStore, job_id: str,
              s: "Scenario | None" = None) -> AsyncIterator[StreamEvent]:
    """The whole stub run: level 1, the partial verdict, level 2, the final verdict.

    The final result lands in the store **before** the final verdict is
    emitted, so that a frontend which fetches `/result` immediately on that
    event does not still get the partial version.
    """
    s = s or DEFAULT_SCENARIO
    for event in level_1_events(s):
        await _pause()
        yield event
    for event in level_2_events(s)[:-1]:
        await _pause()
        yield event
    store.set_result(job_id, final_result(s))
    await _pause()
    yield level_2_events(s)[-1]


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------

SCENARIO_COVER = Scenario(
    key="cover",
    keywords=("cover", "version", "hurt"),
    description="An amateur upload: a cover of Hurt with a looped sample and a shared progression.",
    duration=184.2,
    windows=37,
    sha256="9f2c1d7a4b8e0c35d6a1f47b2e9c8305a7d41f6b0c2e93d85a1b7f4c6d093e21",
    hashes=4812,
    shortlist_from=10,
    language="en",
    transcript_words=47,
    asr_confidence_at_gate=0.31,
    asr_confidence_after_separation=0.78,
    transcript=(
        {"word": "i", "start": 12.4, "end": 12.6},
        {"word": "hurt", "start": 12.6, "end": 13.0},
        {"word": "myself", "start": 13.0, "end": 13.6},
        {"word": "today", "start": 13.6, "end": 14.2},
        {"word": "to", "start": 14.4, "end": 14.6},
        {"word": "see", "start": 14.6, "end": 14.9},
        {"word": "if", "start": 14.9, "end": 15.1},
        {"word": "i", "start": 15.1, "end": 15.3},
        {"word": "still", "start": 15.3, "end": 15.8},
        {"word": "feel", "start": 15.8, "end": 16.4},
    ),
    matches=(
        # The source track. A different recording, the same composition: weak
        # fingerprint, strong harmony, the same lyrics. Rule 4 -> VERSION at
        # both levels.
        Match(
            candidate_id="cand_03",
            matched_hashes=341, peak_ratio=0.31,
            query_span=(12.4, 31.8), candidate_span=(64.1, 83.5), offset=51.7,
            repetitions=1, transform={"tempo": 1.06, "pitch": 2.0},
            qmax=0.63, coverage=0.58, transposition=2, tempo_ratio=1.06,
            chord_sequence=("Am", "F", "C", "G", "Am", "F", "C", "G"),
            alignment_path=((0, 0), (1, 1), (2, 3), (3, 4), (4, 6), (5, 7)),
            jaccard=0.66, semantic_sim=0.74,
            matched_spans=({"query": [12.4, 16.4], "candidate": [64.1, 68.2],
                            "text": "i hurt myself today to see if i still feel"},),
            longest_common_run=11, ms_distance=0.18,
            matched_ngrams=({"query_start": 14.1, "candidate_start": 65.8, "n": 5,
                             "intervals": [2, 2, -3, 5, -2]},
                            {"query_start": 22.6, "candidate_start": 74.3, "n": 6,
                             "intervals": [0, 2, 2, -4, -1, 3]}),
            mean_idf=8.4, corpus_frequency=3,
            probability_l1=0.71, probability_l2=0.94,
        ),
        # A looped, filtered sample. Rule 3 -> EXCERPT/phonogram, and this is
        # the only place in the stub where the recognisability and modification
        # scores mean anything.
        Match(
            candidate_id="cand_01",
            matched_hashes=512, peak_ratio=0.46,
            query_span=(96.4, 105.6), candidate_span=(140.2, 149.4), offset=43.8,
            repetitions=3, transform={"tempo": 1.0, "pitch": 0.0, "lowpass_hz": 3200.0},
            qmax=0.29, coverage=0.14, transposition=0, tempo_ratio=1.0,
            chord_sequence=("D", "D", "C", "D"),
            jaccard=0.04, semantic_sim=0.09,
            longest_common_run=2, ms_distance=0.71,
            mean_idf=9.6, corpus_frequency=2,
            recognizability=0.78, modification=0.41,
            probability_l1=0.66, probability_l2=0.66,
        ),
        # The same composition as cand_03 but a different arrangement: the
        # harmony does not match, the lyrics do. NONE at level 1, LYRICS after
        # level 2 - the only route the tree can really produce, and explicitly
        # uncalibrated.
        Match(
            candidate_id="cand_04",
            matched_hashes=18, peak_ratio=0.05,
            qmax=0.38, coverage=0.31, transposition=-2, tempo_ratio=0.94,
            chord_sequence=("Am", "F", "C", "G"),
            jaccard=0.62, semantic_sim=0.81,
            matched_spans=({"query": [12.4, 16.4], "candidate": [8.9, 13.1],
                            "text": "i hurt myself today"},),
            longest_common_run=4, ms_distance=0.55,
            matched_ngrams=({"query_start": 12.4, "candidate_start": 8.9, "n": 4,
                             "intervals": [2, -2, 1, 0]},),
            mean_idf=7.2, corpus_frequency=6,
            probability_l1=0.12, probability_l2=0.58,
        ),
        # The trap from demo case 5. The harmony is STRONG, above the VERSION
        # threshold - without that there is nothing to degrade and the trap
        # would be an ordinary weak match. Only mean_idf 2.1 turns VERSION into
        # COMMON. An instrumental, so detector D has nothing to compare at any
        # level.
        Match(
            candidate_id="cand_05",
            matched_hashes=47, peak_ratio=0.08,
            qmax=0.60, coverage=0.55, transposition=-3, tempo_ratio=0.98,
            chord_sequence=("Am", "F", "C", "G"),
            alignment_path=((0, 0), (1, 1), (2, 2), (3, 3)),
            lyrics_status="not_applicable", lyrics_reason="instrumental candidate",
            melodic_status="failed",
            melodic_reason="note extraction returned no track at all",
            mean_idf=2.1, corpus_frequency=1877,
            probability_l1=0.35, probability_l2=0.35,
        ),
    ),
)



# Case 1 from section 14: a clean reupload with recompression. It builds trust,
# so it stands first in the walkthrough. Rule 1 needs detector A alone, so the
# class is ready already at level 1 and level 2 only raises the confidence.
SCENARIO_REUPLOAD = Scenario(
    key="exact",
    keywords=("exact", "reupload", "old-town", "oldtown"),
    description="A reupload with recompression: the same recording plus a sample under an open licence.",
    duration=113.5,
    windows=22,
    sha256="3b71e0c95af24d18e7c6b0a2f4d38915c0e7a6b3d29f1428c5e0a7b6d3f91c02",
    hashes=6104,
    shortlist_from=10,
    language="en",
    transcript_words=61,
    asr_confidence_at_gate=0.42,
    asr_confidence_after_separation=0.86,
    transcript=(
        {"word": "yeah", "start": 4.1, "end": 4.4},
        {"word": "im", "start": 4.4, "end": 4.6},
        {"word": "gonna", "start": 4.6, "end": 4.9},
        {"word": "take", "start": 4.9, "end": 5.2},
        {"word": "my", "start": 5.2, "end": 5.4},
        {"word": "horse", "start": 5.4, "end": 5.9},
    ),
    matches=(
        # The same recording, only put through recompression. The fingerprint
        # matches over the whole length, so rule 1 wins before anything else.
        Match(
            candidate_id="cand_06",
            matched_hashes=5218, peak_ratio=0.87,
            query_span=(0.0, 112.8), candidate_span=(0.0, 112.8), offset=0.0,
            repetitions=1,
            qmax=0.94, coverage=0.97, transposition=0, tempo_ratio=1.0,
            chord_sequence=("Bm", "D", "A", "G"),
            alignment_path=((0, 0), (1, 1), (2, 2), (3, 3), (4, 4)),
            jaccard=0.97, semantic_sim=0.99,
            matched_spans=({"query": [4.1, 5.9], "candidate": [4.1, 5.9],
                            "text": "yeah im gonna take my horse"},),
            longest_common_run=14, ms_distance=0.03,
            matched_ngrams=({"query_start": 4.1, "candidate_start": 4.1, "n": 7,
                             "intervals": [0, 2, 2, -2, -3, 5, -2]},),
            mean_idf=9.1, corpus_frequency=1,
            probability_l1=0.92, probability_l2=0.98,
        ),
        # The sample used in this recording. An open licence, so instead of a
        # risk flag the system generates a ready-made attribution (table 11.2,
        # case 6).
        Match(
            candidate_id="cand_05",
            matched_hashes=488, peak_ratio=0.44,
            query_span=(5.2, 13.6), candidate_span=(0.8, 9.2), offset=-4.4,
            repetitions=6, transform={"tempo": 1.0, "pitch": 0.0},
            qmax=0.31, coverage=0.19, transposition=0, tempo_ratio=1.0,
            chord_sequence=("Bm", "D", "A", "G"),
            lyrics_status="not_applicable", lyrics_reason="instrumental candidate",
            longest_common_run=6, ms_distance=0.34,
            matched_ngrams=({"query_start": 5.2, "candidate_start": 0.8, "n": 6,
                             "intervals": [0, 2, 2, -2, -3, 5]},),
            mean_idf=6.1, corpus_frequency=9,
            recognizability=0.69, modification=0.12,
            probability_l1=0.68, probability_l2=0.72,
        ),
    ),
)


# Case 3 from section 14: a version sped up and raised by a semitone, that is
# the classic Content ID workaround. The rights layer is the PHONOGRAM, because
# a specific recording was modified, not the composition - next to it stands a
# cover of the same composition, which touches the WORK layer. That pair is the
# whole of section 11.1.
SCENARIO_MODIFIED = Scenario(
    key="modified",
    keywords=("modified", "speedup", "pitch"),
    description="A recording sped up by 6 percent and raised by a semitone.",
    duration=168.4,
    windows=34,
    sha256="7c1d94ba30e5f28d61a4c07b95e3d182f60a4c7b9d2e5108a3b6c9d0e4f27315",
    hashes=5203,
    shortlist_from=10,
    language="en",
    transcript_words=52,
    asr_confidence_at_gate=0.37,
    asr_confidence_after_separation=0.81,
    transcript=(
        {"word": "i", "start": 11.7, "end": 11.9},
        {"word": "hurt", "start": 11.9, "end": 12.3},
        {"word": "myself", "start": 12.3, "end": 12.8},
        {"word": "today", "start": 12.8, "end": 13.4},
    ),
    matches=(
        # The fingerprint matches strongly, but only once the transformation
        # has been found: rule 2 requires a transformation, a high peak_ratio
        # and confirmation from the harmony all at once.
        Match(
            candidate_id="cand_03",
            matched_hashes=2874, peak_ratio=0.57,
            query_span=(0.0, 158.9), candidate_span=(0.0, 168.4), offset=0.0,
            repetitions=1, transform={"tempo": 1.06, "pitch": 1.0},
            qmax=0.72, coverage=0.81, transposition=1, tempo_ratio=1.06,
            chord_sequence=("Am", "F", "C", "G", "Am", "F", "C", "G"),
            alignment_path=((0, 0), (1, 1), (2, 2), (3, 4), (4, 5)),
            jaccard=0.88, semantic_sim=0.93,
            matched_spans=({"query": [11.7, 13.4], "candidate": [12.4, 14.2],
                            "text": "i hurt myself today"},),
            longest_common_run=13, ms_distance=0.09,
            matched_ngrams=({"query_start": 11.7, "candidate_start": 12.4, "n": 6,
                             "intervals": [2, 2, -3, 5, -2, 0]},),
            mean_idf=8.4, corpus_frequency=3,
            probability_l1=0.79, probability_l2=0.93,
        ),
        # The same composition in an instrumental arrangement. The fingerprint
        # does not match at all, the harmony does - the WORK layer next to the
        # PHONOGRAM layer above.
        Match(
            candidate_id="cand_09",
            matched_hashes=34, peak_ratio=0.06,
            qmax=0.61, coverage=0.56, transposition=-1, tempo_ratio=0.99,
            chord_sequence=("Am", "F", "C", "G"),
            alignment_path=((0, 0), (1, 1), (2, 2), (3, 3)),
            lyrics_status="not_applicable", lyrics_reason="instrumental candidate",
            longest_common_run=9, ms_distance=0.26,
            matched_ngrams=({"query_start": 30.2, "candidate_start": 28.9, "n": 5,
                             "intervals": [2, 2, -3, 5, -2]},),
            mean_idf=7.8, corpus_frequency=5,
            probability_l1=0.55, probability_l2=0.64,
        ),
        # The same composition in a third arrangement. The harmony covers only
        # a piece, but the melody holds for nine notes, so rule 5 says A
        # FRAGMENT OF THE COMPOSITION. The longest_common_run threshold is
        # entered by hand and there is no calibration data (10.4), so the
        # probability stays explicitly uncalibrated.
        Match(
            candidate_id="cand_04",
            matched_hashes=22, peak_ratio=0.05,
            qmax=0.36, coverage=0.29, transposition=-3, tempo_ratio=0.93,
            chord_sequence=("Am", "F", "C", "G"),
            jaccard=0.71, semantic_sim=0.84,
            matched_spans=({"query": [11.7, 13.4], "candidate": [8.9, 10.8],
                            "text": "i hurt myself today"},),
            longest_common_run=9, ms_distance=0.31,
            matched_ngrams=({"query_start": 11.7, "candidate_start": 8.9, "n": 9,
                             "intervals": [2, 2, -3, 5, -2, 0, 2, -2, 1]},),
            mean_idf=7.2, corpus_frequency=6,
            probability_l1=0.12, probability_l2=0.44,
        ),
    ),
)


# Case 4 from section 14: a looped and filtered sample. This is where the
# phonogram layer and the recognisability score live, because taking even a
# very short sample may infringe the producer's right (11.2).
SCENARIO_SAMPLE = Scenario(
    key="sample",
    keywords=("sample", "excerpt", "kashmir", "loop"),
    description="A riff taken in a loop: the source phonogram and a second track with the same sample.",
    duration=196.7,
    windows=39,
    sha256="e40a9d7c2b6158f3a09c4d7e8b1520f6c3a97d40e15b8c2679d3f0a4b8c15e73",
    hashes=5871,
    shortlist_from=10,
    language="en",
    transcript_words=38,
    asr_confidence_at_gate=0.29,
    asr_confidence_after_separation=0.74,
    transcript=(
        {"word": "come", "start": 21.0, "end": 21.4},
        {"word": "with", "start": 21.4, "end": 21.6},
        {"word": "me", "start": 21.6, "end": 22.0},
    ),
    matches=(
        # The source phonogram. The fingerprint matches strongly on a short
        # segment that comes back eight times - rule 3. The modification is
        # low, so only the recognisable-excerpt flag remains, without the
        # borderline pastiche situation.
        Match(
            candidate_id="cand_01",
            matched_hashes=1904, peak_ratio=0.52,
            query_span=(0.0, 12.8), candidate_span=(124.6, 137.4), offset=124.6,
            repetitions=8, transform={"tempo": 1.02, "pitch": 0.0},
            qmax=0.34, coverage=0.21, transposition=0, tempo_ratio=1.02,
            chord_sequence=("D", "D", "C", "D"),
            jaccard=0.06, semantic_sim=0.11,
            longest_common_run=3, ms_distance=0.64,
            mean_idf=9.6, corpus_frequency=2,
            recognizability=0.84, modification=0.22,
            probability_l1=0.88, probability_l2=0.91,
        ),
        # Another track built on the same riff. The system shows both and does
        # not decide who took it from whom - that is what the chronology axis
        # on E7 is for.
        Match(
            candidate_id="cand_02",
            matched_hashes=1122, peak_ratio=0.43,
            query_span=(0.0, 11.9), candidate_span=(8.2, 20.1), offset=8.2,
            repetitions=6, transform={"tempo": 1.02, "pitch": 0.0},
            qmax=0.37, coverage=0.24, transposition=0, tempo_ratio=1.02,
            chord_sequence=("D", "D", "C", "D"),
            jaccard=0.41, semantic_sim=0.52,
            matched_spans=({"query": [21.0, 22.0], "candidate": [19.4, 20.4],
                            "text": "come with me"},),
            longest_common_run=4, ms_distance=0.58,
            mean_idf=9.4, corpus_frequency=2,
            recognizability=0.71, modification=0.44,
            probability_l1=0.57, probability_l2=0.61,
        ),
    ),
)


# Case 5 from section 14, the most important one in the whole demo. The query
# is instrumental, so detector D has nothing to compare at any level and the
# gate routes the run straight to the melody rather than to source separation.
# Both entries have harmony ABOVE the VERSION threshold and both are degraded
# to COMMON, because that progression sits in 2411 tracks of the corpus.
SCENARIO_TRAP = Scenario(
    key="common",
    keywords=("common", "trap", "progression"),
    description="The same progression and tempo, a different track. The system has judgment, not just a match.",
    duration=142.9,
    windows=28,
    sha256="a19c5f38d7204be6c81f0a53d97e2648b05c3f71a9d284e6017b5c3d8f2a94e0",
    hashes=3960,
    shortlist_from=10,
    language="en",
    transcript_words=0,
    asr_confidence_at_gate=0.04,
    asr_confidence_after_separation=0.0,
    transcript=(),
    gate_reason="no_vocals",
    separation=False,
    matches=(
        Match(
            candidate_id="cand_07",
            matched_hashes=29, peak_ratio=0.04,
            qmax=0.61, coverage=0.57, transposition=5, tempo_ratio=1.01,
            chord_sequence=("C", "G", "Am", "F", "C", "G", "F", "C"),
            alignment_path=((0, 0), (1, 1), (2, 2), (3, 3), (4, 4)),
            lyrics_status="not_applicable", lyrics_reason="instrumental query",
            longest_common_run=5, ms_distance=0.49,
            mean_idf=1.7, corpus_frequency=2411,
            probability_l1=0.31, probability_l2=0.31,
        ),
        Match(
            candidate_id="cand_08",
            matched_hashes=21, peak_ratio=0.03,
            qmax=0.58, coverage=0.52, transposition=-2, tempo_ratio=0.97,
            chord_sequence=("C", "G", "Am", "F"),
            alignment_path=((0, 0), (1, 1), (2, 2), (3, 3)),
            lyrics_status="not_applicable", lyrics_reason="instrumental query",
            longest_common_run=3, ms_distance=0.61,
            mean_idf=1.7, corpus_frequency=2411,
            probability_l1=0.28, probability_l2=0.28,
        ),
    ),
)


# The live demo: a specific recording from YouTube, Aretha Franklin's "Let It
# Be" from 1970. Recognised by the video identifier, because the title "let it
# be" does not on its own point at a performance, and the demo starts from a
# pasted address.
#
# Two entries and two different statements from the system at the same harmonic
# strength:
#   - The Beatles: the same work, a different recording. Rule 4 -> VERSION.
#   - Bob Marley: the same C-G-Am-F progression in the same key. Rule 4 also
#     gives VERSION, so the similarity is REAL rather than weak, and only the
#     commonality filter (mean_idf 1.4) degrades it to COMMON. That is the
#     whole content of the demo: the system finds a strong match and says
#     itself that it is irrelevant, because that pattern sits in 612 tracks of
#     the corpus.
SCENARIO_ARETHA = Scenario(
    key="aretha",
    keywords=("uclgp4ntdyk", "aretha"),
    description="Aretha Franklin's cover: the same work as the Beatles' and a shared C-G-Am-F progression.",
    duration=169.4,
    windows=34,
    sha256="b47e0a91c8f3562db07a4e18f5c92d360a1b8e74d92f5063c81a4b7e2f90d5c3",
    hashes=4477,
    shortlist_from=10,
    language="en",
    transcript_words=52,
    asr_confidence_at_gate=0.36,
    asr_confidence_after_separation=0.82,
    transcript=(
        {"word": "when", "start": 8.9, "end": 9.2},
        {"word": "i", "start": 9.2, "end": 9.3},
        {"word": "find", "start": 9.3, "end": 9.7},
        {"word": "myself", "start": 9.7, "end": 10.3},
        {"word": "in", "start": 10.4, "end": 10.6},
        {"word": "times", "start": 10.6, "end": 11.1},
        {"word": "of", "start": 11.1, "end": 11.3},
        {"word": "trouble", "start": 11.3, "end": 12.0},
    ),
    matches=(
        # The source track. The fingerprint does not match, because this is a
        # completely different recording, but the harmony and the lyrics match
        # strongly. Rule 4 -> VERSION at both levels, and the high mean_idf
        # keeps it away from degradation to COMMON.
        Match(
            candidate_id="cand_07",
            matched_hashes=52, peak_ratio=0.07,
            query_span=(8.9, 41.6), candidate_span=(6.2, 38.9), offset=-2.7,
            repetitions=1,
            qmax=0.82, coverage=0.78, transposition=3, tempo_ratio=0.93,
            chord_sequence=("C", "G", "Am", "F", "C", "G", "F", "C"),
            alignment_path=((0, 0), (1, 1), (2, 2), (3, 4), (4, 5), (5, 6), (6, 7)),
            jaccard=0.71, semantic_sim=0.89,
            matched_spans=({"query": [8.9, 12.0], "candidate": [6.2, 9.4],
                            "text": "when i find myself in times of trouble"},),
            longest_common_run=12, ms_distance=0.14,
            matched_ngrams=({"query_start": 9.3, "candidate_start": 6.6, "n": 6,
                             "intervals": [2, 2, 1, -3, -2, 2]},
                            {"query_start": 24.8, "candidate_start": 21.9, "n": 5,
                             "intervals": [0, -2, -1, 3, 2]}),
            mean_idf=7.9, corpus_frequency=6,
            probability_l1=0.73, probability_l2=0.96,
        ),
        # The common element. qmax and coverage MUST cross the VERSION
        # thresholds, otherwise the degradation has nothing to degrade and a
        # plain NONE comes out. The lyrics share almost no vocabulary with the
        # query (jaccard 0.09), but both lines are a formula of consolation, so
        # the semantic similarity crosses the 0.70 threshold - hence no common
        # fragments to show.
        Match(
            candidate_id="cand_08",
            matched_hashes=19, peak_ratio=0.05,
            qmax=0.66, coverage=0.61, transposition=0, tempo_ratio=1.02,
            chord_sequence=("C", "G", "Am", "F"),
            alignment_path=((0, 0), (1, 1), (2, 2), (3, 3)),
            jaccard=0.09, semantic_sim=0.74,
            longest_common_run=3, ms_distance=0.58,
            matched_ngrams=({"query_start": 10.2, "candidate_start": 33.1, "n": 3,
                             "intervals": [2, 2, -4]},),
            mean_idf=1.4, corpus_frequency=612,
            probability_l1=0.36, probability_l2=0.42,
        ),
        # Noise from the shortlist: harmony below the VERSION threshold, alien
        # lyrics. NONE at both levels.
        Match(
            candidate_id="cand_04",
            matched_hashes=11, peak_ratio=0.03,
            qmax=0.41, coverage=0.44, transposition=-4, tempo_ratio=1.05,
            chord_sequence=("Am", "F", "C", "G"),
            jaccard=0.07, semantic_sim=0.21,
            longest_common_run=3, ms_distance=0.69,
            mean_idf=5.8, corpus_frequency=41,
            probability_l1=0.08, probability_l2=0.07,
        ),
    ),
)


SCENARIOS: dict[str, Scenario] = {
    s.key: s for s in (SCENARIO_ARETHA, SCENARIO_COVER, SCENARIO_REUPLOAD,
                       SCENARIO_MODIFIED, SCENARIO_SAMPLE, SCENARIO_TRAP)
}
DEFAULT_SCENARIO = SCENARIO_COVER


def select_scenario(url: str) -> Scenario:
    """The scenario chosen by a keyword in the address.

    Five cases from section 14 on a single public address: without this, every
    query returned the same story and four of the eight evidentiary classes
    showed up nowhere.

    A keyword can also be a video identifier, because the live demo starts from
    a pasted YouTube address rather than from an example button. The identifier
    stands first in the dictionary, so that a specific recording wins over a
    general word.
    """
    address = url.lower()
    for scenario in SCENARIOS.values():
        if any(word in address for word in scenario.keywords):
            return scenario
    return DEFAULT_SCENARIO


# --------------------------------------------------------------------------
# POST /api/explain
# --------------------------------------------------------------------------

# Wiring up a language model is deliberately out of the plan's scope, so the
# stub assembles a fixed text from numbers that are in the result anyway. Not a
# single sentence here comes from a model - it is a skeleton of length and tone
# for screen E8.
EXPLANATION_TEMPLATE = (
    "The query overlaps with the entry {name} ({artist}) over the segment {span}. "
    "The system classifies this as {verdict_class}, rights layer: {layer}. "
    "The probability {probability} comes from {source}. "
    "Technical signal, not legal advice."
)


def explanation(entry: RankingEntry) -> str:
    span = "the whole length of the query"
    alignment = entry.alignment
    if alignment is not None and alignment.query_span is not None:
        start, end = alignment.query_span
        span = f"{start:.1f} s - {end:.1f} s"
    source = ("the calibration model" if entry.probability_status == "calibrated"
              else "a starting threshold, without calibration data")
    layer = entry.verdict_layer or "none, the result concerns no layer"
    return EXPLANATION_TEMPLATE.format(
        name=entry.candidate.name,
        artist=entry.candidate.artist,
        span=span,
        verdict_class=entry.verdict_class,
        layer=layer,
        probability=f"{entry.probability:.2f}"
        if entry.probability is not None else "unknown",
        source=source,
    )

