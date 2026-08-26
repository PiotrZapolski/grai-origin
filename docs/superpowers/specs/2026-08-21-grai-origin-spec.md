# GRAI ORIGIN - executive specification

**Provenance & Similarity Engine for audio**
GRAI x VIBESTARS / CASE 03

Date: 2026-08-21
Status: **the sole source of truth for the implementation**

---

## 0. How to read this document

The project has three documents and they have disjoint roles:

| Document | Role | When to look at it |
|---|---|---|
| `docs/brief/source-spec.md` | the specification from the commissioning party, frozen | when you need to check what was in the original |
| `docs/superpowers/specs/2026-08-21-grai-origin-design.md` | decisions D1-D12 together with rationale and cost of reversal | when you need to know **why** something is one way and not another |
| **this file** | **the complete specification to implement** | **always, when writing code** |

This document is a merge of the first two: it takes the source specification and
applies to it all the decisions and the findings from measuring the catalog. It
contains no cross-references of the kind "per decision D9, this instead" - the
decisions are already applied in the text. The rationale has been shortened to a
single sentence and marked `[D<n>]`, so that the full argument can be found again.

**Rule for implementers:** if this document says something different from the
source specification, this document governs. If something in it is ambiguous, that
is a defect of this document and it has to be reported, not settled quietly in the
code.

Every number concerning the catalog in this document is **measured** on
`Projects/dataset/export_20260701.csv.zip`, not estimated.

---

## 1. The product

The system accepts a URL to an audio clip and returns an ordered list of
candidates indicating the most likely source, with a calibrated probability, an
evidence class and the ability to verify by listening.

The key difference from the obvious solution: the system does not return a single
similarity number, it **decides what kind of similarity it is**. Whether this is
the same fixation, the same work in a different performance, a borrowed fragment,
or an element common to an entire genre. That last class is what separates a
useful tool from a false-alarm generator.

The candidate set is small and explicit. We are not building an internet search
engine.

---

## 2. Four questions, not one

| # | Question | Subject matter of protection | Detector |
|---|---|---|---|
| 1 | Is this the same sound fixation? | phonogram | A |
| 2 | Is this the same work in a different performance? | work | B + D |
| 3 | Was a fragment borrowed? | phonogram or work | A (locally) + C |
| 4 | Is it allowed to be used? | license | metadata |

The system answers each one separately and folds them together only at the fusion
step. Blending them into one score is the most common design error in this class
of tools.

---

## 3. Taxonomy of results

Every match belongs to exactly one class. **The class, not the number, is the
primary output of the system.**

| Class | Code | Rights layer | Interpretation |
|---|---|---|---|
| Identical fixation | `EXACT` | phonogram | reupload, rip, trim |
| Modified fixation | `MODIFIED` | phonogram | speedup, nightcore, pitch shift |
| The same work, a different performance | `VERSION` | work + performance | cover, live, remake |
| Borrowed fragment | `EXCERPT` | phonogram **or** work | sample, loop |
| Lyrical overlap | `LYRICS` | work (lyrics) | translation, reworking, quotation |
| Common element | `COMMON` | none | progression, scale, genre rhythm |
| No match | `NONE` | none | |

`COMMON` is **a result of its own, not a variant of no match**. The system is
meant to say it outright: we found a similarity and we believe it is not material.
That is information, not silence.

`EXCERPT` comes in two variants that have to be distinguished in the code, because
they carry different legal consequences and different exposure to the commonality
filter:

- `EXCERPT/phonogram` - a fingerprint hit on a short segment (detector A). That is
  a sound sample.
- `EXCERPT/work` - a melodic sequence hit without a fingerprint hit (detector C).
  That is a compositional borrowing.

**Names in the code and on the wire.** The notation `EXCERPT/phonogram` is a
human-readable form and appears only in the text of this document. In the code, in
JSON and in the interface, only the underscored identifiers are valid:

```
EXACT  MODIFIED  VERSION  EXCERPT_PHONOGRAM  EXCERPT_WORK  LYRICS  COMMON  NONE
```

`EXCERPT` on its own **is not a valid value** and the contract validator is to
reject it. Those eight are the complete set, there are no others.

---

## 4. Execution architecture

The work splits **not by detector, but by when it can execute** `[D2]`.

| Level | When | Contents | Time budget |
|---|---|---|---|
| **0** | offline, before the demo | candidate representations, IDF corpus, calibration model | no limit |
| **1** | live | ingest, detector A, detector B, shortlisting, preliminary fusion, **verdict** | target 5 s |
| **2** | in the background, arrives as a stream | detector D, detector C, upgrading the verdict | target 30 s |

Level 1 settles `EXACT`, `MODIFIED`, `VERSION`, `COMMON` and `NONE`, that is five
classes out of seven, including the trap from demo case 5. Level 2 adds `LYRICS`,
`EXCERPT/work` and raises the confidence of the rest.

**The verdict appears after level 1 and grows in front of the viewer.** Phrasing
for the walkthrough: *the verdict in five seconds, the evidence arriving over the
next thirty*. It is stronger than "under ten seconds", because it shows the layered
construction of the system instead of hiding it `[D2]`.

```
URL / file
    |
    v
[ INGEST ]  download -> demux -> normalization -> windows 10 s / hop 5 s
    |
    +-------------------- LEVEL 1 (target 5 s) --------------------+
    |                                                              |
    v                          v                                   |
[ A: fingerprint ]       [ B: harmonic ]                           |
    |                          |                                   |
    +------------+-------------+                                   |
                 v                                                 |
        [ SHORTLISTING -> shortlist <= 20 ]                        |
                 v                                                 |
        [ COMMONALITY FILTER ]                                     |
                 v                                                 |
        [ FUSION -> PRELIMINARY VERDICT ] --> SSE: verdict(partial)|
    +--------------------------------------------------------------+
                 |
    +-------------------- LEVEL 2 (target 30 s) -------------------+
                 v
        [ D: lyrics ]  --gate rejected?--> [ demucs ] -> retry
                 v
        [ C: melody ] (shortlist only)
                 v
        [ FUSION AGAIN ] --> SSE: verdict(final)
```

**Overriding rule:** heavy models (source separation, speech transcription) never
run on the whole candidate set. Only on the query and on the shortlist after
shortlisting. Breaking this rule makes running on the target hardware impossible.

**Target hardware:** a Hetzner server, CPU without GPU, **shared with another
project's production**. A process taking all the cores will degrade a live system.
The core limit for the GRAI ORIGIN workload is hard and is set in M0 `[D8]`.

---

## 5. Data

### 5.1 The SecondHandSongs catalog

Four quarterly dumps in `Projects/dataset`, one CSV each in a zip. The reference
for all the numbers: `export_20260701` (the newest).

Columns:

```
performance_id, performance_title, performer, language,
instrumental, youtube_url, work_title
```

| Quantity | Value |
|---|---|
| Performances (rows) | 1,232,494 |
| Unique `work_title` values | 213,134 |
| Unique performers | 222,628 |
| Rows with a `youtube_url` | 1,232,494 (100%, every address unique) |
| Instrumental | 307,194 (24.9%) |
| `performance_title` different from `work_title` | 233,599 (19.0%) |

Growth between dumps: 1,086,636 -> 1,131,730 -> 1,188,437 -> 1,232,494.
Between the oldest and the newest, 158,795 entries were added and **12,937
disappeared**.

Performance groups (key: `work_title`):

| Group size | Works |
|---|---|
| 1 | 90,379 |
| 2 | 47,672 |
| 3-5 | 38,145 |
| 6-10 | 16,724 |
| 11-50 | 16,614 |
| 51+ | 3,600 |

