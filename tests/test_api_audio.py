"""Serving the query and candidate audio. Sections 12 and 13.2 of the specification.

Screen E4 switches playback between the query and the candidate at a
synchronised point. For the browser to be able to seek to a requested second,
the server has to support range requests - otherwise the `audio` element
downloads the file from the beginning and the whole playback synchronisation
ceases to exist.

The second thread of these tests is security. The application stands on a
public address, and an endpoint serving files from disk by an identifier taken
from a request is the classic route to leaking any file from the server. An
identifier may be resolved only through the manifest, and the resulting path
has to lie inside the audio directory even after symlinks are expanded.

**No candidate identifier is written by hand here.** These tests are about
serving files and the `Range` header, not about which candidate won the
ranking, so the identifier comes from the response or from the stub catalogue.
A pinned `cand_07` broke them on every change to the stub scenarios, that is on
a change that had nothing to do with them.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from origin.api import audio, mock

CONTENT = bytes(range(256)) * 4  # 1024 bytes, each with a different value within a block
CANDIDATE_SET = "demo_01"


@pytest.fixture
def audio_root(tmp_path, monkeypatch):
    """The audio directory for the duration of the test. We never touch the real data/audio."""
    directory = tmp_path / "audio"
    directory.mkdir()
    monkeypatch.setenv("ORIGIN_AUDIO_ROOT", str(directory))
    return directory


@pytest.fixture
def client(audio_root, monkeypatch):
    monkeypatch.setenv("ORIGIN_MOCK", "1")
    from origin.api.app import app
    return TestClient(app)


def _file(audio_root, name: str, content: bytes = CONTENT) -> Path:
    path = audio_root / name
    path.write_bytes(content)
    return path


def _start_job(client) -> str:
    return client.post("/api/analyze", json={"url": "https://example.com/a",
                                             "candidate_set": CANDIDATE_SET}).json()["job_id"]


def _ranking(client, job_id: str) -> list[dict]:
    return client.get(f"/api/jobs/{job_id}/result").json()["ranking"]


def _candidate_url(candidate_id: str) -> str:
    return f"/api/audio/candidate/{candidate_id}?set={CANDIDATE_SET}"


@pytest.fixture
def leader(client) -> dict:
    """The candidate in first place in the ranking, straight from the API response.

    Which entry that is and what it is called is decided by the stub. Here we
    only care that it has an identifier and an audio path.
    """
    return _ranking(client, _start_job(client))[0]["candidate"]


@pytest.fixture
def candidate_with_file(audio_root, leader) -> dict:
    """The same candidate, but its recording really lies in the audio directory."""
    _file(audio_root, Path(leader["audio_path"]).name)
    return leader


# --------------------------------------------------------------------------
# Candidate audio: the whole file
# --------------------------------------------------------------------------

def test_candidate_audio_serves_the_whole_file(client, candidate_with_file):
    r = client.get(_candidate_url(candidate_with_file["id"]))
    assert r.status_code == 200
    assert r.content == CONTENT
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-type"].startswith("audio/")


def test_an_unknown_candidate_gives_a_404(client):
    r = client.get(_candidate_url("no_such_candidate"))
    assert r.status_code == 404
    assert "no_such_candidate" in r.json()["detail"]


def test_an_unknown_set_gives_a_404(client, candidate_with_file):
    r = client.get(f"/api/audio/candidate/{candidate_with_file['id']}?set=no_such_set")
    assert r.status_code == 404


def test_a_missing_file_gives_a_readable_404_without_the_directory_layout(client, audio_root, leader):
    """The candidate is in the manifest, the file is not. That is a 404, not an exception trace."""
    r = client.get(_candidate_url(leader["id"]))
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert leader["id"] in detail
    # The message must not carry a server path or the name of the audio directory.
    assert str(audio_root) not in detail
    assert "data/audio" not in detail


# --------------------------------------------------------------------------
# Range requests
# --------------------------------------------------------------------------

def test_a_range_gives_a_206_with_a_slice(client, candidate_with_file):
    r = client.get(_candidate_url(candidate_with_file["id"]),
                   headers={"Range": "bytes=100-199"})
    assert r.status_code == 206
    assert r.content == CONTENT[100:200]
    assert r.headers["content-range"] == f"bytes 100-199/{len(CONTENT)}"
    assert r.headers["content-length"] == "100"
    assert r.headers["accept-ranges"] == "bytes"


def test_an_open_ended_range_ends_at_the_end_of_the_file(client, candidate_with_file):
    r = client.get(_candidate_url(candidate_with_file["id"]),
                   headers={"Range": "bytes=1000-"})
    assert r.status_code == 206
    assert r.content == CONTENT[1000:]
    assert r.headers["content-range"] == f"bytes 1000-{len(CONTENT) - 1}/{len(CONTENT)}"


def test_a_suffix_range_gives_the_tail_of_the_file(client, candidate_with_file):
    r = client.get(_candidate_url(candidate_with_file["id"]),
                   headers={"Range": "bytes=-24"})
    assert r.status_code == 206
    assert r.content == CONTENT[-24:]
    assert r.headers["content-range"] == f"bytes {len(CONTENT) - 24}-{len(CONTENT) - 1}/{len(CONTENT)}"


def test_a_range_beyond_the_file_gives_a_416(client, candidate_with_file):
    r = client.get(_candidate_url(candidate_with_file["id"]),
                   headers={"Range": f"bytes={len(CONTENT)}-{len(CONTENT) + 10}"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(CONTENT)}"


def test_an_unreadable_header_serves_the_whole_file(client, candidate_with_file):
    """RFC 9110: a range that cannot be read is not interpreted."""
    r = client.get(_candidate_url(candidate_with_file["id"]),
                   headers={"Range": "seconds=1-2"})
    assert r.status_code == 200
    assert r.content == CONTENT


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-0", (0, 0)),
        ("bytes=0-", (0, 1023)),
        ("bytes=-1", (1023, 1023)),
        ("bytes=10-5000", (10, 1023)),  # the end clipped to the file size
        ("bytes=5-9, 20-30", (5, 9)),   # we take the first range from the list
    ],
)
def test_range_parsing(header, expected):
    assert audio.range_from_header(header, 1024) == expected


@pytest.mark.parametrize("header", [None, "", "bytes=", "bytes=abc-def", "bytes=x"])
def test_an_unreadable_range_is_no_range(header):
    assert audio.range_from_header(header, 1024) is None


@pytest.mark.parametrize("header", ["bytes=1024-2048", "bytes=2000-"])
def test_an_unsatisfiable_range_raises(header):
    with pytest.raises(audio.UnsatisfiableRange):
        audio.range_from_header(header, 1024)


# --------------------------------------------------------------------------
# Security: nothing from outside the audio directory
# --------------------------------------------------------------------------

def test_an_identifier_escaping_the_directory_does_not_reach_the_file(client, tmp_path):
    """We do not build a path from what arrived in the request - this has to be a 404."""
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"secret")
    for identifier in ("../secret.txt", "..%2F..%2Fsecret.txt", "....//secret.txt"):
        r = client.get(_candidate_url(identifier))
        assert r.status_code == 404, identifier
        assert b"secret" not in r.content, identifier


def test_a_manifest_pointing_outside_the_directory_is_rejected(client, tmp_path, monkeypatch):
    """Even a manifest entry will not lead us outside data/audio."""
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"secret")
    original = mock.candidates()
    identifier = next(iter(original))
    replaced = original[identifier].model_copy(
        update={"audio_path": "data/audio/../secret.txt"}
    )
    monkeypatch.setattr(mock, "candidates",
                        lambda: {**original, identifier: replaced})

    r = client.get(_candidate_url(identifier))
    assert r.status_code == 404
    assert b"secret" not in r.content


def test_a_symlink_leading_outside_the_directory_is_rejected(audio_root, tmp_path):
    """The check runs on the absolute path with symlinks expanded."""
    target = tmp_path / "outside.wav"
    target.write_bytes(CONTENT)
    (audio_root / "link.wav").symlink_to(target)
    with pytest.raises(audio.OutsideAudioRoot):
        audio.resolve("data/audio/link.wav")


def test_an_absolute_path_outside_the_directory_is_rejected(audio_root, tmp_path):
    with pytest.raises(audio.OutsideAudioRoot):
        audio.resolve(str(tmp_path / "outside.wav"))


def test_a_path_inside_the_directory_passes(audio_root):
    file = _file(audio_root, "sample.wav")
    assert audio.resolve("data/audio/sample.wav") == file.resolve()


# --------------------------------------------------------------------------
# Query audio
# --------------------------------------------------------------------------

def test_query_audio_serves_the_input_material(client, audio_root):
    _file(audio_root, f"query_{CANDIDATE_SET}.wav")
    job = _start_job(client)
    r = client.get(f"/api/jobs/{job}/audio")
    assert r.status_code == 200
    assert r.content == CONTENT


def test_query_audio_supports_ranges(client, audio_root):
    _file(audio_root, f"query_{CANDIDATE_SET}.wav")
    job = _start_job(client)
    r = client.get(f"/api/jobs/{job}/audio", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206
    assert r.content == CONTENT[:10]
    assert r.headers["content-range"] == f"bytes 0-9/{len(CONTENT)}"


def test_audio_of_an_unknown_job_gives_a_404(client, audio_root):
    _file(audio_root, f"query_{CANDIDATE_SET}.wav")
    r = client.get("/api/jobs/no_such_job/audio")
    assert r.status_code == 404
    assert "no_such_job" in r.json()["detail"]


def test_query_audio_without_a_file_gives_a_404(client):
    job = _start_job(client)
    r = client.get(f"/api/jobs/{job}/audio")
    assert r.status_code == 404


# --------------------------------------------------------------------------
# URLs in the analysis result
# --------------------------------------------------------------------------

def test_the_result_carries_a_playable_query_url(client, audio_root):
    _file(audio_root, f"query_{CANDIDATE_SET}.wav")
    job = _start_job(client)
    result = client.get(f"/api/jobs/{job}/result").json()
    assert result["query"]["waveform_url"] == f"/api/jobs/{job}/audio"
    assert client.get(result["query"]["waveform_url"]).status_code == 200


def test_the_result_carries_a_playable_candidate_url(client, audio_root):
    """We take the URL from the response together with the identifier, not by hand."""
    job = _start_job(client)
    first = _ranking(client, job)[0]["candidate"]
    _file(audio_root, Path(first["audio_path"]).name)

    # A second read, now with the file on disk: the URL is computed on every read.
    first = _ranking(client, job)[0]["candidate"]
    assert first["audio_url"] == _candidate_url(first["id"])
    assert client.get(first["audio_url"]).status_code == 200
    # audio_path stays unchanged: it is a server path, not a playback URL.
    assert first["audio_path"].startswith("data/audio/")


def test_missing_files_do_not_bring_the_result_down(client):
    """Stub mode with an empty data/audio: the result is complete, the URLs are simply absent.

    A stand-in in an evidentiary tool is worse than nothing, so instead of
    substitute audio we return null and the screen says so outright.
    """
    job = _start_job(client)
    r = client.get(f"/api/jobs/{job}/result")
    assert r.status_code == 200
    result = r.json()
    assert result["query"]["waveform_url"] is None
    assert result["ranking"], "the stub ranking must not be empty"
    assert all(p["candidate"]["audio_url"] is None for p in result["ranking"])


def test_the_final_result_carries_the_urls_too(client, audio_root):
    """Level 2 overwrites the result in the store, so the URLs have to be there just the same."""
    _file(audio_root, f"query_{CANDIDATE_SET}.wav")
    job = _start_job(client)
    with_file = _ranking(client, job)[0]["candidate"]
    _file(audio_root, Path(with_file["audio_path"]).name)

    with client.stream("GET", f"/api/jobs/{job}/stream") as r:
        for _ in r.iter_lines():
            pass

    result = client.get(f"/api/jobs/{job}/result").json()
    assert result["status"] == "final"
    assert result["query"]["waveform_url"] == f"/api/jobs/{job}/audio"
    urls = {p["candidate"]["id"]: p["candidate"]["audio_url"] for p in result["ranking"]}
    assert urls[with_file["id"]] == _candidate_url(with_file["id"])
    # Candidates without a file on disk get no URL that would return a 404.
    without_file = {i: u for i, u in urls.items() if i != with_file["id"]}
    assert without_file, "the stub has to carry more than one candidate"
    assert all(u is None for u in without_file.values())
