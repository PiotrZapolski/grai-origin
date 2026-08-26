"use client";

/**
 * The analysis stage: one step in frame, large, with a visual element of its own.
 *
 * The division of roles against the map on the left is sharp: the map says
 * **where we are in the whole**, the stage says **what is happening right now**.
 * The stage therefore shows the title of the step, two sentences about what
 * technically happens here and what it makes possible, the numbers this step
 * really produced, and a visualization.
 *
 * **Every step has its own visual**, rather than one shared by all of them:
 *
 * | step | visual | data source |
 * |---|---|---|
 * | ingest | stream chronograph | event arrival times |
 * | fingerprint | offset histogram | envelope of detector A |
 * | harmonic | alignment matrix | envelope of detector B |
 * | commonality | counter and bar | shortlist and commonality filter |
 * | preliminary verdict | alignment ribbon | `alignment` of the first entry |
 * | lyrics | counter | envelope of detector D |
 * | melodic | counter | envelope of detector C |
 * | final verdict | verdict lift | both `verdict` events |
 *
 * Where there is no dedicated component, the simplest thing that moves and shows
 * a **real number from this step** stands instead. Nothing invented: a step with
 * no measurement gets a sentence, not a pretty shape.
 */

import type { RankingEntry, StreamEvent } from "../../lib/contracts";
import {
  HEADING_CLASS,
  MICRO_LABEL_CLASS,
  SIGNAL_LABEL_CLASS,
  TECHNICAL_VALUE_CLASS,
} from "../../lib/theme";
import type { Chapter } from "../pipeline/chapters";
import { describeStage } from "../pipeline/stages";
import {
  AlignmentMatrix,
  AlignmentRibbon,
  OffsetHistogram,
  StreamChronograph,
  VerdictLift,
} from "../viz";
import { verdictClassFromDetail, changesBetweenVerdicts } from "../viz/VerdictLift";
import type { CandidateResults } from "./envelopes";
import Metric, { type Measurement } from "./Metric";
import { stepDescription } from "./descriptions";

export interface AnalysisStageProps {
  /** The chapter shown in frame. `null` means: nothing has arrived yet. */
  chapter: Chapter | null;
  events: readonly StreamEvent[];
  /** The first entry of the ranking, if there is one yet. */
  entry: RankingEntry | null;
  results: CandidateResults;
  queryDuration: number | null;
  /**
   * Whether `verdict.final` has already arrived. After that nothing is being
   * computed any more, whatever step happens to be in frame.
   */
  finished?: boolean;
  /**
   * A broken SSE stream. The stage has to know about it for the same reason
   * `StepMap` does: without it the label beside the map keeps announcing work
   * that stopped.
   */
  streamError?: Error | null;
  /**
   * Changing this value **replays the animation from the beginning**.
   *
   * The visualizations animate on mount, so the only honest way to replay them
   * is to mount them anew. A React key does exactly that and requires no
   * reaching into anybody else's component.
   */
  replayKey?: number;
  className?: string;
}

