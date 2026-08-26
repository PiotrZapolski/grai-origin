<p align="center">
  <img src="docs/assets/grai-logo.png" alt="grai" width="200">
</p>

<h1 align="center">GRAI ORIGIN</h1>
<p align="center"><b>PROVENANCE ENGINE</b> for audio<br>
<sub>GRAI x VIBESTARS / CASE 03</sub></p>

This project was built during the **Vibestars hackathon**, session #3, in partnership
with **[grai.fm](https://grai.fm)**. The task was Case 03, "Find the original source":
given a URL to an audio clip and a small set of candidates, return a ranking that leads
to the most likely original. The brief is in
[`docs/brief/grai-x-vibestars-case-03.pdf`](docs/brief/grai-x-vibestars-case-03.pdf).

You paste the address of a recording. The system tells you where that sound
comes from and **what kind** of similarity it is: the same fixation, the same
work in a different performance, a borrowed fragment, or an element common to
an entire genre.

That last class is what separates a useful tool from a false-alarm generator.
The system is meant to say it outright: *we found a similarity and we believe
it is not material.*

| Class | Means |
|:--|:--|
| `EXACT` | the same fixation: reupload, rip, trim |
| `MODIFIED` | the same fixation, modified: speedup, pitch shift |
| `VERSION` | the same work, a different performance: cover, live |
| `EXCERPT_PHONOGRAM` | a borrowed fragment of the recording: sample, loop |
| `EXCERPT_WORK` | a borrowed phrase of the composition |
| `LYRICS` | lyrical overlap only |
| `COMMON` | **an element common to the genre, not a borrowing** |
| `NONE` | no match |

## Documentation

Start with the first one. The rest are in the order in which they are usually
needed.

| File | What it contains |
|:--|:--|
| [`docs/how-it-works.md`](docs/how-it-works.md) | **Visual guide to the eight steps** with diagrams and real numbers |
| [`docs/pitch-narrative.md`](docs/pitch-narrative.md) | Narrative for the presentation: the problem, the stages, why this scales |
| [`docs/demo-scenarios.md`](docs/demo-scenarios.md) | Concrete addresses to paste and the expected verdict |
| [`docs/catalog-examples.md`](docs/catalog-examples.md) | Guide to the reference catalog, with the traps hidden in the data |
| [`docs/superpowers/specs/2026-08-21-grai-origin-spec.md`](docs/superpowers/specs/2026-08-21-grai-origin-spec.md) | **Executive specification**, the source of truth for the implementation |
| [`docs/superpowers/specs/2026-08-21-grai-origin-design.md`](docs/superpowers/specs/2026-08-21-grai-origin-design.md) | Design decisions D1-D12 with rationale and cost of reversal |
| [`docs/brief/source-spec.md`](docs/brief/source-spec.md) | Source specification from the commissioning party, frozen |
| [`docs/references/`](docs/references/) | Legal materials with case law and the grai.fm brand sheet |

## Architecture in one paragraph

The work splits into three execution levels, not by detector but by **when**
something is allowed to happen. Level 0, offline: candidate representations
and the commonality corpus. Level 1, live, target 5 s: acoustic fingerprint,
harmonic similarity, shortlisting, commonality filter, preliminary verdict.
Level 2, in the background: lyrics, melody, final verdict. The heavy models
never touch the full candidate set, only the queries and the shortlists. That
is the only reason this works on a million recordings.

## Stack

**Backend:** Python 3.12, FastAPI, librosa, numpy, scipy, scikit-learn,
datasketch. **Front end:** Next.js, Tailwind, wavesurfer.js. Permissive
licenses only; the list of what was rejected, with reasons, is in section 16
of the specification.

```
src/origin/
  ingest.py, loudness.py, download.py   loading, BS.1770-4, downloading
  detectors/fingerprint.py              A: acoustic fingerprint, offset histogram
  detectors/harmonic.py                 B: chromagram, Qmax, 12 rotations
  detectors/lyrics.py                   D: whisper, confidence gate, MinHash
  detectors/melodic.py                  C: intervals, Mongeau-Sankoff
  shortlist.py, commonality.py          shortlisting, IDF corpus, degradation to COMMON
  fusion.py                             decision tree with binding rule order
  legal.py                              rights layer, flags, Pelham I and II
  calibration.py                        per-class regression, availability indicator
  pipeline.py                           wiring of levels 1 and 2 to the API
  api/                                  FastAPI, SSE, job store, mock
web/                                    ten screens E1-E10
```

## Running it

Tests run **exclusively on the remote server**, never locally. `scripts/rt`
rsyncs the code and runs pytest under a CPU quota; `scripts/rt-web` does the
same with vitest.

```bash
./scripts/rt                      # Python tests (pytest)
./scripts/rt-web                  # front-end tests (vitest)
ORIGIN_MOCK=1 uvicorn origin.api.app:app    # mock mode, five scenarios
uvicorn origin.api.app:app                  # the engine for real
```

Deployment via `docker-compose.yml` plus `docker-compose.prod.yml`, described
in [`docs/deployment.md`](docs/deployment.md).

## What is built and what is not

Honestly, because the brief requires stating what is a signal and what is a
limitation.

**Built and tested.** All eight stages of the engine. The fingerprint with
tempo drift correction. Harmonic similarity with a measured scale (a synthetic
cover stretched by 40% gives 1.000, unrelated material 0.117). Loudness
measurement anchored to the standard (a 1 kHz sine reads -3.0036 LKFS against
the reference -3.01). The commonality filter on a corpus of 291 works, with
chord patterns encoded by scale degrees, independent of key: the I-V-vi-IV
progression occurs in 16 of them and is correctly classified as commonplace.
A decision tree with a binding rule order. A legal layer with CJEU case
citations. Ten screens with the two-stage verdict and A/B listening.

**Built and run against the real models, but not calibrated on them.** The
lyrics and melody detectors were exercised end to end with `faster-whisper`,
`demucs` and `basic-pitch` installed from the `heavy` group in
`pyproject.toml`; the run and its timings are in
[`docs/full-run.md`](docs/full-run.md). Without those packages both detectors
return an explicit `model_unavailable` and the `LYRICS` and `EXCERPT_WORK`
classes are not reachable. Their thresholds still hold the starting values from
the specification, so those two classes stay switched off in the calibration
layer until they are measured on real pairs.

**The harmonic sieve is calibrated on real recordings; the probability model is
not.** These are two different things and it is worth keeping them apart. The
harmonic threshold and the binarisation percentile of the Qmax sieve were
measured on real audio on 2026-08-26: the percentile moved from 10 to 30 and
`VERSION_QMAX` from 0.55 to 0.25, on one real cover pair (Aretha Franklin
against The Beatles, "Let It Be") and 541 real negative pairs from the corpus.
`src/origin/config.py` marks the threshold `calibrated` with that date, and the
whole measurement is in
[`docs/calibration-harmonic.md`](docs/calibration-harmonic.md). The honest
caveat is the positive side: the false-alarm side rests on 541 pairs and is
measured, everything about recall rests on that single pair, because the corpus
holds one performance per work by construction and yields no cover pairs at
all.

The **probability calibration model** is a separate thing and it is still not
trained. The code exists and is tested, but training it needs audio for 500
pairs from the catalog, that audio was never downloaded and the catalog export
is gone. `models/` is empty, every `probability_status` on screen reads
`uncalibrated`, and that is genuinely what it is. The remaining thresholds -
`FINGERPRINT_NOISE_FLOOR`, the `EXCERPT_*` and the `LYRICS_*` ones - still hold
their starting values from the specification, not from measurement on real
audio.

**Slower than the specification promises.** Section 15 asks for a preliminary
verdict under 5 s and complete evidence under 30 s. Measured on four physical
cores of a Ryzen 5 3600 with the real models loaded: preliminary 6.2 to 7.7 s,
final 60 to 99 s, and 478 s when the confidence gate rejects the first
transcript and source separation runs. Two costs dominate - the embedding model
takes 17.5 s to load and nothing prewarms it, and demucs takes 391 s on a
three-minute clip. The targets stand; the numbers are what they are today, and
they are in [`docs/full-run.md`](docs/full-run.md).

**What we do not know.** The thresholds are designed for covers, because that
is what the reference catalog is. We do not know whether they hold up on
samples and remixes, and that is precisely where the legal stakes are highest.

## The first real run

The engine was run end-to-end, without mock mode, on the Aretha Franklin
recording of "Let It Be" against the `demo_01` set (2026-08-26, corpus of 291
works). It ran in four seconds and ranked the candidates correctly: The Beatles'
"Let It Be" first, Bob Marley's "No Woman, No Cry" second. Both, however, came
out `NONE`.

The Beatles recording scored `qmax` 0.0285 and `coverage` 0.0284 against the
query (transposition -4, `tempo_ratio` 1.182); Marley scored 0.0207 and 0.0206.
The fingerprint reported no measurement for either, correctly - the raw
`peak_ratio` of 0.015 and 0.0118 is far below the noise floor, because neither
is the same fixation. The commonality filter behaved as designed: `mean_idf`
3.095 and 1.642, both under the 4.605 corpus threshold, so a work-layer class
would have been degraded to `COMMON`.

What the run established is that `VERSION_QMAX` = 0.55, the value it ran with,
came from synthetic covers rather than real ones: the same candidate against
itself scores 1.000, a real cover 0.0285, an unrelated track 0.0207. The
ordering was right, the scale was not. The full numbers, the control
measurements and the explanation are in
[`docs/walkthrough.md`](docs/walkthrough.md).

That gap was closed the same day. The sieve was recalibrated on real audio -
binarisation percentile 10 to 30, `VERSION_QMAX` 0.55 to 0.25 - which puts the
real cover pair at `qmax` 0.293 against a negative maximum of 0.222 over 541
pairs. The measurement is in
[`docs/calibration-harmonic.md`](docs/calibration-harmonic.md); the numbers
above are the record of what the engine did before it.

## Data

The repository **does not contain** audio, lyrics, or catalog dumps. That is
someone else's property, excluded via `.gitignore`. The reference catalog comes
from SecondHandSongs (1.23 million performances) and requires your own access.

## Legal layer

The system returns a technical signal and an evidence classification, **never a
ruling on infringement**. Of the three conditions for pastiche established by
the CJEU in Pelham II it measures two, and says outright that it does not
measure the third. The demonstration version downloads audio in a way that
conflicts with the terms of service of the platforms involved; in a production
deployment the source must be official catalog deliveries.
