from origin import fusion
from origin.contracts import FingerprintResult, HarmonicResult, LyricsResult, MelodicResult


def _fp(**kw):
    d = dict(candidate_id="c1", peak_ratio=0.0, query_span=(0.0, 0.0), repetitions=0)
    d.update(kw)
    return FingerprintResult(**d)


def _h(**kw):
    d = dict(candidate_id="c1", qmax_score=0.0, coverage=0.0)
    d.update(kw)
    return HarmonicResult(**d)


class FakeCorpus:
    size = 1000
    def idf(self, w): return 9.0
    def document_frequency(self, w): return 1


GENEROUS = FakeCorpus()


def test_rule_1_exact():
    v = fusion.decide(_fp(peak_ratio=0.8, query_span=(0.0, 40.0)), _h(), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "EXACT"
    assert v.verdict_layer == "phonogram"


def test_rule_2_modified():
    v = fusion.decide(_fp(peak_ratio=0.55, query_span=(0.0, 40.0),
                          transform={"tempo_ratio": 1.06, "semitones": 1}),
                      _h(qmax_score=0.7), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "MODIFIED"


def test_rule_3_excerpt_phonogram():
    v = fusion.decide(_fp(peak_ratio=0.5, query_span=(2.0, 10.0), repetitions=3),
                      _h(), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "EXCERPT_PHONOGRAM"
    assert v.verdict_layer == "phonogram"


def test_rule_4_version():
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8),
                      None, LyricsResult(candidate_id="c1", semantic_sim=0.85), 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"
    assert v.verdict_layer == "work"


def test_version_works_when_the_lyrics_detector_is_not_applicable():
    """Global Constraint 4: 24.9% of the catalogue are instrumentals, missing lyrics must not block."""
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8), None,
                      LyricsResult(candidate_id="c1", status="not_applicable",
                                   reason="instrumental"), 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"


def test_version_works_when_the_gate_rejected_the_transcript():
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8), None,
                      LyricsResult(candidate_id="c1", status="gated",
                                   reason="asr_confidence"), 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"


def test_version_works_when_there_was_no_lyrics_detector_at_all():
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8),
                      None, None, 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"


def test_the_gap_between_025_and_040_does_not_lose_the_cover():
    """Section 9.1: at a threshold of 0.25 this case fell through to NONE."""
    v = fusion.decide(_fp(peak_ratio=0.32, query_span=(0.0, 40.0)),
                      _h(qmax_score=0.7, coverage=0.8), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"


def test_rule_5_excerpt_work():
    v = fusion.decide(_fp(peak_ratio=0.05), _h(qmax_score=0.3, coverage=0.2),
                      MelodicResult(candidate_id="c1", longest_common_run=11),
                      None, 9.0, GENEROUS)
    assert v.verdict_class == "EXCERPT_WORK"
    assert v.verdict_layer == "work"


def test_rule_6_lyrics():
    v = fusion.decide(_fp(peak_ratio=0.05), _h(qmax_score=0.2), None,
                      LyricsResult(candidate_id="c1", jaccard=0.7, semantic_sim=0.8),
                      9.0, GENEROUS)
    assert v.verdict_class == "LYRICS"


def test_rule_7_none():
    v = fusion.decide(_fp(), _h(), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "NONE"


def test_the_rule_order_makes_exact_beat_version():
    """The first rule satisfied wins - section 9.1."""
    v = fusion.decide(_fp(peak_ratio=0.9, query_span=(0.0, 60.0)),
                      _h(qmax_score=0.9, coverage=0.9), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "EXACT"


def test_degradation_turns_version_into_common():
    class Poor(FakeCorpus):
        def idf(self, w): return 0.1
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8),
                      None, None, mean_idf=0.1, corpus=Poor())
    assert v.verdict_class == "COMMON"


def test_degradation_does_NOT_touch_exact():
    """Global Constraint 5 - this is demo case 1 against demo case 5."""
    class Poor(FakeCorpus):
        def idf(self, w): return 0.1
    v = fusion.decide(_fp(peak_ratio=0.9, query_span=(0.0, 60.0)), _h(),
                      None, None, mean_idf=0.1, corpus=Poor())
    assert v.verdict_class == "EXACT"


def test_the_verdict_carries_a_justification_for_every_satisfied_condition():
    v = fusion.decide(_fp(peak_ratio=0.8, query_span=(0.0, 40.0)), _h(), None, None, 9.0, GENEROUS)
    assert v.reasons, "screen E3 shows one sentence of justification"


def test_the_chronology_rule_on_a_tie():
    """Section 9.3: the earlier date wins, but only when there is a date at all."""
    a = fusion.RankItem(candidate_id="a", probability=0.80, published="1975-01-01")
    b = fusion.RankItem(candidate_id="b", probability=0.80, published="1999-01-01")
    assert [x.candidate_id for x in fusion.rank([b, a])] == ["a", "b"]


def test_the_chronology_rule_does_not_apply_without_a_date():
    a = fusion.RankItem(candidate_id="a", probability=0.80, published=None)
    b = fusion.RankItem(candidate_id="b", probability=0.81, published=None)
    assert [x.candidate_id for x in fusion.rank([a, b])] == ["b", "a"]


# --- cases added beyond the brief ----------------------------------------

def test_an_unknown_segment_satisfies_neither_rule_1_nor_rule_3():
    """span_length returns None without a query_span; None is neither 0.0 nor 40.0."""
    v = fusion.decide(_fp(peak_ratio=0.8, query_span=None), _h(), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "NONE"


def test_degradation_does_NOT_touch_excerpt_phonogram():
    """Section 8.1: fingerprint hashes are not a genre pattern."""
    class Poor(FakeCorpus):
        def idf(self, w): return 0.1
    v = fusion.decide(_fp(peak_ratio=0.5, query_span=(2.0, 10.0), repetitions=3),
                      _h(), None, None, mean_idf=0.1, corpus=Poor())
    assert v.verdict_class == "EXCERPT_PHONOGRAM"


def test_common_concerns_no_rights_layer():
    """Section 3: the rights layer for COMMON and NONE is empty."""
    class Poor(FakeCorpus):
        def idf(self, w): return 0.1
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8),
                      None, None, mean_idf=0.1, corpus=Poor())
    assert v.verdict_class == "COMMON"
    assert v.verdict_layer == ""
    assert any("common" in r.lower() or "corpus" in r.lower() for r in v.reasons)