/** A number from the `detail` of any row of the chapter. `null` when there is none. */
function numberFromRows(chapter: Chapter | null, key: string): number | null {
  for (const row of chapter?.rows ?? []) {
    const value = row.detail?.[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function verdicts(events: readonly StreamEvent[]): StreamEvent[] {
  return events.filter((event) => event.stage === "verdict");
}

/** A measurement reaches the list only when it has really been computed. */
function add(list: Measurement[], measurement: Measurement | null): void {
  if (measurement !== null) list.push(measurement);
}

function numberMeasurement(
  label: string,
  value: number | null | undefined,
  rest: Partial<Measurement> = {},
): Measurement | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return { label, value, ...rest };
}

function Visualization({
  chapter,
  events,
  entry,
  results,
  queryDuration,
}: Omit<AnalysisStageProps, "className" | "replayKey">) {
  const id = chapter?.id ?? null;

  if (id === "fingerprint") {
    return (
      <OffsetHistogram
        status={results.fingerprint?.status ?? entry?.evidence?.fingerprint?.status}
        reason={results.fingerprint?.reason ?? null}
        matchedHashes={results.fingerprint?.matched_hashes ?? null}
        peakRatio={results.fingerprint?.peak_ratio ?? null}
        repetitions={results.fingerprint?.repetitions ?? 0}
        offset={results.fingerprint?.offset ?? null}
      />
    );
  }

  if (id === "harmonic") {
    return (
      <AlignmentMatrix
        status={results.harmonic?.status ?? entry?.evidence?.harmonic?.status}
        reason={results.harmonic?.reason ?? null}
        path={results.harmonic?.alignment_path ?? []}
        qmax={results.harmonic?.qmax_score ?? null}
        transposition={results.harmonic?.transposition ?? null}
        tempoRatio={results.harmonic?.tempo_ratio ?? null}
        coverage={results.harmonic?.coverage ?? null}
        candidateName={entry?.candidate.name ?? null}
      />
    );
  }

  if (id === "commonality") {
    const measurements: Measurement[] = [];
    const before = numberFromRows(chapter, "from");
    const after = numberFromRows(chapter, "to");
    const corpus = entry?.commonality?.corpus_size ?? numberFromRows(chapter, "corpus");
    const frequency = entry?.commonality?.corpus_frequency ?? null;

    add(
      measurements,
      numberMeasurement("candidates after the shortlist", after, {
        share: before && before > 0 && after !== null ? after / before : null,
        note: before !== null ? `of ${before} before the shortlist` : null,
      }),
    );
    add(
      measurements,
      numberMeasurement("commonality corpus", corpus, { note: "works in the reference corpus" }),
    );
    add(
      measurements,
      numberMeasurement("this pattern occurs in", frequency, {
        share: corpus && corpus > 0 && frequency !== null ? frequency / corpus : null,
        note: "works of the corpus",
      }),
    );

    return (
      <Metric
        measurements={measurements}
        fallback="The shortlist has not given a single number yet."
      />
    );
  }

  if (id === "verdict-preliminary" && entry?.alignment) {
    return (
      <AlignmentRibbon
        alignment={entry.alignment}
        queryDuration={queryDuration}
        candidateName={entry.candidate.name}
      />
    );
  }

  if (id === "lyrics") {
    const measurements: Measurement[] = [];
    add(measurements, numberMeasurement("words in the transcript", numberFromRows(chapter, "words")));
    add(
      measurements,
      numberMeasurement(
        "transcript confidence",
        results.lyrics?.asr_confidence ?? numberFromRows(chapter, "asr_confidence"),
        { unit: "%", decimals: 0, share: results.lyrics?.asr_confidence ?? null },
      ),
    );
    add(
      measurements,
      numberMeasurement("shared phrase coverage", results.lyrics?.jaccard, {
        unit: "%",
        share: results.lyrics?.jaccard ?? null,
      }),
    );

    // Values in 0..1 are shown as percentages, so we scale before the animation.
    const scaled = measurements.map((measurement) =>
      measurement.unit === "%" ? { ...measurement, value: measurement.value * 100 } : measurement,
    );

    return (
      <Metric
        measurements={scaled}
        fallback="The confidence gate rejected the transcript, so there is nothing to measure."
      />
    );
  }

  if (id === "melodic") {
    const measurements: Measurement[] = [];
    add(
      measurements,
      numberMeasurement(
        "longest common run",
        results.melodic?.longest_common_run ?? numberFromRows(chapter, "longest_common_run"),
        { note: "consecutive identical intervals" },
      ),
    );
    add(
      measurements,
      numberMeasurement("Mongeau-Sankoff distance", results.melodic?.ms_distance, { decimals: 2 }),
    );

    return (
      <Metric
        measurements={measurements}
        fallback="The melody detector has not returned a result yet."
      />
    );
  }

  if (id === "verdict-final" || id === "verdict-preliminary") {
    const list = verdicts(events);
    const current = id === "verdict-final" ? list[list.length - 1] : list[0];
    const verdictClass = current ? verdictClassFromDetail(current.detail, "class") : null;

    if (current && verdictClass !== null) {
      const previousClass =
        id === "verdict-final" && list.length > 1
          ? verdictClassFromDetail(list[0].detail, "class")
          : null;
      const previousProbability =
        id === "verdict-final" && list.length > 1 && typeof list[0].detail.probability === "number"
          ? (list[0].detail.probability as number)
          : null;

      return (
        <VerdictLift
          currentClass={verdictClass}
          currentProbability={
            typeof current.detail.probability === "number"
              ? (current.detail.probability as number)
              : (entry?.probability ?? null)
          }
          probabilityStatus={
            current.detail.probability_status === "calibrated" ? "calibrated" : "uncalibrated"
          }
          previousClass={previousClass}
          previousProbability={previousProbability}
          changedBy={changesBetweenVerdicts(events)}
        />
      );
    }
  }

  return <StreamChronograph events={events} />;
}

export function AnalysisStage({
  chapter,
  events,
  entry,
  results,
  queryDuration,
  finished = false,
  streamError = null,
  replayKey = 0,
  className = "",
}: AnalysisStageProps) {
  const rows = chapter?.rows ?? [];
  const facts = rows.flatMap((row) => describeStage(row).facts);
  const description = stepDescription(chapter?.id);

  /*
    The label carries the lime, so it answers exactly the question the accent is
    allowed to answer: **is something being computed right now**. That is the
    same signal `StepMap` puts on its marker (`stepStates`), and the two must not
    disagree - a map with no accent beside a stage announcing work in progress
    tells the room the run is still going after it stopped.

    Three things end it: the final verdict, a broken stream, and a step that
    failed. Once any of them is true the label stays, because the run really did
    reach this step, but it says so in grey.
  */
  const failed = rows.length > 0 && rows[rows.length - 1].status === "failed";
  const running = chapter !== null && !finished && streamError === null && !failed;
  const statusLabel = finished
    ? "Analysis complete"
    : streamError !== null
      ? "Analysis interrupted"
      : "Analysis in progress";

  return (
    <div data-testid="analysis-stage" className={`flex min-h-0 w-full min-w-0 flex-col gap-4 ${className}`}>
      <header className="flex min-w-0 shrink-0 flex-col gap-2">
        <p
          data-testid="stage-status"
          data-accent={running ? "true" : "false"}
          className={running ? SIGNAL_LABEL_CLASS : `${MICRO_LABEL_CLASS} text-muted`}
        >
          {statusLabel}
        </p>
        <h2 className={`text-3xl ${HEADING_CLASS} lg:text-4xl`}>
          {chapter?.title ?? "Waiting for material"}
        </h2>

        {description ? (
          <div data-testid="step-description" className="flex max-w-3xl flex-col gap-1">
            <p className="text-sm leading-relaxed text-text lg:text-base">{description.how}</p>
            <p className="text-sm leading-relaxed text-muted">{description.why}</p>
          </div>
        ) : (
          <p className="max-w-3xl text-sm text-muted lg:text-base">
            {chapter?.sentence ?? "The event stream has not started yet."}
          </p>
        )}
      </header>

      {/*
        Visualizations are sometimes wider than the frame on a 4:3 projector, so
        they get their own container with horizontal scrolling. Pushing the page
        wider is forbidden: the whole stage has to fit on one screen.
      */}
      <div className="min-h-0 w-full min-w-0 flex-1 overflow-x-auto overflow-y-auto">
        <div className="min-w-0 max-w-full">
          <Visualization
            key={`${chapter?.id ?? "none"}-${replayKey}`}
            chapter={chapter}
            events={events}
            entry={entry}
            results={results}
            queryDuration={queryDuration}
          />
        </div>
      </div>

      {facts.length > 0 ? (
        <dl className="flex min-w-0 shrink-0 flex-wrap gap-x-8 gap-y-2">
          {facts.map((fact, index) => (
            <div key={`${fact.label}-${index}`} className="min-w-0">
              <dt className={`${MICRO_LABEL_CLASS} text-muted`}>{fact.label}</dt>
              <dd
                title={fact.title}
                className={`truncate text-lg ${fact.mono ? TECHNICAL_VALUE_CLASS : ""} text-text`}
              >
                {fact.value}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

export default AnalysisStage;
