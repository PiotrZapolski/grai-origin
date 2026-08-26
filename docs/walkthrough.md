# Walkthrough, 90 seconds

Four moves, in this order: problem, solution, result, limitation.
**We state the limitation ourselves, before anyone asks** - that is stronger than
admitting it after a question from the room.

---

## 1. Problem (15 s)

Somebody uploads a recording. The question sounds like "is this someone else's?",
but it is **four questions at once**, not one:

- is this the same **fixation** (phonogram),
- is this a different performance of the same **work** (composition),
- is this a **snippet** taken from someone else's fixation,
- or is this simply a **genre convention** that half a million recordings share.

Tools that answer this with a single similarity number confuse those four cases.
The four questions have different rights layers and different consequences, so the
answer "87% similarity" is not an answer to any of them.

## 2. Solution (25 s)

Four independent detectors, each answering a different question, and an **explicit
decision tree** that assembles an evidence class out of them. No weighted average:
averaging the results of detectors answering different questions destroys the
information about the kind of match.

The work splits not by detector, but by **when it can execute**:

| Level | When | What it does |
|---|---|---|
| 0 | before the show | fingerprints and chromagrams of the candidates, IDF corpus |
| 1 | live, target 5 s | ingest, fingerprint, harmonic similarity, shortlisting, commonality, **verdict** |
| 2 | in the background, target 30 s | lyrics, melody, **upgrading the verdict** |

**The verdict in five seconds, the evidence arriving over the next thirty.** The
verdict appears after level 1 and grows in front of the viewer. Level 2 **upgrades
it and never takes it away**: a failure of a level 2 detector leaves the class from
level 1 standing.

The fifth demo case matters more than the first four. Everyone will show that they
find something. We show that the system can say **"I found a similarity and I
consider it immaterial, and here is why"** - the commonality filter computes the
IDF of the chord pattern over the corpus and degrades a work-layer class to
`COMMON` when the pattern turns out to be well worn.

## 3. Result (35 s)

A live demo, from **local files**, not from addresses. That is the only safeguard
against there being no internet in the room.

Screen E2 shows the run stage by stage. Every event carries the execution level, so
you can see that the verdict landed before level 2, not after it. Screen E4 gives
A/B listening synchronized to the matched segment - for audio the only real check
is the ear.

Numbers from the run on the server (2026-08-26), corpus of 291 works, on
**synthetic material** - a query built by transforming a candidate:

| Case | Class | The number that settled it |
|---|---|---|
| reupload with mp3 96k recompression | `EXACT` | `peak_ratio` 0.99 over a 59.8 s segment |
| heavily processed version | `MODIFIED` | `peak_ratio` 0.58 with `tempo_ratio` 1.03, `qmax` 0.69 |
| unrelated work | `NONE` | `qmax` 0.05, below every threshold |

On real music the numbers look different, and they are written down in "The
first real run, on music" below. That section is the honest one.

## 4. Limitation (15 s)

We say this ourselves, before anyone asks (section 20 of the specification):

> Our thresholds are **calibrated on covers**, because that is the data we got. We
> do not know whether they hold up on samples and remixes, and that is exactly the
> class of cases where the legal stakes are highest. The next step is to build a
> labeled set of samples and repeat the calibration for the `EXCERPT` class.

Plus two things the system says about itself on screen:

- **The probability today is raw, not calibrated.** There is no calibration model,
  so `probability_status` says `uncalibrated`, and the number next to an entry is
  the output of the detector that settled the class. The UI distinguishes that
  visually.
- **This is a technical signal, not a legal opinion.** The note sits in the
  contract, not in a template - a result cannot be built without it.

---

# The first real run, on music (before recalibration)

