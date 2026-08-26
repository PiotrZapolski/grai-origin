import type { Commonality, DetectorKey, DetectorStatus } from "../../lib/contracts";
import { DETECTOR_KEYS } from "../../lib/contracts";
import { formatCount, formatPercent } from "../../lib/format";
import { CRITERION_LABELS, STATE_WORDS } from "../../lib/labels";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";

/**
 * Screen E5 - the breakdown by criterion (sections 13.2, 7.0, 8.2).
 *
 * There are **four** criteria: recording, harmony, melody, lyrics. No rhythm and
 * no video [D5] - an addendum to the brief listed them, but there is no detector
 * behind them in the system, and a bar without a detector is a prop. A prop in an
 * evidentiary tool is worse than its absence, because the whole product is sold
 * on the fact that every number is backed by something.
 */

/**
 * An evidence entry next to a ranking entry. The shape matches `Evidence` from
 * the contracts (`status` plus `reason`), but is deliberately looser: `reason` is
 * sometimes omitted, and the detector envelopes attach their own measurement
 * fields, which this screen does not read. The number for the bar arrives
 * separately, through `scores`.
 */
export interface CriterionEvidence {
  status: DetectorStatus;
  reason?: string | null;
  [field: string]: unknown;
}

export interface CriteriaBarsProps {
  /**
   * The evidence map from a ranking entry. **A missing key means "not measured
   * yet", not "zero"** - level 1 really sends two keys, the full set of four
   * appears only after level 2.
   */
  evidence?: Record<string, CriterionEvidence | undefined> | null;
  /**
   * Normalized 0..1 scores from the detector envelopes. A bar gets a fill only
   * when the status is `ok` and the number is here. The contract forbids
   * measurement fields with any other status, so there is nothing to fill it
   * with.
   */
  scores?: Partial<Record<DetectorKey, number | null>> | null;
  /**
   * The commonality filter for this ranking entry (section 8.2). `Partial`,
   * because the screen reads only the frequency of the pattern and the size of
   * the corpus - `mean_idf` is an input of the fusion, not content for a human.
   */
  commonality?: Partial<Commonality> | null;
  className?: string;
}

/** What a criterion measures - one sentence, when the detector computed a result. */
const CRITERION_MEANING: Record<DetectorKey, string> = {
  fingerprint: "Agreement of the acoustic fingerprint, that is, whether this is the same recording.",
  harmonic: "Convergence of the chord progression, computed with tempo and transposition alignment.",
  melodic: "Common interval sequences of the lead line.",
  lyrics: "Coverage of shared phrases between the transcript of the query and the lyrics of the candidate.",
};

/**
 * The reasons reported by detectors in the language of the screen. The sentences
 * deliberately **do not repeat the worded state** from the heading of the bar:
 * the same message twice reads like two separate facts.
 */
const REASON_GLOSS: Record<string, string> = {
  instrumental: "The candidate is an instrumental recording, so there is nothing to compare.",
  query_instrumental: "The query contains no vocal part.",
  no_lyrics: "The candidate has no lyrics in the manifest.",
  asr_confidence: "The transcript did not reach the confidence threshold, so the result was judged unreliable.",
  low_confidence: "The result did not reach the confidence threshold.",
  no_audio: "The audio material could not be read.",
  no_model: "The model this detector requires is not available.",
  timeout: "The detector did not manage to compute a result within its time window.",
};

/**
 * Why an empty bar is not a zero (section 7.0, constraint 4).
 *
 * The contract forbids measurement fields with any status other than `ok`, so
 * the bar has **nothing** to fill itself with. A viewer looking at an empty bar
 * nevertheless supplies a zero, and zero is a claim about a measurement: "we
 * checked and there is no similarity". The sentence closes that gap and is
 * content, not hedging.
 *
 * It deliberately repeats neither the word "gate" nor the worded state from the
 * heading of the bar - the same message twice reads like two separate facts.
 */
const NOT_A_ZERO =
  "An empty bar is the absence of a measurement, not a result equal to zero. Zero would mean: measured, and there is no similarity.";

/**
 * The sentence about the commonality of a pattern (section 8.2). Instead of an
 * IDF number we show a sentence, because the number says nothing to a person who
 * has to make a decision.
 *
 * The threshold of one percent of the corpus is the same one with which section
 * 8 demotes a match to the `COMMON` class, so the screen says the same thing as
 * the fusion.
 */
