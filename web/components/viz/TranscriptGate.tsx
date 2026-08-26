"use client";

/**
 * The transcript confidence gate: the moment the system rejects its own result.
 *
 * This is the most interesting step of the whole run and until now it was an
 * ordinary counter on screen. Section 7.3: the transcript goes through a
 * confidence gate which, on a score below the threshold, **rejects its own
 * measurement and points to the next step itself**. Only after source separation
 * does the second attempt get through.
 *
 * The panel therefore shows both attempts on one scale: the first runs up to the
 * rejected value and stops under the threshold, then separation slides in, and
 * the second crosses the threshold. All four numbers - both confidences, the
 * threshold and the word count - arrive in the `detail` of the `transcript` and
 * `separation` events.
 *
 * The transcript words appear in **their own rhythm**: the gaps between them are
 * proportional to the differences of `start` from the transcript, not equal.
 * When the result carries no transcript, only the word counter is left, because
 * there is nothing to take the rhythm from.
 */

import { useMemo } from "react";

import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, theme } from "../../lib/theme";
import { useProgress, ease } from "./motion";

/** An event as loose as it has to be to accept both `StreamEvent` and `PipelineEvent`. */
interface LyricsEvent {
  stage: string;
  status: string;
  detail?: Record<string, unknown> | null;
}

/** A transcript word exactly as `QueryInfo.transcript` carries it. */
export interface TranscriptWordSpan {
  word: string;
  start: number;
  end: number;
}

export interface LyricsData {
  /** The confidence the gate rejected. */
  gatedConfidence: number | null;
  threshold: number | null;
  gateReason: string | null;
  /** The step the gate pointed to: `separation` or `melodic`. */
  gateNext: string | null;
  /** The confidence of the second attempt, after separation. */
  confidence: number | null;
  words: number | null;
  language: string | null;
  usedSeparation: boolean;
  separationModel: string | null;
  separationSeconds: number | null;
}

export interface TranscriptGateProps extends Partial<LyricsData> {
  events?: readonly LyricsEvent[];
  /** The transcript words of the query, if the result carries them. */
  transcript?: readonly TranscriptWordSpan[] | null;
  /** `jaccard` from the envelope of detector D for the candidate being shown. */
  jaccard?: number | null;
  semanticSim?: number | null;
  /** The text of the common phrase from `matched_spans`, exactly as it arrived. */
  matchedText?: string | null;
  className?: string;
}

const DURATION_MS = 3000;

/* The successive phases of the run, expressed as a share of the whole. */
const ATTEMPT_1 = [0.0, 0.26] as const;
const REJECTION = 0.3;
const SEPARATION = 0.42;
const ATTEMPT_2 = [0.52, 0.8] as const;
const WORDS = 0.8;

const REASONS: Record<string, string> = {
  asr_confidence: "transcript confidence below the threshold",
  instrumental: "the material is instrumental",
  no_lyrics: "the candidate has no lyrics",
  short_query: "the material is too short for this detector",
};

const STEPS: Record<string, string> = {
  separation: "source separation",
  melodic: "symbolic melody",
  transcript: "transcript retry",
};

