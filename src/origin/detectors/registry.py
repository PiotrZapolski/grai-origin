"""Detector registry. Section 7.0.

The registry is **empty by design**. No detector module calls `register` for
itself: wiring up the full set is done by the single place that builds the
pipeline. If detectors registered themselves at import time, the registration
order would depend on the import order, and every new detector would have to
add itself to this file.
"""
from __future__ import annotations

from origin.detectors.base import Detector

__all__ = ["DETECTORS", "register", "get"]

DETECTORS: dict[str, Detector] = {}


def register(name: str, detector: Detector) -> Detector:
    """Wires a detector in under a name. Returns it so it can be used in one line."""
    DETECTORS[name] = detector
    return detector


def get(name: str) -> Detector:
    """A detector by name. KeyError with a readable list when nobody wired it in."""
    try:
        return DETECTORS[name]
    except KeyError:
        known = ", ".join(sorted(DETECTORS)) or "none"
        raise KeyError(f"detector '{name}' is not wired in; wired in: {known}") from None
