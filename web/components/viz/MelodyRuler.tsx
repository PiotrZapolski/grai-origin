"use client";

/**
 * Symbolic melody: the common sequence of intervals, interval by interval.
 *
 * Section 4 of the narrative: interval sequences are invariant to transposition
 * and to arrangement, and the result is a number that a musicologist and a
 * lawyer both understand - "eleven consecutive intervals identical". This panel
 * shows exactly that number and exactly the intervals the detector returned in
 * `matched_ngrams`.
 *
 * Every n-gram has four things in the contract and all four are on screen: the
 * list of intervals, the length `n`, the second in the query and the second in
 * the candidate. The drawing is the partial sum of the intervals, that is, the
 * shape of the melody without a key - a recomputation of the list from the
 * contract, not a separate measurement.
 *
 * **There is no absolute pitch here and there never will be.** The detector does
 * not return notes, only the differences between them, so both lines start from
 * zero and that is written under the drawing. A shared shape at two different
 * moments in time is the entire content of this step.
 */

import { useMemo } from "react";

import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import { useProgress, ease } from "./motion";

/** An n-gram exactly as it arrives in `MelodicResult.matched_ngrams`. */
export interface MelodyNgram {
  intervals: number[];
  n: number | null;
  queryStart: number | null;
  candidateStart: number | null;
}

export interface MelodyRulerProps {
  /** The `status` of the detector C result. `undefined` means: it has not run yet. */
  status?: "ok" | "not_applicable" | "gated" | "failed";
  reason?: string | null;
  /** The raw `matched_ngrams` from the envelope. Read defensively. */
  ngrams?: unknown;
  longestCommonRun?: number | null;
  msDistance?: number | null;
  /** The threshold of the EXCERPT/work rule from section 9.1, if the screen knows it. */
  threshold?: number | null;
  className?: string;
}

const DURATION_MS = 2200;
const HEIGHT = 96;

const STATE_SENTENCES: Record<string, string> = {
  not_applicable: "The melody detector has nothing to compare here.",
  gated: "The melody detector was held back by its own confidence check.",
  failed: "The melody detector returned no result.",
};

/** N-grams from loose input. An entry without a list of intervals drops out instead of pretending. */
export function readNgrams(raw: unknown): MelodyNgram[] {
  if (!Array.isArray(raw)) return [];
  const result: MelodyNgram[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const intervals = record.intervals;
    if (!Array.isArray(intervals)) continue;
    const numbers = intervals.filter(
      (value): value is number => typeof value === "number" && Number.isFinite(value),
    );
    if (numbers.length !== intervals.length || numbers.length === 0) continue;
    const n = record.n;
    const qs = record.query_start;
    const cs = record.candidate_start;
    result.push({
      intervals: numbers,
      n: typeof n === "number" && Number.isFinite(n) ? n : null,
      queryStart: typeof qs === "number" && Number.isFinite(qs) ? qs : null,
      candidateStart: typeof cs === "number" && Number.isFinite(cs) ? cs : null,
    });
  }
  return result;
}

/** The partial sum of the intervals: the melodic shape computed from the list in the contract. */
export function intervalContour(intervals: readonly number[]): number[] {
  const contour = [0];
  for (const interval of intervals) contour.push(contour[contour.length - 1] + interval);
  return contour;
}

function sign(value: number): string {
  return value > 0 ? `+${value}` : `${value}`;
}

/* -------------------------------------------------------------------------- */
/* A single n-gram                                                            */
/* -------------------------------------------------------------------------- */

