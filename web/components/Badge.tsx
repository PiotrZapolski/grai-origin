import type { VerdictClass } from "../lib/contracts";
import { HEADING_CLASS, MICRO_LABEL_CLASS, VERDICT_LABELS, isAccentClass } from "../lib/theme";

export interface BadgeProps {
  verdict: VerdictClass;
  /** The badge of the best match. Outside it the accent is not warranted. */
  best?: boolean;
  className?: string;
}

/**
 * The badge of an evidence class (screen E3).
 *
 * The heading typeface from grai.fm and a micro-label at once - that is a
 * deliberate combination, not a mistake. `.origin-heading` gives the family, the
 * italic and weight 780, while `text-[11px]`, `uppercase` and
 * `tracking-[0.22em]` from the micro-label override it, because Tailwind
 * utilities beat the components layer. What comes out is an editorial stamp: an
 * italic serif in capitals, which is what an evidence class is in the narrative
 * of the product - a seal, not a field caption.
 *
 * Lime is a signal, not decoration (Global Constraint 11). It goes exclusively
 * to a class that is a signal about one specific recording, and only when the
 * badge describes the best match. `COMMON` and `NONE` never get it, because they
 * are not signals but statements.
 */
export function Badge({ verdict, best = false, className = "" }: BadgeProps) {
  const accented = best && isAccentClass(verdict);

  const styles = accented
    ? "border-accent text-accent"
    : "border-muted/40 text-muted";

  return (
    <span
      data-verdict={verdict}
      data-accent={accented ? "true" : "false"}
      className={`inline-flex items-center rounded-inner border px-3 py-1 ${HEADING_CLASS} ${MICRO_LABEL_CLASS} ${styles} ${className}`}
    >
      {VERDICT_LABELS[verdict]}
    </span>
  );
}

export default Badge;
