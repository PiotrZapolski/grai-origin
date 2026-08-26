import pytest
from origin import legal
from origin.contracts import Candidate, FingerprintResult
from origin.fusion import Verdict


def _cand(**kw):
    d = dict(id="c1", name="N", artist="A", source_url="https://example.com/a",
             audio_path="data/audio/c1.wav", license="all_rights_reserved",
             instrumental=False)
    d.update(kw)
    return Candidate(**d)


def test_exact_touches_the_phonogram_layer():
    l = legal.assess(Verdict("EXACT", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.9), _cand())
    assert "phonogram" in l.rights_layer


def test_version_signals_the_performance_layer():
    """Section 11.1: an artistic performance is a separate layer."""
    l = legal.assess(Verdict("VERSION", "work", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.1), _cand())
    assert "performance" in l.rights_layer


def test_common_raises_no_flag():
    l = legal.assess(Verdict("COMMON", "work", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.1), _cand())
    assert l.risk_flags == []


def test_a_recognisable_excerpt_raises_the_high_risk_flag():
    l = legal.assess(Verdict("EXCERPT_PHONOGRAM", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.85), _cand())
    assert "recognizable_excerpt" in l.risk_flags
    assert l.recognizability > 0.8


def test_strong_modification_with_recognisability_gives_the_pastiche_flag():
    """Section 11.2: a borderline situation is to be flagged as borderline."""
    l = legal.assess(Verdict("EXCERPT_PHONOGRAM", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.7,
                                       transform={"tempo_ratio": 1.3, "semitones": 5}),
                     _cand())
    assert "possible_pastiche" in l.risk_flags
    assert l.modification > 0.3


def test_an_open_licence_generates_an_attribution_and_removes_the_risk():
    l = legal.assess(Verdict("EXACT", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.9),
                     _cand(license="cc-by-4.0"))
    assert l.required_attribution
    assert "recognizable_excerpt" not in l.risk_flags


def test_an_unknown_licence_is_missing_information_not_an_absence_of_restrictions():
    """Section 11.3 and constraint 9."""
    l = legal.assess(Verdict("EXACT", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.9),
                     _cand(license="unknown"))
    assert l.license_status == "unknown"
    assert l.required_attribution is None


def test_every_result_carries_the_disclaimer():
    l = legal.assess(Verdict("NONE", "", []),
                     FingerprintResult(candidate_id="c1"), _cand())
    assert "not legal advice" in l.disclaimer


# --------------------------------------------------------------------------
# Rows of tables 11.1 and 11.2 that the set from the brief does not touch
# --------------------------------------------------------------------------

@pytest.mark.parametrize("verdict_class,layers", [
    ("EXACT", ["phonogram"]),
    ("MODIFIED", ["phonogram"]),
    ("EXCERPT_PHONOGRAM", ["phonogram"]),
    ("VERSION", ["work", "performance"]),
    ("EXCERPT_WORK", ["work"]),
    ("LYRICS", ["work"]),
    ("COMMON", []),
    ("NONE", []),
])
def test_the_full_set_of_rights_layers_for_every_class(verdict_class, layers):
    """Section 11.1: rights_layer carries the FULL SET of layers, not the leading layer."""
    l = legal.assess(Verdict(verdict_class, "", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.5), _cand())
    assert l.rights_layer == layers


def test_the_scores_exist_only_for_the_excerpt_classes():
    """Section 11.2: recognisability and modification are concepts from the Pelham test.

    For EXACT the number means nothing, so it must not exist rather than pass
    itself off as a measured zero.
    """
    l = legal.assess(Verdict("EXACT", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.9), _cand())
    assert l.recognizability is None
    assert l.modification is None


def test_a_rejected_fingerprint_detector_means_no_scores_not_zeros():
    """Section 7.0: gated is not zero, in the legal panel either."""
    l = legal.assess(Verdict("EXCERPT_PHONOGRAM", "phonogram", []),
                     FingerprintResult(candidate_id="c1", status="gated",
                                       reason="below the noise floor"),
                     _cand())
    assert l.recognizability is None
    assert l.modification is None
    assert l.risk_flags == []


def test_an_unknown_licence_does_not_remove_the_risk_flag():
    """Constraint 9: missing metadata is not an absence of restrictions."""
    l = legal.assess(Verdict("EXCERPT_PHONOGRAM", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.85),
                     _cand(license="unknown"))
    assert "recognizable_excerpt" in l.risk_flags


def test_the_attribution_carries_the_performer_the_title_and_the_licence_name():
    """Section 11.2: the text is meant to go straight to the user's clipboard."""
    l = legal.assess(Verdict("EXACT", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.9),
                     _cand(artist="Band", name="Track", license="cc-by-nc-sa-3.0"))
    assert l.required_attribution == 'Band, "Track", CC BY-NC-SA 3.0'
