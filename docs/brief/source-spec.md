# GRAI ORIGIN - technical specification (source)

> This file is an English translation of the original Polish source brief; the content is otherwise unchanged.

**Provenance & Similarity Engine for audio**
GRAI x VIBESTARS / CASE 03 / extended version

> Source document, preserved unchanged. The design decisions that correct it
> against the realities of the hardware and the schedule are in
> `docs/superpowers/specs/2026-08-21-grai-origin-design.md`. This file is the
> point of reference: when the design doc says "section 8 of the specification",
> it means section 8 of this file.

---

## 0. Summary

The system accepts a URL to an audio clip and returns an ordered list of candidates indicating the most likely source, with a calibrated probability, an evidence class and the ability to verify by listening.

The key difference from the obvious solution: the system does not return a single "similarity" number, it **decides what kind of similarity it is** - whether this is the same fixation, the same composition, a borrowed fragment, or an element common to an entire genre. That last class is what separates a useful tool from a false-alarm generator.

Scope as per the brief: a small, explicit candidate set. We are not building an internet search engine.

---

## 1. The problem - four questions, not one

The query "where does this fragment come from" breaks apart into four independent questions with different answers, different methods and different legal consequences.

| # | Question | Subject matter of protection | Method |
|---|---|---|---|
| 1 | Is this the same sound fixation? | phonogram | acoustic fingerprint |
| 2 | Is this the same work in a different performance? | work | harmonic similarity + lyrics |
| 3 | Was a fragment borrowed? | phonogram or work | local alignment |
| 4 | Is it allowed to be used? | license | metadata |

The system answers all four separately and only at the end folds them into a single decision. Blending them into one score is the most common design error in this class of tools.

---

## 2. Taxonomy of results

Every match result belongs to exactly one class. The class, not the number, is the primary output of the system.

| Class | Code | Condition | Interpretation |
|---|---|---|---|
| Identical fixation | `EXACT` | fingerprint hits, alignment > 15 s | reupload, rip, trim |
| The same fixation, modified | `MODIFIED` | fingerprint partially, tempo/key shift | speedup, nightcore, pitch shift |
| The same work, a different performance | `VERSION` | fingerprint does not hit, harmonic similarity + lyrics do | cover, live, remake |
| Borrowed fragment | `EXCERPT` | local alignment < 15 s, repeating | sample, loop |
| Lyrical overlap | `LYRICS` | only the lyrics hit | translation, reworking, quotation |
| Common element | `COMMON` | only a high-frequency pattern hits | progression, scale, genre rhythm |
| No match | `NONE` | all signals below threshold | |

The `COMMON` class is a result of its own, not a variant of no match. The system is meant to say it outright: "we found a similarity and we believe it is not material" - that is information, not silence.

---

## 3. Architecture

```
URL / file
    |
    v
+-----------------------------------------+
| 1. INGEST                               |
|    download -> demux -> normalization   |
|    -> windows 10 s, hop 5 s             |
+-----------------------------------------+
    |
    +----------+----------+----------+
    v          v          v          v
+-------+ +-------+ +-------+ +-------+
|  A    | |  B    | |  C    | |  D    |
|finger-| |harmony| |melody | |lyrics |
|print  | |       | |       | |       |
+-------+ +-------+ +-------+ +-------+
    |          |          |          |
    +----------+----------+----------+
                    |
                    v
+-----------------------------------------+
| 2. SHORTLISTING                         |
|    candidates -> shortlist <= 20        |
+-----------------------------------------+
                    |
                    v
+-----------------------------------------+
| 3. VERIFICATION (costly, shortlist only)|
|    source separation, DTW, alignment    |
+-----------------------------------------+
                    |
                    v
+-----------------------------------------+
| 4. COMMONALITY FILTER                   |
|    pattern IDF -> degrade to COMMON     |
+-----------------------------------------+
                    |
                    v
+-----------------------------------------+
| 5. FUSION + CALIBRATION                 |
|    evidence class + probability         |
+-----------------------------------------+
                    |
                    v
            ranking + evidence
```

**Overriding rule:** heavy models (source separation, speech transcription) never run on the whole candidate set. Only on the query and on the shortlist after shortlisting. Breaking this rule makes running on laptop-class hardware impossible.