| Pool | Groups |
|---|---|
| At least 2 vocal performances | 108,199 |
| Mixed vocal + instrumental | 33,474 |
| Instrumental only | 7,942 |
| At least two languages in the group | 3,541 |
| **After the filter from 5.4 (the drawing pool)** | **69,208** |

### 5.2 Three things the catalog does not contain

Each one has a consequence written into later sections and none of them may be
worked around in the code.

**1. There is no `work_id`. `work_title` is a string and it collides.**

| `work_title` | Performances | What is inside |
|---|---|---|
| `Forever Young` | 219 | the Alphaville work **and** the Bob Dylan work |
| `Crazy` | 377 | Seal, Patsy Cline/Willie Nelson, Iron Savior |
| `Home` | 315 | Depeche Mode, Stephanie Mills/Diana Ross |
| `Angel` | 265 | Shaggy, Sarah McLachlan, Jimi Hendrix |

Naive grouping by title produces false positive pairs, those go into the
calibration regression and lower the thresholds for the whole `VERSION` class.
Handled by: the filter in 5.4 `[D9]`.

**2. There is no release date.** No column at all. Handled by: the manual manifest
in 5.5 `[D10]`.

**3. There are no links between adaptations and originals.** Translations have
their own `work_title`: Clouseau's "Heb ik ooit gezegd" does not sit in the group
for Van Morrison's "Have I Told You Lately", it is a separate work. The `LYRICS`
class has no labels here. Handled by: 10.4 `[D11]`.

Separately, as a warning against a false conclusion: **the row order does not
encode a relationship**. The first few dozen rows look paired up (Kashmir next to
Come with Me, that is a sample), but across the whole file only 10.3% of adjacent
rows share a `work_title`, and 96,234 works are split across more than one block.

### 5.3 Candidate set (product)

Small and explicit: **8-12 candidates** with identifiers, visible on screen. Each
with a full representation profile computed offline (level 0).

Chosen for the demo scenarios in section 14, so as to cover all the evidence
classes.

The manifest `data/candidates/<set_id>.json` - **this is a hand-curated artifact**,
not a generated one:

```json
{
  "set_id": "demo_01",
  "candidates": [
    {
      "id": "cand_07",
      "name": "Kashmir",
      "artist": "Led Zeppelin",
      "shs_performance_id": "18",
      "source_url": "https://youtube.com/watch?v=gEYqSorzOZs",
      "audio_path": "data/audio/cand_07.wav",
      "published": "1975-02-24",
      "published_source": "manual",
      "license": "all_rights_reserved",
      "instrumental": false,
      "language": "en",
      "lyrics_path": "data/lyrics/cand_07.txt"
    }
  ]
}
```

`published_source` accepts only the value `manual` or `metadata_registry`.
**Never `youtube`** - the reason is in 5.5.

`published` and `published_source` are **optional and may be empty**. A missing
date is a valid state, not data waiting to be filled in: the chronology rule from
9.3 applies only to candidates that have a date, and the E7 axis skips the rest. A
made-up date is a defect, an empty one is not. Both fields either appear together
or not at all.

### 5.4 Calibration set

**500 pairs: 250 positive, 250 hard negatives** `[D4]`. A logistic regression on
seven features saturates at a few hundred examples, and the 6,000 pairs from the
source specification are several hours of downloading for a statistically
indistinguishable result.

**Positive pairs** are drawn only from groups meeting all four conditions `[D9]`:

1. between 2 and 10 vocal performances in the group (cuts off the mega-groups of
   standards and carols, which would otherwise dominate the set),
2. distinguishable title: at least 3 words **or** at least 18 characters (cuts off
   `Crazy`, `Home`, `Angel`, that is the places where the collisions actually
   live),
3. at most **one pair per group**,
4. both performances vocal and in the same language.

After the filter, 69,208 groups remain against a need for 250 pairs, that is a
270-fold surplus. Any tightening of the filter is therefore free.

**Hard negatives:** the same artist as the original or the same genre, similar
tempo and key, but different works. Random negatives are useless, because the
system rejects them trivially and the calibration comes out too optimistic.

**Structural negatives:** pairs sharing a chord progression but not a melody. For
calibrating the `COMMON` threshold. In addition, the 90,379 works with exactly one
performance are a pure negative pool, because by definition they have no cover in
the catalog.

**Filter quality control (mandatory):** after drawing, we listen through 20
positive pairs by hand. If more than one turns out to be different works, condition
2 is tightened to 4 words (the pool drops to 43,084, still with a surplus). That is
15 minutes of work protecting every threshold in the system.

### 5.5 Publication dates

The chronology axis (screen E7) and the chronology rule in fusion work **only for
the explicit candidate set**, on dates entered by hand into the manifest from 5.3
`[D10]`.

**Prohibition:** the publication date from YouTube must not be used. A 1959
recording may be uploaded in 2021, and a 2015 cover in 2016, so an axis built on
those dates will regularly point at the cover as the original, that is give **the
opposite answer to the product's main question** in the place that looks the most
objective in the whole interface. In an evidence tool that is a disqualifying
defect, worse than not having the screen.

For entries outside the candidate set, screen E7 shows nothing and the chronology
rule does not apply.

### 5.6 IDF corpus

3,000-5,000 works from the catalog, used solely to count pattern frequencies. They
need not be candidates. The larger it is, the better the commonality filter.

Selection: stratified sampling by language and by group size, so that the corpus is
not dominated by English-language standards. Corpus bias carries directly into the
filter and is written into the limitations (section 19).

### 5.7 Audio downloading

Every audio download job (calibration sample, IDF corpus, candidates) draws **25%
more entries than it needs**, and finishes once it has collected the target number
of successful downloads, not once it has exhausted the list `[D12]`.

The reason: 12,937 entries disappeared from the catalog over three quarters, and on
top of that come videos taken down, made private and region-blocked, which the July
dump does not know about. A download planned down to the item arrives incomplete,
and that only surfaces at counting time.

Technical requirements: a concurrency limit, resumption, an error log with a reason
per entry. Before the full run, **a test on 20 entries** - download limits are the
number one open risk on the preparation side (section 21).

The demo candidate files must sit locally before the show. A dead link is detected
during preparation, not on stage.

---

## 6. Ingest

**Input:** a URL (YouTube, a direct link) or a local upload.

**Steps:**

1. Download: **the `yt_dlp` library imported in Python**, not a CLI invocation.
   `format="bestaudio/best"` plus `download_ranges` limiting to 3 minutes. Longer
   material is cut down to the highest-energy fragment.

   The library rather than a subprocess, because errors then arrive as
   `DownloadError` with a recognizable message instead of an exit code to parse.
   Whether to retry depends on telling "video taken down" apart from "throttling",
   and when downloading a corpus counted in thousands of entries that is the
   difference between a complete and an incomplete set.
2. Decoding with `ffmpeg` to PCM mono **22,050 Hz** (the harmonic path) and
   **16,000 Hz** (the speech path).
3. Loudness normalization to **-23 LUFS**. Without it, energy thresholds stop
   being comparable between recordings from different sources.
4. Silence detection and trimming at the edges.
5. Windowing: **10 s windows with a 5 s hop** (50% overlap). The overlap is
   necessary so that a fragment does not fall between windows.

**Output:** a `Clip` object with an array of windows, the duration, the sample
rates and the **SHA-256 of the normalized signal** (deduplication and cache).

Candidates go through the same pipeline offline.

---

## 7. Detectors

### 7.0 Common contract

**A detector is a function taking a `Clip` and a list of candidates, returning an
envelope.** The engine exposes a registry into which detectors plug without
touching engine code.

