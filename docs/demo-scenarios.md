# What to paste and what should come out of it

## Pitch cheat sheet

Six addresses, six different things to prove. The order is dramatic: you start
with what builds trust and end with what nobody else will show.

| # | You paste | You will see | Why it matters |
|---|---|---|---|
| 1 | Nick Cave, "Let It Be" | **THE SAME WORK** -> Beatles | The fingerprint does not hit, because this is a different recording. Harmonic similarity hits. The system tells **the work apart from the specific fixation** - two different rights and two different rightholders. |
| 2 | Hubert Laws, "Let It Be", instrumental | **THE SAME WORK**, with lyrics marked **"not applicable"** | We did not write "0% lyrical match", because there is nothing to check. Zero would mean "we checked and there is none". That is the distinction on which the credibility of every other number on the screen rests. |
| 3 | Puff Daddy, "Come with Me" | **RECORDING FRAGMENT** -> Kashmir | This is where you turn on A/B listening. The jury **hears** the same riff in both recordings. The legal panel shows the recognizability indicator, a court criterion translated into a measurable signal. |
| 4 | Fugees, "No Woman, No Cry" | **THE SAME WORK** -> Marley, but **COMMON ELEMENT** -> Let It Be | **This is the moment.** Both share the C-G-Am-F progression in the same key, so the similarity is real and strong. The system says outright: I found it and I believe it does not matter, because that pattern is in hundreds of works. Every other tool will show a match here. |
| 5 | Elvis Presley, "Hurt" | **NO MATCH** to Nine Inch Nails | The reference catalog claims this is the same work, because both entries carry the title "Hurt". That is untrue: Elvis sings a composition from 1954, NIN one from 1994. The system is **right against its own database**, because it listens to sound instead of reading labels. |
| 6 | Sevendust, "Hurt" | **THE SAME WORK** -> NIN 1994, with Cash 2002 also in the ranking | The chronology axis shows **which one is the original**. The date comes from release metadata, not from the video platform - because the upload date would regularly point at the cover as the source. |

A sentence worth saying at the fourth one: *most tools answer the question "how
similar is it". This one answers the question "what kind of similarity is it",
and it is the only one that can say the similarity is immaterial.*

The addresses to copy are in the sections below, together with what exactly to
look at.

---

Concrete addresses to paste into the input field, together with the expected
verdict. All of them come from the SecondHandSongs catalog and all of them have
been checked against the `demo_01` candidate set.

> **State as of now.** The application at `https://grai-origin.agentshub.pl`
> runs in mock mode and **returns the same story for every address**. The
> scenarios below will start working once the engine is wired in and the
> candidate audio is downloaded. Until then, treat this page as a demo
> specification, not as an operating manual.

## Candidate set

This is the entire set the system compares against. Ten entries, in the open.

| id | work | performer | release | license |
|---|---|---|---|---|
| `cand_01` | Kashmir | Led Zeppelin | 1975-02-24 | all rights reserved |
| `cand_02` | Come with Me | Puff Daddy and Jimmy Page | 1998-05-18 | all rights reserved |
| `cand_03` | Hurt | Nine Inch Nails | 1994-03-08 | all rights reserved |
| `cand_04` | Hurt | Johnny Cash | 2002-11-05 | all rights reserved |
| `cand_05` | 34 Ghosts IV | Nine Inch Nails | 2008-03-02 | **CC BY-NC-SA 3.0** |
| `cand_06` | Old Town Road | Lil Nas X | 2018-12-03 | all rights reserved |
| `cand_07` | Let It Be | The Beatles | 1970-03-06 | all rights reserved |
| `cand_08` | No Woman, No Cry | Bob Marley & The Wailers | no date | all rights reserved |
| `cand_09` | Hurt | 2Cellos (instrumental) | no date | all rights reserved |
| `cand_10` | Code Monkey | Jonathan Coulton | no date | **CC BY-NC 3.0** |

---

## 1. Cover, that is `VERSION`

**Paste:** `https://youtube.com/watch?v=MjEJxr538ZA`
Nick Cave, "Let It Be"

**Should find:** `cand_07` (Beatles) as **THE SAME WORK**, high confidence.

**What to look at:** the acoustic fingerprint **does not hit**, and that is how it
should be - a different recording, a different performer, a different
arrangement. Harmonic similarity and lyrics hit. That is the difference between
the phonogram and the work, which is the crux of the first page of the
specification.

On the chronology axis the Beatles 1970 stand before everything else.

---

## 2. Cover without lyrics

**Paste:** `https://youtube.com/watch?v=ndHVm2gCZ6M`
Hubert Laws, "Let It Be", instrumental version

**Should find:** `cand_07` as **THE SAME WORK**.

