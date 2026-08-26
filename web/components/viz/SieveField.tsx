"use client";

/**
 * Shortlist and commonality filter: two numbers about two different sets.
 *
 * Section 13.2 has a hard prohibition here on confusing one with the other, so
 * the panel separates them physically into two fields:
 *
 * - **the shortlist** concerns the set we search in: out of `from` candidates
 *   `to` remain. There are exactly as many tiles as the stream reported, and
 *   exactly as many drop out. Which candidate in particular fell away, the
 *   stream does not say - so the tiles are nameless and that is written under
 *   the field;
 * - **commonality** concerns the set we judge the significance of a find
 *   against: the field has as many points as the corpus has entries, and as many
 *   of them light up as there are works in which this pattern occurs. A common
 *   pattern lights up half the field and that reads from the back of the room -
 *   which is the entire thesis of stage 4 of the narrative.
 *
 * Neither of these numbers is computed or guessed here. A missing number ends in
 * a sentence, not a shape.
 */

import { useMemo } from "react";

import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import { scatter } from "./geometry";
import { useAnimatedCanvas, useProgress, ease } from "./motion";

/** An event as loose as it has to be to accept both `StreamEvent` and `PipelineEvent`. */
interface SieveEvent {
  stage: string;
  detail?: Record<string, unknown> | null;
}

export interface SieveData {
  from: number | null;
  to: number | null;
  corpusSize: number | null;
  corpusFrequency: number | null;
  meanIdf: number | null;
}

export interface SieveFieldProps extends Partial<SieveData> {
  /** The event stream. The component pulls `shortlist` and `commonality` out itself. */
  events?: readonly SieveEvent[];
  className?: string;
}

const DURATION_MS = 1800;
/** The most corpus points we draw. Above that one point carries several entries. */
const POINT_LIMIT = 6000;

