# GRAI ORIGIN Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a system that accepts a URL to an audio clip and returns the evidence class of the match (`EXACT`, `MODIFIED`, `VERSION`, `EXCERPT`, `LYRICS`, `COMMON`, `NONE`) together with a calibrated probability and evidence that can be verified by listening.

**Architecture:** A Python backend (FastAPI) with a registry of detectors working on a shared `Clip` object. The work is split into three execution levels: level 0 offline (candidate representations, IDF corpus, calibration model), level 1 live with a 5 s target (fingerprint + harmonic similarity + fusion + verdict), level 2 in the background (lyrics + melody, upgrading the verdict). The front end (Next.js) talks to the backend exclusively over HTTP and SSE, never through an import.

**Tech Stack:** Python 3.11+, FastAPI, librosa, numpy, scipy, scikit-learn, faster-whisper, demucs, basic-pitch, datasketch; Next.js, Tailwind, wavesurfer.js. Permissive licenses only.

**Spec:** `docs/superpowers/specs/2026-08-21-grai-origin-spec.md`

## Global Constraints

These rules bind **every** task. Verbatim copies from the specification, sections given in parentheses.

1. **Tests are run exclusively on Hetzner** through `./scripts/rt`. Never locally: no `pytest` on the laptop, no `npm run dev`, no docker, no background processes.
2. **The core quota is hard.** Another project's production runs on the server. Every computing process goes through `nice -n 19` and `taskset` limited to the quota from `ORIGIN_CPU_QUOTA` (section 4, D8).
3. **Heavy models (demucs, whisper) never run on the whole candidate set.** Only on the query and on the shortlist after shortlisting (section 4).
4. **A detector status appears at two levels**: the envelope and the individual result. Allowed values: `ok`, `not_applicable`, `gated`, `failed`. **`not_applicable` and `gated` are not a zero** (section 7.0).
5. **Degradation to `COMMON` applies only to `VERSION`, `LYRICS`, `EXCERPT/work`. Never to `EXACT`, `MODIFIED`, `EXCERPT/phonogram`** (section 8.1).
6. **The evaluation order of the decision tree is binding**, the first rule satisfied wins (section 9.1).
7. **Every threshold carries its source** (`calibrated` or `manual`), and the UI must distinguish them visually (sections 9.2, 10.5).
8. **`published_source` accepts only `manual` or `metadata_registry`. Never `youtube`** (section 5.5). The manifest validator must reject it.
9. **The chronology rule works only for candidates having `published`** (section 9.3).
10. **The front end never imports anything from the engine.** HTTP and SSE only (section 17.1).
11. **Lime exclusively as a signal** (best match, alert, active step), never as decoration. Technical values in a monospaced face (section 13.1).
12. **No data in the repo**: audio, song lyrics and SHS catalog dumps are excluded by `.gitignore`. The candidate manifest stays.
13. **Audio downloading always with a 25% overage**, finishing once the target number of successful downloads is collected, not once the list is exhausted (section 5.7).
14. **No em-dashes or en-dashes** in the code, comments, commits or the UI. Plain hyphens only.
15. **Language:** comments and commit messages in English, identifiers in English.

### Thresholds (section 9.2) - starting values, entered in `config.py`

| Key | Value | Source |
|---|---|---|
| `EXACT_PEAK_RATIO` | 0.60 | `calibrated` |
| `EXACT_MIN_SPAN_S` | 15.0 | `manual` |
| `MODIFIED_PEAK_RATIO` | 0.50 | `calibrated` |
| `EXCERPT_PEAK_RATIO` | 0.40 | `calibrated` |
| `EXCERPT_MIN_REPETITIONS` | 2 | `manual` |
| `VERSION_MAX_PEAK_RATIO` | 0.40 | `calibrated` |
| `VERSION_QMAX` | 0.55 | `calibrated` |
| `VERSION_COVERAGE` | 0.50 | `calibrated` |
| `EXCERPT_WORK_MIN_RUN` | 8 | `manual` |
| `LYRICS_MAX_QMAX` | 0.40 | `manual` |
| `LYRICS_JACCARD` | 0.50 | `manual` |
| `COMMON_IDF_PERCENTILE` | 0.01 | `calibrated` |
| `FINGERPRINT_NOISE_FLOOR` | 0.25 | `manual` |

---

## File structure

```
src/origin/
  contracts.py        types of all the JSON contracts (sections 7.0, 12)
  config.py           thresholds from 9.2 together with their source, paths, CPU quota
  ingest.py           section 6: download, decoding, normalization, windows
  candidates.py       the candidate manifest from 5.3 together with validation
  detectors/
    base.py           envelope, statuses, detector protocol (7.0)
    registry.py       the registry that fusion iterates over
    fingerprint.py    detector A (7.1)
    harmonic.py       detector B (7.2)
    lyrics.py         detector D (7.3)
    melodic.py        detector C (7.4)
  shortlist.py        shortlisting down to 20 candidates (7.2 preliminary shortlisting)
  commonality.py      IDF corpus and commonality filter (section 8)
  fusion.py           decision tree (section 9)
  legal.py            legal layer (section 11)
  calibration.py      the regression model and its application (section 10)
  api/
    app.py            the FastAPI application
    jobs.py           job store, level queue, SSE stream
    routes.py         the four endpoints from section 12
scripts/
  rt                  running the tests on Hetzner
  fetch_audio.py      downloading with an overage (5.7)
  sample_calibration.py  drawing pairs with the filter from 5.4
  build_corpus.py     IDF corpus (5.6)
  measure.py          the M0 measurement
tests/
  conftest.py         synthetic audio fixtures
  test_*.py           one file per module
web/
  lib/contracts.ts    types mirroring contracts.py
  lib/theme.ts        tokens of the visual system from 13.1
  app/page.tsx        E1
  components/         one directory per screen
```

---

## Execution waves

Tasks within one wave have **disjoint file sets** and may be dispatched in parallel. The waves run in order.

| Wave | Tasks | In parallel |
|---|---|---|
| 0 | T1 remote environment | no |
| 1 | T2 contracts and foundation | no |
| 2 | T3 ingest, T4 manifest, T5 API and SSE, T6 front-end scaffold | yes, 4 |
| 3 | T7 detector A, T8 detector B, T9 audio downloading | yes, 3 |
| 4 | T10 shortlisting, T11 IDF corpus and filter | yes, 2 |
| 5 | T12 fusion, T13 legal layer | no (13 reads the output of 12) |
| 6 | T14 detector D, T15 detector C | yes, 2 |
| 7 | T16 calibration sample, T17 calibration model | no |
| 8 | T18 E1-E2, T19 E3-E4, T20 E5-E7, T21 E8-E10 | yes, 4 |
| 9 | T22 integration and demo scenarios | no |

---

## WAVE 0

### Task 1: Remote environment and running the tests

Without this task none of the others can be verified, because the tests must not be run locally.

**Files:**
- Create: `scripts/rt`
- Create: `.rsyncignore`
- Create: `pyproject.toml`
- Create: `tests/test_smoke.py`
- Create: `scripts/__init__.py` (empty; without it the T9 and T16 tests will not import `scripts.fetch_audio`)
- Create: `docs/measurements.md`

**Interfaces:**
- Consumes: nothing
- Produces: `./scripts/rt <pytest arguments>` running the tests on Hetzner. All subsequent tasks use only this command.

**Preconditions:** port 22 on `<server-ip>` must be open for the address you are working from. Check with `nc -z -G 8 <server-ip> 22`. If it is closed, report BLOCKED, do not attempt a workaround.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "grai-origin"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110",
  "uvicorn>=0.29",
  "pydantic>=2.6",
  "numpy>=1.26",
  "scipy>=1.12",
  "librosa>=0.10",
  "soundfile>=0.12",
  "scikit-learn>=1.4",
  "datasketch>=1.6",
]

[project.optional-dependencies]
heavy = ["faster-whisper>=1.0", "demucs>=4.0", "basic-pitch>=0.3"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]

