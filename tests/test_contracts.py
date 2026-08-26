from typing import get_args

import pytest
from pydantic import ValidationError

from origin import contracts as c


def test_detector_status_has_exactly_four_values():
    assert set(c.DETECTOR_STATUSES) == {"ok", "not_applicable", "gated", "failed"}


def test_verdict_classes_cover_the_taxonomy():
    assert set(c.VERDICT_CLASSES) == {
        "EXACT", "MODIFIED", "VERSION",
        "EXCERPT_PHONOGRAM", "EXCERPT_WORK",
        "LYRICS", "COMMON", "NONE",
    }


def test_a_result_without_a_status_inherits_ok():
    r = c.FingerprintResult(candidate_id="cand_01", peak_ratio=0.8, matched_hashes=100,
                            query_span=(1.0, 20.0), candidate_span=(5.0, 24.0),
                            offset=4.0, repetitions=1)
    assert r.status == "ok"


def test_the_envelope_carries_its_own_status_independent_of_the_results():
    env = c.DetectorEnvelope(detector="lyrics", status="gated",
                             reason="asr_confidence", results=[])
    assert env.status == "gated"
    assert env.results == []


def test_not_applicable_is_not_zero():
    """Global Constraint 4: not applicable is not the same as no similarity."""
    r = c.LyricsResult(candidate_id="cand_01", status="not_applicable",
                       reason="instrumental")
    assert r.jaccard is None
    assert r.semantic_sim is None


def test_candidate_rejects_published_source_youtube():
    """Global Constraint 8: a YouTube date would regularly point at a cover as the original."""
    with pytest.raises(ValidationError):
        c.Candidate(id="cand_01", name="X", artist="Y",
                    source_url="https://youtube.com/watch?v=abc",
                    audio_path="data/audio/cand_01.wav",
                    published="1975-02-24", published_source="youtube",
                    license="all_rights_reserved", instrumental=False)


def test_candidate_accepts_manual_and_metadata_registry():
    for src in ("manual", "metadata_registry"):
        cand = c.Candidate(id="cand_01", name="X", artist="Y",
                           source_url="https://example.com/a",
                           audio_path="data/audio/cand_01.wav",
                           published="1975-02-24", published_source=src,
                           license="all_rights_reserved", instrumental=False)
        assert cand.published_source == src


def test_a_candidate_may_have_no_date():
    """Section 9.3: without a date the chronology rule does not apply, but the candidate is valid."""
    cand = c.Candidate(id="cand_01", name="X", artist="Y",
                       source_url="https://example.com/a",
                       audio_path="data/audio/cand_01.wav",
                       published=None, published_source=None,
                       license="unknown", instrumental=False)
    assert cand.published is None


def test_a_ranking_entry_carries_the_probability_status():
    """Global Constraint 7: the UI must tell a calibrated threshold apart from a written-in one."""
    entry = c.RankingEntry(rank=1, candidate=_candidate(), verdict_class="VERSION",
                           verdict_layer="work", probability=0.71,
                           probability_status="uncalibrated", evidence={},
                           alignment=None, commonality=None, legal=None,
                           explanation="")
    assert entry.probability_status == "uncalibrated"


def test_the_analysis_result_tells_partial_apart_from_full():
    res = c.AnalyzeResult(status="partial", completed_levels=[1],
                          query=c.QueryInfo(duration=184.2, waveform_url=None,
                                            transcript=[]),
                          ranking=[], calibration=None)
    assert res.status == "partial"
    assert res.completed_levels == [1]


# --- tests of the types added on the basis of section 12 of the specification ---


def test_a_status_other_than_ok_must_not_carry_a_number():
    """Global Constraint 4 enforced by the contract, not by convention."""
    with pytest.raises(ValidationError):
        c.HarmonicResult(candidate_id="cand_01", status="gated",
                         reason="fragment too short", qmax_score=0.61)
    with pytest.raises(ValidationError):
        c.FingerprintResult(candidate_id="cand_01", status="failed",
                            reason="decoding error", repetitions=3)


def test_a_status_other_than_ok_allows_non_numeric_fields():
    r = c.LyricsResult(candidate_id="cand_01", status="gated",
                       reason="asr_confidence", used_separation=True)
    assert r.used_separation is True
    assert r.asr_confidence is None


def test_the_envelope_keeps_subclass_fields_when_serialised():
    """Without SerializeAsAny pydantic would trim the result to the DetectorResult fields."""
    env = c.DetectorEnvelope(
        detector="fingerprint",
        results=[c.FingerprintResult(candidate_id="cand_01", peak_ratio=0.82)],
    )
    dump = env.model_dump()
    assert dump["results"][0]["peak_ratio"] == 0.82


