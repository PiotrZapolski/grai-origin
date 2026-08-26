"use client";

/**
 * The run chronograph: when each event really arrived.
 *
 * The only quantity this component draws is **the arrival time of an event
 * measured in the browser**. There is not a single number from the server here
 * and not a single invented one: a mark is placed at the moment `useJobStream`
 * appended the event to the list.
 *
 * That is why the component has **its own measurement failure state**. A screen
 * opened on a finished result receives the full set of events in one render, so
 * every mark would fall in the same millisecond and the chart would show a run
 * lasting zero seconds. Rather than draw such a lie, the chronograph says
 * outright that the events were already in memory and there is nothing to
 * measure.
 *
 * An honest note about the show: the delay between mock events is set by
 * `ORIGIN_MOCK_DELAY`, so in mock mode this chart measures the pace of the
 * stream, not the cost of computing. The measurement is real, its subject is
 * another.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import type { PipelineEvent } from "../pipeline/stages";
import { stageLabel } from "../pipeline/stages";

export interface StreamChronographProps {
  events: readonly PipelineEvent[];
  className?: string;
}

/** Below this spread we assume the events were already in memory. */
const MIN_SPREAD_MS = 150;

export interface StreamClock {
  /** The arrival time of every event in milliseconds since the first one. */
  times: number[];
  /** Whether the measurement concerns the run at all, rather than a single render. */
  reliable: boolean;
}

/**
 * The arrival time of every event, measured on the browser side.
 *
 * A new list shorter than the previous one means a new job, so the clock starts
 * from zero. Without that the second run would inherit the time axis of the
 * first.
 */
export function useEventClock(events: readonly PipelineEvent[]): StreamClock {
  const marks = useRef<number[]>([]);
  const [, setVersion] = useState(0);

  useEffect(() => {
    if (events.length < marks.current.length) marks.current = [];
    if (events.length === marks.current.length) return;

    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    while (marks.current.length < events.length) marks.current.push(now);
    setVersion((version) => version + 1);
  }, [events]);

  const raw = marks.current;
  const base = raw.length > 0 ? raw[0] : 0;
  const times = raw.slice(0, events.length).map((time) => time - base);
  const spread = times.length > 0 ? times[times.length - 1] : 0;

  return { times, reliable: times.length >= 3 && spread >= MIN_SPREAD_MS };
}

export interface StageLane {
  key: string;
  stage: string;
  level: number;
  /** Milliseconds since the first event. */
  from: number;
  to: number;
  /** Whether the lane ends in a state that is not plain success. */
  status: string;
}

/**
 * Stage lanes from the list of events and their arrival times.
 *
 * A lane runs from the first to the last event of a given stage at a given
 * level. A stage that arrived once gets a lane of zero length - and that is the
 * truth about it, not missing data: the stream did not say when it began.
 */
export function stageLanes(
  events: readonly PipelineEvent[],
  times: readonly number[],
): StageLane[] {
  const byKey = new Map<string, StageLane>();
  const order: string[] = [];

  events.forEach((event, index) => {
    const time = times[index];
    if (typeof time !== "number") return;
    const key = `${event.level}:${event.stage}`;
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, {
        key,
        stage: event.stage,
        level: event.level,
        from: time,
        to: time,
        status: String(event.status),
      });
      order.push(key);
      return;
    }
    existing.to = time;
    existing.status = String(event.status);
  });

  return order.map((key) => byKey.get(key) as StageLane);
}

export function StreamChronograph({ events, className = "" }: StreamChronographProps) {
  const clock = useEventClock(events);
  const lanes = useMemo(() => stageLanes(events, clock.times), [events, clock.times]);

  const total = clock.times.length > 0 ? clock.times[clock.times.length - 1] : 0;

  const header = (
    <header className="flex flex-wrap items-baseline justify-between gap-3">
      <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>RUN CHRONOGRAPH</h3>
      {clock.reliable ? (
        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
          TOTAL{" "}
          <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {(total / 1000).toFixed(2)} s
          </span>
        </p>
      ) : null}
    </header>
  );

  if (!clock.reliable) {
    return (
      <section
        data-testid="chronograph"
        data-measurement="none"
        className={`origin-card flex flex-col gap-3 p-6 ${className}`}
      >
        {header}
        <p className="text-sm text-muted">
          The events were already in memory when this view opened, so there is nothing to
          measure the run from. The chronograph draws only the arrival times of events
          measured live and does not reconstruct them after the fact.
        </p>
      </section>
    );
  }

  const toPercent = (ms: number) => (total === 0 ? 0 : (ms / total) * 100);

  return (
    <section
      data-testid="chronograph"
      data-measurement="live"
      data-lanes={lanes.length}
      className={`origin-card flex flex-col gap-4 p-6 ${className}`}
    >
      {header}

      <div className="flex flex-col gap-1">
        {lanes.map((lane) => {
          const left = toPercent(lane.from);
          const width = Math.max(1.2, toPercent(lane.to) - left);
          const signal = lane.status === "final" || lane.status === "gated";
          return (
            <div key={lane.key} className="flex items-center gap-3">
              <span
                className={`w-40 shrink-0 truncate text-muted ${MICRO_LABEL_CLASS}`}
                title={lane.stage}
              >
                {stageLabel(lane.stage)}
              </span>
              <div className="relative h-2.5 flex-1 rounded-full bg-muted/12">
                <span
                  data-lane={lane.stage}
                  data-status={lane.status}
                  className="absolute inset-y-0 rounded-full"
                  style={{
                    left: `${left}%`,
                    width: `${width}%`,
                    backgroundColor: signal ? theme.accent : theme.text,
                    opacity: signal ? 1 : 0.55,
                  }}
                />
              </div>
              <span className={`w-16 shrink-0 text-right text-muted text-xs ${TECHNICAL_VALUE_CLASS}`}>
                {(lane.from / 1000).toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-muted">
        The horizontal axis is the arrival time of the events measured in the browser, from
        the first to the last; the number on the right is the moment the stage started, in
        seconds. In mock mode this chart measures the pace of the stream, not the cost of
        computing - the measurement is real, its subject is another.
      </p>
    </section>
  );
}

export default StreamChronograph;