[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [".", "src"]
markers = [
  "heavy: requires demucs/whisper, skipped by default",
  "integration: requires real audio from data/audio",
]
addopts = "-m 'not heavy' --strict-markers"
```

- [ ] **Step 2: Create `.rsyncignore`**

```
.git/
.venv/
node_modules/
__pycache__/
.pytest_cache/
.superpowers/
data/audio/
data/cache/
web/.next/
```

- [ ] **Step 3: Create `scripts/rt`**

```bash
#!/usr/bin/env bash
# Runs the tests on Hetzner. NEVER locally - see Global Constraints point 1.
# Usage: ./scripts/rt                      (all tests)
#        ./scripts/rt tests/test_ingest.py (a chosen file)
set -euo pipefail

REMOTE="${ORIGIN_REMOTE:?set ORIGIN_REMOTE to your ssh host alias}"
REMOTE_DIR="${ORIGIN_REMOTE_DIR:-/opt/grai-origin}"
QUOTA="${ORIGIN_CPU_QUOTA:-4}"

rsync -az --delete --exclude-from=.rsyncignore ./ "${REMOTE}:${REMOTE_DIR}/"

ssh "${REMOTE}" bash -s -- "${REMOTE_DIR}" "${QUOTA}" "$@" <<'REMOTE_SCRIPT'
set -euo pipefail
DIR="$1"; QUOTA="$2"; shift 2
cd "$DIR"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
fi
.venv/bin/pip install --quiet -e '.[dev]'
LAST_CPU=$((QUOTA - 1))
exec nice -n 19 taskset -c "0-${LAST_CPU}" .venv/bin/python -m pytest "$@"
REMOTE_SCRIPT
```

Set permissions: `chmod +x scripts/rt`.

- [ ] **Step 4: Write the smoke test**

```python
# tests/test_smoke.py
"""Checks that the remote environment stands up at all."""
import sys


def test_python_version():
    assert sys.version_info >= (3, 11)


def test_numpy_works():
    import numpy as np

    assert np.array([1, 2, 3]).sum() == 6


def test_librosa_works():
    import librosa

    y = librosa.tone(440.0, sr=22050, length=22050)
    assert y.shape == (22050,)
```

- [ ] **Step 5: Run the smoke test**

Run: `./scripts/rt tests/test_smoke.py -v`
Expected: 3 passed. The first run installs the dependencies and will take a few minutes.

- [ ] **Step 6: Measure the hardware and write it to `docs/measurements.md`**

Run:
```bash
ssh <ssh-host> 'nproc; free -g | head -2; uptime; df -h /opt | tail -1'
```

Write the result into `docs/measurements.md` in the format:

```markdown
# Measurements - target machine

Date: <date>
Host: <server-ip>

| Quantity | Value |
|---|---|
| Physical cores | <n> |
| RAM | <n> GB |
| Load average | <value> |
| Free space on /opt | <n> GB |
| Core quota for GRAI ORIGIN | <n> |

## Operation timings (filled in during T15 and T14)

| Operation | 60 s clip | Notes |
|---|---|---|
| CQT + chroma | | |
| Acoustic fingerprint | | |
| faster-whisper base | | |
| demucs htdemucs | | |
```

Core quota: **4**. Measured before the start: AMD Ryzen 5 3600, **6 physical cores**,
12 logical through SMT, 62 GB RAM (40 free), load average 3.10.

Careful, there is a trap here: `nproc` returns 12, `nproc --all` returns 32, and there are
six physical cores. Checked in `/sys/devices/system/cpu/*/topology/core_id`: `cpu0-5` map
onto six **different** physical cores, and `cpu6-11` are their SMT siblings. That means
`taskset -c 0-5` takes **the whole physical processor**, not half the machine.

Production takes about three cores, so the quota is `taskset -c 0-3`, which leaves it two
physical cores untouched. That number must not be raised without measuring again.

Code choosing a thread count is to use `len(os.sched_getaffinity(0))`, **never**
`os.cpu_count()` or `nproc --all`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml scripts/rt .rsyncignore tests/test_smoke.py docs/measurements.md
git commit -m "feat: remote environment and running the tests on Hetzner"
```

---

## WAVE 1

### Task 2: Contracts, threshold configuration and test fixtures

The foundation every subsequent task uses. Nothing here computes, everything defines shape.

**Files:**
- Create: `src/origin/__init__.py`
- Create: `src/origin/contracts.py`
- Create: `src/origin/config.py`
- Create: `tests/conftest.py`
- Create: `tests/test_contracts.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `contracts.DetectorEnvelope(detector: str, status: DetectorStatus, reason: str | None, results: list[DetectorResult])`
  - `contracts.FingerprintResult`, `HarmonicResult`, `LyricsResult`, `MelodicResult`
  - `contracts.Candidate`, `CandidateSet`, `RankingEntry`, `AnalyzeResult`
  - `contracts.VERDICT_CLASSES`, `contracts.DETECTOR_STATUSES`
  - `config.THRESHOLDS: dict[str, Threshold]` where `Threshold(value: float, source: Literal["calibrated", "manual"])`
  - pytest fixtures: `sine_wav`, `chord_wav`, `shifted_wav`, `silence_wav`, `noise_wav`

- [ ] **Step 1: Write the contract tests**

```python
# tests/test_contracts.py
import pytest
from pydantic import ValidationError

from origin import contracts as c


def test_detector_status_has_exactly_four_values():
    assert set(c.DETECTOR_STATUSES) == {"ok", "not_applicable", "gated", "failed"}


def test_verdict_classes_cover_the_taxonomy():
    assert set(c.VERDICT_CLASSES) == {
        "EXACT", "MODIFIED", "VERSION",
        "EXCERPT_PHONOGRAM", "EXCERPT_WORK",
        "LYRICS", "COMMON", "NONE",
    }


def test_a_result_without_a_status_inherits_ok():
    r = c.FingerprintResult(candidate_id="cand_01", peak_ratio=0.8, matched_hashes=100,
                            query_span=(1.0, 20.0), candidate_span=(5.0, 24.0),
                            offset=4.0, repetitions=1)
    assert r.status == "ok"


def test_the_envelope_carries_its_own_status_independent_of_the_results():
    env = c.DetectorEnvelope(detector="lyrics", status="gated",
                             reason="asr_confidence", results=[])
    assert env.status == "gated"
    assert env.results == []


def test_not_applicable_is_not_zero():
    """Global Constraint 4: not applicable is not the same as no similarity."""
    r = c.LyricsResult(candidate_id="cand_01", status="not_applicable",
                       reason="instrumental")
    assert r.jaccard is None
    assert r.semantic_sim is None


def test_candidate_rejects_published_source_youtube():
    """Global Constraint 8: a YouTube date would regularly point at the cover as the original."""
    with pytest.raises(ValidationError):
        c.Candidate(id="cand_01", name="X", artist="Y",
                    source_url="https://youtube.com/watch?v=abc",
                    audio_path="data/audio/cand_01.wav",
                    published="1975-02-24", published_source="youtube",
                    license="all_rights_reserved", instrumental=False)


def test_candidate_accepts_manual_and_metadata_registry():
    for src in ("manual", "metadata_registry"):
        cand = c.Candidate(id="cand_01", name="X", artist="Y",
                           source_url="https://example.com/a",
                           audio_path="data/audio/cand_01.wav",
                           published="1975-02-24", published_source=src,
                           license="all_rights_reserved", instrumental=False)
        assert cand.published_source == src


def test_a_candidate_may_have_no_date():
    """Section 9.3: with no date the chronology rule does not apply, but the candidate is valid."""
    cand = c.Candidate(id="cand_01", name="X", artist="Y",
                       source_url="https://example.com/a",
                       audio_path="data/audio/cand_01.wav",
                       published=None, published_source=None,
                       license="unknown", instrumental=False)
    assert cand.published is None


def test_a_ranking_entry_carries_the_probability_status():
    """Global Constraint 7: the UI must tell a calibrated threshold from an entered one."""
    entry = c.RankingEntry(rank=1, candidate=_candidate(), verdict_class="VERSION",
                           verdict_layer="work", probability=0.71,
                           probability_status="uncalibrated", evidence={},
                           alignment=None, commonality=None, legal=None,
                           explanation="")
    assert entry.probability_status == "uncalibrated"


def test_the_analysis_result_tells_partial_apart_from_full():
    res = c.AnalyzeResult(status="partial", completed_levels=[1],
                          query=c.QueryInfo(duration=184.2, waveform_url=None,
                                            transcript=[]),
                          ranking=[], calibration=None)
    assert res.status == "partial"
    assert res.completed_levels == [1]


def _candidate() -> "c.Candidate":
    return c.Candidate(id="cand_01", name="X", artist="Y",
                       source_url="https://example.com/a",
                       audio_path="data/audio/cand_01.wav",
                       published="1975-02-24", published_source="manual",
                       license="all_rights_reserved", instrumental=False)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `./scripts/rt tests/test_contracts.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'origin'`

- [ ] **Step 3: Implement `src/origin/contracts.py`**

All the types as pydantic v2 models. Key requirements:

```python
"""JSON contracts for the whole system. Sections 7.0 and 12 of the specification."""
from typing import Literal, Any

from pydantic import BaseModel, Field, field_validator

DETECTOR_STATUSES = ("ok", "not_applicable", "gated", "failed")
DetectorStatus = Literal["ok", "not_applicable", "gated", "failed"]

VERDICT_CLASSES = (
    "EXACT", "MODIFIED", "VERSION",
    "EXCERPT_PHONOGRAM", "EXCERPT_WORK",
    "LYRICS", "COMMON", "NONE",
)
VerdictClass = Literal[
    "EXACT", "MODIFIED", "VERSION",
    "EXCERPT_PHONOGRAM", "EXCERPT_WORK",
    "LYRICS", "COMMON", "NONE",
]

RightsLayer = Literal["phonogram", "work", "performance"]
PublishedSource = Literal["manual", "metadata_registry"]


class DetectorResult(BaseModel):
    """Result for one candidate. Status defaults to ok - see section 7.0."""
    candidate_id: str
    status: DetectorStatus = "ok"
    reason: str | None = None


class FingerprintResult(DetectorResult):
    matched_hashes: int | None = None
    peak_ratio: float | None = None
    query_span: tuple[float, float] | None = None
    candidate_span: tuple[float, float] | None = None
    offset: float | None = None
    repetitions: int = 0
    transform: dict[str, float] | None = None

    @property
    def span_length(self) -> float:
        if self.query_span is None:
            return 0.0
        return self.query_span[1] - self.query_span[0]


class HarmonicResult(DetectorResult):
    qmax_score: float | None = None
    transposition: int | None = None
    tempo_ratio: float | None = None
    alignment_path: list[tuple[int, int]] = Field(default_factory=list)
    coverage: float | None = None
    chord_sequence: list[str] = Field(default_factory=list)


class LyricsResult(DetectorResult):
    jaccard: float | None = None
    semantic_sim: float | None = None
    matched_spans: list[dict[str, Any]] = Field(default_factory=list)
    asr_confidence: float | None = None
    language: str | None = None
    used_separation: bool = False


class MelodicResult(DetectorResult):
    matched_ngrams: list[dict[str, Any]] = Field(default_factory=list)
    longest_common_run: int = 0
    ms_distance: float | None = None


class DetectorEnvelope(BaseModel):
    """The envelope status concerns the run for the whole query, not a candidate."""
    detector: str
    status: DetectorStatus = "ok"
    reason: str | None = None
    results: list[DetectorResult] = Field(default_factory=list)


class Candidate(BaseModel):
    id: str
    name: str
    artist: str
    shs_performance_id: str | None = None
    source_url: str
    audio_path: str
    published: str | None = None
    published_source: PublishedSource | None = None
    license: str = "unknown"
    instrumental: bool = False
    language: str | None = None
    lyrics_path: str | None = None

    @field_validator("published_source", mode="before")
    @classmethod
    def _reject_youtube(cls, v: Any) -> Any:
        """Section 5.5: the YouTube upload date is not the release date."""
        if v == "youtube":
            raise ValueError(
                "published_source 'youtube' is forbidden: the upload date "
                "is not the release date and the chronology axis would point "
                "at the cover as the original"
            )
        return v
```

Add analogously: `CandidateSet`, `Alignment`, `Commonality`, `Legal`, `QueryInfo`, `RankingEntry`, `CalibrationInfo`, `AnalyzeResult`, `StreamEvent`. Fields exactly as in section 12 of the specification.

- [ ] **Step 4: Write the configuration tests**

```python
# tests/test_config.py
from origin import config


def test_every_threshold_has_a_source():
    """Global Constraint 7."""
    for name, threshold in config.THRESHOLDS.items():
        assert threshold.source in ("calibrated", "manual"), name


def test_thresholds_match_the_specification():
    assert config.THRESHOLDS["EXACT_PEAK_RATIO"].value == 0.60
    assert config.THRESHOLDS["VERSION_QMAX"].value == 0.55
    assert config.THRESHOLDS["VERSION_MAX_PEAK_RATIO"].value == 0.40
    assert config.THRESHOLDS["EXCERPT_MIN_REPETITIONS"].value == 2


def test_version_threshold_is_above_the_noise_floor():
    """Section 9.1: the 0.40 threshold closes the gap between 0.25 and 0.40."""
    assert (config.THRESHOLDS["VERSION_MAX_PEAK_RATIO"].value
            > config.THRESHOLDS["FINGERPRINT_NOISE_FLOOR"].value)


def test_cpu_quota_has_a_default_value():
    assert config.CPU_QUOTA >= 2
```

- [ ] **Step 5: Implement `src/origin/config.py`**

```python
"""Decision thresholds and configuration. Section 9.2 of the specification."""
import os
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Threshold:
    value: float
    source: Literal["calibrated", "manual"]


THRESHOLDS: dict[str, Threshold] = {
    "EXACT_PEAK_RATIO": Threshold(0.60, "calibrated"),
    "EXACT_MIN_SPAN_S": Threshold(15.0, "manual"),
    "MODIFIED_PEAK_RATIO": Threshold(0.50, "calibrated"),
    "EXCERPT_PEAK_RATIO": Threshold(0.40, "calibrated"),
    "EXCERPT_MIN_REPETITIONS": Threshold(2, "manual"),
    "VERSION_MAX_PEAK_RATIO": Threshold(0.40, "calibrated"),
    "VERSION_QMAX": Threshold(0.55, "calibrated"),
    "VERSION_COVERAGE": Threshold(0.50, "calibrated"),
    "EXCERPT_WORK_MIN_RUN": Threshold(8, "manual"),
    "LYRICS_MAX_QMAX": Threshold(0.40, "manual"),
    "LYRICS_JACCARD": Threshold(0.50, "manual"),
    "COMMON_IDF_PERCENTILE": Threshold(0.01, "calibrated"),
    "FINGERPRINT_NOISE_FLOOR": Threshold(0.25, "manual"),
}

CPU_QUOTA = int(os.environ.get("ORIGIN_CPU_QUOTA", "4"))
SR_HARMONIC = 22050
SR_SPEECH = 16000
WINDOW_S = 10.0
HOP_S = 5.0
TARGET_LUFS = -23.0
MAX_DURATION_S = 180.0
SHORTLIST_SIZE = 20
```

**Note:** until the calibration model exists, the thresholds marked `calibrated` hold starting values, but the source stays `calibrated`, because it speaks about the **target** source. Whether the model already exists is settled by `calibration.is_available()` from T17, not by this field.

- [ ] **Step 6: Write the audio fixtures**

```python
# tests/conftest.py
"""Synthetic audio fixtures. Deterministic, no downloading, they work everywhere.

Real audio appears only in tests marked @pytest.mark.integration.
"""
import numpy as np
import pytest
import soundfile as sf

SR = 22050


def _write(tmp_path, name: str, y: np.ndarray, sr: int = SR) -> str:
    path = tmp_path / name
    sf.write(path, y, sr)
    return str(path)


def tone(freq: float, dur: float, sr: int = SR) -> np.ndarray:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * freq * t)


def chord(freqs: list[float], dur: float, sr: int = SR) -> np.ndarray:
    return sum(tone(f, dur, sr) for f in freqs) / len(freqs)


@pytest.fixture
def sine_wav(tmp_path) -> str:
    """Pure 440 Hz tone, 5 s."""
    return _write(tmp_path, "sine.wav", tone(440.0, 5.0))


@pytest.fixture
def chord_wav(tmp_path) -> str:
    """A C-G-Am-F progression, 2 s per chord. Material for detector B and the IDF filter."""
    chords = [
        [261.6, 329.6, 392.0],   # C
        [392.0, 493.9, 587.3],   # G
        [220.0, 261.6, 329.6],   # Am
        [349.2, 440.0, 523.3],   # F
    ]
    y = np.concatenate([chord(c, 2.0) for c in chords])
    return _write(tmp_path, "chord.wav", y)


@pytest.fixture
def shifted_wav(tmp_path) -> str:
    """The same material as chord_wav, sped up by 6%. Material for the MODIFIED class."""
    chords = [
        [261.6, 329.6, 392.0], [392.0, 493.9, 587.3],
        [220.0, 261.6, 329.6], [349.2, 440.0, 523.3],
    ]
    y = np.concatenate([chord(c, 2.0) for c in chords])
    idx = np.arange(0, len(y), 1.06)
    y_faster = np.interp(idx, np.arange(len(y)), y)
    return _write(tmp_path, "shifted.wav", y_faster)


@pytest.fixture
def silence_wav(tmp_path) -> str:
    """Silence with a short tone in the middle. Material for silence trimming."""
    y = np.concatenate([np.zeros(SR * 2), tone(440.0, 1.0), np.zeros(SR * 2)])
    return _write(tmp_path, "silence.wav", y)


@pytest.fixture
def noise_wav(tmp_path) -> str:
    """White noise. Negative control - nothing should match it."""
    rng = np.random.default_rng(42)
    return _write(tmp_path, "noise.wav", rng.normal(0, 0.1, SR * 5))
```

- [ ] **Step 7: Run all the tests**

Run: `./scripts/rt tests/test_contracts.py tests/test_config.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add src/origin tests/conftest.py tests/test_contracts.py tests/test_config.py
git commit -m "feat: contracts, decision thresholds and synthetic audio fixtures"
```

---
## WAVE 2 - in parallel, four tasks, disjoint files

### Task 3: Ingest

**Files:** Create `src/origin/ingest.py`, `tests/test_ingest.py`

**Interfaces:**
- Consumes: `config.SR_HARMONIC`, `SR_SPEECH`, `WINDOW_S`, `HOP_S`, `TARGET_LUFS`, `MAX_DURATION_S`
- Produces: `ingest.load_clip(path_or_url: str) -> Clip`; `Clip` with the fields `y_harmonic: np.ndarray`, `y_speech: np.ndarray`, `sr_harmonic: int`, `sr_speech: int`, `duration: float`, `windows: list[tuple[float, float]]`, `sha256: str`; `Clip.from_array(y: np.ndarray, sr: int) -> Clip` (a helper constructor, used by the T7 tests)

Algorithm: section 6 of the specification, five steps, parameters taken verbatim from there.

- [ ] **Step 1: Tests**

```python
# tests/test_ingest.py
import numpy as np
import pytest
from origin import ingest


def test_windows_have_50_percent_overlap(chord_wav):
    clip = ingest.load_clip(chord_wav)
    assert clip.windows[0] == (0.0, 10.0)
    assert clip.windows[1][0] == 5.0, "a 5 s hop with a 10 s window"


def test_a_clip_shorter_than_the_window_gives_one_window(sine_wav):
    clip = ingest.load_clip(sine_wav)  # 5 s
    assert len(clip.windows) == 1
    assert clip.windows[0] == (0.0, 5.0)


def test_two_paths_with_different_sample_rates(chord_wav):
    clip = ingest.load_clip(chord_wav)
    assert clip.sr_harmonic == 22050
    assert clip.sr_speech == 16000
    assert len(clip.y_harmonic) > len(clip.y_speech)


def test_silence_at_the_edges_is_trimmed(silence_wav):
    clip = ingest.load_clip(silence_wav)
    assert clip.duration < 2.0, "a 5 s file, of which 4 s is silence at the edges"


def test_normalisation_levels_the_loudness(tmp_path):
    """Without this, energy thresholds are not comparable between sources."""
    import soundfile as sf
    t = np.linspace(0, 3, 22050 * 3, endpoint=False)
    quiet = 0.01 * np.sin(2 * np.pi * 440 * t)
    loud = 0.9 * np.sin(2 * np.pi * 440 * t)
    sf.write(tmp_path / "quiet.wav", quiet, 22050)
    sf.write(tmp_path / "loud.wav", loud, 22050)
    a = ingest.load_clip(str(tmp_path / "quiet.wav"))
    b = ingest.load_clip(str(tmp_path / "loud.wav"))
    assert abs(np.abs(a.y_harmonic).mean() - np.abs(b.y_harmonic).mean()) < 0.05


def test_sha_is_deterministic_and_differs_between_sources(chord_wav, noise_wav):
    assert ingest.load_clip(chord_wav).sha256 == ingest.load_clip(chord_wav).sha256
    assert ingest.load_clip(chord_wav).sha256 != ingest.load_clip(noise_wav).sha256


def test_long_material_is_trimmed_to_the_limit(tmp_path):
    import soundfile as sf
    t = np.linspace(0, 300, 22050 * 300, endpoint=False)
    sf.write(tmp_path / "long.wav", 0.5 * np.sin(2 * np.pi * 440 * t), 22050)
    clip = ingest.load_clip(str(tmp_path / "long.wav"))
    assert clip.duration <= 180.0
```

- [ ] **Step 2:** `./scripts/rt tests/test_ingest.py -v` - expected FAIL (module missing)
- [ ] **Step 3:** Implement `ingest.py`. `Clip` as a `@dataclass`. URL downloading through **the `yt_dlp` library imported in Python**, never through a CLI subprocess (`format="bestaudio/best"`, `download_ranges` up to 180 s, `ffmpeg_location` from the `ORIGIN_FFMPEG` variable). Decoding through `ffmpeg`, both paths from a single source file. Normalization to -23 LUFS. Silence trimming through `librosa.effects.trim(top_db=30)`. SHA-256 computed **after** normalization, on `y_harmonic.tobytes()`. Material longer than 180 s is cut down to the window with the highest RMS energy.
- [ ] **Step 4:** `./scripts/rt tests/test_ingest.py -v` - PASS
- [ ] **Step 5:** `git add src/origin/ingest.py tests/test_ingest.py && git commit -m "feat: audio ingest with normalization and windowing"`

---

### Task 4: Candidate manifest

**Files:** Create `src/origin/candidates.py`, `tests/test_candidates.py`, `data/candidates/demo_01.json`

**Interfaces:**
- Consumes: `contracts.Candidate`, `contracts.CandidateSet`
- Produces: `candidates.load_set(set_id: str) -> CandidateSet`; `candidates.validate_set(path: str) -> list[str]` returning a list of errors

`data/candidates/demo_01.json` starts out containing **eight** entries covering the five scenarios from section 14. The `audio_path` fields point at `data/audio/`, which is outside git. T9 fills the entries in.

- [ ] **Step 1: Tests**

```python
# tests/test_candidates.py
import json
import pytest
from origin import candidates


def test_loads_the_demo_set():
    candidate_set = candidates.load_set("demo_01")
    assert len(candidate_set.candidates) >= 8
    assert candidate_set.set_id == "demo_01"


def test_identifiers_are_unique():
    candidate_set = candidates.load_set("demo_01")
    ids = [c.id for c in candidate_set.candidates]
    assert len(ids) == len(set(ids))


def test_validator_rejects_published_source_youtube(tmp_path):
    """Global Constraint 8."""
    bad = {"set_id": "x", "candidates": [{
        "id": "c1", "name": "N", "artist": "A",
        "source_url": "https://youtube.com/watch?v=q",
        "audio_path": "data/audio/c1.wav",
        "published": "2020-01-01", "published_source": "youtube",
        "license": "unknown", "instrumental": False}]}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    errors = candidates.validate_set(str(p))
    assert any("youtube" in e for e in errors)


def test_validator_requires_a_date_source_when_a_date_is_given(tmp_path):
    bad = {"set_id": "x", "candidates": [{
        "id": "c1", "name": "N", "artist": "A",
        "source_url": "https://example.com/a",
        "audio_path": "data/audio/c1.wav",
        "published": "2020-01-01", "published_source": None,
        "license": "unknown", "instrumental": False}]}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    assert candidates.validate_set(str(p))


def test_the_demo_set_passes_validation():
    assert candidates.validate_set("data/candidates/demo_01.json") == []


def test_the_demo_set_has_an_instrumental_candidate():
    """Section 7.3: needed to check the routing of detector D."""
    candidate_set = candidates.load_set("demo_01")
    assert any(c.instrumental for c in candidate_set.candidates)


def test_the_demo_set_has_a_candidate_under_an_open_licence():
    """Scenario 6 from section 14."""
    candidate_set = candidates.load_set("demo_01")
    assert any(c.license.startswith("cc") for c in candidate_set.candidates)
```

- [ ] **Step 2:** `./scripts/rt tests/test_candidates.py -v` - FAIL
- [ ] **Step 3:** Implement `candidates.py` together with `data/candidates/demo_01.json` holding eight entries. Choose works from the SHS catalog (`Projects/dataset`), using the `shs_performance_id` from the export. **Enter the dates by hand** from knowledge of the release, `published_source: "manual"`. At least one instrumental entry and at least one under a CC license.
- [ ] **Step 4:** `./scripts/rt tests/test_candidates.py -v` - PASS
- [ ] **Step 5:** `git add src/origin/candidates.py tests/test_candidates.py data/candidates/demo_01.json && git commit -m "feat: candidate manifest with date source validation"`

---

### Task 5: API, job store and SSE stream

**Files:** Create `src/origin/api/__init__.py`, `app.py`, `jobs.py`, `routes.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `contracts.*`, `candidates.load_set`
- Produces: `app` (FastAPI), `jobs.JobStore` with the methods `create(url, candidate_set) -> str`, `emit(job_id, event: StreamEvent)`, `get_result(job_id) -> AnalyzeResult`, `stream(job_id) -> AsyncIterator[str]`

**Mock mode:** with `ORIGIN_MOCK=1` the endpoints return a complete, contract-conformant response without computing. The front end from T6 and T18-T21 works exclusively in this mode until the engine stands up.

- [ ] **Step 1: Tests**

```python
# tests/test_api.py
import json
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORIGIN_MOCK", "1")
    from origin.api.app import app
    return TestClient(app)


def test_analyze_returns_a_job_id(client):
    r = client.post("/api/analyze", json={"url": "https://example.com/a",
                                          "candidate_set": "demo_01"})
    assert r.status_code == 200
    assert "job_id" in r.json()


def test_the_result_starts_out_partial(client):
    job = client.post("/api/analyze", json={"url": "https://example.com/a",
                                            "candidate_set": "demo_01"}).json()["job_id"]
    r = client.get(f"/api/jobs/{job}/result").json()
    assert r["status"] in ("partial", "complete")
    assert set(r["completed_levels"]) <= {1, 2}


def test_the_verdict_appears_twice(client):
    """Section 12: partial after level 1, final after level 2."""
    job = client.post("/api/analyze", json={"url": "https://example.com/a",
                                            "candidate_set": "demo_01"}).json()["job_id"]
    with client.stream("GET", f"/api/jobs/{job}/stream") as r:
        verdicts = [json.loads(l[6:])
                    for l in r.iter_lines()
                    if l.startswith("data: ") and json.loads(l[6:])["stage"] == "verdict"]
    assert [v["status"] for v in verdicts] == ["partial", "final"]


def test_every_event_carries_a_level(client):
    job = client.post("/api/analyze", json={"url": "https://example.com/a",
                                            "candidate_set": "demo_01"}).json()["job_id"]
    with client.stream("GET", f"/api/jobs/{job}/stream") as r:
        events = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ")]
    assert all(e["level"] in (1, 2) for e in events)


def test_a_gated_event_carries_the_reason_and_the_next_step(client):
    """Section 12: gated is content, not an error - screen E2 shows it."""
    job = client.post("/api/analyze", json={"url": "https://example.com/a",
                                            "candidate_set": "demo_01"}).json()["job_id"]
    with client.stream("GET", f"/api/jobs/{job}/stream") as r:
        events = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ")]
    gated = [e for e in events if e["status"] == "gated"]
    assert gated and "reason" in gated[0]["detail"]


def test_an_unknown_job_gives_a_404(client):
    assert client.get("/api/jobs/no-such-job/result").status_code == 404


def test_an_unknown_candidate_set_gives_a_404(client):
    r = client.post("/api/analyze", json={"url": "https://example.com/a",
                                          "candidate_set": "no_such_set"})
    assert r.status_code == 404
```

- [ ] **Step 2:** `./scripts/rt tests/test_api.py -v` - FAIL
- [ ] **Step 3:** Implement the four endpoints from section 12. An in-memory `JobStore`, an `asyncio.Queue` for the events. `POST /api/explain` in mock mode returns fixed text - wiring in a language model is out of scope for this plan.
- [ ] **Step 4:** `./scripts/rt tests/test_api.py -v` - PASS
- [ ] **Step 5:** `git add src/origin/api tests/test_api.py && git commit -m "feat: API, job store and SSE stream with a two-stage verdict"`

---

### Task 6: Front end - scaffold and visual system

**Files:** Create `web/package.json`, `web/tailwind.config.ts`, `web/lib/theme.ts`, `web/lib/contracts.ts`, `web/lib/api.ts`, `web/app/layout.tsx`, `web/app/page.tsx`, `web/components/Footer.tsx`, `web/components/Badge.tsx`, `web/tests/theme.test.ts`, `scripts/rt-web`

`web/package.json` must include `vitest`, `@testing-library/react`, `@testing-library/jest-dom` and `jsdom` - tasks T18-T21 write component tests and without these none of them will start.

**Interfaces:**
- Consumes: the contracts from section 12 (mirrored TS types, **manually kept in sync** with `contracts.py`)
- Produces: `lib/api.ts` with `analyze(url, set)`, `streamJob(jobId, onEvent)`, `getResult(jobId)`; `components/Footer.tsx`; `components/Badge.tsx` mapping an evidence class onto a badge

Tokens from section 13.1, verbatim:

```typescript
// web/lib/theme.ts
export const theme = {
  bg: "#0B0C0A",          // near-black with an olive cast
  surface: "#141613",     // cards slightly lighter than the background
  text: "#FFFFFF",
  muted: "#8A8F85",
  accent: "#C8FF3D",      // acid lime - EXCLUSIVELY as a signal
} as const;

/** Evidence classes -> label in the UI. Section 13.2 screen E3. */
export const VERDICT_LABELS = {
  EXACT: "IDENTICAL RECORDING",
  MODIFIED: "MODIFIED RECORDING",
  VERSION: "THE SAME WORK",
  EXCERPT_PHONOGRAM: "RECORDING FRAGMENT",
  EXCERPT_WORK: "COMPOSITION FRAGMENT",
  LYRICS: "LYRICAL OVERLAP",
  COMMON: "COMMON ELEMENT",
  NONE: "NO MATCH",
} as const;

/** Lime only for the classes that are a signal. Global Constraint 11. */
export const ACCENT_CLASSES = ["EXACT", "EXCERPT_PHONOGRAM"] as const;
```

- [ ] **Step 1: Tests**

```typescript
// web/tests/theme.test.ts
import { describe, it, expect } from "vitest";
import { VERDICT_LABELS, ACCENT_CLASSES, theme } from "../lib/theme";
import { VERDICT_CLASSES } from "../lib/contracts";

describe("visual system", () => {
  it("every evidence class has a label", () => {
    for (const k of VERDICT_CLASSES) {
      expect(VERDICT_LABELS[k]).toBeTruthy();
    }
  });

  it("lime is a signal, not decoration", () => {
    // Global Constraint 11: the accent only for classes that are a signal
    expect(ACCENT_CLASSES.length).toBeLessThan(VERDICT_CLASSES.length / 2);
    expect(ACCENT_CLASSES).not.toContain("NONE");
    expect(ACCENT_CLASSES).not.toContain("COMMON");
  });

  it("the labels are in all caps", () => {
    for (const v of Object.values(VERDICT_LABELS)) {
      expect(v).toBe(v.toUpperCase());
    }
  });

  it("the background is darker than the card surfaces", () => {
    const brightness = (hex: string) =>
      parseInt(hex.slice(1, 3), 16) + parseInt(hex.slice(3, 5), 16) + parseInt(hex.slice(5, 7), 16);
    expect(brightness(theme.bg)).toBeLessThan(brightness(theme.surface));
  });
});
```

- [ ] **Step 2:** `./scripts/rt-web web/tests/theme.test.ts` - FAIL. Add `scripts/rt-web` analogous to `scripts/rt`, running `vitest run` on Hetzner.
- [ ] **Step 3:** Implement the scaffold. Next.js with the App Router, Tailwind configured on the tokens from `theme.ts`. `Footer.tsx` renders the breadcrumb `GRAI ORIGIN / CASE 03 / <screen>`. Technical values get the `font-mono` class. The page background carries the motif of a large circle running out of frame.
- [ ] **Step 4:** `./scripts/rt-web` - PASS
- [ ] **Step 5:** `git add web scripts/rt-web && git commit -m "feat: front-end scaffold and the visual system from the brief"`

---
## WAVE 3 - in parallel, three tasks

### Task 7: Detector A - acoustic fingerprint

**Files:** Create `src/origin/detectors/__init__.py`, `base.py`, `registry.py`, `fingerprint.py`, `tests/test_fingerprint.py`

**Interfaces:**
- Consumes: `ingest.Clip`, `contracts.FingerprintResult`, `contracts.DetectorEnvelope`
- Produces:
  - `base.Detector` - protocol: `run(clip: Clip, candidates: list[Candidate]) -> DetectorEnvelope`
  - `registry.DETECTORS: dict[str, Detector]` - **an empty dictionary plus a `register(name, detector)` function**

**Ruling preflight (T7/T8 conflict):** detectors **do not register themselves**. Each detector
module exposes only its class, and wiring it into the registry is done by T22 when building the
pipeline. Otherwise T8, T14 and T15 would have to edit `registry.py`, which belongs to T7, and the
parallel waves would collide on one file.
  - `fingerprint.build_index(clip: Clip, candidate_id: str) -> dict[int, list[tuple[str, float]]]`
  - `fingerprint.match(clip: Clip, index) -> dict[str, FingerprintResult]` (the key is `candidate_id`; candidates below the noise floor are skipped, so the key may be absent)
  - `fingerprint.match_transformed(clip: Clip, index) -> dict[str, FingerprintResult]` (the grid of 143 variants, called only explicitly)
  - `fingerprint.FingerprintDetector` with the attribute `level = 1`

Algorithm: section 7.1. Parameters verbatim: STFT window 2048 hop 512, 30-50 peaks per second, target zone of 5 peaks within a 2 s window. The transformation grid of +/-6 semitones in steps of 1 and 0.90-1.15 in steps of 2.5% runs **only** when the match without a transformation failed.

- [ ] **Step 1: Tests**

```python
# tests/test_fingerprint.py
import numpy as np
import pytest
from origin import ingest
from origin.detectors import fingerprint as fp


def test_a_clip_matches_itself(chord_wav):
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="self")
    result = fp.match(clip, idx)["self"]
    assert result.peak_ratio > 0.9


