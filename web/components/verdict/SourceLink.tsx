"use client";

/**
 * The address of the original as a first-class element of the result.
 *
 * The question somebody comes to this tool with is "where is this from", and the
 * answer useful to a human being is **an address that can be opened**, not the
 * name of a work. That is why `candidate.source_url` stands here large,
 * clickable and opened in a new tab - coming back to the result is one tab
 * switch, with no loss of analysis state.
 *
 * The two addresses in the contract are different and **must not be confused**:
 *
 * * `source_url` is the page with the recording, for a human. That is the one we
 *   show here.
 * * `audio_url` is the endpoint serving the file, for the player of screen E4.
 *
 * The release date stands next to the address, because it is what answers the
 * question of why this is the original (section 9.3). It reaches the screen only
 * together with a declared source, exactly as on the E7 axis: a date without a
 * named provenance is the very state both these screens are meant to guard
 * against, because the upload date on a video service is not a release date.
 */

import type { Candidate } from "../../lib/contracts";
import { PUBLISHED_SOURCES } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";

/** The candidate narrowed to the fields the address needs. */
export type SourceCandidate = Pick<
  Candidate,
  "id" | "name" | "artist" | "source_url" | "published" | "published_source"
>;

/**
 * Whether this is an address the browser will open.
 *
 * The contract types `source_url` as an ordinary string, so a local path or an
 * empty string can land there. A dead link in an evidentiary tool is worse than
 * no link: it looks verifiable and leads nowhere.
 */
export function isWebUrl(url: string | null | undefined): url is string {
  if (typeof url !== "string") return false;
  return url.startsWith("https://") || url.startsWith("http://");
}

/** The release date only with a declared provenance. Otherwise `null`. */
export function releaseDate(candidate: SourceCandidate): string | null {
  const { published, published_source: source } = candidate;
  if (typeof published !== "string" || published.length === 0) return null;
  if (!(PUBLISHED_SOURCES as readonly string[]).includes(source ?? "")) return null;
  return published;
}

export interface OriginalLinkProps {
  candidate: SourceCandidate;
  className?: string;
}

/**
 * The address of the original under the verdict card.
 *
 * The element is not lime: the accent belongs to the evidence classes from
 * `ACCENT_CLASSES` and to the active pipeline step, not to every thing that
 * happens to be important (Global Constraint 11). The emphasis here is carried
 * by size, an underline and a frame of its own.
 */
export function OriginalLink({ candidate, className = "" }: OriginalLinkProps) {
  const date = releaseDate(candidate);
  const hasUrl = isWebUrl(candidate.source_url);

  return (
    <section
      data-testid="original-url"
      data-candidate-id={candidate.id}
      aria-label="Address of the original"
      className={`origin-card flex flex-col gap-3 border border-muted/30 p-6 ${className}`}
    >
      <p className={`text-muted ${MICRO_LABEL_CLASS}`}>The source the system points to</p>

      {hasUrl ? (
        <a
          href={candidate.source_url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="original-link"
          className={`break-all text-lg text-text underline decoration-muted underline-offset-4 hover:decoration-text ${TECHNICAL_VALUE_CLASS}`}
        >
          {candidate.source_url}
        </a>
      ) : (
        <p className="text-sm text-muted">
          The manifest gives no page address for this recording, so there is nothing to open.
        </p>
      )}

      {date ? (
        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
          First publication{" "}
          <span data-testid="release-date" className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {date}
          </span>
        </p>
      ) : null}

      {date ? (
        <p className="text-xs text-muted">
          Date from release metadata, not from the video service.
        </p>
      ) : null}
    </section>
  );
}

export interface SourceAddressesProps {
  /** The ranking entries. The first one drops out: it has its own address under the verdict card. */
  candidates: Array<{ rank: number; candidate: SourceCandidate }>;
  selectedId?: string | null;
  className?: string;
}

/**
 * The addresses of the remaining matches, entry by entry.
 *
 * A separate block under the ranking list, not a link inside the entry itself:
 * `RankingList` renders every entry as a `<button>` switching the evidence
 * panel, and a link inside a button is invalid HTML and a trap for a click - the
 * viewer would aim at the address and hit the evidence switch.
 */
export function SourceAddresses({
  candidates,
  selectedId = null,
  className = "",
}: SourceAddressesProps) {
  const rows = candidates.filter((item) => item.rank >= 2);
  if (rows.length === 0) return null;

  return (
    <section data-testid="source-urls" className={className}>
      <h3 className={`${MICRO_LABEL_CLASS} text-muted`}>addresses of the remaining matches</h3>

      <ul className="mt-3 flex flex-col gap-2">
        {rows.map(({ rank, candidate }) => {
          const date = releaseDate(candidate);
          return (
            <li
              key={candidate.id}
              data-testid="entry-url"
              data-candidate-id={candidate.id}
              className={`flex flex-wrap items-baseline gap-x-3 gap-y-1 border-l-2 pl-3 ${
                candidate.id === selectedId ? "border-text" : "border-muted/25"
              }`}
            >
              <span className={`${TECHNICAL_VALUE_CLASS} text-muted`}>{rank}</span>
              <span className="text-sm text-text">{candidate.name}</span>
              {date ? (
                <span className={`${TECHNICAL_VALUE_CLASS} text-xs text-muted`}>{date}</span>
              ) : null}
              {isWebUrl(candidate.source_url) ? (
                <a
                  href={candidate.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`w-full truncate text-xs text-muted underline decoration-muted/60 underline-offset-2 hover:text-text ${TECHNICAL_VALUE_CLASS}`}
                >
                  {candidate.source_url}
                </a>
              ) : (
                <span className="w-full text-xs text-muted">no address in the manifest</span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default OriginalLink;
