"use client";

/**
 * The application shell: one screen, two columns, no page scrolling.
 *
 * The page is **a layout and a remote control**, not a screen. It holds the
 * state that concerns the whole (which job, which step is being discussed),
 * splits it across three views and puts them in frame. Every view lives in its
 * own file and is responsible for what is inside it:
 *
 * - `EntryScreen` - the entry, the address field filling the frame;
 * - `AnalysisView` - the stage, one analysis step in frame;
 * - `ResultView` - the result, the cover, the verdict card and the tabs.
 *
 * The layout follows directly from how the show looks. The viewer has to see two
 * things at all times: **where we are in the whole process** and **what is
 * happening right now**. Hence the split:
 *
 * - **left, narrow** - the map of the eight steps. Finished ones have a marker,
 *   the current one is highlighted, future ones are dimmed. This is a structure,
 *   not a log, so it does not grow downwards and needs no scrolling.
 * - **right, wide** - the stage or the result, one at a time.
 *
 * **The result view is mounted from the first verdict onwards and never
 * disappears.** It is hidden by a class rather than unmounted - card E3 is what
 * remembers where the verdict was lifted from and to (section 12), and
 * unmounting would erase that trace along with the whole level 1 versus level 2
 * narrative.
 *
 * No element may push the page sideways: the container has `overflow-hidden`,
 * every column `min-w-0`, long addresses are wrapped or truncated, and
 * visualizations wider than the frame get their own container with horizontal
 * scrolling.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import AnalysisView from "../components/app/AnalysisView";
import EntryScreen from "../components/app/EntryScreen";
import ResultView from "../components/app/ResultView";
import ScreenFrame from "../components/app/ScreenFrame";
import StepMap from "../components/app/StepMap";
import { candidateResults, collectEnvelopes } from "../components/app/envelopes";
import useAnalysis from "../components/app/useAnalysis";
import { groupIntoChapters, collapseToRows } from "../components/pipeline/chapters";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../lib/theme";

/** The frame height without the brand bar from `app/layout.tsx`. */
const FRAME_HEIGHT = "h-[calc(100dvh-5rem)] max-h-[calc(100dvh-5rem)]";

