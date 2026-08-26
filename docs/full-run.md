# The first complete end-to-end pass, all four detectors on real models

Level 1 and its numbers live in `walkthrough.md`. This file is only about the
run in which detectors C and D executed against real models for the first time.
Nothing here was mocked and `ORIGIN_MOCK` was never set.

Machine: the shared test box, 4 of 6 physical cores (`taskset -c 0-3`, `nice -n
19`, `OMP/MKL/OPENBLAS/NUMEXPR/NUMBA_NUM_THREADS=4`). Another agent's
calibration was running on the same box throughout, load average 9-14. Every
number below is therefore an upper bound on a quiet machine, not a best case.

Code: `harmonic.py` at commit `dba0bea`, that is **before** the recalibration of
the binarisation percentile and `VERSION_QMAX`. The level 1 numbers here will
move once that lands.

## What had to change before anything would run

Nothing in `lyrics.py` or `melodic.py`. Both modules were written without ever
executing a model call and both were **correct against the real libraries** -
see "The assumed API against the real one" below. Everything that broke was
packaging.

### `basic-pitch[onnx]` does not exist as an installable thing on Python 3.12

Every published `basic-pitch` from 0.3.0 to 0.4.0 declares

    tensorflow<2.15.1,>=2.4.1 ; platform_system != "Darwin" and python_version >= "3.11"

as a **core** dependency. The `[onnx]` extra adds `onnxruntime` on top of that,
it does not replace it. No `tensorflow<2.15.1` wheel exists for Python 3.12, so
`pip install -e '.[dev,heavy]'` with `basic-pitch` in the group ends in
`ResolutionImpossible` and installs nothing at all.

The way out is that the ONNX weights ship **inside the basic-pitch wheel**
(`basic_pitch/saved_models/icassp_2022/nmp.onnx`, 230 kB) and
`basic_pitch/__init__.py` falls back through coremltools, tflite and tensorflow
to onnxruntime, warning about each absence on the way. So basic-pitch is
installed with `--no-deps` and everything it actually imports is listed in the
`heavy` group instead. `scripts/install-heavy` does this in the right order and
explains why.

### `resampy` is a hard requirement of the transcription

`basic_pitch/note_creation.py` imports `resampy` at module level, so it is
needed by `predict`, not by some optional path. Without it the melodic heavy
test dies with `ModuleNotFoundError` inside the first transcription.

### `sentence-transformers` was never in the group

Known gap, now closed. Without it `compare` silently returned
`semantic_sim=None` on a fully installed heavy environment, which reads as "the
model is missing" rather than "the group is wrong".

### torch has to come from the CPU index, and it has to come first

The default PyPI `torch` wheel for linux-x86_64 is the CUDA build and drags in
several gigabytes of `nvidia-*` packages onto a machine with no GPU. demucs
pulls torch in, so torch is installed from
`https://download.pytorch.org/whl/cpu` **before** the heavy group is resolved.
Confirmed afterwards: `torch 2.13.0+cpu`, `torch.version.cuda is None`, not one
`nvidia-*` package in site-packages.

### Cost

| | |
|---|---|
| torch + torchaudio, CPU index | ~50 s |
| the project with `[dev,heavy]` | 21 s |
| `basic-pitch --no-deps` | <1 s |
| **total wall time** | **~75 s** |
| venv before | 634 MB |
| venv after | 2.1 GB |

Model weights, downloaded once, all under `/root/.cache/huggingface` (680 MB
total) except basic-pitch, which needs no download:

| model | where | size |
|---|---|---|
| faster-whisper `base` | `hub/models--Systran--faster-whisper-base` | 142 MB |
| demucs `htdemucs` | `hub/models--adefossez--HTDemucs` | 81 MB |
| `paraphrase-multilingual-MiniLM-L12-v2` | `hub/models--sentence-transformers--...` | 458 MB |
| basic-pitch ICASSP 2022 | inside the wheel, `nmp.onnx` | 230 kB |

The embedding model is the largest single artifact in the system and it is the
one used least.

## The assumed API against the real one

Every call was written from documentation and never executed. All of them are
right. This is the full list of what was checked and against what:

