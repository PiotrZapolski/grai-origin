"""Detector D - lyrics. Section 7.3 of the specification.

Three things are the heart of this module and none of them may be reversed:

1. **Whisper runs first, on the full mix. Demucs starts only when the
   confidence gate rejects the first pass** `[D3]`. Source separation sits at
   the input of two detectors at once and is the most expensive operation in
   the system, so we trade a fixed cost for a conditional one. Reversing that
   order does not change the results, only the bill for them - and that is why
   it is easy to miss in review.
2. **The confidence gate is a mechanism, not an ornament.** On an instrumental
   the model hallucinates, and without the gate the system will show random
   lyrics for a track with no vocals. The 7,942 instrumental-only groups in the
   catalogue are the test set for the threshold.
3. **The `instrumental` flag concerns the candidates, not the query.** The
   query arrives as an address without metadata, and whether it is
   instrumental is decided by the gate alone. A candidate with the flag gets
   `not_applicable` and **no number at all**: section 7.0 says outright that
   not applicable is not zero. When every candidate is instrumental, the
   detector finishes immediately and does not start transcription - that is
   where the actual saving comes from.

Calls into the heavy models are confined to three module-level functions
(`_whisper`, `_demucs`, `_embed`). Each imports its library lazily, inside
itself, and raises `ModelUnavailable` when it is missing. Thanks to that the
module imports and tests without `faster-whisper`, `demucs` and
`sentence-transformers` - and those three functions are the only place that has
to be replaced by a stub.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, NamedTuple, Sequence

import numpy as np

from origin.contracts import Candidate, DetectorEnvelope, LyricsResult
from origin.detectors import base
from origin.ingest import Clip

__all__ = [
    "ModelUnavailable",
    "Transcript",
    "GateOutcome",
    "SeparationSink",
    "transcribe",
    "transcribe_with_gate",
    "gate",
    "compare",
    "build_result",
    "tokens",
    "shingles",
    "LyricsDetector",
]

# --- gate thresholds (section 7.3) ------------------------------------------

# Threshold on the mean transcription confidence. A starting value, to be
# adjusted against the negative control from the catalogue: anything above the
# threshold on a purely instrumental recording means the gate is set too low.
# The threshold deliberately does not live in config.THRESHOLDS - it will land
# there together with calibration, once it is measured rather than guessed.
ASR_CONFIDENCE_THRESHOLD = 0.60
# We consider the language stable when the same detection result repeats in at
# least 80% of the windows. Language hopping between windows is the signature
# of a hallucination, not of a multilingual track.
LANGUAGE_STABILITY_THRESHOLD = 0.80
# The language detection window. 30 s is Whisper's natural frame.
LANGUAGE_WINDOW_S = 30.0

# --- comparison parameters (section 7.3) ------------------------------------

# 5-word shingles: shorter ones catch random coincidences, longer ones lose the quote.
SHINGLE_SIZE = 5
PERMUTATION_COUNT = 128
# A common run shorter than this is not a quote but a coincidence of vocabulary.
MIN_WORDS_IN_SPAN = 2

# --- models (the "heavy" group in pyproject.toml) ---------------------------

MODEL_ASR = "base"
MODEL_DEMUCS = "htdemucs"
# Multilingual on purpose: the semantic level is supposed to catch
# translations, so a monolingual model would strip it of the only function
# MinHash does not already perform.
MODEL_EMBEDDINGS = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SR_ASR = 16000


class ModelUnavailable(RuntimeError):
    """The heavy model is not present in the environment.

    A separate type, because the pipeline has to turn it into a `failed`
    envelope with the reason `model_unavailable`, not into an exception that
    ends the whole analysis. A plain ImportError would be lost in a general
    `except` together with real errors.
    """


def _missing_package(package: str, error: BaseException) -> ModelUnavailable:
    return ModelUnavailable(
        f"the package '{package}' is missing; it is installed from the 'heavy' "
        f"group in pyproject.toml (pip install -e '.[heavy]'): {error}"
    )


@dataclass(frozen=True)
class Transcript:
    """The transcription of the query together with how much it trusts itself.

    `words` carries triples (word, start, end) in seconds from the start of the
    clip - it is from those that the `matched_spans` with times are built, that
    is the highlighting in the interface.

    `used_separation` says whether this transcription was produced on separated
    vocals. The field has a default value because `_whisper` has no way of
    knowing that - it is set by `transcribe_with_gate`, which is the only place
    that decides about separation.
    """

    text: str
    confidence: float
    language: str
    language_stable: bool
    words: list[tuple[str, float, float]] = field(default_factory=list)
    used_separation: bool = False


class GateOutcome(NamedTuple):
    """What one gated transcription produced, including the vocal track itself.

    The first three fields are the triple `transcribe_with_gate` has always
    returned, in the same order, so a caller that unpacks by position or reads
    `[0]` keeps working. The fourth is the point of the type: section 7.4 step
    1 says source separation is computed **once**, by detector D, and shared
    with detector C, and it can only be shared if the caller can see it. Before
    this, `transcribe_with_gate` computed the vocals into a local variable and
    dropped them, so detector C transcribed the full mix every time.

    `separated_vocals` is None when the gate passed on the first pass and
    demucs never ran. That is the cheap path from decision `[D3]`, not a
    missing value - there is nothing to share because nothing was separated.
    """

    transcript: Transcript
    passed: bool
    reason: str | None
    separated_vocals: np.ndarray | None = None


@dataclass
class SeparationSink:
    """The one-slot box in which the caller collects the separated vocals.

    Detector D returns a `DetectorEnvelope`, and an envelope is a JSON contract
    - a vocal track is a few million floats and has no business travelling
    there. So the pipeline hands in a sink, the detector fills it when demucs
    ran, and the pipeline passes what it finds to detector C. One sink per run:
    it is mutable state and must not be shared between queries.

    `vocals` stays None when there was no separation. The sink is filled even
    when the gate rejects the second pass as well: the separation happened and
    it is just as useful to the melody as it would have been to an accepted
    transcript.
    """

    vocals: np.ndarray | None = None


# --- isolation of the heavy models ------------------------------------------


@lru_cache(maxsize=1)
def _asr_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise _missing_package("faster-whisper", error) from error
    from origin import config

    return WhisperModel(
        MODEL_ASR, device="cpu", compute_type="int8", cpu_threads=config.CPU_QUOTA
    )


@lru_cache(maxsize=1)
def _demucs_model():
    try:
        from demucs.pretrained import get_model
    except ImportError as error:
        raise _missing_package("demucs", error) from error
    model = get_model(MODEL_DEMUCS)
    model.eval()
    return model


@lru_cache(maxsize=1)
def _embedding_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise _missing_package("sentence-transformers", error) from error
    return SentenceTransformer(MODEL_EMBEDDINGS)


def _resample(y: np.ndarray, from_sr: int, to_sr: int) -> np.ndarray:
    if from_sr == to_sr:
        return np.asarray(y, dtype=np.float32)
    import librosa

    return librosa.resample(
        np.asarray(y, dtype=np.float32), orig_sr=from_sr, target_sr=to_sr
    )


def _whisper(y: np.ndarray, sr: int) -> Transcript:
    """Speech recognition with word-level timestamps.

    Without a VAD filter, on purpose: it is the gate in `gate` that must reject
    hallucinations on material without vocals, not a silencer at the input. A
    silencer would take away from the gate the very material it is calibrated
    on, and would incidentally hide the fact that the threshold is set wrong.
    """
    model = _asr_model()
    audio = _resample(y, int(sr), SR_ASR)
    segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=False)

    pieces: list[str] = []
    words: list[tuple[str, float, float]] = []
    probabilities: list[float] = []
    for segment in segments:
        pieces.append(segment.text)
        for word in getattr(segment, "words", None) or ():
            words.append((word.word.strip(), float(word.start), float(word.end)))
            probabilities.append(float(word.probability))

    # No words means confidence zero, not missing data: the model recognised nothing.
    confidence = float(np.mean(probabilities)) if probabilities else 0.0
    language, stable = _language_stability(model, audio, info)
    return Transcript(
        text=" ".join(pieces).strip(),
        confidence=confidence,
        language=language,
        language_stable=stable,
        words=words,
    )


def _language_stability(model: Any, audio: np.ndarray, info: Any) -> tuple[str, bool]:
    """The same language in at least 80% of the windows (section 7.3 step 3)."""
    whole_language = str(getattr(info, "language", "") or "")
    detect = getattr(model, "detect_language", None)
    window_length = int(LANGUAGE_WINDOW_S * SR_ASR)
    windows = [
        audio[i : i + window_length]
        for i in range(0, len(audio), window_length)
        if len(audio[i : i + window_length]) >= SR_ASR
    ]
    if detect is None or len(windows) < 2:
        # A single window, or an older library without on-demand detection:
        # there is nothing to compare between windows, so the language
        # confidence from the whole pass is what remains. That is a weaker
        # signal and it is described as such, not faked.
        language_confidence = float(getattr(info, "language_probability", 0.0) or 0.0)
        return whole_language, language_confidence >= LANGUAGE_STABILITY_THRESHOLD
    languages = [str(detect(window)[0]) for window in windows]
    dominant, count = Counter(languages).most_common(1)[0]
    return dominant, count / len(languages) >= LANGUAGE_STABILITY_THRESHOLD


def _demucs(y: np.ndarray, sr: int) -> np.ndarray:
    """Source separation, the vocal track. The most expensive operation in the system.

    Run only from `transcribe_with_gate` and only after the first pass has been
    rejected by the gate.
    """
    try:
        import torch
        from demucs.apply import apply_model
    except ImportError as error:
        raise _missing_package("demucs", error) from error

    model = _demucs_model()
    model_sr = int(model.samplerate)
    audio = _resample(y, int(sr), model_sr)
    # Demucs expects (batch, channels, samples) and a stereo model - mono is duplicated.
    input_tensor = torch.from_numpy(np.ascontiguousarray(np.stack([audio, audio])))[None]
    with torch.no_grad():
        stems = apply_model(model, input_tensor.float(), device="cpu", progress=False)[0]
    vocals = stems[list(model.sources).index("vocals")].mean(0).cpu().numpy()
    return _resample(vocals, model_sr, int(sr))


def _embed(sentences: Sequence[str]) -> np.ndarray:
    """Multilingual sentence embeddings, normalised to length 1."""
    model = _embedding_model()
    vectors = model.encode(list(sentences), normalize_embeddings=True)
    return np.asarray(vectors, dtype=np.float32)


# --- transcription and gate -------------------------------------------------


def transcribe(clip: Clip | str | Path) -> Transcript:
    """One speech recognition pass on the full mix, without separation.

    It also accepts a file path, because the negative control from section 7.3
    feeds an instrumental recording directly, without going through the
    pipeline.
    """
    if isinstance(clip, (str, Path)):
        from origin import ingest

        clip = ingest.load_clip(str(clip))
    return _whisper(np.asarray(clip.y_speech), int(clip.sr_speech))


def transcribe_with_gate(clip: Clip) -> GateOutcome:
    """Steps 2-4 of section 7.3. The transcript, the gate decision, and the vocals.

    The order is the entire point of this function: **whisper on the full mix,
    demucs only after a rejection**. When the gate also rejects the pass after
    separation, the last word belongs to that second pass - it is the one that
    carries `used_separation` and it is its reason that reaches the envelope.

    The vocal track comes back in the outcome rather than dying here, because
    detector C reads the same track (section 7.4 step 1). It is returned
    whatever the second gate decides: separation cost 391 s on the measured
    run, and a rejected transcript does not make the vocals any less useful to
    the melody.
    """
    y = np.asarray(clip.y_speech)
    sr = int(clip.sr_speech)

    transcript = _whisper(y, sr)
    passed, reason = gate(transcript)
    if passed:
        return GateOutcome(transcript, True, None)

    vocals = np.asarray(_demucs(y, sr))
    after_separation = replace(_whisper(vocals, sr), used_separation=True)
    passed, reason = gate(after_separation)
    return GateOutcome(after_separation, passed, None if passed else reason, vocals)


def gate(transcript: Transcript) -> tuple[bool, str | None]:
    """The confidence gate from section 7.3 step 3.

    Two reasons come from the specification: mean confidence below the
    threshold, and a language unstable between windows. A third one,
    `no_speech`, we add for an empty transcript at high confidence - comparing
    an empty text would give a jaccard of 0.0, that is the claim "we checked
    and there is no similarity" where we checked nothing.
    """
    if transcript.confidence < ASR_CONFIDENCE_THRESHOLD:
        return False, "asr_confidence"
    if not transcript.language_stable:
        return False, "language_unstable"
    if not tokens(transcript.text):
        return False, "no_speech"
    return True, None


# --- normalisation and comparison (section 7.3 step 5) ----------------------

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def _clean(word: str) -> str:
    """Lower case, no punctuation. The apostrophe disappears so that don't == dont."""
    return _NON_WORD.sub("", word.lower())


