"use client";

/**
 * The histogram of offset differences of detector A (section 7.1).
 *
 * This is proof and picture at once: **a genuine match gives a sharp spike**,
 * because many hashes share the same offset difference, while a random
 * coincidence spreads out flat. The difference is visible to the naked eye and
 * that is the entire content of the panel.
 *
 * Which is exactly why this chart **has no right to be created out of nothing**.
 * A chart drawn from a random number or from a hash of the address would take
 * the meaning away from both cases at once: a flat distribution would stop
 * meaning "this is a coincidence", and a sharp spike would stop meaning "this is
 * a hit".
 *
 * The panel therefore has two modes and both tell the truth about what they have:
 *
 * 1. **With a distribution** (`bins`): an ordinary histogram, the bars grow in
 *    turn, and only the dominant spike gets the lime.
 * 2. **Without a distribution** (today's contract): **a hash swarm**. The cloud
 *    has exactly as many points as there were matched hashes, and exactly that
 *    part of the cloud which the detector measured as `peak_ratio` converges into
 *    a single column. What is true is the size of the swarm and its split into
 *    two parts; the position of an individual point means nothing and the panel
 *    says so outright. There are no invented buckets along the offset axis here,
 *    because nobody sent the offsets of the remaining hashes.
 */

import { useMemo } from "react";

import type { DetectorStatus } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import { readSpikes, dominantIndex, scatter, dominantShare } from "./geometry";
import { useAnimatedCanvas, useProgress, ease } from "./motion";

export interface OffsetHistogramProps {
  /** `undefined` means: the key is not in `evidence`, the detector has not started. */
  status: DetectorStatus | undefined;
  reason?: string | null;
  /**
   * The distribution of offset differences: a list of `{ offset, count }`. The
   * contract does **not** carry it today - the field waits for
   * `FingerprintResult.offset_histogram`.
   */
  bins?: unknown;
  matchedHashes?: number | null;
  /** The share of hashes in the dominant spike. Below 0.25 the spec treats it as noise. */
  peakRatio?: number | null;
  repetitions?: number;
  offset?: number | null;
  /** How many hashes the query had in total (`detail.hashes` of the fingerprint stage). */
  queryHashes?: number | null;
  className?: string;
}

const STATE_SENTENCES: Record<DetectorStatus, string> = {
  ok: "",
  not_applicable: "The fingerprint detector has nothing to compare here.",
  gated: "The fingerprint detector was held back by its own confidence check.",
  failed: "The fingerprint detector returned no result.",
};

/** The noise threshold from section 7.1. Below this share a spike is not proof. */
export const NOISE_THRESHOLD = 0.25;

const HEIGHT = 150;
const DURATION_MS = 1600;
/** The most points we draw. Above that one point carries several hashes. */
const POINT_LIMIT = 1400;

function Header({ peakRatio }: { peakRatio: number | null }) {
  return (
    <header className="flex flex-wrap items-baseline justify-between gap-3">
      <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>OFFSET DIFFERENCES</h3>
      {peakRatio !== null ? (
        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
          DOMINANT SPIKE{" "}
          <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {Math.round(peakRatio * 100)}%
          </span>
        </p>
      ) : null}
    </header>
  );
}

/* -------------------------------------------------------------------------- */
/* The hash swarm: a cloud of true size converging into a spike               */
/* -------------------------------------------------------------------------- */

interface SwarmProps {
  /** How many hashes matched. The size of the swarm is exactly that number. */
  matchedHashes: number;
  /** The share of points that is to fall into the column. Straight from `peak_ratio`. */
  peakRatio: number;
  className?: string;
}

