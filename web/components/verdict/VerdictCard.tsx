"use client";

/**
 * Screen E3 - the verdict. Sections 4, 10.5, 12 and 13.2 of the specification.
 *
 * One full-width card: the name of the source, the badge of the evidence class,
 * the probability with its calibration status and one sentence of reasoning.
 *
 * The heart of this screen is in time, not in layout. The verdict arrives
 * **twice**: `partial` after level 1 (target 5 s) and `final` after level 2
 * (target 30 s), and the class can change in between - the mock moves from
 * VERSION to EXCERPT_WORK. That is not an error to hide but a feature of the
 * product: the system shows a preliminary judgement and lifts it once the slower
 * evidence arrives. Which is why the card remembers the previous verdict and
 * shows where it was lifted from and to, instead of quietly swapping the number.
 */

import { useEffect, useRef, useState } from "react";

import Badge from "../Badge";
import { formatCount, formatPercent } from "../../lib/format";
import { OriginalLink, type SourceCandidate } from "./SourceLink";
import type {
  CalibrationInfo,
  Commonality,
  ProbabilityStatus,
  ResultStatus,
  VerdictClass,
} from "../../lib/contracts";
import {
  HEADING_CLASS,
  MICRO_LABEL_CLASS,
  TECHNICAL_VALUE_CLASS,
  VERDICT_LABELS,
} from "../../lib/theme";

/**
 * The part of a ranking entry the card needs.
 *
 * Deliberately narrower than `RankingEntry`: every `RankingEntry` fits here, but
 * the card does not require the full set of fields, so it can be fed with a
 * `verdict` event from the stream topped up with a candidate, before the full
 * result from `/result` arrives.
 *
 * The candidate here is **a whole `SourceCandidate`**, not just a name-artist
 * pair. The question somebody comes to this tool with is "where is this from",
 * and the answer useful to a human being is an address that can be opened. As
 * long as the card saw two fields of the candidate, the address and the date had
 * to be attached next to it from the outside.
 */
export interface VerdictEntry {
  verdict_class: VerdictClass;
  probability: number | null;
  probability_status: ProbabilityStatus;
  candidate: SourceCandidate;
  explanation?: string | null;
  commonality?: Commonality | null;
}

export interface VerdictCardProps {
  entry: VerdictEntry;
  /** `partial` after level 1, `final` after level 2. */
  status: ResultStatus;
  /** The metrics of the calibration model. `null` means: there is no model (section 10). */
  calibration?: CalibrationInfo | null;
  /** Whether the card describes the best match. Outside it the accent is not warranted. */
  best?: boolean;
  className?: string;
}

/** The trace of a verdict lift: what was there before level 2 arrived. */
interface Lift {
  verdictClass: VerdictClass;
  probability: number | null;
}

const STATUS_LABELS: Record<ResultStatus, string> = {
  partial: "PRELIMINARY VERDICT / LEVEL 1 OF 2",
  final: "FINAL VERDICT / LEVEL 2 OF 2",
  failed: "ANALYSIS INTERRUPTED",
};

/** A percentage with no decimal places. `null` has no right to turn into zero. */
export function probabilityText(probability: number | null): string {
  if (probability === null) return "no number";
  return formatPercent(probability);
}

/**
 * The sentence about the status of the threshold (section 10.5).
 *
 * An uncalibrated number has no right to look the same as a calibrated one, and
 * the precision of the model is translated into language that means something:
 * "it is wrong in 5 cases out of 100" instead of "precision 0.95".
 */
export function calibrationSentence(
  status: ProbabilityStatus,
  calibration?: CalibrationInfo | null,
): string {
  if (status === "uncalibrated") {
    return "Preliminary threshold, no calibration data.";
  }
  if (!calibration) {
    return "Threshold calibrated, model metrics unavailable.";
  }
  const base = `Threshold calibrated on ${calibration.trained_on} pairs from the SecondHandSongs catalogue.`;
  if (calibration.precision_at_threshold === null) {
    return base;
  }
  const mistakes = Math.round((1 - calibration.precision_at_threshold) * 100);
  return `${base} At this level the system is wrong in ${mistakes} cases out of 100.`;
}

