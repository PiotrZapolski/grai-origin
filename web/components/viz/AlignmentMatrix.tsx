"use client";

/**
 * The harmonic similarity matrix with the alignment path (section 7.2).
 *
 * The specification calls this matrix **the most visually convincing piece of
 * evidence in the whole system**, and that is also why the panel has a hard
 * boundary here: it draws only what arrived.
 *
 * Three states, each showing something different and each written out plainly:
 *
 * - **the full matrix** (`matrix`): the heatmap fills in column by column along
 *   the query axis, and the alignment path is drawn after it;
 * - **the path alone** (`alignment_path` without a matrix): the board stays
 *   empty, the panel says there is nothing to fill the background with, and
 *   shows the path on a grid of frames together with the reference diagonal;
 * - **nothing**: a sentence instead of a picture.
 *
 * The greyness of the heatmap is not aesthetics but a rule of the visual system:
 * lime means a signal, and several hundred background cells are not a signal.
 * The lime goes to the path and to the coverage brackets on the axes, that is,
 * to exactly what the finding is.
 *
 * Performance: the heatmap goes through `ImageData` at the resolution of the
 * matrix and one `drawImage` per frame, so a 400 x 400 matrix costs the same as
 * an 8 x 8 one. An SVG with 160,000 rectangles would block the thread on every
 * frame.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { DetectorStatus } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import { useProgress, useReducedMotion, ease } from "./motion";
import {
  type PathPoint,
  readPath,
  pathSlope,
  pathSegments,
  pathExtent,
} from "./geometry";

export interface AlignmentMatrixProps {
  /** `undefined` means: the key is not in `evidence`, the detector has not started. */
  status: DetectorStatus | undefined;
  reason?: string | null;
  /** `alignment_path` from the envelope of detector B: pairs of [query frame, candidate frame]. */
  path: unknown;
  /**
   * The full similarity matrix, indexed `matrix[queryFrame][candidateFrame]`,
   * with values in 0..1. The contract does **not** carry it today - the field is
   * prepared for `HarmonicResult.similarity_matrix` and until it exists, the
   * panel says so.
   */
  matrix?: readonly (readonly number[])[] | null;
  /** How many seconds one frame lasts, if known. Without it the axes are in frames. */
  frameSeconds?: number | null;
  qmax?: number | null;
  transposition?: number | null;
  tempoRatio?: number | null;
  coverage?: number | null;
  /** `chord_sequence` from the envelope of detector B. Chord names exactly as they arrived. */
  chords?: readonly string[] | null;
  candidateName?: string | null;
  className?: string;
}

const STATE_SENTENCES: Record<DetectorStatus, string> = {
  ok: "",
  not_applicable: "The harmonic detector has nothing to compare here.",
  gated: "The harmonic detector was held back by its own confidence check.",
  failed: "The harmonic detector returned no result.",
};

/** The full animation run of the panel. Filling and path drawing overlap. */
const DURATION_MS = 1900;
/** The share of the run after which the heatmap is complete. */
const FILL_END = 0.66;
/** The share of the run at which the path starts. The overlap with the fill is intended. */
const PATH_START = 0.48;

function fillShare(progress: number): number {
  return ease(Math.min(1, progress / FILL_END));
}

function pathShare(progress: number): number {
  if (progress <= PATH_START) return 0;
  return ease(Math.min(1, (progress - PATH_START) / (1 - PATH_START)));
}

/** The colour of a cell: white with opacity rising with the similarity. */
function cellAlpha(value: number): number {
  const v = Math.min(1, Math.max(0, value));
  return Math.round((0.04 + v * 0.72) * 255);
}

