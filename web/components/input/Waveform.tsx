import { useMemo } from "react";

import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";

export interface WaveformProps {
  /** Where the material comes from: an address or the name of a dropped file. */
  source?: string | null;
  /** Peaks in the 0-1 range. `null` means "not measured yet". */
  peaks?: readonly number[] | null;
  /** The target number of bars, when there are more samples than room. */
  bars?: number;
  /** The caption above the waveform. */
  label?: string;
  className?: string;
}

const HEIGHT = 100;
const DEFAULT_BARS = 120;

/** Resampling down to a number of bars that fits on the screen. */
function toBars(peaks: readonly number[], count: number): number[] {
  if (peaks.length <= count) return [...peaks];
  const perBar = peaks.length / count;
  const result: number[] = [];
  for (let i = 0; i < count; i += 1) {
    const start = Math.floor(i * perBar);
    const end = Math.min(peaks.length, Math.floor((i + 1) * perBar));
    let peak = 0;
    for (let j = start; j < end; j += 1) {
      if (peaks[j] > peak) peak = peaks[j];
    }
    result.push(peak);
  }
  return result;
}

/**
 * The waveform of the input material (screen E1).
 *
 * It appears **the moment the material is chosen, before the analysis** - that
 * is the whole difference between this screen and an empty spinner (section
 * 13.2).
 *
 * Without samples the component **does not draw a shape**. Generating a
 * plausible looking wave out of an address alone would be the cheapest prop in
 * a product whose entire pitch is that every value on screen comes from a
 * measurement (section 13.2 for E5). Instead you see a frame, the name of the
 * material and the state written out plainly.
 *
 * The waveform is white, never lime: lime belongs to signals, not to ornament on
 * the entry screen (section 13.1).
 */
export function Waveform({
  source = null,
  peaks = null,
  bars = DEFAULT_BARS,
  label = "Material to examine",
  className = "",
}: WaveformProps) {
  const provisional = !peaks || peaks.length === 0;
  const barValues = useMemo(() => (provisional ? [] : toBars(peaks as number[], bars)), [
    peaks,
    bars,
    provisional,
  ]);

  const width = Math.max(barValues.length, 1) * 3;
  const ticks = Array.from({ length: 48 }, (_, i) => i);

  return (
    <figure
      data-waveform="true"
      data-source={source ?? ""}
      data-provisional={provisional ? "true" : "false"}
      className={`flex flex-col gap-3 rounded-card border border-muted/20 bg-bg/40 p-4 ${className}`}
    >
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <span className={`${MICRO_LABEL_CLASS} text-muted`}>{label}</span>
        {source ? (
          <span
            className={`max-w-full truncate text-xs text-muted ${TECHNICAL_VALUE_CLASS}`}
            title={source}
          >
            {source}
          </span>
        ) : null}
      </figcaption>

      {provisional ? (
        <>
          <svg
            role="img"
            aria-label="Waveform not measured yet"
            viewBox={`0 0 ${ticks.length * 3} ${HEIGHT}`}
            preserveAspectRatio="none"
            className="h-24 w-full text-muted"
          >
            {ticks.map((i) => (
              <rect
                key={i}
                data-placeholder-tick="true"
                x={i * 3}
                y={HEIGHT / 2 - 1}
                width={1.6}
                height={2}
                fill="currentColor"
                opacity={0.45}
              />
            ))}
          </svg>
          <p className="text-xs text-muted">
            Placeholder shape - it does not come from a measurement. The real waveform
            appears once the material has been read.
          </p>
        </>
      ) : (
        <svg
          role="img"
          aria-label="Waveform of the input material"
          viewBox={`0 0 ${width} ${HEIGHT}`}
          preserveAspectRatio="none"
          className="h-24 w-full text-text"
        >
          {barValues.map((peak, i) => {
            const barHeight = Math.max(2, peak * HEIGHT);
            return (
              <rect
                key={i}
                data-bar="true"
                x={i * 3}
                y={(HEIGHT - barHeight) / 2}
                width={1.6}
                height={barHeight}
                fill="currentColor"
                opacity={0.85}
              />
            );
          })}
        </svg>
      )}
    </figure>
  );
}

export default Waveform;
