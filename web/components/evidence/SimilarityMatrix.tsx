"use client";

/**
 * The harmonic similarity matrix (section 13.2, the second panel).
 *
 * A heatmap with the alignment path drawn on it. Two things matter here more
 * than appearance:
 *
 * 1. **A missing key in `evidence` means "not computed yet", not "zero".**
 *    Level 1 sends two keys, not four. For a detector that has not run, the
 *    panel says it is waiting instead of showing an empty matrix - an empty
 *    matrix would read as "checked, there is no similarity".
 * 2. **We do not invent the matrix.** The contract carries the alignment path
 *    and a chord sequence, not a ready matrix. If we have both chord sequences
 *    we compute the similarity for real; if not, we draw the path alone and say
 *    so outright.
 */

import type { DetectorStatus } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";

export interface SimilarityMatrixProps {
  /** `undefined` means: the key is not in `evidence`, the detector has not started. */
  status: DetectorStatus | undefined;
  reason?: string | null;
  /** `alignment_path` from the envelope of detector B: pairs of indices (query, candidate). */
  path: Array<[number, number]>;
  queryChords?: string[];
  candidateChords?: string[];
  qmax?: number | null;
  transposition?: number | null;
  tempoRatio?: number | null;
  coverage?: number | null;
  className?: string;
}

const STATE_SENTENCES: Record<DetectorStatus, string> = {
  ok: "",
  not_applicable: "The harmonic detector has nothing to compare here.",
  gated: "The harmonic detector was held back by its own confidence check.",
  failed: "The harmonic detector returned no result.",
};

/** The root of a chord: the letter with an optional sharp or flat. */
export function chordRoot(chord: string): string {
  const match = /^[A-G](#|b)?/.exec(chord.trim());
  return match ? match[0] : chord.trim();
}

/**
 * The similarity of every pair of chords: 1 for the same chord, 0.5 for the same
 * root with a different quality (C against Cm), 0 for a foreign chord. No
 * learning, no magic - a rule that can be read out in court.
 */
export function chordSimilarityMatrix(
  query: string[],
  candidate: string[],
): number[][] {
  return query.map((queryChord) =>
    candidate.map((candidateChord) => {
      if (queryChord === candidateChord) return 1;
      return chordRoot(queryChord) === chordRoot(candidateChord) ? 0.5 : 0;
    }),
  );
}

function axisSize(path: Array<[number, number]>, axis: 0 | 1, floor: number): number {
  const fromPath = path.reduce((max, pair) => Math.max(max, pair[axis] + 1), 0);
  return Math.max(fromPath, floor);
}

/**
 * The background of a single heatmap cell.
 *
 * **The heatmap is white, not lime.** Previously every cell with a non-zero
 * similarity got `rgba(200, 255, 61, ...)`, that is, the accent flooded the whole
 * panel - several hundred cells at once. That is exactly what Global Constraint
 * 11 guards against: lime stops being a signal when it is the background. Worse,
 * the **alignment path** drowned in it - the only place in the panel that really
 * is a finding, and the one that keeps the accent (the `outline-accent` border).
 *
 * The shade is computed by `color-mix` from the tokens, so there is no `rgba`
 * written into the stylesheet.
 */
function cellBackground(value: number | null): string {
  if (value === null) {
    return `color-mix(in srgb, ${theme.muted} 10%, transparent)`;
  }
  // 6% for no similarity, 56% for an identical chord.
  const share = Math.round((0.06 + value * 0.5) * 100);
  return `color-mix(in srgb, ${theme.text} ${share}%, transparent)`;
}

export function SimilarityMatrix({
  status,
  reason = null,
  path,
  queryChords,
  candidateChords,
  qmax = null,
  transposition = null,
  tempoRatio = null,
  coverage = null,
  className = "",
}: SimilarityMatrixProps) {
  const header = (
    <header className="flex flex-wrap items-baseline justify-between gap-3">
      <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>HARMONIC MATRIX</h3>
      {qmax !== null ? (
        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
          QMAX <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{qmax.toFixed(2)}</span>
        </p>
      ) : null}
    </header>
  );

  if (status === undefined) {
    return (
      <section className={`origin-card flex flex-col gap-4 p-6 ${className}`}>
        {header}
        <p className="text-sm text-muted">
          The harmonic detector has not computed this candidate yet. A missing result is not zero.
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

  const hasMatrix = Boolean(queryChords?.length && candidateChords?.length);
  const matrix = hasMatrix
    ? chordSimilarityMatrix(queryChords as string[], candidateChords as string[])
    : null;

  const rows = axisSize(path, 0, matrix?.length ?? 0);
  const columns = axisSize(path, 1, matrix?.[0]?.length ?? 0);
  const onPath = new Set(path.map(([i, j]) => `${i}-${j}`));

  return (
    <section className={`origin-card flex flex-col gap-4 p-6 ${className}`}>
      {header}

      {!hasMatrix ? (
        <p className="text-sm text-muted">
          The full matrix did not arrive in the evidence, so the panel shows the alignment path
          alone.
        </p>
      ) : null}

      <div
        data-testid="matrix-grid"
        role="img"
        aria-label="Harmonic similarity matrix with the alignment path"
        className="grid gap-px overflow-x-auto"
        style={{ gridTemplateColumns: `repeat(${Math.max(columns, 1)}, minmax(10px, 1fr))` }}
      >
        {Array.from({ length: rows }).flatMap((_, row) =>
          Array.from({ length: columns }).map((__, column) => {
            const value = matrix?.[row]?.[column] ?? null;
            const isOnPath = onPath.has(`${row}-${column}`);
            return (
              <div
                key={`${row}-${column}`}
                data-testid={`cell-${row}-${column}`}
                data-value={value === null ? "" : String(value)}
                data-path={isOnPath ? "true" : "false"}
                title={
                  queryChords && candidateChords
                    ? `${queryChords[row] ?? "?"} against ${candidateChords[column] ?? "?"}`
                    : undefined
                }
                className={`aspect-square ${isOnPath ? "outline outline-1 outline-accent" : ""}`}
                style={{ backgroundColor: cellBackground(value) }}
              />
            );
          }),
        )}
      </div>

      <dl className={`grid grid-cols-3 gap-3 text-muted ${MICRO_LABEL_CLASS}`}>
        <div>
          <dt>TRANSPOSITION</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {transposition === null ? "none" : `${transposition} semitones`}
          </dd>
        </div>
        <div>
          <dt>TEMPO</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {tempoRatio === null ? "none" : tempoRatio.toFixed(2)}
          </dd>
        </div>
        <div>
          <dt>COVERAGE</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {coverage === null ? "none" : `${Math.round(coverage * 100)}%`}
          </dd>
        </div>
      </dl>
    </section>
  );
}

export default SimilarityMatrix;
