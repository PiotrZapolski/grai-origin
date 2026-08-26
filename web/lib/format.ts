/**
 * Formatting of technical values. One place for the whole frontend.
 *
 * These same functions used to sit in `components/pipeline/format.ts`,
 * `components/ranking/RankingList.tsx`, `components/casefile/CaseFile.tsx`,
 * `components/viz/IngestFilm.tsx` and `components/evidence/AbPlayer.tsx` - each
 * in its own copy. Numbers from the screen end up in tests and in screenshots,
 * so they have to look the same everywhere, and that means one implementation,
 * not five.
 *
 * We do not use `Intl.NumberFormat`, because depending on the ICU version
 * compiled into node it inserts a non-breaking space (U+00A0) or a narrow
 * no-break space (U+202F) as the thousands separator for several locales.
 */

/** 4812 -> "4,812". The fractional part is left untouched, with a full stop. */
export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  const negative = value < 0;
  const [whole, fraction] = Math.abs(value).toString().split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const sign = negative ? "-" : "";
  return fraction ? `${sign}${grouped}.${fraction}` : `${sign}${grouped}`;
}

/**
 * A whole count with a thousands separator: "1,240". Format from section 8.2.
 *
 * It rounds, because a corpus count is a number of items - a fraction next to
 * it would claim a precision that this quantity does not have.
 */
export function formatCount(value: number): string {
  return formatNumber(Math.round(value));
}

/** Seconds in a form the eye can compare: "184.2 s". */
export function formatSeconds(value: number): string {
  return `${formatNumber(Math.round(value * 10) / 10)} s`;
}

/** A 0-1 fraction as a percentage with no illusion of precision: 0.94 -> "94%". */
export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Timecode `m:ss`. A technical value, hence the fixed-width typeface. */
export function formatTimecode(value: number): string {
  const total = Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/**
 * Timecode `m:ss.d`, that is, with tenths of a second.
 *
 * Used where a tenth of a second is the content: the axis of the ingested
 * material and the playhead position of the A/B listen.
 */
export function formatTimecodeTenths(value: number): string {
  const safe = Number.isFinite(value) && value > 0 ? value : 0;
  const minutes = Math.floor(safe / 60);
  const rest = safe - minutes * 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}

/** The shared span of the query, e.g. "common span 0:12-0:41". */
export function formatSpan(span: [number, number]): string {
  return `common span ${formatTimecode(span[0])}-${formatTimecode(span[1])}`;
}

/**
 * Shortens a hash to something that fits on one line. The full value stays in
 * the `title` attribute, because truncating an evidentiary value with no access
 * to the original would be hiding information.
 */
export function shortenHash(value: string, visible = 12): string {
  return value.length > visible * 2
    ? `${value.slice(0, visible)}...${value.slice(-visible)}`
    : value;
}

/**
 * Last resort for a field we do not know by name. The contract says
 * `Record<string, unknown>`, so the screen has to survive any value.
 */
export function formatValue(value: unknown): string {
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (value === null || value === undefined) return "none";
  if (Array.isArray(value)) return value.map(formatValue).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** `asr_confidence` -> "asr confidence". A key outside the dictionary must stay readable. */
export function readableKey(key: string): string {
  return key.replace(/_/g, " ");
}
