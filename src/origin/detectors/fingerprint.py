"""Detector A: landmark-style acoustic fingerprint. Section 7.1.

Wang's spectral landmarks: STFT, local maxima, pairing an anchor with peaks
from a target zone, a hash from the triple (f1, f2, dt). Matching is a
histogram of offset differences - simultaneously a significance test and a
determination of the time alignment. A real hit produces a sharp bin, because
many hashes share THE SAME offset difference; random coincidences spread out
flat.

Time everywhere in this module is the time of the SOURCE RECORDING, not of the
trimmed clip. Ingest cuts silence and picks the highest-energy fragment, so
almost every clip has a non-zero `source_offset_s`. A span measured in clip
time would point A/B playback at a different place in the recording than the
one that actually matched.

The grid of 143 transformations does not run by itself. `match` does not see
it. `match_transformed` is called only explicitly and only when matching
without a transformation failed while the harmonic detector returned a high
similarity - the condition from 7.1 is implemented by
`FingerprintDetector.run` through the context.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import librosa
import numpy as np
from scipy.ndimage import maximum_filter

from origin import cache, config, ingest
from origin.contracts import Candidate, DetectorEnvelope, FingerprintResult
from origin.detectors import base
from origin.ingest import Clip

__all__ = [
    "Fingerprint",
    "build_index",
    "cache_path",
    "fingerprint_of",
    "landmarks",
    "load_index",
    "match",
    "match_transformed",
    "prewarm",
    "FingerprintDetector",
]


# --- parameters from section 7.1, values taken literally ---------------------

N_FFT = 2048
HOP = 512
PEAKS_PER_SECOND = 40          # spec: 30-50 peaks per second
FAN_OUT = 5                    # spec: 5 peaks in the target zone
TARGET_ZONE_S = 2.0            # spec: target zone within a 2 s window

# A local maximum is computed over a time-frequency window. The frequency
# neighbourhood must be narrower than the spacing between the components of a
# chord, otherwise a single filter swallows three partials and leaves one peak.
NEIGHBOURHOOD_BINS = 9
NEIGHBOURHOOD_FRAMES = 5
# Threshold relative to the spectrogram peak. It cuts off quantisation noise,
# which carries no repeatable information but at 40 peaks per second could
# crowd real components out of the list.
THRESHOLD_DB = -60.0

# Frequency quantisation is done on a logarithmic scale so that shifting by a
# semitone is an ADDITION of a constant on the quantised axis rather than a
# multiplication with re-rounding. Without that, the transformation grid would
# lose most hashes to quantisation error alone.
UNITS_PER_SEMITONE = 3
UNITS_PER_OCTAVE = 12 * UNITS_PER_SEMITONE
MAX_F_UNITS = 512              # 9 bits per frequency component of the hash
DT_QUANT = 2                   # frames per one dt unit
MAX_DT_UNITS = 1 << 14         # 14 bits for dt, the rest of the 32-bit hash

# Layout of fields in the npz file. The only hand-maintained element of the
# parameter fingerprint.
NPZ_LAYOUT = "fingerprint-npz-1"

# Field names inside the npz file. They stay as they are: they are part of the
# on-disk format, and renaming them would invalidate the whole corpus cache for
# purely cosmetic reasons. They mean "hashes" and "times".
NPZ_HASHES_KEY = "hashe"
NPZ_TIMES_KEY = "czasy"

# --- histogram thresholds ---------------------------------------------------

# The accumulation bin is narrow, because it is what localises the alignment
# and what decides between drift hypotheses. A wide bin swallows the drift and
# stops distinguishing anything: the measured 100 ms of resolution is four
# frames at a hop of 23 ms.
BIN_WIDTH_S = config.threshold("FINGERPRINT_BIN_S")
# The alignment tolerance is SOMETHING ELSE than the bin: it is the width
# within which we count a hash as belonging to an alignment already found. It
# feeds only `peak_ratio`, that is the number the thresholds of fusion rules
# 1-3 stand on (0.60, 0.50, 0.40). Nobody has recalibrated those thresholds,
# and narrowing the tolerance lowers the share for EVERY match, so the
# tolerance and the fusion thresholds have to move together. The chance level
# for 180 s of material is 0.5/180, that is half a percent - the 0.25 threshold
# lies two orders of magnitude above it.
ALIGNMENT_TOLERANCE_S = config.threshold("FINGERPRINT_ALIGN_TOLERANCE_S")
# The coarse bin serves ONLY to localise the cloud of hits before the drift is
# subtracted. It does not feed any number in the result.
COARSE_BIN_WIDTH_S = 0.5
# The radius over which the slope of the hit cloud is computed. It has to be
# clearly wider than the narrow bin, because the line must be fitted to the
# WHOLE drift, not to its truncated middle.
DRIFT_RADIUS_S = 1.5
MIN_PAIRS_FOR_DRIFT = 12
# How many disjoint bins we look for before stopping. This is an upper bound on
# the number of repetitions of the same fragment in the query, not a decision
# threshold: the loop ends earlier anyway once there is no uncovered material
# left.
MAX_BINS = 16
# Below this tempo change and at zero transposition there is nothing to report:
# this is the same material, not a modified version. Half a step of the tempo
# grid: below the grid's resolution we have nothing to claim.
IDENTITY_TOLERANCE = 0.0125
# Below this many matched hashes there is nothing to talk about. This is the
# real filter against random coincidences: the share within a bin carries no
# evidentiary mass, because twelve random hashes in one bin give a share of 1.0.
MIN_MATCHED_HASHES = int(config.threshold("FINGERPRINT_MIN_HASHES"))
# A bin counts as a repetition when it is at least this fraction as populous as
# the dominant one. An absolute threshold does not work: with two occurrences
# each naturally holds about half of the hits.
REPEAT_SHARE = config.threshold("FINGERPRINT_REPEAT_SHARE")

# The transformation grid: +/-6 semitones by 1, and tempo 0.90-1.15 by 2.5 percent.
SEMITONE_GRID = tuple(range(-6, 7))
TEMPO_GRID = tuple(round(0.90 + 0.025 * k, 5) for k in range(11))


# --- landmarks --------------------------------------------------------------


@dataclass
class Landmarks:
    """The clip's spectral peaks: time in frames, frequency in log units.

    We keep the pre-quantisation form, because the transformation grid rescales
    both axes and quantisation is only allowed after the rescaling.
    """

    pt: np.ndarray
    pf: np.ndarray
    pa: np.ndarray
    sr: int
    source_offset_s: float = 0.0

    def __len__(self) -> int:
        return int(self.pt.size)


@dataclass
class Fingerprint:
    """The fingerprint of one recording: hashes and anchor times in SOURCE time.

    This is the level 0 artifact from section 4. It is created offline, lands
    on disk, and level 1 only reads it.
    """

    hashes: np.ndarray
    times: np.ndarray


def _fingerprint_parameters() -> tuple[object, ...]:
    """The ACTUAL parameters the stored fingerprint depends on.

    Not a version literal to bump by hand: the fingerprint also depends on
    ingest and config constants, which live in someone else's module and whose
    change has no reason to touch a constant here.
    """
    return (
        NPZ_LAYOUT,
        N_FFT, HOP, PEAKS_PER_SECOND, FAN_OUT, TARGET_ZONE_S,
        NEIGHBOURHOOD_BINS, NEIGHBOURHOOD_FRAMES, THRESHOLD_DB,
        UNITS_PER_SEMITONE, DT_QUANT, MAX_F_UNITS, MAX_DT_UNITS,
        config.SR_HARMONIC, config.MAX_DURATION_S, config.TARGET_LUFS,
        config.TRIM_TOP_DB,
    )


def cache_path(audio_path: str | Path) -> Path:
    """Path of the npz file with the fingerprint. The key convention lives in `origin.cache`."""
    return cache.artifact_path("fp", audio_path, _fingerprint_parameters())


def _find_landmarks(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """STFT -> local maxima -> density capped at PEAKS_PER_SECOND."""
    empty = (np.zeros(0, np.float32),) * 3
    if y.size < N_FFT:
        return empty

    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP, window="hann"))
    S_db = librosa.amplitude_to_db(S, ref=np.max)

    mask = S_db >= maximum_filter(
        S_db, size=(NEIGHBOURHOOD_BINS, NEIGHBOURHOOD_FRAMES), mode="nearest"
    )
    mask &= S_db > THRESHOLD_DB
    # The outermost bins drop out: parabolic interpolation needs both neighbours.
    mask[0, :] = False
    mask[-1, :] = False
    bins, frames = np.nonzero(mask)
    if bins.size == 0:
        return empty

    values = S_db[bins, frames]
    # Density: in every second only the strongest peaks survive. Without this a
    # loud fragment floods the index and a quiet one contributes nothing.
    seconds = (frames * HOP) // sr
    order = np.lexsort((-values, seconds))
    sorted_seconds = seconds[order]
    _, starts, counts = np.unique(
        sorted_seconds, return_index=True, return_counts=True
    )
    rank = np.arange(sorted_seconds.size) - np.repeat(starts, counts)
    selected = order[rank < PEAKS_PER_SECOND]

    b = bins[selected]
    r = frames[selected]
    # Parabolic interpolation over the log amplitude. Without it a half-bin
    # error at low components is a few percent of the frequency, that is more
    # than a step of the transposition grid - and the grid stops finding
    # anything.
    left = S_db[b - 1, r]
    centre = S_db[b, r]
    right = S_db[b + 1, r]
    denominator = left - 2.0 * centre + right
    delta = np.where(np.abs(denominator) > 1e-9, 0.5 * (left - right) / denominator, 0.0)
    delta = np.clip(delta, -0.5, 0.5)
    exact_bin = np.maximum(b + delta, 1.0)

    pt = r.astype(np.float32)
    pf = (UNITS_PER_OCTAVE * np.log2(exact_bin)).astype(np.float32)
    pa = centre.astype(np.float32)
    ordering = np.argsort(pt, kind="stable")
    return pt[ordering], pf[ordering], pa[ordering]


def landmarks(clip: Clip) -> Landmarks:
    """The clip's landmarks together with its offset relative to the source recording."""
    pt, pf, pa = _find_landmarks(clip.y_harmonic, clip.sr_harmonic)
    return Landmarks(pt, pf, pa, clip.sr_harmonic, clip.source_offset_s)


