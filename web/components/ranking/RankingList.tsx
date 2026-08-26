import type { DetectorKey, RankingEntry } from "../../lib/contracts";
import { DETECTOR_KEYS } from "../../lib/contracts";
import { formatPercent, formatSpan } from "../../lib/format";
import { CRITERION_LABELS, STATE_WORDS, type CriterionState } from "../../lib/labels";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS, isAccentClass } from "../../lib/theme";
import { Badge } from "../Badge";

/**
 * Screen E6 - the ranking (sections 13.2, 10.5).
 *
 * Entries 2-N with their evidence class, probability and a thumbnail of the
 * similarity profile. A click switches the evidence panel, which belongs to
 * another screen (E4), so this component does not render it - it exposes
 * `onSelect`.
 */

export interface RankingListProps {
  /**
   * The full ranking or just its tail. Entry number 1 is skipped either way: the
   * best match has its own verdict card on screen E3, and repeated on the list it
   * would read as a second, separate hit.
   */
  entries: RankingEntry[];
  /** The candidate whose evidence is currently open. */
  selectedId?: string | null;
  onSelect?: (candidateId: string) => void;
  className?: string;
}

/**
 * The thumbnail of the similarity profile: four cells, one per detector.
 *
 * The fill says only **whether** a detector computed a result, not how much came
 * out. The numbers sit in the detector envelopes, not next to the ranking entry
 * (section 7.0), so a thumbnail pretending to show levels would be a prop.
 */
function ProfileThumbnail({ entry }: { entry: RankingEntry }) {
  const states: Array<{ key: DetectorKey; state: CriterionState }> = DETECTOR_KEYS.map((key) => {
    const item = entry.evidence?.[key];
    return { key, state: item === undefined ? "missing" : item.status };
  });

  const summary = states
    .map(({ key, state }) => `${CRITERION_LABELS[key]}: ${STATE_WORDS[state]}`)
    .join(", ");

  return (
    <span
      role="img"
      aria-label={`similarity profile. ${summary}`}
      data-testid="profile-thumbnail"
      className="flex items-end gap-1"
    >
      {states.map(({ key, state }) => (
        <span
          key={key}
          data-criterion={key}
          data-state={state}
          className={`h-4 w-2 border ${
            state === "ok" ? "border-text bg-text" : "border-muted/50 bg-transparent"
          }`}
        />
      ))}
    </span>
  );
}

/**
 * The probability in the language of the screen (section 10.5).
 *
 * `null` does not turn into zero: zero would mean "definitely not", and the
 * system simply has nothing to state. Uncalibrated classes get an explicit label
 * instead of a number pretending to be confidence.
 */
function Probability({ entry }: { entry: RankingEntry }) {
  if (entry.probability === null) {
    return <span className={`${MICRO_LABEL_CLASS} text-muted`}>probability not determined</span>;
  }

  const percent = formatPercent(Math.min(1, Math.max(0, entry.probability)));
  const uncalibrated = entry.probability_status === "uncalibrated";

  return (
    <span className="flex flex-col items-end gap-1">
      <span className={`${TECHNICAL_VALUE_CLASS} text-text`}>{percent}</span>
      <span className={`${MICRO_LABEL_CLASS} text-muted`}>
        {uncalibrated ? "preliminary threshold, no calibration data" : "calibrated confidence"}
      </span>
    </span>
  );
}

/**
 * The list of entries 2-N. An empty list renders nothing: a heading over zero
 * entries would suggest that something failed to load.
 */
export function RankingList({
  entries,
  selectedId = null,
  onSelect,
  className = "",
}: RankingListProps) {
  const tail = entries.filter((entry) => entry.rank >= 2);
  if (tail.length === 0) return null;

  return (
    <section data-testid="ranking" className={className}>
      <h2 className={`${MICRO_LABEL_CLASS} text-muted`}>remaining matches</h2>

      <ul className="mt-4 flex flex-col gap-2">
        {tail.map((entry) => {
          const candidate = entry.candidate;
          const selected = candidate.id === selectedId;
          // Lime exclusively for classes from ACCENT_CLASSES (Global Constraint
          // 11): a second hit on the same recording is an alert, not an ornament
          // for a position on a list. A selected entry is signalled by its frame,
          // not by the accent.
          const accented = isAccentClass(entry.verdict_class);

          return (
            <li key={candidate.id}>
              <button
                type="button"
                data-testid="ranking-entry"
                data-candidate-id={candidate.id}
                data-accent={accented ? "true" : "false"}
                aria-pressed={selected}
                onClick={() => onSelect?.(candidate.id)}
                className={`flex w-full items-center gap-4 rounded-card border bg-surface/70 px-5 py-4 text-left ${
                  selected ? "border-text" : "border-muted/20"
                } ${accented ? "border-l-2 border-l-accent" : ""}`}
              >
                <span className={`${TECHNICAL_VALUE_CLASS} w-8 shrink-0 text-muted`}>
                  {entry.rank}
                </span>

                <span className="flex min-w-0 flex-col gap-1">
                  <span className="truncate text-text">{candidate.name}</span>
                  <span className="truncate text-sm text-muted">{candidate.artist}</span>
                  {entry.alignment?.query_span && (
                    <span className={`${TECHNICAL_VALUE_CLASS} text-xs text-muted`}>
                      {formatSpan(entry.alignment.query_span)}
                    </span>
                  )}
                </span>

                <span className="ml-auto flex shrink-0 items-center gap-5">
                  <ProfileThumbnail entry={entry} />
                  <Badge verdict={entry.verdict_class} />
                  <Probability entry={entry} />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default RankingList;