function Swarm({ matchedHashes, peakRatio, className = "" }: SwarmProps) {
  const points = Math.max(1, Math.min(POINT_LIMIT, Math.round(matchedHashes)));
  const weight = matchedHashes / points;
  const inColumn = Math.round(points * Math.min(1, Math.max(0, peakRatio)));

  const draw = useMemo(
    () =>
      (
        ctx: CanvasRenderingContext2D,
        width: number,
        height: number,
        progress: number,
      ) => {
        const floorY = height - 20;
        const topY = 12;
        const center = width * 0.5;
        const columnWidth = Math.max(18, Math.min(64, width * 0.09));
        const perColumn = Math.max(4, Math.round(columnWidth / 3.2));
        const rows = Math.max(1, Math.ceil(inColumn / perColumn));
        const rowHeight = Math.min(3.4, (floorY - topY) / rows);

        /* The trace of the column: where the points converge. A line alone, no fill. */
        ctx.strokeStyle = `${theme.accent}33`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(Math.round(center - columnWidth / 2) + 0.5, topY);
        ctx.lineTo(Math.round(center - columnWidth / 2) + 0.5, floorY);
        ctx.moveTo(Math.round(center + columnWidth / 2) + 0.5, topY);
        ctx.lineTo(Math.round(center + columnWidth / 2) + 0.5, floorY);
        ctx.stroke();

        /* The floor. */
        ctx.strokeStyle = `${theme.muted}55`;
        ctx.beginPath();
        ctx.moveTo(0, floorY + 0.5);
        ctx.lineTo(width, floorY + 0.5);
        ctx.stroke();

        for (let i = 0; i < points; i += 1) {
          const inSpike = i < inColumn;

          // Start: a cloud scattered across the whole frame. The scatter is a
          // layout, not a measurement - see `scatter` in geometry.ts.
          const x0 = 6 + scatter(i, 1) * (width - 12);
          const y0 = topY + scatter(i, 2) * (floorY - topY);

          let x1: number;
          let y1: number;
          if (inSpike) {
            const row = Math.floor(i / perColumn);
            const column = i % perColumn;
            x1 = center - columnWidth / 2 + ((column + 0.5) / perColumn) * columnWidth;
            y1 = floorY - 2 - row * rowHeight;
          } else {
            // The remaining hashes stay in the cloud: we do not know their
            // offsets, so they must not be arranged into any shape suggesting a
            // distribution.
            const side = scatter(i, 3) < 0.5 ? -1 : 1;
            const distance =
              columnWidth / 2 + 10 + scatter(i, 4) * (width / 2 - columnWidth / 2 - 14);
            x1 = center + side * distance;
            y1 = topY + scatter(i, 5) * (floorY - topY);
          }

          // A staggered start spreads the convergence out in time, so that motion
          // is visible rather than a swapped picture.
          const delay = scatter(i, 6) * 0.35;
          const flight = ease(Math.min(1, Math.max(0, (progress - delay) / (1 - delay))));

          const x = x0 + (x1 - x0) * flight;
          const y = y0 + (y1 - y0) * flight;

          if (inSpike) {
            ctx.fillStyle = theme.accent;
            ctx.globalAlpha = 0.35 + 0.65 * flight;
          } else {
            ctx.fillStyle = theme.text;
            ctx.globalAlpha = 0.32 - 0.14 * flight;
          }
          ctx.fillRect(x - 1, y - 1, 2, 2);
        }
        ctx.globalAlpha = 1;

        /* The zone captions. They say what is what, right on the picture. */
        ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
        ctx.textBaseline = "top";
        ctx.textAlign = "center";
        ctx.fillStyle = `${theme.accent}DD`;
        ctx.fillText("SAME OFFSET", center, floorY + 5);
        ctx.fillStyle = `${theme.muted}AA`;
        ctx.textAlign = "left";
        ctx.fillText("OFFSET UNKNOWN", 4, floorY + 5);
        ctx.textAlign = "right";
        ctx.fillText("OFFSET UNKNOWN", width - 4, floorY + 5);
        ctx.textAlign = "left";
      },
    [points, inColumn],
  );

  const { container, canvas } = useAnimatedCanvas({
    duration: DURATION_MS,
    key: `${points}:${inColumn}`,
    draw,
  });

  return (
    <div
      ref={container}
      data-testid="hash-swarm"
      data-points={points}
      role="img"
      aria-label={`A swarm of ${matchedHashes} matched hashes; ${inColumn} of ${points} points converge into the dominant spike`}
      className={`relative h-44 w-full overflow-hidden rounded-inner border border-muted/16 bg-bg ${className}`}
    >
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
      {weight > 1.05 ? (
        <span
          className={`absolute right-2 top-2 text-muted ${MICRO_LABEL_CLASS} ${TECHNICAL_VALUE_CLASS}`}
        >
          1 point = {weight.toFixed(1)} hashes
        </span>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel                                                                      */
/* -------------------------------------------------------------------------- */

export function OffsetHistogram({
  status,
  reason = null,
  bins,
  matchedHashes = null,
  peakRatio = null,
  repetitions = 0,
  offset = null,
  queryHashes = null,
  className = "",
}: OffsetHistogramProps) {
  const spikes = useMemo(() => readSpikes(bins), [bins]);
  const dominant = useMemo(() => (spikes ? dominantIndex(spikes) : null), [spikes]);
  const share = useMemo(() => (spikes ? dominantShare(spikes) : null), [spikes]);

  const progress = useProgress({
    duration: DURATION_MS,
    key: `${spikes?.length ?? 0}:${peakRatio ?? "none"}:${matchedHashes ?? "none"}`,
    enabled: status === "ok",
  });
  const growth = ease(progress);

  if (status === undefined) {
    return (
      <section
        data-testid="offset-histogram"
        data-state="not-started"
        className={`origin-card flex flex-col gap-4 p-6 ${className}`}
      >
        <Header peakRatio={null} />
        <p className="text-sm text-muted">
          The fingerprint detector has not computed this candidate yet. A missing result is not
          zero.
        </p>
      </section>
    );
  }

  if (status !== "ok") {
    return (
      <section
        data-testid="offset-histogram"
        data-state={status}
        className={`origin-card flex flex-col gap-4 p-6 ${className}`}
      >
        <Header peakRatio={null} />
        <p className="text-sm text-muted">{reason ?? STATE_SENTENCES[status]}</p>
      </section>
    );
  }

  /* ------------------------------------------------------------------ */
  /* The full distribution                                               */
  /* ------------------------------------------------------------------ */
  if (spikes && dominant !== null) {
    const tallest = spikes[dominant].count || 1;
    const total = spikes.reduce((sum, spike) => sum + spike.count, 0);
    const barWidth = 100 / spikes.length;
    const thresholdY = HEIGHT - (NOISE_THRESHOLD * HEIGHT * tallest) / Math.max(1, tallest);

    return (
      <section
        data-testid="offset-histogram"
        data-state="ok"
        data-distribution="present"
        data-spikes={spikes.length}
        className={`origin-card flex flex-col gap-4 p-6 ${className}`}
      >
        <Header peakRatio={peakRatio} />

        <svg
          role="img"
          aria-label={`Histogram of offset differences, ${spikes.length} buckets, dominant spike at ${spikes[dominant].offset.toFixed(2)} seconds`}
          viewBox={`0 0 100 ${HEIGHT}`}
          preserveAspectRatio="none"
          className="h-44 w-full"
        >
          {/* The floor of the chart. */}
          <line
            x1={0}
            y1={HEIGHT}
            x2={100}
            y2={HEIGHT}
            stroke={theme.muted}
            strokeWidth={0.4}
            opacity={0.5}
          />
          {spikes.map((spike, index) => {
            const barShare = spike.count / tallest;
            const isDominant = index === dominant;
            // The background bars grow from left to right, the dominant spike
            // arrives last - it is the punchline of the picture.
            const delay = isDominant ? 0.45 : (index / spikes.length) * 0.45;
            const local = ease(Math.min(1, Math.max(0, (growth - delay) / (1 - delay))));
            const barHeight = barShare * (HEIGHT - 8) * local;
            return (
              <rect
                key={`${spike.offset}-${index}`}
                data-spike={isDominant ? "dominant" : "background"}
                x={index * barWidth + barWidth * 0.12}
                y={HEIGHT - barHeight}
                width={barWidth * 0.76}
                height={Math.max(0, barHeight)}
                fill={isDominant ? theme.accent : theme.text}
                opacity={isDominant ? 1 : 0.28}
              >
                <title>{`${spike.offset.toFixed(2)} s: ${spike.count} hashes`}</title>
              </rect>
            );
          })}
          {/* The noise threshold from section 7.1, relative to the dominant spike. */}
          <line
            x1={0}
            y1={thresholdY}
            x2={100}
            y2={thresholdY}
            stroke={theme.muted}
            strokeWidth={0.4}
            strokeDasharray="2 2"
          />
        </svg>

        <dl className={`grid grid-cols-2 gap-3 text-muted sm:grid-cols-4 ${MICRO_LABEL_CLASS}`}>
          <div>
            <dt>SPIKE OFFSET</dt>
            <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
              {spikes[dominant].offset.toFixed(2)} s
            </dd>
          </div>
          <div>
            <dt>HASHES IN THE SPIKE</dt>
            <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
              {spikes[dominant].count} of {total}
            </dd>
          </div>
          <div>
            <dt>SHARE FROM THE DISTRIBUTION</dt>
            <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
              {share === null ? "none" : `${Math.round(share * 100)}%`}
            </dd>
          </div>
          <div>
            <dt>DISJOINT SPIKES</dt>
            <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{repetitions}</dd>
          </div>
        </dl>

        <p className="text-xs text-muted">
          A sharp spike means that many hashes share the same offset difference, that is, that the
          two recordings are shifted against each other by a constant amount. A flat distribution
          means coincidence.
        </p>
      </section>
    );
  }

  /* ------------------------------------------------------------------ */
  /* Without a distribution: a swarm of true size and the numbers that arrived */
  /* ------------------------------------------------------------------ */
  const hasShare = typeof peakRatio === "number" && Number.isFinite(peakRatio);
  const spikeShare = hasShare ? Math.min(1, Math.max(0, peakRatio as number)) : 0;
  const shareWidth = spikeShare * growth;
  const hasSwarm = hasShare && typeof matchedHashes === "number" && matchedHashes > 0;
  const inSpike = hasSwarm ? Math.round((matchedHashes as number) * spikeShare) : null;
  // The counter runs up to its target value, but never hides it for longer than
  // the animation lasts: the full number stands next to it, in the measurement row.
  const counter = inSpike === null ? null : Math.round(inSpike * growth);

  return (
    <section
      data-testid="offset-histogram"
      data-state="ok"
      data-distribution="none"
      className={`origin-card flex flex-col gap-4 p-6 ${className}`}
    >
      <Header peakRatio={hasShare ? (peakRatio as number) : null} />

      {hasSwarm ? (
        <>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span
              data-testid="spike-counter"
              className={`text-3xl ${TECHNICAL_VALUE_CLASS} ${
                spikeShare >= NOISE_THRESHOLD ? "text-accent" : "text-text"
              }`}
            >
              {counter}
            </span>
            <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
              hashes at the same offset difference, out of {matchedHashes} matched
            </span>
          </div>
          <Swarm matchedHashes={matchedHashes as number} peakRatio={spikeShare} />
        </>
      ) : null}

      <p className="text-sm text-muted">
        The full distribution of offset differences did not arrive in the evidence, so there is
        nothing to draw a histogram from. {hasSwarm
          ? "The swarm has as many points as there were matched hashes, and exactly that part of them converges into the column which the detector measured as the dominant spike. Where an individual point sits means nothing: nobody computed the offsets of the remaining hashes."
          : "Below stand the numbers the detector really returned."}
      </p>

      {hasShare ? (
        <figure className="flex flex-col gap-2">
          <div
            data-testid="share-bar"
            role="img"
            aria-label={`Share of hashes in the dominant spike: ${Math.round((peakRatio as number) * 100)} percent`}
            className="relative h-3 w-full overflow-hidden rounded-full bg-muted/20"
          >
            <span
              className="absolute inset-y-0 left-0 rounded-full transition-none"
              style={{
                width: `${shareWidth * 100}%`,
                backgroundColor:
                  (peakRatio as number) >= NOISE_THRESHOLD ? theme.accent : theme.muted,
              }}
            />
            {/* The noise threshold from section 7.1 marked on the scale, not described in words. */}
            <span
              data-testid="noise-threshold"
              className="absolute inset-y-0 w-px bg-text/60"
              style={{ left: `${NOISE_THRESHOLD * 100}%` }}
            />
          </div>
          <figcaption className="text-xs text-muted">
            The mark stands at the threshold of {NOISE_THRESHOLD.toFixed(2)}: below it the
            specification treats a match as noise rather than as a hit.
          </figcaption>
        </figure>
      ) : null}

      <dl className={`grid grid-cols-2 gap-3 text-muted sm:grid-cols-4 ${MICRO_LABEL_CLASS}`}>
        <div>
          <dt>MATCHED HASHES</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {matchedHashes === null ? "none" : matchedHashes}
          </dd>
        </div>
        <div>
          <dt>QUERY HASHES</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {queryHashes === null ? "none" : queryHashes}
          </dd>
        </div>
        <div>
          <dt>DISJOINT SPIKES</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{repetitions}</dd>
        </div>
        <div>
          <dt>OFFSET</dt>
          <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {offset === null ? "none" : `${offset.toFixed(2)} s`}
          </dd>
        </div>
      </dl>
    </section>
  );
}

export default OffsetHistogram;