---

## 4. Ingest

**Input:** a URL (YouTube, a direct link to a file) or a local upload.

**Steps:**

1. Download - `yt-dlp -f bestaudio --download-sections "*0-180"`. Limited to 3 minutes; longer material is cut down to the highest-energy fragment.
2. Decoding - `ffmpeg` -> PCM mono 22,050 Hz (the harmonic path) and 16,000 Hz (the speech path).
3. Loudness normalization to -23 LUFS. Without it, energy thresholds stop being comparable between recordings from different sources.
4. Silence detection and trimming at the edges.
5. Windowing: 10-second windows with a 5 s hop (50% overlap). The overlap is necessary so that a fragment does not fall between windows.

**Output:** a `Clip` object with an array of windows, the duration, the sample rates and the SHA-256 digest of the normalized signal (for deduplication and caching).

**The candidate set** is prepared offline through the same pipeline. Every candidate has: `id`, `name`, `artist`, `publication_date`, `license`, plus all the representations from section 5.

---

## 5. Detectors

### 5.1 Detector A - acoustic fingerprint

**Answers questions 1 and 3.**

**Algorithm:** Wang-style spectral landmarks (Shazam). STFT spectrogram (window 2048, hop 512) -> detection of local maxima in a time-frequency window -> pairing each peak with several peaks in a target zone -> a hash from the triplet `(f1, f2, dt)` -> a table `hash -> (candidate_id, offset)`.

**Matching:** for the query we compute, for each candidate, a histogram of offset differences. A genuine match gives a sharp peak - many hashes with **the same** offset difference. Random coincidences spread out flat. This is simultaneously a significance test and the determination of the time alignment.

**Output:**
```json
{
  "candidate_id": "cand_07",
  "matched_hashes": 412,
  "peak_ratio": 0.83,
  "query_span": [12.4, 31.8],
  "candidate_span": [64.1, 83.5],
  "offset": 51.7
}
```

`peak_ratio` = the share of hashes in the dominant bin of the histogram. Below 0.25 we treat it as noise.

**Parameters:** 30-50 peaks per second, target zone of 5 peaks within a 2 s window. Denser sampling increases robustness to compression at the cost of index size.

**Extension for tempo and key change (`MODIFIED`):** we repeat the match over a grid of frequency-axis rescalings in the range +/-6 semitones in 1-semitone steps and time-axis rescalings in the range 0.90-1.15 in 2.5% steps. That is 13 x 11 = 143 variants - expensive, so it runs **only when the match without any transformation failed and detector B returned high similarity.** That condition is crucial: the signal from B says "this is that work", the absence of a signal from A says "but not that version", and the grid answers "because it is sped up by 6%".

**Library:** `audfprint` or a custom implementation on `numpy` + `scipy.ndimage.maximum_filter` (~150 lines). Auxiliary `pyacoustid`/`fpcalc` as a second, independent opinion on `EXACT`.

---

### 5.2 Detector B - harmonic similarity

**Answers question 2.** This is the cover detector.

**Features:** CQT (12 bins per octave, from C1, 6 octaves) -> pitch class profile (chroma / HPCP) -> median smoothing over time -> L2 normalization of every frame. Time resolution ~0.1 s, aggregated to ~2 Hz.

**Key invariance:** we do not transpose to a "detected key" (key detection is unreliable). Instead we compute the similarity for all 12 rotations of the chroma vector and take the maximum. The returned rotation is immediately the information "transposed by N semitones" to show in the UI.

**Similarity:** a cross-similarity matrix between the chroma sequences of the query and the candidate, binarized by a percentile threshold (typically the 10th percentile of distances), then **cumulative alignment along diagonals** (the Serra Qmax variant). The result is the length of the longest coherent diagonal path normalized by the length of the shorter sequence.

Why a diagonal path rather than correlation: a cover has a different tempo, so the path is not parallel to the diagonal, it is tilted and locally disturbed. Alignment absorbs that, correlation does not.

**The same matrix is a UI artifact** - rendered as a heatmap with the path highlighted it is the most visually convincing piece of evidence in the whole system, and it costs nothing extra.