def test_noise_does_not_match_music(chord_wav, noise_wav):
    idx = fp.build_index(ingest.load_clip(chord_wav), candidate_id="music")
    result = fp.match(ingest.load_clip(noise_wav), idx).get("music")
    assert result is None or result.peak_ratio < 0.25


def test_the_offset_histogram_gives_a_sharp_peak_on_a_hit(chord_wav):
    """Section 7.1: a true match has many hashes with THE SAME offset difference."""
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="self")
    result = fp.match(clip, idx)["self"]
    assert abs(result.offset) < 0.5


def test_a_trimmed_fragment_gives_a_non_zero_offset(chord_wav):
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="full")
    fragment = ingest.Clip.from_array(clip.y_harmonic[22050 * 2:], clip.sr_harmonic)
    result = fp.match(fragment, idx)["full"]
    assert result.offset == pytest.approx(2.0, abs=0.5)


def test_span_length_is_computed_from_query_span(chord_wav):
    clip = ingest.load_clip(chord_wav)
    idx = fp.build_index(clip, candidate_id="self")
    result = fp.match(clip, idx)["self"]
    assert result.span_length == pytest.approx(
        result.query_span[1] - result.query_span[0])


def test_a_repeated_loop_gives_repetitions_of_at_least_two(tmp_path):
    """Section 9.1 rule 3: EXCERPT requires repetitions >= 2."""
    import soundfile as sf
    from tests.conftest import chord
    loop = chord([261.6, 329.6, 392.0], 2.0)
    track = np.concatenate([np.zeros(22050 * 3), loop, np.zeros(22050 * 3), loop])
    sf.write(tmp_path / "loop.wav", loop, 22050)
    sf.write(tmp_path / "track.wav", track, 22050)
    idx = fp.build_index(ingest.load_clip(str(tmp_path / "loop.wav")), candidate_id="sample")
    result = fp.match(ingest.load_clip(str(tmp_path / "track.wav")), idx)["sample"]
    assert result.repetitions >= 2