function numberAt(detail: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = detail?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function textAt(detail: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = detail?.[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** The numbers of both transcript attempts, straight from the stream. */
export function lyricsData(events: readonly LyricsEvent[] | undefined): LyricsData {
  const empty: LyricsData = {
    gatedConfidence: null,
    threshold: null,
    gateReason: null,
    gateNext: null,
    confidence: null,
    words: null,
    language: null,
    usedSeparation: false,
    separationModel: null,
    separationSeconds: null,
  };
  if (!events) return empty;

  const gated = events.find(
    (event) => event.stage === "transcript" && event.status === "gated",
  );
  const accepted = [...events]
    .reverse()
    .find((event) => event.stage === "transcript" && event.status === "done");
  const separations = events.filter((event) => event.stage === "separation");

  return {
    gatedConfidence: numberAt(gated?.detail, "asr_confidence"),
    threshold: numberAt(gated?.detail, "threshold"),
    gateReason: textAt(gated?.detail, "reason"),
    gateNext: textAt(gated?.detail, "next"),
    confidence: numberAt(accepted?.detail, "asr_confidence"),
    words: numberAt(accepted?.detail, "words"),
    language: textAt(accepted?.detail, "lang") ?? textAt(accepted?.detail, "language"),
    usedSeparation: accepted?.detail?.used_separation === true,
    separationModel:
      separations.map((event) => textAt(event.detail, "model")).find(Boolean) ?? null,
    separationSeconds:
      separations.map((event) => numberAt(event.detail, "seconds")).find((x) => x !== null) ??
      null,
  };
}

/** The share within a phase: 0 before it starts, 1 after it ends. */
function phase(progress: number, from: number, to: number): number {
  if (progress <= from) return 0;
  if (progress >= to) return 1;
  return ease((progress - from) / (to - from));
}

/* -------------------------------------------------------------------------- */
/* The confidence scale                                                       */
/* -------------------------------------------------------------------------- */

function Attempt({
  label,
  value,
  threshold,
  share,
  accepted,
  visible,
}: {
  label: string;
  value: number;
  threshold: number | null;
  share: number;
  accepted: boolean;
  visible: boolean;
}) {
  const reached = value * share;
  return (
    <figure
      data-testid={accepted ? "attempt-accepted" : "attempt-rejected"}
      className="flex flex-col gap-1.5"
      style={{ opacity: visible ? 1 : 0.25, transition: "opacity 240ms ease" }}
    >
      <figcaption className="flex flex-wrap items-baseline justify-between gap-3">
        <span className={`text-muted ${MICRO_LABEL_CLASS}`}>{label}</span>
        <span className={`${MICRO_LABEL_CLASS} ${accepted ? "text-accent" : "text-muted"}`}>
          CONFIDENCE{" "}
          <span className={`${TECHNICAL_VALUE_CLASS} ${accepted ? "text-accent" : "text-text"}`}>
            {value.toFixed(2)}
          </span>
        </span>
      </figcaption>

      <div className="relative h-4 w-full overflow-hidden rounded-full bg-muted/15">
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${Math.max(0, Math.min(1, reached)) * 100}%`,
            backgroundColor: accepted ? theme.accent : `${theme.text}66`,
          }}
        />
        {threshold !== null ? (
          <span
            data-testid="gate-threshold"
            className="absolute inset-y-0 w-0.5 bg-text"
            style={{ left: `${Math.max(0, Math.min(1, threshold)) * 100}%` }}
          />
        ) : null}
      </div>
    </figure>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel                                                                      */
/* -------------------------------------------------------------------------- */

export function TranscriptGate({
  events,
  transcript = null,
  jaccard = null,
  semanticSim = null,
  matchedText = null,
  className = "",
  ...explicit
}: TranscriptGateProps) {
  const fromStream = useMemo(() => lyricsData(events), [events]);
  const d: LyricsData = {
    gatedConfidence: explicit.gatedConfidence ?? fromStream.gatedConfidence,
    threshold: explicit.threshold ?? fromStream.threshold,
    gateReason: explicit.gateReason ?? fromStream.gateReason,
    gateNext: explicit.gateNext ?? fromStream.gateNext,
    confidence: explicit.confidence ?? fromStream.confidence,
    words: explicit.words ?? fromStream.words,
    language: explicit.language ?? fromStream.language,
    usedSeparation: explicit.usedSeparation ?? fromStream.usedSeparation,
    separationModel: explicit.separationModel ?? fromStream.separationModel,
    separationSeconds: explicit.separationSeconds ?? fromStream.separationSeconds,
  };

  const hasAnything = d.gatedConfidence !== null || d.confidence !== null || d.words !== null;

  const progress = useProgress({
    duration: DURATION_MS,
    key: `${d.gatedConfidence ?? "none"}:${d.confidence ?? "none"}:${d.words ?? "none"}`,
    enabled: hasAnything,
  });

  const share1 = phase(progress, ATTEMPT_1[0], ATTEMPT_1[1]);
  const stamp = progress >= REJECTION;
  const separationVisible = progress >= SEPARATION;
  const share2 = phase(progress, ATTEMPT_2[0], ATTEMPT_2[1]);
  const wordsShare = phase(progress, WORDS, 1);

  const words = useMemo(() => (transcript ? [...transcript] : []), [transcript]);
  const rhythm = useMemo(() => {
    if (words.length === 0) return [];
    const start = words[0].start;
    const end = words[words.length - 1].end;
    const span = end - start;
    // The rhythm is real: the gaps are proportional to the time differences in the result.
    return words.map((item) => (span > 0 ? (item.start - start) / span : 0));
  }, [words]);

  const wordCounter = d.words === null ? null : Math.round(d.words * phase(progress, ATTEMPT_2[1], 1));

  if (!hasAnything) {
    return (
      <section
        data-testid="lyrics-gate"
        data-state="none"
        className={`origin-card flex flex-col gap-4 p-6 ${className}`}
      >
        <header className={`text-muted ${MICRO_LABEL_CLASS}`}>TRANSCRIPT CONFIDENCE GATE</header>
        <p className="text-sm text-muted">
          The lyrics detector has not returned a single number yet, so there is nothing to put on
          the scale.
        </p>
      </section>
    );
  }

  return (
    <section
      data-testid="lyrics-gate"
      data-state="ok"
      data-separation={d.usedSeparation ? "true" : "false"}
      className={`origin-card flex flex-col gap-5 p-6 ${className}`}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>TRANSCRIPT CONFIDENCE GATE</h3>
        {d.threshold !== null ? (
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
            THRESHOLD{" "}
            <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{d.threshold.toFixed(2)}</span>
          </p>
        ) : null}
      </header>

      {d.gatedConfidence !== null ? (
        <div className="flex flex-col gap-2">
          <Attempt
            label="FIRST ATTEMPT"
            value={d.gatedConfidence}
            threshold={d.threshold}
            share={share1}
            accepted={false}
            visible
          />
          <p
            data-testid="rejection-stamp"
            className={`${MICRO_LABEL_CLASS} text-text`}
            style={{
              opacity: stamp ? 1 : 0,
              transform: stamp ? "none" : "translateY(4px)",
              transition: "opacity 200ms ease, transform 200ms ease",
            }}
          >
            REJECTED BY THE GATE
            {d.gateReason ? `: ${REASONS[d.gateReason] ?? d.gateReason}` : ""}
          </p>
        </div>
      ) : null}

      {d.gateNext || d.separationModel ? (
        <div
          data-testid="step-after-gate"
          className="flex flex-wrap items-center gap-2 rounded-inner border border-muted/20 bg-bg px-3 py-2"
          style={{
            opacity: separationVisible ? 1 : 0,
            transform: separationVisible ? "none" : "translateX(-8px)",
            transition: "opacity 260ms ease, transform 260ms ease",
          }}
        >
          <span className={`text-muted ${MICRO_LABEL_CLASS}`}>THE GATE POINTED TO</span>
          <span className={`text-text ${MICRO_LABEL_CLASS}`}>
            {d.gateNext ? (STEPS[d.gateNext] ?? d.gateNext) : "source separation"}
          </span>
          {d.separationModel ? (
            <span className={`text-muted ${TECHNICAL_VALUE_CLASS} text-xs`}>
              {d.separationModel}
              {d.separationSeconds !== null ? ` / ${d.separationSeconds.toFixed(1)} s` : ""}
            </span>
          ) : null}
        </div>
      ) : null}

      {d.confidence !== null ? (
        <Attempt
          label={d.usedSeparation ? "AFTER SOURCE SEPARATION" : "SECOND ATTEMPT"}
          value={d.confidence}
          threshold={d.threshold}
          share={share2}
          accepted={d.threshold === null ? true : d.confidence >= d.threshold}
          visible={separationVisible}
        />
      ) : null}

      {/* The words: either the real rhythm from the transcript, or the counter alone. */}
      {words.length > 0 ? (
        <figure className="flex flex-col gap-2">
          <figcaption className="flex flex-wrap items-baseline justify-between gap-3">
            <span className={`text-muted ${MICRO_LABEL_CLASS}`}>TRANSCRIPT</span>
            {d.words !== null ? (
              <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
                WORDS{" "}
                <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{d.words}</span>
              </span>
            ) : null}
          </figcaption>
          <p data-testid="transcript-words" className="flex flex-wrap gap-x-2 gap-y-1 text-lg">
            {words.map((item, i) => (
              <span
                key={`${item.word}-${i}`}
                className="text-text"
                style={{
                  opacity: wordsShare >= rhythm[i] ? 1 : 0.12,
                  transition: "opacity 160ms ease",
                }}
                title={`${item.start.toFixed(1)} s`}
              >
                {item.word}
              </span>
            ))}
          </p>
          <figcaption className="text-xs text-muted">
            The gaps between the words are proportional to their times from the transcript, so the
            text appears in the rhythm of the recording rather than evenly.
          </figcaption>
        </figure>
      ) : d.words !== null ? (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className={`text-3xl text-text ${TECHNICAL_VALUE_CLASS}`}>{wordCounter}</span>
          <span className={`text-muted ${MICRO_LABEL_CLASS}`}>
            words recognized{d.language ? ` in ${d.language}` : ""}
          </span>
        </div>
      ) : null}

      {matchedText ? (
        <figure className="flex flex-col gap-1">
          <figcaption className={`text-muted ${MICRO_LABEL_CLASS}`}>COMMON PHRASE</figcaption>
          <blockquote className="border-l-2 border-accent/60 pl-3 text-sm text-text">
            {matchedText}
          </blockquote>
        </figure>
      ) : null}

      {jaccard !== null || semanticSim !== null ? (
        <dl className={`grid grid-cols-2 gap-3 text-muted sm:grid-cols-3 ${MICRO_LABEL_CLASS}`}>
          {jaccard !== null ? (
            <div>
              <dt>PHRASE COVERAGE</dt>
              <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
                {Math.round(jaccard * 100)}%
              </dd>
            </div>
          ) : null}
          {semanticSim !== null ? (
            <div>
              <dt>SEMANTIC SIMILARITY</dt>
              <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{semanticSim.toFixed(2)}</dd>
            </div>
          ) : null}
          {d.language ? (
            <div>
              <dt>LANGUAGE</dt>
              <dd className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{d.language}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      <p className="text-xs text-muted">
        A rejection by the gate is not a failure but a step: the system judges its own confidence,
        does not trust it and points to what to do next itself. Both numbers on the scale are the
        ones that arrived in the stream, and the threshold is the one from the contract.
      </p>
    </section>
  );
}

export default TranscriptGate;
