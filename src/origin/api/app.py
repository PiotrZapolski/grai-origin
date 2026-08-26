"""The FastAPI application. Run with: `uvicorn origin.api.app:app --reload`.

In development the frontend runs on a different port than the API, so without
CORS none of the four frontend tasks would see a single event. The list of
origins lives in `ORIGIN_CORS` (comma-separated), all of them by default - this
is a demo tool without authentication and without cookies.

At process startup we warm the level 0 cache (section 4): candidate
fingerprints and chromagrams are computed **once, before the first request**,
not on every one. Computed lazily they eat a dozen or so seconds exactly where
we promise five. Warming is switched off by `ORIGIN_PREWARM=0`, and its failure
never blocks startup: a candidate that could not be computed will get `failed`
during the run, and that is all.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from origin.api.routes import router, stub_mode

#: The candidate set warmed at startup. One, because the demo has one.
PREWARM_SET = os.environ.get("ORIGIN_PREWARM_SET", "demo_01")


def prewarm_enabled() -> bool:
    return os.environ.get("ORIGIN_PREWARM", "1").strip().lower() not in ("0", "false", "no")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Level 0 from section 4, called once per process."""
    if prewarm_enabled() and not stub_mode():
        import asyncio

        from origin import pipeline

        # In a worker thread, because decoding the candidates takes time and
        # uvicorn has no reason to block the event loop on it before accepting
        # the first connection. An exception must not stop the API from starting.
        try:
            errors = await asyncio.to_thread(pipeline.prewarm_set, PREWARM_SET)
        except Exception as error:  # noqa: BLE001 - starting the API matters more
            print(f"[origin] warming the cache failed: {error!r}")
        else:
            for detector, reasons in errors.items():
                if reasons:
                    print(f"[origin] {detector}: no representation for {sorted(reasons)}")
    yield


app = FastAPI(
    title="GRAI ORIGIN",
    version="0.1.0",
    description="Determining the provenance of a recording. Technical signal, not legal advice.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("ORIGIN_CORS", "*").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
