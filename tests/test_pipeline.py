"""The end-to-end run. Sections 4 and 12 of the specification.

The tests run on synthetic but REAL audio and on real detectors. No detector is
replaced by a stub here - that is the only way for a test to say anything about
whether the engine actually computes.

Two things look different today than the T22 brief assumed, and the tests
reflect that:

* **The heavy models are not in the environment** (the owner's decision), so
  detectors D and C return a `failed` envelope with the reason
  `model_unavailable`. The test "a level 2 failure does not cancel the verdict"
  is therefore the DEFAULT MODE rather than a monkeypatch - the monkeypatch
  stays separately, for an exception thrown from `run` itself, which
  `run_guarded` will not catch.
* **There is no calibration**, so `probability_status` says `uncalibrated`
  everywhere, and the number next to an entry is the raw score of a detector.
"""
import asyncio

import pytest

from origin import config, pipeline
from origin.api import jobs
from origin.contracts import VERDICT_CLASSES
from origin.detectors import registry

# Level 1 and level 2 stages from section 4. Assigning a stage to a level is a
# contract with the frontend (screen E2 draws two sections from it), not a
# detail of the notation.
LEVEL_1_STAGES = {"ingest", "fingerprint", "harmonic", "shortlist", "commonality"}
LEVEL_2_STAGES = {"transcript", "separation", "melodic"}


def _run(query, candidate_list):
    """The run together with the list of events, in the order they went on the wire."""
    events = []
    result = pipeline.run_sync(query, emit=events.append, candidates=candidate_list)
    return result, events


def _entry(result, candidate_id):
    return next((e for e in result.ranking if e.candidate.id == candidate_id), None)


# --- order and levels -------------------------------------------------------


def test_level_1_emits_the_verdict_before_level_2(pipeline_query, pipeline_candidates):
    """Section 4: a verdict in five seconds, evidence arriving over the next thirty."""
    _, events = _run(pipeline_query, pipeline_candidates)
    stages = [e.stage for e in events]
    verdict_index = stages.index("verdict")

    assert "fingerprint" in stages[:verdict_index]
    assert "harmonic" in stages[:verdict_index]
    assert "melodic" not in stages[:verdict_index]
    assert "transcript" not in stages[:verdict_index]


def test_the_verdict_appears_twice(pipeline_query, pipeline_candidates):
    _, events = _run(pipeline_query, pipeline_candidates)
    verdicts = [e for e in events if e.stage == "verdict"]
    assert [e.status for e in verdicts] == ["partial", "final"]
    assert [e.level for e in verdicts] == [1, 2]


def test_the_stages_go_in_the_order_of_section_12(pipeline_query, pipeline_candidates):
    _, events = _run(pipeline_query, pipeline_candidates)
    stages = [e.stage for e in events]
    # The first occurrence of every stage has to come in the order of section 12.
    order = [
        stages.index(name)
        for name in ("ingest", "fingerprint", "harmonic", "shortlist",
                     "commonality", "verdict", "melodic")
    ]
    assert order == sorted(order)


def test_every_event_carries_the_level_of_its_stage(pipeline_query, pipeline_candidates):
    """Section 12: the `level` field says which execution level the stage comes from."""
    _, events = _run(pipeline_query, pipeline_candidates)
    for event in events:
        if event.stage in LEVEL_1_STAGES:
            assert event.level == 1, event
        elif event.stage in LEVEL_2_STAGES:
            assert event.level == 2, event
        else:
            assert event.stage == "verdict"
            assert event.level in (1, 2)


def test_the_partial_result_is_stored_before_the_verdict(pipeline_query, pipeline_candidates):
    """On the `verdict` event the frontend immediately fetches /result and must get the current one."""
    trace = []

    async def _consume():
        async for event in pipeline.run(
            pipeline_query,
            candidates=pipeline_candidates,
            on_result=lambda r: trace.append(("result", r.status)),
        ):
            if event.stage == "verdict":
                trace.append(("verdict", event.status))

    asyncio.run(_consume())
    assert trace == [
        ("result", "partial"), ("verdict", "partial"),
        ("result", "final"), ("verdict", "final"),
    ]