# --- pairs and hashes -------------------------------------------------------


def _pairs(lm: Landmarks) -> tuple[np.ndarray, np.ndarray]:
    """An anchor plus FAN_OUT peaks spread across the target zone.

    We take one peak from each sub-zone rather than the five nearest ones: the
    five nearest all give small dt, which makes hashes from the whole recording
    fall into a handful of combinations and stop distinguishing anything.
    """
    n = len(lm)
    if n < 2:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    zone = TARGET_ZONE_S * lm.sr / HOP
    pt = lm.pt
    anchors: list[int] = []
    targets: list[int] = []
    for i in range(n):
        lo = int(np.searchsorted(pt, pt[i] + 1.0, side="left"))
        hi = int(np.searchsorted(pt, pt[i] + zone, side="right"))
        if hi <= lo:
            continue
        dt = pt[lo:hi] - pt[i]
        sub_zone = np.minimum((dt / zone * FAN_OUT).astype(np.int64), FAN_OUT - 1)
        amplitudes = lm.pa[lo:hi]
        for s in range(FAN_OUT):
            in_sub_zone = sub_zone == s
            if not in_sub_zone.any():
                continue
            j = lo + int(np.argmax(np.where(in_sub_zone, amplitudes, -np.inf)))
            anchors.append(i)
            targets.append(j)
    return np.array(anchors, np.int64), np.array(targets, np.int64)


