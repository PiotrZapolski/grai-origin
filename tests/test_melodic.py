import pytest
from origin.detectors import melodic as m


def test_intervals_are_transposition_invariant():
    """Section 7.4 step 4: this is the whole idea of the interval representation."""
    a = [60, 62, 64, 65]
    b = [67, 69, 71, 72]  # the same melody a fifth higher
    assert m.to_intervals(a) == m.to_intervals(b) == [2, 2, 1]


def test_ngrams_have_the_requested_length():
    assert m.ngrams([2, 2, 1, -3, -2], n=4) == [(2, 2, 1, -3), (2, 1, -3, -2)]


def test_the_longest_common_run():
    a = [2, 2, 1, -3, -2, 5, 5]
    b = [9, 9, 2, 2, 1, -3, -2, 7]
    assert m.longest_common_run(a, b) == 5


def test_no_common_run_gives_zero():
    assert m.longest_common_run([1, 2, 3], [7, 8, 9]) == 0


def test_ornaments_do_not_destroy_the_match():
    """Section 7.4: a melody played with ornaments is still the same melody."""
    plain = [60, 62, 64, 65, 67]
    ornamented = [60, 61, 62, 64, 65, 66, 67]
    assert m.mongeau_sankoff(m.to_intervals(plain), m.to_intervals(ornamented)) < 0.5


def test_different_melodies_give_a_large_distance():
    assert m.mongeau_sankoff([2, 2, 1], [-7, 5, -3]) > 0.7


def test_a_single_note_does_not_blow_up():
    assert m.to_intervals([60]) == []
    assert m.ngrams([], n=4) == []


def test_the_detector_returns_an_envelope_at_level_two():
    d = m.MelodicDetector()
    assert d.level == 2


@pytest.mark.heavy
def test_transcription_detects_the_dominant_line(chord_wav):
    """The highest active note in a frame, with hysteresis against flicker."""
    from origin import ingest
    notes = m.transcribe_melody(ingest.load_clip(chord_wav))
    assert len(notes) >= 4


# --- below: additions to the set from the brief -----------------------------
# The heavy models do not enter the test environment (the owner's decision), so
# the detector's behaviour WITHOUT a model is a production path rather than an
# exception, and has to be guarded by a test just like the algorithm itself.


def test_identical_melodies_give_a_distance_of_zero():
    assert m.mongeau_sankoff([2, 2, 1, -3], [2, 2, 1, -3]) == 0.0


def test_the_distance_always_lies_between_zero_and_one():
    """The normalisation from section 7.4: ms_distance goes to fusion as a 0-1 number."""
    pairs = [
        ([], []),
        ([2], []),
        ([], [2]),
        ([12, -12, 12, -12], [1]),
        ([1, 1, 1], [11, -11, 11, -11, 11, -11, 11]),
    ]
    for a, b in pairs:
        d = m.mongeau_sankoff(a, b)
        assert 0.0 <= d <= 1.0, (a, b, d)


def test_empty_against_non_empty_is_the_maximum_distance():
    assert m.mongeau_sankoff([], [2, 2, 1]) == 1.0


def test_ngrams_longer_than_the_sequence_give_nothing():
    assert m.ngrams([2, 2], n=4) == []


def test_the_common_run_counts_intervals_not_notes():
    """A transposition must not shorten the run - that is the whole point of section 7.4."""
    a = m.to_intervals([60, 62, 64, 65, 67])
    b = m.to_intervals([72, 74, 76, 77, 79])
    assert m.longest_common_run(a, b) == 4


def test_intervals_also_accept_notes():
    notes = [m.Note(60, 0.0, 0.5), m.Note(62, 0.5, 1.0), m.Note(64, 1.0, 1.5)]
    assert m.to_intervals(notes) == [2, 2]


def test_without_a_model_the_envelope_is_failed_with_the_reason_model_unavailable(sine_wav, monkeypatch):
    """The owner's decision: a missing model is a state, not a failure of the caller.

    Section 9.1 requires fusion to cope with any envelope other than ok, so a
    missing basic-pitch has to leave the detector as `failed` with a
    recognisable reason rather than as an exception escaping into the pipeline.
    """
    from origin import ingest

    monkeypatch.setattr(m, "model_available", lambda: False)
    envelope = m.MelodicDetector().run(ingest.load_clip(sine_wav), [])
    assert envelope.status == "failed"
    assert envelope.reason is not None and "model_unavailable" in envelope.reason
    # Section 7.0: an envelope other than ok carries not a single number.
    assert envelope.results == []


def test_transcription_without_the_package_mentions_the_heavy_group(sine_wav, monkeypatch):
    from origin import ingest

    monkeypatch.setattr(m, "model_available", lambda: False)
    with pytest.raises(ImportError, match="heavy"):
        m.transcribe_melody(ingest.load_clip(sine_wav))


def test_matched_ngrams_find_the_common_phrase():
    query = [2, 2, 1, -3, -2, 5]
    candidate = [9, 9, 2, 2, 1, -3, -2, 7]
    hits = m.matched_ngrams(query, candidate)
    assert hits, "the common five-element phrase has to be found"
    longest = hits[0]
    assert longest["interval_seq"] == [2, 2, 1, -3, -2]
    assert longest["query_index"] == 0
    assert longest["candidate_index"] == 2


def test_matched_ngrams_are_empty_when_nothing_matches():
    assert m.matched_ngrams([1, 2, 3, 4, 5], [-9, -8, -7, -6, -5]) == []
