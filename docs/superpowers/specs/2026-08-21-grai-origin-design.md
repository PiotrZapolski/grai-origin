# GRAI ORIGIN - design decisions and execution architecture

Date: 2026-08-21
Status: approved direction, ready to be written out as an implementation plan
Source document: `docs/brief/source-spec.md`

---

## 1. What this document is

The source specification describes **what** the system is to do, and it does that
well. I am not reproducing it here. This document answers the question **how to
build it in 24 hours on the hardware we have**, and settles the places where the
specification does not close with itself.

Every decision below has three parts: what we are deciding, why, and what
reversing it costs. That third part matters, because in a hackathon decisions are
made on incomplete data and you have to know which ones can be undone at three in
the morning and which cannot.

---

## 2. The constraints everything else follows from

| Constraint | Consequence |
|---|---|
| CPU without GPU, shared with agentshub production | Heavy models do not fit on the interactive path |
| ~~We only get the catalog on site~~ the catalog is on disk now | Calibration and the IDF corpus come off the critical path, see section 2A |
| 24 hours, three people | Anything that blocks two people costs double |
| Demo on someone else's network | Nothing essential may depend on the internet at the moment of the show |

The first constraint is the sharpest and needs a sentence of its own:
**another project's production runs on this machine**. A process that takes all
the cores will degrade a live system. That is not a question of courtesy, it is
the condition for being allowed to run anything there at all.

---

## 2A. The SecondHandSongs catalog: measured, not assumed

The catalog arrived **before** the hackathon, not on site. This is the single
biggest change from the first version of this document and it turns the schedule
in our favor: calibration and the commonality corpus can be built at leisure
rather than at hour 13 with the team at full load.

The collection: four quarterly dumps in `Projects/dataset`, each one a CSV in a
zip. The numbers below come from the `export_20260701` dump (the newest) and are
measured, not estimated.

### The shape of the data

Seven columns, one row per performance:

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
disappeared**. That second number matters more than the first and I come back to
it in D11.

### Performance groups, that is where the labels come from

`work_title` groups performances of the same work. That is the source of positive
pairs for the calibration in section 8 of the specification.

| Group size | Number of works |
|---|---|
| 1 performance | 90,379 |
| 2 performances | 47,672 |
| 3-5 | 38,145 |
| 6-10 | 16,724 |
| 11-50 | 16,614 |
| 51+ | 3,600 |

Works with at least two performances: **122,755**. The theoretical number of
positive pairs: 49.5 million, but that number is useless, because it is dominated
by mega-groups (`Summertime` 1,485 performances, `White Christmas` 1,202, `Have
Yourself a Merry Little Christmas` 1,337). Drawing pairs blindly would give a set
made up mostly of carols and jazz standards.

The breakdown that is useful to us:

| Pool | Number of groups |
|---|---|
| At least 2 vocal performances (the `VERSION` class) | 108,199 |
| Mixed vocal + instrumental (`VERSION` without shared lyrics) | 33,474 |
| Instrumental only | 7,942 |
| At least two different languages in the group | 3,541 |
| **2-10 vocal performances, distinguishable title** | **69,208** |

The last row is the pool we draw from. 69,208 groups against a need for 250
positive pairs is a 270-fold surplus, so every quality filter is free.

### Trap: `work_title` is not the identity of the work

There is **no `work_id` column** in the export. The only grouping key is the title
as a string, and titles collide. This is not a theoretical risk; I checked four
cases and all four are contaminated:

| `work_title` | Performances | What is inside |
|---|---|---|
| `Forever Young` | 219 | the Alphaville work **and** the Bob Dylan work, two different pieces |
| `Crazy` | 377 | Seal, Patsy Cline/Willie Nelson, Iron Savior, three different pieces |
| `Home` | 315 | Depeche Mode, Stephanie Mills/Diana Ross |
| `Angel` | 265 | Shaggy, Sarah McLachlan, Jimi Hendrix |

The consequence is direct: naive grouping by `work_title` produces **false
positive pairs**, and those go straight into the regression from section 8.4 and
ruin the thresholds the whole verdict rests on. The labels look authoritative and
they fail silently, which is the worst kind of defect in data. Handled in D9.

### What the catalog does not contain

1. **Release dates.** None at all. That upends screen E7 (the chronology axis),
   whose entire thesis is "the oldest one is the original". Handled in D10.