def _reduce_repetitions(
    pairs: list[tuple[str, tuple[float, float] | None]],
) -> list[tuple[str, tuple[float, float] | None]]:
    """Reduction of vocal repetitions: a run of the same word counts once.

    "la la la la" carries no more information than "la", and without the
    reduction it would spread across the shingles and inflate the jaccard on
    vocalisations alone. The time of the kept word is extended to the end of
    the last repetition, so that the highlighting in the interface covers the
    whole segment that was actually sung.
    """
    result: list[tuple[str, tuple[float, float] | None]] = []
    for token, time in pairs:
        if result and result[-1][0] == token:
            previous_time = result[-1][1]
            if previous_time is not None and time is not None:
                result[-1] = (token, (previous_time[0], time[1]))
            continue
        result.append((token, time))
    return result


def _pairs(
    text: str, words: Sequence[tuple[str, float, float]] = ()
) -> list[tuple[str, tuple[float, float] | None]]:
    """Normalised tokens together with their times, when the ASR provided them.

    When `words` is given, the tokens come **from it**, not from the text: only
    then does a token index correspond to a word with a known time, and the
    highlighting points at the place in the recording it talks about.
    """
    if words:
        raw = [
            (_clean(word), (float(start), float(end)))
            for word, start, end in words
        ]
    else:
        raw = [(_clean(word), None) for word in text.split()]
    return _reduce_repetitions([(t, c) for t, c in raw if t])