**Preliminary shortlisting:** the full matrix is O(n*m), too expensive for all candidates. Ahead of it we compute a cheap global descriptor: a 2D-DFT of the chromagram, flattened and normalized -> a 256-dimensional vector, compared by cosine. That filters out obvious non-matches in microseconds. The matrix is computed only for the top 20.

**Output:**
```json
{
  "candidate_id": "cand_07",
  "qmax_score": 0.71,
  "transposition": 2,
  "tempo_ratio": 1.06,
  "alignment_path": [[0,0],[1,1]],
  "coverage": 0.62
}
```

`coverage` = what part of the query lies on the alignment path. It distinguishes a cover of the whole work (high) from a borrowed fragment (low) - that is `VERSION` from `EXCERPT`.

**Library:** `librosa` (ISC license) for CQT and chroma, the rest on `numpy`. We deliberately give up Essentia despite its ready-made Qmax implementation - see section 15.

---

### 5.3 Detector C - symbolic melody

**Answers question 3 in the composition layer.** This is the melodic plagiarism detector, the only one that operates on what the law regards as the creative element of a work.

**Steps:**

1. **Source separation** - extracting the vocal and harmonic tracks. Without it, melody transcription on the full mix returns percussion.
2. **Transcription into a symbolic representation** - polyphonic audio-to-MIDI transcription, then extraction of the dominant line (the highest active note in each frame, with hysteresis against flicker).
3. **Quantization** - notes onto the rhythmic grid of the detected tempo; this eliminates interpretive differences.
4. **Conversion into an interval sequence** - instead of absolute pitches we record the differences between successive notes. It gives transposition invariance for free and corresponds to how a human judges melodic similarity.
5. **Optionally a rhythmic contour** - logarithms of the ratios of successive durations, as a second sequence.

**Comparison:** interval n-grams of length 4-8. For each n-gram of the query we look for occurrences in the candidates. Additionally a global match by the Mongeau-Sankoff distance (an edit-distance variant that accounts for note fusion and fragmentation - a melody played with ornaments is still the same melody).

**Output:**
```json
{
  "candidate_id": "cand_07",
  "matched_ngrams": [
    {"interval_seq": [2,2,1,-3,-2], "query_pos": 14.2,
     "candidate_pos": 66.0, "idf": 8.4}
  ],
  "longest_common_run": 11,
  "ms_distance": 0.19
}
```

`longest_common_run` - the length of the longest common interval sequence. That is a number a musicologist and a lawyer both understand: "eleven consecutive identical intervals".

**Cost:** this is the most expensive detector. It runs on the query and the shortlist only.

---

### 5.4 Detector D - lyrics

**Answers questions 2 and 3 in the lyrical layer.** The best accuracy-to-cost ratio - lyrics are a stronger cover invariant than harmony, because a cover changes the arrangement but rarely the words.

**Steps:**

1. Separation of the vocal track (the same result as in detector C, computed once).
2. Speech recognition with word-level timestamps.
3. **Confidence gate** - if the average transcription confidence is below the threshold or the detected language is unstable between windows, the detector returns `null` instead of a result. This is critical: on an instrumental a speech recognition model hallucinates, and without this gate the system will show random text for a work with no vocal.
4. Normalization: lowercasing, removal of punctuation, reduction of vocal repetitions.

**Two-stage comparison:**

- **Literal level** - 5-word shingles, MinHash signatures, Jaccard similarity. Detects copies and quotations. Cheap, scalable.
- **Semantic level** - multilingual sentence embeddings, sentence-to-sentence cosine similarity with alignment. Detects translations and paraphrases that MinHash does not see.

**The reference side:** candidate lyrics are fetched from an open lyrics database, not transcribed. Zero computational cost on the reference side.

**Output:**
```json
{
  "candidate_id": "cand_07",
  "jaccard": 0.64,
  "semantic_sim": 0.89,
  "matched_spans": [
    {"query_text": "...", "candidate_text": "...",
     "query_time": [18.0, 24.5], "idf": 11.2}
  ],
  "asr_confidence": 0.81,
  "language": "en"
}
```

`matched_spans` with timings feeds the highlighted lyrics view in the UI - the user sees *which words* and *when*.

