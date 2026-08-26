"use client";

/**
 * The common span of two recordings, drawn as a ribbon between the waveforms.
 *
 * The time overlay from section 13.2 shows two highlights, each on its own wave.
 * This component adds what is missing there: **an explicit connection between
 * them**, that is, the answer to "this piece of the query corresponds to which
 * piece of the candidate". The ribbon is an ordinary quadrilateral joining the
 * two intervals from `alignment`, that is, a drawing of two pairs of numbers
 * from the contract, not an interpolation.
 *
 * The wave samples are **computed from the audio in the browser** or they are
 * not there at all. Without samples the component draws a flat line and writes
 * that the shape does not come from a measurement - exactly as the entry screen
 * does. Deriving a plausible waveform from an address would be the cheapest prop
 * in the whole product.
 */

import { useMemo } from "react";

import type { Alignment } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import { useProgress, ease } from "./motion";

export interface AlignmentRibbonProps {
  alignment: Alignment | null;
  /** Peaks in 0..1 computed from the audio. `null` means: not measured. */
  queryPeaks?: readonly number[] | null;
  candidatePeaks?: readonly number[] | null;
  queryDuration?: number | null;
  candidateDuration?: number | null;
  candidateName?: string | null;
  className?: string;
}

const WAVE_HEIGHT = 42;
const RIBBON_HEIGHT = 46;
const WIDTH = 1000;
const DURATION_MS = 1400;

/** How many seconds apart to place a tick, so that it does not turn into a solid bar. */
function tickStep(duration: number): number {
  for (const step of [5, 10, 15, 30, 60, 120]) {
    if (duration / step <= 22) return step;
  }
  return Math.ceil(duration / 20);
}

/** A timecode in minutes:seconds format. */
function timecode(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds - minutes * 60);
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

/** The share of an interval in the whole length, clipped to the frame. `null` without data. */
export function spanShare(
  span: [number, number] | null | undefined,
  duration: number | null | undefined,
): { from: number; to: number } | null {
  if (!span || typeof duration !== "number" || duration <= 0) return null;
  const from = Math.max(0, Math.min(span[0], duration)) / duration;
  const to = Math.max(0, Math.min(span[1], duration)) / duration;
  return { from, to: Math.max(from, to) };
}

function Wave({
  peaks,
  label,
  share,
  reveal,
  span,
  duration,
  testid,
}: {
  peaks: readonly number[] | null | undefined;
  label: string;
  share: { from: number; to: number } | null;
  reveal: number;
  /** The interval in seconds straight from `alignment`, to caption the frame. */
  span?: [number, number] | null;
  duration?: number | null;
  testid: string;
}) {
  const bars = peaks && peaks.length > 0 ? peaks : null;
  const step = bars ? WIDTH / bars.length : 0;
  const tick = typeof duration === "number" && duration > 0 ? tickStep(duration) : null;

  return (
    <figure className="flex flex-col gap-1.5">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-3">
        <span className={`text-muted ${MICRO_LABEL_CLASS}`}>{label}</span>
        {span ? (
          <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
            <span className={`text-accent ${TECHNICAL_VALUE_CLASS}`}>
              {timecode(span[0])} to {timecode(span[1])}
            </span>
          </span>
        ) : null}
      </figcaption>
      <svg
        data-testid={testid}
        data-measured={bars ? "true" : "false"}
        role="img"
        aria-label={bars ? `Waveform: ${label}` : `Waveform not measured: ${label}`}
        viewBox={`0 0 ${WIDTH} ${WAVE_HEIGHT}`}
        preserveAspectRatio="none"
        className="h-12 w-full"
      >
        {/* The time ticks: a mark every few seconds, computed from the length of the recording. */}
        {tick !== null && duration
          ? Array.from({ length: Math.floor(duration / tick) + 1 }, (_, i) => {
              const x = ((i * tick) / duration) * WIDTH;
              return (
                <line
                  key={i}
                  x1={x}
                  y1={WAVE_HEIGHT - 6}
                  x2={x}
                  y2={WAVE_HEIGHT}
                  stroke={theme.muted}
                  strokeWidth={1}
                  opacity={0.4}
                />
              );
            })
          : null}

        {share ? (
          <>
            <rect
              data-testid={`${testid}-span`}
              x={share.from * WIDTH}
              y={0}
              width={Math.max(1, (share.to - share.from) * WIDTH * reveal)}
              height={WAVE_HEIGHT}
              fill={theme.accent}
              opacity={0.14}
            />
            {/* The edge of the span travels with the reveal: you can see how far it reaches. */}
            <line
              x1={(share.from + (share.to - share.from) * reveal) * WIDTH}
              y1={0}
              x2={(share.from + (share.to - share.from) * reveal) * WIDTH}
              y2={WAVE_HEIGHT}
              stroke={theme.accent}
              strokeWidth={1.5}
              opacity={reveal < 1 ? 0.9 : 0.5}
            />
          </>
        ) : null}

        {bars ? (
          bars.map((peak, i) => {
            const barHeight = Math.max(1, peak * WAVE_HEIGHT);
            const center = (i + 0.5) / bars.length;
            const inSpan = share !== null && center >= share.from && center <= share.to;
            return (
              <rect
                key={i}
                data-bar="true"
                x={i * step}
                y={(WAVE_HEIGHT - barHeight) / 2}
                width={Math.max(0.6, step * 0.6)}
                height={barHeight}
                fill={inSpan ? theme.accent : theme.text}
                opacity={inSpan ? 0.9 : 0.4}
              />
            );
          })
        ) : (
          <line
            data-placeholder="true"
            x1={0}
            y1={WAVE_HEIGHT / 2}
            x2={WIDTH}
            y2={WAVE_HEIGHT / 2}
            stroke={theme.muted}
            strokeWidth={1}
            strokeDasharray="4 6"
          />
        )}
      </svg>
    </figure>
  );
}