def _hashes(
    lm: Landmarks,
    anchors: np.ndarray,
    targets: np.ndarray,
    semitones: int = 0,
    tempo: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """32-bit hashes from the triple (f1, f2, dt) plus the anchor time in source time.

    `semitones` and `tempo` describe the query RELATIVE TO the candidate: a
    query a semitone higher has units subtracted, a faster query has its time
    axis stretched. The rescaling also covers `source_offset_s`, because the
    whole time axis of a sped-up recording is sped up, including whatever
    ingest cut off the front.
    """
    if anchors.size == 0:
        return np.zeros(0, np.uint32), np.zeros(0, np.float64)
    shift = semitones * UNITS_PER_SEMITONE
    f1 = np.rint(lm.pf[anchors] - shift).astype(np.int64)
    f2 = np.rint(lm.pf[targets] - shift).astype(np.int64)
    dt = np.rint((lm.pt[targets] - lm.pt[anchors]) * tempo / DT_QUANT).astype(np.int64)
    good = (
        (f1 >= 0) & (f1 < MAX_F_UNITS)
        & (f2 >= 0) & (f2 < MAX_F_UNITS)
        & (dt >= 0) & (dt < MAX_DT_UNITS)
    )
    hashes = (f1[good] << 23) | (f2[good] << 14) | dt[good]
    clip_times = lm.pt[anchors][good].astype(np.float64) * HOP / lm.sr
    times = (clip_times + lm.source_offset_s) * tempo
    return hashes.astype(np.uint32), times


# --- the candidate fingerprint, a level 0 artifact --------------------------


def _compute_fingerprint(clip: Clip) -> Fingerprint:
    lm = landmarks(clip)
    hashes, times = _hashes(lm, *_pairs(lm))
    return Fingerprint(hashes.astype(np.uint32), times.astype(np.float32))


def _load_from_cache(file: Path) -> Fingerprint | None:
    data = cache.load_npz(file, (NPZ_HASHES_KEY, NPZ_TIMES_KEY))
    if data is None:
        return None
    return Fingerprint(data[NPZ_HASHES_KEY], data[NPZ_TIMES_KEY])


def _save_to_cache(file: Path, fingerprint: Fingerprint) -> None:
    cache.save_npz(
        file,
        {NPZ_HASHES_KEY: fingerprint.hashes, NPZ_TIMES_KEY: fingerprint.times},
    )


def fingerprint_of(audio_path: str | Path) -> Fingerprint:
    """The fingerprint of a recording on disk, cached in data/cache. Decodes only on a cold cache."""
    file = cache_path(audio_path)
    stored = _load_from_cache(file)
    if stored is not None:
        return stored
    fingerprint = _compute_fingerprint(ingest.load_clip(str(audio_path)))
    _save_to_cache(file, fingerprint)
    return fingerprint


def prewarm(candidates: Sequence[Candidate]) -> dict[str, str]:
    """Computes and stores candidate fingerprints up front. Level 0, offline.

    Section 4 puts candidate representations at level zero, before the demo.
    Computed lazily in the live path they mean a full decode, resampling and
    LUFS normalisation for every candidate on every query - the five-second
    budget of level 1 has nothing to pay for that with.

    Returns a map identifier -> reason for candidates that could not be
    computed. An empty map means the cache is warm throughout.
    """
    errors: dict[str, str] = {}
    if not candidates:
        return errors
    with ThreadPoolExecutor(max_workers=config.worker_count()) as pool:
        submissions = {
            pool.submit(fingerprint_of, candidate.audio_path): candidate
            for candidate in candidates
        }
        for submission, candidate in submissions.items():
            try:
                submission.result()
            except Exception as error:  # noqa: BLE001 - no audio means no measurement
                errors[candidate.id] = f"{type(error).__name__}: {error}"
    return errors


# --- index ------------------------------------------------------------------

Index = dict[int, list[tuple[str, float]]]


def _insert(index: Index, candidate_id: str, fingerprint: Fingerprint) -> Index:
    for h, t in zip(fingerprint.hashes.tolist(), fingerprint.times.tolist()):
        index.setdefault(h, []).append((candidate_id, float(t)))
    return index


def build_index(clip: Clip, candidate_id: str, into: Index | None = None) -> Index:
    """A table hash -> [(candidate_id, source time in seconds)].

    `into` allows building one index for many candidates without merging
    dictionaries on the caller's side.
    """
    return _insert({} if into is None else into, candidate_id, _compute_fingerprint(clip))


def load_index(candidates: Sequence[Candidate]) -> tuple[Index, dict[str, str]]:
    """An index built from ready level 0 artifacts. Does NOT decode audio.

    A candidate without a stored fingerprint comes back in the error map, not
    in the index. The live path is only allowed to read: computing fingerprints
    belongs to `prewarm`, which runs offline.
    """
    index: Index = {}
    errors: dict[str, str] = {}
    for candidate in candidates:
        fingerprint = _load_from_cache(cache_path(candidate.audio_path))
        if fingerprint is None:
            errors[candidate.id] = (
                "no level 0 fingerprint for this candidate; run prewarm"
            )
            continue
        _insert(index, candidate.id, fingerprint)
    return index, errors


# --- histogram of offset differences ----------------------------------------


def _best_bin(
    residuals: np.ndarray, hashes: np.ndarray, width: float
) -> tuple[int, np.ndarray]:
    """The most populous bin. It counts MATCHED HASHES, not hash-candidate pairs.

    One query hash can hit several places in the candidate (stationary material
    repeats the same landmarks), so counting pairs would reward repetitive
    material. The bin is computed on two grids shifted relative to each other,
    because the true offset likes to fall on a grid boundary.
    """
    best_count = 0
    best_mask = np.zeros(residuals.size, bool)
    if residuals.size == 0:
        return best_count, best_mask
    for shift in (0.0, width / 2.0):
        keys = np.floor((residuals + shift) / width).astype(np.int64)
        # One vote per matched hash and bin.
        unique = np.unique(np.stack([keys, hashes]), axis=1)
        values, counts = np.unique(unique[0], return_counts=True)
        i = int(np.argmax(counts))
        if int(counts[i]) > best_count:
            best_count = int(counts[i])
            best_mask = keys == values[i]
    return best_count, best_mask


def _drift(
    differences: np.ndarray, times: np.ndarray, centre: float
) -> tuple[float, float]:
    """The slope of the hit cloud around `centre` and its standard error.

    The tempo grid step is 2.5 percent, so even the correct grid variant is
    still off by 1.25 percent. On a 180 s clip that is two seconds of drift -
    the bin of the CORRECT variant would scatter across twenty 100 ms bins and
    the peak_ratio of a genuine MODIFIED would fall below the noise threshold.
    That is why, before counting, we subtract a line k * time from the
    differences.

    We also return the standard error of the slope, because without it there is
    no way to tell "we measured zero drift" apart from "we have nothing to
    measure it from". The regression is deliberately not trimmed: rejecting the
    worst residuals cuts from the cloud exactly those hits that lie far from
    the centre of the window, that is the ones carrying information about the
    slope, and pulls the result towards zero.
    """
    infinity = float("inf")
    in_window = np.abs(differences - centre) <= DRIFT_RADIUS_S
    n = int(in_window.sum())
    if n < MIN_PAIRS_FOR_DRIFT:
        return 0.0, infinity
    x = times[in_window]
    y = differences[in_window]
    spread = float(np.sum((x - x.mean()) ** 2))
    if spread < 1e-9:
        return 0.0, infinity
    k, intercept = np.polyfit(x, y, 1)
    residuals = y - (k * x + intercept)
    variance = float(np.sum(residuals ** 2)) / max(1, n - 2)
    return float(k), float(np.sqrt(variance / spread))


def _analyse(
    differences: np.ndarray,
    hashes: np.ndarray,
    times: np.ndarray,
    tempo: float = 1.0,
    semitones: int = 0,
    correct_drift: bool = False,
) -> dict[str, object] | None:
    """Turns triples (offset difference, hash, query time) into an alignment and output numbers.

    `times` is the query's source time ALREADY rescaled by the tempo variant,
    so `differences` are comparable with one another. The query span returns to
    its own recording axis by being divided by `tempo`.
    """
    matched = int(np.unique(hashes).size)
    if matched < MIN_MATCHED_HASHES:
        return None

    correction = 0.0
    resampling_consistent = False
    if correct_drift:
        # The coarse bin serves only to localise the cloud; it does not enter
        # the result itself. Without it the line would be fitted over the whole
        # spread, including hits from completely different places in the
        # recording.
        _, coarse = _best_bin(differences, hashes, COARSE_BIN_WIDTH_S)
        if coarse.any():
            measured, _ = _drift(differences, times, float(np.median(differences[coarse])))
            # A second hypothesis: a change of playback speed. It scales both
            # axes by the same factor, so a transposition by `semitones`
            # implies a specific tempo. We test it exactly like the
            # measurement - by the number of aligned hashes - and take
            # whichever explains the data better. A tie goes to the rescaling,
            # because that is one operation instead of two independent ones. A
            # pure time-stretch with keylock comes out of this correctly:
            # there the measurement explains the data CLEARLY better.
            from_key = 2.0 ** (semitones / 12.0) / tempo - 1.0
            count_measured, _ = _best_bin(
                differences - measured * times, hashes, BIN_WIDTH_S
            )
            count_from_key, _ = _best_bin(
                differences - from_key * times, hashes, BIN_WIDTH_S
            )
            if count_from_key >= count_measured:
                correction, resampling_consistent = from_key, True
            else:
                correction = measured
    residuals = differences - correction * times

    available = np.ones(residuals.size, bool)
    bins: list[tuple[int, float, np.ndarray]] = []
    half_tolerance = ALIGNMENT_TOLERANCE_S / 2.0
    for _ in range(MAX_BINS):
        positions = np.flatnonzero(available)
        if positions.size == 0:
            break
        in_bin, mask = _best_bin(
            residuals[positions], hashes[positions], BIN_WIDTH_S
        )
        if in_bin == 0:
            break
        centre = float(np.median(residuals[positions][mask]))
        # The bin LOCALISES the alignment, the tolerance COVERS it. We count
        # hashes lying within the tolerance around the offset we found, not
        # within a grid bucket, so that the result does not depend on where a
        # boundary happened to fall.
        full = np.zeros(residuals.size, bool)
        full[positions[np.abs(residuals[positions] - centre) <= half_tolerance]] = True
        bins.append((int(np.unique(hashes[full]).size), centre, full))
        # Disjointness is measured by the OCCUPIED PIECE OF THE QUERY, not by
        # the distance between offsets. A repetition is a second occurrence of
        # the same fragment at ANOTHER place in the query, so the next bin may
        # only be built from what has not been occupied yet. Separation
        # measured by the target zone would merge a loop shorter than the zone,
        # that is the most common sample case.
        occupied_from = float(times[full].min())
        occupied_to = float(times[full].max())
        available &= (times < occupied_from) | (times > occupied_to)

    if not bins:
        return None
    count, offset, mask = bins[0]
    threshold = max(MIN_MATCHED_HASHES, int(round(REPEAT_SHARE * count)))
    repetitions = sum(1 for c, _, _ in bins if c >= threshold)

    query_times = times[mask] / tempo
    candidate_times = (differences + times)[mask]
    return {
        "matched_hashes": matched,
        "peak_ratio": count / matched,
        "query_span": (float(query_times.min()), float(query_times.max())),
        "candidate_span": (
            float(max(0.0, candidate_times.min())),
            float(max(0.0, candidate_times.max())),
        ),
        "offset": offset,
        "repetitions": repetitions,
        # Technical fields for picking the variant, not part of the contract.
        "_aligned": count,
        "_tempo": tempo * (1.0 + correction),
        "_consistent": resampling_consistent,
    }


# --- matching ---------------------------------------------------------------


def _hits(
    hashes: np.ndarray, times: np.ndarray, index: Index
) -> dict[str, tuple[list[float], list[int], list[float]]]:
    """For every candidate: offset differences, hash indices and query times."""
    collected: dict[str, tuple[list[float], list[int], list[float]]] = {}
    times_list = times.tolist()
    for i, h in enumerate(hashes.tolist()):
        entries = index.get(h)
        if not entries:
            continue
        t = times_list[i]
        for candidate, candidate_time in entries:
            bucket = collected.get(candidate)
            if bucket is None:
                bucket = ([], [], [])
                collected[candidate] = bucket
            bucket[0].append(candidate_time - t)
            bucket[1].append(i)
            bucket[2].append(t)
    return collected


def _match_variants(
    clip: Clip,
    index: Index,
    variants: Sequence[tuple[int, float]],
    store_transform: bool,
) -> dict[str, FingerprintResult]:
    lm = landmarks(clip)
    anchors, targets = _pairs(lm)
    # candidate -> (aligned hashes, semitones, computed fields)
    best: dict[str, tuple[tuple[int, float], int, dict[str, object]]] = {}

    for semitones, tempo in variants:
        hashes, times = _hashes(lm, anchors, targets, semitones, tempo)
        if hashes.size == 0:
            continue
        for candidate, (differences, indices, query_times) in _hits(
            hashes, times, index
        ).items():
            computed = _analyse(
                np.asarray(differences, np.float64),
                np.asarray(indices, np.int64),
                np.asarray(query_times, np.float64),
                tempo=tempo,
                semitones=semitones,
                correct_drift=store_transform,
            )
            if computed is None:
                continue
            # Variants are compared by the NUMBER of aligned hashes, not by the
            # share. The share is normalised inside a variant, so a variant
            # with twelve hits, ten of which fell into one bin by chance, would
            # beat a variant with three hundred hits and a real alignment. The
            # number of aligned hashes is the common measure of evidence.
            # After the drift is subtracted the grid's time axis is partly
            # degenerate: several tempo variants describe the same cloud with a
            # different correction. A tie is settled by the variant closer to
            # identity, so that the choice does not depend on the order in
            # which the grid is iterated.
            key = (int(computed["_aligned"]), -abs(np.log2(tempo)))
            if candidate in best and key <= best[candidate][0]:
                continue
            best[candidate] = (key, semitones, computed)

    results: dict[str, FingerprintResult] = {}
    noise_floor = config.threshold("FINGERPRINT_NOISE_FLOOR")
    for candidate, (_, semitones, computed) in best.items():
        fields = {k: v for k, v in computed.items() if not k.startswith("_")}
        # Below the noise floor the candidate drops out of the result. A share
        # in the dominant bin below that value is a flat distribution, that is
        # a random coincidence.
        if float(fields["peak_ratio"]) < noise_floor:
            continue
        results[candidate] = FingerprintResult(
            candidate_id=candidate,
            transform=_transform(
                semitones, float(computed["_tempo"]), bool(computed["_consistent"])
            )
            if store_transform
            else None,
            **fields,
        )
    return results


def _transform(
    semitones: int, tempo: float, resampling_consistent: bool
) -> dict[str, float] | None:
    """A description of the transformation, or None when the identity variant won.

    Fusion rule 2 checks only `transform != null`, so a transformation of "sped
    up by zero percent and transposed by zero semitones" used to push an
    ordinary reupload into the MODIFIED class.

    `resampling_consistent` is diagnostics for the interface: it says whether
    the measured drift was consistent with the playback-speed hypothesis, or
    whether the tempo is the result of measuring the time axis alone.
    """
    if semitones == 0 and abs(tempo - 1.0) <= IDENTITY_TOLERANCE:
        return None
    return {
        "semitones": float(semitones),
        "tempo_ratio": float(tempo),
        "resampling_consistent": 1.0 if resampling_consistent else 0.0,
    }


def match(clip: Clip, index: Index) -> dict[str, FingerprintResult]:
    """Matching without transformations. It does not touch the grid of 143 variants."""
    return _match_variants(clip, index, ((0, 1.0),), store_transform=False)


def match_transformed(clip: Clip, index: Index) -> dict[str, FingerprintResult]:
    """The grid of 13 x 11 = 143 tempo and key variants. On demand only.

    Section 7.1: this is called only when `match` failed and the harmonic
    detector returned a high similarity. The harmonic signal says "this is that
    track", the absence of a fingerprint signal says "but not that version",
    and the grid answers "because it is sped up by 6 percent".
    """
    variants = [(s, t) for s in SEMITONE_GRID for t in TEMPO_GRID]
    return _match_variants(clip, index, variants, store_transform=True)


# --- detector ---------------------------------------------------------------


class FingerprintDetector:
    """Detector A. Level 1, always computed (section 4)."""

    name = "fingerprint"
    level = 1

    def run(
        self,
        clip: Clip,
        candidates: Sequence[Candidate],
        context: base.Context | None = None,
    ) -> DetectorEnvelope:
        return base.run_guarded(self.name, lambda: self._run(clip, candidates, context))

    def _run(
        self,
        clip: Clip,
        candidates: Sequence[Candidate],
        context: base.Context | None,
    ) -> list[FingerprintResult]:
        index, errors = load_index(candidates)
        hits = match(clip, index)

        for_grid = self._candidates_for_grid(candidates, hits, context)
        if for_grid:
            # The grid is computed only for those candidates for which the
            # harmonic detector says "this is that track" while the fingerprint
            # stays silent. The rest of the index has no reason to go through it.
            narrow, _ = load_index([c for c in candidates if c.id in for_grid])
            hits.update(match_transformed(clip, narrow))

        results = list(hits.values())
        # A candidate without a fingerprint is not zero similarity but a
        # missing measurement - it goes out with status failed and without a
        # single number.
        results.extend(
            FingerprintResult(candidate_id=cid, status="failed", reason=reason)
            for cid, reason in errors.items()
        )
        return results

    @staticmethod
    def _candidates_for_grid(
        candidates: Sequence[Candidate],
        hits: dict[str, FingerprintResult],
        context: base.Context | None,
    ) -> set[str]:
        """The condition from 7.1: the fingerprint failed while the harmonic detector sees this track."""
        if context is None:
            return set()
        harmonic_threshold = config.threshold("VERSION_QMAX")
        fingerprint_threshold = config.threshold("MODIFIED_PEAK_RATIO")
        selected: set[str] = set()
        for candidate in candidates:
            result = hits.get(candidate.id)
            if result is not None and (result.peak_ratio or 0.0) >= fingerprint_threshold:
                continue
            harmonic = context.result("harmonic", candidate.id)
            qmax = getattr(harmonic, "qmax_score", None) if harmonic else None
            if harmonic is not None and harmonic.status == "ok" and (qmax or 0.0) >= harmonic_threshold:
                selected.add(candidate.id)
        return selected
