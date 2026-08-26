/**
 * The technical description of every step: what this element of the engine does
 * and what it gives when comparing the query against the whole recording
 * database.
 *
 * The content is **exactly what the product owner wrote** - this is what he will
 * be saying from the stage, so the screen has to agree with it sentence by
 * sentence. We do not shorten and we do not paraphrase; only the formatting has
 * been tuned.
 *
 * The keys correspond to the chapter identifiers from
 * `components/pipeline/chapters`.
 */

export interface StepDescription {
  /** What this element of the engine does. */
  how: string;
  /** What it gives when comparing against the database. */
  why: string;
}

export const STEP_DESCRIPTIONS: Record<string, StepDescription> = {
  ingest: {
    how: "We bring the query to exactly the same form in which we hold every entry of the database: mono 22,050 Hz, loudness normalized to -23 LUFS under the BS.1770-4 standard, ten-second windows with fifty percent overlap.",
    why: "Without this step the comparison is not a comparison: the same energy threshold would mean one thing for a vinyl rip and another for a studio master. This is the equivalent of normalizing text before indexing documents.",
  },
  fingerprint: {
    how: "We turn the peaks of the spectrum into hashes and look them up in an inverted index covering the whole database, exactly the way a search engine looks words up in a document index.",
    why: "The cost does not grow with the size of the database, because this is a lookup in a dictionary and not a scan. The histogram of offset differences settles at the same time whether the hit is real: a true match gives a sharp spike, coincidence gives a flat distribution.",
  },
  harmonic: {
    how: "Every entry of the database has a precomputed 256-dimensional vector describing its harmonic profile. We compare the query against it by cosine similarity and narrow the database down to the twenty nearest, as in semantic search over embeddings.",
    why: "Only on those twenty do we compute the expensive alignment matrix. The costly part therefore never touches the database at all, and the whole system scales to millions of recordings without the cost of a query going up.",
  },
  commonality: {
    how: "We count in how many entries of the reference corpus the matched pattern occurs and weight the result by it. This is inverse document frequency, the same mechanism that in a search engine tells a meaningful word from a conjunction.",
    why: "With a database counted in millions everything matches something, because a popular chord progression sits in tens of thousands of works. This step tells a borrowing from a convention of the genre, and it is the only reason the results can be used at all without drowning a lawyer in them.",
  },
  "verdict-preliminary": {
    how: "A rule tree with explicit conditions assigns one of the eight evidence classes, using nothing but the fingerprint and the harmony, that is, whatever could be computed against the whole database in a few seconds.",
    why: "The answer is there before the slower evidence arrives, and because the tree is auditable, we can show which condition decided. In a legal application that is not a luxury but the condition of being useful at all.",
  },
  lyrics: {
    how: "We transcribe the vocal and compare five-word shingles using MinHash signatures, the technique used to detect duplicates in large collections of documents. The confidence gate rejects a transcript that cannot be trusted.",
    why: "Candidate lyrics are taken ready-made, so the database needs no processing at all and the entire cost is the single recording of the query. The gate also tells the absence of lyrics from a check that was never made: a speech model hallucinates on an instrumental.",
  },
  melodic: {
    how: "We transcribe the melodic line into symbolic form and compare interval n-grams rather than absolute pitches, indexing them like phrases in a text.",
    why: "This gives invariance to transposition and arrangement, and a number both a musicologist and a lawyer can read: how many consecutive intervals are identical. It is the only detector operating on what the law treats as the creative element of a work.",
  },
  "verdict-final": {
    how: "The slower evidence joins the evidence from the first level and the tree recomputes the class and the confidence again, this time on the full set of signals.",
    why: "The verdict may change and that is a feature, not a defect: you can see the system lift its own answer once it is given more data. Calibration turns the raw score into a probability that can be verified.",
  },
};
export function stepDescription(id: string | null | undefined): StepDescription | null {
  if (typeof id !== "string") return null;
  return STEP_DESCRIPTIONS[id] ?? null;
}