def test_the_verdict_class_always_comes_from_the_contract():
    from origin.contracts import VERDICT_CLASSES
    v = fusion.decide(_fp(), _h(), None, None, 9.0, GENEROUS)
    assert v.verdict_class in VERDICT_CLASSES


def test_a_ranking_without_a_tie_goes_by_probability():
    items = [fusion.RankItem("a", 0.10, "1901-01-01"),
             fusion.RankItem("b", 0.90, "1999-01-01"),
             fusion.RankItem("c", 0.50, None)]
    assert [x.candidate_id for x in fusion.rank(items)] == ["b", "c", "a"]


def test_the_ranking_does_not_touch_the_input_list():
    items = [fusion.RankItem("a", 0.10, None), fusion.RankItem("b", 0.90, None)]
    fusion.rank(items)
    assert [x.candidate_id for x in items] == ["a", "b"]


def test_a_transformed_match_is_modified_not_exact():
    """Rule 1 must not swallow rule 2: a match recovered by the transformation grid is not an identical recording.

    Real numbers from the first run on music: a recording sped up by 6% gave a
    peak_ratio of 0.80 over a 52.7 s segment, but only after the grid had
    transposed and stretched the query back. Without the `transform is None`
    condition in rule 1 this comes out as EXACT.
    """
    v = fusion.decide(
        _fp(peak_ratio=0.796, query_span=(0.0, 52.7),
            transform={"semitones": 2.0, "tempo_ratio": 1.123}),
        _h(qmax_score=0.72), None, None, 9.0, GENEROUS,
    )
    assert v.verdict_class == "MODIFIED"
    assert v.verdict_layer == "phonogram"


# --- the commonality filter is allowed to have nothing to say ----------------


class Strict:
    """A corpus where everything looks common, so anything pushed through degrades."""
    size = 1000
    common_idf_threshold = 100.0
    def idf(self, w): return 0.0
    def document_frequency(self, w): return 900


def test_a_version_the_filter_says_nothing_about_stays_a_version():
    """`mean_idf=None` is the filter abstaining, and abstaining is not "common".

    `harmonic.chord_sequence` merges adjacent repeats and the n-gram sizes
    start at three, so a genuine cover whose matched segment collapses to fewer
    than three distinct chords - a loop, a drone, a short quote - yields no
    patterns at all. Passed on as 0.0 it fell below every possible threshold
    and the user was told the match was "a genre convention, not a signal of
    borrowing".
    """
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8),
                      None, None, None, Strict())
    assert v.verdict_class == "VERSION"
    assert v.verdict_layer == "work"


def test_a_mean_idf_of_zero_still_degrades():
    """The other half of the same rule: zero is a measurement, and it is the lowest one there is."""
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8),
                      None, None, 0.0, Strict())
    assert v.verdict_class == "COMMON"


# --- every class outranks NONE ----------------------------------------------


def test_a_recognised_class_outranks_none_whatever_the_numbers_say():
    """A candidate we found nothing on must not sit at the top of the ranking.

    EXCERPT_WORK is measured by the length of a common interval run, not by a
    score in 0-1, so its number is small on purpose. A NONE carrying an
    unrelated `peak_ratio` of 0.02 is not evidence of anything and cannot be
    allowed to outrank it - `_verdict_event` reads `ranking[0]` and the headline
    verdict on the whole run comes from there.
    """
    excerpt = fusion.RankItem("borrowed", 0.0, None, "EXCERPT_WORK")
    none = fusion.RankItem("unrelated", 0.02, None, "NONE")
    assert [x.candidate_id for x in fusion.rank([none, excerpt])] == ["borrowed", "unrelated"]


def test_none_stays_below_even_with_the_strongest_measurement_of_all():
    ranked = fusion.rank([
        fusion.RankItem("none", 0.99, None, "NONE"),
        fusion.RankItem("lyrics", 0.51, None, "LYRICS"),
    ])
    assert [x.candidate_id for x in ranked] == ["lyrics", "none"]


def test_two_nones_keep_their_input_order():
    """They are all at the bottom, so nothing left tells them apart. Stable sort, no invented order."""
    ranked = fusion.rank([
        fusion.RankItem("a", 0.02, None, "NONE"),
        fusion.RankItem("b", 0.40, None, "NONE"),
    ])
    assert [x.candidate_id for x in ranked] == ["a", "b"]
