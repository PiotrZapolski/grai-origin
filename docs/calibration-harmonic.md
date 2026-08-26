# Calibration of the harmonic detector, 2026-08-26

What was measured: the binarisation percentile of the Qmax sieve in
`origin.detectors.harmonic`, and the `VERSION_QMAX` / `VERSION_COVERAGE`
thresholds that read its output.

Result: the percentile moves from **10 to 30**, `VERSION_QMAX` from **0.55 to
0.25**, `VERSION_COVERAGE` stays at **0.50**.

**Read this first.** This is a calibration of the FALSE-ALARM side with a single
positive anchor. The set is 541 pairs of unrelated real works and **one** real
cover pair. The corpus could not supply more: it holds one performance per work
by construction, so it yields zero cover pairs, and no new audio can be fetched
from this machine. Everything said below about precision is measured;
everything about recall rests on that one pair.

## Why it needed measuring

The first real run (see `walkthrough.md`) gave `qmax_score` 0.0285 for Aretha
Franklin's "Let It Be" against the Beatles' original and 0.0207 against an
unrelated song, with the threshold at 0.55. Synthetic covers - a time-stretched
copy of the same recording - score 1.000, so the threshold had never been held
against a real performance.

The raw cosine matrix between the two "Let It Be" performances has a mean of
0.778 and a p90 of 0.938, with 48% of the cells above 0.8. The chroma sequences
agree. What discarded the agreement was the 10th-percentile mutual-neighbour
sieve: on real audio - vocals, bass, distortion, reverb - frame-to-frame
distances are far larger than on four clean synthetic chords, so the sieve
clipped the real diagonal down to 11 frames out of 386.

## The data

**A note on what this set is and is not.** The intended source of positives was
the IDF corpus: 291 tracks in `data/audio/corpus`, drawn from the
SecondHandSongs export. It yields **zero cover pairs**. The selection script
that built the corpus took `wyk[0]` - exactly one performance per `work_title` -
so the 291 files are 291 distinct works by construction. That was confirmed
independently: every one of the 291 YouTube ids was resolved through the oEmbed
endpoint and the titles were grouped; there is not a single repeated work among
them. The corpus TSV that carried `work_title` lived in a scratch directory and
no longer exists, and the SHS export it came from is gone as well, so the
grouping could not be rebuilt from the source either. New audio cannot be
fetched from the server - YouTube answers "Sign in to confirm you're not a bot"
to the machine's address, which is the same block recorded in
`download-throughput.md`.

So the positive side of this calibration rests on **one** real cover pair, the
only one on the disk. The negative side rests on 541 pairs and is the part of
this document that carries weight.

| | pairs | what they are |
|---|---|---|
| positives | 1 | Aretha Franklin "Let It Be" against The Beatles "Let It Be" |
| negatives | 541 | 400 corpus-vs-corpus, 60 query-vs-corpus, 40 Beatles-vs-corpus, 40 Marley-vs-corpus, 1 Aretha-vs-Marley |

All 542 pairs are real recordings, ingested through the normal path (loudness
normalisation, 180 s cut, CQT chroma at 2 Hz) and read from the `harm-*` cache.
Every pair was scored at every percentile in {10, 20, 30, 40, 50, 60} over all
twelve rotations, taking the best rotation, exactly as `qmax()` does.

## The sweep

`qmax_score`. POS is the single real cover pair; the rest is the distribution
over the 541 unrelated pairs.

| pct | POS | neg min | neg med | neg p90 | neg p99 | neg max | POS - neg max | AUC | d' | chance floor |
|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 0.028 | 0.015 | 0.024 | 0.034 | 0.050 | 0.057 | **-0.029** | 0.748 | 0.47 | 0.02 |
| 20 | 0.110 | 0.023 | 0.041 | 0.058 | 0.087 | 0.123 | **-0.013** | 0.996 | 5.19 | 0.04 |
| **30** | **0.293** | 0.032 | 0.072 | 0.109 | 0.156 | 0.222 | +0.071 | **1.000** | **8.53** | 0.08 |
| 40 | 0.494 | 0.061 | 0.162 | 0.230 | 0.279 | 0.321 | +0.173 | 1.000 | 7.01 | 0.32 |
| 50 | 0.626 | 0.146 | 0.315 | 0.394 | 0.473 | 0.504 | +0.122 | 1.000 | 5.21 | 0.54 |
| 60 | 0.727 | 0.294 | 0.500 | 0.581 | 0.667 | 0.716 | +0.011 | 1.000 | 3.55 | 0.76 |