| written as | real behaviour | verdict |
|---|---|---|
| `predict(path, ICASSP_2022_MODEL_PATH)` -> `_, _, events` | returns `(dict, PrettyMIDI, list)`; keys `note`/`onset`/`contour` | correct |
| `note_events` element is `(start, end, pitch, amplitude, bends)` | 5-tuple, `[0]` `[1]` float seconds, `[2]` int MIDI pitch, `[3]` float32 amplitude, `[4]` list of bends | **the flagged guess is correct** |
| `WhisperModel.transcribe(y, word_timestamps=True, vad_filter=False)` | segments with `.text` and `.words[].word/.start/.end/.probability`; info with `.language`, `.language_probability` | correct |
| `model.detect_language(window)[0]` | returns `(str, float, list)`, `[0]` is the language code | correct |
| `apply_model(model, (1,2,N), device="cpu", progress=False)[0]` | stems indexed by `model.sources == ['drums','bass','other','vocals']`, `model.samplerate == 44100` | correct |
| `SentenceTransformer.encode(list, normalize_embeddings=True)` | `(n, 384)` array, unit norm | correct |

Not one line of `lyrics.py` or `melodic.py` had to change.

### A note on running the heavy tests

`scripts/rt` rsyncs with `--delete` into the shared directory. While another
agent has uncommitted work there, invoking it overwrites that work. The heavy
tests here were run with the same pytest invocation, the same throttle and the
same ffmpeg shim, against a private copy of the tree.

Both heavy tests pass: the negative control on an instrumental, and the melodic
transcription of the dominant line.

## The run