---

## 6. Commonality filter

**Goal:** to tell a borrowing apart from a common element. This is the mechanism that translates the legal principle "creative expression is protected, not the idea or the convention" into working code.

**Construction:** offline, on the reference corpus, we compute the document frequency of every pattern:

- interval n-grams (detector C)
- lyrical shingles (detector D)
- chord sequences derived from chroma (detector B)

For every pattern `w`: `idf(w) = log(N / df(w))`, where `N` is the number of works in the corpus.

**Application:** the match score is weighted by the IDF of the patterns hit. A match based exclusively on low-IDF patterns (below the threshold - typically those occurring in more than 1% of the corpus) is **degraded to the `COMMON` class** regardless of the raw similarity score.

**Interpretation in the UI:** instead of a number we show a sentence along the lines of "this motif occurs in 1,240 works of the corpus - that is a genre convention, not a signal of borrowing".

**Methodological note:** the quality of this filter depends directly on how representative the corpus is. A corpus dominated by one genre will inflate the IDF of that genre's patterns. This has to be written down among the limitations.

---

## 7. Fusion and decision

**We do not compute a weighted average.** The detectors answer different questions, so averaging their results destroys the information about the kind of match. Instead, rules with explicit conditions:

```
IF A.peak_ratio > 0.6 AND A.span_length > 15s
    -> EXACT

IF A(with transformation).peak_ratio > 0.5 AND B.qmax > 0.5
    -> MODIFIED (report the tempo/key rescaling)

IF A.peak_ratio < 0.25 AND B.qmax > 0.55 AND B.coverage > 0.5
    AND (D.semantic_sim > 0.7 OR D = null)
    -> VERSION

IF A.span_length < 15s AND A.repetitions >= 2
    -> EXCERPT

IF B.qmax < 0.4 AND D.jaccard > 0.5
    -> LYRICS

IF (any match) AND mean_idf < commonality_threshold
    -> COMMON

OTHERWISE
    -> NONE
```

The thresholds in this tree **are not pulled out of thin air** - they come from calibration (section 8). The tree is readable and auditable, which matters in a legal application: it is possible to reconstruct why the system reached that decision.

**The chronology rule:** with two matches of the same class and a similar score, the candidate with the earlier first-publication date lands higher in the ranking. The original is usually earlier - this is the cheapest signal in the whole system and often the decisive one.

---

## 8. Calibration

**This is the component that turns a demo into a product.** The brief requires "a readable confidence signal". The output of a similarity function is not confidence - a Qmax of 0.87 does not mean an 87% chance of being right. Without calibration every number in the UI is an ornament.

### 8.1 Data source

The catalog of 1.2 million covers made available by GRAI. **Not as a set to search** - as a source of labels. Titles in this catalog are honest (a cover boasts about the original), so parsing the title yields a `(cover, original)` pair for free. Production queries will have dishonest titles, but the training data has honest ones and that is all that is needed here.

### 8.2 Construction of the set

- **Positives:** 2,000 cover-original pairs drawn from the catalog, after parsing and resolving the titles to canonical works.
- **Hard negatives:** 2,000 pairs chosen to be maximally confusing - the same artist as the original, the same genre, similar tempo and key, but different works. Random negatives are useless, because the system rejects them trivially and the calibration comes out too optimistic.
- **Structural negatives:** pairs sharing a chord progression but not a melody - for calibrating the threshold of the `COMMON` class.

Audio downloaded only for this sample: ~6,000 60-second excerpts.

### 8.3 The calibration model

On the detector outputs (`A.peak_ratio`, `B.qmax`, `B.coverage`, `C.longest_common_run`, `D.jaccard`, `D.semantic_sim`, `mean_idf`) we fit a **logistic regression** with a split into a training and a test set. The output is the probability of the positive class.

A separate model per evidence class - the probability that a match labeled `VERSION` really is a cover is a different quantity from the probability for `EXCERPT`.

Logistic regression rather than a random forest or a network: because it yields weights that can be shown and explained, it is robust on a small sample, and it naturally returns a probability.

### 8.4 Metrics and threshold selection

