## 1. Three subject matters of protection - and why they must be kept apart

The same match result means entirely different legal consequences depending on which layer the detector hit. That distinction is the basis of the `rights_layer` field in the API output.

| Subject matter of protection | What it is | Who holds the rights | Which detector hits it |
|---|---|---|---|
| **Work** (composition + lyrics) | The creative layer: melody, harmony, lyrics | Composer / lyricist (or publisher after transfer of rights) | B (harmonic similarity), C (melody), D (lyrics) |
| **Phonogram** | A specific sound fixation - that recording, not the work | Phonogram producer (usually the label) | A (acoustic fingerprint) |
| **Artistic performance** | The way a specific artist performs it (interpretation, live arrangement) | Performer | flagged with the `VERSION` class |

Basis: Polish copyright law (the Act of 4 February 1994 on Copyright and Related Rights) protects the work separately (art. 1) from the subject matter of related rights - phonograms and artistic performances (chapter 11 of the Act) - with separate rightholders and separate terms of protection. That is why an identical numerical result from detector A (phonogram) and from detector B/C/D (work) does not mean the same thing - and the product must show that separately, not as a single score.

**Microcopy for the UI (E8, the "Rights layer" field):**
> "This match concerns the **[phonogram / work / performance]** - the [layer name] and the work are two different subject matters of protection with different rightholders."

---

## 2. Inspiration versus plagiarism - the test for the system

**Legal basis:** art. 2 of the Act on Copyright and Related Rights.

- Art. 2(1): a derivative work based on someone else's work (translation, reworking, adaptation) is the subject of a separate copyright, but disposing of it and using it requires the consent of the author of the original work.
- **Art. 2(4) - the key provision:** *"A work created as a result of inspiration by another work is not considered a derivative work."* Inspiration requires no consent and is not an infringement.

**The boundary between inspiration and derivative work/plagiarism:** taking over creative elements (a specific melody, a specific harmonic arrangement, a specific lyrical phrase) from someone else's work requires consent. Taking over the idea itself, a mood, a genre convention or an unprotected element (a major scale, a typical chord progression, a standard genre rhythm, a banal phrase) does not require consent, because copyright does not protect ideas, only their creative expression.

**The practical test for the system:** is the element that was taken over protected in itself (that is, does it carry a sufficient level of individual creativity), or is it an element common to and conventional within the genre? That question maps directly onto the mechanism of the **commonality filter** (section 6 of the specification, IDF over patterns) - an element occurring in hundreds of works in the corpus is evidence of convention, not of borrowing.

**Microcopy for the UI (the `COMMON` class):**
> "We found a similarity - and we believe it is not legally material. This pattern occurs in **[N]** works in our reference corpus, which points to an element common to the genre (e.g. a chord progression, a rhythm) rather than to a borrowing of protected creative expression."

---

## 3. Sampling as pastiche - Pelham I and Pelham II (CJEU)

This is the part other teams will probably skip - and the strongest point of the demo's legal narrative.

### Pelham I (C-476/17, judgment of 29 July 2019)

The CJEU held that a phonogram producer may prohibit the taking of even a very short sound sample by way of recording, **unless** the sample has been included in the new work in a modified form **unrecognizable to the ear** on listening. Recognizability of the sample to the average listener is therefore the first boundary test.

### Pelham II (C-590/23, judgment of 14 April 2026)

A continuation of the same case (Kraftwerk vs. Pelham). The CJEU clarified the scope of the **pastiche exception** in art. 5(3)(k) of the InfoSoc Directive - that is, the situation in which use of a sample is lawful despite being recognizable, because it falls within a creative exception. The Court established **three cumulative conditions** that the new work must meet in order to qualify as pastiche:

1. **Evocation** - the new work must evoke one or more existing works.
2. **Perceptible difference** - the new work must differ noticeably from the source.
3. **Recognizable artistic dialogue** - the new work must enter into an artistic or creative dialogue with the source work, recognizable as such, using elements characteristic of the original.

**Key point for the system:** the Court expressly ruled out examining the subjective intent of the creator. **It is enough that the pastiche character is objectively recognizable** to someone who knows the source work. The Court also expressly reserved that **"covert imitation and plagiarism" remain outside the scope of the exception** - pastiche is not a back door for undisclosed copying.

This means that "recognizability to the ear" and "perceptible difference" are not metaphors - they are legal criteria that can be translated into measurable signals of the technical pipeline:

| Legal criterion (Pelham I/II) | Technical signal in the system |
|---|---|
| Recognizability of the sample to the ear | `recognizability` - derived from `peak_ratio` of detector A for the `EXCERPT` class: the higher it is with an unmodified fingerprint, the more recognizable the fragment |
| Perceptible difference / degree of modification | `modification` - the degree of departure from the original (key shift, tempo, filtering, loop length in the new context) |
| Recognizable artistic dialogue | not measurable automatically - the system **does not assess** this, it only flags the situation as requiring human judgment |