def tokens(text: str) -> list[str]:
    """Normalised words of a text. One source of normalisation for the whole module."""
    return [token for token, _ in _pairs(text)]


def shingles(words: Sequence[str], size: int = SHINGLE_SIZE) -> set[str]:
    """n-word shingles. The size is clipped to the length of the text."""
    size = max(1, min(size, len(words)))
    return {
        " ".join(words[i : i + size]) for i in range(len(words) - size + 1)
    }


def _minhash(shingle_set: set[str]):
    from datasketch import MinHash

    signature = MinHash(num_perm=PERMUTATION_COUNT)
    for element in shingle_set:
        signature.update(element.encode("utf-8"))
    return signature


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    """Literal similarity: MinHash signatures over a common shingle size.

    The size has to be common to both texts, otherwise the shingles have no way
    of agreeing. We clip it to the shorter of the texts - otherwise a two-word
    refrain compared with itself would give zero.
    """
    size = max(1, min(SHINGLE_SIZE, len(a), len(b)))
    return float(_minhash(shingles(a, size)).jaccard(_minhash(shingles(b, size))))


_SENTENCE_END = re.compile(r"[.!?\n]+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def _semantic(a: str, b: str) -> float:
    """Sentence-to-sentence similarity with alignment.

    For every query sentence we take the best matching candidate sentence and
    average. Alignment is necessary here, because translation and paraphrase
    reorder the lines, and comparing whole texts with a single vector blurs a
    short, literally borrowed fragment.
    """
    sentences_a, sentences_b = _sentences(a), _sentences(b)
    if not sentences_a or not sentences_b:
        raise ModelUnavailable("nothing to embed: empty text")
    vectors_a = _embed(sentences_a)
    vectors_b = _embed(sentences_b)
    matrix = vectors_a @ vectors_b.T
    return float(np.mean(matrix.max(axis=1)))


def compare(a: str, b: str) -> tuple[float, float | None]:
    """The two-stage comparison from section 7.3: (jaccard, semantic_sim).

    `semantic_sim` is None when the embedding model is not present in the
    environment. Zero would mean "we checked and there is no semantic
    similarity", and that is not true - the literal level keeps being computed
    normally, because MinHash needs no model at all.
    """
    tokens_a, tokens_b = tokens(a), tokens(b)
    if not tokens_a or not tokens_b:
        return 0.0, None
    literal = _jaccard(tokens_a, tokens_b)
    try:
        return literal, _semantic(a, b)
    except ModelUnavailable:
        return literal, None


# --- spans for highlighting -------------------------------------------------


def _common_runs(
    a: Sequence[str], b: Sequence[str], min_words: int
) -> list[tuple[int, int, int, int]]:
    """Maximal common runs of words as (a_from, a_to, b_from, b_to).

    Greedily: from every query position we take the longest match anywhere in
    the candidate text and jump past it, so that the same fragment does not
    report itself several times as several shorter ones.
    """
    runs: list[tuple[int, int, int, int]] = []
    i = 0
    while i < len(a):
        best_length, best_j = 0, -1
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            if k > best_length:
                best_length, best_j = k, j
        if best_length >= min_words:
            runs.append((
                i,
                i + best_length,
                best_j,
                best_j + best_length,
            ))
            i += best_length
        else:
            i += 1
    return runs


def matched_spans(
    query_text: str,
    candidate_text: str,
    words: Sequence[tuple[str, float, float]] = (),
    idf: Callable[[Sequence[str]], float] | None = None,
) -> list[dict[str, Any]]:
    """Common text runs, measured and timed - never quoted.

    A span says **how long the common run was and when it happened**, not what
    it said: `query_len` and `candidate_len` are the character lengths of the
    two runs. The words themselves are the lyrics of a copyrighted recording
    plus a transcript of the user's material, and both would leave the process
    on a public SSE stream. A length and a timestamp is everything the
    highlighted view needs, and it is not a reproduction of anything.

    `query_time` is None when the transcript carried no times - never [0, 0],
    because zero points at the start of the recording, which would be a lie.
    `idf` is computed only when the caller supplies a corpus; without it, it
    stays None rather than zero.
    """
    query_pairs = _pairs(query_text, words)
    query_tokens = [t for t, _ in query_pairs]
    candidate_tokens = tokens(candidate_text)
    min_words = max(
        1, min(MIN_WORDS_IN_SPAN, len(query_tokens), len(candidate_tokens))
    )

    spans: list[dict[str, Any]] = []
    for from_a, to_a, from_b, to_b in _common_runs(
        query_tokens, candidate_tokens, min_words
    ):
        times = [c for _, c in query_pairs[from_a:to_a] if c is not None]
        span_words = query_tokens[from_a:to_a]
        spans.append({
            "query_len": len(" ".join(span_words)),
            "candidate_len": len(" ".join(candidate_tokens[from_b:to_b])),
            "query_time": [times[0][0], times[-1][1]] if times else None,
            "idf": idf(span_words) if idf is not None else None,
        })
    return spans


def build_result(
    candidate_id: str,
    query_text: str,
    candidate_text: str,
    words: Sequence[tuple[str, float, float]] = (),
    asr_confidence: float | None = None,
    language: str | None = None,
    used_separation: bool = False,
    idf: Callable[[Sequence[str]], float] | None = None,
) -> LyricsResult:
    """The result for one candidate: both numbers plus the spans for highlighting."""
    jaccard, semantic = compare(query_text, candidate_text)
    return LyricsResult(
        candidate_id=candidate_id,
        jaccard=jaccard,
        semantic_sim=semantic,
        matched_spans=matched_spans(query_text, candidate_text, words, idf),
        asr_confidence=asr_confidence,
        language=language,
        used_separation=used_separation,
    )


# --- detector ---------------------------------------------------------------


def _candidate_lyrics(candidate: Candidate) -> str:
    """The text from `lyrics_path`. Section 7.3: the reference side is NOT transcribed.

    Whisper on the candidate side would be a cost counted in thousands of
    recordings for data that is already available in an open lyrics database.
    """
    return Path(candidate.lyrics_path or "").read_text(encoding="utf-8")


class LyricsDetector:
    """Detector D. Level 2, that is computed only after level 1.

    It does not register itself - the code that builds the pipeline wires it in
    (section 7.0).
    """

    name = "lyrics"
    level = 2

    def run(
        self,
        clip: Clip | None,
        candidates: Sequence[Candidate],
        context: base.Context | None = None,
        separation_sink: SeparationSink | None = None,
    ) -> DetectorEnvelope:
        """The detector envelope. The three non-`ok` outcomes here are content, not a failure.

        `not_applicable` when there is nothing to compare against, `gated` when
        the gate rejected the query transcript, `failed` when the model is not
        present in the environment. The comparison phase goes under
        `base.run_guarded`, because there a failure really is a failure. The
        transcription phase has its own guard, because `base.run_guarded` can
        return only `ok` or `failed`, while the gate needs `gated` with its own
        reason - and because the reason `model_unavailable` has to be a
        recognisable marker for the pipeline, not a formatted exception text.

        `separation_sink` is optional and is the only thing this detector hands
        out beyond its envelope: the vocal track, for detector C (section 7.4
        step 1). A caller that does not pass one gets exactly the behaviour it
        had before.
        """
        if not candidates:
            return base.empty_envelope(self.name, "not_applicable", "no_candidates")

        with_lyrics = [c for c in candidates if not c.instrumental]
        # An instrumental candidate carries not a single number - section 7.0.
        skipped = [
            LyricsResult(
                candidate_id=candidate.id, status="not_applicable", reason="instrumental"
            )
            for candidate in candidates
            if candidate.instrumental
        ]
        if not with_lyrics:
            # This is where the actual saving from section 7.3 comes from:
            # transcription does not start at all, because there is nothing to
            # compare its result against.
            return DetectorEnvelope(
                detector=self.name,
                status="not_applicable",
                reason="all_candidates_instrumental",
                results=skipped,
            )

        try:
            outcome = transcribe_with_gate(clip)
        except ModelUnavailable:
            return base.empty_envelope(self.name, "failed", "model_unavailable")
        except Exception as error:  # noqa: BLE001 - the reason lands in the envelope, not in a log
            return base.empty_envelope(
                self.name, "failed", f"{type(error).__name__}: {error}"
            )

        # Before the gate decision, deliberately: separation is what it costs
        # whether or not the transcript that came out of it survives, and the
        # melody can use it either way.
        if separation_sink is not None:
            separation_sink.vocals = outcome.separated_vocals

        if not outcome.passed:
            return DetectorEnvelope(
                detector=self.name,
                status="gated",
                reason=outcome.reason,
                results=skipped,
            )

        return base.run_guarded(
            self.name,
            lambda: self._compare_candidates(outcome.transcript, with_lyrics) + skipped,
        )

    def _compare_candidates(
        self, transcript: Transcript, candidates: Sequence[Candidate]
    ) -> list[LyricsResult]:
        results: list[LyricsResult] = []
        for candidate in candidates:
            if not candidate.lyrics_path:
                results.append(LyricsResult(
                    candidate_id=candidate.id,
                    status="not_applicable",
                    reason="no_lyrics",
                ))
                continue
            try:
                text = _candidate_lyrics(candidate)
            except OSError as error:
                # A failure on one candidate must not bring the others down.
                results.append(LyricsResult(
                    candidate_id=candidate.id,
                    status="failed",
                    reason=f"{type(error).__name__}: {error}",
                ))
                continue
            if not tokens(text):
                results.append(LyricsResult(
                    candidate_id=candidate.id,
                    status="not_applicable",
                    reason="no_lyrics",
                ))
                continue
            results.append(build_result(
                candidate.id,
                transcript.text,
                text,
                words=transcript.words,
                asr_confidence=transcript.confidence,
                language=transcript.language,
                used_separation=transcript.used_separation,
            ))
        return results