export default function Page() {
  const analysis = useAnalysis();
  const [stepId, setStepId] = useState<string | null>(null);
  /**
   * The replay counter. It grows on every step selection and is part of the
   * visualization key, so clicking the same step a second time **replays the
   * animation from the beginning** instead of doing nothing. Without it the
   * remote control would only work on a change of step, and the owner discusses
   * the same step several times.
   */
  const [replayKey, setReplayKey] = useState(0);

  const result = analysis.result;
  const ranking = useMemo(() => result?.ranking ?? [], [result]);
  const best = ranking.find((entry) => entry.rank === 1) ?? ranking[0] ?? null;

  const envelopes = useMemo(() => collectEnvelopes(analysis.events), [analysis.events]);
  const bestResults = useMemo(
    () => candidateResults(envelopes, best?.candidate.id),
    [envelopes, best],
  );

  // The chapters are computed from the same dictionary the stage uses, so the
  // steps of the map and the steps of the show cannot drift apart.
  const chapters = useMemo(
    () => groupIntoChapters(collapseToRows(analysis.events)),
    [analysis.events],
  );
  const lastChapter = chapters.length > 0 ? chapters[chapters.length - 1] : null;
  const activeChapter = chapters.find((chapter) => chapter.id === stepId) ?? lastChapter;

  /**
   * The step map is **a remote control for the stage**, not a progress indicator.
   *
   * Selecting a step switches the stage and replays its animation from the
   * beginning, including when it is the same step as before. A selection also
   * **stops** the automatic following of the stream: if somebody is discussing
   * step two, a new event has no right to throw them onto step six mid-sentence.
   */
  const selectStep = useCallback((id: string) => {
    setStepId(id);
    setReplayKey((previous) => previous + 1);
  }, []);

  const queryTitle = analysis.selection?.url ?? "Material examined";

  const resultReady = best !== null && analysis.finished;
  const showsResult = resultReady && stepId === null;

  /*
    The final verdict walks onto the stage by itself, because with no step
    selected `showsResult` becomes true. We do not clear the selection here: if
    somebody is discussing step three when the final verdict arrives, pulling the
    stage away mid-sentence is exactly what the owner complained about. Going
    back to the result has its own button and the right arrow from the last step.
  */

  useEffect(() => {
    setStepId(null);
    setReplayKey(0);
  }, [analysis.jobId]);

  /**
   * The left and right arrows walk through the steps that **have already
   * happened**.
   *
   * On stage a clicker or a keyboard is often easier than aiming a mouse at a
   * narrow bar. The right arrow from the last step returns to the result,
   * because that is the natural end of the story.
   */
  useEffect(() => {
    if (analysis.jobId === null || typeof window === "undefined") return;
    const available = chapters.map((chapter) => chapter.id);
    if (available.length === 0) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;

      const current = stepId ?? available[available.length - 1];
      const index = available.indexOf(current);
      if (index < 0) return;

      event.preventDefault();

      if (event.key === "ArrowRight") {
        if (index === available.length - 1) {
          if (resultReady) setStepId(null);
          return;
        }
        selectStep(available[index + 1]);
        return;
      }

      if (index > 0) selectStep(available[index - 1]);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [analysis.jobId, chapters, stepId, resultReady, selectStep]);

  if (analysis.jobId === null) {
    return (
      <EntryScreen
        className={FRAME_HEIGHT}
        onSubmit={analysis.start}
        busy={analysis.submitting}
        error={analysis.error}
      />
    );
  }

  return (
    <div className={`flex w-full max-w-full gap-6 overflow-hidden ${FRAME_HEIGHT}`}>
      <aside className="flex w-60 min-w-0 shrink-0 flex-col gap-4 overflow-hidden border-r border-muted/20 pr-4 xl:w-72">
        <ScreenFrame screen="E1 INPUT">
          <div className="flex min-w-0 flex-col gap-2">
            <span className={`text-muted ${MICRO_LABEL_CLASS}`}>Material examined</span>
            <span
              title={queryTitle}
              className={`truncate text-sm text-text ${TECHNICAL_VALUE_CLASS}`}
            >
              {queryTitle}
            </span>
            <button
              type="button"
              onClick={analysis.reset}
              className={`mt-1 self-start rounded-full border border-muted/40 px-4 py-1.5 text-text ${MICRO_LABEL_CLASS}`}
            >
              New material
            </button>
          </div>
        </ScreenFrame>

        <ScreenFrame screen="E2 PIPELINE" className="min-h-0">
          <StepMap
            chapters={chapters}
            activeId={activeChapter?.id ?? null}
            onSelect={selectStep}
            finished={analysis.finished}
            streamError={analysis.streamError}
          />
        </ScreenFrame>

        {analysis.error ? (
          <p role="alert" className="text-xs text-muted">
            {analysis.error}
          </p>
        ) : null}
      </aside>

      {/* Both views are mounted at once and switched by a class, not by unmounting. */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <AnalysisView
          className={showsResult ? "hidden" : ""}
          chapter={activeChapter}
          events={analysis.events}
          entry={best}
          results={bestResults}
          queryDuration={result?.query.duration ?? null}
          finished={analysis.finished}
          streamError={analysis.streamError}
          replayKey={replayKey}
          canReturn={resultReady}
          onReturn={() => setStepId(null)}
        />

        <ResultView
          className={showsResult ? "" : "hidden"}
          jobId={analysis.jobId}
          result={result}
          best={best}
          envelopes={envelopes}
          selection={analysis.selection}
          queryTitle={queryTitle}
          generatedAt={analysis.startedAt}
        />
      </main>
    </div>
  );
}
