"""Detector B - harmonic similarity. Section 7.2 of the specification.

All the material is synthetic (conftest.py). There is no real audio and the
tests are not allowed to download anything.
"""
import numpy as np

from origin import config, ingest
from origin.contracts import Candidate
from origin.detectors import harmonic as h


# --- features: the chromagram -----------------------------------------------


def test_chroma_has_twelve_classes(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    assert c.shape[0] == 12


def test_frames_are_l2_normalised(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    norms = np.linalg.norm(c, axis=0)
    assert np.allclose(norms[norms > 0], 1.0, atol=0.01)


def test_the_same_material_gives_a_high_qmax(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    assert h.qmax(c, c).qmax_score > 0.9


def test_noise_gives_a_low_qmax(chord_wav, noise_wav):
    """White noise must not read as the same work.

    Five seconds of noise are eleven frames at 2 Hz, and on eleven frames the
    absolute qmax scale does not apply: a six-frame chain is already 0.545, and
    six frames is about what the calibrated sieve chains by chance on material
    this short. `_binarise` says the same thing about few-second fragments -
    they are to be read as ordering, not against VERSION_QMAX. The absolute
    scale is asserted where it holds, on two hundred frames, in
    `test_alien_material_stays_far_below_the_version_threshold`.

    What does apply here is the verdict, and it is the stronger claim: rule 4
    of section 9.1 takes qmax AND coverage, and the progression does not cover
    noise.
    """
    a = h.chroma(ingest.load_clip(chord_wav))
    b = h.chroma(ingest.load_clip(noise_wav))
    against_noise = h.qmax(a, b)
    assert against_noise.qmax_score < h.qmax(a, a).qmax_score
    assert against_noise.coverage < config.THRESHOLDS["VERSION_COVERAGE"].value


def test_transposition_is_detected_without_key_detection(chord_wav):
    """Section 7.2: we do not transpose to a detected key, because detection is unreliable."""
    c = h.chroma(ingest.load_clip(chord_wav))
    shifted = np.roll(c, 2, axis=0)
    result = h.qmax(c, shifted)
    assert result.qmax_score > 0.9
    assert result.transposition == 2


def test_coverage_tells_a_cover_apart_from_a_fragment(chord_wav):
    """Section 7.2: coverage is exactly what separates VERSION from EXCERPT."""
    c = h.chroma(ingest.load_clip(chord_wav))
    whole = h.qmax(c, c)
    fragment = h.qmax(c[:, : c.shape[1] // 4], c)
    assert whole.coverage > fragment.coverage


def test_the_global_descriptor_has_256_dimensions(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    assert h.global_descriptor(c).shape == (256,)


def test_the_descriptor_filters_more_cheaply_than_the_matrix(chord_wav, noise_wav):
    a = h.global_descriptor(h.chroma(ingest.load_clip(chord_wav)))
    b = h.global_descriptor(h.chroma(ingest.load_clip(noise_wav)))
    similarity = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    assert similarity < 0.8


def test_the_chord_sequence_feeds_the_idf_filter(chord_wav):
    """Section 8: the commonality filter computes the IDF of chord sequences from detector B."""
    seq = h.chord_sequence(h.chroma(ingest.load_clip(chord_wav)))
    assert len(seq) >= 4
    assert all(isinstance(x, str) for x in seq)


def test_the_alignment_path_is_non_empty_on_a_hit(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    assert len(h.qmax(c, c).alignment_path) > 0


# --- a UI artifact: the matrix and the path ---------------------------------


def test_the_similarity_matrix_is_a_ui_artifact(chord_wav):
    """Section 7.2: this same matrix is the heatmap on E4, so it has to be available."""
    c = h.chroma(ingest.load_clip(chord_wav))
    matrix = h.similarity_matrix(c, c)
    assert matrix.shape == (c.shape[1], c.shape[1])
    assert matrix.max() <= 1.0 + 1e-6


def test_the_alignment_path_can_be_drawn(chord_wav):
    """Pairs (query frame, candidate frame) increasing on both axes."""
    c = h.chroma(ingest.load_clip(chord_wav))
    path = h.qmax(c, c).alignment_path
    assert all(isinstance(i, int) and isinstance(j, int) for i, j in path)
    assert all(
        nxt[0] > cur[0] and nxt[1] > cur[1]
        for cur, nxt in zip(path, path[1:])
    )
    assert max(i for i, _ in path) < c.shape[1]


def test_a_cover_with_a_different_tempo_and_key(chord_wav, shifted_wav, noise_wav):
    """shifted_wav is the same material 6 percent faster, that is also a semitone higher.

    An absolute threshold (VERSION_QMAX 0.55) does not apply here and must not
    be pretended: eight seconds with four sustained chords give seventeen
    frames, so the band of the real match occupies more than a fifth of the
    matrix, whereas Serra's ten-percent sieve is calibrated for material in
    which that same diagonal is a fraction of a percent. So the fixture checks
    what is checkable on it: a transposition found without key detection on a
    genuinely retuned signal rather than on np.roll, and an advantage over the
    negative control in both the score and the path length.
    """
    a = h.chroma(ingest.load_clip(chord_wav))
    b = h.chroma(ingest.load_clip(shifted_wav))
    control = h.chroma(ingest.load_clip(noise_wav))

    result = h.qmax(a, b)
    negative = h.qmax(a, control)
    assert result.transposition == 1
    assert result.qmax_score > negative.qmax_score
    assert len(result.alignment_path) > len(negative.alignment_path)
    assert result.tempo_ratio is not None


def test_an_empty_chromagram_carries_no_numbers(chord_wav):
    """Section 7.0: not applicable is not zero."""
    c = h.chroma(ingest.load_clip(chord_wav))
    result = h.qmax(c, c[:, :0])
    assert result.status == "not_applicable"
    assert result.qmax_score is None
    assert result.alignment_path == []


# --- the algorithm core: the absolute scale and the stretching steps ---------


def _synthetic_chromagram(frames: int = 200, seed: int = 7) -> np.ndarray:
    """A chromagram with real variability, deterministic and without downloading audio.

    The audio fixtures from conftest have four sustained chords, that is
    mutually indistinguishable frames - the sieve then picks among ties and no
    number from that material says anything about the scale. Here the chord
    changes every eight frames, frames within a chord differ by noise, and
    smoothing over time gives transitions instead of jumps. This is the material
    Serra's method is supposed to work on, and on it assertions on an absolute
    value are allowed.
    """
    rng = np.random.default_rng(seed)
    templates, _ = h._chord_templates()
    columns = []
    for start in range(0, frames, 8):
        template = templates[rng.integers(len(templates))]
        length = min(8, frames - start)
        block = template[:, None] + rng.normal(0.0, 0.18, size=(12, length))
        columns.append(np.clip(block, 0.0, None))
    raw = np.concatenate(columns, axis=1)
    kernel = np.array([0.25, 0.5, 0.25])
    smoothed = np.stack([np.convolve(row, kernel, mode="same") for row in raw])
    norms = np.linalg.norm(smoothed, axis=0, keepdims=True)
    return (smoothed / np.where(norms > 1e-9, norms, 1.0)).astype(np.float32)


def _unrelated_chromagram(frames: int = 200, seed: int = 99) -> np.ndarray:
    """Chroma with no harmonic structure at all. The negative control on the calibrated scale.

    `_synthetic_chromagram` drawn from a second seed is NOT a model of a second
    recording: both draws come from the same twenty-four chord templates in the
    same eight-frame blocks, so a third of their frames are near-identical and
    the pair scores far above what two real unrelated recordings score. The
    calibration run measured that gap directly - 541 pairs of unrelated real
    works have a median qmax of 0.072 and a maximum of 0.222 at the calibrated
    sieve, while two draws of the toy generator reach 0.338
    (docs/calibration-harmonic.md).

    Frames drawn independently carry no vocabulary to share, and their mutual
    cosine (about 0.69) is close to what two real recordings show (0.78), so
    this is the material on which an assertion against VERSION_QMAX means
    something.
    """
    rng = np.random.default_rng(seed)
    columns = np.abs(rng.normal(size=(12, frames)))
    return (columns / np.linalg.norm(columns, axis=0, keepdims=True)).astype(np.float32)


def _stretch(chromagram: np.ndarray, factor: float) -> np.ndarray:
    """A stretch in time, that is a cover at a different tempo."""
    frames = int(round(chromagram.shape[1] * factor))
    old = np.linspace(0.0, 1.0, chromagram.shape[1])
    new = np.linspace(0.0, 1.0, frames)
    stretched = np.stack([np.interp(new, old, row) for row in chromagram])
    norms = np.linalg.norm(stretched, axis=0, keepdims=True)
    return (stretched / np.where(norms > 1e-9, norms, 1.0)).astype(np.float32)


def test_a_cover_with_a_different_tempo_and_key_crosses_the_version_threshold():
    """The heart of the detector: the same track 40 percent slower and 4 semitones higher.

    This test defends three things at once and each of them is critical on its own:

    1. The (2,1) and (1,2) steps in the recursion. With a 1.4x stretch the path
       has a slope of 1.4, so the diagonal alone loses the alignment after a few
       frames and the score drops to a fraction. A "diagonal only" version fails
       this test immediately, while passing the whole rest of the suite.
    2. The absolute scale. As long as no assertion touches VERSION_QMAX, nobody
       knows whether a real cover fits anywhere near 0.55, that is whether the
       whole VERSION branch is not dead.
    3. Detecting a transposition without key detection, on material that has
       real variability rather than four states.
    """
    semitones = 4
    query = _synthetic_chromagram(frames=200)
    cover = np.roll(_stretch(query, 1.4), semitones, axis=0)

    result = h.qmax(query, cover)

    assert result.qmax_score > config.THRESHOLDS["VERSION_QMAX"].value
    assert result.transposition == semitones
    assert result.tempo_ratio is not None
    assert 1.3 < result.tempo_ratio < 1.5
    assert result.coverage > config.THRESHOLDS["VERSION_COVERAGE"].value


def test_the_diagonal_alone_is_not_enough_for_a_cover_at_a_different_tempo():
    """The control for the above: without the stretching steps the score collapses.

    The recursion run with the single step (1,1) on the same material has to
    give a score far below the VERSION threshold. If it gave a similar one, the
    previous test would defend nothing.
    """
    query = _synthetic_chromagram(frames=200)
    cover = np.roll(_stretch(query, 1.4), 4, axis=0)

    matrix = h.similarity_matrix(query, np.roll(cover, -4, axis=0))
    R = h._binarise(matrix)
    Q_full, _ = h._cumulative_alignment(R)
    Q_diagonal = _diagonal_only(R)
    divisor = min(query.shape[1], cover.shape[1])

    assert float(Q_diagonal) / divisor < config.THRESHOLDS["VERSION_QMAX"].value
    assert float(Q_full.max()) > 2.0 * float(Q_diagonal)


def _diagonal_only(R: np.ndarray) -> float:
    """The longest contiguous run along a diagonal, that is the recursion without the (2,1) and (1,2) steps."""
    best = 0.0
    for start in range(-R.shape[0] + 1, R.shape[1]):
        current = 0.0
        for value in np.diagonal(R, offset=start):
            current = current + 1.0 if value else 0.0
            best = max(best, current)
    return best


def test_two_segments_across_a_gap_do_not_add_up_to_a_cover():
    """The gap penalties: two short quotes inside alien material are not a cover.

    Without penalties the recursion degenerates into LCS and adds up both
    matched segments across a hundred and sixty frames of alien material,
    reporting a cover where there is none.

    The candidate is 80% alien and carries two ten-second quotes. The earlier
    version of this fixture was 60% query - a candidate that reuses three fifths
    of the query verbatim, which the detector is RIGHT to score high, so the
    fixture was proving the opposite of its own docstring the moment the sieve
    stopped clipping every diagonal. The filler is structureless chroma for the
    same reason `_unrelated_chromagram` exists: the toy chord vocabulary carries
    a chance floor of 0.338 at the calibrated sieve, which would swamp the
    effect being measured.
    """
    query = _synthetic_chromagram(frames=200, seed=7)
    filler = _unrelated_chromagram(frames=160, seed=99)
    candidate = np.concatenate(
        [query[:, :20], filler, query[:, 180:]], axis=1
    )

    with_penalties = h.qmax(query, candidate)
    without_penalties = h.qmax(
        query, candidate, params=h.QmaxParams(gamma_onset=0.0, gamma_extension=0.0)
    )

    assert with_penalties.qmax_score < without_penalties.qmax_score
    assert with_penalties.qmax_score < config.THRESHOLDS["VERSION_QMAX"].value
    # The other half of the claim, which the previous version did not make: it
    # is the penalty that keeps this below the threshold, not the material.
    # Summing the two quotes across the gap crosses it.
    assert without_penalties.qmax_score > config.THRESHOLDS["VERSION_QMAX"].value


def test_alien_material_stays_far_below_the_version_threshold():
    """The other side of the scale assertion: the threshold has to filter something out, not just let things through.

    Two negative controls, because they measure different things.

    The first is the same material as in the cover test from a different seed.
    It scores 0.338 at the calibrated sieve, against 1.000 for the cover - the
    ordering the detector exists for. That number is ABOVE VERSION_QMAX, and
    that is a property of the fixture rather than of the detector: 541 pairs of
    unrelated real works measured on 2026-08-26 have a median of 0.072 and a
    maximum of 0.222, so real recordings sit at a fifth of what two draws of the
    toy generator reach. Twenty-four chord templates in eight-frame blocks are
    simply not two different pieces of music. The 0.4 bar is kept as it was.

    The second is material with no vocabulary to share, and it is the one that
    may be held against the calibrated threshold - see `_unrelated_chromagram`.
    """
    query = _synthetic_chromagram(frames=200, seed=7)
    alien = _synthetic_chromagram(frames=200, seed=99)
    unrelated = _unrelated_chromagram(frames=200, seed=99)

    assert h.qmax(query, alien).qmax_score < 0.4
    assert h.qmax(query, unrelated).qmax_score < config.THRESHOLDS["VERSION_QMAX"].value


def test_the_sieve_is_a_parameter_not_a_module_constant():
    """Section 9.2: it is the sieve, not the threshold, that decides the distribution of qmax_score."""
    query = _synthetic_chromagram(frames=120)
    alien = _synthetic_chromagram(frames=120, seed=99)

    tight = h.qmax(query, alien, params=h.QmaxParams(percentile=2.0))
    loose = h.qmax(query, alien, params=h.QmaxParams(percentile=30.0))
    assert loose.qmax_score > tight.qmax_score


# --- pre-filtering, cache and the detector envelope -------------------------


def _candidate(number: int, path: str) -> Candidate:
    return Candidate(
        id=f"cand_{number:02d}",
        name=f"candidate {number}",
        artist="test",
        source_url="https://example.invalid/track",
        audio_path=str(path),
    )


def test_the_detector_is_on_level_one():
    assert h.HarmonicDetector.level == 1
    assert h.HarmonicDetector.name == "harmonic"


def test_the_envelope_has_a_result_for_every_candidate(chord_wav, noise_wav):
    envelope = h.HarmonicDetector().run(
        ingest.load_clip(chord_wav),
        [_candidate(0, chord_wav), _candidate(1, noise_wav)],
    )
    assert envelope.detector == "harmonic"
    assert envelope.status == "ok"
    assert [r.candidate_id for r in envelope.results] == ["cand_00", "cand_01"]


def test_the_matrix_is_computed_only_for_the_shortlist(chord_wav, noise_wav):
    """Section 7.2: the full matrix is O(n*m), so we compute it only for the top N."""
    envelope = h.HarmonicDetector().run(
        ingest.load_clip(chord_wav),
        [_candidate(0, noise_wav), _candidate(1, chord_wav)],
        shortlist_size=1,
    )
    computed = [r for r in envelope.results if r.status == "ok"]
    filtered_out = [r for r in envelope.results if r.status == "not_applicable"]
    assert [r.candidate_id for r in computed] == ["cand_01"]
    assert [r.candidate_id for r in filtered_out] == ["cand_00"]
    assert filtered_out[0].qmax_score is None
    assert filtered_out[0].alignment_path == []
    assert filtered_out[0].reason


def test_a_missing_candidate_file_does_not_bring_the_envelope_down(chord_wav, tmp_path):
    envelope = h.HarmonicDetector().run(
        ingest.load_clip(chord_wav),
        [_candidate(9, tmp_path / "no-such-file.wav")],
    )
    assert envelope.status == "ok"
    assert envelope.results[0].status == "failed"
    assert envelope.results[0].qmax_score is None


def test_the_candidate_representation_is_loaded_from_the_cache(chord_wav, tmp_path, monkeypatch):
    """The CQT is expensive, so candidate representations live in the cache directory."""
    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "cache"))
    first = h.representation(chord_wav)
    assert h.cache_path(chord_wav).exists()
    second = h.representation(chord_wav)
    assert np.array_equal(first.chroma, second.chroma)
    assert np.array_equal(first.descriptor, second.descriptor)
    assert first.chord_sequence == second.chord_sequence


def test_the_cache_directory_listens_to_the_same_variable_as_detector_a(tmp_path, monkeypatch):
    """Two conventions would mean ORIGIN_CACHE_DIR redirects only one detector."""
    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "elsewhere"))
    assert h.cache_path("data/audio/x.wav").parent == tmp_path / "elsewhere"


def test_the_cache_key_covers_parameters_from_another_module(chord_wav, monkeypatch):
    """Chroma depends on ingest and config constants, so they have to sit in the key."""
    before = h.cache_path(chord_wav)
    monkeypatch.setattr(h.config, "SR_HARMONIC", 44100)
    assert h.cache_path(chord_wav) != before
    monkeypatch.setattr(h, "HOP_LENGTH", 4096)
    assert h.cache_path(chord_wav) != before


def test_a_corrupt_npz_does_not_bring_the_envelope_down(chord_wav, tmp_path, monkeypatch):
    """A truncated npz starts with a zip header, so numpy raises BadZipFile."""
    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "cache"))
    file = h.cache_path(chord_wav)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"PK\x03\x04 truncated halfway through the write")

    envelope = h.HarmonicDetector().run(
        ingest.load_clip(chord_wav), [_candidate(0, chord_wav)]
    )
    assert envelope.status == "ok"
    assert envelope.results[0].status == "ok"


def test_prewarm_warms_the_cache_before_the_live_path(chord_wav, tmp_path, monkeypatch):
    """Section 4: candidate representations are level 0, offline, not 5 s live."""
    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "cache"))
    assert not h.cache_path(chord_wav).exists()

    errors = h.prewarm([_candidate(0, chord_wav)])
    assert errors == {}
    assert h.cache_path(chord_wav).exists()


def test_prewarm_reports_candidates_without_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "cache"))
    errors = h.prewarm([_candidate(9, tmp_path / "no-such-file.wav")])
    assert list(errors) == ["cand_09"]


def test_the_detector_satisfies_the_protocol_from_base():
    from origin.detectors import base

    assert isinstance(h.HarmonicDetector(), base.Detector)


def test_the_chord_sequence_is_empty_when_nothing_matched(chord_wav):
    """Section 8 asks about the pattern that actually matched, so without a path it is empty."""
    c = h.chroma(ingest.load_clip(chord_wav))
    result = h.qmax(c, np.zeros((12, 8), dtype=np.float32))
    assert result.alignment_path == []
    assert result.chord_sequence == []
