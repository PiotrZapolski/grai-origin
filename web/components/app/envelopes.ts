/**
 * Detector envelopes gathered from the SSE stream.
 *
 * The reason this file exists is in section 12: next to a ranking entry sits
 * `Evidence` with a status and **no measurement values**. The numbers travel
 * separately, in `detail.envelope` of the stream events, and that is the only
 * place they can be taken from. Without this module screen E5 would show four
 * worded states and zero bars.
 *
 * The rule this module implements: **a number reaches the screen only when it
 * has really arrived**. A missing number does not turn into zero, and a quantity
 * that the contract does not normalize to 0..1 is not stretched into that range
 * - see `criterionScores` for melody.
 */

import type {
  DetectorEnvelope,
  DetectorKey,
  FingerprintResult,
  HarmonicResult,
  LyricsResult,
  MelodicResult,
  StreamEvent,
} from "../../lib/contracts";
import { DETECTOR_KEYS } from "../../lib/contracts";

/** The last envelope of each detector. The key is the same as the criterion on E5. */
export type DetectorEnvelopes = Partial<Record<DetectorKey, DetectorEnvelope>>;

export const EMPTY_RESULTS: CandidateResults = {
  fingerprint: null,
  harmonic: null,
  lyrics: null,
  melodic: null,
};

function isDetectorKey(value: unknown): value is DetectorKey {
  return typeof value === "string" && (DETECTOR_KEYS as readonly string[]).includes(value);
}

/**
 * The envelope from `detail.envelope`, or `null`.
 *
 * In the contract `detail` is a dictionary with arbitrary content, so there is
 * nothing to assume here: we check the three fields we need and reject
 * everything else. An event without an envelope is normal - only the `done` of a
 * detector carries one.
 */
export function readEnvelope(raw: unknown): DetectorEnvelope | null {
  if (!raw || typeof raw !== "object") return null;
  const record = raw as Record<string, unknown>;
  if (!isDetectorKey(record.detector)) return null;
  if (typeof record.status !== "string") return null;
  if (!Array.isArray(record.results)) return null;
  return raw as DetectorEnvelope;
}

/**
 * The envelopes from every event that has arrived so far.
 *
 * A later envelope **replaces** an earlier one from the same detector: lyrics
 * can arrive twice, once rejected by the confidence gate and once accepted after
 * source separation (section 12). The second one governs.
 */
export function collectEnvelopes(events: readonly StreamEvent[]): DetectorEnvelopes {
  const envelopes: DetectorEnvelopes = {};
  for (const event of events) {
    const envelope = readEnvelope(event.detail?.envelope);
    if (envelope !== null && isDetectorKey(envelope.detector)) {
      envelopes[envelope.detector] = envelope;
    }
  }
  return envelopes;
}

/** The results of the four detectors for one candidate. `null` means: there is none. */
export interface CandidateResults {
  fingerprint: FingerprintResult | null;
  harmonic: HarmonicResult | null;
  lyrics: LyricsResult | null;
  melodic: MelodicResult | null;
}

function find(envelopes: DetectorEnvelopes, key: DetectorKey, candidateId: string) {
  const envelope = envelopes[key];
  if (!envelope) return null;
  return envelope.results.find((result) => result.candidate_id === candidateId) ?? null;
}

/**
 * The detector results for the given candidate.
 *
 * The `detector` discriminant is checked on every result, because an envelope
 * may carry a base result (`generic`) which has no measurement fields at all.
 * Such a result does not pretend to be a detector result here, it drops out.
 */
export function candidateResults(
  envelopes: DetectorEnvelopes,
  candidateId: string | null | undefined,
): CandidateResults {
  if (!candidateId) return EMPTY_RESULTS;

  const fingerprint = find(envelopes, "fingerprint", candidateId);
  const harmonic = find(envelopes, "harmonic", candidateId);
  const lyrics = find(envelopes, "lyrics", candidateId);
  const melodic = find(envelopes, "melodic", candidateId);

  return {
    fingerprint: fingerprint && fingerprint.detector === "fingerprint" ? fingerprint : null,
    harmonic: harmonic && harmonic.detector === "harmonic" ? harmonic : null,
    lyrics: lyrics && lyrics.detector === "lyrics" ? lyrics : null,
    melodic: melodic && melodic.detector === "melodic" ? melodic : null,
  };
}

/** A 0..1 value or `null`. Nothing outside that range may reach a bar. */
function fraction(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.min(1, Math.max(0, value));
}

/**
 * The 0..1 scores for the bars of screen E5.
 *
 * Three criteria have a normalized quantity in the contract, compared against
 * the thresholds from `config.THRESHOLDS`, so the bar draws exactly what the
 * fusion decides on: `peak_ratio`, `qmax_score`, `jaccard`.
 *
 * **Melody deliberately gets no number.** Detector C reports
 * `longest_common_run` (a count of intervals, threshold 8) and `ms_distance`
 * (the Mongeau-Sankoff distance), and neither of them is a similarity on a 0..1
 * scale. Converting either into a percentage would require inventing a scale
 * that is not in the specification, that is, drawing a bar with nothing behind
 * it - exactly what section 13.2 forbids for E5. Without a number the component
 * shows a worded state, and that is the intended behaviour.
 */
export function criterionScores(
  envelopes: DetectorEnvelopes,
  candidateId: string | null | undefined,
): Partial<Record<DetectorKey, number>> {
  const results = candidateResults(envelopes, candidateId);
  const bars: Partial<Record<DetectorKey, number>> = {};

  // The result status concerns this candidate, and only with `ok` does the
  // contract allow measurement fields (section 7.0). With anything else there is
  // nothing to fill the bar with.
  const fingerprint =
    results.fingerprint?.status === "ok" ? fraction(results.fingerprint.peak_ratio) : null;
  if (fingerprint !== null) bars.fingerprint = fingerprint;

  const harmonic = results.harmonic?.status === "ok" ? fraction(results.harmonic.qmax_score) : null;
  if (harmonic !== null) bars.harmonic = harmonic;

  const lyrics = results.lyrics?.status === "ok" ? fraction(results.lyrics.jaccard) : null;
  if (lyrics !== null) bars.lyrics = lyrics;

  return bars;
}
