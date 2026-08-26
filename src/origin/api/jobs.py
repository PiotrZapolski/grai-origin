"""The job store and the SSE stream. Section 12 of the specification.

The store lives in process memory and has no persistence: a job lives as long
as the demo session. The only state that really matters is the **order of
events** - the frontend replays the list of stages on screen E2 from it, and
the verdict arrives twice (partial after level 1, final after level 2).

Events are kept in a plain list rather than in an `asyncio.Queue`, for two
reasons: a queue is bound to the event loop that served it, while a job may be
created in one HTTP request and read in another; a list also allows replaying
the events to a listener who connected too late. Screen E2 has to show the
whole run, including the part before the connection.

**The analysis is driven by a background task, not by the listener.** A stream
listener is a reader only, and its disconnection must not cancel anything:
refreshing the page halfway through an analysis has to be reversible, and with
a read-driven producer it used to end with a job that stayed partial forever.
"""
import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from origin.contracts import AnalyzeResult, StreamEvent

# How often a listener checks whether a new event has been added, when it does
# not drive the producer itself. Small, because it concerns only the second and
# further listeners.
POLL_INTERVAL_S = 0.05


class UnknownJob(LookupError):
    """There is no job with this identifier in this process."""


class ResultNotReady(LookupError):
    """The job exists but has no result yet, not even a partial one."""


@dataclass
class Job:
    """One analysis request together with the task computing it."""

    id: str
    url: str
    candidate_set: str
    # The analysis input material on disk. None means nothing was stored and
    # screen E4 has nothing to play on the query side.
    audio_path: str | None = None
    events: list[StreamEvent] = field(default_factory=list)
    result: AnalyzeResult | None = None
    done: bool = False
    # We keep the task reference here, because asyncio only holds a weak
    # reference to it: without this the garbage collector can take the analysis
    # away halfway through.
    task: "asyncio.Task[None] | None" = None


def sse_frame(event: StreamEvent) -> str:
    """One event in SSE format.

    `model_dump_json` goes through SerializeAsAny from the contracts, so the
    fields of detector subclasses inside `detail` survive the dump to JSON.
    """
    return f"data: {event.model_dump_json()}\n\n"


class JobStore:
    """An in-memory job store. One instance per process, created in `routes`."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    # -- job lifecycle ------------------------------------------------------

    def create(self, url: str, candidate_set: str) -> str:
        job_id = uuid.uuid4().hex[:12]
        self._jobs[job_id] = Job(id=job_id, url=url, candidate_set=candidate_set)
        return job_id

    def exists(self, job_id: str) -> bool:
        return job_id in self._jobs

    def get(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError:
            raise UnknownJob(job_id) from None

    def set_audio_path(self, job_id: str, audio_path: str | None) -> None:
        """Stores where the input material lies. We do not check that the file exists."""
        self.get(job_id).audio_path = audio_path

    def start(self, job_id: str, producer: AsyncIterator[StreamEvent]) -> None:
        """Starts the event source as a background task.

        The task lives independently of whether anybody is listening to the
        stream and of whether a listener has disconnected. It requires a
        running event loop, so the endpoint that creates the analysis has to be
        an `async def`.
        """
        job = self.get(job_id)
        job.task = asyncio.create_task(self._pump(job_id, producer),
                                       name=f"origin-job-{job_id}")

    async def _pump(self, job_id: str, producer: AsyncIterator[StreamEvent]) -> None:
        """Copies the producer's events into the store and closes the job.

        A producer exception must not disappear silently: it turns into a
        `failed` event, so that screen E2 shows the failure instead of stopping
        halfway down the list without a word of explanation.
        """
        try:
            async for event in producer:
                self.emit(job_id, event)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - every failure must reach the UI
            self.emit(job_id, StreamEvent(stage="verdict", level=2, status="failed",
                                          detail={"error": f"{type(error).__name__}: {error}"}))
        finally:
            self.finish(job_id)

    def finish(self, job_id: str) -> None:
        self.get(job_id).done = True

    # -- events and result --------------------------------------------------

    def emit(self, job_id: str, event: StreamEvent) -> None:
        self.get(job_id).events.append(event)

    def events(self, job_id: str) -> list[StreamEvent]:
        return list(self.get(job_id).events)

    def set_result(self, job_id: str, result: AnalyzeResult) -> None:
        """Overwrites the result. Level 2 upgrades the verdict, it never takes it away."""
        self.get(job_id).result = result

    def get_result(self, job_id: str) -> AnalyzeResult:
        result = self.get(job_id).result
        if result is None:
            raise ResultNotReady(job_id)
        return result

    # -- stream -------------------------------------------------------------

    async def stream(self, job_id: str) -> AsyncIterator[str]:
        """SSE frames from the start of the run until the job finishes.

        A listener only reads. Every one gets the whole run from the first
        event, including someone who connected halfway through or refreshed the
        page, and none of them affects the pace of the analysis.
        """
        job = self.get(job_id)
        sent = 0
        while True:
            while sent < len(job.events):
                yield sse_frame(job.events[sent])
                sent += 1
            if job.done:
                return
            if job.task is None:
                # Nobody is computing this job and nobody will start. Waiting
                # forever would hold the connection open for no reason at all.
                return
            await asyncio.sleep(POLL_INTERVAL_S)
