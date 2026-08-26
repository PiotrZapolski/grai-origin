"use client";

import { useEffect, useState } from "react";

import { streamJob } from "../../lib/api";
import type { StreamEvent } from "../../lib/contracts";

export interface JobStreamState {
  events: StreamEvent[];
  /** The last verdict that arrived on the stream - preliminary or final. */
  latestVerdict: StreamEvent | null;
  /** Whether `verdict.final` has already arrived. */
  finished: boolean;
  error: Error | null;
}

/**
 * The event stream of one job as React state - the feed for screen E2.
 *
 * Events are **appended, never overwritten**: collapsing them into rows is done
 * by `collapseToRows` from `components/pipeline/chapters`, and screens E3-E5
 * need that same history to lift the verdict without a reload (section 12).
 *
 * A `jobId` equal to `null` means "there is nothing to listen to" and is a valid
 * state: the entry screen lives before any job exists.
 */
export function useJobStream(jobId: string | null): JobStreamState {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    setEvents([]);
    setError(null);
    if (!jobId) return;

    let current = true;
    const handle = streamJob(
      jobId,
      (event) => {
        if (current) setEvents((previous) => [...previous, event]);
      },
      (failure) => {
        // The stream also ends normally, after the last event. We do not show
        // the error once the final verdict has arrived - see `finished`.
        if (current) setError(failure);
      },
    );

    return () => {
      current = false;
      handle.close();
    };
  }, [jobId]);

  const verdicts = events.filter((event) => event.stage === "verdict");
  const finished = verdicts.some((event) => event.status === "final");

  return {
    events,
    latestVerdict: verdicts.length > 0 ? verdicts[verdicts.length - 1] : null,
    finished,
    error: finished ? null : error,
  };
}

export default useJobStream;