2. **Links between adaptations and originals.** Translations have their own
   `work_title` in this collection: Clouseau's "Heb ik ooit gezegd" is not in the
   group for Van Morrison's "Have I Told You Lately", it is a separate work. The
   `LYRICS` class therefore has no labels here. Handled in D11.
3. **Structure in the row order.** I checked whether the file is sorted so that
   performances of one work sit next to each other: it is not. Only 10.3% of
   adjacent rows share a `work_title`, and 96,234 works are split across more than
   one block. The first few dozen rows look like hand-picked pairs (Kashmir next
   to Come with Me, that is a sample) and it is easy to draw the false conclusion
   that adjacency encodes a relationship. It does not.

---

## 3. Decisions

### D1. Measurement before planning

**Decision:** the first 20 minutes go to measuring, on the target machine, how
long demucs, faster-whisper, CQT and the fingerprint really take on a 60-second
clip. The result goes into the file `docs/measurements.md` and only then is the
schedule binding.

**Why:** all the time estimates in the specification and in this document come
from the literature, not from this machine. The difference between "demucs takes a
minute" and "demucs takes four minutes" upends the whole plan, and it costs 20
minutes to find out. This is the only item in the plan that is unconditional.

**Cost of reversal:** none, it is a measurement.

---

### D2. Three execution levels instead of one pass

**Decision:** the work splits not by detector, but by **when** it can execute.

| Level | When | What |
|---|---|---|
| 0 | offline, before the demo | candidate representations, IDF corpus, calibration model |
| 1 | live, target 5 s | ingest, detector A, detector B, preliminary fusion, verdict |
| 2 | in the background, arrives as a stream | detector D, detector C, upgrading the verdict |

Level 1 is enough to settle the classes `EXACT`, `MODIFIED`, `VERSION`, `COMMON`
and `NONE`, that is five out of seven, including the trap from case 5. Level 2
adds `LYRICS` and `EXCERPT` in the composition layer and raises the confidence of
the rest.

**Why:** the "under 10 seconds" promise from section 14 of the specification is
unrealistic on CPU when source separation sits on the path. But that promise is
not really about time, it is about the jury not staring at a spinner. The SSE
stream from section 11 and screen E2 already solve that problem, provided the
verdict appears early and **grows** in front of the viewer.

Phrasing for the walkthrough: *the verdict in five seconds, the evidence arriving
over the next thirty*. That is stronger than "ten seconds", because it shows the
layered construction of the system instead of hiding it.

**Cost of reversal:** high after hour 6. The split into levels permeates the SSE
contract and the state model in the front end. It has to be decided at the start.

---

### D3. Whisper before demucs, the gate decides

**Decision:** speech transcription runs on the full mix first. Source separation
is triggered **only** when the confidence gate from section 5.4 rejects the first
pass.

**Why:** demucs sits at the input of two detectors at once and is the most
expensive operation in the whole system. Whisper on a vocal inside a mix does
worse than on a separated one, but not uselessly so, and the confidence gate is
already in the specification and will tell us itself when it is worth paying
extra. That turns a fixed cost into a conditional one.

**A side effect that is an advantage:** screen E2 can show "transcription rejected
by the gate, starting source separation". You can see the system judging its own
confidence rather than merely computing.

**Cost of reversal:** low, it is one branch in the code.

---

### D4. Calibration sample: 500 pairs, not 6,000

**Decision:** the calibration set drops from 6,000 to 500 pairs (250 positive, 250
hard negatives), keeping the hard-negative construction from section 8.2, drawn
per the rules in D9. The catalog is already on disk, so downloading **starts
before the hackathon**, not at minute zero, with a concurrency limit, the overage
from D12 and an error log.

**Why:** a logistic regression on seven features saturates at a few hundred
examples. Six thousand is several hours of downloading and a high failure rate,
for a statistically indistinguishable result. The difference is between
"calibration made it into the demo" and "calibration did not finish in time".

If downloading goes faster than we assume, we increase the sample. That is a
change of one number and rerunning the script.

**Cost of reversal:** none upward, because more data may always be added.

---

### D5. Video and rhythm drop out of scope

**Decision:** the criteria bars on screen E5 are **recording, harmonic similarity,
melody, lyrics**. No rhythm as a separate criterion, no video frame pairs.

**Why:** the addendum about the interface mentions rhythm and video, but sections
1-15 contain neither a rhythm detector nor video. A criterion bar with no detector
behind it is a dummy, and a dummy in an evidence tool is worse than its absence:
the whole product is sold on the fact that every number is backed. Tempo is
reported by detector B anyway as `tempo_ratio`.