```json
{
  "detector": "lyrics",
  "status": "ok",
  "reason": null,
  "results": [ { "candidate_id": "cand_07" } ]
}
```

`status` appears at **two levels and both are mandatory**:

- **on the envelope** - concerning the detector's run for the whole query (e.g. the
  gate rejected the transcription of the query, so there is nothing to compare),
- **on an individual result** in `results[]` - concerning one candidate (e.g. this
  candidate is instrumental, so comparing lyrics makes no sense, but the remaining
  candidates are computed normally).

A result with no `status` field of its own inherits `ok`. Both take the same
vocabulary and **fusion must handle every one of them**:

| `status` | Meaning | What the UI shows |
|---|---|---|
| `ok` | computed | the value |
| `not_applicable` | the detector does not apply here (e.g. an instrumental recording for D) | "not applicable" plus the reason |
| `gated` | the confidence gate rejected the result as unreliable | "rejected by the confidence gate" |
| `failed` | execution error | "unavailable" |

**`not_applicable` and `gated` are not a zero.** Zero means "we checked and there
is no similarity", which is untrue and in an evidence tool would be a lie `[D11]`.
The bar on screen E5 then shows a state, not a value.

### 7.1 Detector A - acoustic fingerprint

**Answers questions 1 and 3. Level 1.**

**Algorithm:** Wang-style spectral landmarks. STFT (window 2048, hop 512) ->
detection of local maxima in a time-frequency window -> pairing each peak with
several peaks in a target zone -> a hash from the triplet `(f1, f2, dt)` -> a table
`hash -> (candidate_id, offset)`.

**Matching:** a histogram of offset differences for each candidate. A genuine match
gives a sharp peak, that is many hashes with **the same** offset difference. Random
coincidences spread out flat. This is simultaneously a significance test and the
determination of the time alignment.

**Parameters:** 30-50 peaks per second, target zone of 5 peaks within a 2 s window.

**Output:**

```json
{
  "candidate_id": "cand_07",
  "matched_hashes": 412,
  "peak_ratio": 0.83,
  "query_span": [12.4, 31.8],
  "candidate_span": [64.1, 83.5],
  "offset": 51.7,
  "repetitions": 3,
  "transform": null
}
```

`peak_ratio` is the share of hashes in the dominant bin of the histogram. Below
0.25 we treat it as noise. `repetitions` is the number of disjoint bins above the
threshold, that is how many times the same fragment occurred - it settles
`EXCERPT`.

**Extension for tempo and key (`MODIFIED`):** a grid of frequency-axis rescalings
of +/-6 semitones in 1-semitone steps and time-axis rescalings of 0.90-1.15 in 2.5%
steps. That is 13 x 11 = 143 variants, so it runs **only when the match without any
transformation failed and detector B returned high similarity.** That condition is
crucial: the signal from B says "this is that work", the absence of a signal from A
says "but not that version", and the grid answers "because it is sped up by 6%".
The result lands in the `transform` field.

**Library:** a custom implementation on `numpy` + `scipy.ndimage.maximum_filter`
(~150 lines) or `audfprint`. Auxiliary `pyacoustid`/`fpcalc` as a second,
independent opinion on `EXACT`.

### 7.2 Detector B - harmonic similarity

**Answers question 2. Level 1. This is the cover detector.**

**Features:** CQT (12 bins per octave, from C1, 6 octaves) -> pitch class profile
(chroma/HPCP) -> median smoothing over time -> L2 normalization of every frame.
Resolution ~0.1 s, aggregated to ~2 Hz.

**Key invariance:** we do not transpose to a detected key, because key detection is
unreliable. We compute the similarity for all 12 rotations of the chroma vector and
take the maximum. The returned rotation is ready-made information "transposed by N
semitones" for the UI.

**Preliminary shortlisting:** the full matrix is O(n*m), too expensive for all
candidates. First a cheap global descriptor: a 2D-DFT of the chromagram, flattened
and normalized -> a 256-dimensional vector, compared by cosine. The matrix is
computed only for the **top 20**.

**Similarity:** a cross-similarity matrix between the chroma sequences, binarized
by a percentile threshold (typically the 10th percentile of distances), then
**cumulative alignment along diagonals** (the Serra Qmax variant). The result is
the length of the longest coherent diagonal path normalized by the length of the
shorter sequence.

Why a diagonal path rather than correlation: a cover has a different tempo, so the
path is not parallel to the diagonal, it is tilted and locally disturbed. Alignment
absorbs that, correlation does not.

**The same matrix is a UI artifact.** Rendered as a heatmap with the path
highlighted it is the most visually convincing piece of evidence in the system, and
it costs nothing extra.

**Output:**

```json
{
  "candidate_id": "cand_07",
  "qmax_score": 0.71,
  "transposition": 2,
  "tempo_ratio": 1.06,
  "alignment_path": [[0, 0], [1, 1]],
  "coverage": 0.62,
  "chord_sequence": ["C", "G", "Am", "F"]
}
```

`coverage` is the **minimum of the query coverage and the candidate coverage** by
the alignment path. It distinguishes a cover of the whole work (high) from a
borrowed fragment (low), that is `VERSION` from `EXCERPT`.

**An annex, because this departs from the intuitive definition.** The query
fraction alone would return 1.0 for a short snippet fully explained by a
three-minute candidate, that is it would confuse `EXCERPT` with `VERSION` exactly
where this number is supposed to decide. The minimum of both sides does not.

The cost of this change is real and has to be known: a shortened cover, for example
a 90 s radio version against a 180 s candidate, gets a `coverage` below 0.5 and
falls out of rule 4 of the decision tree. That is a deliberate trade of sensitivity
for precision, in line with the precision target of 0.95 from section 10.3.
`chord_sequence` feeds the commonality filter.

**Library:** `librosa` for CQT and chroma, the rest `numpy`. Deliberately without
Essentia despite its ready-made Qmax implementation - the reason is in section 16.

### 7.3 Detector D - lyrics

**Answers questions 2 and 3 in the lyrical layer. Level 2.**

**The order is reversed relative to the source specification:** transcription runs
**on the full mix first**, and source separation is triggered only when the
confidence gate rejects the first pass `[D3]`. Demucs sits at the input of two
detectors at once and is the most expensive operation in the system, so we turn a
fixed cost into a conditional one.

**Steps:**

1. **Checking the `instrumental` flag on the candidate side.** A candidate marked
   as instrumental gets a result with `status: not_applicable` and does not take
   part in the lyrics comparison. The flag comes from the manifest (5.3), where it
   arrives straight from the catalog. That is 24.9% of the catalog, for free,
   because the flag is in the data `[D11]`.

   **The query does not have this flag** and cannot have it, because it arrives as
   a URL with no metadata. Whether the query is instrumental is settled solely by
   the gate in step 3. If **all** the candidates are instrumental, the detector
   finishes immediately with a `not_applicable` envelope and does not start
   transcription - that is where the saving actually arises.
2. Speech recognition with word-level timestamps, on the full mix.
3. **Confidence gate.** If the average transcription confidence is below the
   threshold or the detected language is unstable between windows, the detector
   returns `status: gated`. Critical: on an instrumental the model hallucinates and
   without the gate the system will show random text for a work with no vocal.
4. **If the gate rejected:** source separation with `demucs`, repeating steps 2-3
   on the separated vocal. If the gate rejects again, `status` stays `gated`.
   Screen E2 then shows "transcription rejected by the gate, starting source
   separation" - you can see the system judging its own confidence rather than
   merely computing.
5. Normalization: lowercase, no punctuation, reduction of vocal repetitions.

**Two-stage comparison:**