/** The heatmap at the resolution of the matrix. `null` when there is nothing to draw. */
function matrixBuffer(
  matrix: readonly (readonly number[])[] | null | undefined,
): HTMLCanvasElement | null {
  if (!matrix || matrix.length === 0) return null;
  const columns = matrix.length;
  const rows = matrix.reduce((max, column) => Math.max(max, column.length), 0);
  if (rows === 0) return null;
  if (typeof document === "undefined") return null;

  const canvas = document.createElement("canvas");
  canvas.width = columns;
  canvas.height = rows;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const image = ctx.createImageData(columns, rows);
  for (let q = 0; q < columns; q += 1) {
    for (let c = 0; c < rows; c += 1) {
      // The candidate axis grows upwards, so the image row is mirrored.
      const row = rows - 1 - c;
      const index = (row * columns + q) * 4;
      const value = matrix[q]?.[c];
      const alpha = typeof value === "number" && Number.isFinite(value) ? cellAlpha(value) : 0;
      image.data[index] = 255;
      image.data[index + 1] = 255;
      image.data[index + 2] = 255;
      image.data[index + 3] = alpha;
    }
  }
  ctx.putImageData(image, 0, 0);
  return canvas;
}

interface BoardSize {
  columns: number;
  rows: number;
}

/** The pixels of a path point in a frame of the given size. */
function toPixels(
  point: PathPoint,
  board: BoardSize,
  width: number,
  height: number,
): [number, number] {
  const x = ((point.q + 0.5) / Math.max(1, board.columns)) * width;
  const y = height - ((point.c + 0.5) / Math.max(1, board.rows)) * height;
  return [x, y];
}

/** The path clipped to a given share of its length. */
function pathUpToShare(
  pixels: readonly [number, number][],
  share: number,
): [number, number][] {
  if (pixels.length === 0 || share <= 0) return [];
  if (share >= 1) return [...pixels];

  const lengths: number[] = [];
  let total = 0;
  for (let i = 1; i < pixels.length; i += 1) {
    const dx = pixels[i][0] - pixels[i - 1][0];
    const dy = pixels[i][1] - pixels[i - 1][1];
    const d = Math.hypot(dx, dy);
    lengths.push(d);
    total += d;
  }
  if (total === 0) return [pixels[0]];

  const target = total * share;
  const result: [number, number][] = [pixels[0]];
  let travelled = 0;
  for (let i = 0; i < lengths.length; i += 1) {
    if (travelled + lengths[i] >= target) {
      const rest = lengths[i] === 0 ? 0 : (target - travelled) / lengths[i];
      const [x0, y0] = pixels[i];
      const [x1, y1] = pixels[i + 1];
      result.push([x0 + (x1 - x0) * rest, y0 + (y1 - y0) * rest]);
      return result;
    }
    travelled += lengths[i];
    result.push(pixels[i + 1]);
  }
  return result;
}

function formatAxis(index: number, frameSeconds: number | null | undefined): string {
  if (typeof frameSeconds === "number" && frameSeconds > 0) {
    return `${(index * frameSeconds).toFixed(1)} s`;
  }
  return `${index}`;
}

interface Probe {
  q: number;
  c: number;
  value: number | null;
}

/* -------------------------------------------------------------------------- */
/* Twelve rotations                                                           */
/* -------------------------------------------------------------------------- */

/** Which of the twelve rotations a transposition reduces to. Negative ones too. */
function rotation(transposition: number | null): number | null {
  if (typeof transposition !== "number" || !Number.isFinite(transposition)) return null;
  return ((Math.round(transposition) % 12) + 12) % 12;
}

/** The share of the run over which the rotations sweep past before the choice settles. */
const ROTATION_END = 0.5;

/**
 * The twelve chromagram rotations, one of which wins.
 *
 * The system **does not detect the key**: it compares all twelve rotations and
 * takes the best one, and the number of the winner is a ready answer,
 * "transposed by N semitones". The marker therefore sweeps through the full
 * twelve and stops on the one that arrived in the contract.
 *
 * **Only the winner has a score.** The stream carries a single `qmax_score`, so
 * the remaining eleven rotations cannot be described by a number and none stands
 * here - the empty field is content, not an omission.
 */
