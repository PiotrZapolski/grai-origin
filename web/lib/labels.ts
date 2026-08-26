/**
 * Interface text dictionaries shared by several screens.
 *
 * Criterion labels and the worded detector states used to be written out
 * separately on screen E5 (`components/criteria/CriteriaBars`) and E6
 * (`components/ranking/RankingList`). The same state read like two different
 * ones across the two screens, because the copies drifted word by word. There
 * is one dictionary.
 *
 * **Text** lives here, not appearance - visual tokens stay in `lib/theme.ts`.
 */

import type { DetectorKey, DetectorStatus } from "./contracts";

/**
 * Criterion labels. Four of them, exactly as many as there are detectors: no
 * rhythm and no video, because a bar without a detector behind it is a prop.
 */
export const CRITERION_LABELS: Record<DetectorKey, string> = {
  fingerprint: "recording",
  harmonic: "harmony",
  melodic: "melody",
  lyrics: "lyrics",
};

/**
 * The state of a criterion on screen: four statuses from the contract plus
 * `missing`.
 *
 * `missing` is not a value from the status dictionary but a screen state: it
 * corresponds to a key absent from the evidence map, that is, a detector that
 * has not returned a result yet.
 */
export type CriterionState = DetectorStatus | "missing";

/**
 * A worded state instead of a number. Section 7.0: `not_applicable` and `gated`
 * are not zero. Zero means "we checked and there is no similarity", and writing
 * "0%" next to a recording with no vocals would be a lie [D11].
 */
export const STATE_WORDS: Record<CriterionState, string> = {
  ok: "measured",
  not_applicable: "not applicable",
  gated: "rejected by the confidence gate",
  failed: "unavailable",
  missing: "not measured yet",
};
