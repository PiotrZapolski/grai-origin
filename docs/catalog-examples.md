# The SecondHandSongs catalog - representative examples

A guide to the collection GRAI ORIGIN rests on. Every number and every entry is
**measured and verified** in `export_20260701.csv.zip`, not estimated.

Export columns:

```
performance_id, performance_title, performer, language, instrumental, youtube_url, work_title
```

| Quantity | Value |
|---|---|
| Performances | 1,232,494 |
| Unique `work_title` values | 213,134 |
| Performers | 222,628 |
| Rows with an address | 1,232,494 (100%, each one unique) |
| Instrumental | 307,194 (24.9%) |
| `performance_title` different from `work_title` | 233,599 (19.0%) |

Four quarterly dumps: 1,086,636 -> 1,131,730 -> 1,188,437 -> 1,232,494.
Between the oldest and the newest, **12,937 entries disappeared** - and that
number matters more than the growth, because it says how many links die per
quarter.

---

## 1. Cover, that is the `VERSION` class

The heart of the collection. A work has one `work_title`, many performances, each
with its own address.

### I Put a Spell on You (191 performances)

| id | performer | language |
|---|---|---|
| 33 | Screamin' Jay Hawkins | English |
| 34 | Nina Simone | English |
| 35 | Alan Price Set | English |
| 866 | Creedence Clearwater Revival | English |

Good test material, because the performances are **radically different in
arrangement** while sharing the same harmony and lyrics. Exactly the case for
which the fingerprint detector must fail and the harmonic one must hit.

### Hallelujah (670 performances)

| id | performer |
|---|---|
| 1108 | Leonard Cohen |
| 1109 | Jeff Buckley |
| 1879 | John Cale |
| 1886 | Bono |

Note: some of those 670 are **different works with the same title**. See section 5.

---

## 2. Cover without lyrics, that is `VERSION` with `not_applicable`

### Blackbird (385 performances)

| id | performer | kind |
|---|---|---|
| 1983 | The Beatles | vocal |
| 1984 | Lynne Arriale Trio | **instrumental** |
| 1985 | Chet Atkins | **instrumental** |
| 1986 | Beachfront Property | vocal |

This is the case where it is easiest to get it wrong. The lyrics detector is **not
applicable** here, rather than returning "a score of zero". Fusion must issue
`VERSION` on high harmonic similarity together with `not_applicable` from the
lyrics layer. Writing "0% lyrical match" next to Chet Atkins would be a lie.

There are **33,474** mixed vocal-plus-instrumental groups in the catalog.

### Rainbow Country (4 performances)

| id | performer | kind |
|---|---|---|
| 286 | Bob Marley & The Wailers | vocal |
| 49241 | Dennis Brown | vocal |
| 1129626 | Rock n' Roll Baby Lullaby Ensemble | **instrumental** |

A small group, so cheap to download and fast to test.

---

## 3. Multiple languages in one group

There are **3,541** groups with at least two languages.

### Orly (8 performances)

| id | performer | language | performance title |
|---|---|---|---|
| 928 | Jacques Brel | French | Orly |
| 12916 | Duilio Del Prete | **Italian** | Orly |
| 141681 | Helena [BE1] | French | **Minuit Orly** |

**An important caveat.** These are not "original and adaptation" pairs.
Translations have **their own `work_title`** in this catalog - Clouseau's "Heb ik
ooit gezegd" does not sit in the group for Van Morrison's "Have I Told You
Lately", it is a separate work. That is why the `LYRICS` class has no labels here
and stays rule-based.

---

## 4. A renamed work

19% of performances have a `performance_title` different from the `work_title`.
Sometimes it is a trifle, sometimes an entirely different name.

### Theme for Great Cities (4 performances)

| id | performer | performance title |
|---|---|---|
| 5726 | Simple Minds | Theme for Great Cities |
| 818 | Raven Maize | **The Real Life** |
| 5727 | Minimalistix | Theme **from** Great Cities |

### Cantaloop (Flip Fantasia) (3 performances)

| id | performer | performance title |
|---|---|---|
| 822 | US3 | Cantaloop (Flip Fantasia) |
| 89142 | Mambo Kurt | Cantaloop |
| 869938 | The Manhattan Transfer | Cantaloop (**Flip Out**) |

