import math

import pytest
from origin import commonality as cm
from origin import config


@pytest.fixture
def corpus(tmp_path):
    """The I-V-vi-IV progression in 60 tracks out of 100, a rare motif in one."""
    documents = []
    for i in range(60):
        documents.append([("C", "G", "Am", "F")])
    for i in range(39):
        documents.append([("D", "A", "Bm", "G")])
    documents.append([("C#", "F#", "B", "Eb")])
    return cm.Corpus.from_documents(documents)


def test_a_common_progression_has_a_low_idf(corpus):
    assert corpus.idf(("C", "G", "Am", "F")) < 1.0


def test_a_rare_motif_has_a_high_idf(corpus):
    assert corpus.idf(("C#", "F#", "B", "Eb")) > 4.0


def test_an_absent_pattern_does_not_blow_up(corpus):
    assert corpus.idf(("X", "Y", "Z")) > 0


def test_degradation_applies_to_version(corpus):
    """Global Constraint 5."""
    assert cm.should_degrade("VERSION", mean_idf=0.4, corpus=corpus) is True


def test_degradation_applies_to_lyrics_and_excerpt_work(corpus):
    assert cm.should_degrade("LYRICS", 0.4, corpus) is True
    assert cm.should_degrade("EXCERPT_WORK", 0.4, corpus) is True


def test_degradation_does_NOT_apply_to_exact(corpus):
    """Global Constraint 5: a reupload of a track on a common progression is still a reupload."""
    assert cm.should_degrade("EXACT", mean_idf=0.1, corpus=corpus) is False


def test_degradation_does_NOT_apply_to_modified_or_excerpt_phonogram(corpus):
    assert cm.should_degrade("MODIFIED", 0.1, corpus) is False
    assert cm.should_degrade("EXCERPT_PHONOGRAM", 0.1, corpus) is False


def test_a_high_idf_degrades_nothing(corpus):
    assert cm.should_degrade("VERSION", mean_idf=9.0, corpus=corpus) is False


def test_the_corpus_knows_its_size(corpus):
    assert corpus.size == 100


def test_the_document_frequency_for_the_sentence_in_the_ui(corpus):
    """Section 8.2: the UI says 'this motif occurs in N tracks', it does not report an IDF number."""
    assert corpus.document_frequency(("C", "G", "Am", "F")) == 60


# --- below: tests added to the set from the brief ----------------------------


def test_the_commonality_threshold_lands_on_the_percentile_from_the_config(corpus):
    """Section 8: common is a pattern present in more than COMMON_IDF_PERCENTILE of the corpus.

    With a hundred tracks and a 1% threshold the boundary falls exactly between
    one track and two. The test guards that the filter reads the threshold from
    the config rather than from a constant of its own.
    """
    assert corpus.idf(("C#", "F#", "B", "Eb")) >= corpus.common_idf_threshold
    df_two = cm.Corpus.from_documents(
        [[("A", "B", "C")], [("A", "B", "C")]] + [[("Q", "Q", "Q")]] * 98
    )
    assert df_two.idf(("A", "B", "C")) < df_two.common_idf_threshold


class MinimalCorpus:
    """A corpus exposing ONLY the contract of section 8, without a single extra field.

    Fusion supplies such an object in its own tests. The commonality filter has
    to accept it without an adapter, otherwise every consumer with its own
    corpus runs into an AttributeError on a field the contract never promised.
    """

    def __init__(self, size: int) -> None:
        self.size = size

    def idf(self, pattern) -> float:
        return 0.0

    def document_frequency(self, pattern) -> int:
        return 0


def test_degradation_works_on_the_bare_contract_of_section_8():
    small = MinimalCorpus(size=1000)
    assert cm.should_degrade("VERSION", 0.4, small) is True
    assert cm.should_degrade("LYRICS", 0.4, small) is True
    assert cm.should_degrade("VERSION", 9.0, small) is False
    assert cm.should_degrade("EXACT", 0.1, small) is False
    assert cm.should_degrade("EXCERPT_PHONOGRAM", 0.1, small) is False


def test_the_commonality_threshold_does_not_depend_on_the_corpus_size():
    """`log(N / (p * N))` cancels N, so a small corpus has no different threshold than a large one."""
    expected = math.log(1.0 / config.threshold("COMMON_IDF_PERCENTILE"))
    assert cm.common_idf_threshold() == pytest.approx(expected)
    assert cm.Corpus.from_documents([[("A",)]] * 7).common_idf_threshold == pytest.approx(expected)


