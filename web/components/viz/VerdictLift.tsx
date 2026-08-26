"use client";

/**
 * The lift of the verdict from preliminary to final (section 12).
 *
 * The verdict arrives **twice** and the class can change in between. This
 * component exists so that the change reads as "the system changed its mind on
 * the strength of new evidence" rather than as a blink of the screen: the old
 * value stays on the scale as an empty marker, the new one travels to its place,
 * and underneath stands the list of detectors that arrived **between** one
 * verdict and the other.
 *
 * All three ingredients are data off the wire: the mock and the engine both put
 * `previous_class` and `previous_probability` into the `detail` of the level 2
 * verdict, and the list of detectors is simply what arrived in the meantime.
 * Nothing here is reconstructed after the fact.
 *
 * Motion does not delay access to information: both numbers and both classes
 * stand in the document from the first frame, only the position of the marker is
 * animated.
 */

import { useMemo } from "react";

import type { ProbabilityStatus, StreamEvent, VerdictClass } from "../../lib/contracts";
import { isVerdictClass } from "../../lib/contracts";
import { formatPercent } from "../../lib/format";
import {
  MICRO_LABEL_CLASS,
  SIGNAL_LABEL_CLASS,
  TECHNICAL_VALUE_CLASS,
  VERDICT_LABELS,
  isAccentClass,
  theme,
} from "../../lib/theme";
import { useProgress, ease } from "./motion";

export interface VerdictLiftProps {
  currentClass: VerdictClass;
  currentProbability: number | null;
  probabilityStatus: ProbabilityStatus;
  /** The class before the lift. `null` means: this is the first verdict. */
  previousClass?: VerdictClass | null;
  previousProbability?: number | null;
  /** What arrived between one verdict and the other. Readable detector names. */
  changedBy?: readonly string[];
  className?: string;
}

const DURATION_MS = 1300;

/** Readable detector names for the "what changed the answer" sentence. */
const STAGE_NAMES: Record<string, string> = {
  fingerprint: "acoustic fingerprint",
  harmonic: "harmony",
  transcript: "transcript",
  separation: "source separation",
  melodic: "melody",
  commonality: "commonality filter",
  shortlist: "shortlist",
};

/**
 * The stages that arrived **between** the preliminary and the final verdict.
 *
 * This is the answer to "why did the system change its mind", derived directly
 * from the order of the events. We take finished steps only: a step in progress
 * has contributed nothing yet, so it has no right to stand in the reasoning.
 */
export function changesBetweenVerdicts(events: readonly StreamEvent[]): string[] {
  const preliminary = events.findIndex(
    (event) => event.stage === "verdict" && event.status === "partial",
  );
  const final = events.findIndex(
    (event) => event.stage === "verdict" && event.status === "final",
  );
  if (preliminary < 0 || final < 0 || final <= preliminary) return [];

  const names: string[] = [];
  for (const event of events.slice(preliminary + 1, final)) {
    if (event.stage === "verdict") continue;
    if (event.status === "running") continue;
    const name = STAGE_NAMES[event.stage] ?? event.stage;
    if (!names.includes(name)) names.push(name);
  }
  return names;
}

/** The verdict class from the `detail` of an event, or `null` when it is not there. */
export function verdictClassFromDetail(
  detail: Record<string, unknown>,
  key: string,
): VerdictClass | null {
  const value = detail[key];
  return isVerdictClass(value) ? value : null;
}

function percent(value: number | null): string {
  if (value === null) return "none";
  return formatPercent(value);
}

