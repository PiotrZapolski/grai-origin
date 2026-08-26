import type { Candidate, PublishedSource } from "../../lib/contracts";
import { PUBLISHED_SOURCES } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";

/**
 * Screen E7 - the chronology (sections 13.2, 5.5, 9.3).
 *
 * The axis explains why the original is this one and not that one, so it must
 * not be allowed to lie. It shows **only candidates that have a `published` date
 * from the manifest** [D10]: the upload date on a video service is not a release
 * date, because a recording from 1959 may have been uploaded in 2021 and a cover
 * from 2015 in 2016, so an axis built on such dates would regularly point to the
 * cover as the original - giving the opposite answer to the product's main
 * question in the place that looks the most objective in the whole interface.
 */

/** The candidate narrowed to the fields the axis needs. */
export type TimelineItem = Pick<Candidate, "id" | "name" | "published" | "published_source"> &
  Partial<Pick<Candidate, "artist">>;

export interface TimelineProps {
  items: TimelineItem[];
  /** Highlighting of the entry chosen in the ranking, if it happens to be on the axis. */
  selectedId?: string | null;
  className?: string;
}

/** An entry with a date whose provenance can be named. */
interface DatedItem extends TimelineItem {
  published: string;
  published_source: PublishedSource;
}

function isPublishedSource(value: unknown): value is PublishedSource {
  return typeof value === "string" && (PUBLISHED_SOURCES as readonly string[]).includes(value);
}

/**
 * Only an entry with a date **and** with a named source for that date reaches the
 * axis. A date without a declared provenance is exactly the state this screen is
 * meant to guard against, so it gets no place on the axis - not at the end and
 * not in grey.
 *
 * Lexicographic sorting is correct for ISO dates and treats a year-only date
 * ("1975") as earlier than a full date in the same year, that is, as the start of
 * the interval it certainly lies in.
 */
export function datedItems(items: TimelineItem[]): DatedItem[] {
  return items
    .filter((item): item is DatedItem =>
      typeof item.published === "string" &&
      item.published.length > 0 &&
      isPublishedSource(item.published_source),
    )
    .slice()
    .sort((a, b) => (a.published < b.published ? -1 : a.published > b.published ? 1 : 0));
}

/** A gap proportional to the passage of time, so that the axis is an axis and not a list. */
const MIN_GAP_PX = 14;
const MAX_GAP_PX = 88;

function gapsFor(items: DatedItem[]): number[] {
  const stamps = items.map((item) => Date.parse(item.published));
  const deltas = stamps.map((stamp, index) =>
    index === 0 || !Number.isFinite(stamp) || !Number.isFinite(stamps[index - 1])
      ? 0
      : Math.max(0, stamp - stamps[index - 1]),
  );
  const widest = Math.max(...deltas, 0);
  return deltas.map((delta, index) =>
    index === 0 ? 0 : MIN_GAP_PX + (widest > 0 ? (delta / widest) * (MAX_GAP_PX - MIN_GAP_PX) : 0),
  );
}

/**
 * The chronological axis with the earliest candidate highlighted.
 *
 * When no candidate has a date, the axis **does not render at all**: an empty
 * axis would suggest that the chronology had been checked and nothing followed
 * from it.
 */
export function Timeline({ items, selectedId = null, className = "" }: TimelineProps) {
  const dated = datedItems(items);
  if (dated.length === 0) return null;

  const gaps = gapsFor(dated);

  return (
    <section data-testid="axis" className={`rounded-card border border-muted/20 bg-surface p-6 ${className}`}>
      <h2 className={`${MICRO_LABEL_CLASS} text-muted`}>publication chronology</h2>

      <ol className="relative mt-5 border-l border-muted/30 pl-6">
        {dated.map((item, index) => {
          const earliest = index === 0;
          return (
            <li
              key={item.id}
              data-testid={earliest ? "earliest" : "axis-item"}
              data-candidate-id={item.id}
              data-selected={item.id === selectedId ? "true" : "false"}
              style={{ marginTop: index === 0 ? 0 : gaps[index] }}
              className="relative"
            >
              <span
                aria-hidden="true"
                className={`absolute -left-[27px] top-2 h-2 w-2 rounded-full ${
                  earliest ? "bg-text" : "bg-muted"
                }`}
              />
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <time dateTime={item.published} className={`${TECHNICAL_VALUE_CLASS} text-text`}>
                  {item.published}
                </time>
                <span className={earliest ? "text-text" : "text-muted"}>{item.name}</span>
                {item.artist && <span className="text-sm text-muted">{item.artist}</span>}
              </div>
              {earliest && (
                <p className={`${MICRO_LABEL_CLASS} mt-1 text-muted`}>earliest publication</p>
              )}
            </li>
          );
        })}
      </ol>

      {/*
        Without this paragraph the axis is the most misleading place in the whole
        product: it looks objective and silently suggests that the oldest entry is
        a ruling. Two sentences - first what follows from the axis, then what must
        not be read off it - cost as much as one line and close the whole doubt.
      */}
      <p className="mt-6 max-w-2xl text-sm leading-relaxed text-muted">
        The earliest publication is the most likely original, because the other versions could
        only have come into being after it. That is circumstantial evidence, not proof: the order
        of release does not settle the order of creation, only candidates with a date in the
        manifest stand on the axis, and a work older than all of them may not appear in this set
        at all.
      </p>

      <p className="mt-3 text-sm leading-relaxed text-muted">
        Date from release metadata, not from the video service.
      </p>
    </section>
  );
}

export default Timeline;