def test_the_transformation_grid_does_not_run_without_being_called(chord_wav, shifted_wav):
    """Section 7.1: the 143 variants are expensive and run only on demand."""
    idx = fp.build_index(ingest.load_clip(chord_wav), candidate_id="original")
    without_transform = fp.match(ingest.load_clip(shifted_wav), idx).get("original")
    assert without_transform is None or without_transform.transform is None


def test_the_transformation_grid_finds_the_speedup(chord_wav, shifted_wav):
    idx = fp.build_index(ingest.load_clip(chord_wav), candidate_id="original")
    result = fp.match_transformed(ingest.load_clip(shifted_wav), idx)["original"]
    assert result.transform is not None
    assert result.transform["tempo_ratio"] == pytest.approx(1.06, abs=0.03)


def test_the_detector_returns_an_envelope_with_a_status(chord_wav):
    clip = ingest.load_clip(chord_wav)
    env = fp.FingerprintDetector().run(clip, candidates=[])
    assert env.detector == "fingerprint"
    assert env.status in ("ok", "failed")
```

- [ ] **Step 2:** `./scripts/rt tests/test_fingerprint.py -v` - FAIL
- [ ] **Step 3:** Implement it. `base.py` carries the detector protocol and a helper that builds the envelope. `registry.py` is a simple dictionary that subsequent detectors are added to. Peaks through `scipy.ndimage.maximum_filter`. The hash as a 32-bit number from `(f1, f2, dt)`. The candidate representation is written to disk in `data/cache/` in `npz` format.
- [ ] **Step 4:** `./scripts/rt tests/test_fingerprint.py -v` - PASS
- [ ] **Step 5:** `git add src/origin/detectors tests/test_fingerprint.py && git commit -m "feat: detector A, acoustic fingerprint with an offset histogram"`

---

### Task 8: Detector B - harmonic similarity

**Files:** Create `src/origin/detectors/harmonic.py`, `tests/test_harmonic.py`

**Interfaces:**
- Consumes: `ingest.Clip`, `contracts.HarmonicResult`
- Produces: `harmonic.chroma(clip) -> np.ndarray`; `harmonic.global_descriptor(chroma) -> np.ndarray` (256 dimensions); `harmonic.qmax(chroma_a, chroma_b) -> HarmonicResult`; `harmonic.chord_sequence(chroma) -> list[str]`; `harmonic.HarmonicDetector` with `level = 1`

Algorithm: section 7.2. CQT 12 bins per octave from C1, 6 octaves. All 12 rotations, the maximum. Binarization by the 10th percentile. Serra Qmax along diagonals.

- [ ] **Step 1: Tests**

```python
# tests/test_harmonic.py
import numpy as np
import pytest
from origin import ingest
from origin.detectors import harmonic as h