function Ngram({ ngram, progress, index }: { ngram: MelodyNgram; progress: number; index: number }) {
  const contour = useMemo(() => intervalContour(ngram.intervals), [ngram.intervals]);
  const min = Math.min(...contour);
  const max = Math.max(...contour);
  const span = max - min || 1;

  // Each n-gram starts a moment after the previous one, so they can be read separately.
  const start = Math.min(0.4, index * 0.18);
  const local = ease(Math.min(1, Math.max(0, (progress - start) / (1 - start))));
  // First half: the query line. Second: the candidate slides in and locks.
  const drawing = Math.min(1, local / 0.55);
  const closing = Math.min(1, Math.max(0, (local - 0.45) / 0.55));
  const locked = closing >= 1;

  const width = 1000;
  const step = width / Math.max(1, contour.length - 1);
  const points = contour.map((value, i) => {
    const x = i * step;
    const y = HEIGHT - 10 - ((value - min) / span) * (HEIGHT - 22);
    return [x, y] as const;
  });

  const upTo = (share: number) => {
    const count = Math.max(1, Math.ceil(share * (points.length - 1)) + 1);
    return points.slice(0, count);
  };

  const line = (list: readonly (readonly [number, number])[]) =>
    list.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

  const shift = (1 - closing) * 120;

  return (
    <figure data-testid="melody-ngram" data-intervals={ngram.intervals.length} className="flex flex-col gap-2">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-3">
        <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
          N-GRAM OF {ngram.n ?? ngram.intervals.length} INTERVALS
        </span>
        <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
          {ngram.queryStart !== null ? (
            <>
              QUERY{" "}
              <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
                {ngram.queryStart.toFixed(1)} s
              </span>
            </>
          ) : null}
          {ngram.candidateStart !== null ? (
            <>
              {" / CANDIDATE "}
              <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
                {ngram.candidateStart.toFixed(1)} s
              </span>
            </>
          ) : null}
        </span>
      </figcaption>

      <svg
        role="img"
        aria-label={`Melodic shape from the intervals ${ngram.intervals.map(sign).join(" ")}`}
        viewBox={`0 0 ${width} ${HEIGHT}`}
        preserveAspectRatio="none"
        className="h-24 w-full rounded-inner border border-muted/16 bg-bg"
      >
        {/* The query line: drawn from the left, interval by interval. */}
        <path
          d={line(upTo(drawing))}
          fill="none"
          stroke={theme.text}
          strokeOpacity={0.55}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* The candidate line: the same intervals, sliding towards the query and locking on. */}
        <g transform={`translate(${shift.toFixed(1)}, 0)`} opacity={closing > 0 ? 1 : 0}>
          <path
            d={line(points)}
            fill="none"
            stroke={locked ? theme.accent : theme.muted}
            strokeWidth={locked ? 2.5 : 2}
            strokeDasharray={locked ? undefined : "6 6"}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </g>
        {/* Nodes: one for every note of the shape. */}
        {locked
          ? points.map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r={3} fill={theme.accent} />
            ))
          : null}
      </svg>

      <div className="flex flex-wrap gap-1.5">
        {ngram.intervals.map((interval, i) => {
          const entered = locked || drawing * ngram.intervals.length > i;
          return (
            <span
              key={i}
              data-interval={interval}
              className={`rounded-inner border px-2 py-0.5 text-sm ${TECHNICAL_VALUE_CLASS}`}
              style={{
                borderColor: locked ? `${theme.accent}66` : `${theme.muted}2A`,
                color: locked ? theme.accent : theme.text,
                opacity: entered ? 1 : 0.2,
                transition: "opacity 160ms ease",
              }}
            >
              {sign(interval)}
            </span>
          );
        })}
      </div>
    </figure>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel                                                                      */
/* -------------------------------------------------------------------------- */

export function MelodyRuler({
  status = "ok",
  reason = null,
  ngrams,
  longestCommonRun = null,
  msDistance = null,
  threshold = null,
  className = "",
}: MelodyRulerProps) {
  const list = useMemo(() => readNgrams(ngrams), [ngrams]);

  const progress = useProgress({
    duration: DURATION_MS,
    key: `${list.length}:${longestCommonRun ?? "none"}`,
    enabled: status === "ok" && (list.length > 0 || longestCommonRun !== null),
  });

  const counter =
    longestCommonRun === null ? null : Math.round(longestCommonRun * ease(Math.min(1, progress / 0.6)));

  if (status !== "ok") {
    return (
      <section
        data-testid="melody-ruler"
        data-state={status}
        className={`origin-card flex flex-col gap-4 p-6 ${className}`}
      >
        <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>INTERVAL SEQUENCE</h3>
        <p className="text-sm text-muted">{reason ?? STATE_SENTENCES[status] ?? "No result."}</p>
      </section>
    );
  }

  return (
    <section
      data-testid="melody-ruler"
      data-state="ok"
      data-ngrams={list.length}
      className={`origin-card flex flex-col gap-5 p-6 ${className}`}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>INTERVAL SEQUENCE</h3>
        {msDistance !== null ? (
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
            MONGEAU-SANKOFF{" "}
            <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{msDistance.toFixed(2)}</span>
          </p>
        ) : null}
      </header>

      {longestCommonRun !== null ? (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span
            data-testid="run-counter"
            className={`text-4xl ${TECHNICAL_VALUE_CLASS} ${
              threshold !== null && longestCommonRun >= threshold ? "text-accent" : "text-text"
            }`}
          >
            {counter}
          </span>
          <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
            consecutive identical intervals
            {threshold !== null ? `, the rule threshold is ${threshold}` : ""}
          </span>
        </div>
      ) : null}

      {list.length > 0 ? (
        list.map((ngram, i) => (
          <Ngram key={i} ngram={ngram} progress={progress} index={i} />
        ))
      ) : (
        <p className="text-sm text-muted">
          The detector returned no common n-gram, so there is nothing to draw. The number of the
          longest run stands above on its own, if it arrived.
        </p>
      )}

      <p className="text-xs text-muted">
        The shape is the partial sum of the intervals, that is, the melodic line without a key: the
        detector returns the differences between notes, not the notes, so both lines start at the
        same height. The same shape at two different seconds of the two recordings is the entire
        content here.
      </p>
    </section>
  );
}

export default MelodyRuler;