`coverage`, the same pairs and the same best rotation:

| pct | POS | neg min | neg med | neg p90 | neg p99 | neg max | neg above 0.40 | neg above 0.50 |
|---|---|---|---|---|---|---|---|---|
| 10 | 0.028 | 0.013 | 0.021 | 0.028 | 0.038 | 0.098 | 0.0% | 0.0% |
| 20 | 0.570 | 0.021 | 0.039 | 0.080 | 0.168 | 0.211 | 0.0% | 0.0% |
| **30** | **0.655** | 0.031 | 0.119 | 0.309 | 0.565 | 0.722 | **5.4%** | **2.0%** |
| 40 | 0.711 | 0.095 | 0.438 | 0.624 | 0.701 | 0.711 | 56.9% | 36.6% |
| 50 | 0.758 | 0.245 | 0.621 | 0.722 | 0.750 | 0.771 | - | 85.0% |
| 60 | 0.781 | 0.317 | 0.696 | 0.760 | 0.789 | 0.794 | - | 92.8% |

Negatives per group (median / maximum), so that no single group drives the tail:

| group | 10 | 20 | 30 | 40 | 50 | 60 |
|---|---|---|---|---|---|---|
| corpus vs corpus (400) | 0.026/0.057 | 0.043/0.123 | 0.073/0.222 | 0.166/0.321 | 0.318/0.504 | 0.502/0.716 |
| query vs corpus (60) | 0.021/0.045 | 0.039/0.081 | 0.063/0.168 | 0.164/0.279 | 0.316/0.440 | 0.492/0.634 |
| Beatles vs corpus (40) | 0.021/0.031 | 0.035/0.059 | 0.066/0.129 | 0.152/0.285 | 0.309/0.433 | 0.502/0.625 |
| Marley vs corpus (40) | 0.021/0.029 | 0.036/0.051 | 0.067/0.098 | 0.142/0.205 | 0.289/0.384 | 0.499/0.597 |
| Aretha vs Marley (1) | 0.021 | 0.041 | 0.073 | 0.214 | 0.404 | 0.614 |

### The chance floor

The sieve keeps a fixed FRACTION of the cells whatever the material, so every
percentile carries a score that two sequences reach by chaining accidents
alone. Measured on structureless chroma (frames drawn independently), at three
lengths - 200, 386 and 800 frames - it is length-independent:

| pct | 10 | 20 | 30 | 40 | 50 | 60 |
|---|---|---|---|---|---|---|
| floor | 0.02 | 0.04 | 0.08 | 0.32 | 0.54 | 0.76 |

Above 40 most of the number is that floor rather than an alignment. The signal
above chance - POS minus floor - peaks at 30 (0.213), against 0.174 at 40 and
0.087 at 50.

## The decision

**Percentile 30**, for four reasons, in order of weight:

