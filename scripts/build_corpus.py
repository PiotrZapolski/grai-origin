#!/usr/bin/env python3
"""Building the IDF corpus from downloaded audio. Sections 5.6 and 8 of the specification.

The script DOWNLOADS NOTHING. Fetching the corpus (a stratified draw by
language and group size from the SecondHandSongs export, then
scripts/fetch_audio.py) is a separate step and is on hold for the duration of
the demo. Here the corpus is computed from whatever already lies on the
server's disk, and as many tracks as actually came down land in the
`corpus_size` field. The target 3,000 from section 5.6 still stands - the
bigger the corpus, the better the filter - but an IDF computed on a few hundred
tracks already tells a progression present in half the corpus apart from a
motif occurring once, and that is the entire question the commonality filter
answers.

For every file: ingest -> chroma -> chord sequence -> n-grams -> the pattern set
of one document. The sequences land in a JSONL journal, so an interrupted run
resumes without decoding again.

Usage:
    nice -n 19 python scripts/build_corpus.py
    nice -n 19 python scripts/build_corpus.py --audio-dir data/audio/corpus --out data/corpus/idf.json
"""
from __future__ import annotations

import os

# The core quota has to be set BEFORE numpy and librosa manage to start their
# thread pools, that is before the first import that pulls them in. BLAS and
# numba read these variables once, at initialisation, and a later change
# achieves nothing. config does not import numpy, so it may be loaded here
# without creating a second source for the quota.
from origin import config  # noqa: E402


def _core_quota() -> int:
    """sched_getaffinity, never cpu_count. The server has 12 CPUs, we may occupy four."""
    try:
        available = len(os.sched_getaffinity(0))
    except AttributeError:  # macOS has no sched_getaffinity
        available = 1
    return max(1, min(config.CPU_QUOTA, available))


_QUOTA = str(_core_quota())
for _variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "NUMBA_NUM_THREADS",
):
    os.environ.setdefault(_variable, _QUOTA)

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402

from origin import commonality as cm  # noqa: E402
from origin import ingest  # noqa: E402
from origin.detectors import harmonic  # noqa: E402

AUDIO_DIR = "data/audio/corpus"
CORPUS_FILE = "data/corpus/idf.json"
# The journal of chord sequences. It serves to resume an interrupted run and to
# rebuild the corpus with different n-gram sizes without decoding the audio
# again, which is the only expensive step here.
#
# It lives in data/cache rather than next to the corpus, on purpose: scripts/rt
# synchronises the repository with --delete and excludes data/cache and
# data/audio, but NOT data/corpus. Every test run therefore deletes idf.json
# while the journal survives - and rebuilding the corpus costs seconds instead
# of decoding all the audio again.
JOURNAL = "data/cache/corpus_sequences.jsonl"

EXTENSIONS = (".m4a", ".mp3", ".webm", ".opus", ".wav", ".flac", ".ogg")


def audio_files(directory: str | Path) -> list[Path]:
    """A sorted list of the corpus audio files. A fixed order, so that runs are comparable."""
    path = Path(directory)
    if not path.is_dir():
        raise SystemExit(f"there is no corpus audio directory: {path}")
    return sorted(p for p in path.iterdir() if p.suffix.lower() in EXTENSIONS)


