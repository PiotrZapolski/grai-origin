"use client";

/**
 * The cover art of the original that was found.
 *
 * A YouTube thumbnail is **the real cover of this particular recording**, not a
 * placeholder graphic: the address of the candidate leads to the same video, so
 * the image comes from the same source as the evidence. When the address is not
 * from YouTube or the image fails to load, a tile with the name and the artist
 * remains. No illustration from outside: in an evidentiary tool an image with
 * nothing behind it is the same as a number without a measurement.
 */

import { useEffect, useState } from "react";

import { HEADING_CLASS, MICRO_LABEL_CLASS } from "../../lib/theme";
import { isWebUrl, type SourceCandidate } from "./SourceLink";

/**
 * The video identifier from a YouTube address, or `null`.
 *
 * Three forms are in circulation and all three have to be recognized: `watch?v=`,
 * the shortened `youtu.be/` and `embed/`. Parsed by hand, because `new URL`
 * throws on an address that is not an address, and that is a valid state here,
 * not a failure.
 */
export function youTubeId(url: string | null | undefined): string | null {
  if (typeof url !== "string" || url.length === 0) return null;
  if (!/(^|\.)youtube\.com|(^|\.)youtu\.be/.test(url)) return null;

  const patterns = [
    /[?&]v=([A-Za-z0-9_-]{6,20})/,
    /youtu\.be\/([A-Za-z0-9_-]{6,20})/,
    /\/embed\/([A-Za-z0-9_-]{6,20})/,
    /\/shorts\/([A-Za-z0-9_-]{6,20})/,
  ];
  for (const pattern of patterns) {
    const match = pattern.exec(url);
    if (match) return match[1];
  }
  return null;
}

/**
 * Thumbnail addresses from the best to the most certain.
 *
 * `maxresdefault` exists only for videos uploaded in high resolution and returns
 * 404 for the rest, so on a load error we fall back to `hqdefault`, which is
 * always there. Only after both attempts does the tile remain.
 */
export const THUMBNAIL_LEVELS = ["maxresdefault", "hqdefault"] as const;

/**
 * Cover art fetched in advance and served from our own origin.
 *
 * The first choice, because the show must not depend on whether the room has
 * access to YouTube servers. When the file is missing, `onError` falls back to
 * the external addresses, and only after those to the tile with the name.
 */
export function localCoverUrl(candidateId: string): string {
  return `/covers/${candidateId}.jpg`;
}

export function thumbnailUrl(id: string, level = 0): string {
  const name = THUMBNAIL_LEVELS[Math.min(level, THUMBNAIL_LEVELS.length - 1)];
  return `https://img.youtube.com/vi/${id}/${name}.jpg`;
}

export interface CoverProps {
  candidate: SourceCandidate;
  className?: string;
}

export function Cover({ candidate, className = "" }: CoverProps) {
  const id = youTubeId(candidate.source_url);
  const [level, setLevel] = useState(0);

  // A change of candidate returns to the best thumbnail, otherwise the first
  // failed image would degrade the cover for every entry after it.
  useEffect(() => setLevel(0), [candidate.id]);

  // Level 0 is the local file, the further ones are YouTube addresses.
  const hasImage = level <= THUMBNAIL_LEVELS.length && (level === 0 || id !== null);
  const hasUrl = isWebUrl(candidate.source_url);

  const content = hasImage ? (
    <img
      src={level === 0 ? localCoverUrl(candidate.id) : thumbnailUrl(id as string, level - 1)}
      alt={`Cover: ${candidate.name}, ${candidate.artist}`}
      data-testid="cover-image"
      data-level={level === 0 ? "local" : THUMBNAIL_LEVELS[level - 1]}
      onError={() => setLevel((current) => current + 1)}
      className="h-full w-full max-w-full object-cover"
    />
  ) : (
    <span
      data-testid="cover-tile"
      className="flex h-full w-full flex-col justify-center gap-2 bg-surface p-5"
    >
      <span className={`${MICRO_LABEL_CLASS} text-muted`}>no cover</span>
      <span className={`text-2xl ${HEADING_CLASS}`}>{candidate.name}</span>
      <span className="text-sm text-muted">{candidate.artist}</span>
    </span>
  );

  const shared = "block aspect-video w-full max-w-full overflow-hidden rounded-card border border-muted/25";

  if (!hasUrl) {
    return (
      <div data-testid="cover" className={`${shared} ${className}`}>
        {content}
      </div>
    );
  }

  return (
    <a
      href={candidate.source_url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="cover"
      aria-label={`Open the source: ${candidate.name}, ${candidate.artist}`}
      className={`${shared} transition-colors hover:border-text ${className}`}
    >
      {content}
    </a>
  );
}

export default Cover;