/**
 * Why the confidence of a preliminary verdict may still grow.
 *
 * This is the point at which the viewer asks "so how much is it in the end?" and
 * without an answer reads the level 1 number as the final one. The sentence says
 * what is still missing; it does not promise a particular result.
 */
export function levelSentence(status: ResultStatus): string | null {
  if (status !== "partial") return null;
  return (
    "Level 1 rests on two fast detectors: the acoustic fingerprint and the harmony. " +
    "Level 2 adds the transcript and the melody, so the number will still move and the evidence " +
    "class may change. New evidence does not erase the previous evidence, it joins the fusion."
  );
}

/**
 * Why the similarity that was found is insignificant (class `COMMON`, section 8).
 *
 * Without this sentence the screen says only "COMMON ELEMENT" and looks like a
 * failed search. It is the opposite: the system found a similarity, measured it
 * and **demoted it itself**, because the pattern is common in the corpus. This
 * is the part of the product that has judgement, rather than a match alone.
 */
export function commonClassSentence(verdict: VerdictClass): string | null {
  if (verdict !== "COMMON") return null;
  return (
    "The similarity is real and measured - this is not the absence of a hit. " +
    "It was demoted by the commonality filter: the same pattern sits in many works of the corpus, " +
    "so on its own it does not point to a borrowing. Protection does not cover the conventions of a " +
    "genre, and an identical match on a rare pattern would mean something entirely different."
  );
}

/** The sentence from section 8.2: a corpus number turned into an interpretation. */
export function commonalitySentence(commonality?: Commonality | null): string | null {
  if (!commonality || commonality.corpus_frequency === null) return null;
  const count = formatCount(commonality.corpus_frequency);
  if (commonality.corpus_frequency > 100) {
    return `This pattern occurs in ${count} works of the corpus. That is a convention of the genre, not a signal of borrowing.`;
  }
  return `This pattern occurs in ${count} works of the corpus.`;
}

