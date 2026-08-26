"""Tests of the four endpoints of section 12 and of the SSE stream with the two-stage verdict."""
import json

import pytest
from fastapi.testclient import TestClient

from origin.api.mock import COMMONALITY_IDF_THRESHOLD
from origin.config import THRESHOLDS
from origin.contracts import VERDICT_CLASSES, AnalyzeResult


def _make_client(monkeypatch, delay: str):
    """A client inside a context manager, because the analysis runs in the background.

    Without `with`, starlette creates a separate event loop for every request
    and the background task dies together with the response to the POST. With
    `with`, all requests of one client share a single loop, that is exactly how
    uvicorn behaves in production.
    """
    monkeypatch.setenv("ORIGIN_MOCK", "1")
    monkeypatch.setenv("ORIGIN_MOCK_DELAY", delay)
    from origin.api.app import app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(monkeypatch):
    """The stub without delays. For tests that read the whole stream to the end."""
    yield from _make_client(monkeypatch, "0")


@pytest.fixture
def slow_client(monkeypatch):
    """The stub with a pace, so that the partial state lasts at all.

    With a zero delay, level 2 finishes before the test manages to ask for the
    result - that is an artifact of the stub, not of the contract. A real run
    has five seconds for level 1 and thirty for level 2 (section 15).
    """
    yield from _make_client(monkeypatch, "0.05")


def _start_job(client, candidate_set: str = "demo_01", url: str = "https://example.com/a") -> str:
    return client.post("/api/analyze",
                       json={"url": url, "candidate_set": candidate_set}).json()["job_id"]


