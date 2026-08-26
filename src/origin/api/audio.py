"""Serving audio files and the URLs pointing at them. Sections 12 and 13.2 of the specification.

Screen E4 switches playback between the query and the candidate at a
synchronised point, and that is the most important element of the whole
interface: the brief demands the ability to verify, and for audio the only real
verification is the ear. A browser will seek to a requested second only when
the server answers range requests, which is why handling the `Range` header is
not an ornament here but a precondition for the whole feature.

The second reason this module exists is defensive. The application stands on a
public address, and an endpoint serving files from disk by an identifier taken
from a request is the classic route to leaking any file from the server. That
is why all disk access goes through `resolve`, which:

* does not build a path from what arrived in the request - a candidate
  identifier is resolved by the manifest alone, and what reaches here is
  already a manifest path,
* reduces the path to an absolute form with symlinks expanded,
* rejects anything that afterwards does not lie inside the audio directory.

The audio directory is pointed at by `ORIGIN_AUDIO_ROOT`, by default
`data/audio/` in the repository root. The variable is read on every call, not
at import time, because tests switch it at runtime.
"""
from __future__ import annotations

import mimetypes
import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

from fastapi.responses import Response, StreamingResponse

from origin.contracts import AnalyzeResult

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIRECTORY = REPO_ROOT / "data" / "audio"

# The prefix the manifest writes its paths with (section 5.3 and the validation
# in candidates.py). A relative path is anchored to the configured audio
# directory, so that moving the directory does not require rewriting the
# manifest.
MANIFEST_PREFIX = ("data", "audio")

BYTE_BLOCK = 64 * 1024


class OutsideAudioRoot(ValueError):
    """The path points outside the audio directory. We never serve it."""


class UnsatisfiableRange(ValueError):
    """The range is syntactically valid but does not fit in the file. That is a 416."""


def audio_root() -> Path:
    """The only directory a file may be served from."""
    configured = os.environ.get("ORIGIN_AUDIO_ROOT", "").strip()
    return Path(configured).resolve() if configured else DEFAULT_DIRECTORY.resolve()


def resolve(audio_path: str | Path) -> Path:
    """A manifest path into a path on disk, or `OutsideAudioRoot`.

    A relative path starting with `data/audio/` is counted from the audio
    directory, any other one from the repository root. The result is checked
    only after `resolve()`, so a `..` or a symlink leading outside the
    directory ends in a refusal regardless of how it was written.
    """
    p = Path(audio_path)
    root = audio_root()
    if p.is_absolute():
        candidate = p
    elif p.parts[:2] == MANIFEST_PREFIX:
        candidate = root.joinpath(*p.parts[2:])
    else:
        candidate = REPO_ROOT / p

    candidate = candidate.resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise OutsideAudioRoot(str(audio_path))
    return candidate


def exists(audio_path: str | Path | None) -> bool:
    """Whether this can be played at all. A path outside the directory is the same as a missing file."""
    if audio_path is None:
        return False
    try:
        return resolve(audio_path).is_file()
    except (OutsideAudioRoot, OSError):
        return False


# --------------------------------------------------------------------------
# Range requests
# --------------------------------------------------------------------------

def range_from_header(header: str | None, size: int) -> tuple[int, int] | None:
    """The `Range` header into an inclusive (start, end) pair.

    `None` means: there is no range, or it cannot be read. RFC 9110 then
    requires ignoring the header and serving the whole file rather than
    reporting an error. A range that is syntactically valid but reaches outside
    the file is already a client error and ends in `UnsatisfiableRange`, that
    is a 416 response.

    From a list of ranges we take the first: a multipart response is needed by
    no player, and the client has to be able to accept a narrower range than it
    asked for.
    """
    if not header:
        return None
    unit, separator, rest = header.strip().partition("=")
    if not separator or unit.strip().lower() != "bytes":
        return None

    first, dash, last = rest.split(",")[0].strip().partition("-")
    if not dash:
        return None
    first, last = first.strip(), last.strip()

    if not first:
        # The suffix form: the last N bytes of the file.
        if not last.isdigit():
            return None
        length = int(last)
        if length == 0:
            raise UnsatisfiableRange(header)
        return max(0, size - length), size - 1

    if not first.isdigit() or (last and not last.isdigit()):
        return None
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start > end or start >= size:
        raise UnsatisfiableRange(header)
    return start, end


def _read(path: Path, start: int, length: int) -> Iterator[bytes]:
    """A byte stream from one slice of a file. The recording never enters RAM whole."""
    with path.open("rb") as file:
        file.seek(start)
        remaining = length
        while remaining > 0:
            chunk = file.read(min(BYTE_BLOCK, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk


def audio_response(path: Path, range_header: str | None) -> Response:
    """The audio file, whole or as a slice, according to the `Range` header."""
    size = path.stat().st_size
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {"Accept-Ranges": "bytes"}

    try:
        byte_range = range_from_header(range_header, size)
    except UnsatisfiableRange:
        return Response(
            status_code=416,
            headers={**headers, "Content-Range": f"bytes */{size}"},
        )

    if byte_range is None:
        return StreamingResponse(
            _read(path, 0, size),
            media_type=content_type,
            headers={**headers, "Content-Length": str(size)},
        )

    start, end = byte_range
    length = end - start + 1
    return StreamingResponse(
        _read(path, start, length),
        status_code=206,
        media_type=content_type,
        headers={
            **headers,
            "Content-Length": str(length),
            "Content-Range": f"bytes {start}-{end}/{size}",
        },
    )


# --------------------------------------------------------------------------
# URLs in the analysis result
# --------------------------------------------------------------------------

def query_url(job_id: str) -> str:
    return f"/api/jobs/{quote(job_id, safe='')}/audio"


def candidate_url(set_id: str, candidate_id: str) -> str:
    return (f"/api/audio/candidate/{quote(candidate_id, safe='')}"
            f"?set={quote(set_id, safe='')}")


def fill_in_urls(
    result: AnalyzeResult,
    job_id: str,
    set_id: str,
    query_path: str | None,
) -> AnalyzeResult:
    """Attaches to the result the URLs the frontend will play the query and the candidates from.

    A URL appears **only when the file really lies on disk**. A URL leading to
    a 404 would stall the player on a network error instead of saying outright
    that the material is missing, and we do not generate substitute audio: in
    an evidentiary tool a stand-in is worse than nothing (section 13.2 at E5).

    The result is copied, because the store holds a single model shared by all
    reads while the URLs depend on the job identifier.
    """
    copy = result.model_copy(deep=True)
    copy.query.waveform_url = (
        query_url(job_id) if exists(query_path) else None
    )
    for entry in copy.ranking:
        candidate = entry.candidate
        candidate.audio_url = (
            candidate_url(set_id, candidate.id)
            if exists(candidate.audio_path)
            else None
        )
    return copy

