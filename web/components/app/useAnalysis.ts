"use client";

/**
 * The screens tied together into a single analysis job.
 *
 * The order from section 4: choosing the material submits the job, the `job_id`
 * opens the stream, the stream lights up the successive stages of screen E2, and
 * every `verdict` event is a signal that a newer version of the result is
 * waiting at `/result`.
 *
 * The verdict arrives **twice** and the class can change in between (section
 * 12), which is why the result is one piece of state replaced in place here.
 * Screen E3 receives new data for the same, still mounted component and shows
 * for itself where the verdict was lifted from and to. Unmounting the card
 * between one verdict and the other would erase that trace.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { ResultNotReadyError, analyze, getResult } from "../../lib/api";
import type { AnalyzeResult, StreamEvent } from "../../lib/contracts";
import type { InputSelection } from "../input/UrlInput";
import useJobStream from "../pipeline/useJobStream";

export interface AnalysisState {
  /** The material chosen on screen E1. */
  selection: InputSelection | null;
  jobId: string | null;
  /** The full stream history - screen E2 collapses it on its own. */
  events: StreamEvent[];
  /** The latest state of the result: partial after level 1, final after level 2. */
  result: AnalyzeResult | null;
  /** Whether `verdict.final` has already arrived. */
  finished: boolean;
  /** The job is being submitted - the input field is locked. */
  submitting: boolean;
  /** The timestamp of the submission. Report E10 has to be reproducible. */
  startedAt: string | null;
  error: string | null;
  /**
   * The broken stream as an object, not as a sentence. The step map has to get
   * it, because otherwise the last step glows lime forever, claiming that
   * something is still being computed (Global Constraint 11).
   */
  streamError: Error | null;
  start: (selection: InputSelection) => void;
  reset: () => void;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function useAnalysis(): AnalysisState {
  const [selection, setSelection] = useState<InputSelection | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const stream = useJobStream(jobId);

  /**
   * The count of verdicts, not the verdict itself: this is the only quantity
   * that is meant to change exactly twice in the whole run. An effect depending
   * on the content of the verdict would fetch the result also when the same
   * verdict arrived again after the stream resumed.
   */
  const verdictCount = useMemo(
    () => stream.events.filter((event) => event.stage === "verdict").length,
    [stream.events],
  );

  useEffect(() => {
    if (jobId === null || verdictCount === 0) return;

    let active = true;
    const controller = new AbortController();

    getResult(jobId, controller.signal)
      .then((payload) => {
        if (active) setResult(payload);
      })
      .catch((error: unknown) => {
        if (!active) return;
        // 202 means: the job is alive but there is no result yet. The next
        // verdict will try again, and the previous state stays on screen.
        if (error instanceof ResultNotReadyError) return;
        setSubmitError(message(error));
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [jobId, verdictCount]);

  const start = useCallback((chosen: InputSelection) => {
    setSelection(chosen);
    setJobId(null);
    setResult(null);
    setSubmitError(null);
    setSubmitting(true);

    void analyze(chosen.url, chosen.candidateSet)
      .then((id) => {
        setStartedAt(new Date().toISOString());
        setJobId(id);
      })
      .catch((error: unknown) => setSubmitError(message(error)))
      .finally(() => setSubmitting(false));
  }, []);

  const reset = useCallback(() => {
    setSelection(null);
    setJobId(null);
    setResult(null);
    setStartedAt(null);
    setSubmitError(null);
  }, []);

  return {
    selection,
    jobId,
    events: stream.events,
    result,
    finished: stream.finished,
    submitting,
    startedAt,
    error: submitError ?? (stream.error ? stream.error.message : null),
    streamError: stream.error,
    start,
    reset,
  };
}

export default useAnalysis;
