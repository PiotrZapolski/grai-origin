"use client";

/**
 * The time overlay (section 13.2, the first of four panels).
 *
 * Two waveforms one above the other, the common span highlighted, a slider and a
 * button switching the listen at the synchronized point. The waves are drawn by
 * `wavesurfer.js`, but that is only a picture - the whole synchronization sits
 * in `AbPlayer`, which is embedded here.
 *
 * `alignment` is sometimes `null`, and its fields are independently nullable (a
 * match from lyrics alone has no time alignment). The panel then says outright
 * that there is no alignment and leaves the listen without an offset instead of
 * drawing a highlight that means nothing.
 */

import { useEffect, useRef, useState } from "react";

import type { Alignment } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import AbPlayer from "./AbPlayer";
import { formatTimecodeTenths } from "../../lib/format";

export interface WaveOverlayProps {
  queryUrl: string;
  candidateUrl: string;
  queryDuration: number | null;
  candidateDuration?: number | null;
  alignment: Alignment | null;
  /** The candidate name, for the caption of the second wave. */
  candidateName?: string;
  className?: string;
}

export interface SpanPercent {
  /** A percentage of the frame width. */
  left: number;
  width: number;
}

/**
 * The offset of the candidate relative to the query.
 *
 * `null` means "cannot be computed" and must not be silently turned into zero:
 * zero is the claim that both recordings start at the same place.
 */
export function offsetFromAlignment(alignment: Alignment | null): number | null {
  if (!alignment) return null;
  const { query_span: query, candidate_span: candidate } = alignment;
  if (!query || !candidate) return null;
  return candidate[0] - query[0];
}

/** The span converted into percentages of the frame. Clipped to the length of the recording. */
export function spanPercent(
  span: [number, number] | null | undefined,
  duration: number | null | undefined,
): SpanPercent | null {
  if (!span || !duration || duration <= 0) return null;
  const start = Math.max(0, Math.min(span[0], duration));
  const end = Math.max(start, Math.min(span[1], duration));
  return {
    left: (start / duration) * 100,
    width: ((end - start) / duration) * 100,
  };
}

interface TrackProps {
  url: string;
  duration: number | null;
  span: SpanPercent | null;
  position: number | null;
  label: string;
  spanTestid: string;
  markerTestid: string;
  color: string;
}

/**
 * A lazy, single import of wavesurfer.
 *
 * The import is dynamic, because the library reaches for the DOM and has no
 * business being in the Next.js server pass. It is **one per module**, not one
 * per wave: two parallel `import()` calls for the same module can end up on
 * different instances (in a test the second wave was getting a different module
 * than the first).
 */
let waveModule: Promise<typeof import("wavesurfer.js")> | null = null;

async function loadWavesurfer() {
  if (waveModule === null) waveModule = import("wavesurfer.js");
  return (await waveModule).default;
}

/** One wave with its highlight and playback marker. */
function Track({
  url,
  duration,
  span,
  position,
  label,
  spanTestid,
  markerTestid,
  color,
}: TrackProps) {
  const container = useRef<HTMLDivElement | null>(null);
  const instance = useRef<{ destroy: () => void; setTime?: (time: number) => void } | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const WaveSurfer = await loadWavesurfer();
        if (!alive || !container.current) return;
        instance.current = WaveSurfer.create({
          container: container.current,
          url,
          height: 64,
          waveColor: theme.muted,
          progressColor: color,
          cursorWidth: 0,
          interact: false,
          normalize: true,
        }) as unknown as { destroy: () => void; setTime?: (time: number) => void };
      } catch {
        // A missing decoder or a missing network has no right to bring the
        // evidence panel down. Listening keeps working, only the picture of the
        // wave disappears.
      }
    })();

    return () => {
      alive = false;
      instance.current?.destroy();
      instance.current = null;
    };
  }, [url, color]);

  const positionPercent =
    position !== null && duration && duration > 0
      ? Math.max(0, Math.min(100, (position / duration) * 100))
      : null;

  return (
    <figure className="flex flex-col gap-2">
      <figcaption className={`flex justify-between text-muted ${MICRO_LABEL_CLASS}`}>
        <span>{label}</span>
        <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
          {duration ? formatTimecodeTenths(duration) : "length unknown"}
        </span>
      </figcaption>

      <div className="relative h-16 w-full overflow-hidden rounded-inner border border-muted/20 bg-bg">
        <div ref={container} className="h-full w-full" />

        {span ? (
          <div
            data-testid={spanTestid}
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 border-x border-accent/60 bg-accent/15"
            style={{ left: `${span.left}%`, width: `${span.width}%` }}
          />
        ) : null}

        {positionPercent !== null ? (
          <div
            data-testid={markerTestid}
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 w-px bg-text"
            style={{ left: `${positionPercent}%` }}
          />
        ) : null}
      </div>
    </figure>
  );
}

export function WaveOverlay({
  queryUrl,
  candidateUrl,
  queryDuration,
  candidateDuration = null,
  alignment,
  candidateName = "CANDIDATE",
  className = "",
}: WaveOverlayProps) {
  const offset = offsetFromAlignment(alignment);
  const [position, setPosition] = useState<number>(alignment?.query_span?.[0] ?? 0);

  const querySpanPercent = spanPercent(alignment?.query_span, queryDuration);
  const candidateSpanPercent = spanPercent(alignment?.candidate_span, candidateDuration);

  return (
    // The overlay is the evidence, and the evidence has to dominate together with
    // the verdict (the hierarchy of the show): it gets more air than the other
    // three E4 panels.
    <section
      className={`origin-card flex flex-col gap-6 p-6 sm:p-8 ${className}`}
      data-testid="overlay"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>TIME OVERLAY</h3>
        {offset !== null ? (
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
            OFFSET{" "}
            <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{offset.toFixed(2)} s</span>
            {alignment?.tempo_ratio ? (
              <>
                {" / TEMPO "}
                <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
                  {alignment.tempo_ratio.toFixed(2)}
                </span>
              </>
            ) : null}
          </p>
        ) : null}
      </header>

      {offset === null ? (
        <p className="text-sm text-muted">
          There is no time alignment for this candidate. Listening works, but without an offset:
          both recordings play from the same point of their own time axis.
        </p>
      ) : null}

      {/*
        Both waves are white. Lime on the query wave was a colour code for the
        role of the track, that is, decoration - and in this panel the accent
        belongs to the **common span**, because that is the evidence. When the
        whole wave is lime, the frame of the highlight stops distinguishing
        anything.
      */}
      <Track
        url={queryUrl}
        duration={queryDuration}
        span={querySpanPercent}
        position={position}
        label="QUERY"
        spanTestid="query-common-span"
        markerTestid="query-marker"
        color={theme.text}
      />

      <Track
        url={candidateUrl}
        duration={candidateDuration}
        span={candidateSpanPercent}
        position={offset === null ? position : position + offset}
        label={candidateName}
        spanTestid="candidate-common-span"
        markerTestid="candidate-marker"
        color={theme.text}
      />

      <AbPlayer
        queryUrl={queryUrl}
        candidateUrl={candidateUrl}
        offset={offset ?? 0}
        querySpan={alignment?.query_span ?? null}
        candidateSpan={alignment?.candidate_span ?? null}
        queryDuration={queryDuration}
        onPositionChange={setPosition}
      />
    </section>
  );
}

export default WaveOverlay;