- **Literal level** - 5-word shingles, MinHash signatures, Jaccard similarity.
  Detects copies and quotations. Cheap and scalable.
- **Semantic level** - multilingual sentence embeddings, sentence-to-sentence
  cosine similarity with alignment. Detects translations and paraphrases that
  MinHash does not see.

**The reference side:** candidate lyrics are fetched from an open lyrics database,
not transcribed. Zero computational cost on the reference side.

**Output:**

```json
{
  "candidate_id": "cand_07",
  "jaccard": 0.64,
  "semantic_sim": 0.89,
  "matched_spans": [
    { "query_text": "...", "candidate_text": "...",
      "query_time": [18.0, 24.5], "idf": 11.2 }
  ],
  "asr_confidence": 0.81,
  "language": "en",
  "used_separation": false
}
```

`matched_spans` with timings feeds the highlighted lyrics view - the user sees
**which words and when**.

**Negative control:** the 7,942 instrumental-only groups from the catalog are a
test set for the gate. If transcription returns anything on them above the
threshold, the gate is set wrong. It is the cheapest correctness test in the whole
plan `[D11]`.

### 7.4 Detector C - symbolic melody

**Answers question 3 in the composition layer. Level 2. Built last.**

The only detector operating on what the law regards as the creative element of a
work. At the same time the most expensive and the most unreliable, so the first to
be cut (section 18).

**Steps:**

1. **Source separation** - extracting the vocal and harmonic tracks. Without it,
   melody transcription on the full mix returns percussion. If detector D has
   already run demucs, the result is shared and computed once.
2. **Transcription into a symbolic representation** - polyphonic audio-to-MIDI
   transcription, then extraction of the dominant line (the highest active note in
   a frame, with hysteresis against flicker).
3. **Quantization** of the notes onto the rhythmic grid of the detected tempo,
   which eliminates interpretive differences.
4. **Conversion into an interval sequence** - differences between successive notes
   instead of absolute pitches. It gives transposition invariance for free and
   corresponds to how a human judges melodic similarity.
5. Optionally a rhythmic contour: logarithms of the ratios of successive durations.

**Comparison:** interval n-grams of length 4-8. For each n-gram of the query we
look for occurrences in the candidates. Additionally a global match by the
Mongeau-Sankoff distance (an edit-distance variant accounting for note fusion and
fragmentation, because a melody played with ornaments is still the same melody).

**Output:**

```json
{
  "candidate_id": "cand_07",
  "matched_ngrams": [
    { "interval_seq": [2, 2, 1, -3, -2], "query_pos": 14.2,
      "candidate_pos": 66.0, "idf": 8.4 }
  ],
  "longest_common_run": 11,
  "ms_distance": 0.19
}
```

`longest_common_run` is a number a musicologist and a lawyer both understand:
eleven consecutive identical intervals.

---

## 8. Commonality filter

**Goal:** to tell a borrowing apart from a common element. This is the mechanism
that translates the legal principle "creative expression is protected, not the idea
or the convention" into working code. Without it the product does not differ from
any other similarity tool.

**Construction (level 0, offline):** on the corpus from 5.6 we compute the document
frequency of every pattern:

- interval n-grams (detector C),
- lyrical shingles (detector D),
- chord sequences derived from chroma (detector B, the `chord_sequence` field).

For a pattern `w`: `idf(w) = log(N / df(w))`, where `N` is the number of works in
the corpus.

**Application:** the match score is weighted by the IDF of the patterns hit. A
match based exclusively on low-IDF patterns (occurring in more than 1% of the
corpus) is degraded to the `COMMON` class regardless of the raw similarity score.

### 8.1 Scope of degradation - the governing rule

The source specification says "if any match and `mean_idf` below the threshold,
then `COMMON`", which read literally would allow a reupload to be degraded. The
resolution:

> **Degradation to `COMMON` applies only to classes from the work layer:**
> `VERSION`, `LYRICS`, `EXCERPT/work`.
> **Never to `EXACT`, `MODIFIED` or `EXCERPT/phonogram`.**

The reason: acoustic fingerprint hashes are not genre patterns. A reupload of a
work built on the I-V-vi-IV progression does not stop being a reupload because the
progression is commonplace. The commonality filter answers the question "is this
pattern somebody's creative property", and with a fingerprint hit the question is
not about the pattern but about the specific fixation.

Without this rule, demo case 1 (`EXACT`) could come out as `COMMON`, meaning the
system would contradict itself on the first slide.

### 8.2 Interpretation in the UI

Instead of a number we show a sentence:

> "This motif occurs in 1,240 works of the corpus. That is a genre convention, not
> a signal of borrowing."

**Methodological note:** the quality of the filter depends directly on how
representative the corpus is. A corpus dominated by one genre will inflate the IDF
of that genre's patterns. Written into the limitations.

---

## 9. Fusion and decision

**We do not compute a weighted average.** The detectors answer different questions,
so averaging their results destroys the information about the kind of match.
Instead, a rule tree with explicit conditions, readable and auditable - in a legal
application it must be possible to reconstruct why the system reached that
decision.

### 9.1 Evaluation order

Rules checked **in this order**, the first one satisfied wins:

```
1. EXACT              A.transform == null AND A.peak_ratio > 0.60 AND A.span_length > 15 s
2. MODIFIED           A.transform != null AND A.peak_ratio > 0.50 AND B.qmax > 0.50
3. EXCERPT/phonogram  A.peak_ratio > 0.40 AND A.span_length < 15 s AND A.repetitions >= 2
4. VERSION            A.peak_ratio < 0.40 AND B.qmax > 0.55 AND B.coverage > 0.50
                      AND (D.semantic_sim > 0.70 OR D.status != "ok")
5. EXCERPT/work       C.longest_common_run >= 8 AND B.coverage < 0.40
6. LYRICS             B.qmax < 0.40 AND D.status == "ok" AND D.jaccard > 0.50
7. NONE               in all other cases

After the class is chosen, if the class belongs to {VERSION, LYRICS, EXCERPT/work}
and mean_idf < commonality_threshold  ->  the class is replaced by COMMON.
```

**Amendment, 2026-08-26.** The condition `A.transform == null` in rule 1 is an
addition to the source specification, made after the first run on real music: a
recording sped up by 6% came out as `EXACT`, because the transformation grid had
recovered a `peak_ratio` of 0.80 over a 52.7 s segment and rule 1 checked only
the peak and the length. A match that exists only after the query has been
transformed is by definition not an identical recording, so rule 1 must step
aside and let rule 2 classify it as `MODIFIED`.

The threshold `A.peak_ratio < 0.40` in rule 4 is **deliberately higher than the
0.25 from the source specification**. At 0.25 a query with a `peak_ratio` in the
range 0.25-0.40 and a high `B.qmax` would satisfy no rule and fall through to
`NONE`, that is a weak fingerprint trace would **hide** a correctly recognized
cover. Rules 1-3 already capture every case in which the fingerprint actually hit,
so the guard in rule 4 only has to cut off unambiguous hits, not borderline ones.

The condition `D.status != "ok"` in rule 4 is deliberate: the absence of a reliable
transcription must not block cover recognition, because 24.9% of the catalog is
instrumental recordings. Fusion must work correctly when any detector returns an
envelope other than `ok` - that is a normal operating mode, not a failure
`[D3, D11]`.

### 9.2 Thresholds and their status

The "source" column is **mandatory in the UI**: every threshold coming from a
manual entry must be described as such until calibration replaces it.

