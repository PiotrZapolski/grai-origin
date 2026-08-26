/**
 * Pure evidence geometry. No React, no DOM, no random numbers.
 *
 * **Every function in this file derives its result exclusively from data that
 * really arrived from the API.** There is not a single function here that
 * returns a shape for empty input - missing data ends in `null` or an empty
 * list, and the component is then obliged to **write it out**, not draw it.
 *
 * The slope of the alignment path is computed here rather than measured by a
 * detector, and that is fine: it is an ordinary derivative of a sequence that
 * arrived in the contract, as explicit as the difference between two timecodes.
 * Things that cannot be derived from the contract are not here.
 */

/** A point of the alignment path: the query frame index and the candidate frame index. */
export interface PathPoint {
  q: number;
  c: number;
}

/** `alignment_path` from the envelope of detector B, transcribed into points. */
export function readPath(raw: unknown): PathPoint[] {
  if (!Array.isArray(raw)) return [];
  const points: PathPoint[] = [];
  for (const pair of raw) {
    if (!Array.isArray(pair) || pair.length < 2) continue;
    const [q, c] = pair;
    if (typeof q !== "number" || typeof c !== "number") continue;
    if (!Number.isFinite(q) || !Number.isFinite(c)) continue;
    points.push({ q, c });
  }
  return points;
}

export interface PathExtent {
  /** The number of query frames needed to fit the path. */
  queryFrames: number;
  candidateFrames: number;
}

/** The board size determined by the path. An empty path is zero by zero. */
export function pathExtent(path: readonly PathPoint[]): PathExtent {
  let q = 0;
  let c = 0;
  for (const point of path) {
    if (point.q + 1 > q) q = point.q + 1;
    if (point.c + 1 > c) c = point.c + 1;
  }
  return { queryFrames: q, candidateFrames: c };
}

/** A segment of the path together with its local slope. */
export interface PathSegment {
  from: PathPoint;
  to: PathPoint;
  /**
   * The local tempo ratio: how many candidate frames fall on one query frame.
   * `null` when the segment stands still on the query axis - the quotient does
   * not exist and must not be replaced by one.
   */
  slope: number | null;
}

/**
 * The segments between successive points of the path.
 *
 * A slope of 1.0 means "both recordings run at the same tempo", a value above it
 * means "the candidate moves faster than the query". This is exactly the
 * quantity that detector B reports globally as `tempo_ratio`, only locally, so
 * that you can see **where** the tempo drifted.
 */
export function pathSegments(path: readonly PathPoint[]): PathSegment[] {
  const segments: PathSegment[] = [];
  for (let i = 1; i < path.length; i += 1) {
    const from = path[i - 1];
    const to = path[i];
    const dq = to.q - from.q;
    const dc = to.c - from.c;
    segments.push({ from, to, slope: dq === 0 ? null : dc / dq });
  }
  return segments;
}

/**
 * The average slope of the whole path, or `null`.
 *
 * Computed from the endpoints, not as the mean of the segment slopes: a mean of
 * quotients overweights short segments and with a single vertical step can jump
 * clean off the scale. The quotient of the total increments is what the picture
 * actually shows.
 */
export function pathSlope(path: readonly PathPoint[]): number | null {
  if (path.length < 2) return null;
  const first = path[0];
  const last = path[path.length - 1];
  const dq = last.q - first.q;
  if (dq === 0) return null;
  return (last.c - first.c) / dq;
}

/**
 * A linear scale from a data range onto a pixel range.
 *
 * A zero domain returns the middle of the target range instead of dividing by
 * zero: a single frame is a valid state, not an error.
 */
export function scale(
  value: number,
  fromData: number,
  toData: number,
  fromPixels: number,
  toPixels: number,
): number {
  const domain = toData - fromData;
  if (domain === 0) return (fromPixels + toPixels) / 2;
  return fromPixels + ((value - fromData) / domain) * (toPixels - fromPixels);
}

/** One spike of the offset difference histogram (section 7.1). */
export interface Spike {
  /** The offset difference in seconds. */
  offset: number;
  /** How many hashes fell into this bucket. */
  count: number;
}

/**
 * The histogram spikes from a loose dictionary, or `null`.
 *
 * `null` means: the distribution is not in the evidence. The component then has
 * to write that it is not there - no placeholder shape, because the whole point
 * of this chart is that a sharp spike is proof and a flat distribution is the
 * absence of it. A chart drawn out of nothing would take the meaning away from
 * both cases at once.
 */
export function readSpikes(raw: unknown): Spike[] | null {
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const spikes: Spike[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") return null;
    const record = item as Record<string, unknown>;
    const offset = record.offset;
    const count = record.count;
    if (typeof offset !== "number" || !Number.isFinite(offset)) return null;
    if (typeof count !== "number" || !Number.isFinite(count) || count < 0) return null;
    spikes.push({ offset, count });
  }
  return spikes.length > 0 ? spikes : null;
}

/** The index of the tallest spike, or `null` for empty input. */
export function dominantIndex(spikes: readonly Spike[]): number | null {
  if (spikes.length === 0) return null;
  let best = 0;
  for (let i = 1; i < spikes.length; i += 1) {
    if (spikes[i].count > spikes[best].count) best = i;
  }
  return best;
}

/**
 * The share of the tallest spike in the total - the same quantity that detector
 * A reports as `peak_ratio`. We compute it here only in order to be able to
 * **show agreement** with the number from the contract, never to replace it.
 */
export function dominantShare(spikes: readonly Spike[]): number | null {
  const total = spikes.reduce((sum, spike) => sum + spike.count, 0);
  if (total <= 0) return null;
  const index = dominantIndex(spikes);
  if (index === null) return null;
  return spikes[index].count / total;
}

/* -------------------------------------------------------------------------- */
/* Decorative scatter                                                         */
/* -------------------------------------------------------------------------- */

/**
 * A deterministic 0..1 scatter derived from an index.
 *
 * **This is not data and must never be shown as a number.** It serves solely to
 * spread out the points of a cloud whose **count** is real: the corpus field has
 * as many points as the corpus has entries, and the hash swarm as many as there
 * were matched hashes. Where exactly a single point sits means nothing, and the
 * screen says so.
 *
 * The function is deterministic instead of `Math.random`, because replaying an
 * animation is meant to give the same picture, not a new one - a layout
 * flickering on every render would itself suggest that the measurement had
 * changed.
 */
export function scatter(index: number, seed = 1): number {
  let x = Math.imul(index + 1, 0x9e3779b1) ^ Math.imul(seed + 1, 0x85ebca6b);
  x = Math.imul(x ^ (x >>> 15), 0xc2b2ae35);
  x ^= x >>> 13;
  return ((x >>> 0) % 100000) / 100000;
}

/**
 * The step between the starts of successive analysis windows, or `null`.
 *
 * Computed from two numbers that really arrived in `ingest`: the length of the
 * material and the number of windows. A single window is a valid state with no
 * step - there is nothing to measure a gap between.
 */
export function windowStep(
  duration: number | null,
  windows: number | null,
  windowLength: number,
): number | null {
  if (typeof duration !== "number" || !Number.isFinite(duration) || duration <= 0) return null;
  if (typeof windows !== "number" || !Number.isFinite(windows) || windows < 2) return null;
  const step = (duration - windowLength) / (windows - 1);
  return step > 0 ? step : null;
}