def test_a_candidate_set_has_an_identifier_and_a_list():
    candidate_set = c.CandidateSet(set_id="demo_01", candidates=[_candidate()])
    assert candidate_set.set_id == "demo_01"
    assert candidate_set.candidates[0].id == "cand_01"


def test_a_candidate_set_rejects_youtube_inside_the_list():
    with pytest.raises(ValidationError):
        c.CandidateSet.model_validate({
            "set_id": "demo_01",
            "candidates": [{
                "id": "cand_01", "name": "X", "artist": "Y",
                "source_url": "https://example.com/a",
                "audio_path": "data/audio/cand_01.wav",
                "published": "1975-02-24", "published_source": "youtube",
                "license": "all_rights_reserved", "instrumental": False,
            }],
        })


def test_the_legal_block_by_default_does_not_know_the_licence():
    """Section 11.3: unknown is missing information, never an absence of restrictions."""
    legal = c.Legal()
    assert legal.license_status == "unknown"
    assert legal.risk_flags == []
    assert legal.rights_layer == []
    assert legal.recognizability is None
    assert legal.disclaimer


def test_alignment_and_commonality_are_optional():
    al = c.Alignment(query_span=(12.4, 31.8), candidate_span=(64.1, 83.5),
                     transposition=2, tempo_ratio=1.06)
    assert al.tempo_ratio == 1.06
    assert c.Alignment().query_span is None
    com = c.Commonality(mean_idf=8.4, corpus_frequency=3, corpus_size=4128)
    assert com.mean_idf == 8.4


def test_the_evidence_in_the_ranking_uses_the_status_vocabulary_of_7_0():
    entry = c.RankingEntry(
        rank=1, candidate=_candidate(), verdict_class="EXCERPT_PHONOGRAM",
        verdict_layer="phonogram", probability=0.94,
        probability_status="calibrated",
        evidence={"lyrics": {"status": "not_applicable", "reason": "instrumental"}},
    )
    assert entry.evidence["lyrics"].status == "not_applicable"
    with pytest.raises(ValidationError):
        c.RankingEntry(rank=1, candidate=_candidate(), verdict_class="NONE",
                       probability_status="uncalibrated",
                       evidence={"lyrics": {"status": "invented"}})


def test_the_ranking_rejects_a_class_outside_the_taxonomy():
    with pytest.raises(ValidationError):
        c.RankingEntry(rank=1, candidate=_candidate(), verdict_class="EXCERPT",
                       probability_status="uncalibrated")


def test_a_stream_event_carries_the_level_and_the_detail():
    """Section 12: gated with a next field is content, not an error."""
    ev = c.StreamEvent(stage="transcript", level=2, status="gated",
                       detail={"reason": "asr_confidence", "next": "separation"})
    assert ev.level == 2
    assert ev.detail["next"] == "separation"
    assert c.StreamEvent(stage="verdict", level=2, status="final").detail == {}


def test_the_calibration_info_carries_the_model_version():
    cal = c.CalibrationInfo(model_version="lr_v3", trained_on=500,
                            precision_at_threshold=0.95)
    res = c.AnalyzeResult(status="final", completed_levels=[1, 2],
                          query=c.QueryInfo(duration=184.2),
                          ranking=[], calibration=cal)
    assert res.calibration.model_version == "lr_v3"


def _candidate() -> "c.Candidate":
    return c.Candidate(id="cand_01", name="X", artist="Y",
                       source_url="https://example.com/a",
                       audio_path="data/audio/cand_01.wav",
                       published="1975-02-24", published_source="manual",
                       license="all_rights_reserved", instrumental=False)


# --- fix round 1: C1, I1-I5 ---


def test_gated_with_a_zero_is_rejected():
    """C1: jaccard=0.0 with a rejected transcript is a claim, not missing data."""
    for field, value in (("jaccard", 0.0), ("semantic_sim", 0.0)):
        with pytest.raises(ValidationError):
            c.LyricsResult(candidate_id="c1", status="gated",
                           reason="asr_confidence", **{field: value})
    with pytest.raises(ValidationError):
        c.FingerprintResult(candidate_id="c1", status="failed",
                            reason="decoding error", peak_ratio=0.0)
    with pytest.raises(ValidationError):
        c.HarmonicResult(candidate_id="c1", status="not_applicable",
                         reason="no chroma", qmax_score=0.0, coverage=0.0)


def test_a_dictionary_and_a_list_are_claims_too():
    """C1: the carrier does not matter, what matters is that the field claims something."""
    with pytest.raises(ValidationError):
        c.FingerprintResult(candidate_id="c1", status="gated", reason="x",
                            transform={"tempo": 1.06})
    with pytest.raises(ValidationError):
        c.LyricsResult(candidate_id="c1", status="gated", reason="x",
                       matched_spans=[{"query_text": "a"}])
    with pytest.raises(ValidationError):
        c.MelodicResult(candidate_id="c1", status="failed", reason="x",
                        matched_ngrams=[{"ngram": [1, 2]}])
    with pytest.raises(ValidationError):
        c.HarmonicResult(candidate_id="c1", status="gated", reason="x",
                         alignment_path=[(3, 5)])
    with pytest.raises(ValidationError):
        c.HarmonicResult(candidate_id="c1", status="gated", reason="x",
                         chord_sequence=["C", "G"])


