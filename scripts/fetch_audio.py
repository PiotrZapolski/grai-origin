#!/usr/bin/env python3
"""Fetching audio with an overshoot for dead links. Section 5.7 of the specification.

The heart of it: fetching stops once the TARGET NUMBER OF SUCCESSFUL downloads
has been collected, not once the list is exhausted. Between the October and
July dumps of the SecondHandSongs catalogue, 12,937 entries disappeared, and on
top of that come videos taken down, private and region-blocked, which the July
dump knows nothing about. A download planned item by item arrives incomplete
and that only shows up when counting, at the worst possible moment.

Command line usage:
    python scripts/fetch_audio.py --set demo_01
    python scripts/fetch_audio.py --urls-file list.txt --target 20 --slice 60
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field

from origin.download import reason_from_message

# An overshoot of 25% relative to the target. Section 5.7: this is an estimate,
# not a measurement - if the share of dead links turns out to be higher, it is
# raised here and only here.
OVERSHOOT = 1.25

# Default slice length in seconds. Section 6 trims material to 180 s, but for
# the IDF corpus and for throughput tests a minute is enough.
SLICE_S = 60

# A hard time limit for a single entry. Without it, one hung connection blocks
# a thread until the end of the run.
TIME_LIMIT_S = 240

AUDIO_DIR = "data/audio"
ERROR_LOG = "data/cache/fetch_errors.jsonl"
CANDIDATES_DIR = "data/candidates"

@dataclass
class FetchReport:
    """The result of a run. The failure reason is per entry, not aggregate."""

    successful: list[str]
    failed: list[tuple[str, str]]
    attempted: int
    seconds: float = 0.0
    throttled: list[str] = field(default_factory=list)
    timings: list[dict] = field(default_factory=list)


def default_concurrency() -> int:
    """The number of parallel downloads.

    We take the allocated cores, not all the visible ones: the target machine
    has 32 logical CPUs according to nproc --all, while the GRAI ORIGIN quota
    is four cores (taskset -c 0-3 in scripts/rt). os.cpu_count() would give
    eight times too many here.
    """
    quota = os.environ.get("ORIGIN_CPU_QUOTA")
    if quota and quota.strip().isdigit():
        return max(1, int(quota))
    if hasattr(os, "sched_getaffinity"):
        return max(1, len(os.sched_getaffinity(0)))
    return 1


def with_overshoot(target: int, overshoot: float = OVERSHOOT) -> int:
    """How many entries to draw in order to collect the target number of successful downloads."""
    return int(math.ceil(max(0, target) * overshoot))


def _identifier(item: dict) -> str:
    for key in ("id", "candidate_id", "video_id", "sha256"):
        value = item.get(key)
        if value:
            return str(value)
    return str(item.get("url", "?"))


def _url(item: dict) -> str:
    for key in ("url", "youtube_url", "link", "source_url"):
        value = item.get(key)
        if value:
            return str(value)
    raise RuntimeError("entry without a URL")


def _yt_dlp():
    """Lazy import: unit tests replace _fetch_one and do not need the package."""
    import yt_dlp  # noqa: PLC0415 - see the docstring

    return yt_dlp


def _reason_from_exception(error: BaseException) -> str:
    """The exception type plus the message.

    The type stays in the reason on purpose: a DownloadError about a dead link
    and a DownloadError about throttling that differ only in the message text
    have to be distinguishable, because that is what decides whether retrying
    makes any sense at all.
    """
    text = str(error).strip()
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)          # ANSI colours from yt-dlp
    text = re.sub(r"^ERROR:\s*", "", text)
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    text = " ".join(text.split())
    return f"{type(error).__name__}: {text}"[:300] if text else type(error).__name__


def _ffmpeg_downloader_failure(reason: str) -> bool:
    """Whether the error comes from the external ffmpeg downloader rather than from the material itself."""
    return "ffmpeg exited with code" in (reason or "").lower()


def _download_options(ident: str, directory: str, slice_s: int, slice_locally: bool) -> dict:
    """yt_dlp options for one entry.

    By default the slice is taken during the download (download_ranges). For
    fragmented formats, that is the whole of YouTube, that is done by yt_dlp's
    native downloader. For an ordinary file over http yt_dlp reaches for the
    ffmpeg downloader, and on the target machine that one crashes on any
    network input - then the local-slicing variant kicks in: the whole stream
    natively, the cut only in postprocessing.
    """
    options = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(directory, f"{ident}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "ignoreerrors": False,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 20,
        "concurrent_fragment_downloads": 1,  # parallelism is already handled per entry
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
    }
    if slice_locally:
        # -t works on a file already on disk, so it bypasses the troublesome network path.
        options["postprocessor_args"] = {"extractaudio": ["-t", str(slice_s)]}
    else:
        yt_dlp = _yt_dlp()
        options["download_ranges"] = yt_dlp.utils.download_range_func(None, [(0, slice_s)])
        options["force_keyframes_at_cuts"] = True
    # scripts/rt supplies the static ffmpeg from imageio-ffmpeg and exports ORIGIN_FFMPEG.
    ffmpeg = os.environ.get("ORIGIN_FFMPEG")
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg
    return options


def _fetch_one(item: dict, directory: str) -> str:
    """Fetches one entry with the yt_dlp library and returns the path to the wav file.

    Raises an exception with a readable reason when it fails - fetch_many
    stores that reason in the report and in the error log. yt_dlp exceptions
    carry a type, so the reason tells a dead link apart from throttling without
    parsing exit codes.
    """
    ident = _identifier(item)
    address = _url(item)
    slice_s = int(item.get("slice_s") or SLICE_S)
    target_file = os.path.join(directory, f"{ident}.wav")

    # Resuming: a finished file from a previous run is not downloaded again.
    if os.path.exists(target_file) and os.path.getsize(target_file) > 0:
        return target_file

    os.makedirs(directory, exist_ok=True)
    yt_dlp = _yt_dlp()
    started = time.monotonic()

    def watchdog(_state: dict) -> None:
        # yt_dlp has no time limit on the whole download, and one hung
        # connection can occupy a thread until the end of the run. The progress
        # hook is the only place from which an ongoing download can be aborted.
        if time.monotonic() - started > TIME_LIMIT_S:
            raise RuntimeError(f"timeout after {TIME_LIMIT_S} s")

    def download(slice_locally: bool) -> None:
        options = _download_options(ident, directory, slice_s, slice_locally)
        options["progress_hooks"] = [watchdog]
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([address])

    try:
        download(slice_locally=False)
    except Exception as error:  # noqa: BLE001 - the reason goes to the report, not to stderr
        reason = _reason_from_exception(error)
        if not _ffmpeg_downloader_failure(reason):
            raise RuntimeError(reason) from error
        try:
            download(slice_locally=True)
        except Exception as second:  # noqa: BLE001
            raise RuntimeError(_reason_from_exception(second)) from second

    if not (os.path.exists(target_file) and os.path.getsize(target_file) > 0):
        raise RuntimeError("PostprocessingError: yt_dlp left no wav file behind")
    return target_file


def _task(item: dict, directory: str) -> str:
    """Calls _fetch_one through the global name, so that tests can replace it."""
    return _fetch_one(item, directory)


def _append_log(path: str, entry: dict) -> None:
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        # The error log must not bring the download down. The reason is in the
        # report anyway.
        pass


def fetch_many(
    items: list[dict],
    target: int,
    directory: str,
    concurrency: int | None = None,
    error_log: str | None = ERROR_LOG,
) -> FetchReport:
    """Fetches until the target number of successful downloads is collected, or the list runs out.

    It never starts more tasks than needed: at any moment the number of
    successes plus the number of downloads in flight does not exceed the
    target. That is why with nothing but successes the number of calls equals
    the target exactly, rather than the length of the list.
    """
    start = time.monotonic()
    successful: list[str] = []
    failed: list[tuple[str, str]] = []
    throttled: list[str] = []
    timings: list[dict] = []

    if target <= 0 or not items:
        return FetchReport([], [], 0, 0.0, [], [])

    if directory:
        os.makedirs(directory, exist_ok=True)
    workers = max(1, int(concurrency or default_concurrency()))
    queue = iter(list(items))
    exhausted = False

    with ThreadPoolExecutor(max_workers=workers) as pool:
        in_flight: dict = {}

        def top_up() -> None:
            nonlocal exhausted
            while (
                not exhausted
                and len(in_flight) < workers
                and len(successful) + len(in_flight) < target
            ):
                try:
                    item = next(queue)
                except StopIteration:
                    exhausted = True
                    return
                in_flight[pool.submit(_timed, item, directory)] = item

        top_up()
        while in_flight:
            done, _ = wait(list(in_flight), return_when=FIRST_COMPLETED)
            for future in done:
                item = in_flight.pop(future)
                ident = _identifier(item)
                try:
                    path, elapsed = future.result()
                except Exception as error:  # noqa: BLE001 - the reason goes to the report
                    reason = str(error) or error.__class__.__name__
                    elapsed = float(getattr(error, "elapsed", 0.0))
                    category = reason_from_message(reason)
                    failed.append((ident, reason))
                    if category == "throttled":
                        throttled.append(ident)
                    timings.append(
                        {
                            "id": ident,
                            "ok": False,
                            "seconds": round(elapsed, 2),
                            "reason": reason,
                            "category": category,
                        }
                    )
                    if error_log:
                        _append_log(
                            error_log,
                            {
                                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "id": ident,
                                "url": item.get("url") or item.get("youtube_url"),
                                "reason": reason,
                                "category": category,
                            },
                        )
                else:
                    successful.append(path)
                    timings.append(
                        {"id": ident, "ok": True, "seconds": round(elapsed, 2), "reason": None}
                    )
            top_up()

    return FetchReport(
        successful=successful,
        failed=failed,
        attempted=len(successful) + len(failed),
        seconds=round(time.monotonic() - start, 2),
        throttled=throttled,
        timings=timings,
    )


def _timed(item: dict, directory: str) -> tuple[str, float]:
    """Times a single download - needed for the extrapolation from section 5.7."""
    started = time.monotonic()
    try:
        path = _task(item, directory)
    except Exception as error:  # noqa: BLE001 - we attach the time to the exception and re-raise
        try:
            error.elapsed = time.monotonic() - started  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        raise
    return path, time.monotonic() - started


# --- inputs from disk ------------------------------------------------------


def load_set(name: str, directory: str = CANDIDATES_DIR) -> list[dict]:
    """The candidate manifest. The file shape is created in Task 4, so we read tolerantly."""
    path = name if os.path.exists(name) else os.path.join(directory, f"{name}.json")
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, dict):
        for key in ("candidates", "items", "entries"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise RuntimeError(f"{path}: could not find a list of candidates")
    return [p if isinstance(p, dict) else {"url": str(p)} for p in data]


def load_urls(path: str) -> list[dict]:
    """A list of addresses, one per line. The identifier comes from the address, so file names stay stable."""
    items = []
    with open(path, encoding="utf-8") as file:
        for line in file:
            address = line.strip()
            if not address or address.startswith("#"):
                continue
            match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{6,})", address)
            ident = match.group(1) if match else re.sub(r"\W+", "_", address)[-32:]
            items.append({"id": ident, "url": address})
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetching audio with an overshoot (section 5.7)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--set", dest="candidate_set", help="name of a manifest in data/candidates")
    source.add_argument("--urls-file", dest="urls", help="a file with addresses, one per line")
    parser.add_argument("--target", type=int, default=0, help="how many successful downloads (0 = the whole list)")
    parser.add_argument("--out-dir", dest="directory", default=AUDIO_DIR)
    parser.add_argument("--slice", dest="slice_s", type=int, default=SLICE_S)
    parser.add_argument("--concurrency", type=int, default=0)
    parser.add_argument("--shuffle", type=int, default=0, help="seed for drawing the overshoot pool")
    parser.add_argument("--report", default="", help="where to write the JSON report")
    args = parser.parse_args(argv)

    items = load_set(args.candidate_set) if args.candidate_set else load_urls(args.urls)
    for item in items:
        item.setdefault("slice_s", args.slice_s)

    target = args.target or len(items)
    if args.shuffle:
        rng = random.Random(args.shuffle)
        rng.shuffle(items)
    # A 25% overshoot: the pool is larger than the target, so that dead links do
    # not eat into the sample.
    pool_size = with_overshoot(target)
    if len(items) > pool_size:
        items = items[:pool_size]

    report = fetch_many(
        items,
        target=target,
        directory=args.directory,
        concurrency=args.concurrency or None,
    )

    print(f"successful: {len(report.successful)}/{target}  attempted: {report.attempted}  time: {report.seconds} s")
    for ident, reason in report.failed:
        print(f"  ERROR [{reason_from_message(reason)}] {ident}: {reason}")
    if report.throttled:
        print(f"  WARNING throttling on entries: {', '.join(report.throttled)}")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "successful": report.successful,
                    "failed": report.failed,
                    "attempted": report.attempted,
                    "seconds": report.seconds,
                    "throttled": report.throttled,
                    "timings": report.timings,
                },
                file,
                ensure_ascii=False,
                indent=2,
            )
    return 0 if len(report.successful) >= min(target, len(items)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
