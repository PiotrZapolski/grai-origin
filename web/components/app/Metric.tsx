"use client";

/**
 * The simplest thing that moves and shows a real number.
 *
 * For steps that have no dedicated visualization in `components/viz/`, the stage
 * needs something in motion - but the motion must not be decoration. The counter
 * runs up **to the value measured in this step**, and the bar grows to the share
 * that really came out. There is no default value here: a field without a
 * measurement simply does not reach the list.
 */

import { useEffect, useState } from "react";

import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";

export interface Measurement {
  label: string;
  /** The measured value. The counter runs up to it from zero. */
  value: number;
  /** A suffix after the number, e.g. "%" or "s". */
  unit?: string;
  /** How many decimal places to show. */
  decimals?: number;
  /** A 0..1 share for the bar. Without it there is no bar. */
  share?: number | null;
  /** A sentence under the number. */
  note?: string | null;
}

const DURATION_MS = 900;

/** Easing of the run-up: fast at the start, soft at the end. */
function ease(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

function useCountUp(target: number, key: string): number {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined" || typeof requestAnimationFrame !== "function") {
      setValue(target);
      return;
    }
    // A viewer who asked the system to reduce motion gets the number at once.
    const reducedMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) {
      setValue(target);
      return;
    }

    let frame = 0;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION_MS);
      setValue(target * ease(t));
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, key]);

  return value;
}

function Row({ measurement }: { measurement: Measurement }) {
  const current = useCountUp(measurement.value, measurement.label);
  const share =
    typeof measurement.share === "number" ? Math.min(1, Math.max(0, measurement.share)) : null;
  const width =
    share === null ? 0 : share * (measurement.value === 0 ? 1 : current / measurement.value);

  return (
    <li
      data-testid="measurement"
      data-label={measurement.label}
      className="flex min-w-0 flex-col gap-2"
    >
      <span className={`${MICRO_LABEL_CLASS} text-muted`}>{measurement.label}</span>
      <span className={`text-4xl text-text ${TECHNICAL_VALUE_CLASS}`}>
        {current.toFixed(measurement.decimals ?? 0)}
        {measurement.unit ? (
          <span className="ml-1 text-2xl text-muted">{measurement.unit}</span>
        ) : null}
      </span>
      {share !== null ? (
        /*
          The bar is a magnitude, not a signal, so it is not lime (Global
          Constraint 11). Two set sizes on the commonality step used to draw two
          lime bars side by side; by the time the verdict arrived the accent had
          been spent on decoration and meant nothing.
        */
        <span aria-hidden="true" className="block h-1.5 w-full max-w-md bg-muted/20">
          <span
            className="block h-full bg-text/60"
            style={{ width: `${Math.min(100, width * 100)}%` }}
          />
        </span>
      ) : null}
      {measurement.note ? (
        <span className="text-xs text-muted">{measurement.note}</span>
      ) : null}
    </li>
  );
}

export interface MetricProps {
  measurements: readonly Measurement[];
  /** A sentence instead of numbers, when the step has measured nothing yet. */
  fallback?: string;
  className?: string;
}

export function Metric({ measurements, fallback, className = "" }: MetricProps) {
  if (measurements.length === 0) {
    return (
      <p className={`text-sm text-muted ${className}`}>
        {fallback ?? "This step has not returned a single measured value yet."}
      </p>
    );
  }

  return (
    <ul className={`flex flex-wrap gap-x-12 gap-y-6 ${className}`}>
      {measurements.map((measurement) => (
        <Row key={measurement.label} measurement={measurement} />
      ))}
    </ul>
  );
}

export default Metric;