def _events(client, job_id: str) -> list[dict]:
    with client.stream("GET", f"/api/jobs/{job_id}/stream") as r:
        return [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ")]


def test_analyze_returns_a_job_id(client):
    r = client.post("/api/analyze", json={"url": "https://example.com/a",
                                          "candidate_set": "demo_01"})
    assert r.status_code == 200
    assert "job_id" in r.json()


def test_the_result_starts_out_partial(slow_client):
    job = slow_client.post("/api/analyze",
                           json={"url": "https://example.com/a",
                                 "candidate_set": "demo_01"}).json()["job_id"]
    r = slow_client.get(f"/api/jobs/{job}/result").json()
    assert r["status"] in ("partial", "complete")
    assert set(r["completed_levels"]) <= {1, 2}


def test_the_verdict_appears_twice(client):
    """Section 12: partial after level 1, final after level 2."""
    job = client.post("/api/analyze", json={"url": "https://example.com/a",
                                            "candidate_set": "demo_01"}).json()["job_id"]
    with client.stream("GET", f"/api/jobs/{job}/stream") as r:
        verdicts = [json.loads(l[6:])
                    for l in r.iter_lines()
                    if l.startswith("data: ") and json.loads(l[6:])["stage"] == "verdict"]
    assert [v["status"] for v in verdicts] == ["partial", "final"]


def test_every_event_carries_a_level(client):
    job = client.post("/api/analyze", json={"url": "https://example.com/a",
                                            "candidate_set": "demo_01"}).json()["job_id"]
    with client.stream("GET", f"/api/jobs/{job}/stream") as r:
        events = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ")]
    assert all(e["level"] in (1, 2) for e in events)


def test_a_gated_event_carries_the_reason_and_the_next_step(client):
    """Section 12: gated is content, not an error - screen E2 shows it."""
    job = client.post("/api/analyze", json={"url": "https://example.com/a",
                                            "candidate_set": "demo_01"}).json()["job_id"]
    with client.stream("GET", f"/api/jobs/{job}/stream") as r:
        events = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ")]
    gated = [e for e in events if e["status"] == "gated"]
    assert gated and "reason" in gated[0]["detail"]


def test_an_unknown_job_gives_a_404(client):
    assert client.get("/api/jobs/no-such-job/result").status_code == 404


def test_an_unknown_candidate_set_gives_a_404(client):
    r = client.post("/api/analyze", json={"url": "https://example.com/a",
                                          "candidate_set": "no_such_set"})
    assert r.status_code == 404


# --------------------------------------------------------------------------
# The two-stage verdict as a product feature, not a compromise. Sections 4 and 12.
# --------------------------------------------------------------------------

def test_gated_also_carries_the_next_step(client):
    """Without the next field, screen E2 would show the gate as a failure rather than a step."""
    gated = [e for e in _events(client, _start_job(client)) if e["status"] == "gated"]
    assert gated[0]["detail"]["next"] == "separation"


def test_the_levels_do_not_go_backwards_in_the_stream(client):
    events = _events(client, _start_job(client))
    levels = [e["level"] for e in events]
    assert levels == sorted(levels)


def test_the_partial_verdict_ends_level_1_and_the_final_one_ends_level_2(client):
    verdicts = [e for e in _events(client, _start_job(client)) if e["stage"] == "verdict"]
    assert [v["level"] for v in verdicts] == [1, 2]


def test_the_final_verdict_raises_the_confidence_and_says_where_from(client):
    """The verdict has to grow before the viewer's eyes, and the frontend must know what it replaces."""
    verdicts = [e for e in _events(client, _start_job(client)) if e["stage"] == "verdict"]
    partial, final = verdicts
    assert final["detail"]["probability"] > partial["detail"]["probability"]
    assert final["detail"]["class"] in VERDICT_CLASSES
    assert final["detail"]["previous_class"] == partial["detail"]["class"]
    assert final["detail"]["previous_probability"] == partial["detail"]["probability"]


def test_level_2_may_change_the_class_of_a_ranking_entry(slow_client):
    """Raising the verdict is a change of class, not just of a number.

    The frontend has to be able to swap the badge and reorder the list without
    reloading the screen, so the stub does both.
    """
    job = _start_job(slow_client)
    before = {p["candidate"]["id"]: p["verdict_class"]
              for p in slow_client.get(f"/api/jobs/{job}/result").json()["ranking"]}
    _events(slow_client, job)
    after_analysis = slow_client.get(f"/api/jobs/{job}/result").json()["ranking"]
    after = {p["candidate"]["id"]: p["verdict_class"] for p in after_analysis}
    assert any(before[k] != after[k] for k in before), "no class was raised"
    order_before = list(before)
    order_after = [p["candidate"]["id"] for p in after_analysis]
    assert order_before != order_after, "the ranking did not reorder"


def test_the_stream_has_the_sse_content_type(client):
    job = _start_job(client)
    with client.stream("GET", f"/api/jobs/{job}/stream") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        list(r.iter_lines())


def test_the_stream_of_an_unknown_job_gives_a_404(client):
    assert client.get("/api/jobs/no-such-job/stream").status_code == 404


def test_the_result_after_the_stream_is_final(slow_client):
    """Level 2 raises the result in the result endpoint too, not only in the stream."""
    job = _start_job(slow_client)
    before = slow_client.get(f"/api/jobs/{job}/result").json()
    assert before["status"] == "partial" and before["completed_levels"] == [1]
    _events(slow_client, job)
    after = slow_client.get(f"/api/jobs/{job}/result").json()
    assert after["status"] == "final" and after["completed_levels"] == [1, 2]


def test_the_final_result_conforms_to_the_contract(client):
    job = _start_job(client)
    _events(client, job)
    AnalyzeResult.model_validate(client.get(f"/api/jobs/{job}/result").json())


# --------------------------------------------------------------------------
# Stub mode is a product: four frontend teams work exclusively on it.
# --------------------------------------------------------------------------

def test_the_stub_gives_a_full_ranking(client):
    job = _start_job(client)
    _events(client, job)
    ranking = client.get(f"/api/jobs/{job}/result").json()["ranking"]
    assert len(ranking) >= 3
    assert [p["rank"] for p in ranking] == list(range(1, len(ranking) + 1))
    assert all(p["verdict_class"] in VERDICT_CLASSES for p in ranking)


def test_the_stub_has_all_four_detectors_in_the_evidence(client):
    job = _start_job(client)
    _events(client, job)
    ranking = client.get(f"/api/jobs/{job}/result").json()["ranking"]
    for entry in ranking:
        assert set(entry["evidence"]) == {"fingerprint", "harmonic", "melodic", "lyrics"}


def test_the_stub_has_a_detector_with_a_status_other_than_ok(client):
    """Section 7.0: the frontend must not assume the detector returned a number."""
    job = _start_job(client)
    _events(client, job)
    ranking = client.get(f"/api/jobs/{job}/result").json()["ranking"]
    statuses = {d["status"] for p in ranking for d in p["evidence"].values()}
    assert statuses - {"ok"}


def test_the_partial_result_does_not_fake_level_2_evidence(slow_client):
    """A missing key means 'not computed yet'. A zero would mean 'checked and there is none'."""
    job = _start_job(slow_client)
    ranking = slow_client.get(f"/api/jobs/{job}/result").json()["ranking"]
    for entry in ranking:
        assert set(entry["evidence"]) == {"fingerprint", "harmonic"}


def test_the_stub_tells_a_raw_probability_apart_from_a_calibrated_one(slow_client):
    """Section 10.5: the UI must tell the two apart, so the stub provides both."""
    job = _start_job(slow_client)
    partial = slow_client.get(f"/api/jobs/{job}/result").json()
    assert partial["calibration"] is None
    assert partial["ranking"][0]["probability_status"] == "uncalibrated"
    _events(slow_client, job)
    final = slow_client.get(f"/api/jobs/{job}/result").json()
    assert final["calibration"]["model_version"]
    assert final["ranking"][0]["probability_status"] == "calibrated"


def test_a_detector_event_carries_the_detail_fields(client):
    """The trap from T2: a list typed as the base class loses subclass fields in JSON.

    Without SerializeAsAny in the contracts, only candidate_id and status would
    be left here, and peak_ratio would never reach the frontend.
    """
    events = _events(client, _start_job(client))
    fingerprint = [e for e in events if e["stage"] == "fingerprint" and e["status"] == "done"][0]
    results = fingerprint["detail"]["envelope"]["results"]
    assert any("peak_ratio" in r and r["peak_ratio"] is not None for r in results)
    harmonic = [e for e in events if e["stage"] == "harmonic" and e["status"] == "done"][0]
    assert any(r.get("qmax_score") for r in harmonic["detail"]["envelope"]["results"])


def test_explain_returns_text_on_demand(client):
    job = _start_job(client)
    _events(client, job)
    candidate = client.get(f"/api/jobs/{job}/result").json()["ranking"][0]["candidate"]["id"]
    r = client.post("/api/explain", json={"job_id": job, "candidate_id": candidate})
    assert r.status_code == 200
    assert len(r.json()["explanation"]) > 40


def test_explain_for_an_unknown_candidate_gives_a_404(client):
    job = _start_job(client)
    r = client.post("/api/explain", json={"job_id": job, "candidate_id": "no_such_candidate"})
    assert r.status_code == 404


def test_without_stub_mode_the_engine_computes_not_the_stub(monkeypatch, tmp_path):
    """A silent stub in production would be a lie, so without ORIGIN_MOCK the engine computes.

    Until T22 this branch returned 503, because there was no engine to plug in.
    Now there is, so the test guards the opposite: the job has to really start,
    and the stream has to carry the `ingest` stage, which the stub will never
    produce for a non-existent file - it does not read the disk and ends every
    run with a verdict.
    """
    monkeypatch.delenv("ORIGIN_MOCK", raising=False)
    monkeypatch.setenv("ORIGIN_PREWARM", "0")
    # The input material directory, so that the path passes the allow-list on
    # the endpoint and the run gets as far as trying to open the file.
    monkeypatch.setenv("ORIGIN_QUERIES_ROOT", str(tmp_path))
    missing_file = str(tmp_path / "no-such-file.wav")

    from origin.api.app import app
    with TestClient(app) as client:
        r = client.post("/api/analyze", json={"url": missing_file,
                                              "candidate_set": "demo_01"})
        assert r.status_code == 200
        events = _events(client, r.json()["job_id"])

    stages = [(e["stage"], e["status"]) for e in events]
    assert ("ingest", "failed") in stages
    assert ("verdict", "failed") in stages


def test_without_stub_mode_an_unknown_set_still_gives_a_404(monkeypatch):
    """A wrong set name has to give a 404 before anything starts."""
    monkeypatch.delenv("ORIGIN_MOCK", raising=False)
    monkeypatch.setenv("ORIGIN_PREWARM", "0")
    from origin.api.app import app
    with TestClient(app) as client:
        r = client.post("/api/analyze", json={"url": "/tmp/a.wav",
                                              "candidate_set": "no_such_set"})
    assert r.status_code == 404


def _analyze_without_the_stub(monkeypatch, tmp_path, url: str):
    """One POST /api/analyze against the real path, with the input directory at tmp_path."""
    monkeypatch.delenv("ORIGIN_MOCK", raising=False)
    monkeypatch.setenv("ORIGIN_PREWARM", "0")
    monkeypatch.setenv("ORIGIN_QUERIES_ROOT", str(tmp_path))
    from origin.api.app import app
    with TestClient(app) as client:
        return client.post("/api/analyze",
                           json={"url": url, "candidate_set": "demo_01"})


def test_a_path_outside_the_input_directory_is_refused(monkeypatch, tmp_path):
    """Any file on disk was readable through this field, and the stream said whether it opened.

    `ingest.load_clip` treats whatever is not an address as a path, so
    `{"url": "/etc/shadow"}` made the container open the file and decode it,
    and the SSE stream reported its existence, its duration and the sha256 of
    the decoded signal. That is an unauthenticated file-probe oracle on a
    machine full of production containers.
    """
    r = _analyze_without_the_stub(monkeypatch, tmp_path, "/etc/shadow")
    assert r.status_code == 400
    # The refusal must not tell the caller whether the file was there.
    assert "shadow" not in r.text


def test_climbing_out_of_the_input_directory_is_refused(monkeypatch, tmp_path):
    """The comparison happens after realpath, so `..` does not get around it either."""
    outside = tmp_path.parent / "outside.wav"
    outside.write_bytes(b"")
    r = _analyze_without_the_stub(
        monkeypatch, tmp_path, str(tmp_path / ".." / "outside.wav")
    )
    assert r.status_code == 400


def test_a_scheme_that_is_not_http_is_refused(monkeypatch, tmp_path):
    """file:// and friends are not addresses we fetch, and they are not paths either."""
    r = _analyze_without_the_stub(monkeypatch, tmp_path, "file:///etc/passwd")
    assert r.status_code == 400


def test_a_file_in_the_input_directory_is_accepted(monkeypatch, tmp_path):
    """The allow-list has to let the material we do analyse through, or it is just a wall."""
    query = tmp_path / "query.wav"
    query.write_bytes(b"")
    r = _analyze_without_the_stub(monkeypatch, tmp_path, str(query))
    assert r.status_code == 200


def test_health_says_whether_it_runs_on_stubs(client):
    r = client.get("/api/health").json()
    assert r["mock"] is True


# --------------------------------------------------------------------------
# The verdict must be reachable by the tree of section 9.1, not written by hand.
# --------------------------------------------------------------------------

def _detector_numbers(events: list[dict]) -> dict[str, dict]:
    """Raw numbers per candidate, collected from the envelopes in the stream."""
    numbers: dict[str, dict] = {}
    for event in events:
        envelope = event["detail"].get("envelope")
        if not envelope or event["status"] != "done":
            continue
        for result in envelope["results"]:
            numbers.setdefault(result["candidate_id"], {})[envelope["detector"]] = result
    return numbers


def _tree(a: dict, b: dict, c: dict | None, d: dict | None, mean_idf: float) -> str:
    """An independent rewrite of the tree from section 9.1. The first rule satisfied wins.

    Written from the text of the specification, not imported from the stub -
    otherwise the test would confirm itself. `c` and `d` are None at level 1,
    because detectors C and D have not run yet.
    """
    threshold = {name: t.value for name, t in THRESHOLDS.items()}
    peak = a.get("peak_ratio") or 0.0
    span = a.get("query_span")
    length = (span[1] - span[0]) if span else 0.0
    if peak > threshold["EXACT_PEAK_RATIO"] and length > threshold["EXACT_MIN_SPAN_S"]:
        return "EXACT"
    qmax = b.get("qmax_score") or 0.0
    if a.get("transform") and peak > threshold["MODIFIED_PEAK_RATIO"] and qmax > 0.50:
        return "MODIFIED"
    if (peak > threshold["EXCERPT_PEAK_RATIO"] and length < threshold["EXACT_MIN_SPAN_S"]
            and (a.get("repetitions") or 0) >= threshold["EXCERPT_MIN_REPETITIONS"]):
        return "EXCERPT_PHONOGRAM"

    coverage = b.get("coverage") or 0.0
    lyrics_status = d["status"] if d else None
    semantic = (d.get("semantic_sim") if d else None) or 0.0
    if (peak < threshold["VERSION_MAX_PEAK_RATIO"] and qmax > threshold["VERSION_QMAX"]
            and coverage > threshold["VERSION_COVERAGE"]
            and (semantic > 0.70 or lyrics_status != "ok")):
        return _commonality("VERSION", mean_idf)
    if (c and c["status"] == "ok"
            and (c.get("longest_common_run") or 0) >= threshold["EXCERPT_WORK_MIN_RUN"]
            and coverage < 0.40):
        return _commonality("EXCERPT_WORK", mean_idf)
    if (d and qmax < threshold["LYRICS_MAX_QMAX"] and lyrics_status == "ok"
            and (d.get("jaccard") or 0.0) > threshold["LYRICS_JACCARD"]):
        return _commonality("LYRICS", mean_idf)
    return "NONE"


def _commonality(verdict_class: str, mean_idf: float) -> str:
    if verdict_class in ("VERSION", "LYRICS", "EXCERPT_WORK") and mean_idf < COMMONALITY_IDF_THRESHOLD:
        return "COMMON"
    return verdict_class


def test_every_verdict_is_reachable_by_the_tree_of_9_1(slow_client):
    """A hand-written class can be UNREACHABLE in the tree.

    Rule 4 requires coverage above 0.50, rule 5 below 0.40, and detector B runs
    only at level 1, so it is the same number for both verdicts. A stub that
    declared VERSION at level 1 and EXCERPT_WORK at level 2 was selling a
    transition the engine will never make.
    """
    job = _start_job(slow_client)
    partial = slow_client.get(f"/api/jobs/{job}/result").json()
    events = _events(slow_client, job)
    final = slow_client.get(f"/api/jobs/{job}/result").json()
    numbers = _detector_numbers(events)

    for entry in partial["ranking"]:
        cid = entry["candidate"]["id"]
        expected = _tree(numbers[cid]["fingerprint"], numbers[cid]["harmonic"],
                         None, None, entry["commonality"]["mean_idf"])
        assert entry["verdict_class"] == expected, f"level 1, {cid}"

    for entry in final["ranking"]:
        cid = entry["candidate"]["id"]
        expected = _tree(numbers[cid]["fingerprint"], numbers[cid]["harmonic"],
                         numbers[cid]["melodic"], numbers[cid]["lyrics"],
                         entry["commonality"]["mean_idf"])
        assert entry["verdict_class"] == expected, f"level 2, {cid}"


def test_the_trap_has_a_strong_similarity_not_a_weak_one(client):
    """Demo case 5: "I found a strong similarity and I consider it irrelevant".

    Degradation to COMMON concerns only VERSION, LYRICS and EXCERPT/work, so a
    candidate with a weak harmony falls to NONE and there is no trap. For there
    to be one, qmax and coverage have to cross the VERSION thresholds first.
    """
    job = _start_job(client)
    events = _events(client, job)
    numbers = _detector_numbers(events)
    ranking = client.get(f"/api/jobs/{job}/result").json()["ranking"]
    common = [p for p in ranking if p["verdict_class"] == "COMMON"]
    assert common, "the stub does not show the COMMON case at all"
    for entry in common:
        harmonic = numbers[entry["candidate"]["id"]]["harmonic"]
        assert harmonic["qmax_score"] > THRESHOLDS["VERSION_QMAX"].value
        assert harmonic["coverage"] > THRESHOLDS["VERSION_COVERAGE"].value
        assert entry["commonality"]["mean_idf"] < COMMONALITY_IDF_THRESHOLD
        assert entry["commonality"]["corpus_frequency"] > 100


# --------------------------------------------------------------------------
# Calibration and the legal layer
# --------------------------------------------------------------------------

def test_uncalibrated_classes_do_not_pretend_to_be_calibrated(client):
    """Section 10.4: LYRICS and EXCERPT/work stay explicitly uncalibrated.

    A heading "threshold calibrated on 500 pairs from SecondHandSongs" next to a
    class for which there are and will be no training pairs is an untrue
    statement.
    """
    job = _start_job(client)
    _events(client, job)
    for entry in client.get(f"/api/jobs/{job}/result").json()["ranking"]:
        if entry["verdict_class"] in ("LYRICS", "EXCERPT_WORK", "COMMON", "NONE"):
            assert entry["probability_status"] == "uncalibrated", entry["verdict_class"]


def test_the_risk_flags_come_from_section_11_3(client):
    """Section 11.3 knows two flags and both are in English, like every identifier."""
    allowed = {"recognizable_excerpt", "possible_pastiche"}
    job = _start_job(client)
    _events(client, job)
    for entry in client.get(f"/api/jobs/{job}/result").json()["ranking"]:
        assert set(entry["legal"]["risk_flags"]) <= allowed


def test_the_stub_shows_the_borderline_pastiche_situation(client):
    """The "high modification with recognisability preserved" path from 11.2.

    Without it the legal panel never renders the borderline case.
    """
    job = _start_job(client)
    _events(client, job)
    ranking = client.get(f"/api/jobs/{job}/result").json()["ranking"]
    with_pastiche = [p for p in ranking if "possible_pastiche" in p["legal"]["risk_flags"]]
    assert with_pastiche
    legal_block = with_pastiche[0]["legal"]
    assert legal_block["recognizability"] and legal_block["modification"]
    assert with_pastiche[0]["verdict_layer"] == "phonogram"


def test_a_common_element_and_an_open_licence_get_no_flag(client):
    """Two rows of table 11.2 say "no flag", and one adds an attribution."""
    job = _start_job(client)
    _events(client, job)
    ranking = client.get(f"/api/jobs/{job}/result").json()["ranking"]
    for entry in ranking:
        if entry["verdict_class"] in ("COMMON", "NONE"):
            assert entry["legal"]["risk_flags"] == []
            assert entry["verdict_layer"] is None
        if entry["candidate"]["license"].startswith("cc"):
            assert entry["legal"]["risk_flags"] == []
            assert entry["legal"]["required_attribution"]


def test_the_legal_scores_exist_only_where_they_mean_something(client):
    """11.2: recognisability is derived from A.peak_ratio FOR THE EXCERPT CLASS."""
    job = _start_job(client)
    _events(client, job)
    for entry in client.get(f"/api/jobs/{job}/result").json()["ranking"]:
        if not entry["verdict_class"].startswith("EXCERPT"):
            assert entry["legal"]["recognizability"] is None
            assert entry["legal"]["modification"] is None


# --------------------------------------------------------------------------
# The confidence gate as an envelope status, not only a stage status
# --------------------------------------------------------------------------

def test_the_confidence_gate_gives_an_envelope_without_a_single_number(client):
    """Section 7.0: an envelope other than ok must not carry a number.

    A stage status and an envelope status are two different vocabularies.
    Without a `gated` envelope the bar "rejected by the confidence gate" on E5
    has nothing to stand on, and the contract validator is never exercised by
    the frontend.
    """
    gate = [e for e in _events(client, _start_job(client)) if e["status"] == "gated"]
    envelope = gate[0]["detail"]["envelope"]
    assert envelope["status"] == "gated"
    assert envelope["reason"]
    assert envelope["results"]
    for result in envelope["results"]:
        assert result["status"] == "gated"
        for field, value in result.items():
            if field in ("candidate_id", "status", "reason", "detector"):
                continue
            assert not value, f"field {field} carries a number with status gated"


# --------------------------------------------------------------------------
# The stub does not invent a catalogue of its own
# --------------------------------------------------------------------------

def test_the_stub_does_not_invent_candidates():
    """The same identifier has to mean the same track as in the manifest.

    The manifest cannot be read at runtime: the data/ directory does not enter
    the API image, so the stub holds a mirror of it, and a drift is caught by
    this test.
    """
    from origin import candidates
    from origin.api import mock
    manifest = {c.id: c for c in candidates.load_set("demo_01").candidates}
    for identifier, candidate in mock.CANDIDATES.items():
        assert identifier in manifest, f"{identifier} does not exist in the manifest"
        assert candidate.model_dump() == manifest[identifier].model_dump()


def test_the_known_sets_agree_with_the_catalogue():
    from pathlib import Path

    from origin import candidates
    from origin.api import mock
    on_disk = {p.stem for p in Path(candidates.CANDIDATES_DIR).glob("*.json")}
    assert set(mock.KNOWN_SETS) == on_disk


# --------------------------------------------------------------------------
# The analysis is driven by a background task, not by the stream listener
# --------------------------------------------------------------------------

def test_disconnecting_halfway_does_not_cancel_the_job(client, monkeypatch):
    """Refreshing the page during an analysis has to be reversible.

    When the run was driven by the listener's reads, closing the connection
    killed the producer: the remaining events were never created and `/result`
    returned a partial result for the rest of the process's life.
    """
    monkeypatch.setenv("ORIGIN_MOCK_DELAY", "0.05")
    job = _start_job(client)
    with client.stream("GET", f"/api/jobs/{job}/stream") as r:
        for line in r.iter_lines():
            if line.startswith("data: ") and json.loads(line[6:])["stage"] == "verdict":
                break  # we disconnect right after the partial verdict

    events = _events(client, job)
    assert [e["status"] for e in events if e["stage"] == "verdict"] == ["partial", "final"]
    assert client.get(f"/api/jobs/{job}/result").json()["status"] == "final"


def test_a_second_listener_gets_the_whole_run_from_the_start(client):
    """Connecting after the fact has to give the full set, not the tail of the stage list."""
    job = _start_job(client)
    first = _events(client, job)
    second = _events(client, job)
    assert second == first
    assert second[0]["stage"] == "ingest"


# --------------------------------------------------------------------------
# Five scenarios from section 14, not one
# --------------------------------------------------------------------------

def _scenario_numbers(s) -> dict[str, dict]:
    """Raw numbers per candidate straight from the stub envelopes, without HTTP."""
    from origin.api import mock
    envelopes = (mock.fingerprint_envelope(s), mock.harmonic_envelope(s),
                 mock.lyrics_envelope(s), mock.melodic_envelope(s))
    numbers: dict[str, dict] = {}
    for envelope in envelopes:
        dump = envelope.model_dump(mode="json")
        for result in dump["results"]:
            numbers.setdefault(result["candidate_id"], {})[dump["detector"]] = result
    return numbers


def test_every_scenario_agrees_with_the_tree_of_9_1():
    """The tree applies in all five cases, not only in the default one."""
    from origin.api import mock
    for s in mock.SCENARIOS.values():
        numbers = _scenario_numbers(s)
        for level in (1, 2):
            for entry in mock.result(s, level).ranking:
                cid = entry.candidate.id
                expected = _tree(
                    numbers[cid]["fingerprint"], numbers[cid]["harmonic"],
                    numbers[cid]["melodic"] if level == 2 else None,
                    numbers[cid]["lyrics"] if level == 2 else None,
                    entry.commonality.mean_idf)
                assert entry.verdict_class == expected, f"{s.key}, level {level}, {cid}"


def test_the_scenarios_cover_the_classes_of_section_14():
    """The five demo cases are five different classes. One scenario knows only one."""
    from origin.api import mock
    classes = {p.verdict_class
               for s in mock.SCENARIOS.values()
               for level in (1, 2)
               for p in mock.result(s, level).ranking}
    assert set(VERDICT_CLASSES) == classes, "the frontend has nothing to see every badge on"
    layers = {p.verdict_layer
              for s in mock.SCENARIOS.values()
              for p in mock.result(s, 2).ranking}
    assert {"phonogram", "work", None} == layers


def test_a_scenario_is_chosen_by_the_address(client):
    """Screen E1 has example buttons, so the address has to mean something."""
    from origin.api import mock
    for scenario in mock.SCENARIOS.values():
        keyword = scenario.keywords[0]
        job = _start_job(client, url=f"https://example.com/{keyword}")
        verdict = [e for e in _events(client, job) if e["stage"] == "verdict"][-1]
        expected = mock.result(scenario, 2).ranking[0]
        assert verdict["detail"]["candidate_id"] == expected.candidate.id, keyword
        assert verdict["detail"]["class"] == expected.verdict_class


def test_health_lists_the_scenarios(client):
    r = client.get("/api/health").json()
    assert "common" in r["mock_scenarios"] and len(r["mock_scenarios"]) >= 5


def test_a_query_without_vocals_does_not_go_to_separation(client):
    """The gate from 7.3 makes a decision, it does not report a failure.

    Separating sources in a recording with no vocals would achieve nothing, so
    the next step is the melody. That is a different decision, not the same
    failure.
    """
    events = _events(client, _start_job(client, url="https://example.com/trap"))
    gate = [e for e in events if e["status"] == "gated"][0]
    assert gate["detail"]["reason"] == "no_vocals"
    assert gate["detail"]["next"] == "melodic"
    assert not [e for e in events if e["stage"] == "separation"]
