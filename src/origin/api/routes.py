"""The endpoints of section 12 of the specification.

`POST /api/analyze` creates a job, `GET /api/jobs/{id}/stream` carries the run
as SSE, `GET /api/jobs/{id}/result` gives the current state of the result, and
`POST /api/explain` describes one ranking entry in words.

On top of that, two audio sources for the A/B playback on screen E4 (section
13.2): `GET /api/jobs/{id}/audio` serves the analysis input material, and
`GET /api/audio/candidate/{id}` a candidate's recording. Both support range
requests, because without them the browser will not seek the recording to the
synchronised point and the whole point of switching playback disappears. All
disk access goes through `origin.api.audio`, which makes sure we never leave the
audio directory.

Stub mode is switched on by `ORIGIN_MOCK=1` and is read **on every request**,
not at module import: the frontend process and the tests toggle it at runtime.
"""
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from origin import config
from origin.api import audio
from origin.api import jobs as job_store
from origin.api import mock
from origin.contracts import AnalyzeResult, Candidate, CandidateSet, RankingEntry

router = APIRouter(prefix="/api")

# One store per process. Jobs live in memory and die with the server - section
# 12 knows no persistence, and a demo lasts less than a process.
store = job_store.JobStore()


class AnalyzeRequest(BaseModel):
    url: str
    candidate_set: str = "demo_01"


class AnalyzeResponse(BaseModel):
    job_id: str


class ExplainRequest(BaseModel):
    job_id: str
    candidate_id: str


class ExplainResponse(BaseModel):
    explanation: str = Field(description="A natural language description, generated on demand.")


def stub_mode() -> bool:
    return os.environ.get("ORIGIN_MOCK", "").strip().lower() not in ("", "0", "false", "no")


def _load_set(set_id: str) -> CandidateSet:
    """The candidate manifest, or a 404.

    The import inside the function is deliberate: `candidates` is being built in
    parallel and may not exist yet, and one missing module must not bring down
    the import of the whole API and block a frontend working on stubs.
    """
    try:
        from origin import candidates
    except ImportError as error:  # pragma: no cover - a transitional state of the plan
        raise HTTPException(
            status_code=503,
            detail="the candidate manifest is not available yet; "
                   "to work on the interface run the API with ORIGIN_MOCK=1",
        ) from error
    try:
        return candidates.load_set(set_id)
    except (FileNotFoundError, KeyError, ValueError) as error:
        raise HTTPException(
            status_code=404, detail=f"unknown candidate set '{set_id}'"
        ) from error


def _checked_source(url: str) -> str:
    """The input material address, or a 400. An allow-list, never a deny-list.

    Two forms are accepted and nothing else: an `http(s)` address, and a path
    to a file in the directory `config.queries_dir()` names. Anything else -
    another scheme, and above all any other path on disk - is refused before
    the engine sees it.

    Without this the field is an unauthenticated read of any file on the
    server: `ingest.load_clip` treats whatever is not an address as a path,
    opens it, decodes it, and the SSE stream reports back that it existed and
    how long it was. The path is compared only after `realpath`, so `..` and a
    symlink pointing out of the directory end the same way as an absolute path
    somewhere else.
    """
    if url.startswith(("http://", "https://")):
        return url
    root = os.path.realpath(config.queries_dir())
    file = os.path.realpath(url)
    if file != root and os.path.commonpath((root, file)) == root:
        return file
    raise HTTPException(
        status_code=400,
        detail="the address must be an http:// or https:// URL, "
               "or a path to a file in the input material directory",
    )


def _engine():
    """The pipeline module, or a readable 503.

    The import inside the function, for the same reason as with the manifest:
    the engine drags in numpy, librosa and four detectors. A frontend process
    running on stubs has no reason at all to load them, and one missing heavy
    dependency must not bring down the import of the whole API.
    """
    try:
        from origin import pipeline
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail=f"the analysis engine cannot be loaded ({error}); "
                   "to work on the interface run the API with ORIGIN_MOCK=1",
        ) from error
    return pipeline


@router.get("/health")
def health() -> dict[str, Any]:
    """Whether the API stands and whether it answers from stubs. The frontend must see that difference.

    `mock_scenarios` are the keywords recognised in the query address: screen E1
    builds its example buttons from them instead of guessing what the stub can
    do.
    """
    return {"status": "ok", "mock": stub_mode(),
            "mock_scenarios": sorted(mock.SCENARIOS)}


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request_body: AnalyzeRequest) -> AnalyzeResponse:
    # `async def`, because the analysis starts as a background task and needs a
    # running event loop. Refreshing the page halfway must not cancel it.
    if stub_mode():
        if request_body.candidate_set not in mock.KNOWN_SETS:
            raise HTTPException(
                status_code=404,
                detail=f"unknown candidate set '{request_body.candidate_set}'",
            )
        scenario = mock.select_scenario(request_body.url)
        job_id = store.create(request_body.url, request_body.candidate_set)
        # The stub downloads nothing, so it only points at where the input
        # material would lie if somebody put it there. Whether the file exists
        # is decided only when the result is assembled.
        store.set_audio_path(job_id, mock.query_audio_path(request_body.candidate_set))
        # The level 1 result is ready straight away, just as in a real run it
        # would be ready after five seconds. Level 2 arrives over the stream.
        store.set_result(job_id, mock.partial_result(scenario))
        store.start(job_id, mock.run(store, job_id, scenario))
        return AnalyzeResponse(job_id=job_id)

    # The real path. We load the set either way, so that a wrong name gives a
    # 404 before anything starts.
    candidate_set = _load_set(request_body.candidate_set)
    # The allow-list runs after the set is loaded, so that a wrong set name
    # still gives the 404 it always gave, and before the engine is imported,
    # so that a refused address costs nothing.
    source = _checked_source(request_body.url)
    pipeline = _engine()
    job_id = store.create(request_body.url, request_body.candidate_set)
    # We store the input material only when it is a file on disk: with an
    # address, screen E4 has nothing to play on the query side, because the
    # downloaded file lives in a temporary directory and disappears with ingest.
    if not source.startswith(("http://", "https://")):
        store.set_audio_path(job_id, source)
    store.start(job_id, pipeline.run(
        source,
        request_body.candidate_set,
        candidates=candidate_set.candidates,
        # The partial result lands in the store before the `verdict` event, so a
        # frontend which fetches /result immediately on that event gets the
        # version matching what it has just seen in the stream.
        on_result=lambda result: store.set_result(job_id, result),
    ))
    return AnalyzeResponse(job_id=job_id)


