# GRAI ORIGIN - license status of the sources (step 3)

> Goal: verified, current information about the licenses of the data sources listed in `specyfikacja-techniczna.txt` (section 15) and in `first-response-from-AI.txt`, so that the team knows exactly what may be downloaded, used and shown at the demo - without guessing.

---

## MusicBrainz (metadata: identifiers, titles, first-release dates)

**The license is split into two parts - this matters, because the initial claim of "CC0 for most of the data" is a simplification:**

| Part of the data | License | What it means |
|---|---|---|
| **Core data** (recordings, artists, releases, relationships) | **CC0** (public domain) | Usable without restriction, no attribution required |
| **Supplementary data** | **CC BY-NC-SA 3.0** | Requires: crediting the source (MusicBrainz), non-commercial use, releasing derivative works under the same license |

**Conclusion for the team:** the chronology rule (first-release date) and the canonical identifiers are most likely core data (CC0) - safe to use without reservations. If you reach for data marked "supplementary", you must add attribution and you may not use it commercially without further verification. **Do not assume in advance which category a given record falls into - check it at import time.**

**Import:** a local PostgreSQL mirror instead of querying the public endpoint (as earlier research suggested) - faster, and it does not load the public API during a hackathon.

---

## MUSAN (audio corpus: speech/music/noise)

**Correction to the earlier note in `first-response-from-AI.txt`:** the official distribution page (OpenSLR) states the license of the whole corpus as **CC BY 4.0** (Attribution 4.0 International), not "US public domain or CC" in general terms, as was written earlier. CC BY 4.0 **permits commercial use**, provided appropriate attribution is given.

**Required attribution (citation):**
> Snyder, D., Chen, G., & Povey, D. (2015). *MUSAN: A Music, Speech, and Noise Corpus.* arXiv:1510.08484.

**Note:** the earlier description (a `LICENSE` file binding each file to a separate license) may refer to the internal structure of the package of source materials for the corpus (MUSAN is a compilation from many sources) - if the team plans to pull individual files out as demo examples (not just train on the whole thing), it is worth **verifying the `LICENSE` file in the downloaded package**, because individual recordings inside it may have different original sources, even though the corpus as a whole is released collectively under CC BY 4.0.

---

## LRCLIB (reference lyrics, synchronized)

**License of the repository/code:** MIT (permissive, allows commercial and research use without restriction).

**Important caveat:** the MIT license covers the **code** of the LRCLIB project (server/API), **not the lyrics content** in the database. The lyrics themselves come from users and may be covered by the copyright of composers/publishers - LRCLIB does not claim rights to the lyrics content, it only provides the infrastructure for searching it. For your use case (comparing the lyrics of a query against reference lyrics in order to detect similarity, not redistributing lyrics) this is not a problem - but **do not present it as "lyrics under an open license"** in the legal layer, only as a "reference source for comparison", so as not to suggest something untrue to the jury.

**Status:** no explicit query limits in the public documentation - treat it sensibly (do not generate thousands of queries in a loop without need).

---

## Summary - what can safely be said at the demo

| Source | Used for | What can be said to the jury |
|---|---|---|
| MusicBrainz (core data) | release dates, canonical IDs | "Core data under CC0 - no restrictions." |
| MusicBrainz (supplementary) | additional metadata | "This part of the database is licensed CC BY-NC-SA - we use it non-commercially only, with attribution." |
| MUSAN | test/training audio corpus | "CC BY 4.0 license, commercial use permitted, citation required." |
| LRCLIB | reference lyrics | "Infrastructure under the MIT license - the lyrics themselves remain the property of their authors, we use them purely for comparison, not redistribution." |

**Anecdote for the demo (confirmed):** MusicBrainz really does have a license split across parts of the data - the AI-research authors themselves joked that "even the database about licenses has two licenses". That is true and can safely be repeated on stage.

---

## To be done by the team

1. At MusicBrainz import time - mark in the database which fields come from core data (CC0) and which from supplementary (CC BY-NC-SA), so that the legal panel (`license_status`, `required_attribution`) can distinguish them correctly per record rather than in bulk.
2. Check the `LICENSE` file in the downloaded MUSAN package with respect to the specific files used as demo examples (cases 1 and 6 from `grai-przypadki-demo.md`).
3. In the legal panel (E8) do not call the LRCLIB lyrics "openly licensed" - it is a reference source, not licensed content for redistribution.

---

## Sources

- [About / Data License - MusicBrainz](https://musicbrainz.org/doc/About/Data_License)
- [musan - OpenSLR](https://www.openslr.org/17/)
- [GitHub - tranxuanthang/lrclib](https://github.com/tranxuanthang/lrclib)