Everything in this section is the run as it happened, with the pre-calibration
thresholds - binarisation percentile 10, `VERSION_QMAX` 0.55. It was
recalibrated the same day; see [Resolved](#resolved) at the end of the section.
The numbers below are kept as they were measured, because they are the record
of what the system did before that change.

2026-08-26, on the test server, `ORIGIN_MOCK` off, candidate set `demo_01`,
IDF corpus of 291 works. The first time the engine saw a recording nobody had
manufactured for it.

**Query:** `data/audio/query_demo_01.wav`, Aretha Franklin, "Let It Be", 3:31.
Ingest kept the highest-energy 180 s (`MAX_DURATION_S`), cutting 30.0 s off the
front, and split it into 36 windows.

**Candidates with audio:** `cand_07` - The Beatles, "Let It Be", 4:02, the same
work in a different performance. `cand_08` - Bob Marley & The Wailers, "No
Woman, No Cry", 7:07, a different work that shares the I-V-vi-IV progression.
The remaining eight candidates of the set have no file and came back as
`audio_missing`, one word, from every detector.

**Timing.** The preliminary verdict landed 3.96 s after the stream opened, the
final one in the same second - level 2 has no models, so it had nothing to add.

## What actually came out

| | `cand_07` (Beatles) | `cand_08` (Marley) |
|---|---|---|
| expected | `VERSION` | `VERSION` degraded to `COMMON`, or `NONE` |
| **got** | **`NONE`** | **`NONE`** |
| `peak_ratio` | no measurement (raw 0.015, below the 0.25 noise floor) | no measurement (raw 0.0118) |
| `qmax_score` | 0.0285 | 0.0207 |
| `coverage` | 0.0284 | 0.0206 |
| `transposition` | -4 | -3 |
| `tempo_ratio` | 1.182 | 1.000 |
| `mean_idf` | 3.095 | 1.642 |
| `corpus_frequency` | 109 of 291 | 277 of 291 |
| `probability` | 0.0285, `uncalibrated` | 0.0207, `uncalibrated` |

The ranking put `cand_07` first and `cand_08` second, which is the right order.
Everything else missed.

## Why

**1. The fingerprint was right to stay silent.** Raw `peak_ratio` came out at
0.015 for `cand_07` (533 matched hashes over the 80.2-186.2 s span) and 0.0118
for `cand_08` (1694 hashes, 2 repetitions). Both sit far under the
`FINGERPRINT_NOISE_FLOOR` of 0.25, so the detector reported no number at all -
correctly. Neither candidate is the same fixation as the query, and that is
exactly what the noise floor is there to say.

**2. `VERSION_QMAX` = 0.55 is not a threshold measured on covers.** Three
control measurements from the same material make the scale visible:

| Pair | `qmax` |
|---|---|
| `cand_07` against itself | 1.000 |
| query (Aretha) against `cand_07` (Beatles) - the true cover | 0.0285 |
| query against `cand_08` - unrelated work | 0.0207 |
| `cand_07` against `cand_08` - unrelated works | 0.018 |

A cover scores above an unrelated pair, but by 0.008, not by half a scale. The
0.55 threshold was set on synthetic material where the "cover" is a
time-stretched copy of the same recording - the regime that returns exactly
1.000 above. Two genuinely different performances share a chord progression,
not a chroma trajectory: Aretha's arrangement is gospel, four semitones away
and 18% slower, with different fills and a reharmonised turnaround. The Qmax
gap penalty (`gamma_onset` 5.0) against a 10% mutual-neighbourhood sieve breaks
the diagonal every few frames, and the longest cumulative run ends at 11 frames
out of 386 - 5.5 seconds. `coverage` is that same 11 frames, which is why it
tracks `qmax` almost exactly.

**3. The 180-second cut compares the wrong minutes.** `MAX_DURATION_S` = 180
trims every recording to its highest-energy three minutes. The query lost 30 s
from the front, `cand_07` lost 62 s, and `cand_08`, at 7:07, lost 247 s. The
two windows that reach Qmax are therefore not the same section of the song, and
the alignment pays for that before the algorithm starts.

**4. The transformation grid never ran.** Section 7.1 starts the 143 variants
only when harmonic similarity says "this is that work", that is `qmax` >=
`VERSION_QMAX`. At 0.0285 the condition was nowhere near, so the second
fingerprint pass had no candidates.

**5. The commonality half of the expectation held.** `mean_idf` is 3.095 for
`cand_07` and 1.642 for `cand_08`, both under the corpus threshold of 4.605, and
`cand_08`'s matched pattern occurs in 277 of the 291 works. Had either
candidate reached a work-layer class, both would have been degraded to `COMMON`
- which is what the corpus was supposed to say about a I-V-vi-IV progression.
One caveat: `mean_idf` is computed on the chords of the **matched segment**, and
that segment is 11 frames long, so these two numbers rest on five chords.

## What this run establishes

The pipeline runs end to end on real audio, in four seconds, and orders the
candidates correctly. What it does not do is reach the `VERSION` class, and the
reason is not the wiring but the number: `VERSION_QMAX` was never calibrated on
real cover pairs, only on synthetic ones. Moving it by hand to 0.03 would fit
this single run and mean nothing - the gap between a cover and an unrelated
track here is 0.008, which is inside the noise of one measurement. The honest
next step is the one section 20 already names: a labelled set of real cover
pairs and a calibration run, with a re-examination of the 180 s cut and of the
gap penalty at the same time.

## Resolved

That next step ran the same day, 2026-08-26. The sieve was recalibrated on real
audio: the binarisation percentile moved from **10 to 30** and `VERSION_QMAX`
from **0.55 to 0.25** (`VERSION_COVERAGE` stayed at 0.50). The 10th-percentile
mutual-neighbour sieve was what clipped the real diagonal to 11 frames; at 30
the same Aretha/Beatles pair scores `qmax` **0.293** and `coverage` 0.655,
against a maximum of 0.222 over 541 real negative pairs from the corpus, so
0.25 sits in that gap.

The measurement, including why 30 and not 40, is in
[`calibration-harmonic.md`](calibration-harmonic.md). Its own limit is stated
there and carries over here: the false-alarm side is measured on 541 pairs, the
recall side still rests on this one cover pair. Nothing above has been rewritten
to the new numbers - it is what the engine did before the change.

---

# What fell apart while running through the scenarios

A record from the runs on the server, not a wish list. Every item is something that
actually only surfaced once the whole thing was run.

### 1. Shortlisting fell over on a candidate with no audio

`shortlist.select` sorts candidates by the harmonic descriptor and reaches for it
through `harmonic.representation`, which for a candidate with no file raises an
exception **inside the sort key**. One missing file therefore wiped out the whole
shortlisting, and with it the whole ranking.

Fixed in `pipeline._do_odsiewu`: only candidates for which harmonic similarity
returned `ok` go into shortlisting. When it returned that for nobody, the
fingerprint takes over, and when that stays silent too - the whole set in manifest
order. Better to shortlist badly than to show nothing.

### 2. Every detector named a missing file differently

A candidate with no audio got `"no level 0 fingerprint for this candidate; run
prewarm"` from the fingerprint detector, and `"IngestError: no such file: ..."`
from the harmonic one. Both are true and both describe the **symptom** that the
given detector sees on its own side. The cause is one, and the front end has no way
to recognize it without parsing the exception text.

Fixed in `pipeline._powod`: when the file is not on disk, the reason seen by the
front end is `audio_missing`, one word, the same in every detector.

### 3. The grid of 143 transformations had no way to run

Section 7.1 starts the grid only when the fingerprint stays silent **and harmonic
similarity says "this is that work"**. The condition requires a harmonic result,
and section 12 puts the fingerprint before harmonic similarity in the event order.
With a single fingerprint pass the condition had no way to exist: the context was
always empty and the grid never ran.

Fixed: the fingerprint runs twice. The first pass on the whole set, without
context. After harmonic similarity, a second one, **only on the candidates meeting
the 7.1 condition**, with context, and its results overwrite the first ones. On the
run with material sped up by 6% the grid recovered a transformation of
`tempo_ratio` 1.12 and `semitones` 2.0, which the first pass did not see at all.

### 4. Rules 1 and 2 of the tree argue over sped-up material

Scenario 3 (sped up, raised by a semitone) came out as `EXACT`, not `MODIFIED`.
This is not a pipeline or measurement error: the transformation grid recovered a
`peak_ratio` of 0.80 over a 52.7 s segment, and **rule 1 does not check whether the
match required a transformation**, so it wins ahead of rule 2. The measurement is
correct (`transform` carries the tempo and semitones); what is in dispute is the
rule order in section 9.1.

Fixed in `fusion.decide`: rule 1 now also requires `A.transform == null`. A match
that exists only after the query has been transformed is by definition not an
identical recording, so rule 1 steps aside and rule 2 classifies it as
`MODIFIED`. Section 9.1 of the specification carries the same condition and an
amendment note saying why.

### 5. The `VERSION` class was not reachable on doctored material

An attempt to destroy a recording so that the fingerprint would be lost while
harmonic similarity survived (1200 Hz low-pass, time-stretch, compression,
distortion) ended in the class `MODIFIED` with a `peak_ratio` of 0.58 - the
transformation grid recovered the fingerprint regardless. The conclusion:
**`VERSION` requires a different performance, not a processed copy of the same
recording**, and it cannot be shown without a real cover in the candidate set.

The real cover has since been run, and it did not reach `VERSION` either - see
"The first real run, on music" above. The obstacle turned out to be the
`VERSION_QMAX` threshold, not the material.

### 6. The heavy models are absent and that is the normal mode

Level 2 today emits `failed` with the reason `model_unavailable` for both
detectors. Fusion recomputes on what it has, and the final verdict comes out of the
same signals as the preliminary one. The verdict **does not disappear**, and that
is precisely the property level 2 is meant to guarantee. The `verdict final` event
carries `previous_class`, so the front end has something to show that the class did
not change.
