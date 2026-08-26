"use client";

/**
 * The side map of the run: eight steps from top to bottom, one screen, no log.
 *
 * The map shows **the whole structure at once**, so the viewer knows where we
 * are and how much is left. What is happening right now is told by the stage on
 * the right (`AnalysisStage`). Both views are fed by the same `CHAPTERS`
 * dictionary and the same grouping function from `components/pipeline/chapters`,
 * so the steps, their titles and their order cannot drift apart.
 *
 * A finished step gets a marker, the current one is highlighted, a future one is
 * dimmed.
 *
 * The map is **a remote control**: a click switches the stage to that step and
 * replays its animation from the beginning, including on a second click on the
 * same step. A future step is not clickable and looks not clickable, because
 * there is nothing to show - the animation of a step that has not happened would
 * be a prop. Once the analysis has finished, everything that went through the
 * stream is clickable, so any step can be revisited and discussed again.
 */

import type { Chapter } from "../pipeline/chapters";
import { CHAPTERS } from "../pipeline/chapters";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";

export interface StepMapProps {
  /** The chapters that really happened, in order of arrival. */
  chapters: readonly Chapter[];
  /** The step shown on the stage. */
  activeId: string | null;
  onSelect: (id: string) => void;
  /** Whether the run has reached its end - then the last step is done too. */
  finished: boolean;
  /**
   * A broken SSE stream. The map has to know about it, because otherwise the
   * last step glows lime forever, claiming that something is still being
   * computed.
   */
  streamError?: Error | null;
  className?: string;
}

export type StepState = "done" | "current" | "future";

export interface MapStep {
  id: string;
  title: string;
  sentence: string | null;
  state: StepState;
  /**
   * Whether this step carries the lime. At most one ever does (Global
   * Constraint 11).
   *
   * The accent is **narrower than the `current` state**: the state says where
   * the run stopped, the accent says that something is being computed there
   * right now. After the stream breaks, the first is still true, the second is
   * not.
   */
  accent: boolean;
}

/**
 * The state of each of the eight steps.
 *
 * A step is done once its events have arrived and the next one has started, or
 * the whole run has finished. Without that, the last step would hang as "in
 * progress" even when the analysis stopped long ago.
 *
 * The lime goes out entirely in three cases, because in each of them it would
 * lie: after the final verdict (the signal moves to the verdict card of screen
 * E3), after the stream breaks (nothing is being computed any more, and a
 * glowing step would say otherwise) and when the last step ended in failure (a
 * "something is happening here" signal on a step that failed is plainly
 * misleading).
 */
export function stepStates(
  chapters: readonly Chapter[],
  finished: boolean,
  interrupted = false,
): MapStep[] {
  const reached = new Set(chapters.map((chapter) => chapter.id));
  const lastChapter = chapters.length > 0 ? chapters[chapters.length - 1] : null;
  const lastId = lastChapter?.id ?? null;

  const lastRow =
    lastChapter && lastChapter.rows.length > 0
      ? lastChapter.rows[lastChapter.rows.length - 1]
      : null;
  const failure = lastRow?.status === "failed";

  return CHAPTERS.map((definition) => {
    let state: StepState = "future";
    if (reached.has(definition.id)) {
      state = definition.id === lastId && !finished ? "current" : "done";
    }
    return {
      id: definition.id,
      title: definition.title,
      sentence: definition.sentence,
      state,
      accent: state === "current" && !interrupted && !failure,
    };
  });
}

const MARKER: Record<StepState, string> = {
  done: "+",
  current: ">",
  future: "-",
};

export function StepMap({
  chapters,
  activeId,
  onSelect,
  finished,
  streamError = null,
  className = "",
}: StepMapProps) {
  const steps = stepStates(chapters, finished, streamError !== null);

  return (
    <ol className={`flex w-full min-w-0 flex-col gap-1 ${className}`}>
      {steps.map((step, index) => {
        const selected = step.id === activeId;
        const available = step.state !== "future";

        return (
          <li key={step.id} className="min-w-0">
            <button
              type="button"
              data-testid="map-step"
              data-step={step.id}
              data-state={step.state}
              data-accent={step.accent ? "true" : "false"}
              data-selected={selected ? "true" : "false"}
              aria-current={selected ? "step" : undefined}
              aria-disabled={!available}
              disabled={!available}
              title={available ? step.sentence ?? step.title : "This step has not happened yet"}
              onClick={() => onSelect(step.id)}
              className={`flex w-full min-w-0 items-baseline gap-3 rounded-inner border px-3 py-2 text-left transition-colors ${
                selected
                  ? "border-text bg-surface"
                  : available
                    ? "border-transparent hover:border-muted/40 hover:bg-surface/60"
                    : "border-transparent"
              } ${
                step.state === "future"
                  ? "cursor-not-allowed text-muted/40 opacity-60"
                  : step.accent
                    ? "cursor-pointer text-accent"
                    : "cursor-pointer text-text"
              }`}
            >
              <span className={`${TECHNICAL_VALUE_CLASS} shrink-0 text-xs opacity-70`}>
                {MARKER[step.state]}
              </span>
              <span className={`${TECHNICAL_VALUE_CLASS} shrink-0 text-xs opacity-50`}>
                {index + 1}
              </span>
              <span className={`${MICRO_LABEL_CLASS} min-w-0 truncate`}>{step.title}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export default StepMap;