function Rotations({
  transposition,
  qmax,
  progress,
}: {
  transposition: number | null;
  qmax: number | null;
  progress: number;
}) {
  const winner = rotation(transposition);
  if (winner === null) return null;

  const sweep = Math.min(1, progress / ROTATION_END);
  // One and a half turns through the full twelve, then a stop on the winner.
  const current = sweep >= 1 ? winner : Math.floor(ease(sweep) * 18 + winner) % 12;
  const settled = sweep >= 1;

  return (
    <figure data-testid="chromagram-rotations" data-rotation={winner} className="flex flex-col gap-2">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-3">
        <span className={`text-muted ${MICRO_LABEL_CLASS}`}>TWELVE ROTATIONS</span>
        <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
          WINNER{" "}
          <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {winner}{" "}
            {transposition !== null
              ? `(${transposition >= 0 ? "+" : ""}${transposition} semitones)`
              : ""}
          </span>
        </span>
      </figcaption>

      <div className="flex gap-1">
        {Array.from({ length: 12 }, (_, i) => {
          const active = i === current;
          const won = settled && i === winner;
          return (
            <span
              key={i}
              data-rotation-slot={i}
              data-state={won ? "won" : active ? "checking" : "checked"}
              className={`flex h-9 flex-1 items-center justify-center rounded-inner border text-[11px] ${TECHNICAL_VALUE_CLASS}`}
              style={{
                borderColor: won
                  ? theme.accent
                  : active
                    ? `${theme.text}66`
                    : `${theme.muted}2A`,
                backgroundColor: won
                  ? `${theme.accent}1F`
                  : active
                    ? `${theme.text}12`
                    : "transparent",
                color: won ? theme.accent : active ? theme.text : `${theme.muted}`,
              }}
            >
              {i}
            </span>
          );
        })}
      </div>

      <p className="text-xs text-muted">
        Key detection is unreliable, so the system does not do it: it compares the full twelve
        rotations and takes the best one. The numeric score{" "}
        {qmax === null ? "arrives" : `of ${qmax.toFixed(2)} arrives`} for the winning rotation
        only, so the remaining eleven fields stay without a value.
      </p>
    </figure>
  );
}

/* -------------------------------------------------------------------------- */
/* Chord sequence                                                             */
/* -------------------------------------------------------------------------- */

/** The chords of the candidate exactly as they arrived in the envelope. They enter in turn. */
function Chords({ chords, progress }: { chords: readonly string[]; progress: number }) {
  const visible = ease(Math.min(1, progress / 0.8)) * chords.length;
  return (
    <figure data-testid="chord-sequence" className="flex flex-col gap-2">
      <figcaption className={`text-muted ${MICRO_LABEL_CLASS}`}>CHORD SEQUENCE</figcaption>
      <div className="flex flex-wrap gap-1.5">
        {chords.map((chord, i) => {
          const entered = Math.min(1, Math.max(0, visible - i));
          return (
            <span
              key={`${chord}-${i}`}
              data-chord={chord}
              className={`rounded-inner border border-muted/20 px-2.5 py-1 text-sm text-text ${TECHNICAL_VALUE_CLASS}`}
              style={{
                opacity: 0.15 + 0.85 * entered,
                transform: `translateY(${(1 - entered) * 4}px)`,
              }}
            >
              {chord}
            </span>
          );
        })}
      </div>
    </figure>
  );
}

