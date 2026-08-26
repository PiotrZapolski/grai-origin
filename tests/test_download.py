"""Classification of download errors. Tests moved here from test_ingest.py with the code.

Whether retrying makes sense depends on telling a taken-down video apart from
throttling, and with a corpus counted in thousands of entries that is the
difference between a complete and an incomplete sample (section 6).
"""
import pytest

from origin import download


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Video unavailable. This video has been removed by the uploader", "unavailable"),
        ("ERROR: Private video. Sign in if you've been granted access", "unavailable"),
        ("This video is no longer available due to a copyright claim by X", "unavailable"),
        ("Sign in to confirm your age. This video may be inappropriate", "unavailable"),
        ("HTTP Error 429: Too Many Requests", "throttled"),
        ("Sign in to confirm you're not a bot", "throttled"),
        ("The uploader has not made this video available in your country", "geoblocked"),
        # A geoblock on copyright grounds is not taken-down material: over a
        # different link it downloads fine, so retrying is allowed
        ("contains content from SME, who has blocked it in your country on "
         "copyright grounds", "geoblocked"),
        ("Unable to download webpage: <urlopen error timed out>", "network"),
        ("something else entirely", "unknown"),
    ],
)
def test_download_error_classification(message, expected):
    """Whether to retry depends on telling a taken-down video apart from throttling (section 6)."""
    assert download.reason_from_message(message) == expected


def test_throttling_beats_a_network_error_when_both_match():
    """The resolution order has to be explicit: throttling is more specific."""
    assert download.reason_from_message(
        "Unable to download webpage: HTTP Error 429"
    ) == "throttled"


def test_a_bare_number_in_the_identifier_is_not_throttling():
    """yt_dlp messages carry a video identifier, and that can be any string."""
    assert download.reason_from_message(
        "ERROR: [youtube] dQw429abc: Video unavailable"
    ) == "unavailable"


def test_the_http_code_beats_the_message_text():
    """DownloadError carries exc_info with the original exception, where the code is hard data."""
    import urllib.error

    class InconspicuousError(Exception):
        pass

    error = InconspicuousError("something else entirely")
    error.exc_info = (
        urllib.error.HTTPError,
        urllib.error.HTTPError("http://x", 429, "Too Many Requests", {}, None),
        None,
    )
    assert download.reason_from_exception(error) == "throttled"


def test_a_missing_ffmpeg_is_a_missing_tool_not_an_unknown_error():
    error = FileNotFoundError(2, "No such file or directory: 'ffmpeg'")
    assert download.reason_from_exception(error) == "missing_tool"