**Cost of reversal:** high for video (a new pipeline: frame extraction, perceptual
hashes, separate storage). Low for rhythm, because the rhythmic contour is already
foreseen as an option in step 5 of detector C.

---

### D6. Candidates are a small explicit set, the IDF corpus is a separate number

**Decision:** the candidate set stays small and explicit, per the brief and
section 10.1: 8-12 entries with identifiers. The figure in the thousands visible on
screen E2 concerns the **commonality corpus**, not the candidates, and is labeled
as such.

**Why:** the addendum about the interface says "candidates after shortlisting: 12
of 4,000", which contradicts section 10.1 and the brief. The resolution is that
both numbers are true, they simply refer to different things. The screen will show
two lines:

```
candidates after shortlisting   8 of 12
commonality corpus              4,128 works
```

That is honest and it sounds better than one inflated number, because it shows
that the system consults a large corpus in order to judge the **materiality** of a
match, not in order to search the internet.

**Cost of reversal:** low, they are labels in the UI.

---

### D7. Detector build order reversed relative to appendix A

**Decision:** the order is **A, B, IDF filter, D, calibration, C**.

**Why:** appendix A puts D first as the cheapest, which is true on the reference
data side (we take the lyrics ready-made) but untrue on the compute side: D
requires whisper, and in the pessimistic variant demucs as well. Detector A is
pure numpy and computes in milliseconds, detector B is a single CQT and computes in
seconds. On a machine without a GPU, computational cost is what decides the order.

On top of that, A and B together handle five evidence classes and the whole demo
apart from case six, so they deliver a working product earliest.

The IDF filter jumps ahead of detector D, even though appendix A places it after.
The reason is that the filter costs a few dozen lines, rests on chord sequences
that detector B has already computed anyway, and **is the only thing standing
behind case 5**. Case 5 is the entire difference between this product and any
other similarity tool, so it cannot depend on whether we finish speech
transcription in time. This order is also the one executed by the "data and
evidence" role in the schedule in section 6.

**Cost of reversal:** none, it is a task order.

---

### D8. Processor quota for the hackathon workload

**Decision:** everything we run on the production machine runs in a container with
an explicit core limit, leaving production some headroom. We set the limit after
the measurement from D1.

**Why:** another project's live system runs on this machine. An unconstrained
demucs will take all the cores and degrade it in a way visible to its users.

**Cost of reversal:** none, it is one line of configuration.

---

### D9. Calibration pool with a title collision filter

**Decision:** positive pairs are drawn only from groups meeting all four
conditions, not from all 122,755 groups:

1. between 2 and 10 vocal performances (cuts off the mega-groups of standards and
   carols),
2. distinguishable title: at least 3 words or at least 18 characters (cuts off
   `Crazy`, `Home`, `Angel`, that is where the collisions actually live),
3. **at most one pair per group** (no work dominates the set),
4. both performances in the same language and both vocal, unless the pair is going
   deliberately into the mixed pool.

The filter leaves 69,208 groups. The hard-negative set from section 8.2 stays
unchanged, with one addition: the 90,379 works with exactly one performance are a
pure negative pool, because by definition they have no cover in the catalog.

**Why:** without point 2, pairs such as "Forever Young by Alphaville versus
Forever Young by Bob Dylan" enter the set described as the same work. The
regression from section 8.4 then learns that divergent harmony and divergent
lyrics can be normal in covers, and **lowers the thresholds for the whole**
`VERSION` **class**. The result is false alarms in the demo whose source nobody
will find at three in the morning, because the data looks correct. Point 3 is
equally important: without it half the set is `Summertime`, and the model learns a
single work.

The cost of those four rules is a dozen or so lines in the sampling script and
zero at run time. The pool surplus is 270-fold, so filtering costs nothing.

**Verification that the filter works:** after drawing the sample we listen through
20 positive pairs by hand. If more than one turns out to be different works, the
filter is too weak and we tighten point 2 to 4 words (the pool drops to 43,084,
still with an enormous surplus). That is 15 minutes of work protecting every
threshold in the system.

**Cost of reversal:** none, they are conditions in the query against the set.

---

### D10. Screen E7 gets its dates by hand, or it does not exist

**Decision:** the chronology axis works **only for the explicit set of 8-12
candidates**, and the release dates are entered by hand into the candidate
manifest. For entries outside that set, screen E7 shows nothing. Under the axis,
one sentence: the date comes from release metadata, not from the video platform.