This is material for the case where **the title does not help and you have to
listen**. Which is exactly the case the product exists for: production queries
have dishonest titles, or none at all.

---

## 5. Trap: the title is not the identity of the work

**There is no `work_id` column in the export.** The only grouping key is a string,
and strings collide. This is not a theoretical risk.

### Forever Young (219 performances, **two different works**)

| id | performer | whose work it is |
|---|---|---|
| 28 | Alphaville | the Alphaville work |
| 29 | Paul Michiels | a cover of Alphaville |
| 16551 | **Bob Dylan** | **an entirely different work** |
| 16552 | Jimmy LaFave | a cover of Dylan |

### Crazy (377 performances, **at least three works**)

| id | performer | whose work it is |
|---|---|---|
| 10829 | Seal | the Seal work |
| 13025 | Patsy Cline | **the Willie Nelson work** |
| 13026 | Willie Nelson | the same one as Patsy Cline |
| 10830 | Iron Savior | **yet another one** |

### Angel (265 performances)

Shaggy (1133), Sarah McLachlan (3915) and Jimi Hendrix (9713) in one group.
Three different works.

**Why this is dangerous.** Naive grouping by title produces pairs described as
"the same work" that are not. Those pairs land in the calibration regression and
teach the model that covers can normally have divergent harmony and divergent
lyrics, which **lowers the thresholds for the whole `VERSION` class**. The result
is false alarms whose source nobody will find, because the data looks correct.

Handling: the filter requires a title of at least three words or eighteen
characters. `Crazy`, `Home` and `Angel` drop out, `Have I Told You Lately` stays.

---

## 6. Trap: mega-groups

| `work_title` | performances |
|---|---|
| Summertime | 1,485 |
| Have Yourself a Merry Little Christmas | 1,337 |
| White Christmas | 1,202 |
| Silent Night! Holy Night! | 1,120 |
| Over the Rainbow | 1,004 |

There are **3,600** groups above 50 performances. The theoretical number of
positive pairs in the whole catalog is 49.5 million, but it is dominated by those
groups: `Summertime` alone yields over 1.1 million pairs.

Drawing pairs blindly would give a set made up mostly of carols and jazz
standards, and the model would learn a single work. That is why the corpus and the
calibration sample reject groups larger than 20, and from the remainder take **at
most one pair per group**.

---

## 7. The distribution, that is how much of what there is in this collection

| Group size | Works |
|---|---|
| 1 performance | 90,379 |
| 2 | 47,672 |
| 3-5 | 38,145 |
| 6-10 | 16,724 |
| 11-50 | 16,614 |
| 51+ | 3,600 |

**90,379 works with a single performance are a pure negative pool** - by
definition they have no cover in the catalog.

| Languages (top 8) | Performances |
|---|---|
| English | 693,273 |
| none (instrumental) | 307,194 |
| Spanish | 72,965 |
| Portuguese | 31,522 |
| French | 30,359 |
| Italian | 16,368 |
| German | 13,003 |
| Finnish | 12,334 |

---

## 8. What the catalog does not contain

1. **Release dates.** No column at all. The chronology axis, which explains why
   *this* one is the original, has nothing to be built from, and the dates have to
   be entered by hand. The YouTube upload date **is not** the release date: a 1959
   recording may be uploaded in 2021, and a 2015 cover in 2016.
2. **Links between adaptations and originals** (section 3).
3. **Structure in the row order.** The first few dozen rows look paired up
   (Kashmir next to Come with Me, that is a sample), but across the whole file
   only 10.3% of neighbors share a `work_title`, and 96,234 works are split across
   more than one block. Adjacency does not encode a relationship.

---

## 9. How to use it

Read it as a stream, do not unpack it - the file is 151 MB:

```bash
unzip -p export_20260701.csv.zip | head -20
unzip -p export_20260701.csv.zip | grep -i "put a spell"
```

Downloading: **only from a home connection**. From a data-center address YouTube
rejects everything, measured 0 out of 20 attempts, a bot-verification message,
seven different clients bounced the same way. From a home connection the success
rate is 59 out of 60.
