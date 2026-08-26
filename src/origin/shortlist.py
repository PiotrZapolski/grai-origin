"""Pre-filtering down to a shortlist. Section 7.2 of the specification.

The full similarity matrix (harmonic.qmax) is O(n*m) and is computed only for
whatever passes through this sieve. The sieve itself is cheap: cosine
similarity of global descriptors (harmonic.global_descriptor), descending sort,
truncation to the limit.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from origin import config
from origin.contracts import Candidate
from origin.detectors import harmonic
from origin.ingest import Clip

__all__ = ["select", "score"]

# Default query descriptor used when there is neither a clip nor an injected
# vector - for example with synthetic candidates in tests, where there is no
# query audio at all. Constant and non-zero, so that the cosine has something
# to tell apart between candidates with different descriptors instead of giving
# everyone zero.
_DEFAULT_QUERY_DESCRIPTOR = np.ones(harmonic.DESCRIPTOR_DIM, dtype=np.float32)


def _query_descriptor(
    clip: Clip | None, query_descriptor: np.ndarray | None
) -> np.ndarray:
    """The query descriptor: injected > computed from the clip > constant default."""
    if query_descriptor is not None:
        return np.asarray(query_descriptor, dtype=np.float32)
    if clip is not None:
        return harmonic.global_descriptor(harmonic.chroma(clip))
    return _DEFAULT_QUERY_DESCRIPTOR


def _candidate_descriptor(candidate: Candidate) -> np.ndarray:
    """The candidate descriptor from the harmonic cache, if one exists.

    harmonic.representation does exactly that: it checks the cache under
    audio_path and only on a miss recomputes the chromagram from the real audio.
    """
    return harmonic.representation(candidate.audio_path).descriptor


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if norm <= 1e-12:
        return 0.0
    return float(np.dot(a, b)) / norm


def score(
    clip: Clip | None,
    candidate: Candidate,
    query_descriptor: np.ndarray | None = None,
) -> float:
    """Cosine similarity of the global descriptors of the query and the candidate.

    query_descriptor is an injected query descriptor: it allows skipping the
    computation from the clip when there is no clip (synthetic candidates in
    tests) or when select() has already computed it and does not want to do it
    a second time for every single candidate.
    """
    query = _query_descriptor(clip, query_descriptor)
    candidate_vector = _candidate_descriptor(candidate)
    return _cosine(query, candidate_vector)


def select(
    clip: Clip | None,
    candidates: Sequence[Candidate],
    limit: int = config.SHORTLIST_SIZE,
) -> list[Candidate]:
    """The shortlist: candidates sorted by score descending, truncated to the limit.

    An empty candidate set gives an empty list. A set smaller than the limit
    passes through whole - this truncates, it never pads.
    """
    if not candidates:
        return []
    query = _query_descriptor(clip, None)
    ranked = sorted(
        candidates,
        key=lambda candidate: score(clip, candidate, query_descriptor=query),
        reverse=True,
    )
    return ranked[: max(0, limit)]
