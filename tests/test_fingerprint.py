import importlib
import pkgutil

import numpy as np
import pytest
import soundfile as sf

from origin import ingest
from origin.contracts import Candidate
from origin.detectors import fingerprint as fp

SR = 22050


def _candidate(path: str, ident: str = "c1") -> Candidate:
    return Candidate(
        id=ident, name="track", artist="performer",
        source_url="https://example.invalid/x", audio_path=path,
    )


def test_a_clip_matches_itself(chord_wav):
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="self")
    result = fp.match(clip, idx)["self"]
    assert result.peak_ratio > 0.9


def test_noise_does_not_match_music(chord_wav, noise_wav):
    idx = fp.build_index(ingest.load_clip(chord_wav), candidate_id="music")
    result = fp.match(ingest.load_clip(noise_wav), idx).get("music")
    assert result is None or result.peak_ratio < 0.25


def test_the_offset_histogram_gives_a_sharp_peak_on_a_hit(chord_wav):
    """Section 7.1: a real match has many hashes with THE SAME offset difference."""
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="self")
    result = fp.match(clip, idx)["self"]
    assert abs(result.offset) < 0.5


def test_a_trimmed_fragment_gives_a_non_zero_offset(chord_wav):
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="full")
    fragment = ingest.Clip.from_array(clip.y_harmonic[22050 * 2:], clip.sr_harmonic)
    result = fp.match(fragment, idx)["full"]
    assert result.offset == pytest.approx(2.0, abs=0.5)


def test_span_length_is_computed_from_query_span(chord_wav):
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="self")
    result = fp.match(clip, idx)["self"]
    assert result.span_length == pytest.approx(
        result.query_span[1] - result.query_span[0])


def test_a_repeated_loop_gives_repetitions_of_at_least_two(tmp_path):
    """Section 9.1 rule 3: EXCERPT requires repetitions >= 2."""
    from tests.conftest import chord
    loop = chord([261.6, 329.6, 392.0], 2.0)
    track = np.concatenate([np.zeros(22050 * 3), loop, np.zeros(22050 * 3), loop])
    sf.write(tmp_path / "loop.wav", loop, 22050)
    sf.write(tmp_path / "track.wav", track, 22050)
    idx = fp.build_index(ingest.load_clip(str(tmp_path / "loop.wav")), candidate_id="sample")
    result = fp.match(ingest.load_clip(str(tmp_path / "track.wav")), idx)["sample"]
    assert result.repetitions >= 2


def test_a_match_against_itself_has_one_occurrence(chord_wav):
    """The control for the loop test: without a repetition, repetitions must be 1, not more."""
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="self")
    assert fp.match(clip, idx)["self"].repetitions == 1


def test_the_transformation_grid_does_not_run_without_being_called(chord_wav, shifted_wav, monkeypatch):
    """Section 7.1: the 143 variants are expensive and start on demand only.

    We count CALLS rather than the content of the transform field: `match`
    constructs `transform=None` by definition, so checking the field passes even
    when the grid has been ground through in the background.
    """
    idx = fp.build_index(ingest.load_clip(chord_wav), candidate_id="original")
    clip = ingest.load_clip(shifted_wav)

    counter = {"n": 0}
    original = fp._hashes

    def counting(*args, **kwargs):
        counter["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(fp, "_hashes", counting)

    fp.match(clip, idx)
    assert counter["n"] == 1, "match computed more than one variant"

    counter["n"] = 0
    fp.match_transformed(clip, idx)
    assert counter["n"] == 13 * 11


def test_the_transformation_grid_finds_the_speedup(chord_wav, shifted_wav):
    idx = fp.build_index(ingest.load_clip(chord_wav), candidate_id="original")
    result = fp.match_transformed(ingest.load_clip(shifted_wav), idx)["original"]
    assert result.transform is not None
    assert result.transform["tempo_ratio"] == pytest.approx(1.06, abs=0.03)


def test_the_identity_variant_is_not_a_transformation(chord_wav):
    """Fusion rule 2 looks only at transform != null, so a zero must not be there."""
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="self")
    assert fp.match_transformed(clip, idx)["self"].transform is None


