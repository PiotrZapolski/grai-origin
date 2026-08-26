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


# --- the address is checked before yt_dlp is given it ------------------------


def _resolving_to(monkeypatch, address: str):
    """DNS replaced by a fixed answer. No test in this file touches the network."""
    monkeypatch.setattr(
        download.socket, "getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", (address, 80))],
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9200/_cluster/health",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://[::1]/",
    ],
)
def test_an_address_on_our_own_network_is_refused(url):
    """The container sits on a shared Docker network next to the production services.

    Without this check the analysis field is a request forgery: yt_dlp fetches
    the metadata endpoint or an internal service from the inside, and the
    outcome comes back to the caller in the `ingest` failed event.
    """
    with pytest.raises(download.DownloadError) as error:
        download.check_target(url)
    assert error.value.reason == "blocked"


def test_a_name_resolving_to_loopback_is_refused(monkeypatch):
    """A literal IP is the easy case. The name pointing at the same place is the real one."""
    _resolving_to(monkeypatch, "127.0.0.1")
    with pytest.raises(download.DownloadError) as error:
        download.check_target("http://localhost/whatever")
    assert error.value.reason == "blocked"


def test_a_name_resolving_to_a_public_address_passes(monkeypatch):
    """The check must let real material through, or the analysis fetches nothing at all."""
    _resolving_to(monkeypatch, "93.184.216.34")
    download.check_target("https://example.com/watch?v=abc")


def test_one_internal_address_among_several_is_enough_to_refuse(monkeypatch):
    """A name resolving to one public and one private address is a way of reaching the second."""
    monkeypatch.setattr(
        download.socket, "getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 80)),
                         (0, 0, 0, "", ("10.1.2.3", 80))],
    )
    with pytest.raises(download.DownloadError) as error:
        download.check_target("https://sneaky.example/x")
    assert error.value.reason == "blocked"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/a.mp3",
                                 "gopher://example.com/"])
def test_a_scheme_other_than_http_is_refused(url):
    """Defence in depth: the API layer refuses these too, this is the last place before the request leaves."""
    with pytest.raises(download.DownloadError) as error:
        download.check_target(url)
    assert error.value.reason == "blocked"


def test_a_name_that_does_not_resolve_is_not_fetched(monkeypatch):
    """We cannot check what an address points at if we cannot resolve it, so we do not fetch it."""
    def refuse(*a, **k):
        raise OSError("Name or service not known")

    monkeypatch.setattr(download.socket, "getaddrinfo", refuse)
    with pytest.raises(download.DownloadError) as error:
        download.check_target("https://no-such-host.invalid/a")
    assert error.value.reason == "network"


def test_fetch_checks_the_address_before_it_imports_yt_dlp(monkeypatch):
    """The check has to sit in fetch, not only in its callers - it is the last gate."""
    def fail(*a, **k):
        raise AssertionError("the address reached the download layer")

    monkeypatch.setattr(download.socket, "getaddrinfo", fail)
    with pytest.raises(download.DownloadError) as error:
        download.fetch("http://169.254.169.254/latest/meta-data/", "/tmp")
    assert error.value.reason == "blocked"