**What to look at:** the lyrics bar shows **"not applicable, instrumental
recording"**, not zero percent. This is the very distinction the whole product is
about: zero would mean "we checked and there is no match", whereas the truth is
that there is nothing to check. The verdict must come out regardless, because
harmonic similarity is enough.

Instrumentals are 24.9% of the catalog, so this is not an exotic case.

---

## 3. Sample, that is `EXCERPT`

**Paste:** `https://youtube.com/watch?v=vrSyrOaoAug`
Puff Daddy and Jimmy Page, "Come with Me"

**Should find:** `cand_01` (Kashmir) as **RECORDING FRAGMENT**.

**What to look at:** this is the moment for A/B listening. The fragment is short
and repetitive, the fingerprint hits locally rather than across the full length.
The legal panel raises a high-risk flag and shows the **recognizability
indicator** - not a metaphor, but a criterion applied by a court translated into
a measurable signal.

A fallback variant of the same case:
`https://youtube.com/watch?v=9YpvNgCSaCU` (Old Town Road) should find `cand_05`
(34 Ghosts IV). That one is more interesting legally, because the source carries
an **open license**, so instead of a risk flag the system generates ready-made
attribution text to copy.

---

## 4. The trap, that is `COMMON`

**This is the most important scenario in the whole demo.**

**Paste:** `https://youtube.com/watch?v=oA8UEWLUkd0`
Fugees, "No Woman, No Cry"

**Should find two things at once:**

1. `cand_08` (Bob Marley) as **THE SAME WORK** - it is a cover and that is how it
   should be.
2. `cand_07` (Let It Be) as a **COMMON ELEMENT**, not as a match.

**What to look at:** both works share the C-G-Am-F progression in the same key
and have similar tempos, so the harmonic detector will find a **strong
similarity** to Let It Be. And that is exactly why this is a test: the system is
to say outright "I found this similarity and I consider it immaterial", with the
number of works in the corpus that share the same pattern.

Every other tool will show a match here. This one is to degrade it and explain
why.

---

## 5. A system smarter than its own data

**Paste:** `https://youtube.com/watch?v=EfUhip9jvH8`
Elvis Presley, "Hurt"

**Should find:** **NO MATCH** to `cand_03` (Nine Inch Nails) - or at most a common
element. Certainly **not** "the same work".

**Why this is interesting:** in the SecondHandSongs catalog both recordings sit
under the same `work_title` "Hurt", which means **the reference data claims they
are the same work**. And that is untrue: Elvis sings the "Hurt" by Jimmie Crane
from 1954, while Nine Inch Nails is an entirely different composition by Trent
Reznor from 1994.

The catalog has no column with a work identifier, only the title as a string -
and titles collide. If the system rejects this match, it **will be right against
its own reference database**, because it listens to sound instead of reading
labels.

This is also the reason the calibration set filters out short titles: without
that, such pairs would enter training as "the same work" and lower the thresholds
for all covers.

---

## 6. Three performances of one work

**Paste:** `https://youtube.com/watch?v=exdpr709_CI`
Sevendust, "Hurt"

**Should find:** `cand_03` (Nine Inch Nails, 1994) in first place, and in the
ranking also `cand_04` (Johnny Cash, 2002) and `cand_09` (2Cellos, instrumental).

**What to look at:** the chronology axis. Nine Inch Nails 1994 stands before
Johnny Cash 2002, which explains visually **which one is the original**. Under the
axis stands the sentence that the date comes from release metadata, not from the
video platform - because the YouTube upload date would regularly point at the
cover as the source.

For `cand_09` the lyrics bar will again show "not applicable".

---

## 7. Reupload, that is `EXACT`

This scenario requires material the catalog does not contain: **the same
recording under a different address**. SecondHandSongs indexes one address per
performance, so there is no duplicate in it.

For the demo the file has to be prepared by hand: take a candidate recording,
transcode it (different bitrate, different container, possibly trim a few seconds
off the beginning) and point at it as the query.

**Should find:** that same candidate as an **IDENTICAL RECORDING**, with the
fingerprint hitting across the full length and the time alignment showing the
trim.

The same applies to the `MODIFIED` scenario: what is needed is a version sped up
by a few percent and raised by a semitone, that is a file to prepare rather than
an address to paste.

---

## Summary: what each scenario proves

| # | Class | What it proves |
|---|---|---|
| 1 | `VERSION` | it understands the difference between the phonogram and the work |
| 2 | `VERSION` | absence of lyrics is not a zero |
| 3 | `EXCERPT` | the legal layer and the recognizability indicator |
| 4 | `COMMON` | **it has judgment, not just matching** |
| 5 | `NONE` | it trusts the sound more than the labels in the database |
| 6 | `VERSION` | chronology points at the original |
| 7 | `EXACT` | robustness to recompression and trimming |
