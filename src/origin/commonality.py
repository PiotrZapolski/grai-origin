"""The IDF corpus and the commonality filter. Section 8 of the specification.

This is the mechanism that translates the legal principle "what is protected is
creative expression, not an idea or a convention" into working code. Without it
the product does not differ from any other similarity tool.

A pattern is a tuple of strings: a chord-sequence n-gram from detector B, an
interval n-gram from detector C, or a text shingle from detector D. The corpus
knows only the document frequency of patterns; it does not know which detector
produced them.
"""
from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from . import config

# Version of the idf.json file layout. Changing the meaning of a field bumps
# this number, so that an old corpus does not load quietly as a new one.
FORMAT = "grai-origin-idf-2"

# Separator of pattern elements in the JSON key. The US control character (unit
# separator), because a pattern can be a text shingle and any printable
# character could occur inside it.
SEPARATOR = "\x1f"

# Sizes of chord-sequence n-grams. The same constant applies when building the
# corpus and when computing the query's patterns - patterns computed with
# different sizes would not hit the same keys and every query pattern would
# look rare.
CHORD_NGRAM_SIZES: tuple[int, ...] = (3, 4, 5)

# Section 8.1, the decisive rule. Degradation applies ONLY to classes from the
# work layer. A reupload of a track built on the I-V-vi-IV progression does not
# stop being a reupload because the progression is common: with a fingerprint
# hit the question is not about a genre pattern but about a specific recording.
# Without this, demo case 1 (EXACT) could come out as COMMON.
DEGRADABLE_CLASSES: frozenset[str] = frozenset({"VERSION", "LYRICS", "EXCERPT_WORK"})

Pattern = tuple[str, ...]


def _as_pattern(value: Iterable[object] | str) -> Pattern:
    """Normalises a pattern to a tuple of strings.

    A list and a tuple with the same content must hit the same key, because one
    comes from JSON and the other from a detector.
    """
    if isinstance(value, str):
        return (value,)
    return tuple(str(element) for element in value)


# Pitch-class names in the same order as harmonic.NOTES. Repeated here on
# purpose: the commonality filter reads only the LABELS produced by detector B,
# not its tables, and it must not blow up when a pattern arrives from another
# source.
NOTES: tuple[str, ...] = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_NOTE_INDEX = {note: i for i, note in enumerate(NOTES)}


def _parse_chord(label: object) -> tuple[int, str] | None:
    """A chord label into (root pitch class, mode). None for an unrecognised one."""
    text = str(label)
    mode = ""
    if len(text) > 1 and text.endswith("m"):
        text, mode = text[:-1], "m"
    index = _NOTE_INDEX.get(text)
    if index is None:
        return None
    return index, mode


def _degrees(ngram: Sequence[object]) -> Pattern:
    """A chord n-gram into degrees counted from the first chord, preserving the mode.

    `C-G-Am-F` and `D-A-Bm-G` are the same progression played in two keys and
    come out of here as one pattern `0-7-9m-5`.

    An n-gram with a label that cannot be parsed (silence, a chord outside the
    major-minor vocabulary) stays in its raw form. Better that such a pattern
    meets nothing than that it quietly merges with somebody else's degree.
    """
    parsed = [_parse_chord(c) for c in ngram]
    if not parsed or any(p is None for p in parsed):
        return tuple(str(c) for c in ngram)
    base = parsed[0][0]  # type: ignore[index]
    return tuple(
        f"{(index - base) % 12}{mode}"
        for index, mode in parsed  # type: ignore[misc]
    )