def test_spans_are_in_source_recording_time(tmp_path):
    """Section 6: ingest cuts silence, so clip time is not recording time.

    A span in clip time would point A/B playback at a different place in the
    recording.
    """
    from tests.conftest import progression
    sf.write(tmp_path / "bare.wav", progression(), SR)
    with_silence = np.concatenate([np.zeros(SR * 3), progression()])
    sf.write(tmp_path / "with_silence.wav", with_silence, SR)

    clip = ingest.load_clip(str(tmp_path / "with_silence.wav"))
    assert clip.source_offset_s == pytest.approx(3.0, abs=0.3)

    idx = fp.build_index(clip, candidate_id="with_silence")
    result = fp.match(clip, idx)["with_silence"]
    assert result.query_span[0] > 2.5
    assert result.candidate_span[0] > 2.5

    # The same material without the leading silence: the offset has to show the
    # difference between the cuts.
    bare_idx = fp.build_index(ingest.load_clip(str(tmp_path / "bare.wav")), candidate_id="bare")
    bare_result = fp.match(clip, bare_idx)["bare"]
    # The tolerance is deliberately loose: the fixture is four stationary
    # chords, and stationary material matches itself to within the length of a
    # chord. The test guards that the offset carries the difference between the
    # cuts (about -3 s) rather than the zero that would come out if it were
    # computed in clip time.
    assert bare_result.offset == pytest.approx(-3.0, abs=1.0)


def test_run_reads_fingerprints_from_disk_and_does_not_decode_audio(chord_wav, tmp_path, monkeypatch):
    """Section 4: candidate representations are a level 0 artifact, offline."""
    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "cache"))
    candidate = _candidate(chord_wav)
    clip = ingest.load_clip(chord_wav)

    def forbidden(*args, **kwargs):
        raise AssertionError("the live path is decoding candidate audio")

    # A cold cache: the candidate comes back as failed, without a single number.
    monkeypatch.setattr(fp.ingest, "load_clip", forbidden)
    cold = fp.FingerprintDetector().run(clip, candidates=[candidate])
    assert cold.status == "ok"
    assert [r.status for r in cold.results] == ["failed"]
    assert "prewarm" in (cold.results[0].reason or "")
    assert cold.results[0].carries_claim() is None

    # Level 0 is computed once, offline.
    monkeypatch.undo()
    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "cache"))
    assert fp.prewarm([candidate]) == {}

    monkeypatch.setattr(fp.ingest, "load_clip", forbidden)
    warm = fp.FingerprintDetector().run(clip, candidates=[candidate])
    assert [r.status for r in warm.results] == ["ok"]
    assert warm.results[0].peak_ratio > 0.9


def test_the_detector_returns_an_envelope_with_a_status(chord_wav):
    clip = ingest.load_clip(chord_wav)
    env = fp.FingerprintDetector().run(clip, candidates=[])
    assert env.detector == "fingerprint"
    assert env.status in ("ok", "failed")


def test_an_exception_in_the_run_gives_a_failed_envelope(chord_wav, monkeypatch):
    """Section 9.1: a detector failure must not bring the analysis down."""
    clip = ingest.load_clip(chord_wav)

    def explode(*args, **kwargs):
        raise RuntimeError("the index fell apart")

    monkeypatch.setattr(fp, "load_index", explode)
    env = fp.FingerprintDetector().run(clip, candidates=[_candidate("missing.wav")])
    assert env.status == "failed"
    assert env.results == []
    assert "the index fell apart" in (env.reason or "")


def test_the_grid_starts_only_on_a_signal_from_the_harmony(chord_wav, shifted_wav, tmp_path, monkeypatch):
    """Section 7.1: the grid is started only by the harmony saying 'this is that track'."""
    from origin.contracts import DetectorEnvelope, HarmonicResult
    from origin.detectors import base

    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "cache"))
    candidate = _candidate(chord_wav, "original")
    assert fp.prewarm([candidate]) == {}
    clip = ingest.load_clip(shifted_wav)

    without_context = fp.FingerprintDetector().run(clip, candidates=[candidate])
    assert all(r.transform is None for r in without_context.results)

    context = base.Context(envelopes={
        "harmonic": DetectorEnvelope(
            detector="harmonic",
            results=[HarmonicResult(candidate_id="original", qmax_score=0.82)],
        )
    })
    with_context = fp.FingerprintDetector().run(
        clip, candidates=[candidate], context=context
    )
    result = next(r for r in with_context.results if r.candidate_id == "original")
    assert result.transform is not None
    assert result.transform["tempo_ratio"] == pytest.approx(1.06, abs=0.03)


def test_no_detector_registers_itself():
    """The T7/T8 preflight decision: wiring into the registry belongs to the pipeline.

    We compare the registry state BEFORE and AFTER the import rather than
    against an empty dictionary: the registry is global to the process and the
    pipeline wires the full set into it, so another test module may have filled
    it already, and an empty dictionary would check the file order in the suite
    instead of what this rule really says.
    """
    from origin import detectors
    from origin.detectors import registry

    before = dict(registry.DETECTORS)
    for module in pkgutil.iter_modules(detectors.__path__):
        importlib.import_module(f"origin.detectors.{module.name}")
    assert registry.DETECTORS == before