export function VerdictCard({
  entry,
  status,
  calibration = null,
  best = true,
  className = "",
}: VerdictCardProps) {
  const [lift, setLift] = useState<Lift | null>(null);
  const previous = useRef<Lift | null>(null);

  useEffect(() => {
    const before = previous.current;
    previous.current = {
      verdictClass: entry.verdict_class,
      probability: entry.probability,
    };
    if (before === null) return;
    if (
      before.verdictClass !== entry.verdict_class ||
      before.probability !== entry.probability
    ) {
      setLift(before);
    }
  }, [entry.verdict_class, entry.probability]);

  const commonalityText = commonalitySentence(entry.commonality);
  const levelText = levelSentence(status);
  const commonClassText = commonClassSentence(entry.verdict_class);
  const lifted = lift !== null;

  return (
    <>
    <section
      data-testid="verdict-card"
      data-status={status}
      data-verdict={entry.verdict_class}
      data-lifted={lifted ? "true" : "false"}
      /*
       * The transition has to be visible and readable rather than a blink: the
       * border and the background cross over half a second, so the eye has time
       * to notice that the card moved. The styles are here, because globals.css
       * belongs to another task.
       */
      style={{ transition: "border-color 600ms ease, box-shadow 600ms ease" }}
      /*
       * The verdict is the largest element of the show and is meant to look it:
       * a larger card, a larger heading, a larger number. The other screens give
       * way. The lift outline goes through `ring-accent` rather than a hard-coded
       * `rgba(200,255,61,...)` - the same signal, only taken from the token.
       */
      className={`origin-card w-full p-8 sm:p-10 ${
        lifted ? "ring-1 ring-accent/40" : ""
      } ${className}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p data-testid="verdict-stage" className={`text-muted ${MICRO_LABEL_CLASS}`}>
            {STATUS_LABELS[status]}
          </p>
          <h2 className={`mt-3 text-4xl sm:text-5xl ${HEADING_CLASS}`}>
            {entry.candidate.name}
          </h2>
          <p className="mt-2 text-lg text-muted">{entry.candidate.artist}</p>
        </div>
        <Badge verdict={entry.verdict_class} best={best} />
      </header>

      {/*
        The address of the original and the release date stand **directly under
        the badge**, not at the foot of the card.

        The question somebody came here with is "where is this from", so the
        answer must not sit behind the confidence, the explanation and the lift
        line. On a 1080p projector the card is taller than the frame that holds
        it, and whatever is last is whatever gets scrolled away - the address is
        the last thing that may happen to.

        Outside the best match the address is not warranted: the addresses of
        entries 2-N have their own block under the ranking (`SourceAddresses`).
      */}
      {best ? <OriginalLink candidate={entry.candidate} className="mt-6" /> : null}

      <div className="mt-8 flex flex-wrap items-end gap-x-10 gap-y-4">
        <div>
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
            {entry.probability_status === "calibrated" ? "CONFIDENCE" : "PRELIMINARY CONFIDENCE"}
          </p>
          <p
            data-testid="confidence"
            data-probability-status={entry.probability_status}
            className={`mt-2 text-6xl sm:text-7xl ${TECHNICAL_VALUE_CLASS} ${
              entry.probability_status === "calibrated" ? "text-text" : "text-muted"
            }`}
          >
            {probabilityText(entry.probability)}
          </p>
        </div>

        <p
          className={`max-w-md border-l-2 pl-4 text-sm ${
            entry.probability_status === "calibrated"
              ? "border-muted/40 text-muted"
              : "border-dashed border-muted/60 text-muted"
          }`}
        >
          {calibrationSentence(entry.probability_status, calibration)}
        </p>
      </div>

      {entry.explanation ? (
        <p className="mt-8 max-w-3xl text-lg leading-relaxed">{entry.explanation}</p>
      ) : null}

      {/*
        The explanation of the `COMMON` class stands at full contrast, not in
        grey: it is not a footnote to the verdict, it is the verdict. Without it
        "COMMON ELEMENT" reads like a failed search.
      */}
      {commonClassText ? (
        <p
          data-testid="common-explanation"
          className="mt-6 max-w-3xl border-l-2 border-muted/40 pl-4 leading-relaxed text-text"
        >
          {commonClassText}
        </p>
      ) : null}

      {commonalityText ? <p className="mt-4 max-w-3xl text-sm text-muted">{commonalityText}</p> : null}

      {/*
        Why the number will still grow. Without lime - this is not an alert but a
        description of the state of the analysis.
      */}
      {levelText ? (
        <p
          data-testid="level-explanation"
          className="mt-6 max-w-3xl text-sm leading-relaxed text-muted"
        >
          {levelText}
        </p>
      ) : null}

      {lift ? (
        /*
         * The previous class stays in the sentence but does not get a badge of
         * its own: one verdict is meant to stand on screen, not two at once.
         */
        <p
          data-testid="lift"
          className="mt-6 flex flex-wrap items-baseline gap-x-2 border-t border-muted/20 pt-4 text-sm text-muted"
        >
          {/*
            The label is a micro-label, but both numbers are measurements, so
            they go in the fixed-width typeface. Previously the whole line was a
            single uppercase string and the percentages lost the signal of a
            measurement.
          */}
          <span className={MICRO_LABEL_CLASS}>VERDICT LIFTED</span>
          <span>from {VERDICT_LABELS[lift.verdictClass]}</span>
          <span className={TECHNICAL_VALUE_CLASS}>
            {probabilityText(lift.probability)}
          </span>
          <span>to {VERDICT_LABELS[entry.verdict_class]}</span>
          <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{probabilityText(entry.probability)}</span>
        </p>
      ) : null}
    </section>
    </>
  );
}

export default VerdictCard;