export function commonalitySentence(
  commonality: Partial<Commonality> | null | undefined,
): string | null {
  const frequency = commonality?.corpus_frequency;
  if (frequency === null || frequency === undefined) return null;

  const noun = frequency === 1 ? "work" : "works";
  const head = `This pattern occurs in ${formatCount(frequency)} ${noun} of the corpus.`;

  const size = commonality?.corpus_size;
  if (size === null || size === undefined || size <= 0) return head;

  const share = frequency / size;
  const tail =
    share > 0.01
      ? "That is a convention of the genre, not a signal of borrowing."
      : "That is a rare pattern in the corpus, so the hit means something.";
  return `${head} ${tail}`;
}

interface CriterionRowProps {
  criterion: DetectorKey;
  entry: CriterionEvidence | undefined;
  score: number | null | undefined;
  commonality: Partial<Commonality> | null | undefined;
}

function CriterionRow({ criterion, entry, score, commonality }: CriterionRowProps) {
  const status = entry?.status;
  const state = entry === undefined ? "missing" : status ?? "ok";

  // A number belongs to the `ok` status alone. With any other one the contract
  // forbids measurement fields, so there is nothing to fill the bar with
  // (section 7.0).
  const measured =
    state === "ok" && typeof score === "number" && Number.isFinite(score)
      ? Math.min(1, Math.max(0, score))
      : null;

  const reason = typeof entry?.reason === "string" ? entry.reason : null;
  const gloss = reason ? REASON_GLOSS[reason] ?? null : null;

  let interpretation: string;
  if (state === "ok") {
    interpretation = CRITERION_MEANING[criterion];
  } else if (gloss) {
    interpretation = gloss;
  } else if (reason) {
    interpretation = `Reason reported by the detector: ${reason}.`;
  } else if (state === "missing") {
    interpretation = "The detector has not returned a result for this candidate yet.";
  } else {
    interpretation = "The detector gave no reason.";
  }

  // The commonality filter concerns patterns of the work layer, not the acoustic
  // fingerprint (section 8.1): fingerprint hashes are not conventions of a genre,
  // so a sentence about the corpus next to the recording bar would be talking
  // about something other than it suggests.
  const showsCommonality = state === "ok" && criterion !== "fingerprint";
  const commonalityText = showsCommonality ? commonalitySentence(commonality) : null;

  // A bar without a fill is the place where the viewer supplies a zero for
  // himself. The sentence says outright what that empty bar is, and it appears
  // with every state other than `ok` - including "not measured yet", which is
  // not a zero either.
  const zeroNote = state === "ok" ? null : NOT_A_ZERO;

  return (
    <li
      data-testid="criterion-bar"
      data-criterion={criterion}
      data-state={state}
      className="rounded-card border border-muted/20 bg-surface/70 px-5 py-4"
    >
      <div className="flex items-baseline justify-between gap-4">
        <span className={`${MICRO_LABEL_CLASS} text-muted`}>{CRITERION_LABELS[criterion]}</span>
        {measured === null ? (
          <span className={`${MICRO_LABEL_CLASS} text-muted`}>{STATE_WORDS[state]}</span>
        ) : (
          <span className={`${TECHNICAL_VALUE_CLASS} text-text`}>
            {formatPercent(measured)}
          </span>
        )}
      </div>

      {measured !== null && (
        <div aria-hidden="true" className="mt-3 h-1.5 w-full bg-muted/20">
          <div className="h-full bg-text" style={{ width: `${measured * 100}%` }} />
        </div>
      )}

      <p className="mt-3 text-sm leading-relaxed text-muted">{interpretation}</p>

      {zeroNote && (
        <p data-testid="not-zero" className="mt-2 text-sm leading-relaxed text-muted/80">
          {zeroNote}
        </p>
      )}

      {commonalityText && (
        <p data-testid="commonality" className="mt-2 text-sm leading-relaxed text-muted">
          {commonalityText}
        </p>
      )}
    </li>
  );
}

/**
 * Horizontal bars per detector with a score and a one-sentence interpretation.
 *
 * A bar with a status other than `ok` shows **a worded state, not a zero**
 * (section 7.0), and a missing key in the evidence map means "not measured yet",
 * because level 1 sends two detectors out of four.
 */
export function CriteriaBars({
  evidence,
  scores,
  commonality,
  className = "",
}: CriteriaBarsProps) {
  return (
    <ul className={`flex flex-col gap-3 ${className}`}>
      {DETECTOR_KEYS.map((criterion) => (
        <CriterionRow
          key={criterion}
          criterion={criterion}
          entry={evidence?.[criterion]}
          score={scores?.[criterion]}
          commonality={commonality}
        />
      ))}
    </ul>
  );
}

export default CriteriaBars;
