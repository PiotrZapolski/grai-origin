"use client";

/**
 * The analysis view: the stage with one step in frame plus the way back to the
 * result.
 *
 * The view is **hidden by a class, not unmounted**, because the visualizations
 * animate on mount. Unmounting the stage on every trip to the result and back
 * would replay all of that motion on every single click.
 */

import type { RankingEntry, StreamEvent } from "../../lib/contracts";
import { MICRO_LABEL_CLASS } from "../../lib/theme";
import type { Chapter } from "../pipeline/chapters";
import AnalysisStage from "./AnalysisStage";
import type { CandidateResults } from "./envelopes";

export interface AnalysisViewProps {
  /** The chapter shown in frame. `null` means: nothing has arrived yet. */
  chapter: Chapter | null;
  events: readonly StreamEvent[];
  /** The first entry of the ranking, if there is one yet. */
  entry: RankingEntry | null;
  results: CandidateResults;
  queryDuration: number | null;
  /** Whether `verdict.final` has already arrived. */
  finished: boolean;
  /** A broken SSE stream. The stage stops announcing work in progress. */
  streamError: Error | null;
  /** Changing this value replays the step animation from the beginning. */
  replayKey: number;
  /**
   * Whether there is anywhere to go back to. The button appears only with the
   * final verdict, because before that the result does not exist.
   */
  canReturn: boolean;
  onReturn: () => void;
  className?: string;
}

export function AnalysisView({
  chapter,
  events,
  entry,
  results,
  queryDuration,
  finished,
  streamError,
  replayKey,
  canReturn,
  onReturn,
  className = "",
}: AnalysisViewProps) {
  return (
    <div className={`flex min-h-0 min-w-0 flex-1 flex-col gap-4 ${className}`}>
      <AnalysisStage
        chapter={chapter}
        events={events}
        entry={entry}
        results={results}
        queryDuration={queryDuration}
        finished={finished}
        streamError={streamError}
        replayKey={replayKey}
      />

      {canReturn ? (
        <button
          type="button"
          onClick={onReturn}
          className={`self-start rounded-full border border-muted/40 px-5 py-2 text-text ${MICRO_LABEL_CLASS}`}
        >
          Back to the result
        </button>
      ) : null}
    </div>
  );
}

export default AnalysisView;
