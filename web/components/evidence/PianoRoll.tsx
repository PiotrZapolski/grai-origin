"use client";

/**
 * Melody as a piano roll (section 13.2, the fourth panel).
 *
 * Detector C compares **sequences of intervals**, not absolute pitches, because
 * a compositional borrowing survives transposition. That is why the piano roll
 * draws the same sequence twice: once in the time axis of the query, once in the
 * time axis of the candidate. Matching shapes one above the other are the entire
 * content of this panel.
 *
 * The pitches are counted from zero, because intervals carry no reference point.
 * Writing any specific note here would be a number with nothing behind it.
 */

import type { DetectorStatus } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import { formatTimecodeTenths } from "../../lib/format";

export interface Ngram {
  queryStart: number;
  candidateStart: number;
  n: number;
  intervals: number[];
}

export interface PianoRollProps {
  /** `undefined` means: the key is not in `evidence`, the detector has not started. */
  status: DetectorStatus | undefined;
  reason?: string | null;
  /** `matched_ngrams` from the envelope of detector C. */
  ngrams: Array<Record<string, unknown> | null | undefined>;
  longestCommonRun?: number | null;
  msDistance?: number | null;
  className?: string;
}

const STATE_SENTENCES: Record<DetectorStatus, string> = {
  ok: "",
  not_applicable: "The melody detector has nothing to compare here.",
  gated: "The melody detector was held back by its own confidence check.",
  failed: "The melody detector returned no result.",
};

/** The time step of one note in the picture. A piano roll shows shape, not rhythm. */
const STEP_S = 0.5;
const NOTE_HEIGHT = 10;
const NOTE_WIDTH = 26;

/** A sequence of pitches from a sequence of intervals. The first note is the zero point. */
export function notesFromIntervals(intervals: number[], start = 0): number[] {
  const notes = [start];
  for (const interval of intervals) {
    notes.push(notes[notes.length - 1] + interval);
  }
  return notes;
}

/** Reads one n-gram from a loose dictionary. `null` means: it cannot be trusted. */
export function readNgram(raw: unknown): Ngram | null {
  if (!raw || typeof raw !== "object") return null;
  const record = raw as Record<string, unknown>;
  const { query_start: qs, candidate_start: cs, n, intervals } = record;
  if (typeof qs !== "number" || typeof cs !== "number") return null;
  if (!Array.isArray(intervals) || intervals.some((step) => typeof step !== "number")) return null;
  return {
    queryStart: qs,
    candidateStart: cs,
    n: typeof n === "number" ? n : intervals.length + 1,
    intervals: intervals as number[],
  };
}

interface RowProps {
  ngram: Ngram;
  source: "query" | "candidate";
  pitches: number[];
  lowest: number;
  highest: number;
}

function Row({ ngram, source, pitches, lowest, highest }: RowProps) {
  const span = Math.max(1, highest - lowest);
  const imageHeight = (span + 1) * NOTE_HEIGHT;
  const start = source === "query" ? ngram.queryStart : ngram.candidateStart;

  return (
    <figure className="flex flex-col gap-1">
      <figcaption className={`flex justify-between text-muted ${MICRO_LABEL_CLASS}`}>
        <span>{source === "query" ? "QUERY" : "CANDIDATE"}</span>
        <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>from {formatTimecodeTenths(start)}</span>
      </figcaption>
      <svg
        role="img"
        aria-label={`A sequence of ${pitches.length} notes, source ${source}`}
        width={pitches.length * NOTE_WIDTH}
        height={imageHeight}
        viewBox={`0 0 ${pitches.length * NOTE_WIDTH} ${imageHeight}`}
        className="max-w-full"
      >
        {pitches.map((pitch, index) => (
          <rect
            key={`${source}-${index}`}
            data-testid="note"
            data-source={source}
            data-pitch={String(pitch)}
            data-time={String(start + index * STEP_S)}
            x={index * NOTE_WIDTH}
            y={(highest - pitch) * NOTE_HEIGHT}
            width={NOTE_WIDTH - 4}
            height={NOTE_HEIGHT - 2}
            rx={2}
            /*
             * Both sequences are white. Lime used to distinguish the query from
             * the candidate here, that is, it served as a colour code for a role -
             * which is decoration, not a signal (Global Constraint 11). The
             * distinction is carried by the caption above each row, and the whole
             * point of the panel is that **both shapes are the same**; two colours
             * only obscured that similarity.
             */
            fill={theme.text}
            opacity={source === "query" ? 0.95 : 0.6}
          />
        ))}
      </svg>
    </figure>
  );
}

export function PianoRoll({
  status,
  reason = null,
  ngrams,
  longestCommonRun = null,
  msDistance = null,
  className = "",
}: PianoRollProps) {
  const header = (
    <header className="flex flex-wrap items-baseline justify-between gap-3">
      <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>MELODY</h3>
      {longestCommonRun !== null ? (
        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
          LONGEST COMMON RUN{" "}
          <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{longestCommonRun}</span>
        </p>
      ) : null}
    </header>
  );

  if (status === undefined) {
    return (
      <section className={`origin-card flex flex-col gap-4 p-6 ${className}`}>
        {header}
        <p className="text-sm text-muted">
          The melody detector has not computed this candidate yet. A missing result is not zero.
        </p>
      </section>
    );
  }

  if (status !== "ok") {
    return (
      <section className={`origin-card flex flex-col gap-4 p-6 ${className}`}>
        {header}
        <p className="text-sm text-muted">{reason ?? STATE_SENTENCES[status]}</p>
      </section>
    );
  }

  const readable = ngrams.map(readNgram).filter((ngram): ngram is Ngram => ngram !== null);

  return (
    <section className={`origin-card flex flex-col gap-4 p-6 ${className}`}>
      {header}

      {readable.length === 0 ? (
        <p className="text-sm text-muted">No melodic run overlapped enough to be shown.</p>
      ) : null}

      <div data-testid="pianoroll" className="flex flex-col gap-6 overflow-x-auto">
        {readable.map((ngram, index) => {
          const pitches = notesFromIntervals(ngram.intervals);
          const lowest = Math.min(...pitches);
          const highest = Math.max(...pitches);
          return (
            <div key={`ngram-${index}`} className="flex flex-col gap-3 border-t border-muted/20 pt-4 first:border-t-0 first:pt-0">
              <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
                COMMON INTERVALS{" "}
                <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
                  {ngram.intervals.join(" ")}
                </span>
              </p>
              <Row
                ngram={ngram}
                source="query"
                pitches={pitches}
                lowest={lowest}
                highest={highest}
              />
              <Row
                ngram={ngram}
                source="candidate"
                pitches={pitches}
                lowest={lowest}
                highest={highest}
              />
            </div>
          );
        })}
      </div>

      {msDistance !== null ? (
        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
          MELODIC DISTANCE{" "}
          <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{msDistance.toFixed(2)}</span>
        </p>
      ) : null}
    </section>
  );
}

export default PianoRoll;
