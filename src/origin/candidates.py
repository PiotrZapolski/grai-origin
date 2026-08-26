"""Candidate manifest. Section 5.3 of the specification.

The candidate set is a MANUALLY CURATED artifact, not something generated from
a directory listing. This module only loads it and checks it for defects that
would propagate to the chronology axis and to fusion.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from origin.contracts import Candidate, CandidateSet

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATES_DIR = REPO_ROOT / "data" / "candidates"


def set_path(set_id: str) -> Path:
    """Manifest path for a given set identifier."""
    return CANDIDATES_DIR / f"{set_id}.json"


def _resolve(path: str | Path) -> Path:
    """A relative path is taken first from the working directory and second
    from the repository root. Without this, tests would depend on where pytest
    was launched from, while there is only one manifest and it always lies in
    the same place."""
    p = Path(path)
    if p.is_absolute() or p.exists():
        return p
    candidate = REPO_ROOT / p
    return candidate if candidate.exists() else p


def load_set(set_id: str) -> CandidateSet:
    """Loads the manifest data/candidates/<set_id>.json.

    Does not check that the audio files exist: the manifest is created before
    downloading, and downloading may fail for some entries (section 5.7).
    """
    path = set_path(set_id)
    if not path.exists():
        raise FileNotFoundError(f"no manifest for set '{set_id}': {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return CandidateSet.model_validate(data)


def validate_set(path: str) -> list[str]:
    """Returns a list of human-readable manifest errors. An empty list means: the manifest is fine.

    Schema validation is not repeated here - the Candidate model in
    contracts.py does that, together with the ban on published_source ==
    "youtube" from section 5.5. Here we translate pydantic errors into text and
    add the rules the type system cannot express.
    """
    file_path = _resolve(path)
    if not file_path.exists():
        return [f"{file_path}: the manifest file does not exist"]
    try:
        data: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{file_path}: the file is not valid JSON ({exc})"]

    try:
        candidate_set = CandidateSet.model_validate(data)
    except ValidationError as exc:
        return [_describe_pydantic_error(error) for error in exc.errors()]

    return _extra_rules(candidate_set)


def _describe_pydantic_error(error: dict[str, Any]) -> str:
    location = ".".join(str(part) for part in error["loc"]) or "<root>"
    return f"{location}: {error['msg']}"


def _extra_rules(candidate_set: CandidateSet) -> list[str]:
    errors: list[str] = []
    if not candidate_set.candidates:
        errors.append("candidates: the set contains no candidates")

    errors += _uniqueness_errors(candidate_set.candidates, "id", lambda c: c.id)
    errors += _uniqueness_errors(
        candidate_set.candidates, "audio_path", lambda c: c.audio_path
    )

    for i, candidate in enumerate(candidate_set.candidates):
        errors += [f"candidates.{i}.{error}" for error in _candidate_errors(candidate)]
    return errors


def _uniqueness_errors(candidates, field, key) -> list[str]:
    seen: set[str] = set()
    repeated: list[str] = []
    for candidate in candidates:
        value = key(candidate)
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return [f"candidates: {field} '{v}' occurs more than once" for v in repeated]


def _candidate_errors(candidate: Candidate) -> list[str]:
    errors: list[str] = []

    # Section 5.5: a date and its source travel together. A date without a
    # source is a date of unknown provenance, which is exactly the defect the
    # chronology axis must not have. A source without a date means nothing.
    if candidate.published is not None and candidate.published_source is None:
        errors.append(
            "published_source: date given without a source; section 5.5 requires "
            "'manual' or 'metadata_registry'"
        )
    if candidate.published is None and candidate.published_source is not None:
        errors.append(
            f"published_source: source '{candidate.published_source}' without a date"
        )

    # The chronology rule from 9.3 compares these values, so they must be ISO dates.
    if candidate.published is not None:
        try:
            date.fromisoformat(candidate.published)
        except ValueError:
            errors.append(
                f"published: '{candidate.published}' is not an ISO date "
                f"in YYYY-MM-DD format"
            )

    if not candidate.audio_path.startswith("data/audio/"):
        errors.append(
            f"audio_path: '{candidate.audio_path}' must lie under data/audio/"
        )

    # An instrumental track has no lyrics. A lyrics path on an instrumental
    # means a curation mistake and would let detector D in where it should
    # return not_applicable (section 7.3).
    if candidate.instrumental and candidate.lyrics_path is not None:
        errors.append("lyrics_path: an instrumental candidate cannot have lyrics")

    return errors