def test_a_status_other_than_ok_with_only_default_values_passes():
    r = c.FingerprintResult(candidate_id="c1", status="not_applicable",
                            reason="no candidate audio")
    assert r.peak_ratio is None
    assert r.repetitions == 0


def test_the_taxonomy_has_one_source_of_truth():
    """I1: the tuple is derived from the type, not written next to it."""
    assert c.VERDICT_CLASSES == get_args(c.VerdictClass)
    assert c.DETECTOR_STATUSES == get_args(c.DetectorStatus)


def test_the_envelope_survives_a_round_trip_through_json():
    """I2: reading without a discriminator built a base DetectorResult and lost the evidence."""
    env = c.DetectorEnvelope(
        detector="fingerprint",
        results=[c.FingerprintResult(candidate_id="cand_01", peak_ratio=0.82,
                                     query_span=(1.0, 20.0), repetitions=2)],
    )
    returned = c.DetectorEnvelope.model_validate_json(env.model_dump_json())
    assert isinstance(returned.results[0], c.FingerprintResult)
    assert returned.results[0].peak_ratio == 0.82
    assert returned.results[0].query_span == (1.0, 20.0)
    assert returned == env


def test_every_result_type_survives_a_round_trip_through_json():
    for result in (
        c.HarmonicResult(candidate_id="c1", qmax_score=0.61, coverage=0.5,
                         chord_sequence=["C", "G"]),
        c.LyricsResult(candidate_id="c1", jaccard=0.64, language="en"),
        c.MelodicResult(candidate_id="c1", longest_common_run=11),
    ):
        env = c.DetectorEnvelope(detector=result.detector, results=[result])
        returned = c.DetectorEnvelope.model_validate_json(env.model_dump_json())
        assert type(returned.results[0]) is type(result)
        assert returned.results[0] == result


def test_a_result_without_a_tag_takes_it_from_the_envelope():
    """Section 7.0 writes a result as {"candidate_id": "cand_07"}, without a tag."""
    env = c.DetectorEnvelope.model_validate(
        {"detector": "lyrics", "status": "ok", "reason": None,
         "results": [{"candidate_id": "cand_07", "jaccard": 0.64}]}
    )
    assert isinstance(env.results[0], c.LyricsResult)
    assert env.results[0].jaccard == 0.64


def test_assignment_after_construction_is_validated_too():
    """I3: a detector computes first and sets the status later."""
    r = c.FingerprintResult(candidate_id="c1", peak_ratio=0.9)
    with pytest.raises(ValidationError):
        r.status = "gated"
    assert r.status == "ok"
    assert r.peak_ratio == 0.9


def test_an_envelope_with_a_status_other_than_ok_allows_no_numbers_in_the_results():
    """I4: section 7.0 puts both status levels on an equal footing."""
    with pytest.raises(ValidationError):
        c.DetectorEnvelope(
            detector="lyrics", status="gated", reason="asr_confidence",
            results=[c.LyricsResult(candidate_id="c1", jaccard=0.83)],
        )
    env = c.DetectorEnvelope(
        detector="lyrics", status="not_applicable", reason="all candidates instrumental",
        results=[c.LyricsResult(candidate_id="c1", status="not_applicable",
                                reason="instrumental")],
    )
    assert env.results[0].jaccard is None
    env.status = "ok"
    env.results = [c.LyricsResult(candidate_id="c1", jaccard=0.83)]
    with pytest.raises(ValidationError):
        env.status = "gated"
    assert env.status == "ok"


def test_span_length_without_a_span_is_none():
    """I5: 0.0 would satisfy the length condition for EXCERPT_PHONOGRAM."""
    assert c.FingerprintResult(candidate_id="c1").span_length is None
    assert c.FingerprintResult(candidate_id="c1",
                               query_span=(1.0, 20.0)).span_length == 19.0


def test_legal_is_never_null_on_the_wire():
    """Section 12 shows "legal": {} - an empty Legal is the valid state "we know nothing"."""
    entry = c.RankingEntry(rank=1, candidate=_candidate(), verdict_class="NONE",
                           probability_status="uncalibrated")
    assert entry.legal == c.Legal()
    with_null = c.RankingEntry(rank=1, candidate=_candidate(), verdict_class="NONE",
                               probability_status="uncalibrated", legal=None)
    assert with_null.legal == c.Legal()
    assert with_null.model_dump()["legal"]["license_status"] == "unknown"