| Threshold | Starting value | Target source |
|---|---|---|
| `EXACT`: `A.peak_ratio` | 0.60 | calibration |
| `EXACT`: segment length | 15 s | entered, not calibrated |
| `MODIFIED`: `A.peak_ratio` | 0.50 | calibration |
| `EXCERPT/phonogram`: `A.peak_ratio` | 0.40 | calibration |
| `EXCERPT/phonogram`: `repetitions` | 2 | entered, not calibrated |
| `VERSION`: `B.qmax` | 0.55 | **calibration, this is the product's main threshold** |
| `VERSION`: `B.coverage` | 0.50 | calibration |
| `EXCERPT/work`: `longest_common_run` | 8 | entered, no data |
| `LYRICS`: `D.jaccard` | 0.50 | **entered, no calibration data** |
| `COMMON`: `commonality_threshold` | 1% of the corpus | calibration on structural negatives |

### 9.3 The chronology rule

With two matches of the same class and a similar score, the candidate with the
earlier first-publication date lands higher in the ranking. The original is usually
earlier, it is the cheapest signal in the system and often the decisive one.

The rule applies **only to candidates having `published` from the manifest** (5.5).
With no date, the order is determined solely by probability, and the UI does not
suggest precedence.

---

## 10. Calibration

**This is the component that turns a demo into a product.** The brief requires a
readable confidence signal, and the output of a similarity function is not
confidence: a Qmax of 0.87 does not mean an 87% chance of being right. Without
calibration every number in the UI is an ornament.

### 10.1 When

**Before the hackathon, offline (level 0)** `[D4]`. The catalog is already on disk,
so downloading the sample does not sit on the critical path and does not compete
for resources with the team's work.

### 10.2 The model

Input features: `A.peak_ratio`, `B.qmax`, `B.coverage`, `C.longest_common_run`,
`D.jaccard`, `D.semantic_sim`, `mean_idf`.

**Logistic regression** with a split into a training and a test set, the output
being the probability of the positive class. **A separate model per evidence
class** - the probability that a match labeled `VERSION` really is a cover is a
different quantity from the one for `EXCERPT`.

Regression rather than a random forest or a network: it yields weights that can be
shown and explained, it is robust on a small sample and it naturally returns a
probability.

Missing features (the detector returned `not_applicable`, `gated` or `failed`) are
handled by an availability indicator per feature, not by inserting a zero. Zero is
an informative value and inserting it artificially shifts the weights.

### 10.3 Metrics and threshold selection

- ROC curve and AUC per class,
- **calibration curve** (reliability diagram): whether "90% confidence" really is
  right in 9 cases out of 10,
- selection of the operating threshold at a given precision. For a legal
  application we target **precision >= 0.95**, because a false alarm about
  infringement costs more than a miss,
- confusion matrix between the evidence classes.

### 10.4 Classes without calibration

The `LYRICS` class stays **rule-based and explicitly uncalibrated** `[D11]`. In the
catalog, translations are separate works, so original-adaptation pairs simply do
not exist, and the 3,541 multilingual groups are mostly the same work sung in
several languages under one title, not paired adaptations.

The class stays in the product despite the lack of calibration, because it answers
a real legal question (reworking lyrics is a different right from a cover) and demo
case 4 requires it. Honesty is provided by the label, not by removal: a system
saying "I have no data here" is a stronger argument than a system pretending it has
data everywhere.

The same applies to `EXCERPT/work` - the `longest_common_run` threshold is entered
by hand.

### 10.5 Presentation in the UI

Instead of "87% similarity":

> **Confidence 94%** - threshold calibrated on 500 pairs from the SecondHandSongs
> catalog.
> At this level the system is wrong in 6 cases out of 100.
> [see the calibration curve]

For uncalibrated classes:

> **Preliminary threshold, no calibration data.**

---

## 11. Legal layer

The system returns **flags and an evidence classification, never a ruling on
infringement**. Assessing infringement requires a human. This is not hedging, it is
a product feature: it positions the tool as triage for the legal team rather than a
machine handing down judgments.

### 11.1 Separating the rights layers

The result always indicates which layer it concerns:

- **phonogram** (a specific fixation) - detector A,
- **work** (composition and lyrics) - detectors B, C, D,
- **artistic performance** - a separate layer, flagged with `VERSION`.

**Two fields, two roles.** `RankingEntry.verdict_layer` is **single-valued** and
carries the **leading** layer, the one the verdict flows from. The full set of
layers the result touches is carried by `Legal.rights_layer`, and that is where
`VERSION` gets `["work", "performance"]`. The single-valuedness of `verdict_layer`
is intentional, it is not a simplification to be fixed: the interface needs one
label next to the class badge, and the legal panel separately shows the full set.

The rightholders and terms of protection differ for each, so the same number means
something different.

**Basis.** The Act of 4 February 1994 on Copyright and Related Rights protects the
work separately (art. 1) from the subject matter of related rights, that is
phonograms and artistic performances (chapter 11), with separate rightholders and
separate terms of protection. Hence the table of three subject matters of
protection, which panel E8 shows outright next to every layer hit:

| Subject matter of protection | Who holds the rights | Which detector hits it | Basis |
|---|---|---|---|
| Work (composition and lyrics) | composer and lyricist, or publisher after transfer of rights | B (harmonic similarity), C (melody), D (lyrics) | art. 1 of the Act |
| Phonogram (a specific fixation) | phonogram producer, usually the label | A (acoustic fingerprint) | chapter 11 of the Act |
| Artistic performance | performer | no detector of its own, flagged with `VERSION` | chapter 11 of the Act |

An identical numerical result from detector A (phonogram) and from detectors B/C/D
(work) does not mean the same thing, so the product shows the layers separately
rather than as one score. `VERSION` touches two layers at once and the panel is to
say so.

### 11.2 Interpretive rules

| Situation | Signal from the system | Basis |
|---|---|---|
| A low-IDF element | `COMMON`, no flag | protection does not cover ideas, conventions or unprotected elements (art. 1(1) of the Act of 4 February 1994 in conjunction with art. 2(4)) |
| Inspiration without taking over creative elements | `COMMON` or `NONE` | art. 2(4) of the Act of 4 February 1994: "a work created as a result of inspiration by another work is not considered a derivative work" |
| Borrowing of lyrics, translation, reworking | `LYRICS` | art. 2(1) of the Act of 4 February 1994: a derivative work is the subject of a separate right, but disposing of it requires the consent of the author of the original work |
| A short, recognizable fragment of a phonogram | `EXCERPT/phonogram` + high-risk flag | Pelham I, CJEU judgment of 29 July 2019, C-476/17: a phonogram producer may prohibit the taking of even a very short sample, unless it has been included in the new work in a modified form unrecognizable to the ear |
| A heavily modified fragment, in a new context | `EXCERPT` + "possible pastiche" flag | Pelham II, CJEU judgment of 14 April 2026, C-590/23, interpreting art. 5(3)(k) of Directive 2001/29/EC (InfoSoc): pastiche requires, cumulatively, evocation of the work, a perceptible difference and a recognizable artistic dialogue |
| A candidate under an open license | no risk flag | the license permits the use, the system generates the attribution |

**Recognizability indicator** - derived from `A.peak_ratio` for the `EXCERPT`
class: the higher it is with an unmodified fingerprint, the more the fragment is
recognizable to the ear. This is not a metaphor, it is a criterion applied by a
court translated into a measurable signal.

**Modification indicator** - the degree of departure from the original (key shift,
tempo, spectral filtering, loop length in the new context). High modification with
recognizability preserved is a borderline situation and is to be marked as such.
The legal criterion stands in Pelham II as the second condition for pastiche: a
perceptible difference of the new work relative to the source.

**What the system does not assess.** Of the three cumulative conditions for
pastiche (Pelham II) the system measures two and stops before the third. That is a
declared boundary of the tool, not a gap to be filled in the next iteration, and
panel E8 is to say so outright:

