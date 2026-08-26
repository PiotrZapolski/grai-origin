"use client";

/**
 * Ingest of the material: length, analysis windows, file hash (section "Stage 1").
 *
 * The three numbers this step really produces and not one more: `duration`,
 * `windows` and `sha256` from the `ingest` event. Everything visible is derived
 * from them:
 *
 * - **the time axis** has the length of the material, with a tick every ten
 *   seconds;
 * - **the windows** are drawn one for one: as many rectangles as the stream
 *   reported windows, and the step between them is the quotient
 *   `(duration - 10) / (windows - 1)`, an ordinary derivative of two numbers
 *   from the contract, as explicit as the difference between two timecodes;
 * - **the hash** is 64 real hexadecimal digits, each in its own cell, and the
 *   brightness of a cell is the value of that digit.
 *
 * What is **not here and never will be**: a waveform (nobody sent any samples)
 * and a loudness meter (the measured loudness is not in the stream).
 * Normalization targets -23 LUFS under BS.1770-4 and that is written out in
 * words under the panel, because drawing a meter creeping up to that value would
 * be showing a measurement nobody performed.
 */

import { useMemo } from "react";

import { formatTimecodeTenths } from "../../lib/format";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import { windowStep } from "./geometry";
import { useAnimatedCanvas, useReducedMotion, ease } from "./motion";

/** An event as loose as it has to be to accept both `StreamEvent` and `PipelineEvent`. */
interface IngestEvent {
  stage: string;
  detail?: Record<string, unknown> | null;
}

export interface IngestData {
  duration: number | null;
  windows: number | null;
  sha256: string | null;
}

export interface IngestFilmProps extends Partial<IngestData> {
  /** The event stream. The component finds `ingest` in it if no numbers are given. */
  events?: readonly IngestEvent[];
  /** The length of an analysis window in seconds. Section "Stage 1" says ten. */
  windowSeconds?: number;
  className?: string;
}

/** The full run: the windows sliding in plus the hash lighting up. */
const DURATION_MS = 1600;
/** The share of the run after which all the windows are in. */
const WINDOWS_END = 0.72;
const WINDOW_SECONDS = 10;

