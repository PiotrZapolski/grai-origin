/**
 * Splitting the analysis run into chapters of the show (screen E2).
 *
 * The SSE stream sends a dozen or so events, but **the narrative has eight
 * moments**, not a dozen. A chapter is a unit of storytelling: one sentence can
 * be said about it out loud, it fits into the frame whole and then gives way to
 * the next one. Several events making up a single chapter is the norm, not the
 * exception - the shortlist and the commonality filter answer one question
 * together.
 *
 * **A chapter appears only when an event for it has arrived.** There is no list
 * of eight slots waiting to be filled, because an empty chapter would claim that
 * something is happening when nothing is. A stage the dictionary does not know
 * gets a chapter of its own instead of falling off the screen.
 *
 * The sentence of a chapter describes **the question this chapter answers**, not
 * whatever happened to come out. What really came out is said by the rows below
 * it - including a rejection by the confidence gate, which is more interesting
 * than a step that simply succeeded.
 */

import type { PipelineEvent } from "./stages";

/** States after which a step is closed and can no longer be overwritten. */
const CLOSED = new Set(["gated", "failed"]);

/**
 * Collapses the event stream into screen rows.
 *
 * For one stage the engine sends `running` first and the result afterwards, so
 * drawing events one to one would give a list full of duplicates. A result
 * therefore **replaces** its own transitional state.
 *
 * The key is the stage plus level pair, because `verdict` arrives twice: the
 * preliminary one from level 1 and the final one from level 2 (section 4).
 * These are two different steps of the narrative.
 *
 * A row once **closed** (`gated`, `failed`) stays in its place forever and only
 * absorbs its own `running` state. Everything else lands underneath it. This is
 * about the run from section 4: lyrics -> the gate rejected it -> demucs ->
 * retry. If the result of the retry replaced the gate row, the screen would read
 * in the opposite order to the run and the reason for starting separation would
 * disappear - the only content for which that step is on screen at all
 * (section 12).
 */
export function collapseToRows(events: readonly PipelineEvent[]): PipelineEvent[] {
  const rows: PipelineEvent[] = [];

  events.forEach((event) => {
    for (let i = rows.length - 1; i >= 0; i -= 1) {
      const candidate = rows[i];
      if (candidate.stage !== event.stage || candidate.level !== event.level) continue;

      // The first row of the same stage and level decides - and only it. The
      // scan must not go deeper, because a closed gate may lie underneath and
      // the result of the retry has to land **below** it.
      if (CLOSED.has(String(candidate.status))) break;

      rows[i] = event;
      return;
    }
    rows.push(event);
  });

  return rows;
}

export interface ChapterDefinition {
  id: string;
  /** The chapter heading. */
  title: string;
  /** One sentence that can be said out loud while the chapter is in frame. */
  sentence: string | null;
}

/**
 * Eight chapters in order of appearance. The order of this array is the order of
 * the show for everything the dictionary knows.
 */
export const CHAPTERS: ChapterDefinition[] = [
  {
    id: "ingest",
    title: "Ingest",
    sentence: "We bring the material to a single format and cut it into analysis windows.",
  },
  {
    id: "fingerprint",
    title: "Acoustic fingerprint",
    sentence: "We look for the same recording, hash by hash.",
  },
  {
    id: "harmonic",
    title: "Harmony",
    sentence: "We look for the same work in a different performance.",
  },
  {
    id: "commonality",
    title: "Shortlist and commonality",
    sentence: "We check whether the similarity we found means anything at all.",
  },
  {
    id: "verdict-preliminary",
    title: "Preliminary verdict",
    sentence: "The first answer, still before the deepening.",
  },
  {
    id: "lyrics",
    title: "Lyrics",
    sentence: "We compare the sung layer, provided the system trusts its own transcript.",
  },
  {
    id: "melodic",
    title: "Melody",
    sentence: "We compare the melodic line interval by interval.",
  },
  {
    id: "verdict-final",
    title: "Final verdict",
    sentence: "Here the system lifts its own answer on the strength of new evidence.",
  },
];

const STAGE_TO_CHAPTER: Record<string, string> = {
  ingest: "ingest",
  fingerprint: "fingerprint",
  harmonic: "harmonic",
  shortlist: "commonality",
  commonality: "commonality",
  transcript: "lyrics",
  separation: "lyrics",
  melodic: "melodic",
};

/** Prefix of the ad hoc chapter for a stage outside the dictionary. */
export const UNKNOWN_STAGE_PREFIX = "stage:";

/**
 * Which chapter an event belongs to.
 *
 * `verdict` is the only stage resolved by level, because it arrives twice and
 * these are **two different moments of the narrative**: the preliminary one ends
 * level 1, the final one is the punchline of the whole run (section 12).
 */
export function chapterId(stage: string, level: number): string {
  if (stage === "verdict") return level >= 2 ? "verdict-final" : "verdict-preliminary";
  return STAGE_TO_CHAPTER[stage] ?? `${UNKNOWN_STAGE_PREFIX}${stage}`;
}

/** The chapter definition for an id. An unknown stage gets one of its own. */
export function chapterDefinition(id: string): ChapterDefinition {
  const known = CHAPTERS.find((chapter) => chapter.id === id);
  if (known) return known;
  const stage = id.startsWith(UNKNOWN_STAGE_PREFIX)
    ? id.slice(UNKNOWN_STAGE_PREFIX.length)
    : id;
  return {
    id,
    title: stage.toUpperCase(),
    sentence: "A stage outside the run plan. The screen shows it exactly as it arrived.",
  };
}

export interface Chapter extends ChapterDefinition {
  /** The rows belonging to this chapter, in order of arrival. */
  rows: PipelineEvent[];
  /** The execution level the first row of the chapter comes from. */
  level: number;
}

/**
 * Rows grouped into chapters.
 *
 * Grouping is **by first occurrence**, not by adjacency: if the engine squeezed
 * something from another stage between two lyrics events, the screen still has
 * eight chapters, not nine. The order of rows inside a chapter stays exactly as
 * it arrived from the stream.
 */
export function groupIntoChapters(rows: readonly PipelineEvent[]): Chapter[] {
  const byId = new Map<string, Chapter>();
  const order: string[] = [];

  for (const row of rows) {
    const id = chapterId(row.stage, row.level);
    let chapter = byId.get(id);
    if (!chapter) {
      chapter = { ...chapterDefinition(id), rows: [], level: row.level };
      byId.set(id, chapter);
      order.push(id);
    }
    chapter.rows.push(row);
  }

  return order.map((id) => byId.get(id) as Chapter);
}

/**
 * Whether the run has reached its end, that is, whether the queue should be
 * pushed through instead of waiting.
 *
 * The final verdict is the punchline and nothing will arrive after it
 * (section 12). A broken stream ends the run just as effectively, only worse.
 */
export function runFinished(
  rows: readonly PipelineEvent[],
  interrupted: boolean,
): boolean {
  if (interrupted) return true;
  return rows.some((row) => row.stage === "verdict" && row.status === "final");
}
