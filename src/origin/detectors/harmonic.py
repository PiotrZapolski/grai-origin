"""Detector B - harmonic similarity. Section 7.2 of the specification.

This is the cover detector and the only component that answers the question "is
this the same work in a different performance". Four things are the heart of it
and none of them may be simplified:

1. We do not transpose to a detected key. Key detection is unreliable, and its
   error would propagate to the whole result. We compute the similarity for all
   12 rotations of the chroma vector and take the maximum. The returned
   rotation is ready-made "transposed by N semitones" information for the
   interface.
2. A diagonal path, not a correlation. A cover has a different tempo, so the
   similarity path is not parallel to the diagonal but slanted and locally
   disturbed. Cumulative alignment along diagonals (Serra's Qmax variant)
   absorbs that, a correlation does not. A correlation here strips the detector
   of its only function.
3. coverage tells VERSION apart from EXCERPT. Fusion (9.1) bases the choice of
   class on that number, so it must mean exactly what it promises.
4. The similarity matrix is an interface artifact, not an intermediate step.
   Rendered as a heatmap with the alignment path drawn on it, it is the most
   visually convincing piece of evidence in the system and costs nothing extra.

Pre-filtering with the global descriptor is a feasibility condition: the full
matrix is O(n*m) and we compute it only for the shortlist, never for all
candidates.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import librosa
import numpy as np
from scipy.ndimage import median_filter

from origin import cache, config, ingest
from origin.contracts import Candidate, DetectorEnvelope, HarmonicResult
from origin.detectors import base
from origin.ingest import Clip

__all__ = [
    "chroma",
    "global_descriptor",
    "similarity_matrix",
    "qmax",
    "chord_sequence",
    "shortlist",
    "representation",
    "prewarm",
    "cache_path",
    "QmaxParams",
    "DEFAULT_PARAMS",
    "Representation",
    "HarmonicDetector",
]

# --- feature parameters (section 7.2) ---------------------------------------

BINS_PER_OCTAVE = 12
N_OCTAVES = 6
FMIN_NOTE = "C1"
# A hop of 2048 samples at 22050 Hz is 0.093 s, that is the "~0.1 s" promised
# in the specification. A power of two is required by the recursive decimation
# inside the CQT.
HOP_LENGTH = 2048
# Median smoothing over time knocks down transient percussive artefacts, which
# carry no harmonic information.
MEDIAN_FRAMES = 5
TARGET_RATE_HZ = 2.0

# --- global descriptor parameters -------------------------------------------

DESCRIPTOR_FRAMES = 64
DESCRIPTOR_PITCH_BINS = 8
DESCRIPTOR_TIME_BINS = 32
DESCRIPTOR_DIM = DESCRIPTOR_PITCH_BINS * DESCRIPTOR_TIME_BINS  # 256

# --- Qmax alignment parameters ----------------------------------------------

# Section 7.2: "binarised with a percentile threshold (typically the 10th
# percentile of distances)". The percentile is computed per row AND per column,
# that is by mutual neighbourhood, exactly as in Serra's original construction.
# A global percentile alone lets whole rows and columns through at once when
# one of the recordings has frames similar to everything (noise, silence, a
# drone), and a horizontal line is not an alignment.
#
# CALIBRATED ON REAL AUDIO, 2026-08-26, 542 pairs (docs/calibration-harmonic.md):
# one real cover pair and 541 pairs of unrelated works taken from the 291-track
# IDF corpus. The specification's "typically the 10th percentile" comes from
# Serra's work on studio material and does not survive real covers: at 10 the
# only real cover in the set scores 0.028 while the WORST of the 541 unrelated
# pairs scores 0.057, that is the sieve orders a cover BELOW noise (AUC 0.748).
# At 30 the same cover scores 0.293 against a negative median of 0.072 and a
# negative maximum of 0.222 - AUC 1.000, d' 8.53, the best standardised
# separation on the whole grid, and 0 of 541 unrelated pairs cross the
# VERSION rule (qmax > 0.25 AND coverage > 0.50), that is precision 1.00 on
# the measured set.
#
# 40 gives a wider gap in raw qmax (0.494 against a negative maximum of 0.321)
# and was rejected on coverage: at 40 the sieve inflates the alignment path
# until 36.6% of UNRELATED pairs reach coverage above 0.50 and 56.9% above
# 0.40, so `coverage` stops separating anything and both rule 4 (coverage >
# 0.50) and rule 5 (coverage < 0.40) of section 9.1 lose their meaning. At 30
# only 2.0% of unrelated pairs pass coverage 0.50. A number that appears in the
# verdict as evidence has to be evidence.
BINARISATION_PERCENTILE = 30.0
# Penalty for opening a gap in the path and for extending it. Values from
# Serra's paper on cross recurrence quantification.
GAMMA_ONSET = 5.0
GAMMA_EXTENSION = 0.5
# Numeric tolerance when comparing against the threshold: the distance of a
# frame from itself is sometimes 1.1e-16 instead of zero, and without this it
# would drop off its own diagonal.
TOLERANCE = 1e-9

# Layout of fields in the npz file. The only thing in the cache key under the
# control of this module - the rest of the key is a hash of the actual
# parameters, see _representation_parameters.
NPZ_LAYOUT = "harmonic-npz-1"


@dataclass(frozen=True)
class QmaxParams:
    """The binarisation sieve and the alignment penalties. The most important knob in the detector.

    It is this sieve, not the `VERSION_QMAX` threshold, that decides the
    distribution of `qmax_score`: too tight and it clips the real diagonal, too
    loose and it lets the negative control through, and calibrating the
    threshold will not repair a badly scaled distribution. That is why the
    percentile and both gammas are a parameter one can run a sweep over, rather
    than a constant compiled into the recursion.

    - `percentile`: the distance percentile in the mutual-neighbourhood sieve,
    - `gamma_onset`: the penalty for opening a gap in the path,
    - `gamma_extension`: the penalty for extending an already open gap.
    """

    percentile: float = BINARISATION_PERCENTILE
    gamma_onset: float = GAMMA_ONSET
    gamma_extension: float = GAMMA_EXTENSION


DEFAULT_PARAMS = QmaxParams()

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


# --- features ---------------------------------------------------------------


def _aggregate(c: np.ndarray, factor: int) -> np.ndarray:
    """Averages neighbouring frames down to the target ~2 Hz."""
    if factor <= 1 or c.shape[1] == 0:
        return c
    full = c.shape[1] // factor
    if full == 0:
        return c.mean(axis=1, keepdims=True)
    head = c[:, : full * factor].reshape(c.shape[0], full, factor).mean(axis=2)
    tail = c[:, full * factor :]
    if tail.shape[1] == 0:
        return head
    return np.concatenate([head, tail.mean(axis=1, keepdims=True)], axis=1)


def _normalise_l2(c: np.ndarray) -> np.ndarray:
    """L2 normalisation of every frame. A frame without energy stays zero.

    Thanks to that the dot product of two frames is directly a cosine and the
    similarity matrix is computed with a single matrix multiplication.
    """
    norms = np.linalg.norm(c, axis=0, keepdims=True)
    empty = norms <= 1e-8
    result = c / np.where(empty, 1.0, norms)
    result[:, empty[0]] = 0.0
    return result.astype(np.float32)


def chroma(clip: Clip) -> np.ndarray:
    """The chromagram of the query or of a candidate. Shape (12, frame_count).

    CQT with 12 bins per octave from C1, 6 octaves -> pitch-class profile ->
    median smoothing over time -> aggregation to ~2 Hz -> L2 normalisation of
    every frame.
    """
    y = np.asarray(clip.y_harmonic, dtype=np.float32)
    sr = int(clip.sr_harmonic)
    if y.size == 0:
        return np.zeros((12, 0), dtype=np.float32)

    c = librosa.feature.chroma_cqt(
        y=y,
        sr=sr,
        hop_length=HOP_LENGTH,
        fmin=librosa.note_to_hz(FMIN_NOTE),
        n_octaves=N_OCTAVES,
        bins_per_octave=BINS_PER_OCTAVE,
        n_chroma=12,
    )
    c = median_filter(c, size=(1, MEDIAN_FRAMES), mode="nearest")
    factor = max(1, int(round((sr / HOP_LENGTH) / TARGET_RATE_HZ)))
    return _normalise_l2(_aggregate(c, factor))


def _rescale_time(c: np.ndarray, count: int) -> np.ndarray:
    """Interpolates the chromagram onto a fixed frame grid.

    A fixed grid gives the descriptor independence from the recording length
    and from the global tempo, which is exactly what cover pre-filtering needs.
    """
    if c.shape[1] == count:
        return c
    if c.shape[1] == 1:
        return np.repeat(c, count, axis=1)
    old = np.linspace(0.0, 1.0, c.shape[1])
    new = np.linspace(0.0, 1.0, count)
    return np.stack([np.interp(new, old, row) for row in c])


def global_descriptor(chromagram: np.ndarray) -> np.ndarray:
    """A cheap global descriptor for pre-filtering. A 256-dimensional vector.

    A 2D DFT of the chromagram, magnitude, flatten, normalise. The magnitude
    along the pitch-class axis gives invariance to transposition, the magnitude
    along the time axis gives invariance to a shift in time - both are wanted
    here, because pre-filtering has to let a cover in a different key through
    rather than reject it before the matrix is computed.

    The DC component is zeroed. After L2 normalisation of the frames it carries
    only the frame count, so leaving it in would dominate the cosine comparison
    and every piece of material would look similar to every other.
    """
    c = np.asarray(chromagram, dtype=np.float64)
    if c.ndim != 2 or c.shape[0] != 12 or c.shape[1] == 0:
        return np.zeros(DESCRIPTOR_DIM, dtype=np.float32)

    spectrum = np.abs(np.fft.fft2(_rescale_time(c, DESCRIPTOR_FRAMES)))
    block = np.array(spectrum[:DESCRIPTOR_PITCH_BINS, :DESCRIPTOR_TIME_BINS], dtype=np.float64)
    block[0, 0] = 0.0
    vector = np.log1p(block).ravel()
    vector -= vector.mean()
    norm = float(np.linalg.norm(vector))
    if norm > 1e-12:
        vector /= norm
    return vector.astype(np.float32)


def _chord_templates() -> tuple[np.ndarray, list[str]]:
    templates: list[np.ndarray] = []
    names: list[str] = []
    for i, note in enumerate(NOTES):
        for suffix, intervals in (("", (0, 4, 7)), ("m", (0, 3, 7))):
            vector = np.zeros(12, dtype=np.float64)
            for interval in intervals:
                vector[(i + interval) % 12] = 1.0
            templates.append(vector / np.linalg.norm(vector))
            names.append(note + suffix)
    return np.stack(templates), names


_TEMPLATES, _CHORD_NAMES = _chord_templates()


def chord_sequence(chromagram: np.ndarray) -> list[str]:
    """The chord sequence that feeds the commonality filter from section 8.

    Major and minor templates are matched against every frame, then adjacent
    repetitions are merged. The filter computes the IDF of n-grams of this
    sequence, so what interests it is the progression, not how many frames each
    chord lasted: without merging, every n-gram would be dominated by
    repetitions of a single chord.
    """
    c = np.asarray(chromagram, dtype=np.float64)
    if c.ndim != 2 or c.shape[0] != 12 or c.shape[1] == 0:
        return []
    norms = np.linalg.norm(c, axis=0)
    hits = (_TEMPLATES @ c).argmax(axis=0)

    sequence: list[str] = []
    for frame, index in enumerate(hits):
        if norms[frame] <= 1e-8:
            continue
        label = _CHORD_NAMES[int(index)]
        if not sequence or sequence[-1] != label:
            sequence.append(label)
    return sequence


# --- similarity matrix and alignment ----------------------------------------


def similarity_matrix(chroma_a: np.ndarray, chroma_b: np.ndarray) -> np.ndarray:
    """The cross-similarity matrix, query frames in the rows.

    The frames are L2 normalised, so the dot product is directly a cosine. This
    same matrix is the heatmap on screen E4 - it is not an intermediate step to
    be thrown away once the score is computed.
    """
    return np.asarray(chroma_a, dtype=np.float32).T @ np.asarray(chroma_b, dtype=np.float32)


def _binarise(
    matrix: np.ndarray,
    params: QmaxParams = DEFAULT_PARAMS,
    valid: np.ndarray | None = None,
) -> np.ndarray:
    """Mutual percentile neighbourhood over distances (1 - cosine).

    The sieve is calibrated for full-length material and for REAL
    performances: two recordings of the same work share a chord progression,
    not a chroma trajectory, so frame-to-frame distances between a cover and
    its original are far larger than between a recording and a transformed copy
    of itself. The percentile that survives that is 30, measured on 542 pairs
    (docs/calibration-harmonic.md); the 10 the specification suggests clips the
    real diagonal down to a few frames and orders a genuine cover below an
    unrelated track.

    The sieve is scale-free: it keeps a fixed FRACTION of the cells whatever
    the material, so every percentile carries a chance floor - a score two
    unrelated sequences reach by chaining accidents alone. Measured on
    structureless chroma: 0.02 at 10, 0.08 at 30, 0.32 at 40, 0.54 at 50 and
    0.76 at 60. Above 40 most of the number is that floor rather than an
    alignment, which is the second reason the sweep stopped at 30.

    Short material is a different regime and still does not scale: with a dozen
    frames of sustained chords the real band occupies a fifth of the matrix, so
    numbers from few-second fragments should be read as ordering, not as
    comparable with the VERSION_QMAX threshold.
    """
    distance = 1.0 - matrix
    row_threshold = np.percentile(distance, params.percentile, axis=1, keepdims=True)
    column_threshold = np.percentile(distance, params.percentile, axis=0, keepdims=True)
    R = (distance <= row_threshold + TOLERANCE) & (distance <= column_threshold + TOLERANCE)
    if valid is not None:
        # A frame without energy has a cosine of zero with every other frame,
        # so its row is flat and the percentile lets it through whole. Without
        # this mask a candidate made entirely of silence would get a
        # qmax_score of 1.0 against any query - the worst possible false alarm
        # in an evidentiary tool.
        R &= valid
    return R


def _shift(vector: np.ndarray, by: int) -> np.ndarray:
    """result[j] = vector[j - by], with zeros before the start."""
    result = np.zeros_like(vector)
    if by < vector.size:
        result[by:] = vector[: vector.size - by]
    return result


# The three allowed backward steps: (1,1) along the diagonal, (2,1) and (1,2)
# for local tempo differences. The order matters - argmax breaks a tie in
# favour of the diagonal, that is alignment without stretching.
_STEPS = ((1, 1), (2, 1), (1, 2))


def _cumulative_alignment(
    R: np.ndarray, params: QmaxParams = DEFAULT_PARAMS
) -> tuple[np.ndarray, np.ndarray]:
    """Serra's Qmax variant: cumulative alignment along diagonals.

    Q[i,j] depends only on rows i-1 and i-2, so a whole row is computed with a
    single set of numpy operations. Looping over query frames instead of over
    cells is the difference between seconds and minutes for a three-minute
    track.
    """
    N, M = R.shape
    Q = np.zeros((N, M), dtype=np.float32)
    pointer = np.zeros((N, M), dtype=np.int8)
    empty_q = np.zeros(M, dtype=np.float32)
    empty_r = np.zeros(M, dtype=bool)

    for i in range(N):
        previous_q = Q[i - 1] if i >= 1 else empty_q
        two_back_q = Q[i - 2] if i >= 2 else empty_q
        previous_r = R[i - 1] if i >= 1 else empty_r
        two_back_r = R[i - 2] if i >= 2 else empty_r

        candidates = np.stack([
            _shift(previous_q, 1),   # (i-1, j-1)
            _shift(two_back_q, 1),   # (i-2, j-1)
            _shift(previous_q, 2),   # (i-1, j-2)
        ])
        # The penalty depends on whether the predecessor was a hit: in that
        # case we are opening a gap, otherwise we are extending one.
        predecessors = np.stack([
            _shift(previous_r, 1),
            _shift(two_back_r, 1),
            _shift(previous_r, 2),
        ])
        penalties = np.where(predecessors, params.gamma_onset, params.gamma_extension)

        with_hit = candidates.max(axis=0) + 1.0
        hit_arg = candidates.argmax(axis=0)
        with_gap = candidates - penalties
        best_gap = with_gap.max(axis=0)
        gap_arg = with_gap.argmax(axis=0)
        gap_is_worth_it = best_gap > 0.0

        Q[i] = np.where(R[i], with_hit, np.where(gap_is_worth_it, best_gap, 0.0))
        pointer[i] = np.where(
            R[i],
            hit_arg + 1,
            np.where(gap_is_worth_it, gap_arg + 1, 0),
        ).astype(np.int8)

    return Q, pointer


def _reconstruct_path(Q: np.ndarray, pointer: np.ndarray) -> list[tuple[int, int]]:
    """The alignment path from the end of the best match, ready to be drawn."""
    if Q.size == 0 or float(Q.max()) <= 0.0:
        return []
    i, j = (int(x) for x in np.unravel_index(int(Q.argmax()), Q.shape))
    path: list[tuple[int, int]] = []
    while True:
        path.append((i, j))
        step = int(pointer[i, j])
        if step == 0:
            break
        di, dj = _STEPS[step - 1]
        ni, nj = i - di, j - dj
        if ni < 0 or nj < 0 or Q[ni, nj] <= 0.0:
            break
        i, j = ni, nj
    path.reverse()
    return path


@dataclass
class _Match:
    score: float
    transposition: int
    path: list[tuple[int, int]]
    matrix: np.ndarray


def _match_rotation(
    a: np.ndarray, b: np.ndarray, k: int, params: QmaxParams = DEFAULT_PARAMS
) -> _Match:
    matrix = similarity_matrix(a, np.roll(b, -k, axis=0))
    valid = (np.linalg.norm(a, axis=0) > 0.0)[:, None] & (
        np.linalg.norm(b, axis=0) > 0.0
    )[None, :]
    Q, pointer = _cumulative_alignment(_binarise(matrix, params, valid), params)
    shorter_length = min(a.shape[1], b.shape[1])
    score = float(Q.max()) / shorter_length if shorter_length else 0.0
    return _Match(
        score=min(1.0, max(0.0, score)),
        # The rotation mapped onto the range [-5, 6]: "five semitones down"
        # reads better in the interface than "seven up".
        transposition=k if k <= 6 else k - 12,
        path=_reconstruct_path(Q, pointer),
        matrix=matrix,
    )


def qmax(
    chroma_a: np.ndarray,
    chroma_b: np.ndarray,
    candidate_id: str = "",
    params: QmaxParams = DEFAULT_PARAMS,
) -> HarmonicResult:
    """Harmonic similarity of the query (a) to the candidate (b).

    It computes the alignment for all 12 rotations of the candidate's chroma
    and returns the best one. There is no key detection here and there must not
    be - see the module header.

    The heatmap for screen E4 is reconstructed from the result without
    repeating the alignment:
    similarity_matrix(chroma_a, np.roll(chroma_b, -result.transposition, axis=0))
    gives exactly the matrix the returned alignment_path lies on.
    """
    a = np.asarray(chroma_a, dtype=np.float32)
    b = np.asarray(chroma_b, dtype=np.float32)
    if a.ndim != 2 or b.ndim != 2 or a.shape[1] == 0 or b.shape[1] == 0:
        # Section 7.0: not applicable is not zero, so the result carries no
        # number at all.
        return HarmonicResult(
            candidate_id=candidate_id,
            status="not_applicable",
            reason="empty chromagram, there is nothing to align",
        )

    best = max(
        (_match_rotation(a, b, k, params) for k in range(12)),
        key=lambda m: m.score,
    )
    path = best.path

    query_frames = {i for i, _ in path}
    candidate_frames = {j for _, j in path}
    # coverage: the share of material lying on the alignment path, computed on
    # both sides and taken as the smaller of the two. The query fraction alone
    # would return 1.0 for a ten-second snippet fully explained by three
    # minutes of the candidate, that is it would mark a borrowed fragment as a
    # cover of the whole track - exactly the confusion of EXCERPT with VERSION
    # that this number is meant to prevent (sections 7.2 and 9.1).
    coverage = min(len(query_frames) / a.shape[1], len(candidate_frames) / b.shape[1])

    tempo = None
    if len(path) >= 2:
        query_span = path[-1][0] - path[0][0]
        if query_span > 0:
            # How much candidate time falls on one unit of query time: 1.06
            # means the candidate flows 6 percent slower than the query.
            tempo = (path[-1][1] - path[0][1]) / query_span

    # Section 8 asks about the pattern that ACTUALLY matched. Without a path
    # none did, so the field stays empty. Returning the query's whole
    # progression would be the same lie the 7.0 contract defends against, only
    # smuggled through a non-measurement field - and that is what we would feed
    # the IDF filter with.
    segment = a[:, path[0][0] : path[-1][0] + 1] if path else a[:, :0]
    return HarmonicResult(
        candidate_id=candidate_id,
        qmax_score=best.score,
        transposition=best.transposition,
        tempo_ratio=tempo,
        alignment_path=path,
        coverage=coverage,
        chord_sequence=chord_sequence(segment),
    )


# --- candidate representations and cache ------------------------------------


@dataclass
class Representation:
    """The representation of one recording. The CQT is expensive, so it lives in the cache."""

    chroma: np.ndarray
    descriptor: np.ndarray
    chord_sequence: list[str] = field(default_factory=list)


def _representation_parameters() -> tuple[object, ...]:
    """The ACTUAL parameters the stored representation depends on.

    Not a version literal to bump by hand. The chromagram depends not only on
    this module's constants but also on ingest and config constants, which live
    in someone else's module and whose change has no reason at all to touch a
    constant here. The hashed tuple invalidates the cache on its own - the only
    manual element is the layout of fields in the npz, because that is the only
    thing under this module's control.
    """
    return (
        NPZ_LAYOUT,
        BINS_PER_OCTAVE, N_OCTAVES, FMIN_NOTE, HOP_LENGTH,
        MEDIAN_FRAMES, TARGET_RATE_HZ,
        DESCRIPTOR_FRAMES, DESCRIPTOR_PITCH_BINS, DESCRIPTOR_TIME_BINS,
        config.SR_HARMONIC, config.MAX_DURATION_S, config.TARGET_LUFS,
        config.WINDOW_S, config.HOP_S, config.TRIM_TOP_DB,
    )


def cache_path(audio_path: str | Path) -> Path:
    """Path of the npz file with the representation. The key convention lives in `origin.cache`."""
    return cache.artifact_path("harm", audio_path, _representation_parameters())


def _load_from_cache(file: Path) -> Representation | None:
    data = cache.load_npz(file, ("chroma", "descriptor", "chords"))
    if data is None:
        return None
    return Representation(
        chroma=np.asarray(data["chroma"], dtype=np.float32),
        descriptor=np.asarray(data["descriptor"], dtype=np.float32),
        chord_sequence=[str(x) for x in data["chords"]],
    )


def _save_to_cache(file: Path, representation_to_save: Representation) -> None:
    cache.save_npz(
        file,
        {
            "chroma": representation_to_save.chroma,
            "descriptor": representation_to_save.descriptor,
            # Chords travel as an array of strings, because npz does not know
            # Python lists and allow_pickle is switched off on read.
            "chords": np.array(representation_to_save.chord_sequence, dtype="<U8"),
        },
        compressed=True,
    )


def representation(audio_path: str | Path) -> Representation:
    """The chromagram, descriptor and chord sequence of a recording, cached in data/cache."""
    file = cache_path(audio_path)
    stored = _load_from_cache(file)
    if stored is not None:
        return stored

    c = chroma(ingest.load_clip(str(audio_path)))
    computed = Representation(
        chroma=c,
        descriptor=global_descriptor(c),
        chord_sequence=chord_sequence(c),
    )
    _save_to_cache(file, computed)
    return computed


def _compute_representations(
    candidates: Sequence[Candidate],
) -> tuple[dict[str, Representation], dict[str, str]]:
    """Representations of the whole candidate set, in parallel, skipping the ones already stored."""
    representations: dict[str, Representation] = {}
    errors: dict[str, str] = {}
    if not candidates:
        return representations, errors

    with ThreadPoolExecutor(max_workers=config.worker_count()) as pool:
        submissions = {
            pool.submit(representation, candidate.audio_path): candidate
            for candidate in candidates
        }
        for submission, candidate in submissions.items():
            try:
                representations[candidate.id] = submission.result()
            except Exception as error:  # noqa: BLE001 - no audio means no measurement
                errors[candidate.id] = f"{type(error).__name__}: {error}"
    return representations, errors


def prewarm(candidates: Sequence[Candidate]) -> dict[str, str]:
    """Computes and stores candidate representations up front. Level 0, offline.

    Section 4 puts candidate representations at level zero, before the demo,
    and not without reason: computed lazily in the live path, with a cold cache
    for twenty candidates they eat a dozen or so seconds exactly where we
    promise five. The level 1 budget holds only with a warm cache, so something
    has to warm it up.

    Returns a map identifier -> reason for candidates that could not be
    computed. An empty map means the cache is warm throughout.
    """
    _, errors = _compute_representations(candidates)
    return errors


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if norm <= 1e-12:
        return 0.0
    return float(a @ b) / norm


def shortlist(
    query_descriptor: np.ndarray,
    descriptors: dict[str, np.ndarray],
    size: int | None = None,
) -> list[str]:
    """Pre-filtering. Returns candidate identifiers in descending order.

    Section 7.2: the full matrix is O(n*m) and with the full candidate set it
    will not fit in the level 1 budget, so we compute the matrix only for what
    passes through this sieve.
    """
    count = config.SHORTLIST_SIZE if size is None else size
    ranked = sorted(
        descriptors.items(),
        key=lambda pair: _cosine(query_descriptor, pair[1]),
        reverse=True,
    )
    return [identifier for identifier, _ in ranked[: max(0, count)]]


# --- detector envelope ------------------------------------------------------


class HarmonicDetector:
    """Detector B. Level 1, a 5 s budget shared with the rest of the level.

    It does not register itself - the code that builds the pipeline wires it in
    (section 7.0). `params` is passed down to the alignment, so that a sweep
    over the sieve can be run on the whole detector rather than on bare `qmax`
    alone.
    """

    name = "harmonic"
    level = 1

    def __init__(self, params: QmaxParams = DEFAULT_PARAMS) -> None:
        self.params = params

    def run(
        self,
        clip: Clip,
        candidates: Sequence[Candidate],
        context: base.Context | None = None,
        *,
        shortlist_size: int | None = None,
    ) -> DetectorEnvelope:
        """The detector envelope. Section 9.1: a failure must not bring the analysis down.

        The whole pass - features, descriptor, pre-filtering, cache reads and
        alignment - goes under `base.run_guarded`, which turns any exception
        into a `failed` envelope with a reason. The only thing left outside the
        guard is the check whether the query carries any signal at all, because
        that is the only case in which the envelope should be `not_applicable`
        rather than `failed`.

        We accept `context` for compatibility with the protocol from `base` and
        do not read it: section 7.2 places no neighbour-dependent rule in this
        detector. The pipeline calls all detectors the same way, so the third
        positional argument has to mean the same thing everywhere.
        """
        if not np.asarray(clip.y_harmonic).size:
            return base.empty_envelope(
                self.name, "not_applicable", "the query has no harmonic material"
            )
        return base.run_guarded(
            self.name, lambda: self._run(clip, candidates, shortlist_size)
        )

    def _run(
        self,
        clip: Clip,
        candidates: Sequence[Candidate],
        shortlist_size: int | None,
    ) -> list[HarmonicResult]:
        query_chroma = chroma(clip)
        if query_chroma.shape[1] == 0:
            return [
                HarmonicResult(
                    candidate_id=candidate.id,
                    status="not_applicable",
                    reason="the query has no harmonic material",
                )
                for candidate in candidates
            ]

        query_descriptor = global_descriptor(query_chroma)
        representations, errors = _compute_representations(candidates)

        passed = set(
            shortlist(
                query_descriptor,
                {k: r.descriptor for k, r in representations.items()},
                shortlist_size,
            )
        )

        results: list[HarmonicResult] = []
        for candidate in candidates:
            if candidate.id in errors:
                results.append(HarmonicResult(
                    candidate_id=candidate.id,
                    status="failed",
                    reason=errors[candidate.id],
                ))
            elif candidate.id in passed:
                results.append(qmax(
                    query_chroma,
                    representations[candidate.id].chroma,
                    candidate_id=candidate.id,
                    params=self.params,
                ))
            else:
                # Section 7.0: zero would mean "we checked and there is no
                # similarity", whereas we deliberately did not compute the
                # matrix.
                results.append(HarmonicResult(
                    candidate_id=candidate.id,
                    status="not_applicable",
                    reason="filtered out by the global descriptor before the matrix was computed",
                ))
        return results
