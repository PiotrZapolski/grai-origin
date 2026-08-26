"""Step 1 of section 6: fetching the material and recognising why it failed.

Classifying the error matters here as much as the download itself. With a
corpus counted in thousands of entries, telling "video taken down" apart from
"throttling" decides whether to retry, and therefore whether the sample comes
out complete. The dictionary of reasons is documented in `DownloadError`.

This is the ONLY implementation of that classification in the repository: it is
used both by the live path (`origin.ingest`) and by corpus fetching
(`scripts/fetch_audio`). Two copies would mean that a pattern added after a
failed run fixes one of them while the other still reports "not recognised".
"""
from __future__ import annotations

import errno
import os
import re
from pathlib import Path

from origin import config
from origin.errors import DownloadError

__all__ = [
    "is_url",
    "reason_from_message",
    "reason_from_exception",
    "fetch",
]


# The order matters and is tested: the more specific reason wins. Throttling
# beats a network error, because "unable to download" also accompanies a 429.
_ERROR_PATTERNS: tuple[tuple[str, str], ...] = (
    # Territorial block. This is NOT material taken down: over a different link
    # it downloads fine, so retrying from another network makes sense. That is
    # why the word "copyright" alone must not map to unavailable - the message
    # "blocked it in your country on copyright grounds" is exactly a geoblock.
    (r"in your country|in your location|geo.?restrict|geo.?block|"
     r"not available from your location", "geoblocked"),
    # Throttling or an anti-bot gate - the material exists, retry later.
    # "http error 429" with context, not a bare 429: yt_dlp messages carry a
    # video identifier that can be an arbitrary string. The apostrophe in
    # "you're" is typographic on YouTube (U+2019), hence `.?` instead of '.
    (r"http error 429|too many requests|rate.?limit|throttl|"
     r"sign in to confirm you.?re not a bot", "throttled"),
    # Material taken down, private, behind a login, behind an age gate or
    # behind a paywall - retrying the same request will achieve nothing. The
    # last four variants came from corpus fetching, where they had their own
    # classification.
    (r"video unavailable|has been removed|no longer available|private video|"
     r"is private|members-only|this video is not available|account associated "
     r"with this video has been terminated|confirm your age|age.?restricted|"
     r"sign in to view|premieres in|join this channel|"
     r"requested format is not available", "unavailable"),
    # Transport layer - retry immediately.
    (r"unable to download|timed out|timeout|connection|temporary failure|"
     r"network|http error 5\d\d|remote end closed", "network"),
)


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def reason_from_message(message: str) -> str:
    """Turns a yt_dlp message into a retry reason. The dictionary is in DownloadError."""
    text = message.lower()
    for pattern, reason in _ERROR_PATTERNS:
        if re.search(pattern, text):
            return reason
    return "unknown"


def _http_code(error: BaseException) -> int | None:
    """Extracts the HTTP code from the exception or from the exc_info carried by DownloadError.

    yt_dlp wraps the original exception in `exc_info`, so a 429 code is hard
    data there instead of something to guess from the message text.
    """
    candidates: list[BaseException] = [error]
    exc_info = getattr(error, "exc_info", None)
    if isinstance(exc_info, tuple) and len(exc_info) >= 2:
        if isinstance(exc_info[1], BaseException):
            candidates.append(exc_info[1])
    for attribute in ("__cause__", "__context__"):
        nested = getattr(error, attribute, None)
        if isinstance(nested, BaseException):
            candidates.append(nested)
    for candidate in candidates:
        # urllib has .code, the yt_dlp networking layer has .status
        code = getattr(candidate, "code", None)
        if not isinstance(code, int):
            code = getattr(candidate, "status", None)
        if isinstance(code, int):
            return code
    return None


def reason_from_exception(error: BaseException) -> str:
    """The retry reason for any exception from the download path.

    Not just DownloadError: `extract_info` also throws ExtractorError,
    GeoRestrictedError and PostProcessingError (very likely with
    force_keyframes_at_cuts, because the cut is done by ffmpeg), and a bare
    OSError when ffmpeg is missing. The retry layer must get a reason from each
    of them, otherwise the library gives nothing beyond the CLI exit code.
    """
    try:
        from yt_dlp import utils as yt_utils
    except ImportError:
        yt_utils = None

    if yt_utils is not None:
        if isinstance(error, getattr(yt_utils, "GeoRestrictedError", ())):
            return "geoblocked"
        if isinstance(error, getattr(yt_utils, "PostProcessingError", ())):
            return "postprocessing"
    if isinstance(error, ImportError):
        return "missing_tool"
    if isinstance(error, OSError) and error.errno == errno.ENOENT:
        return "missing_tool"

    code = _http_code(error)
    if code == 429:
        return "throttled"
    if code in (404, 410):
        return "unavailable"
    if isinstance(code, int) and 500 <= code < 600:
        return "network"
    return reason_from_message(str(error))


def _check_size(path: str) -> str:
    """Hard limit on the downloaded file, see config.MAX_DOWNLOAD_BYTES.

    When download_ranges cannot be applied to a format, yt_dlp only warns and
    downloads everything. Without this threshold a three-hour recording would
    quietly enter librosa and eat several gigabytes of RAM on a shared machine.
    """
    size = os.path.getsize(path)
    if size > config.MAX_DOWNLOAD_BYTES:
        raise DownloadError(
            f"the downloaded file is {size} B, the limit is {config.MAX_DOWNLOAD_BYTES} B; "
            f"the limit to {config.MAX_DURATION_S} s probably did not take effect",
            "oversized",
        )
    return path


def fetch(url: str, directory: str) -> str:
    """Downloads audio with the yt_dlp library. Not through the CLI - see section 6 step 1.

    The library raises exceptions with a readable message and with exc_info
    instead of an exit code to parse, so taken-down material can be told apart
    from throttling.
    """
    try:
        import yt_dlp
    except ImportError as error:
        raise DownloadError(f"the yt_dlp library is missing: {error}", "missing_tool") from error

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(directory) / "%(id)s.%(ext)s"),
        "quiet": True,
        # Warnings stay on deliberately: a warning is exactly how yt_dlp
        # signals that download_ranges cannot be applied to a format.
        "no_warnings": False,
        "noprogress": True,
        "noplaylist": True,
        # Section 6: we do not download more than the limit we are about to trim to anyway.
        "download_ranges": yt_dlp.utils.download_range_func(
            None, [(0, config.MAX_DURATION_S)]
        ),
        "force_keyframes_at_cuts": True,
        "max_filesize": config.MAX_DOWNLOAD_BYTES,
    }
    # ffmpeg is not installed system-wide; scripts/rt exports the path to the
    # static binary from imageio-ffmpeg.
    ffmpeg = os.environ.get("ORIGIN_FFMPEG")
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise DownloadError(f"no metadata for {url}", "unknown")
            if "entries" in info:
                entries = [e for e in info["entries"] if e]
                if not entries:
                    raise DownloadError(f"empty playlist {url}", "unavailable")
                info = entries[0]
            downloaded = info.get("requested_downloads") or []
            if downloaded and downloaded[0].get("filepath"):
                return _check_size(str(downloaded[0]["filepath"]))
            return _check_size(str(ydl.prepare_filename(info)))
    except DownloadError:
        raise
    except (yt_dlp.utils.YoutubeDLError, OSError) as error:
        raise DownloadError(str(error), reason_from_exception(error)) from error