**Why:** the catalog contains no date column at all. Screen E7 rests on the thesis
"the oldest one is the original" and without dates there is nothing to build it
from.

The tempting workaround is to take the publication date from YouTube, and that
**must not be done**. The YouTube upload date is not the release date: a 1959
recording may be uploaded in 2021, and a 2015 cover in 2016. An axis built on those
dates will regularly point at the cover as the original, that is give **the
opposite answer to the product's main question**, and do so in the place that looks
the most objective in the whole interface. In an evidence tool that is a
disqualifying defect, worse than not having the screen.

Entering a dozen or so dates by hand costs 10 minutes, because the candidate set is
curated by hand anyway (D6). The screen stays, the thesis stays, the data is true.

**Cost of reversal:** low. Should a source of release dates appear (MusicBrainz,
Discogs), the axis extends to the full ranking with no changes to the interface.

---

### D11. The `instrumental` flag as routing, the `LYRICS` class without calibration

**Decision:** three things following from the columns the catalog does and does not
have:

1. **Detector D does not run for recordings marked `instrumental`.**
   That is 24.9% of the collection. It saves the most expensive element of the path
   (whisper, conditionally demucs) on every fourth query, and the decision is free,
   because the flag is in the data. On screen E5 the lyrics bar then shows "not
   applicable, instrumental recording", not zero. Zero would mean "we checked and
   there is no similarity", which is untrue.
2. **The 7,942 instrumental-only groups are a negative control** for detector D. If
   transcription returns anything on them above the gate from section 5.4, the gate
   is set wrong. It is the cheapest correctness test in the whole plan.
3. **The `LYRICS` class stays rule-based and explicitly uncalibrated.** In the
   catalog, translations are separate works with their own `work_title`, so
   "original - adaptation" pairs simply do not exist. There are 3,541 multilingual
   groups, but those are mostly the same work sung in several languages under one
   title, not paired adaptations. In the interface the `LYRICS` class gets the
   annotation "preliminary threshold, no calibration data" next to its confidence.

**Why point 3 stays in the product despite the lack of calibration:** the `LYRICS`
class answers a real legal question (reworking lyrics is a different right from a
cover) and test case 4 requires it. Cutting it would be honest but costly in the
demo. Honesty is provided by the label, not by removal: a system that says "I have
no data here" is a stronger argument before a jury than a system pretending it has
data everywhere.

**Cost of reversal:** none for points 1-2. Point 3 reverses the moment a source of
adaptation-original pairs appears.

---

### D12. Dead links included in the download budget

**Decision:** every audio download job (calibration sample, IDF corpus, candidates)
draws **25% more entries than it needs**, and finishes when it has collected the
target number of successful downloads, not when it exhausts the list. The manifest
records what failed to download and why.

**Why:** between the October dump and the July one, **12,937 entries disappeared
from the catalog**, that is about 1.2% over three quarters, and those are only the
ones removed on the SecondHandSongs side. On top of that come videos taken down,
set to private and region-blocked, which the dump does not know about, because the
July snapshot was taken before today. A download planned down to the item arrives
incomplete, and that only surfaces at counting time, at the worst possible moment.

The demo candidates are a separate matter: their files must sit locally before the
show (assumption 5 in section 8), so a dead link is detected during preparation,
not on stage.

**Cost of reversal:** none, it is one number in the script.

---

## 4. Module boundaries

The split into three roles from section 16 stands. For it to be real, the
boundaries have to be contracts, not suggestions.

