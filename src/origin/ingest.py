"""Ingest: download, decode, normalise, trim silence, window.

The five steps of section 6 of the specification. Candidates go through
exactly the same path as the query - which is why the whole pipeline lives in a
single `_build` function used by both `load_clip` and `Clip.from_array`.

This module is orchestration and nothing more. Two steps have their own
modules, because they are self-contained and anchored outside it: downloading
together with recognising the failure reason lives in `origin.download`, and
BS.1770-4 loudness measurement in `origin.loudness`.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from origin import config, download, loudness
from origin.errors import DownloadError, IngestError

__all__ = [
    "Clip",
    "IngestError",
    "DownloadError",
    "load_clip",
    "split_into_windows",
]


@dataclass
class Clip:
    """Normalised input material in two paths, with a window grid.

    Time in `windows`, and in everything the detectors compute from it, is
    counted from the start of the CLIP, not of the source recording.
    `source_offset_s` says how many seconds of the source were cut off the
    front - by picking the highest-energy fragment and by trimming silence. To
    show a span in the source recording (A/B playback, a quote in a report),
    that number has to be added. Without it the span would point at a
    completely different place in the recording, and an evidentiary tool would
    be lying.
    """

    y_harmonic: np.ndarray
    y_speech: np.ndarray
    sr_harmonic: int
    sr_speech: int
    duration: float
    windows: list[tuple[float, float]] = field(default_factory=list)
    sha256: str = ""
    source_offset_s: float = 0.0

    @classmethod
    def from_array(cls, y: np.ndarray, sr: int) -> "Clip":
        """Constructor from an in-memory array. The same pipeline as for a file."""
        return _build(np.asarray(y, dtype=np.float32), int(sr))

    def to_source(self, span: tuple[float, float]) -> tuple[float, float]:
        """Converts a span from clip time to source-recording time."""
        return (span[0] + self.source_offset_s, span[1] + self.source_offset_s)


# --- step 2: decoding -------------------------------------------------------


def _read_soundfile(path: str) -> tuple[np.ndarray, int]:
    """Decoding through soundfile/libsndfile - the fast path for WAV/FLAC/OGG."""
    y, sr = sf.read(path, dtype="float32", always_2d=False)
    y = np.asarray(y, dtype=np.float32)
    if y.ndim > 1:
        # soundfile returns (samples, channels) - we average over the channel axis.
        y = y.mean(axis=1, dtype=np.float32)
    return y, int(sr)


def _transcode_to_wav(path: str, target: str) -> None:
    """Rewrites the material to WAV through ffmpeg when libsndfile does not know the codec.

    Librosa 1.0 decodes only what libsndfile knows, with no fallback to
    audioread, which used to handle AAC quietly. libsndfile does not know AAC,
    and the whole corpus (291 tracks) and all demo candidates live in m4a -
    yt_dlp fetches them as bestaudio[ext=m4a] - so without this step every file
    would bounce off as "Format not recognised". We change only the container
    and the codec: mono, float32, the sample rate stays native so that
    resampling is done by _build exactly as for any other source.
    """
    ffmpeg = os.environ.get("ORIGIN_FFMPEG", "ffmpeg")
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", path,
        "-vn", "-ac", "1", "-c:a", "pcm_f32le", "-f", "wav", target,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except OSError as error:
        raise IngestError(f"could not start ffmpeg ({ffmpeg}): {error}") from error
    if result.returncode != 0 or not Path(target).exists():
        reason = (result.stderr or "").strip().splitlines()
        raise IngestError(
            f"ffmpeg {result.returncode}: {reason[-1] if reason else 'no message'}"
        )


def _decode_through_ffmpeg(path: str) -> tuple[np.ndarray, int]:
    """Fallback for containers libsndfile does not know (m4a/AAC and similar).

    The temporary file is cleaned up in finally, so that a transcoding failure
    does not leave rubbish in /tmp.
    """
    handle = tempfile.NamedTemporaryFile(prefix="origin-transcode-", suffix=".wav", delete=False)
    handle.close()
    try:
        _transcode_to_wav(path, handle.name)
        return _read_soundfile(handle.name)
    except Exception as error:
        raise IngestError(f"could not decode {path}: {error}") from error
    finally:
        Path(handle.name).unlink(missing_ok=True)


def _decode(path: str) -> tuple[np.ndarray, int]:
    """One decode to mono at the native sample rate; both paths come from it.

    soundfile first. When libsndfile does not know the codec (typically AAC in
    m4a), we transcode through ffmpeg into a temporary WAV and decode that file.
    """
    try:
        y, sr = _read_soundfile(path)
    except Exception:
        y, sr = _decode_through_ffmpeg(path)
    if y.size == 0:
        raise IngestError(f"empty material: {path}")
    return np.asarray(y, dtype=np.float32), int(sr)


def _cut_highest_energy_fragment(y: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """Material longer than the limit is cut down to the window with the highest RMS energy.

    Returns the fragment and its start in samples, because without that number
    there is no way to reconstruct which place in the source ended up in the
    clip.
    """
    limit = int(round(config.MAX_DURATION_S * sr))
    if y.size <= limit:
        return y, 0
    hop = max(1, int(round(config.HOP_S * sr)))
    # Cumulative sum of squares: the energy of any window in constant time.
    cumulative = np.concatenate(([0.0], np.cumsum(np.square(y, dtype=np.float64))))
    starts = np.arange(0, y.size - limit + 1, hop)
    energies = cumulative[starts + limit] - cumulative[starts]
    start = int(starts[int(np.argmax(energies))])
    return y[start:start + limit], start


# --- step 4: silence trimming ----------------------------------------------


def _bounds_without_silence(y: np.ndarray) -> tuple[int, int]:
    _, interval = librosa.effects.trim(y, top_db=config.TRIM_TOP_DB)
    start, end = int(interval[0]), int(interval[1])
    if end <= start:
        # The material is entirely below the threshold (e.g. pure silence) - we
        # cut nothing, because an empty clip carries no information for the
        # detectors.
        return 0, int(y.size)
    return start, end


# --- step 5: windowing ------------------------------------------------------


def split_into_windows(duration: float) -> list[tuple[float, float]]:
    """Windows of WINDOW_S with a hop of HOP_S, that is 50 percent overlap.

    The overlap is not an optimisation but a correctness condition: without it
    a short fragment falls between windows and stops being detectable.

    All windows are closed at the end of the material, so that the report does
    not promise audio that does not exist. The last start is dropped when what
    remains of it is a stub shorter than MIN_WINDOW_S: such a window has fewer
    samples than the fingerprint detector's n_fft, so the STFT would return
    zeros, chroma would divide by zero and a nan would reach fusion. It would
    blow up at the consumer, not here.
    """
    if duration <= 0:
        return []
    starts: list[float] = []
    start = 0.0
    while start < duration:
        starts.append(start)
        start += config.HOP_S
    if len(starts) > 1 and duration - starts[-1] < config.MIN_WINDOW_S:
        starts.pop()
    return [(s, min(s + config.WINDOW_S, duration)) for s in starts]


# --- pipeline ---------------------------------------------------------------


def _build(y: np.ndarray, sr_native: int) -> Clip:
    if y.ndim > 1:
        y = librosa.to_mono(y)
    if y.size == 0:
        raise IngestError("empty material")

    y, sample_offset = _cut_highest_energy_fragment(y, sr_native)
    offset_s = sample_offset / sr_native

    y_harmonic = librosa.resample(y, orig_sr=sr_native, target_sr=config.SR_HARMONIC)
    y_speech = librosa.resample(y, orig_sr=sr_native, target_sr=config.SR_SPEECH)

    gain = loudness.gain_to_target(y_harmonic, config.SR_HARMONIC)
    y_harmonic = (y_harmonic * gain).astype(np.float32)
    y_speech = (y_speech * gain).astype(np.float32)

    start, end = _bounds_without_silence(y_harmonic)
    y_harmonic = y_harmonic[start:end]
    # The same bounds in time, converted to the speech path's grid - otherwise
    # the two paths would drift apart by a fraction of a second and offsets
    # would stop meaning the same thing in both detectors.
    start_speech = int(round(start / config.SR_HARMONIC * config.SR_SPEECH))
    end_speech = min(y_speech.size, int(round(end / config.SR_HARMONIC * config.SR_SPEECH)))
    y_speech = y_speech[start_speech:end_speech]
    offset_s += start / config.SR_HARMONIC

    duration = y_harmonic.size / config.SR_HARMONIC
    return Clip(
        y_harmonic=y_harmonic,
        y_speech=y_speech,
        sr_harmonic=config.SR_HARMONIC,
        sr_speech=config.SR_SPEECH,
        duration=duration,
        windows=split_into_windows(duration),
        # SHA after normalisation, not of the source file: it must identify the
        # signal, not the container, so that the cache hits even with a
        # different input format.
        sha256=hashlib.sha256(y_harmonic.tobytes()).hexdigest(),
        source_offset_s=offset_s,
    )


def load_clip(path_or_url: str) -> Clip:
    """Loads local material or material from a URL and runs it through the five steps of section 6."""
    if download.is_url(path_or_url):
        with tempfile.TemporaryDirectory(prefix="origin-ingest-") as directory:
            path = download.fetch(path_or_url, directory)
            y, sr = _decode(path)
            return _build(y, sr)
    if not Path(path_or_url).exists():
        raise IngestError(f"no such file: {path_or_url}")
    y, sr = _decode(path_or_url)
    return _build(y, sr)