def chord_ngrams(
    sequence: Sequence[str],
    sizes: Sequence[int] = CHORD_NGRAM_SIZES,
) -> list[Pattern]:
    """N-grams of the chord sequence from `harmonic.chord_sequence`, key-independent.

    Shared by corpus building and by the live path. If each side computed
    n-grams in its own way, the corpus and the query would speak different
    alphabets.

    A pattern is degrees counted from the first chord, not absolute names, and
    that is the condition for the filter working at all. Detector B is
    explicitly transposition-independent (section 7.2, twelve rotations), so a
    filter judging its hits with key-dependent patterns would be internally
    inconsistent with it: a match found at transposition +2 would be judged by
    patterns that never meet at all. Measured on a corpus of 291 tracks:
    I-V-vi-IV written absolutely as `C-G-Am-F` has df = 1 and passes for a rare
    motif, while counted by degrees as `0-7-9m-5` it has df = 16, that is 5.5%
    of the corpus, and goes to degradation as it should.
    """
    result: list[Pattern] = []
    for size in sizes:
        if size <= 0:
            continue
        for start in range(len(sequence) - size + 1):
            result.append(_degrees(sequence[start:start + size]))
    return result


class Corpus:
    """Document frequency of patterns in the corpus from section 5.6.

    It holds numbers only: how many corpus tracks contain a given pattern and
    how many tracks the corpus has at all. The corpus audio is neither needed
    here nor available after building.
    """

    def __init__(self, size: int, document_frequency: dict[Pattern, int]) -> None:
        self._size = max(0, int(size))
        self._df: dict[Pattern, int] = {
            _as_pattern(pattern): int(count) for pattern, count in document_frequency.items()
        }

    # --- building -----------------------------------------------------------

    @classmethod
    def from_documents(cls, documents: Sequence[Sequence[Iterable[object]]]) -> "Corpus":
        """A corpus from a list of documents, where a document is one track's list of patterns.

        A pattern repeated within one track counts once: this is a DOCUMENT
        frequency, not a number of occurrences. A track that returns to the
        same progression twenty times does not make it twenty times more
        common.
        """
        df: dict[Pattern, int] = {}
        size = 0
        for document in documents:
            size += 1
            for pattern in {_as_pattern(p) for p in document}:
                df[pattern] = df.get(pattern, 0) + 1
        return cls(size, df)

    @classmethod
    def load(cls, path: str | Path) -> "Corpus":
        """Loads a corpus written by scripts/build_corpus.py."""
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
        layout = data.get("format", FORMAT)
        if layout != FORMAT:
            raise ValueError(f"unknown IDF corpus layout: {layout!r}, expected {FORMAT!r}")
        df = {
            tuple(key.split(SEPARATOR)): int(count)
            for key, count in data.get("document_frequency", {}).items()
        }
        return cls(int(data.get("corpus_size", 0)), df)

    def save(self, path: str | Path, **metadata: object) -> Path:
        """Writes the corpus to JSON. The target directory is outside git."""
        file = Path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        content: dict[str, object] = {
            "format": FORMAT,
            "corpus_size": self._size,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chord_ngram_sizes": list(CHORD_NGRAM_SIZES),
        }
        content.update(metadata)
        content["document_frequency"] = {
            SEPARATOR.join(pattern): count for pattern, count in sorted(self._df.items())
        }
        with open(file, "w", encoding="utf-8") as handle:
            json.dump(content, handle, ensure_ascii=False)
        return file

    # --- reading ------------------------------------------------------------

    @property
    def size(self) -> int:
        """The number of tracks in the corpus, that is the N in the IDF formula."""
        return self._size

    def __len__(self) -> int:
        return self._size

    @property
    def distinct_patterns(self) -> int:
        """How many different patterns the corpus knows at all. A coverage measure, not a corpus size."""
        return len(self._df)

    def patterns(self) -> Iterable[Pattern]:
        """All known patterns. For reports and for inspecting the IDF distribution."""
        return self._df.keys()

    def document_frequency(self, pattern: Iterable[object] | str) -> int:
        """In how many corpus tracks this pattern occurs.

        Section 8.2: this is the number that goes to the UI in the sentence
        "this motif occurs in N tracks of the corpus". An absent pattern occurs
        in zero tracks and is reported as such - raising that to one would lie
        to the user. One enters only in the IDF formula, as a guard against
        division by zero.
        """
        return int(self._df.get(_as_pattern(pattern), 0))

    def idf(self, pattern: Iterable[object] | str) -> float:
        """`idf(w) = log(N / df(w))`, section 8. For an absent pattern `df = 1`.

        An absent pattern gets the highest IDF this corpus can give, not
        infinity: a corpus of a few hundred tracks is not proof that the
        pattern exists nowhere, only that it does not exist here.
        """
        if self._size <= 0:
            return 0.0
        df = max(1, self.document_frequency(pattern))
        return math.log(self._size / df)

    @property
    def common_idf_threshold(self) -> float:
        """The IDF threshold of this corpus. A shortcut for `commonality.common_idf_threshold()`."""
        return common_idf_threshold()