**Microcopy for the UI (the `EXCERPT` class, the `recognizable_excerpt` flag):**
> "The fragment is recognizable to the ear (recognizability indicator: **[X]%**) - under Pelham I (CJEU, 2019) such a sample may require the consent of the phonogram producer."

**Microcopy for the UI (the `possible_pastiche` flag):**
> "The fragment is heavily modified and embedded in a new context (modification indicator: **[Y]%**) - it may qualify as pastiche within the meaning of the CJEU judgment in Pelham II (C-590/23, 14.04.2026). Assessing whether all three conditions are met jointly (evocation, difference, artistic dialogue) requires a human."

---

## 4. License status - a separate source of truth

License status **does not follow from the audio analysis** - it is a separate metadata layer, independent of whether the system detected a similarity.

- **MusicBrainz** - an open register of music metadata. Most of the data is published under **CC0** (may be downloaded and used freely), part of the database is covered by **CC BY-NC-SA 3.0** - this has to be distinguished per record, not assumed as one license for the whole database.
- **MUSAN** - a corpus of about 109 hours of audio in the public domain (US) or under a Creative Commons license, with a `LICENSE` file binding each file to its license and required attribution; deliberately limited to content that permits commercial use.
- **LRCLIB** - a free, open API with synchronized lyrics, without limits and without terms-of-service problems - the reference source for detector D.

**The rule for the product:** an "unknown" status must be displayed as **absence of information**, never as "no restrictions". This is literally point 6 of section 17 of the specification (known limitations) - a more frequent case than "all rights reserved".

**Microcopy for the UI (the `license_status` field):**
- `cc0`: "Public domain / CC0 - may be used without restriction."
- `cc_by` / `cc_by_nc_sa`: "License **[name]** - attribution required: *[required_attribution]*."
- `all_rights_reserved`: "All rights reserved - use requires the rightholder's consent."
- `unknown`: "License status unknown - this does not mean there are no restrictions, only that no metadata is available."

---

## 5. Legal output as a flag, not a ruling

In accordance with section 9.3 of the specification, every result is to contain a standardized legal block:

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

**Disclaimer - fixed text, always displayed with panel E8:**
> "This tool indicates technical signals (similarity, recognizability, metadata status); it does not assess infringement of the law. Assessing whether copyright or related rights have been infringed requires analysis by a lawyer - including establishing whether the author of the new work had access to the earlier work (publication chronology alone is circumstantial, not proof)."

This positions the product as a **triage tool for the legal team**, not a machine handing down rulings - in line with the assumption in section 9 of the specification.

---

## 6. Short cheat sheet - evidence class to legal message

| Class (`verdict_class`) | Message in the UI |
|---|---|
| `EXACT` | "Identical sound fixation - concerns rights in the phonogram." |
| `MODIFIED` | "The same fixation, modified (tempo/key) - still concerns rights in the phonogram." |
| `VERSION` | "The same work, a different performance - concerns rights in the composition and lyrics, not in the specific recording." |
| `EXCERPT` | "Borrowed fragment - check the recognizability and modification indicators (the Pelham I/II criteria)." |
| `LYRICS` | "Lyrical overlap only - possibly a translation, a quotation or a reworking." |
| `COMMON` | "Similarity detected, but this is an element common to the genre - not a signal of infringement." |
| `NONE` | "No material match in the candidate set." |

---

## Sources

- [CJEU Clarifies Pastiche Exception for Sampling in Pelham II - National Law Review](https://natlawreview.com/article/cjeu-clarifies-pastiche-exception-under-eu-copyright-law)
- [Pelham II case: CJEU redefines the "pastiche" exception and its application to sampling - ECIJA](https://www.ecija.com/en/news-and-insights/caso-pelham-ii-el-tjue-redefine-la-excepcion-de-pastiche-y-su-aplicacion-al-sampling/)
- [Pastiche of a work is also sampling (CJEU judgment in Pelham II) - Lege Artis](https://czasopismo.legeartis.org/2026/04/pastisz-utworu-sampling-kraftwerk-pelham-wyrok-tsue/)
- [Art. 2 of the Act on Copyright and Related Rights - LexLege](https://lexlege.pl/ustawa-o-prawie-autorskim-i-prawach-pokrewnych/art-2/)
- [Music Sampling and Pastiche: CJEU Defines the Scope of a Key Copyright Exception - Jones Day](https://www.jonesday.com/en/insights/2026/05/music-sampling-and-pastiche-cjeu-defines-the-scope-of-a-key-copyright-exception)