def load_journal(path: str | Path) -> dict[str, list[str]]:
    """Sequences computed in earlier runs, keyed by file name.

    Failed entries do not reach the result, so the next run tries them again: a
    failed decode is sometimes the consequence of an interrupted download
    rather than a property of the file.
    """
    file = Path(path)
    if not file.exists():
        return {}
    known: dict[str, list[str]] = {}
    with open(file, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # a truncated line after a killed run
            if entry.get("chords") is not None:
                known[str(entry["file"])] = [str(c) for c in entry["chords"]]
    return known


def chord_sequence(path: Path) -> list[str]:
    """Ingest, chroma and the chord sequence of one corpus track.

    Transcoding containers that libsndfile does not know (m4a/AAC and similar)
    now lives in ingest._decode, so every consumer gets it for free - there is
    no need here to tell formats apart or to call ffmpeg separately.
    """
    clip = ingest.load_clip(str(path))
    return harmonic.chord_sequence(harmonic.chroma(clip))


def collect_sequences(
    files: list[Path],
    journal: str | Path,
    threads: int,
) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """Chord sequences of the whole file set, in parallel, skipping the ones already computed.

    An error on one file does not interrupt the run: the corpus is built from
    what can be decoded, and the rejection reason goes to the journal and to
    the report.
    """
    done = load_journal(journal)
    to_compute = [p for p in files if p.name not in done]
    errors: list[tuple[str, str]] = []
    if not to_compute:
        return done, errors

    Path(journal).parent.mkdir(parents=True, exist_ok=True)
    with open(journal, "a", encoding="utf-8") as log, ThreadPoolExecutor(max_workers=threads) as pool:
        submissions = {pool.submit(chord_sequence, p): p for p in to_compute}
        for number, (submission, file) in enumerate(submissions.items(), start=1):
            try:
                chords = submission.result()
            except Exception as error:  # noqa: BLE001 - no audio means no document, not the end of the run
                reason = f"{type(error).__name__}: {error}"
                errors.append((file.name, reason))
                entry = {"file": file.name, "chords": None, "error": reason}
            else:
                done[file.name] = chords
                entry = {"file": file.name, "chords": chords}
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
            log.flush()
            if number % 25 == 0:
                print(f"  computed {number}/{len(to_compute)}", flush=True)
    return done, errors


def build_corpus(sequences: dict[str, list[str]]) -> cm.Corpus:
    """The IDF corpus from the chord sequences. One track is one document."""
    documents = [cm.chord_ngrams(chords) for chords in sequences.values()]
    return cm.Corpus.from_documents(documents)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IDF corpus from downloaded audio (sections 5.6 and 8)")
    parser.add_argument("--audio-dir", default=AUDIO_DIR)
    parser.add_argument("--out", default=CORPUS_FILE)
    parser.add_argument("--journal", default=JOURNAL)
    parser.add_argument("--limit", type=int, default=0, help="how many files to take (0 = all)")
    parser.add_argument("--threads", type=int, default=0, help="0 = the core quota")
    args = parser.parse_args(argv)

    # The corpus is a background job on the machine production runs on.
    try:
        os.nice(19)
    except (AttributeError, OSError):
        pass

    files = audio_files(args.audio_dir)
    if args.limit:
        files = files[: args.limit]
    threads = args.threads or config.worker_count()
    print(f"files: {len(files)}  threads: {threads}  directory: {args.audio_dir}", flush=True)

    start = time.monotonic()
    sequences, errors = collect_sequences(files, args.journal, threads)
    # Only files from the current list enter the corpus, even if the journal
    # remembers more. Otherwise --limit would give a different corpus size than
    # it says.
    selected = {p.name: sequences[p.name] for p in files if p.name in sequences}
    corpus = build_corpus(selected)
    seconds = round(time.monotonic() - start, 1)

    corpus.save(
        args.out,
        source_dir=str(args.audio_dir),
        documents_failed=len(errors),
        build_seconds=seconds,
    )

    print(f"corpus: {corpus.size} tracks, {corpus.distinct_patterns} distinct patterns -> {args.out}")
    print(f"time: {seconds} s")
    for name, reason in errors:
        print(f"  ERROR {name}: {reason}")
    if corpus.size:
        threshold = corpus.common_idf_threshold
        common = sum(1 for p in corpus.patterns() if corpus.idf(p) < threshold)
        print(f"commonality IDF threshold: {threshold:.3f}  patterns below the threshold: {common}")
    return 0 if corpus.size else 1


if __name__ == "__main__":
    raise SystemExit(main())