def common_idf_threshold() -> float:
    """The IDF threshold below which a pattern passes for a genre convention.

    Section 8: common is a pattern occurring in more than
    COMMON_IDF_PERCENTILE of the corpus. The percentile threshold converts into
    an IDF threshold with the same formula that computes the IDF:
    `log(N / (p * N))`, that is `log(1 / p)`. The N cancels out, so the
    threshold does not depend on the corpus size - which means that every
    corpus object satisfying the contract of section 8 goes through the filter
    the same way, regardless of whether it is an instance of this class.

    At p = 0.01 the threshold comes out at log(100) = 4.605. A pattern present
    in two tracks out of a hundred has an IDF of log(50) = 3.91 and is common,
    one present in a single track has log(100) and is not yet - because one
    percent is not "more than one percent".
    """
    return math.log(1.0 / config.threshold("COMMON_IDF_PERCENTILE"))


def _corpus_threshold(corpus: object) -> float:
    """The commonality threshold for a specific corpus.

    A corpus that exposes its own `common_idf_threshold` decides for itself -
    that is the escape hatch for a corpus with a threshold computed from the
    actual IDF distribution, which section 10 foresees as the calibrated
    version. A corpus exposing only the contract of section 8 (`idf`,
    `document_frequency`, `size`) gets a threshold computed from the config and
    does not need to know the commonality filter exists.
    """
    own = getattr(corpus, "common_idf_threshold", None)
    if isinstance(own, (int, float)) and not isinstance(own, bool):
        return float(own)
    return common_idf_threshold()


def mean_idf(patterns: Sequence[Iterable[object]], corpus: Corpus) -> float:
    """The mean IDF of the matched patterns. This is the number that goes into `should_degrade`.

    An empty pattern list returns 0.0. Fusion then has a match the commonality
    filter has nothing to say about, so it should not push it through that
    filter at all - work-layer classes always arrive with patterns, because it
    is exactly on patterns that they were recognised.
    """
    if corpus is None:
        return 0.0
    values = [corpus.idf(pattern) for pattern in patterns]
    if not values:
        return 0.0
    return sum(values) / len(values)


def should_degrade(verdict_class: str, mean_idf: float, corpus: Corpus) -> bool:
    """Whether to degrade the class to COMMON. Section 8.1.

    Whether the class belongs to the work-layer set is checked BEFORE the
    threshold, and that is the whole decisive rule: EXACT, MODIFIED and
    EXCERPT_PHONOGRAM come out of here false no matter how common the patterns
    are, because fingerprint hashes are not genre patterns.

    A missing corpus (size zero) degrades nothing either. Without a corpus the
    commonality filter has nothing to base the claim of commonness on.

    From the corpus it takes only `size`, one of the three fields of the
    section 8 contract. Any object satisfying that contract - including the
    stub in the fusion tests - passes through here without an adapter.
    """
    if verdict_class not in DEGRADABLE_CLASSES:
        return False
    if corpus is None or int(corpus.size) <= 0:
        return False
    return bool(float(mean_idf) < _corpus_threshold(corpus))