function numberAt(detail: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = detail?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * The numbers of both fields from the stream.
 *
 * `corpus` arrives in `shortlist` and `corpus_size` in `commonality`, and they
 * are the same corpus count; we take whichever really arrived.
 */
export function sieveData(events: readonly SieveEvent[] | undefined): SieveData {
  const empty: SieveData = {
    from: null,
    to: null,
    corpusSize: null,
    corpusFrequency: null,
    meanIdf: null,
  };
  if (!events) return empty;

  const shortlist = [...events].reverse().find((event) => event.stage === "shortlist");
  const commonality = [...events].reverse().find((event) => event.stage === "commonality");

  return {
    from: numberAt(shortlist?.detail, "from"),
    to: numberAt(shortlist?.detail, "to"),
    corpusSize: numberAt(commonality?.detail, "corpus_size") ?? numberAt(shortlist?.detail, "corpus"),
    corpusFrequency: numberAt(commonality?.detail, "corpus_frequency"),
    meanIdf: numberAt(commonality?.detail, "mean_idf"),
  };
}

/* -------------------------------------------------------------------------- */
/* The candidate shortlist                                                    */
/* -------------------------------------------------------------------------- */

function Sieve({ from, to, progress }: { from: number; to: number; progress: number }) {
  const kept = Math.min(from, Math.max(0, to));
  const dropped = from - kept;
  // The dropping starts at once and ends halfway through the run, so the counter
  // below still has something to run up to.
  const fallen = Math.min(dropped, Math.floor(ease(Math.min(1, progress / 0.55)) * dropped));

  return (
    <figure data-testid="sieve-field" data-candidates={from} className="flex flex-col gap-2">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-3">
        <span className={`text-muted ${MICRO_LABEL_CLASS}`}>CANDIDATE SHORTLIST</span>
        <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
          REMAINING{" "}
          <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {from - fallen} of {from}
          </span>
        </span>
      </figcaption>

      <div className="flex flex-wrap gap-1.5">
        {Array.from({ length: from }, (_, i) => {
          // Tiles drop from the end: the stream does not say which candidate fell
          // away, so the order is a convention and the field assigns them no identity.
          const hasFallen = i >= from - fallen;
          return (
            <span
              key={i}
              data-tile={hasFallen ? "dropped" : "kept"}
              className="h-8 w-8 rounded-inner border"
              style={{
                borderColor: hasFallen ? `${theme.muted}1F` : `${theme.text}3D`,
                backgroundColor: hasFallen ? "transparent" : `${theme.text}12`,
                opacity: hasFallen ? 0.22 : 1,
                transform: hasFallen ? "translateY(6px) scale(0.9)" : "none",
                transition: "opacity 260ms ease, transform 260ms ease",
              }}
            />
          );
        })}
      </div>

      <p className="text-xs text-muted">
        There are as many tiles as there were candidates entering the shortlist. The stream does
        not say which one in particular dropped out, only how many remained - which is why the
        tiles carry no names.
      </p>
    </figure>
  );
}

/* -------------------------------------------------------------------------- */
/* The corpus field                                                           */
/* -------------------------------------------------------------------------- */

function CorpusField({
  corpusSize,
  corpusFrequency,
}: {
  corpusSize: number;
  corpusFrequency: number;
}) {
  const points = Math.max(1, Math.min(POINT_LIMIT, Math.round(corpusSize)));
  const weight = corpusSize / points;
  const litCount = Math.min(
    points,
    Math.round((Math.min(corpusFrequency, corpusSize) / corpusSize) * points),
  );

  /**
   * Which points of the field are lit. Computed **once**, not per frame: the
   * scatter is a layout and not a measurement, so it has to stay fixed for the
   * whole run.
   *
   * The order of lighting comes from the same list, so the points light up spread
   * across the whole field instead of filling it as a block - the pattern occurs
   * in N works of the corpus, not in N neighbouring ones.
   */
  const lit = useMemo(() => {
    const order: number[] = [];
    const seen = new Set<number>();
    let attempt = 0;
    while (order.length < litCount && attempt < points * 12) {
      const candidate = Math.floor(scatter(attempt, 11) * points);
      attempt += 1;
      if (seen.has(candidate)) continue;
      seen.add(candidate);
      order.push(candidate);
    }
    // A top-up in case of a dense field: the rest goes in order.
    for (let i = 0; order.length < litCount && i < points; i += 1) {
      if (seen.has(i)) continue;
      seen.add(i);
      order.push(i);
    }
    const when = new Map<number, number>();
    order.forEach((index, i) => when.set(index, (i + 1) / Math.max(1, order.length)));
    return when;
  }, [points, litCount]);

  const draw = useMemo(
    () =>
      (
        ctx: CanvasRenderingContext2D,
        width: number,
        height: number,
        progress: number,
      ) => {
        if (width <= 0 || height <= 0) return;

        // A grid with the proportions of the frame: enough columns for the points
        // to come out square.
        const columns = Math.max(
          1,
          Math.round(Math.sqrt((points * width) / Math.max(1, height))),
        );
        const rows = Math.ceil(points / columns);
        const stepX = width / columns;
        const stepY = height / rows;
        const side = Math.max(1, Math.min(stepX, stepY) - 1);

        const reveal = ease(progress);
        /* The background of the field in one pass: every point in white at low opacity. */
        ctx.fillStyle = theme.text;
        ctx.globalAlpha = 0.12;
        for (let i = 0; i < points; i += 1) {
          ctx.fillRect((i % columns) * stepX, Math.floor(i / columns) * stepY, side, side);
        }

        /* Lit: only those that have already entered the reveal queue. */
        ctx.fillStyle = theme.accent;
        ctx.globalAlpha = 1;
        lit.forEach((turn, index) => {
          if (turn > reveal) return;
          ctx.fillRect(
            (index % columns) * stepX,
            Math.floor(index / columns) * stepY,
            side,
            side,
          );
        });
        ctx.globalAlpha = 1;
      },
    [points, lit],
  );

  const { container, canvas } = useAnimatedCanvas({
    duration: DURATION_MS,
    key: `${points}:${litCount}`,
    draw,
  });

  return (
    <div
      ref={container}
      data-testid="corpus-field"
      data-points={points}
      data-lit={litCount}
      role="img"
      aria-label={`Corpus field: ${corpusSize} works, the pattern occurs in ${corpusFrequency}`}
      className="relative h-40 w-full overflow-hidden rounded-inner border border-muted/16 bg-bg p-1"
    >
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
      {weight > 1.05 ? (
        <span
          className={`absolute right-2 top-2 rounded bg-bg/80 px-1 text-muted ${MICRO_LABEL_CLASS} ${TECHNICAL_VALUE_CLASS}`}
        >
          1 point = {weight.toFixed(1)} works
        </span>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel                                                                      */
/* -------------------------------------------------------------------------- */

export function SieveField({
  events,
  from,
  to,
  corpusSize,
  corpusFrequency,
  meanIdf,
  className = "",
}: SieveFieldProps) {
  const fromStream = useMemo(() => sieveData(events), [events]);
  const fromCount = from ?? fromStream.from;
  const toCount = to ?? fromStream.to;
  const corpus = corpusSize ?? fromStream.corpusSize;
  const frequency = corpusFrequency ?? fromStream.corpusFrequency;
  const idf = meanIdf ?? fromStream.meanIdf;

  const hasSieve = fromCount !== null && toCount !== null && fromCount > 0;
  const hasCorpus = corpus !== null && corpus > 0 && frequency !== null;

  const progress = useProgress({
    duration: DURATION_MS,
    key: `${fromCount ?? "none"}:${toCount ?? "none"}:${corpus ?? "none"}:${frequency ?? "none"}`,
    enabled: hasSieve || hasCorpus,
  });
  const growth = ease(progress);

  const corpusShare = hasCorpus ? Math.min(1, (frequency as number) / (corpus as number)) : null;
  const corpusCounter = hasCorpus ? Math.round((frequency as number) * growth) : null;

  return (
    <section
      data-testid="significance-field"
      className={`origin-card flex flex-col gap-5 p-6 ${className}`}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>SHORTLIST AND COMMONALITY</h3>
        {idf !== null ? (
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
            MEAN IDF{" "}
            <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{idf.toFixed(2)}</span>
          </p>
        ) : null}
      </header>

      {hasSieve ? (
        <Sieve from={fromCount as number} to={toCount as number} progress={progress} />
      ) : (
        <p className="text-sm text-muted">
          The shortlist has not yet reported how many candidates entered and how many remained.
        </p>
      )}

      {hasCorpus ? (
        <figure className="flex flex-col gap-2">
          <figcaption className="flex flex-wrap items-baseline justify-between gap-3">
            <span className={`text-muted ${MICRO_LABEL_CLASS}`}>REFERENCE CORPUS</span>
            <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
              SHARE{" "}
              <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
                {((corpusShare as number) * 100).toFixed(1)}%
              </span>
            </span>
          </figcaption>

          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span
              data-testid="corpus-counter"
              className={`text-3xl ${TECHNICAL_VALUE_CLASS} ${
                (corpusShare as number) >= 0.05 ? "text-accent" : "text-text"
              }`}
            >
              {corpusCounter}
            </span>
            <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
              works of the corpus carry this same pattern, out of {corpus} checked
            </span>
          </div>

          <CorpusField corpusSize={corpus as number} corpusFrequency={frequency as number} />

          <figcaption className="text-xs text-muted">
            Every point is one entry of the reference corpus, and the lime lights up on as many of
            them as the pattern really occurs in. A pattern present across a large part of the
            field is nobody's property but a convention of the genre - and that is exactly why a
            match resting on it alone drops to the class "common element", no matter how high the
            raw score was.
          </figcaption>
        </figure>
      ) : (
        <p className="text-sm text-muted">
          The commonality filter has not yet reported in how many works of the corpus this pattern
          occurs.
        </p>
      )}
    </section>
  );
}

export default SieveField;