| Legal criterion (Pelham I/II) | Technical signal | Status |
|---|---|---|
| Evocation and recognizability of the sample to the ear | `recognizability`, derived from `A.peak_ratio` | measured |
| Perceptible difference from the source | `modification` (key, tempo, filtering, loop length) | measured |
| Recognizable artistic dialogue | no technical signal | **not measured**, the situation goes to human judgment |

Two clarifications from Pelham II, without which the measurement would make no
sense:

1. The Court **ruled out examining the subjective intent of the creator**. What
   counts is whether the pastiche character is objectively recognizable to somebody
   who knows the source work. That is why an objective signal (recognizability,
   degree of modification) can say anything about pastiche at all.
2. **Covert imitation and plagiarism remain outside the scope of the exception.** A
   high modification indicator is not a green light and the UI has no right to
   present it as one.

Separately from the conditions for pastiche, the system **does not establish
access**: publication chronology (section 9.3) is circumstantial, not proof that
the author of the new work knew the earlier one.

### 11.3 Output

```json
{
  "rights_layer": ["phonogram", "work"],
  "risk_flags": ["recognizable_excerpt", "possible_pastiche"],
  "recognizability": 0.78,
  "modification": 0.41,
  "license_status": "unknown",
  "required_attribution": null,
  "disclaimer": "Technical signal, not a legal opinion."
}
```

`license_status: "unknown"` must be displayed as **absence of information**, never
as absence of restrictions. License status does not follow from the audio analysis:
it is a separate metadata layer, independent of whether the system detected a
similarity.

**The note that this is not legal advice stays visible at all times.** The stronger
the citations in the panel, the greater the risk that somebody reads a case
citation as an opinion. The provisions and judgments cited say **where the signal
comes from**, and are not an assessment of any particular case.

### 11.4 Sources of the legal bases

- The Act of 4 February 1994 on Copyright and Related Rights: art. 1 (the work),
  art. 2(1) (derivative work), art. 2(4) (inspiration), chapter 11 (related rights:
  phonograms and artistic performances).
- Directive 2001/29/EC (InfoSoc), art. 5(3)(k): the caricature, parody and pastiche
  exception.
- CJEU judgment of 29 July 2019, C-476/17 (Pelham I) - recognizability of the
  sample to the ear as the boundary of the phonogram producer's right.
- CJEU judgment of 14 April 2026, C-590/23 (Pelham II) - the three cumulative
  conditions for pastiche, the exclusion of any examination of subjective intent,
  and the exclusion of covert imitation and plagiarism from the exception.

The source material for these citations: `docs/references/legal-layer-source.md`
and `docs/references/license-status-source.md`. That work was not produced in
this project, it comes from earlier materials of the brand.

---

## 12. API contracts

The contracts are **the only point of contact between the three roles**
(section 17). The front end works on mocks conforming to this schema from hour
zero. A change in this file requires saying so out loud, because it breaks the work
of the other two people.

### `POST /api/analyze`

```json
{ "url": "https://...", "candidate_set": "demo_01" }
```

Returns `{ "job_id": "..." }`.

### `GET /api/jobs/{id}/stream` (SSE)

Events in order. The `level` field says which execution level the stage comes from:

```
{"stage":"ingest",     "level":1,"status":"done",   "detail":{"duration":184.2,"windows":37}}
{"stage":"fingerprint","level":1,"status":"done",   "detail":{"hashes":4812}}
{"stage":"harmonic",   "level":1,"status":"running","detail":{}}
{"stage":"shortlist",  "level":1,"status":"done",   "detail":{"from":12,"to":8,"corpus":4128}}
{"stage":"commonality","level":1,"status":"done",   "detail":{"mean_idf":8.4}}
{"stage":"verdict",    "level":1,"status":"partial","detail":{"class":"VERSION","probability":0.71}}
{"stage":"transcript", "level":2,"status":"gated",  "detail":{"reason":"asr_confidence","next":"separation"}}
{"stage":"separation", "level":2,"status":"running","detail":{}}
{"stage":"transcript", "level":2,"status":"done",   "detail":{"words":47,"lang":"en"}}
{"stage":"melodic",    "level":2,"status":"done",   "detail":{"longest_common_run":11}}
{"stage":"verdict",    "level":2,"status":"final",  "detail":{"class":"VERSION","probability":0.94}}
```

The `verdict` event appears **twice**: `partial` after level 1 and `final` after
level 2. The front end must be able to upgrade the displayed verdict without
reloading the screen. The class may change in the process.

An event with `status: "gated"` carrying `next` is content, not an error - screen
E2 shows it as the step "the system judges its own confidence".

### `GET /api/jobs/{id}/result`

```json
{
  "status": "partial",
  "completed_levels": [1],
  "query": { "duration": 184.2, "waveform_url": "...", "transcript": [] },
  "ranking": [
    {
      "rank": 1,
      "candidate": {
        "id": "cand_07", "name": "...", "artist": "...",
        "published": "1977-05-20", "published_source": "manual",
        "license": "all_rights_reserved"
      },
      "verdict_class": "EXCERPT_PHONOGRAM",
      "verdict_layer": "phonogram",
      "probability": 0.94,
      "probability_status": "calibrated",
      "evidence": {
        "fingerprint": { "status": "ok" },
        "harmonic":    { "status": "ok" },
        "melodic":     { "status": "failed", "reason": "..." },
        "lyrics":      { "status": "not_applicable", "reason": "instrumental" }
      },
      "alignment": {
        "query_span": [12.4, 31.8], "candidate_span": [64.1, 83.5],
        "transposition": 2, "tempo_ratio": 1.06
      },
      "commonality": { "mean_idf": 8.4, "corpus_frequency": 3, "corpus_size": 4128 },
      "legal": {},
      "explanation": "..."
    }
  ],
  "calibration": {
    "model_version": "lr_v3", "trained_on": 500,
    "precision_at_threshold": 0.95
  }
}
```

`probability_status` accepts `calibrated` or `uncalibrated` and **the UI must
distinguish them visually** (10.5).

`evidence.*.status` uses the envelopes from 7.0. The front end may not assume that
every detector returned a number.

### `POST /api/explain`

Generates a natural-language description from the structured evidence. Invoked **on
the user's request, not automatically**. This is the only place in the system where
a language model appears, and it must sit off the critical path.

---

## 13. Interface

### 13.1 Visual system

| Element | Value |
|---|---|
| Background | near-black with an olive cast |
| Accent | acid lime, **exclusively as a signal**, never decoration |
| Headings | heavy sans-serif, white |
| Micro-labels | all caps, lime, small size, wide tracking |
| Surfaces | rounded cards slightly lighter than the background |
| Technical values | monospaced face (scores, timecodes, hashes) |
| Background motif | a large circle, a segment out of frame |
| Footer | a breadcrumb `GRAI ORIGIN / CASE 03 / <screen>` |

Lime is reserved for: the best match, an alert, the active pipeline step. Product
name **GRAI ORIGIN**, subtitle `PROVENANCE ENGINE`. The output report is called a
*case file*, laid out with the footer from the brief - the jury sees their own
visual language coming back as a product.

### 13.2 Screens

**E1 Input.** A URL field, a file drop, three buttons with prepared examples. The
waveform appears immediately after pasting, before the analysis begins. Zero empty
loading screen.

**E2 Live pipeline.** A vertical list of stages lighting up one after another, fed
by SSE. Each stage shows what it produced. Two numbers on screen and **both are
true, they simply refer to different things** `[D6]`:

```
candidates after shortlisting   8 of 12
commonality corpus              4,128 works
```