export function AlignmentMatrix({
  status,
  reason = null,
  path,
  matrix = null,
  frameSeconds = null,
  qmax = null,
  transposition = null,
  tempoRatio = null,
  coverage = null,
  chords = null,
  candidateName = null,
  className = "",
}: AlignmentMatrixProps) {
  const points = useMemo(() => readPath(path), [path]);
  const extent = useMemo(() => pathExtent(points), [points]);

  const matrixColumns = matrix?.length ?? 0;
  const matrixRows = matrix?.reduce((max, column) => Math.max(max, column.length), 0) ?? 0;

  const board: BoardSize = {
    columns: Math.max(extent.queryFrames, matrixColumns, 1),
    rows: Math.max(extent.candidateFrames, matrixRows, 1),
  };

  const hasMatrix = matrixColumns > 0 && matrixRows > 0;
  const hasPath = points.length > 0;

  const container = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [probe, setProbe] = useState<Probe | null>(null);
  const reducedMotion = useReducedMotion();

  const buffer = useMemo(() => matrixBuffer(matrix), [matrix]);

  const marker = useMemo(
    () => `${points.length}:${matrixColumns}x${matrixRows}:${qmax ?? "none"}`,
    [points.length, matrixColumns, matrixRows, qmax],
  );
  const progress = useProgress({
    duration: DURATION_MS,
    key: marker,
    enabled: status === "ok" && (hasMatrix || hasPath),
  });

  /* The size of the frame. Without ResizeObserver (jsdom, SSR) a single measurement remains. */
  useEffect(() => {
    const node = container.current;
    if (!node) return;

    const measure = () => {
      setSize({ width: node.clientWidth, height: node.clientHeight });
    };
    measure();

    if (typeof ResizeObserver !== "function") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [status]);

  /* One draw per progress frame. */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const { width, height } = size;
    if (width <= 0 || height <= 0) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const density = typeof window !== "undefined" ? Math.min(2, window.devicePixelRatio || 1) : 1;
    canvas.width = Math.round(width * density);
    canvas.height = Math.round(height * density);
    ctx.setTransform(density, 0, 0, density, 0, 0);
    ctx.clearRect(0, 0, width, height);

    /* The reference grid: ten cells on each axis, a hairline. */
    ctx.strokeStyle = `${theme.muted}22`;
    ctx.lineWidth = 1;
    for (let i = 1; i < 10; i += 1) {
      const x = Math.round((i / 10) * width) + 0.5;
      const y = Math.round((i / 10) * height) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    /* The heatmap filling in along the query axis. */
    if (buffer) {
      const share = fillShare(progress);
      const visibleColumns = Math.max(1, Math.ceil(buffer.width * share));
      const targetWidth = (visibleColumns / buffer.width) * width;
      ctx.imageSmoothingEnabled = buffer.width >= 64;
      ctx.drawImage(
        buffer,
        0,
        0,
        visibleColumns,
        buffer.height,
        0,
        0,
        targetWidth,
        height,
      );
      /* The leading edge of the fill: a vertical line where the drawing stands. */
      if (share < 1) {
        ctx.strokeStyle = `${theme.text}55`;
        ctx.beginPath();
        ctx.moveTo(targetWidth, 0);
        ctx.lineTo(targetWidth, height);
        ctx.stroke();
      }
    }

    /* The reference diagonal: what it would look like if both recordings ran at the same tempo. */
    ctx.save();
    ctx.strokeStyle = `${theme.muted}66`;
    ctx.setLineDash([3, 5]);
    ctx.beginPath();
    ctx.moveTo(0, height);
    ctx.lineTo(width, 0);
    ctx.stroke();
    ctx.restore();

    /* The alignment path. The only element in lime. */
    if (hasPath) {
      const pixels = points.map((point) => toPixels(point, board, width, height));
      const visible = pathUpToShare(pixels, pathShare(progress));
      if (visible.length > 1) {
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        ctx.strokeStyle = `${theme.accent}26`;
        ctx.lineWidth = 7;
        ctx.beginPath();
        ctx.moveTo(visible[0][0], visible[0][1]);
        for (const [x, y] of visible.slice(1)) ctx.lineTo(x, y);
        ctx.stroke();

        ctx.strokeStyle = theme.accent;
        ctx.lineWidth = 1.75;
        ctx.beginPath();
        ctx.moveTo(visible[0][0], visible[0][1]);
        for (const [x, y] of visible.slice(1)) ctx.lineTo(x, y);
        ctx.stroke();
      }
      /* The frames the path has already passed. Every point is a pair from the contract. */
      const stepShare = 1 / Math.max(1, pixels.length - 1);
      pixels.forEach(([x, y], i) => {
        const lit = pathShare(progress) >= i * stepShare;
        if (!lit) return;
        ctx.fillStyle = `${theme.accent}CC`;
        ctx.fillRect(x - 2, y - 2, 4, 4);
      });

      if (visible.length > 0) {
        const [x, y] = visible[visible.length - 1];
        const inProgress = pathShare(progress) < 1;
        /* The halo of the head: you can see where the drawing stands. */
        ctx.fillStyle = inProgress ? `${theme.accent}33` : `${theme.accent}1A`;
        ctx.beginPath();
        ctx.arc(x, y, inProgress ? 9 : 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = theme.accent;
        ctx.beginPath();
        ctx.arc(x, y, 2.8, 0, Math.PI * 2);
        ctx.fill();
      }

      /* The coverage brackets on both axes: how far the path reaches. */
      const qFrom = Math.min(...points.map((p) => p.q));
      const qTo = Math.max(...points.map((p) => p.q));
      const cFrom = Math.min(...points.map((p) => p.c));
      const cTo = Math.max(...points.map((p) => p.c));
      ctx.fillStyle = `${theme.accent}CC`;
      const x0 = (qFrom / board.columns) * width;
      const x1 = ((qTo + 1) / board.columns) * width;
      ctx.fillRect(x0, height - 2, Math.max(2, x1 - x0), 2);
      const y1 = height - ((cTo + 1) / board.rows) * height;
      const y0 = height - (cFrom / board.rows) * height;
      ctx.fillRect(0, y1, 2, Math.max(2, y0 - y1));
    }

    /* The probe crosshair under the cursor. */
    if (probe) {
      const [x, y] = toPixels({ q: probe.q, c: probe.c }, board, width, height);
      ctx.strokeStyle = `${theme.text}44`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
  }, [buffer, hasPath, board, probe, progress, size, points]);

  const onCursor = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const node = container.current;
      if (!node) return;
      const rect = node.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      const ux = (event.clientX - rect.left) / rect.width;
      const uy = (event.clientY - rect.top) / rect.height;
      const q = Math.min(board.columns - 1, Math.max(0, Math.floor(ux * board.columns)));
      const c = Math.min(board.rows - 1, Math.max(0, Math.floor((1 - uy) * board.rows)));
      const value = matrix?.[q]?.[c];
      setProbe({
        q,
        c,
        value: typeof value === "number" && Number.isFinite(value) ? value : null,
      });
    },
    [matrix, board.columns, board.rows],
  );

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
      <section
        data-testid="alignment-matrix"
        data-state="not-started"
        className={`origin-card flex flex-col gap-4 p-6 ${className}`}
      >
        {header}
        <p className="text-sm text-muted">
          The harmonic detector has not computed this candidate yet. A missing result is not zero.
        </p>
      </section>
    );
  }

  if (status !== "ok") {
    return (
      <section
        data-testid="alignment-matrix"
        data-state={status}
        className={`origin-card flex flex-col gap-4 p-6 ${className}`}
      >
        {header}
        <p className="text-sm text-muted">{reason ?? STATE_SENTENCES[status]}</p>
      </section>
    );
  }

  if (!hasMatrix && !hasPath) {
    return (
      <section
        data-testid="alignment-matrix"
        data-state="no-data"
        className={`origin-card flex flex-col gap-4 p-6 ${className}`}
      >
        {header}
        <p className="text-sm text-muted">
          For this entry the harmonic detector returned neither a matrix nor an alignment path.
          There is nothing to draw, so the board stays empty.
        </p>
      </section>
    );
  }

  const slope = pathSlope(points);
  const segments = pathSegments(points);
  const slopes = segments
    .map((segment) => segment.slope)
    .filter((value): value is number => value !== null);

  return (
    <section
      data-testid="alignment-matrix"
      data-state="ok"
      data-matrix={hasMatrix ? "present" : "none"}
      data-path-points={points.length}
      className={`origin-card flex flex-col gap-4 p-6 ${className}`}
    >
      {header}

      {!hasMatrix ? (
        <p className="text-sm text-muted">
          The full similarity matrix did not arrive in the evidence, so the background of the board
          stays empty - there is nothing to fill it with. What is visible is the alignment path on
          a grid of frames and the reference diagonal, that is, the course both recordings would
          take at the same tempo.
        </p>
      ) : null}

      <Rotations transposition={transposition} qmax={qmax} progress={progress} />

      <div className="flex gap-3">
        {/* The candidate axis, read from bottom to top. */}
        <div className="flex w-6 shrink-0 flex-col justify-between py-1">
          <span className={`text-muted ${MICRO_LABEL_CLASS} ${TECHNICAL_VALUE_CLASS}`}>
            {formatAxis(board.rows, frameSeconds)}
          </span>
          <span
            className={`text-muted ${MICRO_LABEL_CLASS} [writing-mode:vertical-rl] rotate-180 self-center`}
          >
            CANDIDATE
          </span>
          <span className={`text-muted ${MICRO_LABEL_CLASS} ${TECHNICAL_VALUE_CLASS}`}>0</span>
        </div>

        <div className="min-w-0 flex-1">
          <div
            ref={container}
            data-testid="matrix-board"
            role="img"
            aria-label={
              hasMatrix
                ? `Harmonic similarity matrix of ${board.columns} by ${board.rows} frames with the alignment path`
                : `Alignment path on a grid of ${board.columns} by ${board.rows} frames, without a similarity matrix`
            }
            onMouseMove={onCursor}
            onMouseLeave={() => setProbe(null)}
            className="relative aspect-[16/10] w-full overflow-hidden rounded-inner border border-muted/16 bg-bg"
          >
            <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
          </div>

          <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2">
            <span className={`text-muted ${MICRO_LABEL_CLASS}`}>QUERY</span>
            <span className={`text-muted ${MICRO_LABEL_CLASS} ${TECHNICAL_VALUE_CLASS}`}>
              0 to {formatAxis(board.columns, frameSeconds)}
            </span>
          </div>
        </div>
      </div>

      <p
        data-testid="matrix-readout"
        className={`min-h-[1.25rem] text-xs text-muted ${TECHNICAL_VALUE_CLASS}`}
      >
        {probe === null
          ? "The cursor over the board shows the pair of frames underneath it."
          : `query ${formatAxis(probe.q, frameSeconds)} / candidate ${formatAxis(
              probe.c,
              frameSeconds,
            )}${probe.value === null ? " / similarity unknown" : ` / similarity ${probe.value.toFixed(2)}`}`}
      </p>

      {chords && chords.length > 0 ? <Chords chords={chords} progress={progress} /> : null}

      {slopes.length > 0 ? (
        <div data-testid="path-slope" className="flex flex-col gap-1">
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
            PATH SLOPE{" "}
            <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
              {slope === null ? "none" : slope.toFixed(2)}
            </span>
          </p>
          <p className="text-xs text-muted">
            How many candidate frames fall on one query frame. A value equal to one means the same
            tempo, a larger one means the candidate runs faster. The number is a derivative of the
            path from the contract, not a separate measurement.
          </p>
        </div>
      ) : null}

      <dl className={`grid grid-cols-2 gap-3 text-muted sm:grid-cols-4 ${MICRO_LABEL_CLASS}`}>
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
        <div>
          <dt>PATH POINTS</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{points.length}</dd>
        </div>
      </dl>

      {candidateName ? (
        <p className="text-xs text-muted">
          The vertical axis is the recording of entry {candidateName}, the horizontal one is the
          input material.
          {reducedMotion ? " Motion turned off at the browser's request." : ""}
        </p>
      ) : null}
    </section>
  );
}

export default AlignmentMatrix;
