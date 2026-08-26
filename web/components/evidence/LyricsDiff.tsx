"use client";

/**
 * Lyrics with highlighting (section 13.2, the third panel).
 *
 * Two columns, the common phrases highlighted, a click seeks playback to the
 * place. Seeking goes through `onSeek`, because playback is governed by
 * `AbPlayer` and there must not be two independent playheads in one evidence
 * panel.
 *
 * In the contract `matched_spans` is a loose dictionary (`list[dict[str, Any]]`),
 * so every span goes through `readSpan` and either has the full set of numbers or
 * does not reach the screen. Guessing missing timecodes in an evidentiary tool is
 * worse than not having them.
 */

import type { DetectorStatus, TranscriptWord } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";
import { formatTimecodeTenths } from "../../lib/format";

export type LyricsSide = "query" | "candidate";

export interface CommonPhrase {
  query: [number, number];
  candidate: [number, number];
  text: string;
}

export interface LyricsDiffProps {
  /** `undefined` means: the key is not in `evidence`, the detector has not started. */
  status: DetectorStatus | undefined;
  reason?: string | null;
  /** `matched_spans` from the envelope of detector D. */
  spans: Array<Record<string, unknown> | null | undefined>;
  /** The transcript of the query from `QueryInfo.transcript`. */
  transcript?: TranscriptWord[];
  candidateName?: string;
  onSeek?: (seconds: number, side: LyricsSide) => void;
  className?: string;
}

const STATE_SENTENCES: Record<DetectorStatus, string> = {
  ok: "",
  not_applicable: "The lyrics detector has nothing to compare here.",
  gated: "The transcript was rejected by the confidence gate, the system is retrying after source separation.",
  failed: "The lyrics detector returned no result.",
};

function numberPair(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length < 2) return null;
  const [a, b] = value;
  if (typeof a !== "number" || typeof b !== "number") return null;
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return [a, b];
}

/** Reads one span from a loose dictionary. `null` means: it cannot be trusted. */
export function readSpan(raw: unknown): CommonPhrase | null {
  if (!raw || typeof raw !== "object") return null;
  const record = raw as Record<string, unknown>;
  const query = numberPair(record.query);
  const candidate = numberPair(record.candidate);
  const text = typeof record.text === "string" ? record.text : null;
  if (!query || !candidate || text === null) return null;
  return { query, candidate, text };
}

/** Whether a transcript word lies inside one of the common phrases. */
export function wordInCommonPhrase(word: TranscriptWord, phrases: CommonPhrase[]): boolean {
  return phrases.some((phrase) => word.start >= phrase.query[0] && word.end <= phrase.query[1]);
}

export function LyricsDiff({
  status,
  reason = null,
  spans,
  transcript = [],
  candidateName = "CANDIDATE",
  onSeek,
  className = "",
}: LyricsDiffProps) {
  const header = (
    <header className="flex flex-wrap items-baseline justify-between gap-3">
      <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>LYRICS</h3>
    </header>
  );

  if (status === undefined) {
    return (
      <section className={`origin-card flex flex-col gap-4 p-6 ${className}`}>
        {header}
        <p className="text-sm text-muted">
          The lyrics detector has not computed this candidate yet. Level 2 is still arriving.
        </p>
      </section>
    );
  }

  if (status !== "ok") {
    return (
      <section className={`origin-card flex flex-col gap-4 p-6 ${className}`}>
        {header}
        <p className="text-sm text-muted">{reason ?? STATE_SENTENCES[status]}</p>
      </section>
    );
  }

  const phrases = spans.map(readSpan).filter((phrase): phrase is CommonPhrase => phrase !== null);

  return (
    <section className={`origin-card flex flex-col gap-4 p-6 ${className}`}>
      {header}

      <div className="grid gap-6 md:grid-cols-2">
        <div data-testid="query-column" className="flex flex-col gap-3">
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>QUERY</p>

          {transcript.length > 0 ? (
            <p className="flex flex-wrap gap-x-1.5 gap-y-1 leading-relaxed">
              {transcript.map((word, index) => {
                const shared = wordInCommonPhrase(word, phrases);
                return (
                  <button
                    key={`${word.word}-${word.start}-${index}`}
                    type="button"
                    data-shared={shared ? "true" : "false"}
                    onClick={() => onSeek?.(word.start, "query")}
                    title={formatTimecodeTenths(word.start)}
                    className={shared ? "bg-accent/15 px-0.5 text-text" : "text-muted"}
                  >
                    {word.word}
                  </button>
                );
              })}
            </p>
          ) : null}

          {/*
            The phrases in the query column are shown only when there is no
            transcript. With a transcript they are the same words twice, and
            doubled evidence reads like two separate hits.
          */}
          {(transcript.length === 0 ? phrases : []).map((phrase, index) => (
            <button
              key={`query-${index}`}
              type="button"
              data-shared="true"
              onClick={() => onSeek?.(phrase.query[0], "query")}
              className="flex flex-col items-start gap-1 rounded-inner border-l-2 border-accent bg-accent/10 px-3 py-2 text-left"
            >
              <span className={`text-[11px] text-muted ${TECHNICAL_VALUE_CLASS}`}>
                {formatTimecodeTenths(phrase.query[0])} to {formatTimecodeTenths(phrase.query[1])}
              </span>
              <span>{phrase.text}</span>
            </button>
          ))}

          {transcript.length === 0 && phrases.length === 0 ? (
            <p className="text-sm text-muted">The transcript of the query is empty.</p>
          ) : null}
        </div>

        <div data-testid="candidate-column" className="flex flex-col gap-3">
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>{candidateName}</p>

          {phrases.map((phrase, index) => (
            <button
              key={`candidate-${index}`}
              type="button"
              data-shared="true"
              onClick={() => onSeek?.(phrase.candidate[0], "candidate")}
              className="flex flex-col items-start gap-1 rounded-inner border-l-2 border-accent bg-accent/10 px-3 py-2 text-left"
            >
              <span className={`text-[11px] text-muted ${TECHNICAL_VALUE_CLASS}`}>
                {formatTimecodeTenths(phrase.candidate[0])} to {formatTimecodeTenths(phrase.candidate[1])}
              </span>
              <span>{phrase.text}</span>
            </button>
          ))}

          {phrases.length === 0 ? (
            <p className="text-sm text-muted">No stretch of lyrics overlapped enough to be shown.</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export default LyricsDiff;
