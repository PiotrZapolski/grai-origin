"""Detector C - symbolic melody. Section 7.4 of the specification.

The only detector operating on what the law treats as the creative element of a
work: on the melody, not on the recording. At the same time the most expensive
and the least reliable, hence level 2 and first on the retreat ladder of
section 18.

Three things are the heart of it and none of them may be simplified:

1. **Intervals, not absolute pitches.** [60, 62, 64, 65] and [67, 69, 71, 72]
   are the same melody a fifth higher and both give [2, 2, 1]. Transpositional
   invariance then comes for free and matches how a human judges melodic
   similarity. Comparing absolute pitches would force us to look for the same
   melody twelve times and would still miss a cover sung a semitone lower by a
   tired vocalist.
2. **Mongeau-Sankoff, not a plain edit distance.** An edit-distance variant
   that accounts for fusion and fragmentation of notes, because a melody played
   with ornaments is still the same melody: one whole-tone leap split into two
   semitones must cost pennies, not two full operations.
3. **longest_common_run is a number for a human.** A musicologist and a lawyer
   understand "eleven consecutive identical intervals"; they do not understand
   a normalised edit distance. Fusion (section 9.1, rule 5) bases the
   EXCERPT_WORK class on that number, so it must mean exactly what it promises.

**Heavy models are not installed in the test environment.** Transcription sits
in a single function with a lazy import, while the whole comparison core -
intervals, n-grams, common runs, Mongeau-Sankoff - operates on lists of numbers
and can be verified without any model. Without basic-pitch the detector returns
a `failed` envelope with the reason `model_unavailable` rather than an
exception: section 9.1 requires fusion to cope with every envelope other than
`ok`, and a missing model is exactly such a state, not a failure of the caller.

Source separation is **shared with detector D** (section 7.4 step 1): it is the
same demucs pass and it is computed once. That is why it enters here as the
optional `separated_vocals` parameter supplied by the pipeline, rather than as
a call inside this module.
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from origin import cache, config, ingest
from origin.contracts import Candidate, DetectorEnvelope, MelodicResult
from origin.detectors import base
from origin.ingest import Clip

__all__ = [
    "Note",
    "Melody",
    "to_intervals",
    "ngrams",
    "longest_common_run",
    "mongeau_sankoff",
    "matched_ngrams",
    "model_available",
    "transcribe_melody",
    "dominant_line",
    "beat_grid",
    "quantize",
    "melody",
    "representation",
    "cache_path",
    "MelodicDetector",
]

# --- comparison parameters (section 7.4) ------------------------------------

# Section 7.4: "interval n-grams of length 4-8". The same tuple applies when
# building the IDF corpus from section 8, otherwise the query pattern would not
# hit the corpus key and every phrase would look rare.
NGRAM_SIZES: tuple[int, ...] = (4, 5, 6, 7, 8)

# The scale of the penalty for a mismatch between intervals, in semitones. A
# mismatch of four semitones or more costs as much as replacing a note with any
# other one: above a major third, two intervals are no longer a variant of the
# same melodic move but a different move, and distinguishing "how different"
# any further would only blur the result.
PITCH_SCALE = 4.0
# The cost of inserting or deleting one interval. Equal to the maximum
# replacement cost, and not by accident: thanks to that the most expensive
# possible path is max(len(a), len(b)), so the normalisation denominator is an
# attainable maximum rather than a value taken from the ceiling.
W_INDEL = 1.0
# Surcharge for every additional element in a fusion or a fragmentation.
# Clearly cheaper than a replacement, because that is the whole point of
# Mongeau-Sankoff: an ornament must cost pennies. Zero would be a mistake
# though - a fragmentation with no penalty at all would let any sequence be
# matched to any other as long as the sums agreed.
FRAGMENTATION_GAMMA = 0.3
# At most how many candidate notes may correspond to one query note. Three
# ornaments on one leap is the upper bound of what is still the same phrase;
# above that only the computation cost and the risk of a forced match grow.
MAX_FRAGMENT = 4

# How many matched n-grams reach the result. Without a limit, a looped melody
# produces hundreds of variants of the same phrase and the report stops being
# readable.
MAX_MATCHED_NGRAMS = 50

# --- transcription parameters (section 7.4 steps 2 and 3) -------------------

# Time resolution of the dominant line. 10 ms is about half of the shortest
# note that makes sense in a melody, so the grid loses no rhythm and costs
# nothing.
FRAME_S = 0.01
# Hysteresis against flicker (section 7.4 step 2). A new note has to be the
# highest for 50 ms to take over the line. Without it, every accidental entry
# of an upper partial would cut a long note into several and ruin the whole
# interval sequence - and an interval computed on a truncated note is a zero
# nobody played.
HYSTERESIS_S = 0.05
# Beat subdivision for quantisation (section 7.4 step 3). Sixteenths: finer
# would mean letting through the interpretive differences that quantisation is
# here to remove.
SUBDIVISIONS_PER_BEAT = 4
# Rejection threshold for a note shorter than half a grid cell. After snapping
# to the grid such a note merges with its neighbour or disappears, and left in
# with zero length it contributes an interval to the sequence that corresponds
# to nothing audible.
MIN_NOTE_FRACTION = 0.5

# Layout of fields in the npz file with a candidate's melody. The only manual
# element of the cache key; the rest is a hash of the actual parameters, see
# _representation_parameters.
NPZ_LAYOUT = "melodic-npz-1"

_PACKAGE_NAME = "basic_pitch"
_MODEL_MISSING_REASON = (
    "model_unavailable: the basic-pitch package is not installed; "
    "it lives in the optional 'heavy' dependency group (pip install -e '.[heavy]')"
)


@dataclass(frozen=True)
class Note:
    """A note in the symbolic representation. Time counted from the start of the CLIP.

    Exactly like everything the detectors compute from a `Clip`: converting to
    source-recording time is done by `Clip.to_source`, and by nothing else.
    """

    pitch: int
    start: float
    end: float
    confidence: float = 1.0

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class Melody:
    """The melodic line of one recording, ready for comparison.

    It holds both the notes and the intervals derived from them, because the
    comparison needs intervals while the report needs the time at which the
    matched phrase occurred. `times[i]` is the start of the note that opens the
    interval `intervals[i]`.
    """

    notes: list[Note] = field(default_factory=list)

    @property
    def intervals(self) -> list[int]:
        return to_intervals(self.notes)

    @property
    def times(self) -> list[float]:
        return [n.start for n in self.notes[:-1]]


# --- the symbolic core: numbers, no models ----------------------------------


def _pitches(notes: Sequence[object]) -> list[int]:
    """MIDI pitches from a list of notes or from a ready list of numbers.

    Both forms come in the same way on purpose: transcription gives `Note`
    objects, the IDF corpus and the tests give bare numbers, and the interval
    representation is identical for both.
    """
    return [int(getattr(n, "pitch", n)) for n in notes]


def to_intervals(midi_notes: Sequence[object]) -> list[int]:
    """The interval sequence: differences between consecutive notes. Section 7.4 step 4.

    A single note forms no interval at all, and an empty list is the correct
    answer here rather than missing data.
    """
    pitches = _pitches(midi_notes)
    return [b - a for a, b in zip(pitches, pitches[1:])]


def ngrams(intervals: Sequence[int], n: int) -> list[tuple[int, ...]]:
    """All contiguous subsequences of length n, in order of occurrence.

    Tuples, not lists: an n-gram is a key in the IDF corpus from section 8, so
    it has to be hashable.
    """
    if n <= 0:
        return []
    return [
        tuple(int(x) for x in intervals[start:start + n])
        for start in range(len(intervals) - n + 1)
    ]


def longest_common_run(a: Sequence[int], b: Sequence[int]) -> int:
    """The length of the longest common CONTIGUOUS subsequence. Section 7.4.

    Contiguous, not scattered: "eleven consecutive identical intervals" is a
    claim that will hold up in an expert opinion. Eleven intervals scattered
    across a whole track is a claim about nothing.
    """
    if not a or not b:
        return 0
    previous = [0] * (len(b) + 1)
    longest = 0
    for x in a:
        current = [0] * (len(b) + 1)
        for j, y in enumerate(b, start=1):
            if x == y:
                current[j] = previous[j - 1] + 1
                if current[j] > longest:
                    longest = current[j]
        previous = current
    return longest


def _replacement_cost(x: int, y: int) -> float:
    """Penalty for playing interval x instead of y, clipped to 1.0."""
    return min(1.0, abs(x - y) / PITCH_SCALE)


def _merge_cost(x: int, run: Sequence[int]) -> float:
    """Penalty for splitting interval x into a run of intervals (or for fusing them).

    It is the SUM of the run that counts, because three semitones up in a row
    lead exactly where one leap of a minor third leads. That is the whole
    difference between Mongeau-Sankoff and a plain edit distance: a melody
    played with ornaments reaches the same notes, only by a longer route.

    The sums agreeing is not enough on its own, and that is the most important
    correction here. Interval +2 split into [+1, +1] is an ornament, but split
    into [+5, -3] it has the same sum and is not an ornament - it is a leap of
    a fourth and a return, that is a different phrase. That is why the penalty
    also includes the EXCESS MOVEMENT: by how much the route actually travelled
    is longer than the straight-line route. Without that term any two intervals
    with a matching sum would glue together for pennies and the distance would
    stop telling melodies apart.
    """
    total = sum(run)
    excess_movement = sum(abs(v) for v in run) - abs(total)
    mismatch = (abs(x - total) + excess_movement) / PITCH_SCALE
    return min(1.0, mismatch) + FRAGMENTATION_GAMMA * (len(run) - 1)


def mongeau_sankoff(a: Sequence[int], b: Sequence[int]) -> float:
    """The Mongeau-Sankoff distance of two interval sequences, normalised to 0-1.

    Four operations: replacement, insertion, deletion, and fusion and
    fragmentation (one note against a run of notes on the other side). The last
    two are what distinguishes this variant from Levenshtein and are the only
    reason we compute it here.

    The normalisation divides by max(len(a), len(b)), that is by the cost of
    the most expensive path the DP can choose when `W_INDEL` equals the maximum
    replacement cost. The denominator is therefore an attainable maximum rather
    than a constant from the ceiling, and the returned number is comparable
    between a pair of long and a pair of short melodies. 0.0 means "the same
    melody", 1.0 means "nothing in common".

    An empty sequence against a non-empty one gives 1.0: there is nothing to
    match. Two empty ones give 0.0, because they are identical.
    """
    la, lb = len(a), len(b)
    if la == 0 and lb == 0:
        return 0.0
    if la == 0 or lb == 0:
        return 1.0

    x = [int(v) for v in a]
    y = [int(v) for v in b]
    infinity = math.inf
    D = [[infinity] * (lb + 1) for _ in range(la + 1)]
    D[0][0] = 0.0
    for i in range(la + 1):
        for j in range(lb + 1):
            if i == 0 and j == 0:
                continue
            best = infinity
            if i > 0:
                best = min(best, D[i - 1][j] + W_INDEL)
            if j > 0:
                best = min(best, D[i][j - 1] + W_INDEL)
            if i > 0 and j > 0:
                best = min(best, D[i - 1][j - 1] + _replacement_cost(x[i - 1], y[j - 1]))
            if i > 0:
                # fragmentation: a query interval split into several candidate intervals
                for k in range(2, min(MAX_FRAGMENT, j) + 1):
                    best = min(
                        best, D[i - 1][j - k] + _merge_cost(x[i - 1], y[j - k:j])
                    )
            if j > 0:
                # fusion: several query intervals merged into one candidate interval
                for k in range(2, min(MAX_FRAGMENT, i) + 1):
                    best = min(
                        best, D[i - k][j - 1] + _merge_cost(y[j - 1], x[i - k:i])
                    )
            D[i][j] = best

    return min(1.0, max(0.0, D[la][lb] / max(la, lb)))


def _ngram_positions(intervals: Sequence[int], n: int) -> dict[tuple[int, ...], list[int]]:
    """A map n-gram -> indices of its occurrences."""
    positions: dict[tuple[int, ...], list[int]] = {}
    for index, gram in enumerate(ngrams(intervals, n)):
        positions.setdefault(gram, []).append(index)
    return positions


def matched_ngrams(
    query_intervals: Sequence[int],
    candidate_intervals: Sequence[int],
    query_times: Sequence[float] | None = None,
    candidate_times: Sequence[float] | None = None,
    idf: Callable[[tuple[int, ...]], float] | None = None,
    sizes: Sequence[int] = NGRAM_SIZES,
    limit: int = MAX_MATCHED_NGRAMS,
) -> list[dict[str, object]]:
    """Interval phrases shared by the query and the candidate, longest first.

    Time is optional, because the algorithm itself does not need it while the
    report does: without `query_times` the result carries interval indices,
    with them it adds `query_pos` and `candidate_pos` in clip seconds, exactly
    as in the JSON of section 7.4.

    `idf` is injected rather than imported: the commonality filter from section
    8 lives in `origin.commonality` and needs a corpus that the detector has no
    right to load for itself. Without a corpus the `idf` field simply does not
    appear - and that is more honest than writing a zero there, which fusion
    would read as "a common pattern" (section 7.0).

    Longest first, because a longer shared phrase is a stronger claim, and the
    limit cuts off the tail of repetitions from a looped melody.
    """
    hits: list[dict[str, object]] = []
    taken_q: set[int] = set()
    for n in sorted({int(s) for s in sizes}, reverse=True):
        if n <= 0:
            continue
        candidate_positions = _ngram_positions(candidate_intervals, n)
        if not candidate_positions:
            continue
        for query_index, gram in enumerate(ngrams(query_intervals, n)):
            occurrences = candidate_positions.get(gram)
            if not occurrences:
                continue
            # A phrase contained in an already reported longer one is not a
            # separate claim, only a piece of it.
            if any(index in taken_q for index in range(query_index, query_index + n)):
                continue
            taken_q.update(range(query_index, query_index + n))
            candidate_index = occurrences[0]
            entry: dict[str, object] = {
                "interval_seq": list(gram),
                "query_index": query_index,
                "candidate_index": candidate_index,
            }
            if query_times is not None and query_index < len(query_times):
                entry["query_pos"] = float(query_times[query_index])
            if candidate_times is not None and candidate_index < len(candidate_times):
                entry["candidate_pos"] = float(candidate_times[candidate_index])
            if idf is not None:
                entry["idf"] = float(idf(gram))
            hits.append(entry)
            if len(hits) >= limit:
                return hits
    return hits


# --- transcription: the only place that needs a model -----------------------


def model_available() -> bool:
    """Whether basic-pitch is in the environment. find_spec, not an import.

    Importing basic-pitch itself pulls in TensorFlow and costs several seconds
    plus a few hundred megabytes of RAM. The detector asks about model
    availability on EVERY pass, including when the package is absent, so the
    question has to be cheap.
    """
    try:
        return find_spec(_PACKAGE_NAME) is not None
    except (ImportError, ValueError):
        return False


def _write_temporary(y: np.ndarray, sr: int) -> Path:
    """Audio to disk, because basic-pitch takes a path, not an array."""
    import soundfile as sf

    handle, path = tempfile.mkstemp(prefix="origin-melodic-", suffix=".wav")
    os.close(handle)
    sf.write(path, np.asarray(y, dtype=np.float32), int(sr))
    return Path(path)


def transcribe_melody(
    clip: Clip, separated_vocals: np.ndarray | None = None
) -> list[Note]:
    """Polyphonic audio -> MIDI transcription. Section 7.4 step 2.

    Returns ALL detected notes, not the dominant line: extracting the line is a
    separate step (`dominant_line`) that needs no model and can be verified
    without one.

    `separated_vocals` is the vocal track from demucs, **shared with detector
    D** (section 7.4 step 1): if D has already run the separation, the pipeline
    passes its result here and it is computed once. Without separation the
    transcription runs on the full mix and mostly picks the drums out of it, so
    the result is fit at best for monophonic material - which is why the
    parameter is optional rather than silently empty by default.

    Without the `basic-pitch` package it raises ImportError naming the
    dependency group. The detector itself does not propagate that exception: it
    checks `model_available()` beforehand and returns a `failed` envelope with
    the reason `model_unavailable`.
    """
    if not model_available():
        raise ImportError(_MODEL_MISSING_REASON)

    # Lazy import: TensorFlow enters memory only on an actual transcription, not
    # when the module is imported by fusion or by the core tests.
    from basic_pitch import ICASSP_2022_MODEL_PATH  # noqa: PLC0415
    from basic_pitch.inference import predict  # noqa: PLC0415

    y = clip.y_harmonic if separated_vocals is None else separated_vocals
    y = np.asarray(y, dtype=np.float32)
    if y.size == 0:
        return []

    path = _write_temporary(y, clip.sr_harmonic)
    try:
        _, _, events = predict(str(path), ICASSP_2022_MODEL_PATH)
    finally:
        path.unlink(missing_ok=True)

    notes = [
        Note(
            pitch=int(event[2]),
            start=float(event[0]),
            end=float(event[1]),
            confidence=float(event[3]),
        )
        for event in events
    ]
    notes.sort(key=lambda n: (n.start, -n.pitch))
    return notes


# --- dominant line, quantisation: no model ----------------------------------


def dominant_line(
    notes: Sequence[Note],
    frame_s: float = FRAME_S,
    hysteresis_s: float = HYSTERESIS_S,
) -> list[Note]:
    """The highest active note in a frame, with hysteresis against flicker. Step 2.

    The rule "the highest one wins" is unreliable in polyphony over short
    distances: a partial, a second voice or a single frame of a chord takes
    over the line for 20 ms and cuts a long note into three. The hysteresis
    requires a contender to be the highest for `hysteresis_s` before it takes
    over the line - thanks to that the interval sequence describes the melody
    rather than the detector's jitter.
    """
    if not notes:
        return []
    end = max(n.end for n in notes)
    if end <= 0:
        return []
    frame_count = max(1, int(math.ceil(end / frame_s)))

    pitches = np.full(frame_count, -1, dtype=np.int32)
    owner = np.full(frame_count, -1, dtype=np.int32)
    for index, note in enumerate(notes):
        start_frame = max(0, int(note.start / frame_s))
        end_frame = min(frame_count, max(start_frame + 1, int(math.ceil(note.end / frame_s))))
        if end_frame <= start_frame:
            continue
        frames = np.arange(start_frame, end_frame)
        better = frames[pitches[frames] < note.pitch]
        pitches[better] = note.pitch
        owner[better] = index

    hysteresis_frames = max(1, int(round(hysteresis_s / frame_s)))
    chosen = np.full(frame_count, -1, dtype=np.int32)
    current = -1
    contender = -1
    counter = 0
    for frame in range(frame_count):
        top = int(owner[frame])
        if top == current:
            contender, counter = -1, 0
        else:
            if top == contender:
                counter += 1
            else:
                contender, counter = top, 1
            # The first note has nothing to displace, so it enters immediately.
            if counter >= hysteresis_frames or current == -1:
                current = contender
                contender, counter = -1, 0
        chosen[frame] = current

    line: list[Note] = []
    start = 0
    for frame in range(1, frame_count + 1):
        is_end = frame == frame_count or chosen[frame] != chosen[start]
        if not is_end:
            continue
        index = int(chosen[start])
        if index >= 0:
            source = notes[index]
            line.append(Note(
                pitch=source.pitch,
                start=start * frame_s,
                end=frame * frame_s,
                confidence=source.confidence,
            ))
        start = frame
    return line


def beat_grid(clip: Clip, subdivisions: int = SUBDIVISIONS_PER_BEAT) -> list[float]:
    """The rhythmic grid of the detected tempo. Section 7.4 step 3.

    An empty list means "no pulse detected" and is a valid state: material
    without a clear rhythm must pass through quantisation untouched rather than
    be snapped to a grid invented from an average.
    """
    if subdivisions < 1:
        subdivisions = 1
    y = np.asarray(clip.y_harmonic, dtype=np.float32)
    if y.size == 0:
        return []
    import librosa  # noqa: PLC0415 - librosa enters memory only when there is audio

    _, beats = librosa.beat.beat_track(
        y=y, sr=int(clip.sr_harmonic), units="time", trim=False
    )
    beats = [float(t) for t in np.atleast_1d(beats)]
    if len(beats) < 2:
        return []

    grid: list[float] = []
    for earlier, later in zip(beats, beats[1:]):
        step = (later - earlier) / subdivisions
        grid.extend(earlier + step * i for i in range(subdivisions))
    grid.append(beats[-1])
    return grid


def _snap(time: float, grid: Sequence[float]) -> float:
    """The nearest grid point. The grid is increasing, so a bisection is enough."""
    import bisect  # noqa: PLC0415

    position = bisect.bisect_left(grid, time)
    if position == 0:
        return grid[0]
    if position == len(grid):
        return grid[-1]
    before, after = grid[position - 1], grid[position]
    return before if time - before <= after - time else after


def quantize(notes: Sequence[Note], grid: Sequence[float]) -> list[Note]:
    """Snaps notes to the rhythmic grid. Section 7.4 step 3.

    It removes interpretive differences: the same performance with and without
    rubato must give the same symbol sequence. Notes shorter than half a grid
    cell disappear after snapping, and adjacent notes of the same pitch merge -
    because two touching notes of the same pitch contribute a zero interval to
    the sequence that nobody played.

    An empty grid leaves the notes unchanged: see `beat_grid`.
    """
    if not notes:
        return []
    if not grid:
        return list(notes)

    cell = min(
        (after - before for before, after in zip(grid, grid[1:]) if after > before),
        default=0.0,
    )
    minimum = cell * MIN_NOTE_FRACTION

    snapped: list[Note] = []
    for note in notes:
        start = _snap(note.start, grid)
        end = _snap(note.end, grid)
        if end - start < minimum:
            continue
        snapped.append(
            Note(pitch=note.pitch, start=start, end=end, confidence=note.confidence)
        )

    merged: list[Note] = []
    for note in snapped:
        if merged and merged[-1].pitch == note.pitch and merged[-1].end >= note.start:
            previous = merged[-1]
            merged[-1] = Note(
                pitch=previous.pitch,
                start=previous.start,
                end=max(previous.end, note.end),
                confidence=max(previous.confidence, note.confidence),
            )
        else:
            merged.append(note)
    return merged


def melody(clip: Clip, separated_vocals: np.ndarray | None = None) -> Melody:
    """The full chain from section 7.4: separation -> transcription -> line -> grid.

    The separation is not computed here. It arrives ready from outside, because
    detector D performs exactly the same one and section 7.4 step 1 requires it
    to be computed once.
    """
    return Melody(notes=quantize(
        dominant_line(transcribe_melody(clip, separated_vocals)),
        beat_grid(clip),
    ))


# --- candidate representations and cache ------------------------------------


def _representation_parameters() -> tuple[object, ...]:
    """The ACTUAL parameters the stored melody depends on.

    Not a version literal to bump by hand: the transcription also depends on
    ingest constants, which live in someone else's module and whose change has
    no reason to touch a constant here. The hashed tuple invalidates the cache
    on its own.
    """
    return (
        NPZ_LAYOUT,
        FRAME_S, HYSTERESIS_S, SUBDIVISIONS_PER_BEAT, MIN_NOTE_FRACTION,
        config.SR_HARMONIC, config.MAX_DURATION_S, config.TARGET_LUFS,
        config.WINDOW_S, config.HOP_S, config.TRIM_TOP_DB,
    )


def cache_path(audio_path: str | Path) -> Path:
    """Path of the npz file with the melody. The key convention lives in `origin.cache`."""
    return cache.artifact_path("melo", audio_path, _representation_parameters())


def _load_from_cache(file: Path) -> Melody | None:
    data = cache.load_npz(file, ("pitch", "start", "end", "confidence"))
    if data is None:
        return None
    return Melody(notes=[
        Note(pitch=int(p), start=float(s), end=float(e), confidence=float(c))
        for p, s, e, c in zip(
            data["pitch"], data["start"], data["end"], data["confidence"]
        )
    ])


def _save_to_cache(file: Path, line: Melody) -> None:
    cache.save_npz(file, {
        "pitch": np.array([n.pitch for n in line.notes], dtype=np.int16),
        "start": np.array([n.start for n in line.notes], dtype=np.float32),
        "end": np.array([n.end for n in line.notes], dtype=np.float32),
        "confidence": np.array([n.confidence for n in line.notes], dtype=np.float32),
    }, compressed=True)


def representation(audio_path: str | Path) -> Melody:
    """The melody of a recording, cached in data/cache.

    Transcription is the most expensive operation in the whole system and the
    candidates do not change, so it is computed once per file. Section 4 puts
    candidate representations at level zero, and that is not an optimisation
    for later: without a warm cache, level 2 does not fit in any budget.
    """
    file = cache_path(audio_path)
    stored = _load_from_cache(file)
    if stored is not None:
        return stored
    computed = melody(ingest.load_clip(str(audio_path)))
    _save_to_cache(file, computed)
    return computed


# --- detector envelope ------------------------------------------------------


class MelodicDetector:
    """Detector C. Level 2, first on the retreat ladder of section 18.

    It does not register itself - the code that builds the pipeline wires it in
    (section 7.0).

    `separated_vocals` is passed through `run` as a map `candidate id -> audio`
    plus an entry under the key `QUERY` for the query. Detector D runs demucs
    first and the pipeline passes its result here; a missing entry means only
    "there was no separation", not an error.
    """

    name = "melodic"
    level = 2

    #: The query's key in the map of vocal tracks.
    QUERY = "__query__"

    def __init__(self, idf: Callable[[tuple[int, ...]], float] | None = None) -> None:
        # The commonality filter from section 8 is injected, not imported: the
        # corpus is a level 0 artifact and the detector has no right to load it
        # for itself.
        self.idf = idf

    def run(
        self,
        clip: Clip,
        candidates: Sequence[Candidate],
        context: "base.Context | None" = None,
        separated_vocals: dict[str, np.ndarray] | None = None,
    ) -> DetectorEnvelope:
        """The detector envelope. Section 9.1: a failure must not bring the analysis down.

        Two states come out from under the `base.run_guarded` guard, because
        both are a state of the material rather than an execution error:

        - no model -> `failed` with the reason `model_unavailable`. The owner's
          decision: heavy models do not enter the environment, and fusion has
          to handle every envelope other than `ok` anyway, so a missing model
          is an ordinary state of that envelope, not an exception flying
          upwards.
        - no harmonic material -> `not_applicable`.
        """
        if not model_available():
            return base.empty_envelope(self.name, "failed", _MODEL_MISSING_REASON)
        if not np.asarray(clip.y_harmonic).size:
            return base.empty_envelope(
                self.name, "not_applicable", "the query has no material to transcribe"
            )
        return base.run_guarded(
            self.name, lambda: self._run(clip, candidates, separated_vocals or {})
        )

    def _run(
        self,
        clip: Clip,
        candidates: Sequence[Candidate],
        separation: dict[str, np.ndarray],
    ) -> list[MelodicResult]:
        query_vocals = separation.get(self.QUERY)
        # Section 7.4 step 1: the vocal track when detector D separated one,
        # the full mix when it did not. The flag says which, on every result,
        # because a distance measured over drums and accompaniment is a
        # different number from one measured over a voice.
        used_separation = query_vocals is not None
        query_melody = melody(clip, query_vocals)
        query_intervals = query_melody.intervals
        query_times = query_melody.times
        if not query_intervals:
            # Section 7.0: zero would mean "we checked and there is no
            # similarity". There is no query melody, so we checked nothing.
            return [
                MelodicResult(
                    candidate_id=candidate.id,
                    status="not_applicable",
                    reason="the query has no melodic line",
                    used_separation=used_separation,
                )
                for candidate in candidates
            ]

        results: list[MelodicResult] = []
        for candidate in candidates:
            try:
                candidate_melody = representation(candidate.audio_path)
            except Exception as error:  # noqa: BLE001 - no audio means no measurement
                results.append(MelodicResult(
                    candidate_id=candidate.id,
                    status="failed",
                    reason=f"{type(error).__name__}: {error}",
                    used_separation=used_separation,
                ))
                continue

            candidate_intervals = candidate_melody.intervals
            if not candidate_intervals:
                results.append(MelodicResult(
                    candidate_id=candidate.id,
                    status="not_applicable",
                    reason="the candidate has no melodic line",
                    used_separation=used_separation,
                ))
                continue

            results.append(MelodicResult(
                candidate_id=candidate.id,
                matched_ngrams=matched_ngrams(
                    query_intervals,
                    candidate_intervals,
                    query_times,
                    candidate_melody.times,
                    self.idf,
                ),
                longest_common_run=longest_common_run(
                    query_intervals, candidate_intervals
                ),
                ms_distance=mongeau_sankoff(query_intervals, candidate_intervals),
                used_separation=used_separation,
            ))
        return results