# --- level 2 raises the verdict, it never takes it away ----------------------


def test_missing_heavy_models_do_not_cancel_the_verdict(pipeline_query, pipeline_candidates):
    """The default mode, not a failure: detectors D and C have no model in the environment.

    Fusion recomputes on what it has, so the final class comes out of the same
    signals as the partial one. That is the property the T22 brief checked with
    a monkeypatch - today nothing has to be patched to see it.
    """
    if _models_present():
        pytest.skip("the heavy models are installed; this test describes an environment without them")

    result, events = _run(pipeline_query, pipeline_candidates)
    assert result.status == "final"
    assert result.completed_levels == [1, 2]

    top = result.ranking[0]
    assert top.evidence["melodic"].status == "failed"
    assert "model_unavailable" in (top.evidence["melodic"].reason or "")
    assert top.evidence["lyrics"].status == "failed"

    # The final verdict stands on the same signals as the partial one, so the
    # class does not change. The event says so outright, so the frontend has
    # something to animate with.
    verdicts = [e for e in events if e.stage == "verdict"]
    assert verdicts[1].detail["previous_class"] == verdicts[0].detail["class"]
    assert verdicts[1].detail["class"] == verdicts[0].detail["class"]


def test_an_exception_from_a_level_2_detector_becomes_a_failed_envelope(
    pipeline_query, pipeline_candidates, monkeypatch
):
    """The second fence beyond run_guarded: an exception from `run` itself has to stop here too."""
    from origin.detectors import melodic

    def explode(self, clip, candidates, context=None, separated_vocals=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(melodic.MelodicDetector, "run", explode)

    result, events = _run(pipeline_query, pipeline_candidates)
    assert result.status == "final"
    top = result.ranking[0]
    assert top.evidence["melodic"].status == "failed"
    assert "boom" in (top.evidence["melodic"].reason or "")
    # The stage went on the wire as failed rather than disappearing from the stream.
    melodic_events = [e for e in events if e.stage == "melodic"]
    assert [e.status for e in melodic_events] == ["running", "failed"]


def test_a_level_1_failure_does_not_end_the_run(
    pipeline_query, pipeline_candidates, monkeypatch
):
    """Section 9.1: fusion has to work with every envelope other than ok."""
    from origin.detectors import fingerprint

    monkeypatch.setattr(
        fingerprint.FingerprintDetector, "run",
        lambda self, clip, candidates, context=None: (_ for _ in ()).throw(RuntimeError("no index")),
    )
    result, events = _run(pipeline_query, pipeline_candidates)

    assert result.status == "final"
    assert [e.status for e in events if e.stage == "verdict"] == ["partial", "final"]
    assert result.ranking, "pre-filtering has to work on the harmony alone"
    assert result.ranking[0].evidence["fingerprint"].status == "failed"


# --- Global Constraint 3: the heavy models only on the shortlist -------------


def test_the_heavy_models_do_not_run_beyond_the_shortlist(
    pipeline_query, pipeline_candidates, monkeypatch
):
    """Breaking this rule makes work on the target hardware impossible (section 4)."""
    from origin.detectors import lyrics, melodic

    seen: dict[str, list[str]] = {}

    def spy(name, original):
        def wrapped(self, clip, candidates, context=None, **rest):
            seen[name] = [c.id for c in candidates]
            return original(self, clip, candidates, context, **rest)
        return wrapped

    monkeypatch.setattr(lyrics.LyricsDetector, "run",
                        spy("lyrics", lyrics.LyricsDetector.run))
    monkeypatch.setattr(melodic.MelodicDetector, "run",
                        spy("melodic", melodic.MelodicDetector.run))

    events = []
    pipeline.run_sync(pipeline_query, emit=events.append, candidates=pipeline_candidates)

    prefilter = next(e for e in events if e.stage == "shortlist")
    shortlist_size = prefilter.detail["to"]
    assert shortlist_size <= config.SHORTLIST_SIZE
    for name in ("lyrics", "melodic"):
        assert len(seen[name]) == shortlist_size, (
            f"detector {name} received more candidates than the shortlist"
        )
    # A candidate without audio does not pass pre-filtering, so level 2 never sees it.
    assert "missing" not in seen["melodic"]


# --- section 7.4 step 1: one separation, computed by D and shared with C -----


def _melody_of(pitches):
    from origin.detectors import melodic

    return melodic.Melody([
        melodic.Note(pitch, float(i), float(i) + 1.0)
        for i, pitch in enumerate(pitches)
    ])


def _stub_the_melody_transcription(monkeypatch, received):
    """Detector C without basic-pitch: the real detector, a stubbed transcription.

    Only the two functions that touch the model are replaced. Everything the
    test then asserts - which audio arrived, which flag left - is decided by
    the detector and the pipeline, not by the stub.
    """
    from origin.detectors import melodic

    def query_melody(clip, separated_vocals=None):
        received.append(separated_vocals)
        return _melody_of((60, 62, 64, 65))

    monkeypatch.setattr(melodic, "model_available", lambda: True)
    monkeypatch.setattr(melodic, "melody", query_melody)
    monkeypatch.setattr(melodic, "representation", lambda path: _melody_of((60, 62, 64, 67)))


def _stub_the_transcript(monkeypatch, vocals):
    """Detector D without whisper: the gate passes, and it returns `vocals`.

    `vocals=None` is the cheap path of decision D3 - the gate passed on the
    first pass and demucs never ran, so there is nothing to share.
    """
    from origin.detectors import lyrics

    transcript = lyrics.Transcript(
        text="hello darkness my old friend", confidence=0.9,
        language="en", language_stable=True, words=[],
    )
    monkeypatch.setattr(
        lyrics, "transcribe_with_gate",
        lambda clip: lyrics.GateOutcome(transcript, True, None, vocals),
    )


def _melodic_measurements(events):
    """The melodic results that carry a measurement, from the stage envelope.

    A ranking entry's `Evidence` is only a status and a reason (section 12) -
    the numbers themselves travel in the envelope attached to the stage event,
    which is what screens E4-E5 read.
    """
    done = next(e for e in events if e.stage == "melodic" and e.status != "running")
    return [r for r in done.detail["envelope"]["results"] if r["status"] == "ok"]


def test_the_vocals_separated_by_the_lyrics_pass_reach_the_melody(
    pipeline_query, pipeline_candidates, monkeypatch
):
    """Section 7.4 step 1: separation is computed ONCE, by D, and shared with C.

    Without this wiring the melody is transcribed from the full mix even when
    a vocal track already exists, and basic-pitch then mostly follows the drums
    and the accompaniment - the degenerate case its own docstring warns about.
    On the first real run that showed up as the unrelated candidate scoring the
    better Mongeau-Sankoff distance of the two.
    """
    import numpy as np

    vocals = np.linspace(-0.5, 0.5, 2048, dtype=np.float32)
    received: list = []
    _stub_the_transcript(monkeypatch, vocals)
    _stub_the_melody_transcription(monkeypatch, received)

    _, events = _run(pipeline_query, pipeline_candidates)

    assert received, "detector C never transcribed the query melody"
    assert received[0] is vocals, (
        "detector C transcribed something other than the vocal track detector D separated"
    )
    measured = _melodic_measurements(events)
    assert measured, "no candidate got a melodic measurement"
    assert all(r["used_separation"] is True for r in measured)


def test_without_separation_the_melody_reads_the_mix_and_says_so(
    pipeline_query, pipeline_candidates, monkeypatch
):
    """The gate passed on the first pass, so there is no vocal track to share.

    The melody is then read from the full mix rather than paying for a
    separation of its own (391 s measured), and every result carries
    `used_separation=False` so that the interface and the report can read the
    distance in that light instead of guessing.
    """
    received: list = []
    _stub_the_transcript(monkeypatch, None)
    _stub_the_melody_transcription(monkeypatch, received)

    _, events = _run(pipeline_query, pipeline_candidates)

    assert received == [None], "the melody was handed audio nobody separated"
    measured = _melodic_measurements(events)
    assert measured, "no candidate got a melodic measurement"
    assert all(r["used_separation"] is False for r in measured)


# --- a candidate without audio ----------------------------------------------


def test_a_candidate_without_audio_does_not_bring_the_run_down(pipeline_query, pipeline_candidates):
    """Section 5.7: the manifest is created before fetching and fetching may fail."""
    result, events = _run(pipeline_query, pipeline_candidates)

    ingest_event = next(e for e in events if e.stage == "ingest" and e.status == "done")
    assert ingest_event.detail["audio_missing"] == ["missing"]
    assert result.status == "final"

    # A candidate without a file carries not a single number and speaks with one
    # reason, not with whichever symptom a detector happened to see.
    envelope = next(
        e for e in events if e.stage == "fingerprint" and e.status != "running"
    ).detail["envelope"]
    missing = [r for r in envelope["results"] if r["candidate_id"] == "missing"]
    assert missing and missing[0]["status"] == "failed"
    assert missing[0]["peak_ratio"] is None


# --- real numbers -----------------------------------------------------------


def test_the_same_recording_gives_exact(pipeline_query, pipeline_candidates):
    """Rule 1 of 9.1 on a real fingerprint, not on a written-in number."""
    result, _ = _run(pipeline_query, pipeline_candidates)
    entry = _entry(result, "same")
    assert entry is not None
    assert entry.verdict_class == "EXACT"
    assert entry.verdict_layer == "phonogram"
    assert entry.rank == 1, "the same recording has to lead the ranking"
    assert entry.probability is not None and entry.probability > config.threshold(
        "EXACT_PEAK_RATIO"
    )


def test_the_negative_control_gets_no_evidentiary_class(pipeline_query, pipeline_candidates):
    """White noise must not hit anything. Section 15: the negative control."""
    result, _ = _run(pipeline_query, pipeline_candidates)
    entry = _entry(result, "noise")
    assert entry is not None
    assert entry.verdict_class in ("NONE", "COMMON")


def test_every_entry_has_a_class_from_the_taxonomy(pipeline_query, pipeline_candidates):
    result, _ = _run(pipeline_query, pipeline_candidates)
    assert result.ranking
    for entry in result.ranking:
        assert entry.verdict_class in VERDICT_CLASSES
        assert set(entry.evidence) == {"fingerprint", "harmonic", "melodic", "lyrics"}
        assert entry.legal.disclaimer


def test_the_ranking_is_ordered_descending(pipeline_query, pipeline_candidates):
    result, _ = _run(pipeline_query, pipeline_candidates)
    assert [e.rank for e in result.ranking] == list(range(1, len(result.ranking) + 1))


# --- there is no calibration and the system says so outright -----------------


def test_there_is_no_calibration_so_the_numbers_are_raw(pipeline_query, pipeline_candidates):
    """Section 10.5: the UI must tell a number from a model apart from a raw score."""
    result, events = _run(pipeline_query, pipeline_candidates)
    assert result.calibration is None, "no model has to mean no block, not a written-in version"
    for entry in result.ranking:
        assert entry.probability_status == "uncalibrated"
    for event in events:
        if event.stage == "verdict":
            assert event.detail["probability_status"] == "uncalibrated"


# --- material that cannot be loaded -----------------------------------------


def test_bad_material_ends_with_a_failed_verdict(tmp_path, pipeline_candidates):
    """Without input material every subsequent stage would be pretending to work."""
    events = []
    result = pipeline.run_sync(
        str(tmp_path / "no-such-file.wav"), emit=events.append, candidates=pipeline_candidates
    )
    assert result.status == "failed"
    assert result.ranking == []
    stages = [(e.stage, e.status) for e in events]
    assert ("ingest", "failed") in stages
    assert ("verdict", "failed") in stages


# --- the detector registry --------------------------------------------------


def test_the_registry_is_wired_up_in_one_place():
    """Section 7.0: no detector registers itself, the pipeline does it."""
    for name in ("fingerprint", "harmonic", "lyrics", "melodic"):
        assert registry.get(name) is pipeline.DETECTORS[name]
    assert [registry.get(n).level for n in pipeline.LEVEL_1] == [1, 1]
    assert [registry.get(n).level for n in pipeline.LEVEL_2] == [2, 2]


def test_the_detectors_register_once(pipeline_query, pipeline_candidates):
    """A run must not multiply detector instances on every request."""
    before = {n: registry.get(n) for n in pipeline.DETECTORS}
    _run(pipeline_query, pipeline_candidates)
    assert {n: registry.get(n) for n in pipeline.DETECTORS} == before


# --- the seam with the job store --------------------------------------------


def test_the_producer_fits_the_job_store(pipeline_query, pipeline_candidates):
    """`store.start(job_id, pipeline.run(...))` without a single adapter."""

    async def scenario():
        store = jobs.JobStore()
        job_id = store.create(pipeline_query, "demo_01")
        store.start(job_id, pipeline.run(
            pipeline_query,
            candidates=pipeline_candidates,
            on_result=lambda r: store.set_result(job_id, r),
        ))
        await store.get(job_id).task
        return store.events(job_id), store.get_result(job_id)

    events, result = asyncio.run(scenario())
    assert [e.status for e in events if e.stage == "verdict"] == ["partial", "final"]
    assert result.status == "final"
    # Every event has to serialise into an SSE frame without an exception - the
    # detector envelopes travel in `detail` and they are what would break the
    # dump if anything in them were unserialisable.
    assert all(jobs.sse_frame(e).startswith("data: ") for e in events)


# --- the corpus -------------------------------------------------------------


def test_a_missing_corpus_does_not_bring_the_run_down(pipeline_query, pipeline_candidates):
    """The commonality filter without a corpus degrades nothing and does not break the analysis."""
    result, events = _run(pipeline_query, pipeline_candidates)
    prefilter = next(e for e in events if e.stage == "shortlist")
    assert prefilter.detail["corpus"] == 0
    assert result.ranking[0].verdict_class == "EXACT"


def test_the_corpus_feeds_the_commonality_numbers(
    pipeline_query, pipeline_candidates, tmp_path, monkeypatch
):
    """The numbers from section 8 have to reach the event and the ranking entry."""
    from origin import commonality
    from origin.detectors import harmonic
    from origin import ingest

    sequence = harmonic.chord_sequence(harmonic.chroma(ingest.load_clip(pipeline_query)))
    patterns = commonality.chord_ngrams(sequence)
    if not patterns:
        pytest.skip("the query material gave no chord pattern at all")

    file = tmp_path / "idf.json"
    commonality.Corpus.from_documents([patterns] * 50).save(file)
    monkeypatch.setenv("ORIGIN_CORPUS", str(file))

    result, events = _run(pipeline_query, pipeline_candidates)
    prefilter = next(e for e in events if e.stage == "shortlist")
    assert prefilter.detail["corpus"] == 50

    commonality_event = next(e for e in events if e.stage == "commonality")
    assert commonality_event.detail["corpus_size"] == 50
    # A reupload built on a common progression does not stop being a reupload
    # (section 8.1): only work-layer classes are degraded.
    assert _entry(result, "same").verdict_class == "EXACT"


# --- helpers ----------------------------------------------------------------


def _models_present() -> bool:
    from origin.detectors import melodic

    return melodic.model_available()