export function AlignmentRibbon({
  alignment,
  queryPeaks = null,
  candidatePeaks = null,
  queryDuration = null,
  candidateDuration = null,
  candidateName = null,
  className = "",
}: AlignmentRibbonProps) {
  /*
    The stream often does not carry the length of the candidate recording, and
    without it there is no way to place its interval on an axis. Rather than give
    up the only picture of this step, we take a shared axis ending at the last
    known second and **write underneath that this is what we did**. The timecodes
    themselves are true regardless of where the axis ends.
  */
  const candidateEnd = alignment?.candidate_span?.[1] ?? null;
  const provisionalAxis = candidateDuration === null && candidateEnd !== null;
  const candidateLength =
    candidateDuration ?? (candidateEnd !== null ? Math.max(candidateEnd, queryDuration ?? 0) : null);

  const queryShare = useMemo(
    () => spanShare(alignment?.query_span, queryDuration),
    [alignment, queryDuration],
  );
  const candidateShare = useMemo(
    () => spanShare(alignment?.candidate_span, candidateLength),
    [alignment, candidateLength],
  );

  const hasRibbon = queryShare !== null && candidateShare !== null;
  const progress = useProgress({
    duration: DURATION_MS,
    key: `${alignment?.query_span?.join("-") ?? "none"}:${alignment?.candidate_span?.join("-") ?? "none"}`,
    enabled: hasRibbon,
  });
  const reveal = ease(progress);

  const notMeasured = !queryPeaks?.length || !candidatePeaks?.length;

  return (
    <section
      data-testid="alignment-ribbon"
      data-ribbon={hasRibbon ? "present" : "none"}
      className={`origin-card flex flex-col gap-4 p-6 ${className}`}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>COMMON SPAN</h3>
        {alignment?.tempo_ratio != null ? (
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
            TEMPO{" "}
            <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
              {alignment.tempo_ratio.toFixed(2)}
            </span>
          </p>
        ) : null}
      </header>

      <Wave
        peaks={queryPeaks}
        label="INPUT MATERIAL"
        share={queryShare}
        reveal={reveal}
        span={alignment?.query_span ?? null}
        duration={queryDuration}
        testid="query-wave"
      />

      {hasRibbon && queryShare && candidateShare ? (
        <svg
          data-testid="ribbon"
          aria-hidden="true"
          viewBox={`0 0 ${WIDTH} ${RIBBON_HEIGHT}`}
          preserveAspectRatio="none"
          className="h-12 w-full"
        >
          <polygon
            points={[
              `${queryShare.from * WIDTH},0`,
              `${queryShare.to * WIDTH},0`,
              `${candidateShare.to * WIDTH},${RIBBON_HEIGHT}`,
              `${candidateShare.from * WIDTH},${RIBBON_HEIGHT}`,
            ].join(" ")}
            fill={theme.accent}
            opacity={0.12 * reveal}
          />
          {/* A ray sliding from the upper interval down to the lower one: you can see what maps to what. */}
          <line
            data-testid="ribbon-ray"
            x1={(queryShare.from + (candidateShare.from - queryShare.from) * reveal) * WIDTH}
            y1={reveal * RIBBON_HEIGHT}
            x2={(queryShare.to + (candidateShare.to - queryShare.to) * reveal) * WIDTH}
            y2={reveal * RIBBON_HEIGHT}
            stroke={theme.accent}
            strokeWidth={2}
            opacity={reveal < 1 ? 0.9 : 0.35}
          />
          <line
            x1={queryShare.from * WIDTH}
            y1={0}
            x2={candidateShare.from * WIDTH}
            y2={RIBBON_HEIGHT}
            stroke={theme.accent}
            strokeWidth={1.2}
            opacity={reveal}
          />
          <line
            x1={queryShare.to * WIDTH}
            y1={0}
            x2={candidateShare.to * WIDTH}
            y2={RIBBON_HEIGHT}
            stroke={theme.accent}
            strokeWidth={1.2}
            opacity={reveal}
          />
        </svg>
      ) : (
        <p className="text-sm text-muted">
          This entry has no time alignment on both sides, so there is nothing to join. A match
          based on lyrics alone carries no intervals in time.
        </p>
      )}

      <Wave
        peaks={candidatePeaks}
        label={candidateName ? `RECORDING: ${candidateName.toUpperCase()}` : "CANDIDATE RECORDING"}
        share={candidateShare}
        reveal={reveal}
        span={alignment?.candidate_span ?? null}
        duration={candidateLength}
        testid="candidate-wave"
      />

      {provisionalAxis ? (
        <p className="text-xs text-muted">
          The stream did not report the length of the candidate recording, so its axis ends at the
          last known second of the common span. The timecodes on both sides are true, the scale of
          the candidate axis is a convention.
        </p>
      ) : null}

      {notMeasured ? (
        <p className="text-xs text-muted">
          The shape of the wave on at least one side does not come from a measurement - the samples
          could not be computed. The alignment intervals are true, the waveform itself is not
          drawn.
        </p>
      ) : null}
    </section>
  );
}

export default AlignmentRibbon;