That sounds better than one inflated number, because it shows that the system
consults a large corpus in order to judge the **materiality** of a match, not in
order to search the internet.

**E3 Verdict.** One full-width card: the name of the source, the evidence class
badge, the calibrated probability, one sentence of justification. The card **must
be able to upgrade itself** when `verdict.final` arrives (section 12).

**E4 Evidence.** Four panels:

- **Time overlay** - two waveforms one above the other, the shared segment
  highlighted, a slider and **an A/B button switching the listening at the
  synchronized point**. This is the most important element of the whole interface:
  the brief requires the ability to check, and the only real verification for audio
  is the ear.
- **Harmonic similarity matrix** - a heatmap with the alignment path drawn on it.
- **Highlighted lyrics** - two columns, shared phrases emphasized, a click scrolls
  playback.
- **Melody** - a pianoroll with the shared interval sequence.

**E5 Criteria breakdown.** Horizontal bars per detector with the score and a
one-sentence interpretation. The criteria are **recording, harmonic similarity,
melody, lyrics**. No rhythm and no video `[D5]` - the addendum to the brief listed
them, but the system has no detector behind them, and a bar without a detector is a
dummy. A dummy in an evidence tool is worse than its absence, because the whole
product is sold on the fact that every number is backed. Tempo is reported by
detector B as `tempo_ratio`.

A detector bar with a status other than `ok` shows **a worded state, not a zero**
(7.0). Next to each bar, the commonality indicator: "this pattern: 3 works in the
corpus" or "1,240 works".

**E6 Ranking.** Positions 2-N with the class, the probability and a thumbnail of
the profile. A click switches the evidence panel.

**E7 Chronology.** First-publication dates on a single axis, the earliest one
emphasized. **Only for candidates with `published` in the manifest** `[D10]`. Under
the axis a sentence: "the date comes from release metadata, not from the video
platform".

**E8 Legal panel.** The rights layer, risk flags, the recognizability and
modification indicators, license status, ready-made attribution text to copy, a
clear note that this is not legal advice.

**E9 Calibration.** ROC curve, reliability diagram, the number of training pairs,
precision at the operating threshold. The screen nobody else will have.

**E10 Case file.** Export of the result as a downloadable report, in the brief's
branding.

---

## 14. Demo scenarios

Five cases, each showing a different class. The order matters dramatically.

| # | Case | Class | What it proves |
|---|---|---|---|
| 1 | A clean reupload with recompression | `EXACT` | the system works, it builds trust |
| 2 | A cover or a live version | `VERSION` | it understands the work versus phonogram difference |
| 3 | A version sped up by 6%, +1 semitone | `MODIFIED` | robustness against Content ID workarounds |
| 4 | A looped, filtered sample | `EXCERPT/phonogram` | the legal layer, the recognizability indicator |
| 5 | **The trap**: the same progression and tempo, a different work | `COMMON` | **the system has judgment, not just matching** |

**Case 5 is the most important.** Every team will show that it finds something.
Only you will show that the system can say "I found a similarity and I consider it
immaterial, and here is why".

Optionally case 6: a candidate under an open license, the system generates
ready-made attribution text.

**Walkthrough** (~90 seconds): problem -> solution -> result -> limitation. You
state the limitation yourselves, before anyone asks.

All five cases must work **from local files**, not from URLs. That is the only
safeguard against there being no internet in the room.

---

## 15. Evaluation

Metrics computed and shown, not declared.

| Metric | Definition | Target |
|---|---|---|
| Top-1 accuracy | the correct source in 1st place | > 0.85 on cover pairs |
| Recall@5 | the correct source in the top five | > 0.95 |
| Precision at the threshold | correct flags / all flags | >= 0.95 |
| Class accuracy | correctly assigned evidence class | confusion matrix |
| Calibration error | deviation of the curve from the diagonal | ECE < 0.05 |
| **Time to preliminary verdict** | median from URL to `verdict.partial` | **< 5 s** |
| **Time to complete evidence** | median from URL to `verdict.final` | **< 30 s** |

The last two replace the single "under 10 seconds" target from the source
specification, which on CPU with source separation on the path is unattainable
`[D2]`.

**Measured, 2026-08-26.** The targets above stay as targets; this is what the
first complete run against the real models actually cost. Hardware: four
physical cores of a Ryzen 5 3600 (`taskset -c 0-3`, `nice -n 19`, all four
thread-count variables at 4) on a shared box with another job running
throughout, so these are upper bounds. Query: 179 s of audio, two shortlisted
candidates.

| | target | measured |
|---|---|---|
| preliminary verdict | < 5 s | 6.2 s cold, 7.7 s with lyrics compared |
| complete evidence | < 30 s | 60 s cold, 99 s with lyrics compared |
| the separation branch alone | - | 478 s |

The two costs that dominate: the embedding model takes **17.5 s** to load and
nothing prewarms it, and **demucs takes 391 s** on this clip whenever the
confidence gate of 7.3 rejects the first pass. The gate passed here by 0.084,
so the 478 s branch was measured separately rather than paid; that branch is
sixteen times the final-verdict target and is selected by a single threshold.
Full numbers in `docs/full-run.md`.

Separately: **the false alarm rate on structural negatives**, that is how often the
system marks a shared progression as a borrowing. That is a metric measuring
exactly what sets you apart, and it is worth showing.

---

## 16. Stack and licenses

The rule: **permissive licenses only**, so that GRAI can deploy this without a
conversation with a lawyer.

| Layer | Choice | License |
|---|---|---|
| Downloading | `yt-dlp` | Unlicense |
| Decoding | `ffmpeg` | LGPL |
| DSP, CQT, chroma | `librosa` + `numpy`/`scipy` | ISC / BSD |
| Fingerprint | custom landmark implementation / `audfprint` | MIT |
| Control fingerprint | `pyacoustid` / `fpcalc` | MIT / LGPL |
| Source separation | `demucs` | MIT |
| Melody transcription | `basic-pitch` | Apache 2.0 |
| Speech recognition | `faster-whisper` / `whisper.cpp` | MIT |
| Lyrical similarity | `datasketch` + `sentence-transformers` | MIT / Apache 2.0 |
| Calibration | `scikit-learn` | BSD |
| Database | SQLite / Postgres, `duckdb` for analytics | public domain / MIT |
| Backend | FastAPI | MIT |
| Front end | Next.js + Tailwind + `wavesurfer.js` | MIT / BSD |

**Deliberately rejected:**

| Rejected | Reason |
|---|---|
| Essentia | AGPLv3 for non-commercial uses, commercial use under a separate license; pretrained models CC BY-NC-ND |
| MERT | weights under CC-BY-NC, commercial use prohibited |
| Panako | AGPL, a service built on it forces opening the code |
| ACRCloud, AudD, Audible Magic | paid APIs, they move the crux of the problem outside |
| ByteCover | no public weights, would require training |

This table is demo material. A team that deliberately rejected a technically better
component because of its license looks like a team that has deployed something
before.

---

## 17. Division of work, schedule, milestones

### 17.1 Module boundaries

```
                 JSON contracts from section 12
                              |
   +--------------------------+--------------------------+
   |                          |                          |
ENGINE                    PRODUCT                  DATA AND EVIDENCE
   |                          |                          |
ingest                    screens E1-E10           detector C
detector A                SSE stream               detector D
detector B                visualizations           IDF corpus
shortlisting              A/B listening            calibration
fusion                    case file                legal layer
                                                   demo cases
```

**The separating rule:** the product never imports anything from the engine. It
talks exclusively over HTTP and SSE, and from hour zero through a mock server
returning contract-conformant responses. The front end is ready before the engine
computes anything, and there is no hour in which somebody waits.

