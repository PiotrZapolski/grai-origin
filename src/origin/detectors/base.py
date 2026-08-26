"""The shared detector envelope. Section 7.0 of the specification.

A detector is a function taking a `Clip` and a list of candidates and returning
an envelope. Status exists at two levels - the envelope and the individual
result - and both are mandatory. The helpers below guard one rule that is easy
to break by accident: a result with a status other than `ok` must not carry any
measurement value, because `not_applicable` and `gated` are not zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence, runtime_checkable

from origin.contracts import (
    Candidate,
    DetectorEnvelope,
    DetectorResult,
    DetectorStatus,
)
from origin.ingest import Clip

__all__ = [
    "Detector",
    "Context",
    "envelope",
    "empty_envelope",
    "run_guarded",
]


@dataclass(frozen=True)
class Context:
    """Envelopes of detectors computed EARLIER within the same query.

    Section 7.1 makes running the grid of 143 transformations conditional on
    whether the harmonic detector returned a high similarity. Without a channel
    for such a signal the condition has no way to exist in the code, and it
    ends with the grid either always running or never running. The context is
    optional: a detector without it computes normally, just without the rules
    that depend on its neighbours.
    """

    envelopes: dict[str, DetectorEnvelope] = field(default_factory=dict)

    def result(self, detector: str, candidate_id: str) -> DetectorResult | None:
        """The given detector's result for the given candidate, or None.

        None means "there is no measurement" and nothing more. The caller has
        to check the result's status itself, because `gated` and
        `not_applicable` are not zero (section 7.0).
        """
        envelope_for_detector = self.envelopes.get(detector)
        if envelope_for_detector is None or envelope_for_detector.status != "ok":
            return None
        for result in envelope_for_detector.results:
            if result.candidate_id == candidate_id:
                return result
        return None


@runtime_checkable
class Detector(Protocol):
    """The detector protocol. `level` is the level from section 4: 1 always runs.

    `context` is optional and deliberately last: level 1 detectors computed in
    parallel get None, while those whose rules depend on their neighbours
    (section 7.1) get the already computed envelopes.
    """

    name: str
    level: int

    def run(
        self,
        clip: Clip,
        candidates: Sequence[Candidate],
        context: "Context | None" = None,
    ) -> DetectorEnvelope: ...


def envelope(name: str, results: Sequence[DetectorResult]) -> DetectorEnvelope:
    """The envelope of a successful run. Individual result statuses stay their own."""
    return DetectorEnvelope(detector=name, status="ok", results=list(results))


def empty_envelope(
    name: str, status: DetectorStatus, reason: str
) -> DetectorEnvelope:
    """The envelope of a run that did not happen: it carries not a single number.

    Used for `failed`, `gated` and `not_applicable` at the level of the whole
    query. The result list stays empty on purpose - the contract would reject a
    result carrying a measurement value under such an envelope status anyway.
    """
    return DetectorEnvelope(detector=name, status=status, reason=reason)


def run_guarded(
    name: str, run: Callable[[], Sequence[DetectorResult]]
) -> DetectorEnvelope:
    """Runs a detector pass and turns an exception into a `failed` envelope.

    Section 9.1: fusion must work correctly when any detector returns an
    envelope other than `ok`. A failure in one detector must not bring the
    whole analysis down, so the exception ends here rather than in the pipeline.
    """
    try:
        return envelope(name, run())
    except Exception as error:  # noqa: BLE001 - the reason lands in the envelope, not in a log
        return empty_envelope(name, "failed", f"{type(error).__name__}: {error}")