`POST /api/analyze` with `query_demo_01.wav` (Aretha Franklin, "Let It Be", 179 s
after trimming to `MAX_DURATION_S`) against the `demo_01` set. Eight of the ten
candidates have no audio on disk and drop out at level 1; the shortlist is
`cand_07` (The Beatles, "Let It Be") and `cand_08` (Bob Marley, "No Woman, No
Cry").

Two passes are recorded. They differ in one thing only: the second uses a
manifest with `lyrics_path` filled in, because **every candidate in `demo_01`
has `lyrics_path: null`** and detector D therefore cannot produce a single
number - see "The lyrics gap" below.

### Timing per stage, from the SSE timestamps

| stage | pass A, cold melody cache | pass B, warm melody cache + lyrics compared |
|---|---|---|
| ingest | 1.37 s | 1.17 s |
| fingerprint | 1.28 s | 1.12 s |
| harmonic | 2.70 s | 3.48 s |
| shortlist + commonality | 0.60 s | 1.48 s |
| **preliminary verdict at** | **6.20 s** | **7.68 s** |
| transcript | 29.17 s | 73.96 s |
| melodic | 24.48 s | 17.78 s |
| **final verdict at** | **59.97 s** | **99.42 s** |

Against the promise of section 12:

- **preliminary under 5 s: missed**, 6.2 s and 7.7 s. Level 1 itself is cheap;
  what pushes it over is that the query's own representations are computed on
  the request path while only the candidates are prewarmed.
- **final under 30 s: missed by two to three times.** On four cores this budget
  is not reachable with whisper `base` on 179 s of audio, and that is the
  cheapest whisper there is.

What the 29 s and 74 s of the transcript stage are made of, measured separately:

- loading whisper `base`: 6.5 s, once per process
- one whisper pass over the full 179 s mix: 41 s in a cold process, of which
  about 6 s is the six extra `detect_language` calls that `_language_stability`
  makes, one per 30 s window, each a separate encoder pass
- loading `paraphrase-multilingual-MiniLM-L12-v2`: 17.5 s, once per process,
  and it is why pass B's transcript stage is 45 s longer than pass A's

The melodic stage is 24.5 s cold and 17.8 s warm. The difference is the two
candidate transcriptions. Note that `pipeline.prewarm` warms **fingerprint and
harmonic only**; `melodic.representation` documents itself as a level 0
artifact ("without a warm cache, level 2 does not fit in any budget") but
nothing ever prewarms it, so the first analysis of a set pays for every
shortlisted candidate on the request path.

### Detector D, lyrics

The first real test of the confidence gate, and it behaved:

| | |
|---|---|
| words recognised in the query | 240 |
| `asr_confidence`, first pass on the full mix | **0.6837** |
| threshold | 0.60 |
| language | `en`, stable across all six windows |
| **gate** | **passed on the first pass** |
| demucs | **did not run** |
| second whisper pass | did not happen |
| `used_separation` | `false` |

The margin is 0.084. That is thin for a 1967 live vocal over a full band, and
it is the whole point of the design that separation stays conditional - but a
threshold of 0.70 would have sent this recording down the expensive branch.

Against the two candidates:

| | cand_07, The Beatles | cand_08, Bob Marley |
|---|---|---|
| relationship to the query | the same lyrics | different lyrics |
| `jaccard` | **0.21875** | **0.0** |
| `semantic_sim` | **0.5196** | **0.4221** |
| matched spans | 23 | 5 |
| longest matched span | 87 characters, 4.52-18.20 s | 9 characters |

`jaccard` separates the two cleanly: 0.219 against exactly 0.0. `semantic_sim`
barely separates them at all - 0.52 against 0.42 for a text that has nothing to
do with the query. The multilingual MiniLM puts any two English song lyrics in
roughly the same neighbourhood, so the semantic number carries much less
discriminating power than the literal one. That is a calibration question, not
a bug, but any fusion weight placed on `semantic_sim` should be set knowing the
floor is around 0.42 rather than around 0.

The five spans on cand_08 are all nine characters or shorter: common word runs,
not shared lyrics.

### The branch the gate did not take

demucs never ran in either pass, so it was measured separately on the same clip,
same machine, same throttle, by calling the detector's own `_demucs` and
`_whisper` directly:

| step | time | notes |
|---|---|---|
| pass 1, whisper on the full 179 s mix | 41.2 s | `asr_confidence` 0.6837, 240 words, gate passes |
| demucs `htdemucs` on the full clip | **391.2 s** | 6.5 minutes for 179 s of audio |
| pass 2, whisper on the separated vocal | 46.0 s | `asr_confidence` 0.7353, 122 words, gate passes |
| **total had the gate rejected** | **478.4 s** | against 41.2 s for the accepted path |

So the conditional cost of decision D3 is a **factor of 11.6** on the transcript
stage, and 478 s against a 30 s budget is sixteen times over. Deferring
separation until the gate rejects is clearly the right call - but it also means
the system has two performance regimes an order of magnitude apart, and which
one a recording lands in is decided by a single threshold with, on this
recording, 0.084 of margin.

Two things in the second pass are worth recording. Separation does raise
confidence, 0.6837 to 0.7353, which is what the design assumes. But it also
**halves the word count**, 240 down to 122: the separated vocal is cleaner and
much sparser. The gate looks only at mean confidence, so it cannot see that the
second pass bought certainty by discarding half the material - and it is the
second pass whose transcript reaches the comparison. On a recording where the
gate does reject, `jaccard` will be computed against roughly half the words.

Peak RSS of that process, with whisper and demucs both resident, was **1812 MiB**.

### Detector C, melody

| | cand_07 | cand_08 |
|---|---|---|
| `longest_common_run` | 4 | 3 |
| `ms_distance` | 0.5278 | 0.4573 |
| matched n-grams | 2 | 0 |

**The sign is wrong.** cand_08, which shares nothing with the query, gets the
*better* (lower) Mongeau-Sankoff distance of the two. The reason is visible in
the code rather than in the numbers: `MelodicDetector.run` accepts
`separated_vocals`, and `pipeline` never passes it. Section 7.4 step 1 says the
separation is computed once by detector D and shared with C; in practice
`transcribe_with_gate` computes `vocals` as a local variable and discards it,
`LyricsDetector` has no way to hand it back, and `pipeline` calls
`DETECTORS["melodic"].run(clip, shortlisted)` with two arguments. So the melody
is always transcribed from the full mix - exactly the degenerate case
`transcribe_melody`'s own docstring warns about, where basic-pitch mostly picks
the drums and the accompaniment. On this run demucs never ran at all, so there
was nothing to share either way, but the wiring is missing regardless of the
gate.

Until that is connected, detector C's numbers on polyphonic material should not
be read as melodic evidence.

### Verdict

| | cand_07 | cand_08 |
|---|---|---|
| rank | 1 | 2 |
| `verdict_class` | NONE | NONE |
| `probability` | 0.02850 | 0.02073 |
| `probability_status` | `uncalibrated` | `uncalibrated` |
| harmonic `qmax_score` | 0.02850 | 0.02073 |
| harmonic transposition | -4 | -3 |
| harmonic `tempo_ratio` | 1.1818 | 1.0 |
| harmonic coverage | 0.0284 | 0.0206 |
| fingerprint | dropped below the noise floor | dropped below the noise floor |
| `mean_idf` | 3.095 | 1.642 |
| corpus frequency | 109 / 291 | 277 / 291 |

**The class did not change between the preliminary and the final verdict**:
NONE at level 1, NONE at level 2, and the probability is byte-identical
(0.02850 both times). The spec allows the class to move at level 2; here
neither detector C nor detector D moved it, because the number that decides is
the harmonic `qmax_score` and at 0.0285 it is an order of magnitude below
`VERSION_QMAX`. That is the same 0.03-on-a-real-cover problem the harmonic
recalibration is addressing, and it means this run cannot yet demonstrate a
level 2 promotion.

One reporting detail worth noting: both shortlisted candidates fell below
`FINGERPRINT_NOISE_FLOOR` and the fingerprint detector drops such candidates
from its result set entirely. Downstream this surfaces as `not_applicable, no
result for this candidate` - the same shape as "we never checked" - for two
candidates that were in fact checked and found not to match. Section 7.0 is
emphatic that not applicable is not zero; this is the mirror of that, a measured
zero rendered as not applicable.

### Memory

Measured as `VmHWM` of the uvicorn process.

| state | peak |
|---|---|
| API started, before any model | 126 MiB |
| after a run with whisper + basic-pitch (pass A) | **963 MiB** |
| after a run that also loads the embedding model (pass B) | **1.70 GiB** |
| whisper + demucs resident, measured out of process | **1812 MiB** |

**The production limit of 1.3 GB does not hold.** whisper plus basic-pitch alone
sit at 963 MiB, and the first `semantic_sim` comparison adds another 760 MiB and
takes the process to 1.70 GiB. Both numbers are already above or close to the
limit before demucs is loaded at all, and demucs is the branch the gate takes on
any recording whose vocal is harder than this one. Either the limit rises well
past 2 GB, or the models do not all live in one process.

Note that all three models are held by `lru_cache(maxsize=1)` for the life of
the process, so this is a floor that never comes back down, not a transient
peak.

## The lyrics gap

Every candidate in `data/candidates/demo_01.json` has `lyrics_path: null`.
`LyricsDetector._compare_candidates` requires it and returns `not_applicable,
no_lyrics` without it, so on the committed demo set detector D transcribes the
query, spends 29 seconds doing it, runs its gate, and then produces no number
for any candidate. Pass A above is exactly that outcome.

Section 7.3 is deliberate that the reference side is not transcribed - whisper
on the candidate side is a cost counted in thousands of recordings for text an
open lyrics database already has - but no such fetcher exists yet, so there is
nothing to fill the field with.

To get pass B's numbers the reference texts were produced on the test machine
by transcribing the two candidates once, offline, and writing them to
`data/lyrics/`, which is gitignored. They are a stand-in for the lyrics
database, they are not committed, and the manifest that points at them
(`demo_01_lyrics`) exists only on the test machine. The committed demo set is
untouched.

## After vocal sharing

Section 7.4 step 1 is now wired: detector D's separation is collected by the
pipeline and handed to detector C, `melodic.representation` is prewarmed with
the other two level 0 artifacts, and every melodic result carries
`used_separation` so the number can be read for what it is.

Same machine, same throttle, same clip and the same `demo_01_lyrics` manifest
as pass B above. `harmonic.py` is still at `dba0bea`, so level 1 has not moved.
The API ran on port 8077 without `ORIGIN_MOCK` and is stopped again.

| stage | pass B, before | after vocal sharing |
|---|---|---|
| ingest | 1.17 s | 1.76 s |
| fingerprint | 1.12 s | 1.43 s |
| harmonic | 3.48 s | 3.75 s |
| shortlist + commonality | 1.48 s | 0.61 s |
| **preliminary verdict at** | **7.68 s** | **7.82 s** |
| transcript | 73.96 s | 38.84 s |
| melodic | 17.78 s | 11.10 s |
| **final verdict at** | **99.42 s** | **57.76 s** |

The melodic stage drops from 17.8 s to 11.1 s because the candidate melodies
now come out of the level 0 cache instead of being transcribed on the request
path. The transcript stage is 35 s shorter, and that is **not** this change:
the same two model loads and the same single whisper pass happen in both runs.
It is the shared box, whose load average moved between the two measurements -
which is exactly why the earlier numbers were recorded as upper bounds. The
final verdict is still nearly twice the 30 s target either way.

### The melody

| | cand_07, The Beatles | cand_08, Bob Marley |
|---|---|---|
| `longest_common_run` | 4 | 3 |
| `ms_distance` | **0.5278** | **0.4573** |
| matched n-grams | 2 | 0 |
| `used_separation` | **false** | **false** |

**The numbers did not move, and that is the correct outcome for this
recording.** The confidence gate passes on the first pass here
(`asr_confidence` 0.6837 against a threshold of 0.60), so demucs never runs,
there is no vocal track for detector D to share, and detector C reads the full
mix exactly as before. What changed is that the result now says so: before this
run, "0.4573" and "0.4573 measured over drums, bass and accompaniment" were the
same string on the wire.

The decision behind that: when there is no separation to share, detector C
transcribes the mix rather than separating on its own. A separation of its own
costs 391 s on this clip - more than ten times the whole final-verdict budget -
for a detector that sits first on the retreat ladder of section 18. So the
melody accepts the worse input and labels it, and the unlabelled version of
this number is gone.

The sign therefore stays wrong on this recording: cand_08, which shares nothing
with the query, still gets the lower Mongeau-Sankoff distance. That is now a
statement about basic-pitch on a full mix rather than an unexplained result,
and the label on the field says which of the two regimes produced it.

### The lyrics, unchanged as expected

| | cand_07 | cand_08 |
|---|---|---|
| `jaccard` | 0.21875 | 0.0 |
| `semantic_sim` | 0.5196 | 0.4221 |
| matched spans | 23 (longest 106 characters) | 5 (longest 9 characters) |
| `used_separation` | false | false |

### Prewarming the melody

`pipeline.prewarm` now warms three detectors rather than two, and the API log
names the same eight candidates for all of them:

    [origin] fingerprint: no representation for ['cand_01' ... 'cand_10']
    [origin] harmonic:    no representation for ['cand_01' ... 'cand_10']
    [origin] melodic:     no representation for ['cand_01' ... 'cand_10']

Melodic prewarming is sequential, not pooled like the fingerprint: basic-pitch
holds an ONNX session per thread and the process already sits near the
container's memory ceiling. Without basic-pitch installed it is one dictionary
and no file is decoded, so the level 0 path stays free on a machine with no
heavy models. The price is paid at startup, and it is paid on the test machine
too: `tests/test_pipeline.py`, `tests/test_lyrics.py` and `tests/test_melodic.py`
together take 12 m 43 s with the heavy models present, because each pipeline
test warms three candidate melodies into its own temporary cache directory.
Without basic-pitch the same three files cost nothing at all.

### What sharing actually buys, measured on the branch the gate does not take

The run above cannot show the effect of the fix, because its gate passes and
there is nothing to share. So the same pipeline was run once more with a single
value changed: `ASR_CONFIDENCE_THRESHOLD` raised from 0.60 to **0.70**, the
value this report already noted would send this recording down the expensive
branch. Nothing else differs. Detector D then rejects the first pass, demucs
runs once, its vocal track goes into the sink, and detector C reads it.

In process rather than through the API, because the threshold is a module
constant and not configuration; every other part of the path is the ordinary
pipeline. Same box, same throttle, same manifest.

| stage | at threshold 0.60 (gate passes) | at threshold 0.70 (gate rejects) |
|---|---|---|
| preliminary verdict at | 7.82 s | 5.68 s |
| transcript, including separation | 38.84 s | 152.56 s |
| melodic | 11.10 s | 4.24 s |
| **final verdict at** | **57.76 s** | **162.45 s** |
| peak RSS of the process | - | **1975 MiB** |

| detector C | cand_07, The Beatles | cand_08, Bob Marley |
|---|---|---|
| `ms_distance`, melody from the full mix | 0.5278 | **0.4573** |
| `ms_distance`, melody from the shared vocals | **0.4576** | 0.5186 |
| `longest_common_run`, mix | 4 | 3 |
| `longest_common_run`, vocals | 3 | 3 |
| `used_separation` | true | true |

**The sign is right when the vocals are shared.** The cover gets the lower
distance, 0.4576 against 0.5186, and the ordering the full-mix run produced was
an artifact of basic-pitch following the drums and the accompaniment. That is
what section 7.4 step 1 was for. The melodic stage also gets *faster* on a
separated track, 11.1 s down to 4.24 s: the vocal line yields far fewer note
events than a full band does.

The lyrics side of the same run repeats the warning already recorded above.
Separation lifts `asr_confidence` from 0.6837 to 0.8365, and `jaccard` against
the true source falls from 0.219 to 0.078, because the second pass keeps far
fewer words. `semantic_sim` moves 0.520 to 0.566 for the cover and 0.422 to
0.434 for the unrelated track, so the gap it offers stays about as narrow as
before.

One number for the container limit: with the pipeline, whisper, demucs,
basic-pitch and the embedding model all resident in one process, peak RSS was
**1975 MiB** - above the 1812 MiB measured out of process, and the reason
`docker-compose.prod.yml` now asks for 2560m.