def test_chroma_has_twelve_classes(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    assert c.shape[0] == 12


def test_frames_are_l2_normalised(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    norms = np.linalg.norm(c, axis=0)
    assert np.allclose(norms[norms > 0], 1.0, atol=0.01)


def test_the_same_material_gives_a_high_qmax(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    assert h.qmax(c, c).qmax_score > 0.9


def test_noise_gives_a_low_qmax(chord_wav, noise_wav):
    a = h.chroma(ingest.load_clip(chord_wav))
    b = h.chroma(ingest.load_clip(noise_wav))
    assert h.qmax(a, b).qmax_score < 0.4


def test_transposition_is_detected_without_key_detection(chord_wav):
    """Section 7.2: we do not transpose to a detected key, because detection is unreliable."""
    c = h.chroma(ingest.load_clip(chord_wav))
    shifted = np.roll(c, 2, axis=0)
    result = h.qmax(c, shifted)
    assert result.qmax_score > 0.9
    assert result.transposition == 2


def test_coverage_tells_a_cover_apart_from_a_fragment(chord_wav):
    """Section 7.2: coverage is exactly what separates VERSION from EXCERPT."""
    c = h.chroma(ingest.load_clip(chord_wav))
    whole = h.qmax(c, c)
    fragment = h.qmax(c[:, : c.shape[1] // 4], c)
    assert whole.coverage > fragment.coverage


def test_the_global_descriptor_has_256_dimensions(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    assert h.global_descriptor(c).shape == (256,)


def test_the_descriptor_filters_more_cheaply_than_the_matrix(chord_wav, noise_wav):
    a = h.global_descriptor(h.chroma(ingest.load_clip(chord_wav)))
    b = h.global_descriptor(h.chroma(ingest.load_clip(noise_wav)))
    similarity = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    assert similarity < 0.8


def test_the_chord_sequence_feeds_the_idf_filter(chord_wav):
    """Section 8: the commonality filter computes the IDF of chord sequences from detector B."""
    seq = h.chord_sequence(h.chroma(ingest.load_clip(chord_wav)))
    assert len(seq) >= 4
    assert all(isinstance(x, str) for x in seq)


def test_the_alignment_path_is_non_empty_on_a_hit(chord_wav):
    c = h.chroma(ingest.load_clip(chord_wav))
    assert len(h.qmax(c, c).alignment_path) > 0
```

- [ ] **Step 2:** `./scripts/rt tests/test_harmonic.py -v` - FAIL
- [ ] **Step 3:** Implement it. CQT through `librosa.cqt`, chroma through `librosa.feature.chroma_cqt`, smoothing with `scipy.ndimage.median_filter`, aggregation to 2 Hz. The cross-similarity matrix computed only for the top 20 from the descriptor. `alignment_path` returned in a form suitable for drawing on the heatmap in E4.
- [ ] **Step 4:** `./scripts/rt tests/test_harmonic.py -v` - PASS
- [ ] **Step 5:** `git add src/origin/detectors/harmonic.py tests/test_harmonic.py && git commit -m "feat: detector B, harmonic similarity with Qmax alignment"`

---

### Task 9: Audio downloading with an overage

**Files:** Create `scripts/fetch_audio.py`, `tests/test_fetch_audio.py`

**Interfaces:**
- Consumes: `contracts.Candidate`
- Produces: `fetch_audio.fetch_many(items: list[dict], target: int, directory: str) -> FetchReport`; `FetchReport(successful: list[str], failed: list[tuple[str, str]], attempted: int)`

Section 5.7: **a 25% overage**, finishing once the target number of successes is collected, an error log with a reason per entry.

- [ ] **Step 1: Tests**

```python
# tests/test_fetch_audio.py
import pytest
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
    assert len(calls) == 10, "must not download more than needed"


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
```

- [ ] **Step 2:** `./scripts/rt tests/test_fetch_audio.py -v` - FAIL
- [ ] **Step 3:** Implement it. `_fetch_one` calls `yt-dlp` with a time limit. Concurrency through `concurrent.futures.ThreadPoolExecutor` with `max_workers` from `config.CPU_QUOTA`. Error log to `data/cache/fetch_errors.jsonl`.
- [ ] **Step 4:** `./scripts/rt tests/test_fetch_audio.py -v` - PASS
- [ ] **Step 5:** Download audio for the eight candidates from `data/candidates/demo_01.json`. Run: `python scripts/fetch_audio.py --set demo_01`. The result lands in `data/audio/`, outside git.
- [ ] **Step 6:** `git add scripts/fetch_audio.py tests/test_fetch_audio.py && git commit -m "feat: audio downloading with an overage for dead links"`

---

## WAVE 4 - in parallel, two tasks

### Task 10: Shortlisting down to the shortlist

**Files:** Create `src/origin/shortlist.py`, `tests/test_shortlist.py`

**Interfaces:**
- Consumes: `harmonic.global_descriptor`, `contracts.Candidate`
- Produces: `shortlist.select(clip, candidates, limit=config.SHORTLIST_SIZE) -> list[Candidate]`

- [ ] **Step 1: Tests**

```python
# tests/test_shortlist.py
import pytest
from origin import shortlist


def test_never_returns_more_than_the_limit(fake_candidates_40):
    assert len(shortlist.select(None, fake_candidates_40, limit=20)) <= 20


def test_keeps_descending_similarity_order(fake_candidates_40):
    result = shortlist.select(None, fake_candidates_40, limit=10)
    scores = [shortlist.score(None, c) for c in result]
    assert scores == sorted(scores, reverse=True)


def test_a_set_smaller_than_the_limit_passes_whole(fake_candidates_5):
    assert len(shortlist.select(None, fake_candidates_5, limit=20)) == 5


def test_an_empty_set_does_not_blow_up():
    assert shortlist.select(None, [], limit=20) == []
```

Add the `fake_candidates_40` and `fake_candidates_5` fixtures to `tests/conftest.py` - that is the only change to somebody else's file in this task, append at the end, do not modify the existing ones.

- [ ] **Step 2:** `./scripts/rt tests/test_shortlist.py -v` - FAIL
- [ ] **Step 3:** Implement it. Cosine similarity of the global descriptors, sorting in descending order, truncation to the limit.
- [ ] **Step 4:** `./scripts/rt tests/test_shortlist.py -v` - PASS
- [ ] **Step 5:** `git add src/origin/shortlist.py tests/test_shortlist.py tests/conftest.py && git commit -m "feat: candidate shortlisting by global descriptor"`

---

### Task 11: IDF corpus and commonality filter

This is the task standing behind demo case 5, that is behind the only thing that sets this product apart.

**Files:** Create `src/origin/commonality.py`, `scripts/build_corpus.py`, `tests/test_commonality.py`

**Interfaces:**
- Consumes: `harmonic.chord_sequence`
- Produces:
  - `commonality.Corpus.load(path) -> Corpus`, `Corpus.from_documents(documents: list[list[tuple]]) -> Corpus`, `Corpus.idf(pattern: tuple) -> float`, `Corpus.document_frequency(pattern) -> int`, `Corpus.size: int`
  - `commonality.mean_idf(patterns: list[tuple], corpus: Corpus) -> float`
  - `commonality.should_degrade(verdict_class: str, mean_idf: float, corpus: Corpus) -> bool`

- [ ] **Step 1: Tests**

```python
# tests/test_commonality.py
import pytest
from origin import commonality as cm


@pytest.fixture
def corpus(tmp_path):
    """The I-V-vi-IV progression in 60 tracks out of 100, a rare motif in one."""
    documents = []
    for i in range(60):
        documents.append([("C", "G", "Am", "F")])
    for i in range(39):
        documents.append([("D", "A", "Bm", "G")])
    documents.append([("C#", "F#", "B", "Eb")])
    return cm.Corpus.from_documents(documents)


def test_a_common_progression_has_a_low_idf(corpus):
    assert corpus.idf(("C", "G", "Am", "F")) < 1.0


def test_a_rare_motif_has_a_high_idf(corpus):
    assert corpus.idf(("C#", "F#", "B", "Eb")) > 4.0


def test_an_absent_pattern_does_not_blow_up(corpus):
    assert corpus.idf(("X", "Y", "Z")) > 0


def test_degradation_applies_to_version(corpus):
    """Global Constraint 5."""
    assert cm.should_degrade("VERSION", mean_idf=0.4, corpus=corpus) is True


def test_degradation_applies_to_lyrics_and_excerpt_work(corpus):
    assert cm.should_degrade("LYRICS", 0.4, corpus) is True
    assert cm.should_degrade("EXCERPT_WORK", 0.4, corpus) is True


def test_degradation_does_NOT_apply_to_exact(corpus):
    """Global Constraint 5: a reupload of a track on a commonplace progression is still a reupload."""
    assert cm.should_degrade("EXACT", mean_idf=0.1, corpus=corpus) is False


def test_degradation_does_NOT_apply_to_modified_or_excerpt_phonogram(corpus):
    assert cm.should_degrade("MODIFIED", 0.1, corpus) is False
    assert cm.should_degrade("EXCERPT_PHONOGRAM", 0.1, corpus) is False


def test_a_high_idf_degrades_nothing(corpus):
    assert cm.should_degrade("VERSION", mean_idf=9.0, corpus=corpus) is False


def test_the_corpus_knows_its_size(corpus):
    assert corpus.size == 100


def test_the_document_frequency_for_the_sentence_in_the_ui(corpus):
    """Section 8.2: the UI says 'this motif occurs in N tracks', it does not give the IDF number."""
    assert corpus.document_frequency(("C", "G", "Am", "F")) == 60
```

- [ ] **Step 2:** `./scripts/rt tests/test_commonality.py -v` - FAIL
- [ ] **Step 3:** Implement it. `idf(w) = log(N / df(w))`, with `df = 1` for absent patterns. The degradation threshold: patterns occurring in more than `COMMON_IDF_PERCENTILE` of the corpus. `should_degrade` checks the class membership of the set `{VERSION, LYRICS, EXCERPT_WORK}` **before** comparing against the threshold.
- [ ] **Step 4:** Implement `scripts/build_corpus.py`: stratified sampling by language and group size from the SHS export (section 5.6), downloading the audio through `fetch_audio.fetch_many`, computing chroma and chord sequences, writing the corpus to `data/corpus/idf.json`. Target: 3,000 works.
- [ ] **Step 5:** `./scripts/rt tests/test_commonality.py -v` - PASS
- [ ] **Step 6:** `git add src/origin/commonality.py scripts/build_corpus.py tests/test_commonality.py && git commit -m "feat: IDF corpus and commonality filter limited to the work layer"`

---
## WAVE 5 - sequential

### Task 12: Fusion and decision tree

The heart of the system. The rule order is binding and the tests guard precisely that.

**Files:** Create `src/origin/fusion.py`, `tests/test_fusion.py`

**Interfaces:**
- Consumes: all the `contracts.*Result`, `config.THRESHOLDS`, `commonality.should_degrade`
- Produces:
  - `fusion.decide(fp: FingerprintResult | None, harm: HarmonicResult | None, mel: MelodicResult | None, lyr: LyricsResult | None, mean_idf: float, corpus) -> Verdict`
  - `Verdict(verdict_class: str, verdict_layer: str, reasons: list[str])` - positional constructor, in this order
  - `fusion.RankItem(candidate_id: str, probability: float, published: str | None)`
  - `fusion.rank(items: list[RankItem]) -> list[RankItem]` - sorting in descending order by `probability`; on a tie (difference < 0.02) the earlier `published` wins, and `None` does not take part in the chronology rule

The tree: section 9.1, seven rules, the first one satisfied wins, `COMMON` degradation **after** the class is chosen.

- [ ] **Step 1: Tests**

```python
# tests/test_fusion.py
import pytest
from origin import fusion
from origin.contracts import FingerprintResult, HarmonicResult, LyricsResult, MelodicResult


def _fp(**kw):
    d = dict(candidate_id="c1", peak_ratio=0.0, query_span=(0.0, 0.0), repetitions=0)
    d.update(kw)
    return FingerprintResult(**d)


def _h(**kw):
    d = dict(candidate_id="c1", qmax_score=0.0, coverage=0.0)
    d.update(kw)
    return HarmonicResult(**d)


class FakeCorpus:
    size = 1000
    def idf(self, w): return 9.0
    def document_frequency(self, w): return 1


GENEROUS = FakeCorpus()


def test_rule_1_exact():
    v = fusion.decide(_fp(peak_ratio=0.8, query_span=(0.0, 40.0)), _h(), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "EXACT"
    assert v.verdict_layer == "phonogram"


def test_rule_2_modified():
    v = fusion.decide(_fp(peak_ratio=0.55, query_span=(0.0, 40.0),
                          transform={"tempo_ratio": 1.06, "semitones": 1}),
                      _h(qmax_score=0.7), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "MODIFIED"


def test_rule_3_excerpt_phonogram():
    v = fusion.decide(_fp(peak_ratio=0.5, query_span=(2.0, 10.0), repetitions=3),
                      _h(), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "EXCERPT_PHONOGRAM"
    assert v.verdict_layer == "phonogram"


def test_rule_4_version():
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8),
                      None, LyricsResult(candidate_id="c1", semantic_sim=0.85), 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"
    assert v.verdict_layer == "work"


def test_version_works_when_the_lyrics_detector_is_not_applicable():
    """Global Constraint 4: 24.9% of the catalog is instrumental, missing lyrics must not block."""
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8), None,
                      LyricsResult(candidate_id="c1", status="not_applicable",
                                   reason="instrumental"), 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"


def test_version_works_when_the_gate_rejected_the_transcript():
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8), None,
                      LyricsResult(candidate_id="c1", status="gated",
                                   reason="asr_confidence"), 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"


def test_version_works_when_there_was_no_lyrics_detector_at_all():
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8),
                      None, None, 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"


def test_the_gap_between_025_and_040_does_not_lose_the_cover():
    """Section 9.1: at a threshold of 0.25 this case fell through to NONE."""
    v = fusion.decide(_fp(peak_ratio=0.32, query_span=(0.0, 40.0)),
                      _h(qmax_score=0.7, coverage=0.8), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "VERSION"


def test_rule_5_excerpt_work():
    v = fusion.decide(_fp(peak_ratio=0.05), _h(qmax_score=0.3, coverage=0.2),
                      MelodicResult(candidate_id="c1", longest_common_run=11),
                      None, 9.0, GENEROUS)
    assert v.verdict_class == "EXCERPT_WORK"
    assert v.verdict_layer == "work"


def test_rule_6_lyrics():
    v = fusion.decide(_fp(peak_ratio=0.05), _h(qmax_score=0.2), None,
                      LyricsResult(candidate_id="c1", jaccard=0.7, semantic_sim=0.8),
                      9.0, GENEROUS)
    assert v.verdict_class == "LYRICS"


def test_rule_7_none():
    v = fusion.decide(_fp(), _h(), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "NONE"


def test_the_rule_order_makes_exact_beat_version():
    """The first rule satisfied wins - section 9.1."""
    v = fusion.decide(_fp(peak_ratio=0.9, query_span=(0.0, 60.0)),
                      _h(qmax_score=0.9, coverage=0.9), None, None, 9.0, GENEROUS)
    assert v.verdict_class == "EXACT"


def test_degradation_turns_version_into_common():
    class Poor(FakeCorpus):
        def idf(self, w): return 0.1
    v = fusion.decide(_fp(peak_ratio=0.1), _h(qmax_score=0.7, coverage=0.8),
                      None, None, mean_idf=0.1, corpus=Poor())
    assert v.verdict_class == "COMMON"


def test_degradation_does_NOT_touch_exact():
    """Global Constraint 5 - this is demo case 1 against demo case 5."""
    class Poor(FakeCorpus):
        def idf(self, w): return 0.1
    v = fusion.decide(_fp(peak_ratio=0.9, query_span=(0.0, 60.0)), _h(),
                      None, None, mean_idf=0.1, corpus=Poor())
    assert v.verdict_class == "EXACT"


def test_the_verdict_carries_a_justification_for_every_satisfied_condition():
    v = fusion.decide(_fp(peak_ratio=0.8, query_span=(0.0, 40.0)), _h(), None, None, 9.0, GENEROUS)
    assert v.reasons, "screen E3 shows one sentence of justification"


def test_the_chronology_rule_on_a_tie():
    """Section 9.3: the earlier date wins, but only when there is a date at all."""
    a = fusion.RankItem(candidate_id="a", probability=0.80, published="1975-01-01")
    b = fusion.RankItem(candidate_id="b", probability=0.80, published="1999-01-01")
    assert [x.candidate_id for x in fusion.rank([b, a])] == ["a", "b"]


def test_the_chronology_rule_does_not_apply_without_a_date():
    a = fusion.RankItem(candidate_id="a", probability=0.80, published=None)
    b = fusion.RankItem(candidate_id="b", probability=0.81, published=None)
    assert [x.candidate_id for x in fusion.rank([a, b])] == ["b", "a"]
```

- [ ] **Step 2:** `./scripts/rt tests/test_fusion.py -v` - FAIL
- [ ] **Step 3:** Implement the tree exactly in the order from section 9.1. Every rule appends an English sentence to `reasons`. Degradation through `commonality.should_degrade` **after** the class is chosen, never before.
- [ ] **Step 4:** `./scripts/rt tests/test_fusion.py -v` - PASS
- [ ] **Step 5:** `git add src/origin/fusion.py tests/test_fusion.py && git commit -m "feat: fusion and decision tree with a binding rule order"`

---

### Task 13: Legal layer

**Files:** Create `src/origin/legal.py`, `tests/test_legal.py`

**Interfaces:**
- Consumes: `fusion.Verdict`, `contracts.FingerprintResult`, `contracts.Candidate`
- Produces: `legal.assess(verdict, fp, candidate) -> contracts.Legal`

Section 11. `recognizability` from `A.peak_ratio` for the `EXCERPT` classes. `modification` from `transform`.

- [ ] **Step 1: Tests**

```python
# tests/test_legal.py
import pytest
from origin import legal
from origin.contracts import Candidate, FingerprintResult
from origin.fusion import Verdict


def _cand(**kw):
    d = dict(id="c1", name="N", artist="A", source_url="https://example.com/a",
             audio_path="data/audio/c1.wav", license="all_rights_reserved",
             instrumental=False)
    d.update(kw)
    return Candidate(**d)


def test_exact_touches_the_phonogram_layer():
    l = legal.assess(Verdict("EXACT", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.9), _cand())
    assert "phonogram" in l.rights_layer


def test_version_signals_the_performance_layer():
    """Section 11.1: an artistic performance is a separate layer."""
    l = legal.assess(Verdict("VERSION", "work", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.1), _cand())
    assert "performance" in l.rights_layer


def test_common_raises_no_flag():
    l = legal.assess(Verdict("COMMON", "work", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.1), _cand())
    assert l.risk_flags == []


def test_a_recognisable_excerpt_raises_the_high_risk_flag():
    l = legal.assess(Verdict("EXCERPT_PHONOGRAM", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.85), _cand())
    assert "recognizable_excerpt" in l.risk_flags
    assert l.recognizability > 0.8


def test_strong_modification_with_recognisability_gives_the_pastiche_flag():
    """Section 11.2: a borderline situation is to be marked as borderline."""
    l = legal.assess(Verdict("EXCERPT_PHONOGRAM", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.7,
                                       transform={"tempo_ratio": 1.3, "semitones": 5}),
                     _cand())
    assert "possible_pastiche" in l.risk_flags
    assert l.modification > 0.3


def test_an_open_licence_generates_an_attribution_and_removes_the_risk():
    l = legal.assess(Verdict("EXACT", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.9),
                     _cand(license="cc-by-4.0"))
    assert l.required_attribution
    assert "recognizable_excerpt" not in l.risk_flags


def test_an_unknown_licence_is_missing_information_not_an_absence_of_restrictions():
    """Section 11.3 and limitation 9."""
    l = legal.assess(Verdict("EXACT", "phonogram", []),
                     FingerprintResult(candidate_id="c1", peak_ratio=0.9),
                     _cand(license="unknown"))
    assert l.license_status == "unknown"
    assert l.required_attribution is None


def test_every_result_carries_the_disclaimer():
    l = legal.assess(Verdict("NONE", "", []),
                     FingerprintResult(candidate_id="c1"), _cand())
    assert "not a legal opinion" in l.disclaimer
```

- [ ] **Step 2:** `./scripts/rt tests/test_legal.py -v` - FAIL
- [ ] **Step 3:** Implement it per the table in section 11.2. `disclaimer` fixed: `"Technical signal, not a legal opinion."`
- [ ] **Step 4:** `./scripts/rt tests/test_legal.py -v` - PASS
- [ ] **Step 5:** `git add src/origin/legal.py tests/test_legal.py && git commit -m "feat: legal layer with recognizability and modification indicators"`

---

## WAVE 6 - in parallel, two tasks

### Task 14: Detector D - lyrics

**Files:** Create `src/origin/detectors/lyrics.py`, `tests/test_lyrics.py`

**Interfaces:**
- Consumes: `ingest.Clip`, `contracts.LyricsResult`, `contracts.Candidate`
- Produces: `lyrics.Transcript(text: str, confidence: float, language: str, language_stable: bool, words: list[tuple[str, float, float]])`; `lyrics.transcribe(clip) -> Transcript`; `lyrics.transcribe_with_gate(clip) -> tuple[Transcript, bool, str | None]`; `lyrics.gate(transcript) -> tuple[bool, str | None]`; `lyrics.compare(a: str, b: str) -> tuple[float, float]`; `lyrics.LyricsDetector` with `level = 2`

Section 7.3. **Whisper before demucs**, separation only after the gate rejects.

- [ ] **Step 1: Tests**

```python
# tests/test_lyrics.py
import pytest
from origin.contracts import Candidate
from origin.detectors import lyrics as ly


def _cand(**kw):
    d = dict(id="c1", name="N", artist="A", source_url="https://example.com/a",
             audio_path="data/audio/c1.wav", license="unknown", instrumental=False)
    d.update(kw)
    return Candidate(**d)


def test_an_instrumental_candidate_gets_not_applicable():
    """Global Constraint 4 and section 7.3 step 1."""
    env = ly.LyricsDetector().run(clip=None, candidates=[_cand(instrumental=True)])
    r = env.results[0]
    assert r.status == "not_applicable"
    assert r.reason == "instrumental"
    assert r.jaccard is None, "not applicable is not a zero"


def test_all_instrumental_finishes_without_transcription(monkeypatch):
    """Section 7.3: this is where the actual saving arises."""
    calls = []
    monkeypatch.setattr(ly, "transcribe", lambda c: calls.append(1))
    env = ly.LyricsDetector().run(clip=object(), candidates=[
        _cand(id="a", instrumental=True), _cand(id="b", instrumental=True)])
    assert env.status == "not_applicable"
    assert calls == [], "must not start whisper when there is nothing to compare against"


def test_the_gate_rejects_low_confidence():
    ok, reason = ly.gate(ly.Transcript(text="la la", confidence=0.2, language="en",
                                       language_stable=True, words=[]))
    assert ok is False
    assert reason == "asr_confidence"


def test_the_gate_rejects_an_unstable_language():
    ok, reason = ly.gate(ly.Transcript(text="x", confidence=0.9, language="en",
                                       language_stable=False, words=[]))
    assert ok is False
    assert reason == "language_unstable"


def test_the_gate_lets_a_good_transcript_through():
    ok, reason = ly.gate(ly.Transcript(text="the quick brown fox jumps over",
                                       confidence=0.9, language="en",
                                       language_stable=True, words=[]))
    assert ok is True and reason is None


def test_separation_starts_only_after_the_gate_rejects(monkeypatch):
    """Section 7.3 step 4 and decision D3: a fixed cost turned into a conditional one."""
    order = []
    monkeypatch.setattr(ly, "_whisper", lambda y, sr: order.append("whisper") or
                        ly.Transcript(text="", confidence=0.1, language="en",
                                      language_stable=True, words=[]))
    monkeypatch.setattr(ly, "_demucs", lambda y, sr: order.append("demucs") or y)
    ly.transcribe_with_gate(clip=_fake_clip())
    assert order[0] == "whisper", "whisper always first, on the full mix"
    assert "demucs" in order


def test_separation_does_not_start_when_the_gate_let_it_through(monkeypatch):
    order = []
    monkeypatch.setattr(ly, "_whisper", lambda y, sr: order.append("whisper") or
                        ly.Transcript(text="the quick brown fox jumps over",
                                      confidence=0.95, language="en",
                                      language_stable=True, words=[]))
    monkeypatch.setattr(ly, "_demucs", lambda y, sr: order.append("demucs") or y)
    ly.transcribe_with_gate(clip=_fake_clip())
    assert "demucs" not in order


def test_identical_text_gives_a_jaccard_of_one():
    j, s = ly.compare("the quick brown fox jumps over",
                      "the quick brown fox jumps over")
    assert j == pytest.approx(1.0, abs=0.01)


def test_different_text_gives_a_low_jaccard():
    j, s = ly.compare("the quick brown fox jumps over",
                      "pack my box with five dozen jugs")
    assert j < 0.2


def test_matched_spans_carry_the_times_for_highlighting_in_the_ui():
    """Section 7.3: the user sees which words and when."""
    r = ly.build_result("c1", "quick brown", "quick brown",
                        words=[("quick", 1.0, 1.5), ("brown", 1.5, 2.2)])
    assert r.matched_spans
    assert "query_time" in r.matched_spans[0]


@pytest.mark.heavy
def test_the_negative_control_on_an_instrumental(instrumental_audio):
    """Section 7.3: the cheapest correctness test in the whole plan.

    The instrumental-only groups from the catalog (7,942 of them) are the test set
    for the gate. Anything above the threshold means the gate is set wrong.
    """
    t = ly.transcribe(instrumental_audio)
    ok, _ = ly.gate(t)
    assert ok is False


def _fake_clip():
    import numpy as np
    class C:
        y_speech = np.zeros(16000)
        sr_speech = 16000
    return C()
```

- [ ] **Step 1b: Add the `instrumental_audio` fixture to `tests/conftest.py`**

```python
@pytest.fixture
def instrumental_audio(tmp_path) -> str:
    """A recording with no vocal. Negative control for the confidence gate from 7.3."""
    melody = np.concatenate([tone(f, 0.5) for f in (523.3, 587.3, 659.3, 698.5)] * 4)
    return _write(tmp_path, "instrumental.wav", melody)
```

- [ ] **Step 2:** `./scripts/rt tests/test_lyrics.py -v` - FAIL
- [ ] **Step 3:** Implement it. `faster-whisper` model `base`, `word_timestamps=True`. Language stability: the same detected language in at least 80% of the windows. MinHash through `datasketch`, 5-word shingles. The semantic level through `sentence-transformers`, a multilingual model. Candidate lyrics from `candidate.lyrics_path`, **not transcribed**.
- [ ] **Step 4:** `./scripts/rt tests/test_lyrics.py -v` - PASS. Run the test marked `heavy` separately: `./scripts/rt tests/test_lyrics.py -m heavy`
- [ ] **Step 5:** Add the `faster-whisper` and `demucs` timings to `docs/measurements.md`
- [ ] **Step 6:** `git add src/origin/detectors/lyrics.py tests/test_lyrics.py docs/measurements.md && git commit -m "feat: detector D with a confidence gate and conditional source separation"`

---

### Task 15: Detector C - symbolic melody

**Files:** Create `src/origin/detectors/melodic.py`, `tests/test_melodic.py`

**Interfaces:**
- Consumes: `ingest.Clip`, `contracts.MelodicResult`
- Produces: `melodic.to_intervals(midi_notes) -> list[int]`; `melodic.ngrams(intervals, n) -> list[tuple]`; `melodic.longest_common_run(a, b) -> int`; `melodic.mongeau_sankoff(a, b) -> float`; `melodic.MelodicDetector` with `level = 2`

Section 7.4. The most expensive detector, first on the fallback ladder.

- [ ] **Step 1: Tests**

```python
# tests/test_melodic.py
import pytest
from origin.detectors import melodic as m


def test_intervals_are_transposition_invariant():
    """Section 7.4 step 4: this is the whole idea of the interval representation."""
    a = [60, 62, 64, 65]
    b = [67, 69, 71, 72]  # the same melody a fifth higher
    assert m.to_intervals(a) == m.to_intervals(b) == [2, 2, 1]


def test_ngrams_have_the_requested_length():
    assert m.ngrams([2, 2, 1, -3, -2], n=4) == [(2, 2, 1, -3), (2, 1, -3, -2)]


def test_the_longest_common_run():
    a = [2, 2, 1, -3, -2, 5, 5]
    b = [9, 9, 2, 2, 1, -3, -2, 7]
    assert m.longest_common_run(a, b) == 5


def test_no_common_run_gives_zero():
    assert m.longest_common_run([1, 2, 3], [7, 8, 9]) == 0


def test_ornaments_do_not_destroy_the_match():
    """Section 7.4: a melody played with ornaments is still the same melody."""
    plain = [60, 62, 64, 65, 67]
    ornamented = [60, 61, 62, 64, 65, 66, 67]
    assert m.mongeau_sankoff(m.to_intervals(plain), m.to_intervals(ornamented)) < 0.5


def test_different_melodies_give_a_large_distance():
    assert m.mongeau_sankoff([2, 2, 1], [-7, 5, -3]) > 0.7


def test_a_single_note_does_not_blow_up():
    assert m.to_intervals([60]) == []
    assert m.ngrams([], n=4) == []


def test_the_detector_returns_an_envelope_at_level_two():
    d = m.MelodicDetector()
    assert d.level == 2


@pytest.mark.heavy
def test_transcription_detects_the_dominant_line(chord_wav):
    """The highest active note in a frame, with hysteresis against flicker."""
    from origin import ingest
    notes = m.transcribe_melody(ingest.load_clip(chord_wav))
    assert len(notes) >= 4
```

- [ ] **Step 2:** `./scripts/rt tests/test_melodic.py -v` - FAIL
- [ ] **Step 3:** Implement it. `basic-pitch` for the transcription, the dominant line with hysteresis, quantization onto the tempo grid from `librosa.beat.beat_track`. Mongeau-Sankoff normalized to the range 0-1. Source separation **shared with detector D**, if that one has already computed it.
- [ ] **Step 4:** `./scripts/rt tests/test_melodic.py -v` - PASS
- [ ] **Step 5:** `git add src/origin/detectors/melodic.py tests/test_melodic.py && git commit -m "feat: detector C, symbolic melody over intervals"`

---
## WAVE 7 - sequential

### Task 16: Calibration sample with a title collision filter

This task defends every threshold in the system against contaminated labels.

**Files:** Create `scripts/sample_calibration.py`, `tests/test_sample_calibration.py`

**Interfaces:**
- Consumes: the SHS export from `Projects/dataset/export_20260701.csv.zip`
- Produces: `sample_calibration.pool(csv_path) -> list[Group]`; `sample_calibration.sample_pairs(groups, n_pos, n_neg, seed) -> Sample`; the result to `data/calibration/pairs.json`

The filter from section 5.4, four conditions. The pool after filtering: **69,208 groups** against a need for 250 pairs.

- [ ] **Step 1: Tests**

```python
# tests/test_sample_calibration.py
import pytest
from scripts import sample_calibration as sc


@pytest.fixture
def groups():
    return [
        sc.Group("Bohemian Rhapsody", [("Queen", "en", False), ("Braids", "en", False)]),
        sc.Group("Crazy", [("Seal", "en", False), ("Patsy Cline", "en", False)]),
        sc.Group("Home", [("Depeche Mode", "en", False), ("Diana Ross", "en", False)]),
        sc.Group("Have I Told You Lately", [("Van Morrison", "en", False),
                                            ("Rod Stewart", "en", False)]),
        sc.Group("Summertime", [(f"W{i}", "en", False) for i in range(1485)]),
        sc.Group("Solo Track Only Once", [("Solo", "en", False)]),
        sc.Group("All Instrumental Suite Here", [("A", None, True), ("B", None, True)]),
    ]


def test_rejects_groups_larger_than_ten(groups):
    p = sc.pool_from_groups(groups)
    assert not any(g.work_title == "Summertime" for g in p)


def test_rejects_short_titles_because_that_is_where_collisions_live(groups):
    """Section 5.4 condition 2: Crazy is Seal and Patsy Cline, two different pieces."""
    p = sc.pool_from_groups(groups)
    titles = {g.work_title for g in p}
    assert "Crazy" not in titles
    assert "Home" not in titles


def test_lets_distinguishable_titles_through(groups):
    p = sc.pool_from_groups(groups)
    titles = {g.work_title for g in p}
    assert "Bohemian Rhapsody" in titles
    assert "Have I Told You Lately" in titles


def test_rejects_singletons(groups):
    p = sc.pool_from_groups(groups)
    assert not any(g.work_title == "Solo Track Only Once" for g in p)


def test_rejects_groups_without_two_vocal_performances(groups):
    p = sc.pool_from_groups(groups)
    assert not any(g.work_title == "All Instrumental Suite Here" for g in p)


def test_at_most_one_pair_per_group(groups):
    """Section 5.4 condition 3: without this, half the set is one work."""
    sample = sc.sample_pairs(sc.pool_from_groups(groups), n_pos=2, n_neg=0, seed=1)
    titles = [p.work_title for p in sample.positives]
    assert len(titles) == len(set(titles))


def test_singletons_are_the_negative_pool(groups):
    """Section 5.4: a work with one performance by definition has no cover."""
    assert any(g.work_title == "Solo Track Only Once"
               for g in sc.negative_pool_from_groups(groups))


def test_tightening_to_four_words_is_available(groups):
    """Section 5.4 quality control: if >1 of the 20 pairs is bad, we tighten."""
    p = sc.pool_from_groups(groups, min_words=4)
    assert all(len(g.work_title.split()) >= 4 for g in p)


def test_the_draw_is_reproducible(groups):
    p = sc.pool_from_groups(groups)
    a = sc.sample_pairs(p, n_pos=2, n_neg=0, seed=7)
    b = sc.sample_pairs(p, n_pos=2, n_neg=0, seed=7)
    assert [x.work_title for x in a.positives] == [x.work_title for x in b.positives]


def test_the_default_sample_size_is_500_pairs():
    assert sc.DEFAULT_POSITIVES == 250
    assert sc.DEFAULT_NEGATIVES == 250


@pytest.mark.integration
def test_the_real_export_gives_a_pool_of_about_69_thousand():
    """Measured on export_20260701: 69,208 groups after filtering."""
    p = sc.pool("../dataset/export_20260701.csv.zip")
    assert 60_000 < len(p) < 80_000
```

- [ ] **Step 2:** `./scripts/rt tests/test_sample_calibration.py -v` - FAIL
- [ ] **Step 3:** Implement the four filter conditions from section 5.4. Hard negatives: the same performer or a similar tempo and key, different works. Structural negatives: pairs sharing a chord sequence, not sharing a melody.
- [ ] **Step 4:** `./scripts/rt tests/test_sample_calibration.py -v` - PASS
- [ ] **Step 5:** Draw the sample: `python scripts/sample_calibration.py --out data/calibration/pairs.json`, download the audio through `fetch_audio.fetch_many` with a 25% overage
- [ ] **Step 6: Filter quality control (mandatory, section 5.4)**

Listen through 20 positive pairs by hand. Write the result to `docs/kontrola-probki.md`: how many pairs turned out to be different works. **If more than one**, tighten `min_words` to 4 and redraw. Without this step the task is not complete.

- [ ] **Step 7:** `git add scripts/sample_calibration.py tests/test_sample_calibration.py docs/kontrola-probki.md && git commit -m "feat: calibration sample with a title collision filter"`

---

### Task 17: Calibration model

**Files:** Create `src/origin/calibration.py`, `tests/test_calibration.py`

**Interfaces:**
- Consumes: `data/calibration/pairs.json`, the outputs of all the detectors
- Produces:
  - `calibration.fit(features, labels, verdict_class) -> Model`
  - `Model.predict_proba(features) -> float`, `Model.save(path)`, `Model.load(path) -> Model`
  - `Model.coefficients: np.ndarray`, `Model.feature_names: list[str]`, `Model.verdict_class: str`
  - `calibration.to_vector(features: dict[str, float | None]) -> tuple[np.ndarray, np.ndarray]` returning the feature vector and an availability vector of the same length
  - `calibration.is_available(verdict_class) -> bool`
  - `calibration.probability_status(verdict_class) -> Literal["calibrated", "uncalibrated"]`
  - `calibration.operating_threshold(model, X, y, target_precision) -> float`
  - `calibration.metrics(model, X_test, y_test) -> Metrics` with the fields `auc`, `ece`, `precision_at_threshold`, `reliability_curve`

Section 10. **A separate model per evidence class.** Missing features through an availability indicator, **never through a zero**.

- [ ] **Step 1: Tests**

```python
# tests/test_calibration.py
import numpy as np
import pytest
from origin import calibration as cal


@pytest.fixture
def data():
    rng = np.random.default_rng(0)
    X_pos = rng.normal(0.7, 0.1, (200, 7))
    X_neg = rng.normal(0.3, 0.1, (200, 7))
    X = np.vstack([X_pos, X_neg])
    y = np.array([1] * 200 + [0] * 200)
    return X, y


def test_the_model_returns_a_probability_in_range(data):
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    p = m.predict_proba(X[0])
    assert 0.0 <= p <= 1.0


def test_a_separate_model_per_class(data):
    """Section 10.2: the probability for VERSION is a different quantity from EXCERPT."""
    X, y = data
    a = cal.fit(X, y, verdict_class="VERSION")
    b = cal.fit(X, y[::-1], verdict_class="EXCERPT_PHONOGRAM")
    assert a.verdict_class != b.verdict_class
    assert not np.allclose(a.coefficients, b.coefficients)


def test_a_missing_feature_is_not_zero(data):
    """Section 10.2: zero is an informative value and it shifts the weights."""
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    features = {"A.peak_ratio": 0.8, "B.qmax": 0.7, "B.coverage": 0.6,
                "C.longest_common_run": None, "D.jaccard": None,
                "D.semantic_sim": None, "mean_idf": 9.0}
    values, availability = cal.to_vector(features)
    assert availability[3] == 0.0, "the availability indicator says the feature was absent"
    assert len(values) == len(availability)


def test_the_regression_gives_weights_that_can_be_shown(data):
    """Section 10.2: regression was chosen over a forest so that it can be explained."""
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    assert len(m.coefficients) == 7
    assert m.feature_names


def test_the_metrics_contain_auc_ece_and_precision(data):
    X, y = data
    m = cal.fit(X[:300], y[:300], verdict_class="VERSION")
    met = cal.metrics(m, X[300:], y[300:])
    assert 0.0 <= met.auc <= 1.0
    assert met.ece >= 0.0
    assert met.reliability_curve


def test_the_operating_threshold_targets_a_precision_of_095(data):
    """Section 10.3: a false alarm about infringement costs more than a miss."""
    X, y = data
    m = cal.fit(X[:300], y[:300], verdict_class="VERSION")
    threshold = cal.operating_threshold(m, X[300:], y[300:], target_precision=0.95)
    assert 0.0 < threshold < 1.0


def test_the_lyrics_class_has_no_model():
    """Section 10.4: the catalog has no original-adaptation pairs."""
    assert cal.is_available("LYRICS") is False


def test_the_excerpt_work_class_has_no_model():
    assert cal.is_available("EXCERPT_WORK") is False


def test_a_missing_model_gives_the_status_uncalibrated():
    status = cal.probability_status("LYRICS")
    assert status == "uncalibrated"


def test_the_model_saves_and_loads(data, tmp_path):
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    m.save(tmp_path / "v.joblib")
    loaded = cal.Model.load(tmp_path / "v.joblib")
    assert np.allclose(loaded.predict_proba(X[0]), m.predict_proba(X[0]))
```

- [ ] **Step 2:** `./scripts/rt tests/test_calibration.py -v` - FAIL
- [ ] **Step 3:** Implement `LogisticRegression` from `scikit-learn`. The feature vector: 7 values plus 7 availability indicators, 14 dimensions in total. ECE computed over 10 bins. `is_available` returns `False` for `LYRICS` and `EXCERPT_WORK` **hard**, regardless of whether the model file exists.
- [ ] **Step 4:** `./scripts/rt tests/test_calibration.py -v` - PASS
- [ ] **Step 5:** Train on the sample from T16, save the models to `models/`, write the metrics to `docs/kalibracja.md`
- [ ] **Step 6:** `git add src/origin/calibration.py tests/test_calibration.py docs/kalibracja.md && git commit -m "feat: calibration per evidence class with a feature availability indicator"`

---

## WAVE 8 - in parallel, four tasks, disjoint component directories

All four work exclusively in the mock mode from T5 (`ORIGIN_MOCK=1`). None of them touches `web/lib/`, because that belongs to T6.

### Task 18: Screens E1 and E2

**Files:** Create `web/components/input/UrlInput.tsx`, `Waveform.tsx`, `ExampleButtons.tsx`, `web/components/pipeline/PipelineList.tsx`, `StageRow.tsx`, `web/tests/pipeline.test.tsx`

**Interfaces:**
- Consumes: `lib/api.ts`, `lib/theme.ts`, `lib/contracts.ts`
- Produces: `<UrlInput onSubmit>`, `<PipelineList events>`

- [ ] **Step 1: Tests**

```typescript
// web/tests/pipeline.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PipelineList } from "../components/pipeline/PipelineList";

const events = [
  { stage: "ingest", level: 1, status: "done", detail: { duration: 184.2, windows: 37 } },
  { stage: "fingerprint", level: 1, status: "done", detail: { hashes: 4812 } },
  { stage: "shortlist", level: 1, status: "done", detail: { from: 12, to: 8, corpus: 4128 } },
  { stage: "transcript", level: 2, status: "gated",
    detail: { reason: "asr_confidence", next: "separation" } },
];

describe("E2 live pipeline", () => {
  it("every stage shows what it produced", () => {
    render(<PipelineList events={events} />);
    expect(screen.getByText(/4,812/)).toBeInTheDocument();
  });

  it("shows two numbers and both are labeled", () => {
    // The Global Constraint from section 13.2: candidates are not the corpus
    render(<PipelineList events={events} />);
    expect(screen.getByText(/8 of 12/)).toBeInTheDocument();
    expect(screen.getByText(/4,128/)).toBeInTheDocument();
    expect(screen.getByText(/commonality corpus/i)).toBeInTheDocument();
  });

  it("a gated stage is content, not an error", () => {
    render(<PipelineList events={events} />);
    expect(screen.getByText(/gate/i)).toBeInTheDocument();
    expect(screen.getByText(/separation/i)).toBeInTheDocument();
  });

  it("lime only on the active step", () => {
    const { container } = render(
      <PipelineList events={[...events, { stage: "harmonic", level: 1, status: "running", detail: {} }]} />
    );
    const highlighted = container.querySelectorAll("[data-accent='true']");
    expect(highlighted.length).toBe(1);
  });

  it("technical values in a monospaced face", () => {
    const { container } = render(<PipelineList events={events} />);
    expect(container.querySelector(".font-mono")).toBeTruthy();
  });
});
```

- [ ] **Step 2:** `./scripts/rt-web web/tests/pipeline.test.tsx` - FAIL
- [ ] **Step 3:** Implement it. E1: a URL field, a file drop, three example buttons, the waveform **immediately after pasting**, before the analysis (wavesurfer.js). E2: a vertical list lighting up one after another, fed by SSE.
- [ ] **Step 4:** `./scripts/rt-web` - PASS
- [ ] **Step 5:** `git add web/components/input web/components/pipeline web/tests/pipeline.test.tsx && git commit -m "feat: screens E1 input and E2 live pipeline"`

---

### Task 19: Screens E3 and E4 - verdict and evidence

E4 is the most important screen in the product. A/B listening must not be cut at any level of the fallback ladder.

**Files:** Create `web/components/verdict/VerdictCard.tsx`, `web/components/evidence/WaveOverlay.tsx`, `AbPlayer.tsx`, `SimilarityMatrix.tsx`, `LyricsDiff.tsx`, `PianoRoll.tsx`, `web/tests/verdict.test.tsx`, `web/tests/evidence.test.tsx`

**Interfaces:**
- Consumes: `lib/api.ts`, `lib/theme.ts`
- Produces: `<VerdictCard entry status>`, `<AbPlayer queryUrl candidateUrl offset>`

- [ ] **Step 1: Tests**

```typescript
// web/tests/verdict.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen, rerender } from "@testing-library/react";
import { VerdictCard } from "../components/verdict/VerdictCard";

const preliminary = { verdict_class: "VERSION", probability: 0.71,
                  probability_status: "uncalibrated",
                  candidate: { name: "Kashmir", artist: "Led Zeppelin" },
                  explanation: "Harmony and lyrics match, the fingerprint does not hit." };

describe("E3 verdict", () => {
  it("shows the evidence class badge", () => {
    render(<VerdictCard entry={preliminary} status="partial" />);
    expect(screen.getByText("THE SAME WORK")).toBeInTheDocument();
  });

  it("tells a calibrated threshold from an entered one", () => {
    // Global Constraint 7
    render(<VerdictCard entry={preliminary} status="partial" />);
    expect(screen.getByText(/preliminary threshold|no calibration data/i)).toBeInTheDocument();
  });

  it("the card upgrades itself once the final verdict arrives", () => {
    // Section 12: the verdict appears twice and the class may change
    const { rerender } = render(<VerdictCard entry={preliminary} status="partial" />);
    rerender(<VerdictCard entry={{ ...preliminary, verdict_class: "EXACT", probability: 0.94,
                                   probability_status: "calibrated" }} status="final" />);
    expect(screen.getByText("IDENTICAL RECORDING")).toBeInTheDocument();
    expect(screen.queryByText("THE SAME WORK")).not.toBeInTheDocument();
  });

  it("the COMMON class does not get lime", () => {
    const { container } = render(
      <VerdictCard entry={{ ...preliminary, verdict_class: "COMMON" }} status="final" />);
    expect(container.querySelector("[data-accent='true']")).toBeNull();
  });

  it("shows one sentence of justification", () => {
    render(<VerdictCard entry={preliminary} status="partial" />);
    expect(screen.getByText(/fingerprint does not hit/)).toBeInTheDocument();
  });
});
```

```typescript
// web/tests/evidence.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AbPlayer } from "../components/evidence/AbPlayer";

describe("E4 A/B listening", () => {
  it("switches the source while keeping the position", () => {
    // Section 13.2: the only real verification for audio is the ear
    render(<AbPlayer queryUrl="/q.wav" candidateUrl="/c.wav" offset={51.7} />);
    const button = screen.getByRole("button", { name: /A\/B/i });
    fireEvent.click(button);
    expect(screen.getByTestId("active-source").textContent).toBe("B");
  });

  it("point B is shifted by the alignment offset", () => {
    render(<AbPlayer queryUrl="/q.wav" candidateUrl="/c.wav" offset={51.7} />);
    fireEvent.click(screen.getByRole("button", { name: /A\/B/i }));
    expect(Number(screen.getByTestId("position-b").textContent)).toBeCloseTo(51.7, 1);
  });
});
```

- [ ] **Step 2:** `./scripts/rt-web` - FAIL
- [ ] **Step 3:** Implement the four E4 panels. Time overlay: two waveforms, the shared segment highlighted, a slider, an A/B button. Matrix: a heatmap with the alignment path drawn on it. Lyrics: two columns with highlighting, a click scrolls playback. Melody: a pianoroll.
- [ ] **Step 4:** `./scripts/rt-web` - PASS
- [ ] **Step 5:** `git add web/components/verdict web/components/evidence web/tests/verdict.test.tsx web/tests/evidence.test.tsx && git commit -m "feat: screens E3 verdict and E4 evidence with A/B listening"`

**Note:** stage **only the files listed**. Wave 8 runs in parallel and `git add web/tests` would take a neighbouring task's work.

---

### Task 20: Screens E5, E6, E7

**Files:** Create `web/components/criteria/CriteriaBars.tsx`, `web/components/ranking/RankingList.tsx`, `web/components/timeline/Timeline.tsx`, `web/tests/criteria.test.tsx`, `web/tests/timeline.test.tsx`

- [ ] **Step 1: Tests**

```typescript
// web/tests/criteria.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CriteriaBars } from "../components/criteria/CriteriaBars";

describe("E5 criteria breakdown", () => {
  it("has exactly four criteria", () => {
    // D5: no rhythm and no video - there is no detector behind them
    render(<CriteriaBars evidence={{}} />);
    expect(screen.getAllByTestId("criterion-bar")).toHaveLength(4);
    expect(screen.queryByText(/rhythm/i)).toBeNull();
    expect(screen.queryByText(/video/i)).toBeNull();
  });

  it("not_applicable shows a worded state, not a zero", () => {
    // Global Constraint 4
    render(<CriteriaBars evidence={{
      lyrics: { status: "not_applicable", reason: "instrumental" } }} />);
    expect(screen.getByText(/not applicable/i)).toBeInTheDocument();
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("gated shows rejection by the gate", () => {
    render(<CriteriaBars evidence={{
      lyrics: { status: "gated", reason: "asr_confidence" } }} />);
    expect(screen.getByText(/gate/i)).toBeInTheDocument();
  });

  it("shows the commonality indicator next to every bar", () => {
    render(<CriteriaBars evidence={{ harmonic: { status: "ok", qmax_score: 0.7 } }}
                         commonality={{ corpus_frequency: 1240, corpus_size: 4128 }} />);
    expect(screen.getByText(/1,240 works/)).toBeInTheDocument();
  });
});
```

```typescript
// web/tests/timeline.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Timeline } from "../components/timeline/Timeline";

describe("E7 chronology", () => {
  it("emphasizes the earliest one", () => {
    render(<Timeline items={[
      { id: "a", name: "A", published: "1975-02-24", published_source: "manual" },
      { id: "b", name: "B", published: "1998-06-01", published_source: "manual" }]} />);
    expect(screen.getByTestId("earliest").textContent).toContain("A");
  });

  it("skips candidates with no date", () => {
    // D10: for entries outside the manifest the axis shows nothing
    render(<Timeline items={[
      { id: "a", name: "A", published: "1975-02-24", published_source: "manual" },
      { id: "b", name: "B", published: null, published_source: null }]} />);
    expect(screen.queryByText("B")).toBeNull();
  });

  it("says where the date comes from", () => {
    render(<Timeline items={[
      { id: "a", name: "A", published: "1975-02-24", published_source: "manual" }]} />);
    expect(screen.getByText(/release metadata, not from the video platform/i)).toBeInTheDocument();
  });

  it("does not render the axis when no candidate has a date", () => {
    const { container } = render(<Timeline items={[
      { id: "b", name: "B", published: null, published_source: null }]} />);
    expect(container.querySelector("[data-testid='axis']")).toBeNull();
  });
});
```

- [ ] **Step 2:** `./scripts/rt-web` - FAIL
- [ ] **Step 3:** Implement it. E6: positions 2-N, a click switches the evidence panel from E4.
- [ ] **Step 4:** `./scripts/rt-web` - PASS
- [ ] **Step 5:** `git add web/components/criteria web/components/ranking web/components/timeline web/tests/criteria.test.tsx web/tests/timeline.test.tsx && git commit -m "feat: screens E5 criteria, E6 ranking, E7 chronology"`

**Note:** stage only the files listed, wave 8 runs in parallel.

---

### Task 21: Screens E8, E9, E10

**Files:** Create `web/components/legal/LegalPanel.tsx`, `web/components/calibration/CalibrationCharts.tsx`, `web/components/casefile/CaseFile.tsx`, `web/tests/legal.test.tsx`

- [ ] **Step 1: Tests**

```typescript
// web/tests/legal.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LegalPanel } from "../components/legal/LegalPanel";

describe("E8 legal panel", () => {
  it("always shows the note that this is not legal advice", () => {
    render(<LegalPanel legal={{ rights_layer: [], risk_flags: [],
      license_status: "unknown", required_attribution: null,
      disclaimer: "Technical signal, not a legal opinion." }} />);
    expect(screen.getByText(/not a legal opinion/i)).toBeInTheDocument();
  });

  it("an unknown license is absence of information, not absence of restrictions", () => {
    // Limitation 9 from the specification
    render(<LegalPanel legal={{ rights_layer: [], risk_flags: [],
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    expect(screen.getByText(/no information/i)).toBeInTheDocument();
    expect(screen.queryByText(/permitted/i)).toBeNull();
  });

  it("an open license gives ready-made attribution text to copy", () => {
    render(<LegalPanel legal={{ rights_layer: ["phonogram"], risk_flags: [],
      license_status: "cc-by-4.0", required_attribution: "Work X, author Y, CC BY 4.0",
      disclaimer: "x" }} />);
    expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
  });

  it("a high-risk flag gets lime", () => {
    const { container } = render(<LegalPanel legal={{ rights_layer: ["phonogram"],
      risk_flags: ["recognizable_excerpt"], license_status: "unknown",
      required_attribution: null, disclaimer: "x" }} />);
    expect(container.querySelector("[data-accent='true']")).toBeTruthy();
  });
});
```

- [ ] **Step 2:** `./scripts/rt-web` - FAIL
- [ ] **Step 3:** Implement it. E9: ROC curve, reliability diagram, the number of pairs, precision at the threshold. E10: case file export in the brief's branding, with the footer `GRAI ORIGIN / CASE 03 / <screen>`.
- [ ] **Step 4:** `./scripts/rt-web` - PASS
- [ ] **Step 5:** `git add web/components/legal web/components/calibration web/components/casefile web/tests/legal.test.tsx && git commit -m "feat: screens E8 legal, E9 calibration, E10 case file"`

**Note:** stage only the files listed, wave 8 runs in parallel.

---

## WAVE 9 - sequential

### Task 22: End-to-end integration and demo scenarios

**Files:** Create `src/origin/pipeline.py`, `tests/test_pipeline.py`, `tests/test_demo_scenarios.py`, `docs/walkthrough.md`; Modify `src/origin/api/routes.py`

**Interfaces:**
- Consumes: everything
- Produces: `pipeline.run(url, candidate_set, emit) -> AnalyzeResult` executing level 1, emitting the preliminary verdict, then level 2 and the final verdict

- [ ] **Step 1: Tests**

```python
# tests/test_pipeline.py
import pytest
from origin import pipeline


def test_level_1_emits_the_verdict_before_level_2(chord_wav):
    """Section 4: the verdict in five seconds, the evidence arriving over the next thirty."""
    events = []
    pipeline.run(chord_wav, "demo_01", emit=events.append)
    stages = [e.stage for e in events]
    verdict_index = stages.index("verdict")
    assert "fingerprint" in stages[:verdict_index]
    assert "harmonic" in stages[:verdict_index]
    assert "melodic" not in stages[:verdict_index]


def test_the_verdict_appears_twice(chord_wav):
    events = []
    pipeline.run(chord_wav, "demo_01", emit=events.append)
    verdicts = [e for e in events if e.stage == "verdict"]
    assert [x.status for x in verdicts] == ["partial", "final"]


def test_a_level_2_detector_failure_does_not_cancel_the_verdict(chord_wav, monkeypatch):
    """Critical for the demo: level 2 upgrades the verdict, it never takes it away."""
    from origin.detectors import melodic
    monkeypatch.setattr(melodic.MelodicDetector, "run",
                        lambda self, c, k: (_ for _ in ()).throw(RuntimeError("boom")))
    result = pipeline.run(chord_wav, "demo_01", emit=lambda e: None)
    assert result.status == "complete"
    assert result.ranking[0].evidence["melodic"]["status"] == "failed"


def test_the_heavy_models_do_not_run_beyond_the_shortlist(chord_wav, monkeypatch):
    """Global Constraint 3: breaking this rule makes work on this hardware impossible."""
    calls = []
    from origin.detectors import lyrics
    monkeypatch.setattr(lyrics, "_demucs", lambda y, sr: calls.append(1) or y)
    pipeline.run(chord_wav, "demo_01", emit=lambda e: None)
    assert len(calls) <= 1, "separation only on the query, never on the candidates"
```

```python
# tests/test_demo_scenarios.py
"""The five scenarios from section 14. These are the tests that must pass before the show."""
import pytest

pytestmark = pytest.mark.integration


def test_scenario_1_a_reupload_gives_exact(demo_reupload):
    assert _verdict_class(demo_reupload) == "EXACT"


def test_scenario_2_a_cover_gives_version(demo_cover):
    assert _verdict_class(demo_cover) == "VERSION"


def test_scenario_3_a_sped_up_version_gives_modified(demo_speedup):
    assert _verdict_class(demo_speedup) == "MODIFIED"


def test_scenario_4_a_sample_gives_excerpt(demo_sample):
    assert _verdict_class(demo_sample) == "EXCERPT_PHONOGRAM"


def test_scenario_5_the_trap_gives_common(demo_trap):
    """The most important test in the project.

    Every team will show that it finds something. This test checks that the system can
    say 'I found a similarity and I consider it immaterial'.
    """
    assert _verdict_class(demo_trap) == "COMMON"


def test_scenario_5_reports_the_number_of_tracks_in_the_corpus(demo_trap):
    from origin import pipeline
    result = pipeline.run(demo_trap, "demo_01", emit=lambda e: None)
    assert result.ranking[0].commonality.corpus_frequency > 100


def _verdict_class(url):
    from origin import pipeline
    return pipeline.run(url, "demo_01", emit=lambda e: None).ranking[0].verdict_class
```

- [ ] **Step 1b: Add the scenario fixtures to `tests/conftest.py`**

Five fixtures returning paths to the files in `data/audio/demo/` that you prepared in T9:
`demo_reupload`, `demo_cover`, `demo_speedup`, `demo_sample`, `demo_trap`. Each marked
`@pytest.mark.integration`, each skipped through `pytest.skip` when the file is not on disk -
the unit tests must work on a machine with no downloaded audio.

```python
@pytest.fixture
def demo_reupload() -> str:
    return _demo_file("reupload.wav")


def _demo_file(name: str) -> str:
    import os
    path = os.path.join("data", "audio", "demo", name)
    if not os.path.exists(path):
        pytest.skip(f"missing {path} - run scripts/fetch_audio.py")
    return path
```

- [ ] **Step 2:** `./scripts/rt tests/test_pipeline.py -v` - FAIL
- [ ] **Step 3:** Implement `pipeline.run`. Level 2 in an `asyncio.create_task`, an exception from any detector caught and turned into a `failed` envelope. Wire it into `routes.py`, turn off mock mode.
- [ ] **Step 4:** `./scripts/rt tests/test_pipeline.py tests/test_demo_scenarios.py -v` - PASS
- [ ] **Step 5:** Write `docs/walkthrough.md`: problem, solution, result, limitation, in 90 seconds. We state the limitation ourselves, before anyone asks - the content from section 20 of the specification.
- [ ] **Step 6:** Run through the whole demo scenario five times. Record in `docs/walkthrough.md` what fell apart and what was fixed.
- [ ] **Step 7:** `git add src/origin/pipeline.py tests/test_pipeline.py tests/test_demo_scenarios.py docs/walkthrough.md src/origin/api/routes.py && git commit -m "feat: end-to-end integration and five demo scenarios"`

---

## Specification coverage map

| Specification section | Task |
|---|---|
| 3 taxonomy | T2 |
| 4 architecture, three levels | T22 |
| 5.1-5.2 catalog | T16 |
| 5.3 candidate manifest | T4 |
| 5.4 calibration set | T16 |
| 5.5 publication dates | T4, T20 |
| 5.6 IDF corpus | T11 |
| 5.7 audio downloading | T9 |
| 6 ingest | T3 |
| 7.0 detector envelope | T2, T7 |
| 7.1 detector A | T7 |
| 7.2 detector B | T8 |
| 7.3 detector D | T14 |
| 7.4 detector C | T15 |
| 8 commonality filter | T11 |
| 9 fusion and the tree | T12 |
| 10 calibration | T16, T17 |
| 11 legal layer | T13 |
| 12 API contracts | T2, T5 |
| 13.1 visual system | T6 |
| 13.2 screens E1-E10 | T18, T19, T20, T21 |
| 14 demo scenarios | T22 |
| 15 evaluation | T17, T22 |
| 16 stack and licenses | T1 |
| 17.4 milestones | T1 (M0) |

**Deliberately out of scope for this plan:** `POST /api/explain` with a real language model (T5 leaves a mock), the case file format as PDF (T21 makes a printable page).