export function VerdictLift({
  currentClass,
  currentProbability,
  probabilityStatus,
  previousClass = null,
  previousProbability = null,
  changedBy = [],
  className = "",
}: VerdictLiftProps) {
  const lifted = previousClass !== null || previousProbability !== null;

  const marker = `${previousClass ?? "none"}:${previousProbability ?? "none"}:${currentClass}:${currentProbability ?? "none"}`;
  // The motion covers the first verdict too: the badge slides in and the number
  // runs up.
  const progress = useProgress({ duration: DURATION_MS, key: marker });
  const transition = ease(progress);

  // Without a lift the number starts from zero, with one from the old value.
  const fromOld = previousProbability ?? 0;
  const toNew = currentProbability ?? 0;
  const position = fromOld + (toNew - fromOld) * transition;

  const accent = isAccentClass(currentClass);
  const changes = useMemo(() => changedBy.filter((name) => name.length > 0), [changedBy]);
  const classChanged = previousClass !== null && previousClass !== currentClass;

  return (
    <section
      data-testid="verdict-lift"
      data-lifted={lifted ? "true" : "false"}
      data-class={currentClass}
      data-previous-class={previousClass ?? ""}
      className={`origin-card flex flex-col gap-5 p-6 ${className}`}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className={lifted ? SIGNAL_LABEL_CLASS : `${MICRO_LABEL_CLASS} text-muted`}>
          {lifted ? "VERDICT LIFTED" : "PRELIMINARY VERDICT"}
        </h3>
        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
          {probabilityStatus === "calibrated" ? "CALIBRATED" : "RAW, NOT CALIBRATED"}
        </p>
      </header>

      {/*
        The confidence number runs up to its target value, but it **never hides
        information**: the full value stands in parallel in the caption of the
        scale below and is legible there from the first frame. A missing number
        does not turn into zero or a dash - the panel writes outright that there
        is none.
      */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          data-testid="confidence-number"
          className={`text-6xl leading-none ${TECHNICAL_VALUE_CLASS} ${
            accent ? "text-accent" : "text-text"
          }`}
        >
          {currentProbability === null ? "no number" : formatPercent(position)}
        </span>
        <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
          {probabilityStatus === "calibrated"
            ? "calibrated probability"
            : "raw score, not calibrated"}
        </span>
      </div>

      {/* The class: the old one struck through, the new one whole. A change of class is content, not ornament. */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
        {classChanged && previousClass ? (
          <>
            <span
              data-testid="previous-class"
              className={`text-muted line-through ${MICRO_LABEL_CLASS}`}
            >
              {VERDICT_LABELS[previousClass]}
            </span>
            <span aria-hidden="true" className={`text-muted ${MICRO_LABEL_CLASS}`}>
              &rarr;
            </span>
          </>
        ) : null}
        {/* The class badge slides in from the side: a ruling is meant to be an event. */}
        <span
          data-testid="current-class"
          className={`rounded-inner border px-3 py-1.5 text-lg ${
            accent ? "text-accent" : "text-text"
          } ${MICRO_LABEL_CLASS}`}
          style={{
            borderColor: accent ? `${theme.accent}80` : `${theme.muted}33`,
            backgroundColor: accent ? `${theme.accent}14` : "transparent",
            opacity: 0.25 + 0.75 * transition,
            transform: `translateX(${((1 - transition) * -10).toFixed(1)}px)`,
          }}
        >
          {VERDICT_LABELS[currentClass]}
        </span>
      </div>

      {/* The probability scale. The old marker stays, the new one travels to its place. */}
      <figure className="flex flex-col gap-2">
        <div
          role="img"
          aria-label={
            lifted
              ? `Probability lifted from ${percent(previousProbability)} to ${percent(currentProbability)}`
              : `Probability ${percent(currentProbability)}`
          }
          className="relative h-8 w-full rounded-inner border border-muted/20 bg-bg"
        >
          {/* The distance travelled: from the old value to the current marker position. */}
          {lifted && previousProbability !== null ? (
            <span
              data-testid="lift-segment"
              className="absolute inset-y-0 bg-text/10"
              style={{
                left: `${Math.min(previousProbability, position) * 100}%`,
                width: `${Math.abs(position - previousProbability) * 100}%`,
              }}
            />
          ) : null}

          {previousProbability !== null ? (
            <span
              data-testid="previous-marker"
              title={`preliminary verdict: ${percent(previousProbability)}`}
              className="absolute inset-y-1 w-px bg-muted"
              style={{ left: `${previousProbability * 100}%` }}
            />
          ) : null}

          {currentProbability !== null ? (
            <span
              data-testid="current-marker"
              className="absolute inset-y-0 w-0.5"
              style={{
                left: `${position * 100}%`,
                backgroundColor: accent ? theme.accent : theme.text,
              }}
            />
          ) : null}
        </div>

        <figcaption className="flex flex-wrap items-baseline justify-between gap-3">
          <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
            {previousProbability === null ? (
              "NO EARLIER VALUE"
            ) : (
              <>
                FROM{" "}
                <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
                  {percent(previousProbability)}
                </span>
              </>
            )}
          </span>
          <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
            TO{" "}
            <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
              {percent(currentProbability)}
            </span>
          </span>
        </figcaption>
      </figure>

      {lifted ? (
        <p data-testid="lift-reason" className="text-sm text-muted">
          {changes.length > 0
            ? `The answer was changed by the evidence that arrived in between: ${changes.join(", ")}.`
            : "No finished step arrived between one verdict and the other, so the change is carried by the level 2 numbers alone."}
        </p>
      ) : (
        <p className="text-sm text-muted">
          This is the answer after level 1. Level 2 may lift it or change the class.
        </p>
      )}
    </section>
  );
}

export default VerdictLift;