@router.get("/jobs/{job_id}/stream")
async def stream(job_id: str) -> StreamingResponse:
    if not store.exists(job_id):
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")
    return StreamingResponse(
        store.stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Without this a proxy buffers the stream and the partial verdict
            # arrives together with the final one, that is the whole product
            # feature disappears on the way.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/jobs/{job_id}/result", response_model=None)
def result(job_id: str) -> AnalyzeResult | JSONResponse:
    """The current state of the result: partial after level 1, final after level 2.

    The audio URLs are added only here, because they depend on the job
    identifier rather than on what the engine computed. The result in the store
    stays unchanged, so the next read will compute them again against the
    current state of the disk.
    """
    try:
        job = store.get(job_id)
        return audio.fill_in_urls(
            store.get_result(job_id),
            job_id=job_id,
            set_id=job.candidate_set,
            query_path=job.audio_path,
        )
    except job_store.ResultNotReady:
        # The job exists but there is nothing to show yet. A 404 would lie about
        # its existence, and an empty ranking would pretend nothing was found.
        return JSONResponse({"job_id": job_id, "status": "pending"}, status_code=202)
    except job_store.UnknownJob:
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'") from None


@router.get("/audio/candidate/{candidate_id}", response_model=None)
def candidate_audio(
    candidate_id: str,
    request: Request,
    set_id: str = Query("demo_01", alias="set"),
) -> Response:
    """A candidate's recording for the A/B playback on screen E4.

    The identifier is resolved by **the manifest alone**. We assemble nothing
    from the path that arrived in the request: that is the only way to stop an
    endpoint serving files from disk from becoming a read of any file on the
    server.
    """
    candidate = _candidate(set_id, candidate_id)
    file = _audio_file(candidate.audio_path, f"of candidate '{candidate_id}'")
    return audio.audio_response(file, request.headers.get("range"))


@router.get("/jobs/{job_id}/audio", response_model=None)
def query_audio(job_id: str, request: Request) -> Response:
    """The analysis input material. The other side of the A/B switch."""
    try:
        job = store.get(job_id)
    except job_store.UnknownJob:
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'") from None
    if job.audio_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"job '{job_id}' has no stored input material",
        )
    file = _audio_file(job.audio_path, f"of the query of job '{job_id}'")
    return audio.audio_response(file, request.headers.get("range"))


def _candidate(set_id: str, candidate_id: str) -> Candidate:
    """A candidate from the manifest, or a 404. Stub mode has its own fixed set."""
    if stub_mode():
        if set_id not in mock.KNOWN_SETS:
            raise HTTPException(
                status_code=404, detail=f"unknown candidate set '{set_id}'"
            )
        candidate = mock.candidates().get(candidate_id)
    else:
        candidate_set = _load_set(set_id)
        candidate = next((c for c in candidate_set.candidates if c.id == candidate_id), None)
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown candidate '{candidate_id}' in set '{set_id}'",
        )
    return candidate


def _audio_file(audio_path: str, description: str) -> Path:
    """A manifest path into a file to serve, or a readable 404.

    A path from outside the audio directory and a file that does not exist end
    the same way: a 404 without an exception trace and without a directory name.
    The server's directory layout is not information for the browser, and
    distinguishing those two cases in the message would tell an attacker whether
    they hit.
    """
    try:
        file = audio.resolve(audio_path)
    except audio.OutsideAudioRoot:
        raise HTTPException(status_code=404, detail=f"no audio file {description}") from None
    if not file.is_file():
        raise HTTPException(status_code=404, detail=f"no audio file {description}")
    return file


@router.post("/explain", response_model=ExplainResponse)
def explain(request_body: ExplainRequest) -> ExplainResponse:
    """A description in words for one ranking entry. Called on the user's demand.

    Section 12: this is the only place with a language model and it has to stay
    off the critical path. In stub mode a fixed text comes back, without any
    model.
    """
    try:
        result_for_job = store.get_result(request_body.job_id)
    except job_store.ResultNotReady:
        raise HTTPException(
            status_code=409, detail=f"job '{request_body.job_id}' has no result yet"
        ) from None
    except job_store.UnknownJob:
        raise HTTPException(
            status_code=404, detail=f"unknown job '{request_body.job_id}'"
        ) from None

    entry = _entry(result_for_job, request_body.candidate_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"candidate '{request_body.candidate_id}' does not appear in the ranking",
        )
    if stub_mode():
        return ExplainResponse(explanation=mock.explanation(entry))
    raise HTTPException(
        status_code=503,
        detail="the language model is not wired in; run the API with ORIGIN_MOCK=1",
    )


def _entry(result: AnalyzeResult, candidate_id: str) -> RankingEntry | None:
    return next((e for e in result.ranking if e.candidate.id == candidate_id), None)