```
                 JSON contracts from section 11
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
returning contract-conformant responses. Thanks to that the front end is ready
before the engine computes anything, and there is no hour in which somebody waits.

**The shared contracts file** is the only place where those three roles touch. A
change in it requires saying so out loud, because it breaks the work of the other
two people.

**Detector registry:** the engine exposes an interface into which data and evidence
plug C and D without touching engine code. A detector is a function taking a `Clip`
and a list of candidates, returning a list of results or `null`. Fusion copes with
`null` from any detector, because the confidence gate from D3 can return one in
normal operation.

---

## 5. Fallback ladder

The order in which we cut things when time runs out. Fixed now, while sober,
because at four in the morning people make bad decisions.

| Level | What goes | What stays in the demo |
|---|---|---|
| 1 | detector C (melody) | the melody bar disappears from E5, it is not mocked |
| 2 | screen E9 (calibration) | confidence described as "preliminary threshold, uncalibrated" |
| 3 | detector D (lyrics) | A and B stay, the `LYRICS` class is unavailable |
| 4 | IDF filter | case 5 drops out of the demo, and that is a real loss |
| 5 | everything but A and E1-E4 | the show comes down to "we find reuploads and samples" |

**Level 4 is the limit of meaning.** Without the commonality filter the product
stops differing from any other similarity tool. If the plan reaches that level, it
is better to cut two other things earlier than to lose case 5.

**What we never cut:** the A/B listening on screen E4. The brief requires the
ability to check, and for audio the only real check is the ear. It is one of the
cheaper things in the whole plan and the strongest in the show.

---

## 6. Revised schedule

Changes relative to section 16: measurement at the start, calibration moved from
hour 13 to the moment the catalog arrived, detector order per D7.

| Hours | Engine | Product | Data and evidence |
|---|---|---|---|
| 0-1 | **measurement D1**, contracts | skeleton on mocks | contracts, candidate selection |
| 1-3 | ingest + detector A | E1, E2, SSE stream | downloading the candidates |
| 3-5 | detector B, shortlisting | E3, E4 time overlay | IDF corpus (sample downloaded before the start, D4) |
| 5-7 | fusion, decision tree | E4 matrix, A/B listening | IDF filter |
| 7-9 | integration, level 2 | E5, E6 | detector D |
| 9-12 | threshold tuning | E7 chronology, E8 legal | calibration, E9 |
| 12-16 | detector C, if the rest stands | E10 case file | cases 5 and 6 |
| 16-20 | slack for whatever falls apart | | |
| 20-24 | five run-throughs of the scenario, walkthrough | | |

**Safety point: hour 5.** By then there is a working demo with the `EXACT` and
`VERSION` classes, the time overlay and A/B listening. Everything beyond that is an
increment.

Four hours of slack before the end is not a luxury. This plan holds nine things
that may not work the first time, and statistically several of them will not.

---

## 7. Definition of readiness

A milestone counts as met when it can be shown to a stranger without explanation.
Not when the code compiles.

| Milestone | Condition for passing |
|---|---|
| M0 measurement | `docs/measurements.md` holds timings from this machine, the schedule confirmed or corrected |
| M1 skeleton | the front end renders a full result from the mock, all screens clickable |
| M2 `EXACT` | a pasted reupload URL gives a verdict and a highlighted shared segment |
| M3 listening | the A/B button switches the sound at the synchronized point |
| M4 `VERSION` | a cover is recognized, the similarity matrix visible with the path drawn |
| M5 `COMMON` | case 5 returns `COMMON` with the number of works in the corpus |
| M6 calibration | E9 shows the curve with the number of pairs it was built on |
| M7 demo | five run-throughs without failure, the walkthrough fitting into 90 seconds |

---

## 8. Assumptions to confirm before the start

Things we do not know that could upend the plan. Each one can be checked in a
dozen or so minutes and is better checked before hour zero.

1. ~~**Format of the GRAI catalog.**~~ **Settled, section 2A.** Cover-original
   pairs can be extracted from `work_title`, but the key is a string and it
   collides, hence the filter in D9. The labels exist, they are numerous, and they
   are contaminated in a predictable way.
2. ~~**Audio availability.**~~ **Partly settled.** Each of the 1,232,494 rows has a
   unique `youtube_url`, so a sound source exists for everything. What remains
   unsettled is how many of those addresses are alive today, hence the overage from
   D12.
3. **Download limits.** Still open and now the **main preparation risk**, because
   obtaining labels has stopped being one. Several hundred downloads from one
   address are sometimes restricted. We need a concurrency limit, resumption and an
   error log. Check on 20 entries before the full sample starts.
4. **Python version and wheel availability for `basic-pitch` and `demucs`.**
   These are dependencies that can fail to build on an older interpreter and eat an
   hour on compilation.
5. **The network in the room.** The three prepared examples on screen E1 must work
   from a local file, not from a URL. That is the only safeguard against there being
   no internet at the moment of the show and it costs half an hour.

---

## 9. What this document does not settle

Deliberately left out of scope, to be decided along the way:

- The choice of specific works for case 5. It requires listening and judgment, it
  cannot be planned in advance. It is the hardest task of the "data and evidence"
  role and it should start early, because it may take several attempts.
- The final thresholds in the decision tree from section 7. By definition they come
  from calibration, so before it they are entered preliminarily and marked
  explicitly.
- The wording of the texts in the legal layer. It requires review by somebody who
  understands the difference between a technical signal and a legal opinion.