function numberAt(detail: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = detail?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** The numbers of the ingest step from the stream. A missing event means all `null`. */
export function ingestData(events: readonly IngestEvent[] | undefined): IngestData {
  const empty: IngestData = { duration: null, windows: null, sha256: null };
  if (!events) return empty;
  const ingest = [...events].reverse().find((event) => event.stage === "ingest");
  if (!ingest) return empty;
  const sha = ingest.detail?.sha256;
  return {
    duration: numberAt(ingest.detail, "duration"),
    windows: numberAt(ingest.detail, "windows"),
    sha256: typeof sha === "string" && sha.length > 0 ? sha : null,
  };
}

/* -------------------------------------------------------------------------- */
/* The window grid on the canvas                                              */
/* -------------------------------------------------------------------------- */

interface AnalysisWindow {
  from: number;
  to: number;
}

function layoutWindows(seconds: number, count: number, windowLength: number): AnalysisWindow[] {
  const step = windowStep(seconds, count, windowLength);
  const list: AnalysisWindow[] = [];
  for (let i = 0; i < count; i += 1) {
    const from = step === null ? 0 : Math.min(i * step, Math.max(0, seconds - windowLength));
    list.push({ from, to: Math.min(seconds, from + windowLength) });
  }
  return list;
}

/* -------------------------------------------------------------------------- */
/* Component                                                                  */
/* -------------------------------------------------------------------------- */

export function IngestFilm({
  events,
  duration,
  windows,
  sha256,
  windowSeconds = WINDOW_SECONDS,
  className = "",
}: IngestFilmProps) {
  const fromStream = useMemo(() => ingestData(events), [events]);
  const seconds = duration ?? fromStream.duration;
  const windowCount = windows ?? fromStream.windows;
  const hash = sha256 ?? fromStream.sha256;

  const reducedMotion = useReducedMotion();
  const step = windowStep(seconds, windowCount, windowSeconds);
  const overlap = step === null ? null : Math.max(0, windowSeconds - step);

  const windowList = useMemo(
    () =>
      seconds !== null && windowCount !== null && windowCount > 0
        ? layoutWindows(seconds, windowCount, windowSeconds)
        : [],
    [seconds, windowCount, windowSeconds],
  );

  const draw = useMemo(
    () =>
      (
        ctx: CanvasRenderingContext2D,
        width: number,
        height: number,
        progress: number,
      ) => {
        if (seconds === null || seconds <= 0 || windowList.length === 0) return;

        const marginX = 2;
        const field = Math.max(1, width - marginX * 2);
        const toX = (value: number) => marginX + (value / seconds) * field;
        const axisY = height - 22;
        const laneHeight = 13;
        const rows = 2;

        /* A tick every ten seconds. Real numbers, because they come from the length. */
        ctx.strokeStyle = `${theme.muted}30`;
        ctx.lineWidth = 1;
        ctx.fillStyle = `${theme.muted}99`;
        ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
        ctx.textBaseline = "top";
        for (let s = 0; s <= seconds; s += 10) {
          const x = Math.round(toX(s)) + 0.5;
          ctx.beginPath();
          ctx.moveTo(x, axisY - 4);
          ctx.lineTo(x, axisY + 4);
          ctx.stroke();
          if (s % 30 === 0) ctx.fillText(`${s}`, x + 3, axisY + 6);
        }

        /* The axis. */
        ctx.strokeStyle = `${theme.muted}66`;
        ctx.beginPath();
        ctx.moveTo(marginX, axisY + 0.5);
        ctx.lineTo(width - marginX, axisY + 0.5);
        ctx.stroke();

        /* The windows slide in one by one, in two rows, so the overlap is visible. */
        const share = ease(Math.min(1, progress / WINDOWS_END));
        const visible = share * windowList.length;

        windowList.forEach((analysisWindow, i) => {
          const entering = Math.min(1, Math.max(0, visible - i));
          if (entering <= 0) return;
          const smooth = ease(entering);
          const x0 = toX(analysisWindow.from);
          const x1 = toX(analysisWindow.to);
          const row = i % rows;
          const y = axisY - 18 - row * (laneHeight + 4) - (1 - smooth) * 10;

          ctx.globalAlpha = smooth;
          ctx.fillStyle = `${theme.text}1F`;
          ctx.fillRect(x0, y, Math.max(2, x1 - x0), laneHeight);
          ctx.strokeStyle = `${theme.text}59`;
          ctx.lineWidth = 1;
          ctx.strokeRect(Math.round(x0) + 0.5, Math.round(y) + 0.5, Math.max(2, x1 - x0) - 1, laneHeight - 1);
          ctx.globalAlpha = 1;
        });

        /* The leading edge: where the drawing stands. It disappears once the windows are complete. */
        if (share < 1) {
          const last = windowList[Math.min(windowList.length - 1, Math.floor(visible))];
          const x = Math.round(toX(last.to)) + 0.5;
          ctx.strokeStyle = `${theme.accent}CC`;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(x, axisY - 18 - rows * (laneHeight + 4));
          ctx.lineTo(x, axisY);
          ctx.stroke();
        }
      },
    [seconds, windowList],
  );

  const { container, canvas } = useAnimatedCanvas({
    duration: DURATION_MS,
    key: `${seconds ?? "none"}:${windowCount ?? "none"}`,
    enabled: windowList.length > 0,
    draw,
  });

  const digits = useMemo(() => (hash ? hash.slice(0, 64).split("") : []), [hash]);

  return (
    <section
      data-testid="ingest-film"
      data-windows={windowCount ?? ""}
      className={`origin-card flex flex-col gap-4 p-6 ${className}`}
    >
      <style>{`
        @keyframes origin-cell-enter {
          from { opacity: 0; transform: translateY(3px); }
          to   { opacity: 1; transform: none; }
        }
        .origin-hash-cell {
          animation: origin-cell-enter 320ms cubic-bezier(0.33, 1, 0.68, 1) both;
        }
        @media (prefers-reduced-motion: reduce) {
          .origin-hash-cell { animation: none; opacity: 1; }
        }
      `}</style>

      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>INGEST AND ANALYSIS WINDOWS</h3>
        {seconds !== null ? (
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
            LENGTH{" "}
            <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{formatTimecodeTenths(seconds)}</span>
          </p>
        ) : null}
      </header>

      {windowList.length > 0 ? (
        <div
          ref={container}
          data-testid="windows-board"
          role="img"
          aria-label={`Time axis of ${seconds?.toFixed(1)} seconds with ${windowCount} analysis windows of ${windowSeconds} seconds each`}
          className="relative h-32 w-full overflow-hidden rounded-inner border border-muted/16 bg-bg"
        >
          <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
        </div>
      ) : (
        <p className="text-sm text-muted">
          The ingest event has not reported the length of the material or the number of windows
          yet, so there is nothing to lay out on the time axis.
        </p>
      )}

      <dl className={`grid grid-cols-2 gap-3 text-muted sm:grid-cols-4 ${MICRO_LABEL_CLASS}`}>
        <div>
          <dt>ANALYSIS WINDOWS</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{windowCount ?? "none"}</dd>
        </div>
        <div>
          <dt>WINDOW LENGTH</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{windowSeconds.toFixed(0)} s</dd>
        </div>
        <div>
          <dt>WINDOW STEP</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {step === null ? "none" : `${step.toFixed(2)} s`}
          </dd>
        </div>
        <div>
          <dt>OVERLAP</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {overlap === null ? "none" : `${overlap.toFixed(2)} s`}
          </dd>
        </div>
      </dl>

      {digits.length > 0 ? (
        <figure className="flex flex-col gap-2">
          <figcaption className={`text-muted ${MICRO_LABEL_CLASS}`}>
            SHA-256 OF THE MATERIAL
          </figcaption>
          <div
            data-testid="hash-grid"
            role="img"
            aria-label={`SHA-256 hash of the material: ${hash}`}
            className="grid grid-cols-[repeat(32,minmax(0,1fr))] gap-[2px]"
          >
            {digits.map((digit, i) => {
              const value = parseInt(digit, 16);
              const brightness = Number.isNaN(value) ? 0.1 : 0.12 + (value / 15) * 0.62;
              return (
                <span
                  key={`${i}-${digit}`}
                  className={`origin-hash-cell flex aspect-square items-center justify-center rounded-[2px] text-[9px] leading-none ${TECHNICAL_VALUE_CLASS}`}
                  style={{
                    animationDelay: reducedMotion ? "0ms" : `${600 + i * 14}ms`,
                    backgroundColor: `rgba(255,255,255,${brightness.toFixed(3)})`,
                    color: brightness > 0.45 ? theme.bg : `${theme.text}99`,
                  }}
                >
                  {digit}
                </span>
              );
            })}
          </div>
        </figure>
      ) : null}

      <p className="text-xs text-muted">
        Every rectangle is one analysis window: there are exactly as many of them as the stream
        reported, and the step between them is the quotient of the length of the material and the
        number of windows. Loudness normalization targets -23 LUFS under BS.1770-4, but the stream
        does not carry the measured loudness, so the screen does not draw it. There is no waveform
        here either - nobody computed any samples.
      </p>
    </section>
  );
}

export default IngestFilm;