- ROC curve and AUC per class
- calibration curve (reliability diagram) - a check of whether "90% confidence" really is right in 9 cases out of 10
- selection of the operating threshold at a given precision - for a legal application we target **precision >= 0.95**, because a false alarm about infringement costs more than a miss
- confusion matrix between the evidence classes

### 8.5 Presentation in the UI

Instead of "87% similarity":

> **Confidence 94%** - threshold calibrated on 4,000 pairs from the GRAI catalog.
> At this level the system is wrong in 6 cases out of 100.
> [see the calibration curve]

---

## 9. Legal layer

The system returns **flags and an evidence classification, never a ruling on infringement**. Assessing infringement requires a human. This is not hedging - it is a product feature, because it positions the tool as triage for the legal team rather than a machine handing down judgments.

### 9.1 Separating the rights layers

The result always indicates which layer it concerns:

- **phonogram** (a specific fixation) - hit by detector A
- **work** (composition and lyrics) - hit by detectors B, C, D
- **artistic performance** - a separate layer, flagged with the `VERSION` class

The rightholders and terms of protection differ for each of them, so the same number means something different.

### 9.2 Interpretive rules embedded in the product

| Situation | Signal from the system | Basis |
|---|---|---|
| A low-IDF element | `COMMON`, no flag | protection does not cover ideas, conventions or unprotected elements |
| Inspiration without taking over creative elements | `COMMON` or `NONE` | a work created as a result of inspiration is not a derivative work |
| A short, recognizable fragment of a phonogram | `EXCERPT` + high-risk flag | taking even a very short sound sample may infringe the phonogram producer's right, unless it has been altered in a way unrecognizable to the ear |
| A heavily modified fragment, in a new context | `EXCERPT` + "possible pastiche" flag | the pastiche exception requires evocation of the work, perceptible differences and a recognizable artistic dialogue; the assessment is objective, not based on the creator's intent |
| A candidate under an open license | `NONE` in the risk layer | the license permits the use, the system generates the required attribution |

**Recognizability indicator** - derived from the output of detector A for the `EXCERPT` class: the higher the `peak_ratio` with an unmodified fingerprint, the more the fragment is "recognizable to the ear". This is a legal criterion translated into a measurable signal and it is worth naming outright, because it is not a metaphor - it is a test applied by a court.

**Modification indicator** - the degree of departure from the original (key shift, tempo, spectral filtering, loop length in the new context). High modification with recognizability preserved is a borderline situation and is to be marked as such.

### 9.3 Legal output

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

---

## 10. Data

### 10.1 Candidate set (product)

As per the brief: a small, explicit set. 8-12 candidates visible on screen with identifiers. Each with a full representation profile computed offline.

Candidates are chosen for the demo so as to cover all the evidence classes (section 13).

### 10.2 IDF corpus

3,000-5,000 works from the GRAI catalog, used solely to count pattern frequencies. They need not be candidates. The larger it is, the better the commonality filter.

### 10.3 Calibration set

6,000 excerpts as described in 8.2.

### 10.4 Reference metadata

An open register of music metadata for canonical data and **first-publication dates** (the chronology rule). Import of a dump into a local analytical database, matched on a normalized artist-title key.

---

## 11. API contracts

The contracts are defined before implementation so that three people can work in parallel. The front end works on mocks conforming to this schema from the first hour.

### `POST /api/analyze`

```json
{ "url": "https://...", "candidate_set": "demo_01" }
```
Returns `{ "job_id": "..." }`.

### `GET /api/jobs/{id}/stream` (SSE)

Events in order:
```
{"stage":"ingest","status":"done","detail":{"duration":184.2,"windows":37}}
{"stage":"fingerprint","status":"done","detail":{"hashes":4812}}
{"stage":"harmonic","status":"running"}
{"stage":"transcript","status":"done","detail":{"words":47,"lang":"en"}}
{"stage":"shortlist","status":"done","detail":{"from":12,"to":8}}
{"stage":"verify","status":"done"}
{"stage":"result","status":"done","detail":{}}
```

The stream feeds the live pipeline view. Processing time becomes an element of the narrative instead of an empty spinner.

### `GET /api/jobs/{id}/result`

```json
{
  "query": { "duration": 184.2, "waveform_url": "...",
             "transcript": [] },
  "ranking": [
    {
      "rank": 1,
      "candidate": { "id": "cand_07", "name": "...",
                     "artist": "...", "published": "1977-05-20",
                     "license": "all_rights_reserved" },
      "verdict_class": "EXCERPT",
      "probability": 0.94,
      "evidence": {
        "fingerprint": {},
        "harmonic": {},
        "melodic": {},
        "lyrics": {}
      },
      "alignment": { "query_span": [12.4, 31.8],
                     "candidate_span": [64.1, 83.5],
                     "transposition": 2, "tempo_ratio": 1.06 },
      "commonality": { "mean_idf": 8.4, "corpus_frequency": 3 },
      "legal": {},
      "explanation": "..."
    }
  ],
  "calibration": { "model_version": "lr_v3",
                   "trained_on": 4000, "precision_at_threshold": 0.95 }
}
```

### `POST /api/explain`

Generates a natural-language description from the structured evidence. Invoked **on the user's request**, not automatically - this is the only place in the system where a language model appears, and it must sit off the critical path.

---

## 12. Interface

### 12.1 Visual system

Derived from the GRAI brief:

| Element | Value |
|---|---|
| Background | near-black with an olive cast |
| Accent | acid lime - **exclusively as a signal**, never decoration |
| Headings | heavy sans-serif, white |
| Micro-labels | all caps, lime, small size, wide tracking |
| Surfaces | rounded cards slightly lighter than the background |
| Technical values | monospaced face (scores, timecodes, hashes) |
| Background motif | a large circle, a segment out of frame |
| Footer | a breadcrumb `GRAI ORIGIN / CASE 03 / <screen>` |

Working product name: **GRAI ORIGIN**, subtitle `PROVENANCE ENGINE`. The output report is called a *case file* and laid out with the footer from the brief - the jury sees their own visual language coming back as a product.

### 12.2 Screens

**E1 - Input.** A URL field, a file drop, three buttons with prepared examples (insurance against dead wifi on site). The waveform appears immediately after pasting, before the analysis begins.

**E2 - Live pipeline.** A vertical list of stages lighting up one after another. Each stage shows what it produced: "fingerprint: 4,812 hashes", "candidates after shortlisting: 8 of 12". Fed by the SSE stream.

**E3 - Verdict.** One full-width card: the name of the source, the evidence class badge, the calibrated probability, one sentence of justification. Badge color by class, lime reserved for `EXACT` and `EXCERPT`.

**E4 - Evidence.** Four panels:

- **Time overlay** - two waveforms one above the other, the shared segment highlighted, a slider, **an A/B button switching the listening at the synchronized point**. This is the most important element of the whole interface: the brief requires "the ability to check", and the only real verification for audio is the ear. No chart replaces it.
- **Harmonic similarity matrix** - a heatmap with the alignment path drawn on it.
- **Highlighted lyrics** - two columns, shared phrases emphasized, a click scrolls playback to the spot.
- **Melody** - two staves or a pianoroll representation with the shared interval sequence.

**E5 - Criteria breakdown.** Horizontal bars per detector with the score and a one-sentence interpretation. Next to each: the commonality indicator ("this pattern: 3 works in the corpus" / "1,240 works").

**E6 - Ranking.** Positions 2-N with the class, the probability and a thumbnail of the profile. A click switches the evidence panel.

**E7 - Chronology.** First-publication dates of all the matches on a single axis, the earliest one emphasized. A visual explanation of why *this* one is the original.

**E8 - Legal panel.** The rights layer, risk flags, the recognizability and modification indicators, license status, required attribution, a note that this is not legal advice.

**E9 - Calibration.** ROC curve, reliability diagram, the number of training pairs, precision at the operating threshold. The screen nobody else will have.

**E10 - Case file.** Export of the result as a downloadable report, in the brief's branding.

---

## 13. Demo scenarios

Five cases, each showing a different evidence class. The order matters dramatically.

| # | Case | Expected class | What it proves |
|---|---|---|---|
| 1 | A clean reupload with recompression | `EXACT` | the system works, it builds trust |
| 2 | Cover / live version | `VERSION` | it understands the work versus phonogram difference |
| 3 | A version sped up by 6%, +1 semitone | `MODIFIED` | robustness against Content ID workarounds |
| 4 | A looped, filtered sample | `EXCERPT` | the legal layer, the recognizability indicator |
| 5 | **The trap** - the same progression and tempo, a different work | `COMMON` | **the system has judgment, not just matching** |

Case 5 is the most important. Every team will show that it finds something. Only you will show that the system can say "I found a similarity and I consider it immaterial, and here is why".

Optionally case 6: a candidate under an open license -> the system generates ready-made attribution text.

**Walkthrough** (required by the brief, ~90 seconds): problem -> solution -> result -> limitation. You state the limitation yourselves, before anyone asks.

---

## 14. Evaluation

Metrics computed and shown, not declared.

| Metric | Definition | Target |
|---|---|---|
| Top-1 accuracy | share of queries where the correct source is in 1st place | > 0.85 on cover pairs |
| Recall@5 | the correct source in the top five | > 0.95 |
| Precision at the threshold | correct flags / all flags | >= 0.95 |
| Class accuracy | correctly assigned evidence class | confusion matrix |
| Calibration error | deviation of the curve from the diagonal | ECE < 0.05 |
| Response time | median from URL to verdict | < 10 s |

Separately: **the false alarm rate on structural negatives** - that is, how often the system marks a shared progression as a borrowing. That is a metric worth showing, because it measures exactly what sets you apart.

---

## 15. Stack and licenses

The rule: **permissive licenses only**, so that GRAI can deploy this without a conversation with a lawyer.

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
| MERT | weights under CC-BY-NC - commercial use prohibited |
| Panako | AGPL - a service built on it forces opening the code |
| ACRCloud, AudD, Audible Magic | paid APIs, they move the crux of the problem outside |
| ByteCover | no public weights, would require training |

This table is demo material in itself. A team that deliberately rejected a technically better component because of its license looks like a team that has deployed something before.

---

## 16. Division of work

| Role | Scope | People |
|---|---|---|
| **Engine** | ingest, detectors A and B, shortlisting, fusion | 1 |
| **Product** | UI, SSE stream, visualizations, A/B listening | 1 |
| **Data and evidence** | detectors C and D, IDF corpus, calibration, legal layer, demo cases | 1 |

The third role looks like the lightest one, and it is the most differentiating - case 5 requires manually finding a good pair of works, and calibration is the only component nobody else will build.

### Schedule

| Hours | Task | Checkpoint |
|---|---|---|
| 0-1 | API contracts, front-end skeleton on mocks, start downloading in the background | the front end renders the mock |
| 1-3 | ingest + detector A | `EXACT` works end to end |
| 3-6 | detector D (lyrics) + reference lyrics | **a working demo, the safety point** |
| 6-10 | detector B (harmonic similarity) + the matrix in the UI | `VERSION` works |
| 10-13 | IDF corpus + commonality filter | case 5 works |
| 13-16 | calibration: downloading the sample, regression, screen E9 | real probabilities |
| 16-19 | detector C (melody) - **only if the rest stands** | otherwise a mock with an explicit label |
| 19-21 | A/B listening, legal panel, chronology, case file | |
| 21-24 | five run-throughs of the scenario, fixes, walkthrough | the demo does not fall over |

After hour 6 you have a working product. Everything beyond that is an increment, not a condition.

---

## 17. Known limitations

Written out, because the brief requires stating "what is a signal and what is a limitation", and stating them unprompted is stronger than admitting them when asked.

1. **The thresholds are calibrated on covers.** The GRAI catalog contains covers, not samples. The thresholds for the `EXCERPT` class are an extrapolation and have not been verified on a representative sample.
2. **The commonality filter will inherit the corpus bias.** A corpus dominated by one genre will inflate the IDF of that genre's patterns and lower sensitivity in underrepresented genres.
3. **Speech transcription fails on instrumentals, dense mixes and multi-voice singing.** The confidence gate limits that, but at the cost of detector D's sensitivity.
4. **Melody transcription is unreliable for polyphony.** Detector C works well on a clear vocal line, poorly on dense textures.
5. **The system does not settle the question of access.** Similarity without showing that the author had contact with the earlier work is not enough to establish infringement. Chronology is circumstantial, not proof.
6. **The license layer is only as good as the metadata.** The "unknown" status is more frequent than "all rights reserved" and must be displayed as absence of information, not as absence of restrictions.
7. **Downloading from platforms.** The demo uses downloading that conflicts with the platform's terms of service. In a production deployment the source must be official catalog deliveries or your own assets.

## 18. The one thing we do not know

Required by the brief. The answer follows from section 17, point 1:

> Our thresholds are calibrated on covers, because that is the data we got. We do not know whether they hold up on samples and remixes - and that is precisely the class of cases where the legal stakes are highest. The next step is to build a labeled set of samples and repeat the calibration for the `EXCERPT` class.

That is the answer of a team that ran an evaluation, rather than guessing.

---

## Appendix A - order of detector implementation

If time were only enough for part of it, the order by value-to-cost ratio:

1. **D (lyrics)** - the best ratio, references for free, one file to transcribe
2. **A (fingerprint)** - fastest to build, gives the time alignment for the UI
3. **B (harmonic similarity)** - the crux of cover detection, gives the best visualization
4. **IDF filter** - a few dozen lines, the biggest narrative return
5. **Calibration** - a few dozen lines, the biggest credibility return
6. **C (melody)** - the most expensive, the most unreliable, but the only one operating on the protected element of a work

Items 1-5 are a complete, defensible product. Item 6 is a bonus.

---

## Appendix B - branding and screens (source addendum)

> **Editorial note, added after the matter was settled with the commissioning party.**
> The text below is preserved in the original and lists, in the criteria
> breakdown, bars for "rhythm" and "video". **Video was never in the scope of
> this project** - the system works on sound only, and the reference catalog
> contains audio only, so there is not even any material to compare. Rhythm was
> cut separately, because there is no detector behind it, and a bar without a
> detector is a dummy.
> The binding criteria are four: recording, harmonic similarity, melody, lyrics.
> See decision D5 in the decisions document and section 13.2 of the executive
> specification.

Python and React for sure. UI - the branding from the brief.

The visual system extracted from the PDF: a near-black background with an olive cast, a single acid lime accent, a very heavy white sans-serif in the headings, lime micro-labels in all caps, rounded cards a touch lighter than the background, a large-circle motif in the background, a breadcrumb footer in the style GRAI x VIBESTARS / CASE 03 / 01.

Translate that literally: lime only as a signal (best match, alert, active step), never as decoration. Technical values - scores, timecodes, hashes - in a monospaced font. Name the tool like an internal product, e.g. GRAI ORIGIN with the subtitle PROVENANCE ENGINE. Call the result a case file and generate it in the layout of the same footer as the brief. The jury will see their own visual language coming back to them as a product.

Screens:

Input - a URL field, a file drop, three buttons with ready-made examples. The waveform appears immediately after pasting. Zero empty loading screen.

Live analysis - a vertical list of pipeline steps lighting up one after another, each step showing what it produced ("fingerprint: 4,812 hashes", "transcription: 47 words", "candidates after shortlisting: 12 of 4,000"). That builds the UX narrative the brief scores, and buys you processing time as part of the show.

Verdict - one large card: the name of the source, the evidence class as a badge (IDENTICAL RECORDING / THE SAME WORK / FRAGMENT / NO MATCH), the confidence indicator and one sentence of justification.

Evidence - this is the "wow" moment. Two waveforms laid one above the other with the overlapping segment highlighted, a slider and an A/B button switching the listening between the clip and the candidate at the synchronized point. The jury hears that it is the same thing. No chart replaces that.

Criteria breakdown - horizontal bars with percentages per criterion (recording / melody / lyrics / rhythm / video), each with a one-sentence interpretation on hover. Next to it: a lyrics view with shared phrases highlighted, and pairs of video frames side by side for visual material.

Ranking - positions 2-5 with the score and a thumbnail of the similarity profile, clickable, switching the evidence panel.

Chronology axis - publication dates of all the matched candidates on one line, the oldest one emphasized. It visually explains why this one is the original.

Legal panel - license status, what is permitted, ready-made attribution text to copy, a list of risk flags and a clear note that this is not legal advice.