def test_a_corpus_may_impose_its_own_threshold():
    """The escape hatch for a threshold computed from the actual IDF distribution (section 10)."""

    class WithOwnThreshold(MinimalCorpus):
        common_idf_threshold = 0.2

    corpus = WithOwnThreshold(size=1000)
    assert cm.should_degrade("VERSION", 0.4, corpus) is False
    assert cm.should_degrade("VERSION", 0.1, corpus) is True


def test_a_pattern_repeated_within_a_track_counts_once():
    """This is a DOCUMENT frequency: a track returning to a progression does not raise df."""
    corpus = cm.Corpus.from_documents([[("C", "G", "Am", "F")] * 20])
    assert corpus.document_frequency(("C", "G", "Am", "F")) == 1


def test_an_absent_pattern_occurs_in_zero_tracks(corpus):
    """Section 8.2: the UI gets the true number, the one appears only in the IDF formula."""
    assert corpus.document_frequency(("X", "Y", "Z")) == 0


def test_a_list_and_a_tuple_are_the_same_pattern(corpus):
    """A pattern from JSON arrives as a list, from a detector as a tuple."""
    assert corpus.document_frequency(["C", "G", "Am", "F"]) == 60


def test_an_empty_corpus_degrades_nothing():
    empty = cm.Corpus.from_documents([])
    assert empty.size == 0
    assert cm.should_degrade("VERSION", 0.0, empty) is False


def test_the_mean_idf_is_the_mean_over_the_patterns(corpus):
    patterns = [("C", "G", "Am", "F"), ("C#", "F#", "B", "Eb")]
    expected = (corpus.idf(patterns[0]) + corpus.idf(patterns[1])) / 2
    assert cm.mean_idf(patterns, corpus) == pytest.approx(expected)


def test_chord_ngrams_are_shared_by_the_corpus_and_the_query():
    """Both sides have to compute patterns the same way, otherwise the keys never meet."""
    ngrams = cm.chord_ngrams(["C", "G", "Am", "F", "C"], sizes=(4,))
    assert ngrams == [("0", "7", "9m", "5"), ("0", "2m", "10", "5")]
    assert cm.chord_ngrams(["C", "G"], sizes=(4,)) == []


def test_the_same_progression_in_two_keys_gives_the_same_pattern():
    """The heart of the filter: detector B does not see the key, so the corpus must not either.

    I-V-vi-IV in C and in D is one progression. Counted by absolute names they
    lay under two keys, so df spread across twelve keys and the most common
    progression in the world looked like a rare motif.
    """
    in_c = cm.chord_ngrams(["C", "G", "Am", "F"], sizes=(4,))
    in_d = cm.chord_ngrams(["D", "A", "Bm", "G"], sizes=(4,))
    assert in_c == in_d == [("0", "7", "9m", "5")]

    # All twelve transpositions of the same progression are one pattern, and a
    # corpus built from them sees it as present in every track.
    keys = [
        ["C", "G", "Am", "F"], ["C#", "G#", "A#m", "F#"], ["D", "A", "Bm", "G"],
        ["D#", "A#", "Cm", "G#"], ["E", "B", "C#m", "A"], ["F", "C", "Dm", "A#"],
        ["F#", "C#", "D#m", "B"], ["G", "D", "Em", "C"], ["G#", "D#", "Fm", "C#"],
        ["A", "E", "F#m", "D"], ["A#", "F", "Gm", "D#"], ["B", "F#", "G#m", "E"],
    ]
    corpus = cm.Corpus.from_documents([cm.chord_ngrams(k, sizes=(4,)) for k in keys])
    assert corpus.distinct_patterns == 1
    assert corpus.document_frequency(("0", "7", "9m", "5")) == 12


def test_the_chord_mode_stays_in_the_degree():
    """Major and minor on the same degree are not the same pattern."""
    major = cm.chord_ngrams(["C", "F", "G"], sizes=(3,))
    minor = cm.chord_ngrams(["Cm", "Fm", "Gm"], sizes=(3,))
    assert major == [("0", "5", "7")]
    assert minor == [("0m", "5m", "7m")]


def test_a_label_outside_the_vocabulary_stays_raw():
    """Silence or a chord outside major-minor must not quietly merge with somebody else's degree."""
    assert cm.chord_ngrams(["C", "N", "G"], sizes=(3,)) == [("C", "N", "G")]


def test_writing_and_reading_the_corpus_preserves_the_numbers(corpus, tmp_path):
    file = tmp_path / "corpus" / "idf.json"
    corpus.save(file, source="test")
    loaded = cm.Corpus.load(file)
    assert loaded.size == corpus.size
    assert loaded.document_frequency(("C", "G", "Am", "F")) == 60
    assert loaded.idf(("D", "A", "Bm", "G")) == pytest.approx(corpus.idf(("D", "A", "Bm", "G")))
