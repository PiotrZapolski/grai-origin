from scripts import fetch_audio as fa


def test_it_stops_after_reaching_the_target_not_after_exhausting_the_list(monkeypatch):
    """Section 5.7: this is the whole difference between a complete and an incomplete sample."""
    calls = []

    def fake(item, directory):
        calls.append(item["id"])
        return f"{directory}/{item['id']}.wav"

    monkeypatch.setattr(fa, "_fetch_one", fake)
    items = [{"id": f"p{i}", "url": "u"} for i in range(100)]
    report = fa.fetch_many(items, target=10, directory="/tmp")
    assert len(report.successful) == 10
    assert len(calls) == 10, "we must not fetch more than needed"


def test_the_overshoot_covers_dead_links(monkeypatch):
    def fake(item, directory):
        if int(item["id"][1:]) % 3 == 0:
            raise RuntimeError("video unavailable")
        return f"{directory}/{item['id']}.wav"

    monkeypatch.setattr(fa, "_fetch_one", fake)
    items = [{"id": f"p{i}", "url": "u"} for i in range(100)]
    report = fa.fetch_many(items, target=20, directory="/tmp")
    assert len(report.successful) == 20


def test_the_report_records_the_reason_for_every_failure(monkeypatch):
    def fake(item, directory):
        raise RuntimeError("video unavailable")

    monkeypatch.setattr(fa, "_fetch_one", fake)
    items = [{"id": f"p{i}", "url": "u"} for i in range(5)]
    report = fa.fetch_many(items, target=3, directory="/tmp")
    assert report.successful == []
    assert len(report.failed) == 5
    assert all("unavailable" in reason for _, reason in report.failed)


def test_a_list_shorter_than_the_target_ends_without_an_exception(monkeypatch):
    monkeypatch.setattr(fa, "_fetch_one", lambda i, d: f"{d}/{i['id']}.wav")
    report = fa.fetch_many([{"id": "p0", "url": "u"}], target=10, directory="/tmp")
    assert len(report.successful) == 1
    assert report.attempted == 1


def test_the_default_overshoot_is_25_percent():
    assert fa.OVERSHOOT == 1.25


def test_it_recognises_throttling_despite_the_typographic_apostrophe():
    """The real YouTube message has a U+2019 apostrophe, not an ASCII one.

    A throughput test on twenty addresses from the catalogue came back with
    nineteen such errors classified as unrecognised. Throttling has to be
    visible in the report, because of all the reasons it is the only one where
    retrying makes sense.
    """
    reason = (
        "DownloadError: jrClQbBWCJk: Sign in to confirm you’re not a bot. "
        "Use --cookies-from-browser or --cookies for the authentication."
    )
    assert fa.reason_from_message(reason) == "throttled"


def test_it_tells_a_dead_link_apart_from_throttling():
    """There is one dictionary of reasons, shared with origin.download (section 6)."""
    assert fa.reason_from_message(
        "DownloadError: 5FB2MV9JN24: Video unavailable"
    ) == "unavailable"
    assert fa.reason_from_message(
        "DownloadError: HTTP Error 429: Too Many Requests"
    ) == "throttled"


def test_it_recognises_a_failure_of_the_ffmpeg_downloader():
    """The static ffmpeg from imageio-ffmpeg crashes on any network input.

    Measured on the target machine: it processes local files correctly, but with
    an http or https input it ends in SIGSEGV (code -11). The download_ranges
    path for non-fragmented formats runs into that, so it has to be recognised
    and handled by a fallback rather than counted as a dead link.
    """
    assert fa._ffmpeg_downloader_failure("DownloadError: ffmpeg exited with code -11")
    assert not fa._ffmpeg_downloader_failure("DownloadError: Video unavailable")


def test_the_fallback_options_do_not_slice_with_ffmpeg_over_the_network():
    primary = fa._download_options("abc", "/tmp", 60, slice_locally=False)
    fallback = fa._download_options("abc", "/tmp", 60, slice_locally=True)

    assert "download_ranges" in primary, "by default we slice while downloading"
    assert "download_ranges" not in fallback, "the fallback path does not touch the network with ffmpeg"
    assert fallback["postprocessor_args"]["extractaudio"] == ["-t", "60"]
    assert fallback["outtmpl"] == "/tmp/abc.%(ext)s"