1. **Coverage stays evidence.** At 40 the sieve inflates the alignment path
   until 36.6% of unrelated pairs reach coverage above 0.50 and 56.9% above
   0.40. Rule 4 of section 9.1 requires `coverage > 0.50` and rule 5 requires
   `coverage < 0.40`; at 40 the first is satisfied by a third of all unrelated
   pairs and the second is denied to more than half of them, so both stop
   deciding anything. The verdict prints coverage as a reason ("coverage 0.71
   above 0.50") - a sentence that is also true of a third of unrelated pairs is
   not evidence. At 30 only 2.0% of unrelated pairs pass 0.50.
2. **Best standardised separation.** d' peaks at 30 (8.53 against 7.01 at 40),
   and the cover sits at 4.08x the negative median, against 3.05x at 40.
3. **The score still means alignment.** See the chance floor above.
4. **AUC 1.000.** From 30 upwards the cover scores above all 541 unrelated
   pairs. At 10 and 20 it does not: at 10 the cover (0.028) scores BELOW the
   worst unrelated pair (0.057), which is the failure the whole exercise
   started from, and at 20 it is still below the maximum (0.110 against 0.123).

40 wins on one measure only - the raw gap over the observed negative maximum
(0.173 against 0.071) - and loses coverage entirely to buy it.

**`VERSION_QMAX` = 0.25.** The cover is at 0.293, the 541 unrelated pairs top
out at 0.222 with a p99 of 0.156. 0.25 sits in that gap: above the 99.8th
percentile of the negatives, 0.043 below the cover.

**`VERSION_COVERAGE` = 0.50**, unchanged, now measured: the cover reaches 0.655
and 2.0% of unrelated pairs pass 0.50.

Rule 4 takes both together, and that is the number that matters for the
precision target of section 10.3:

| threshold pair at pct 30 | unrelated pairs passing | cover passes |
|---|---|---|
| qmax > 0.15 and coverage > 0.50 | 2 of 541 (0.37%) | yes |
| qmax > 0.20 and coverage > 0.50 | 0 of 541 (0.00%) | yes |
| **qmax > 0.25 and coverage > 0.50** | **0 of 541 (0.00%)** | **yes** |
| qmax > 0.25 and coverage > 0.60 | 0 of 541 (0.00%) | yes |

Precision on the measured set is 1.00 with recall 1.00. With 0 false alarms in
541 trials the upper bound on the false-alarm rate is 0.55% at 95% confidence
(rule of three). The spec asks for precision >= 0.95; the measurement supports
that claim on the false-alarm side.

What it does not support is a claim about **recall**, and this is the honest
limit of this document: one positive pair. "Precision at recall >= 0.80" cannot
be computed from a single positive, and neither can the shape of the positive
distribution. A cover that sits 15% below this one in `qmax` would be missed.
The follow-up is the one section 20 already names and this run could not do: a
labelled set of real cover pairs, fetched over a connection YouTube does not
block, and a repeat of this sweep.

## What this changed in the tests

Two synthetic negative controls in `tests/test_harmonic.py` broke, and the
reason is worth recording, because it is the same effect from the other side.

`_synthetic_chromagram` draws twenty-four chord templates in eight-frame
blocks. Two independent draws share that vocabulary, so a third of their frames
are near-identical, and the pair scores **0.338** at percentile 30 - above the
calibrated threshold - while 541 pairs of unrelated real works have a median of
0.072 and a maximum of 0.222. The toy generator is not a model of two different
pieces of music, and this was checked rather than assumed: a larger continuous
chord vocabulary gives 0.282, disjoint major/minor vocabularies 0.280, longer
blocks 0.333, a 400-frame alien 0.362. The scores stay in the same band because
the sieve is rank-based - it does not care how far apart the frames are, only
how they order.

Neither threshold was touched to accommodate this. Instead:

- `_unrelated_chromagram` was added: frames drawn independently, no vocabulary
  to share, mutual cosine 0.69 against 0.78 for two real recordings. It scores
  0.098 at percentile 30. Assertions against `VERSION_QMAX` are made on that
  material.
- `test_alien_material_stays_far_below_the_version_threshold` keeps its 0.4 bar
  on the old material unchanged and adds the assertion against `VERSION_QMAX`
  on the new one.
- `test_two_segments_across_a_gap_do_not_add_up_to_a_cover` had a candidate
  built from 60% of the query verbatim; it passed at percentile 10 only because
  the sieve was clipping every diagonal. The candidate is now 80% alien
  material carrying two ten-second quotes, which is what the docstring always
  claimed, and the test gained an assertion it never made: without the gap
  penalties the two quotes sum ACROSS the gap and cross the threshold
  (0.115 with penalties, 0.590 without).

`tests/test_config.py` pinned `VERSION_QMAX` to its 0.55 starting value and now
pins it to 0.25.

## How to repeat it

On the server, with the chroma cache warm:

```bash
cd /opt/grai-origin
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4
nice -n 19 taskset -c 0-3 .venv/bin/python - <<'PY'
from origin.detectors import harmonic as h
a = h.representation("data/audio/query_demo_01.m4a").chroma
b = h.representation("data/audio/cand_07.m4a").chroma
for pct in (10, 20, 30, 40, 50, 60):
    r = h.qmax(a, b, params=h.QmaxParams(percentile=float(pct)))
    print(pct, round(r.qmax_score, 3), round(r.coverage, 3))
PY
```

The full 542-pair sweep takes about 27 minutes on the four allotted cores.