The third role looks like the lightest one, and it is the most differentiating:
case 5 requires manually finding a good pair of works, and calibration is the only
component nobody else will build.

### 17.2 Detector build order

**A, B, IDF filter, D, calibration, C** `[D7]`.

Reversed relative to appendix A of the source specification, which put D first as
the cheapest. That is true on the reference data side (we take the lyrics
ready-made) and untrue on the compute side: D is the only detector that may need
demucs, and A is pure `numpy`. A and B together handle five classes and the whole
demo apart from case 6.

The IDF filter jumps ahead of D, because it costs a few dozen lines, rests on chord
sequences already computed by B and **is the only thing standing behind case 5**.

### 17.3 Schedule

| Hours | Engine | Product | Data and evidence |
|---|---|---|---|
| 0-1 | **measurement M0**, contracts | skeleton on mocks | contracts, candidate selection |
| 1-3 | ingest + detector A | E1, E2, SSE stream | downloading the candidates |
| 3-5 | detector B, shortlisting | E3, E4 time overlay | IDF corpus |
| 5-7 | fusion, decision tree | E4 matrix, A/B listening | IDF filter |
| 7-9 | integration, level 2 | E5, E6 | detector D |
| 9-12 | threshold tuning | E7 chronology, E8 legal | loading the calibration, E9 |
| 12-16 | detector C, if the rest stands | E10 case file | cases 5 and 6 |
| 16-20 | slack for whatever falls apart | | |
| 20-24 | five run-throughs of the scenario, walkthrough | | |

The calibration sample and the model are built **before hour zero** (10.1), so in
hours 9-12 only the loading and the screen remain.

**Safety point: hour 5.** By then there is a working demo with the `EXACT` and
`VERSION` classes, the time overlay and A/B listening. Everything beyond that is an
increment.

Four hours of slack before the end is not a luxury. This plan holds nine things
that may not work the first time, and statistically several of them will not.

### 17.4 Milestones

A milestone counts as met when it can be shown to a stranger without explanation.
Not when the code compiles.

| Milestone | Condition for passing |
|---|---|
| **M0** measurement | `docs/measurements.md` holds timings for demucs, whisper, CQT and the fingerprint **from the target machine**; the schedule confirmed or corrected |
| M1 skeleton | the front end renders a full result from the mock, all screens clickable |
| M2 `EXACT` | a pasted reupload URL gives a verdict and a highlighted shared segment |
| M3 listening | the A/B button switches the sound at the synchronized point |
| M4 `VERSION` | a cover is recognized, the similarity matrix with the path drawn |
| M5 `COMMON` | case 5 returns `COMMON` with the number of works in the corpus |
| M6 calibration | E9 shows the curve with the number of pairs it was built on |
| M7 demo | five run-throughs without failure, the walkthrough fitting into 90 seconds |

**M0 is unconditional and comes first.** All the time estimates in this document
come from the literature, not from the target machine. The difference between
"demucs takes a minute" and "demucs takes four minutes" upends the whole plan, and
it costs 20 minutes to find out `[D1]`.

---

## 18. Fallback ladder

The cutting order for when time runs out. Fixed now, while sober, because at four
in the morning people make bad decisions.

| Level | What goes | What stays in the demo |
|---|---|---|
| 1 | detector C (melody) | the melody bar disappears from E5, it is not mocked |
| 2 | screen E9 (calibration) | confidence described as a preliminary, uncalibrated threshold |
| 3 | detector D (lyrics) | A and B stay, the `LYRICS` class is unavailable |
| 4 | IDF filter | case 5 drops out of the demo, and that is a real loss |
| 5 | everything but A and E1-E4 | the show comes down to "we find reuploads and samples" |

**Level 4 is the limit of meaning.** Without the commonality filter the product
stops differing from any other similarity tool. If the plan reaches that level, it
is better to cut two other things earlier than to lose case 5.

**What we never cut:** the A/B listening on screen E4. The brief requires the
ability to check, and for audio the only real check is the ear. It is one of the
cheaper things in the plan and the strongest in the show.

---

## 19. Known limitations

Written out, because the brief requires stating what is a signal and what is a
limitation, and stating them unprompted is stronger than admitting them when asked.

1. **The thresholds are calibrated on covers.** The catalog contains covers, not
   samples. The thresholds for `EXCERPT` are an extrapolation and have not been
   verified on a representative sample.
2. **The calibration labels are noisy because of title collisions.** `work_title`
   is not the identity of the work (5.2), and the filter in 5.4 reduces the
   contamination but does not remove it. The scale of the residual noise is
   measured by hand on 20 pairs, not computed.
3. **The commonality filter will inherit the corpus bias.** A corpus dominated by
   one genre will inflate the IDF of that genre's patterns and lower sensitivity in
   underrepresented genres.
4. **The `LYRICS` class is uncalibrated** and will stay that way until a source of
   original-adaptation pairs appears (10.4).
5. **Chronology works only for the explicit candidates** with hand-entered dates
   (5.5). For the rest of the system the argument "the oldest one is the original"
   is not available.
6. **Speech transcription fails** on instrumentals, dense mixes and multi-voice
   singing. The gate limits that, but at the cost of detector D's sensitivity.
7. **Melody transcription is unreliable for polyphony.** Detector C works well on a
   clear vocal line, poorly on dense textures.
8. **The system does not settle the question of access.** Similarity without
   showing that the author had contact with the earlier work is not enough to
   establish infringement. Chronology is circumstantial, not proof.
9. **The license layer is only as good as the metadata.** The "unknown" status is
   more frequent than "all rights reserved" and must be displayed as absence of
   information, not as absence of restrictions.
10. **Downloading from platforms.** The demo uses downloading that conflicts with
    the platform's terms of service. In a production deployment the source must be
    official catalog deliveries or your own assets.

---

## 20. The one thing we do not know

Required by the brief. The answer follows from limitation 1:

> Our thresholds are calibrated on covers, because that is the data we got. We do
> not know whether they hold up on samples and remixes, and that is precisely the
> class of cases where the legal stakes are highest. The next step is to build a
> labeled set of samples and repeat the calibration for the `EXCERPT` class.

That is the answer of a team that ran an evaluation, rather than guessing.

---

## 21. Open assumptions

Unsettled things that could upend the plan. Each one can be checked in a dozen or
so minutes and is better checked before hour zero.

1. **Download limits.** The number one risk on the preparation side, ever since
   obtaining labels stopped being one. Several hundred downloads from one address
   in a short time are sometimes restricted. We need a concurrency limit,
   resumption and an error log. **Check on 20 entries before the full sample
   starts.**
2. **Liveness of the addresses in the dump.** We know that 12,937 entries
   disappeared from the catalog over three quarters. We do not know what share of
   the remaining addresses is dead today. The 25% overage from 5.7 is an estimate,
   not a measurement.
3. **Python version and wheel availability for `basic-pitch` and `demucs`.**
   Dependencies capable of failing to build on an older interpreter and eating an
   hour on compilation.
4. **The core quota on the target machine.** How much may be taken without
   degrading the production running on the same server. Set in M0 `[D8]`.
5. **The source of candidate lyrics.** The plan assumes an open lyrics database on
   the reference side. If it turns out to be unavailable, detector D requires
   transcription on the candidate side too, which changes its cost from one-off to
   linear.

---

## 22. What this document deliberately does not settle

- The exact form of the sentence embedding model for detector D.
- The `case file` format (PDF or a printable page).
- Whether `POST /api/explain` calls a local or an external model.
- The repository directory structure.

These decisions belong to the implementers and do not affect the contracts.
