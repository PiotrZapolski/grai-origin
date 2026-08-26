import pytest
from origin.contracts import Candidate
from origin.detectors import lyrics as ly


def _cand(**kw):
    d = dict(id="c1", name="N", artist="A", source_url="https://example.com/a",
             audio_path="data/audio/c1.wav", license="unknown", instrumental=False)
    d.update(kw)
    return Candidate(**d)


def test_an_instrumental_candidate_gets_not_applicable():
    """Global Constraint 4 and section 7.3 step 1."""
    env = ly.LyricsDetector().run(clip=None, candidates=[_cand(instrumental=True)])
    r = env.results[0]
    assert r.status == "not_applicable"
    assert r.reason == "instrumental"
    assert r.jaccard is None, "not applicable is not zero"


def test_all_instrumental_finishes_without_transcription(monkeypatch):
    """Section 7.3: this is where the actual saving comes from."""
    calls = []
    monkeypatch.setattr(ly, "transcribe", lambda c: calls.append(1))
    env = ly.LyricsDetector().run(clip=object(), candidates=[
        _cand(id="a", instrumental=True), _cand(id="b", instrumental=True)])
    assert env.status == "not_applicable"
    assert calls == [], "whisper must not be started when there is nothing to compare against"


def test_the_gate_rejects_low_confidence():
    ok, reason = ly.gate(ly.Transcript(text="la la", confidence=0.2, language="en",
                                       language_stable=True, words=[]))
    assert ok is False
    assert reason == "asr_confidence"


def test_the_gate_rejects_an_unstable_language():
    ok, reason = ly.gate(ly.Transcript(text="x", confidence=0.9, language="en",
                                       language_stable=False, words=[]))
    assert ok is False
    assert reason == "language_unstable"


def test_the_gate_lets_a_good_transcript_through():
    ok, reason = ly.gate(ly.Transcript(text="hello darkness my old friend",
                                       confidence=0.9, language="en",
                                       language_stable=True, words=[]))
    assert ok is True and reason is None


def test_separation_starts_only_after_the_gate_rejects(monkeypatch):
    """Section 7.3 step 4 and decision D3: a fixed cost turned into a conditional one."""
    order = []
    monkeypatch.setattr(ly, "_whisper", lambda y, sr: order.append("whisper") or
                        ly.Transcript(text="", confidence=0.1, language="en",
                                      language_stable=True, words=[]))
    monkeypatch.setattr(ly, "_demucs", lambda y, sr: order.append("demucs") or y)
    ly.transcribe_with_gate(clip=_fake_clip())
    assert order[0] == "whisper", "whisper always first, on the full mix"
    assert "demucs" in order


def test_separation_does_not_start_when_the_gate_let_it_through(monkeypatch):
    order = []
    monkeypatch.setattr(ly, "_whisper", lambda y, sr: order.append("whisper") or
                        ly.Transcript(text="hello darkness my old friend",
                                      confidence=0.95, language="en",
                                      language_stable=True, words=[]))
    monkeypatch.setattr(ly, "_demucs", lambda y, sr: order.append("demucs") or y)
    ly.transcribe_with_gate(clip=_fake_clip())
    assert "demucs" not in order


def test_identical_text_gives_a_jaccard_of_one():
    j, s = ly.compare("hello darkness my old friend", "hello darkness my old friend")
    assert j == pytest.approx(1.0, abs=0.01)


def test_different_text_gives_a_low_jaccard():
    j, s = ly.compare("hello darkness my old friend",
                      "the quick brown fox jumps over")
    assert j < 0.2


def test_matched_spans_carry_the_times_for_highlighting_in_the_ui():
    """Section 7.3: the user sees which words and when."""
    r = ly.build_result("c1", "hello darkness", "hello darkness",
                        words=[("hello", 1.0, 1.5), ("darkness", 1.5, 2.2)])
    assert r.matched_spans
    assert "query_time" in r.matched_spans[0]


@pytest.mark.heavy
def test_the_negative_control_on_an_instrumental(instrumental_audio):
    """Section 7.3: the cheapest correctness test in the whole plan.

    The instrumental-only groups from the catalogue (7,942 of them) are the test
    set for the gate. Anything above the threshold means the gate is set wrong.
    """
    t = ly.transcribe(instrumental_audio)
    ok, _ = ly.gate(t)
    assert ok is False


def test_a_missing_model_gives_a_failed_envelope_not_an_exception(monkeypatch):
    """The owner's decision: without the heavy models the pipeline must keep working.

    Section 9.1 requires fusion to handle an envelope other than ok. Nobody will
    handle an exception from a detector, so a missing model has to end in an
    envelope with a recognisable reason rather than in the failure of the whole
    analysis.
    """
    def no_model(y, sr):
        raise ly.ModelUnavailable("stub: no faster-whisper")

    monkeypatch.setattr(ly, "_whisper", no_model)
    env = ly.LyricsDetector().run(clip=_fake_clip(), candidates=[_cand()])
    assert env.status == "failed"
    assert env.reason == "model_unavailable"
    assert env.results == [], "a failed envelope carries not a single number"


def _fake_clip():
    import numpy as np
    class C:
        y_speech = np.zeros(16000)
        sr_speech = 16000
    return C()
