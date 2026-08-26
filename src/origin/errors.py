"""Input-path exceptions. Section 6 of the specification.

The hierarchy lives in a separate module because both the download layer and
ingest have to see it, and downloading is a step of ingest, not the other way
round. Keeping the base class in ingest would force the download module to
import its own caller.
"""
from __future__ import annotations

__all__ = ["IngestError", "DownloadError"]


class IngestError(RuntimeError):
    """Input error: the material did not download, did not decode, or is empty."""


class DownloadError(IngestError):
    """The download failed. The `reason` field says whether retrying makes sense.

    Section 6: telling "video taken down" apart from "throttling" decides
    whether to retry, and with a corpus counted in thousands of entries that is
    the difference between a complete and an incomplete set. Dictionary of
    reasons:

    unavailable    material taken down or behind a login - do not retry
    geoblocked     territorial block - retry from another link, the material exists
    throttled      throttling or an anti-bot gate - retry later
    network        transport layer - retry immediately
    postprocessing the ffmpeg cut blew up - retry without download_ranges
    missing_tool   ffmpeg or a library is missing - fix the environment, do not retry
    oversized      more than the limit was downloaded - do not retry without changing options
    unknown        not recognised
    """

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason
