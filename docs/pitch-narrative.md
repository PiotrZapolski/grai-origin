# GRAI ORIGIN - the pitch narrative

Copyright checking at catalog scale. What happens technically, stage by stage,
and why this construction carries over to millions of recordings.

---

## 1. The problem, before a word about technology

GRAI is a music company with a catalog. The question "does this sound infringe
someone's rights" comes up with every new entry, every upload, every license.
Today it is answered by a human, and an expensive one - a lawyer or a
musicologist.

**The key observation: this is not one question, it is four.**

| Question | What is protected | Who holds the rights |
|---|---|---|
| Is this the same fixation? | phonogram | producer, usually the label |
| Is this the same work played differently? | composition and lyrics | composer, lyricist |
| Was a fragment borrowed? | phonogram or work | depends which |
| Is it allowed to be used? | license | depends on the contract |

A tool that returns a single similarity number answers none of them. It answers
the question "how similar", which nobody asked.

**This is the sentence worth opening the pitch with:** *most tools say how similar
something is. We say what kind of similarity it is, because only that has legal
consequences.*

---

## 2. What happens after you paste an address, stage by stage

### Stage 0, before the question: the catalog computed offline

Every recording in the catalog has three representations computed once and
stored: an **acoustic fingerprint** (a few thousand hashes), a **harmonic
profile** (a chromagram plus a 256-dimensional vector) and **lyrics** (if there
are any).

That is a one-off cost per catalog entry, not per query. I come back to this in
the section on scale, because the whole trick lives there.

### Stage 1, loading: bringing everything to a common scale

Download, decode, loudness normalization to **-23 LUFS** per the BS.1770-4
standard, silence trimming, windowing into ten-second windows with half overlap.

Normalization is not cosmetic. Without it the same energy threshold means
something different for a vinyl rip and for a studio master, so every threshold in
the system starts lying. Our measurement is anchored to the standard at two
independent points: a 1 kHz sine reads **-3.0036 LKFS** against the reference
-3.01.

### Stage 2, acoustic fingerprint: is this the same fixation

Shazam-style spectral landmarks. Local spectral maxima, paired into triplets,
turned into hashes. For the query and each candidate we compute a **histogram of
offset differences**.

And here is something worth saying out loud, because it sounds like magic and is
simple statistics: **a true hit gives a sharp spike, chance gives a flat
distribution.** If two recordings are the same fixation, hundreds of hashes agree
at **the same** time offset. If it is coincidence, the hits scatter evenly.

The same histogram also yields the **time alignment**, that is the information
about which second of each recording holds the shared fragment. That is what feeds
the A/B listening.

### Stage 3, harmonic similarity: is this the same work

A cover has a different arrangement, a different voice, a different tempo and a
different key, so the fingerprint will not catch it. What catches it is the
**harmonic profile**: twelve pitch classes over time, compared through cumulative
alignment along diagonals.

Two decisions worth naming, because both are counterintuitive:

**We do not detect the key.** Key detection is unreliable, and its error would
propagate into the whole result. Instead we compare **all twelve rotations** and
take the best one. The rotation number is a ready-made answer to "transposed by N
semitones".

**We do not compute correlation, but a diagonal path.** A cover has a different
tempo, so the match does not run parallel to the diagonal, it is tilted and
locally ragged. Correlation does not see that, alignment does. Measured: a cover
stretched in time by 40% gives us the maximum score, unrelated material 0.117.

### Stage 4, the commonality filter: does this similarity mean anything at all

**This is the stage that sets this tool apart from all the others.**

On the reference corpus we count how often each pattern occurs: a chord sequence,
a sequence of melodic intervals, a lyrical phrase. A pattern occurring in half the
corpus is nobody's property, it is a genre convention.

A match based exclusively on commonplace patterns is **degraded to the "common
element" class**, no matter how high the raw score was.

This is not a clever heuristic, it is a statute translated into code. Art. 2(4) of
the Act on Copyright: *a work created as a result of inspiration by another work
is not considered a derivative work*. The law does not protect ideas or
conventions, only creative expression. The commonality filter answers exactly the
question of which side of that boundary the pattern found falls on.

### Stage 5, the verdict: a class, not a number

A rule tree with explicit conditions, checked in a fixed order. The result is
**one of eight classes**, not a percentage:

`EXACT` the same fixation, `MODIFIED` the same one sped up or retuned, `VERSION`
the same work performed differently, `EXCERPT_PHONOGRAM` a borrowed fragment of a
recording, `EXCERPT_WORK` a borrowed phrase of a composition, `LYRICS` lyrical
overlap only, `COMMON` a common element, `NONE` nothing.

The tree is auditable. It is possible to show **why** the system reached that
decision, which in a legal application is not a luxury but a condition of
usefulness.

### Stage 6, in the background: lyrics and melody

Speech transcription and melody transcription are the most expensive operations in
the system and the only ones requiring source separation. That is why they are
**not on the critical path**.

The preliminary verdict lands after stage 5. Stage 6 arrives in the background and
**upgrades** the verdict. Phrasing for the pitch: *the verdict in five seconds, the
evidence arriving over the next thirty.*

---

## 3. Why this scales

This is the crux of the deployment conversation, so it is worth saying outright.

### The expensive things never touch the catalog

This is the single rule from which all the scalability follows:

| Operation | How many times per query | Depends on catalog size |
|---|---|---|
| Source separation, speech transcription, melody transcription | once, on the query itself | **no** |
| Full harmonic similarity matrix | at most 20 times | **no** |
| Hash lookup in the index | a few thousand times | sublinearly |
| 256-dimensional vector comparison | once per candidate, vectorized | linearly, but in seconds for millions |

**The cost of the heavy part is constant regardless of whether the catalog holds a
thousand entries or ten million.** The catalog is touched only by operations that
are an index lookup or a matrix multiplication.

Concretely, for the 1.2 million recording catalog we already have:

- **Fingerprint**: an inverted hash index. A query has a few thousand hashes, each
  one a dictionary lookup. That is exactly how Shazam works at billions of queries.
- **Harmonic similarity**: 1.2 million vectors of 256 dimensions is about 300 MB in
  float16. An approximate nearest neighbor index returns the top twenty in
  milliseconds.
- **The rest**: computed on twenty entries, that is on a constant.

Growing the catalog is a **one-off, offline, parallelized** cost, not a per-query
cost.

### At scale, finding things stops being the problem

And this is the most important sentence in this section.

In a catalog of ten thousand entries you can review the results by hand. In a
catalog of a million **everything matches something**. The I-V-vi-IV progression
occurs in tens of thousands of works, so a naive similarity system will return tens
of thousands of hits per query and drown the legal team.

**The bottleneck at scale is not detection, it is not drowning in the results.**
That is why the commonality filter and calibration are not ornaments but the
condition for this being deployable at all.

Calibration answers the question of what a score actually means: a regression model
on labeled pairs from the catalog turns raw similarity into a **probability that can
be checked**. We pick the operating threshold for **precision of at least 0.95**,
because in a legal application a false alarm costs more than a miss: the first eats
a lawyer's time, the second comes back years later.

### The deployment path

1. **A batch index for the whole catalog**, once, offline. A fingerprint and a
   harmonic vector for every entry.
2. **A queue instead of a live request** for batch work. The interface you see is
   for the single-item case, but the engine is the same.
3. **Threshold monitoring.** The catalog changes, so the distributions shift.
   Calibration is a living component, not a one-off.

---

## 4. Why this catches plagiarism, not just duplicates

Any acoustic fingerprint will find a duplicate. Plagiarism is harder, because by
definition it **is not the same recording**.

Three things make it possible:

**Separating the layers.** The same number means something different for a
phonogram and for a work. Sampling someone else's recording infringes the
producer's rights, even if the composition is original. Playing someone else's
melody with your own band infringes the composer's rights, even though no sound was
copied. A system that blends this into one score cannot answer either of those two
questions.

**Comparison at the level of the composition, not the signal.** Interval sequences
of a melody are invariant to transposition and to arrangement. Along the way we
return the **longest common sequence of intervals**, that is a number a musicologist
and a lawyer both understand: "eleven consecutive identical intervals".

**Telling borrowing apart from convention.** Without that there is no plagiarism
detection, only suspicion generation.

### Where the boundary lies, and that has to be said unprompted

Of the three conditions for pastiche that the CJEU established in the judgment
**Pelham II (C-590/23, 14 April 2026)**, we measure two: the **recognizability of
the fragment to the ear** and the **degree of modification**. The third, the
**recognizable artistic dialogue**, we do not measure and will not measure.

The system **does not rule on infringement**. It returns an evidence class and
flags, and leaves the judgment to a human. That is not hedging, it is positioning:
this is triage for a legal team that has too much material and too little time.

The system also does not settle the question of **access**. Similarity without
showing that the author could have known the earlier work is not enough to
establish infringement. Chronology is circumstantial, not proof, and it is
described that way in the interface.

---

## 5. What we still do not know

Required by the brief, and better said unprompted than in answer to a question.

**The harmonic threshold is calibrated on real recordings; the probability model
is not.** `VERSION_QMAX` and the binarisation percentile of the Qmax sieve were
measured on real audio - one real cover pair and 541 real negative pairs - and
that measurement is in `docs/calibration-harmonic.md`. It settles the
false-alarm side; the recall side rests on that single pair. The probability
calibration model, the one behind the confidence figures, is a separate thing
and it is not trained, so every probability is marked `uncalibrated`. The
SecondHandSongs catalog is 1.2 million performances grouped by work - an ideal
source of labels for the class "the same work" - but we do not know whether
those thresholds hold up on samples and remixes, and that is precisely the class
of cases where the legal stakes are highest.

The next step is concrete: build a labeled set of samples and repeat the calibration
separately for the fragment class.

The second thing worth mentioning, because it shows we read our own data: **the
reference catalog itself makes a mistake our system can catch.** It has no work
identifier, only the title as a string, so Elvis Presley's "Hurt" from 1954 and Nine
Inch Nails' "Hurt" from 1994 sit in one group as the same work. Our system listens
to sound instead of reading labels, so it will say those are two different
compositions - and it will be right against its own reference database.
