"""Shared cache of level 0 artifacts. Section 4 of the specification.

Both level 1 detectors compute a candidate's representation offline and in the
live path only read it back from disk. There is a single convention, because
two would mean that ORIGIN_CACHE_DIR redirects one detector and leaves the
other alone, and that an atomic write fixed in one place stays unfixed in the
other.

The file key is made of two parts:

* a hash of the tuple of the ACTUAL parameters the artifact depends on. The
  tuple also covers constants from other modules: changing `config.SR_HARMONIC`
  has to invalidate the cache on its own, rather than waiting for someone to
  bump a version literal in the detector by hand. The only thing kept by hand
  is the layout of fields in the npz file, because that is the only thing under
  the control of the module that writes the file.
* the identity of the source file: path, modification time and size.
"""
from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

__all__ = ["cache_dir", "artifact_path", "load_npz", "save_npz"]

CACHE_DIR_ENV = "ORIGIN_CACHE_DIR"
DEFAULT_CACHE_DIR = "data/cache"


def cache_dir() -> Path:
    """The cache directory. Read on every call, because tests move it at runtime."""
    return Path(os.environ.get(CACHE_DIR_ENV, DEFAULT_CACHE_DIR))


def artifact_path(prefix: str, audio_path: str | Path, parameters: tuple[Any, ...]) -> Path:
    """Path of the artifact npz file for a given recording. The cache directory is outside git.

    `parameters` is passed by the caller on every call, not once at import
    time: the constants an artifact depends on live partly in other modules,
    and when they are patched in tests the key has to change immediately.
    """
    path = Path(audio_path)
    try:
        stat = path.stat()
        source = f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
    except OSError:
        source = str(path)
    fingerprint = hashlib.sha256(repr(parameters).encode()).hexdigest()[:16]
    key = hashlib.sha256(f"{fingerprint}|{source}".encode()).hexdigest()[:32]
    return cache_dir() / f"{prefix}-{key}.npz"


def load_npz(file: Path, fields: Sequence[str]) -> dict[str, np.ndarray] | None:
    """The requested arrays from an npz file, or None when the file is missing or corrupt.

    A missing field counts exactly the same as a corrupt file: an artifact
    written with a different field layout is not the artifact the caller is
    asking for, and it has to be recomputed.

    The except clause is deliberately broad: a truncated npz starts with a zip
    header, so numpy enters zipfile and raises BadZipFile, which inherits
    straight from Exception. A narrower clause would let that exception through
    and blow up the detector's envelope, whereas a corrupt cache should simply
    be recomputed.
    """
    if not file.exists():
        return None
    try:
        with np.load(file, allow_pickle=False) as data:
            return {name: data[name] for name in fields}
    except Exception:  # noqa: BLE001 - a corrupt cache is recomputed
        return None


def save_npz(
    file: Path, arrays: dict[str, np.ndarray], *, compressed: bool = False
) -> None:
    """Atomic write: a reader will never see a half-written file.

    The temporary name is unique per WRITE, not per process: artifacts are
    computed in a thread pool sharing one PID, so two candidates with the same
    audio_path would write to a single temporary file and swap in truncated
    content.

    A failed write is not the caller's error: the cache is an optimisation, not
    a source of truth, so all that is left behind is a cleaned-up temporary
    file.
    """
    temporary = file.with_suffix(f".{uuid4().hex}.tmp.npz")
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        write = np.savez_compressed if compressed else np.savez
        write(temporary, **arrays)
        os.replace(temporary, file)
    except Exception:  # noqa: BLE001 - the cache is an optimisation, not a source of truth
        temporary.unlink(missing_ok=True)
