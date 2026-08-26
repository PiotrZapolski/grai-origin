"use client";

/**
 * A/B listening - the single most important element of the whole interface
 * (section 13.2).
 *
 * The brief demands a way to check, and for audio the only real verification is
 * the ear: the jury has to **hear** that this is the same recording. No chart
 * replaces that, which is why this panel must not be cut at any rung of the
 * fallback ladder.
 *
 * The entire synchronization sits in a single number. The position is always
 * expressed **in the time axis of the query**; the candidate plays at the same
 * musical moment, shifted by the `offset` from the alignment
 * (`candidate_span[0] - query_span[0]`). Switching A/B zeroes nothing and does
 * not start from the beginning - that would be switching to the wrong position,
 * that is, losing the evidence.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { formatTimecodeTenths } from "../../lib/format";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";

export type Source = "A" | "B";

export interface AbPlayerProps {
  queryUrl: string;
  candidateUrl: string;
  /** The offset of the candidate relative to the query, in seconds. */
  offset: number;
  /** The common span in the query axis. It sets the starting point of the listen. */
  querySpan?: [number, number] | null;
  /** The common span in the candidate axis. Used for the caption, not for computing the position. */
  candidateSpan?: [number, number] | null;
  /** The length of the query. Without it the slider has no honest range. */
  queryDuration?: number | null;
  /** A seek requested from the outside (e.g. clicking a phrase in the lyrics panel). */
  position?: number;
  onPositionChange?: (position: number) => void;
  className?: string;
}

/**
 * The candidate position for a given query position.
 *
 * The clamp to zero covers a negative offset, that is, the case in which the
 * candidate starts later than the query. Negative time does not exist, and
 * falling back to zero is the only sensible behaviour.
 */
export function candidatePosition(queryPosition: number, offset: number): number {
  return Math.max(0, queryPosition + offset);
}

export function AbPlayer({
  queryUrl,
  candidateUrl,
  offset,
  querySpan = null,
  candidateSpan = null,
  queryDuration = null,
  position,
  onPositionChange,
  className = "",
}: AbPlayerProps) {
  const queryRef = useRef<HTMLAudioElement | null>(null);
  const candidateRef = useRef<HTMLAudioElement | null>(null);

  // Listening starts where the evidence starts, not at the beginning of the file.
  const [playhead, setPlayhead] = useState(() => querySpan?.[0] ?? 0);
  const [source, setSource] = useState<Source>("A");
  const [playing, setPlaying] = useState(false);
  const [length, setLength] = useState<number | null>(queryDuration);

  useEffect(() => {
    if (queryDuration !== null) setLength(queryDuration);
  }, [queryDuration]);

  const positionB = candidatePosition(playhead, offset);

  /** Writes the position onto an audio element. jsdom does not play, but it sees the number. */
  const assignTime = useCallback((element: HTMLAudioElement | null, time: number) => {
    if (!element) return;
    try {
      element.currentTime = time;
    } catch {
      // The browser rejects a seek before the metadata has loaded. The position
      // stays in React state and will be applied on the next move.
    }
  }, []);

  const movePlayhead = useCallback(
    (next: number) => {
      setPlayhead(next);
      assignTime(queryRef.current, next);
      assignTime(candidateRef.current, candidatePosition(next, offset));
      onPositionChange?.(next);
    },
    [offset, onPositionChange, assignTime],
  );

  // A seek requested from the outside, e.g. clicking a common phrase in the lyrics.
  useEffect(() => {
    if (position === undefined) return;
    setPlayhead(position);
    assignTime(queryRef.current, position);
    assignTime(candidateRef.current, candidatePosition(position, offset));
  }, [position, offset, assignTime]);

  const play = useCallback((element: HTMLAudioElement | null) => {
    const promise = element?.play();
    // Playback can be rejected by the autoplay policy. That is not a reason to
    // bring the panel down.
    if (promise && typeof promise.catch === "function") promise.catch(() => undefined);
  }, []);

  const toggleSource = useCallback(() => {
    const next: Source = source === "A" ? "B" : "A";
    const incoming = next === "A" ? queryRef.current : candidateRef.current;
    const outgoing = next === "A" ? candidateRef.current : queryRef.current;

    outgoing?.pause();
    // The crucial moment: the new source gets the **shared instant**, not zero.
    assignTime(incoming, next === "A" ? playhead : candidatePosition(playhead, offset));
    if (playing) play(incoming);
    setSource(next);
  }, [play, playing, offset, playhead, assignTime, source]);

  const togglePlayback = useCallback(() => {
    const active = source === "A" ? queryRef.current : candidateRef.current;
    if (playing) {
      active?.pause();
      setPlaying(false);
      return;
    }
    assignTime(active, source === "A" ? playhead : candidatePosition(playhead, offset));
    play(active);
    setPlaying(true);
  }, [play, playing, offset, playhead, assignTime, source]);

  const range = length ?? 0;

  return (
    <div className={`flex flex-col gap-4 ${className}`} data-testid="ab-listen">
      <audio
        ref={queryRef}
        data-testid="query-audio"
        data-playing={playing && source === "A" ? "true" : "false"}
        src={queryUrl}
        preload="metadata"
        onLoadedMetadata={(event) => {
          const measured = event.currentTarget.duration;
          if (queryDuration === null && Number.isFinite(measured)) setLength(measured);
        }}
      />
      <audio
        ref={candidateRef}
        data-testid="candidate-audio"
        data-playing={playing && source === "B" ? "true" : "false"}
        src={candidateUrl}
        preload="metadata"
      />

      <div className="flex flex-wrap items-center gap-3">
        {/*
          Listening is the heart of the show, so both buttons are larger than the
          rest of the controls in the product. Neither of them is lime: the source
          switch is interface state, not the best match, an alert or an active
          pipeline step (Global Constraint 11). The state is carried by full
          contrast and a fill that reads from the back of the room.
        */}
        <button
          type="button"
          onClick={togglePlayback}
          className={`rounded-full border border-muted/40 px-6 py-3 ${MICRO_LABEL_CLASS}`}
        >
          {playing ? "PAUSE" : "PLAY"}
        </button>

        <button
          type="button"
          onClick={toggleSource}
          aria-label="Switch A/B listening at the synchronized point"
          data-source={source}
          className={`rounded-full border px-6 py-3 ${MICRO_LABEL_CLASS} ${
            source === "B" ? "border-text bg-text/10 text-text" : "border-muted/40 text-text"
          }`}
        >
          SWITCH A/B
        </button>

        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
          SOURCE{" "}
          <span data-testid="active-source" className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {source}
          </span>
        </p>

        <p className={`ml-auto text-muted ${MICRO_LABEL_CLASS}`}>
          {source === "A" ? "QUERY" : "CANDIDATE"}{" "}
          <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {formatTimecodeTenths(source === "A" ? playhead : positionB)}
          </span>
        </p>
      </div>

      <input
        type="range"
        aria-label="Listening point"
        min={0}
        max={range || 1}
        step={0.01}
        value={playhead}
        disabled={range <= 0}
        onChange={(event) => movePlayhead(Number(event.target.value))}
        // `accent-text`, not `accent-accent`: the slider is a control, not an
        // evidentiary signal.
        className="w-full accent-text disabled:opacity-40"
      />

      {range <= 0 ? (
        <p className="text-xs text-muted">
          The length of the recording is unknown, the slider is waiting for metadata. The A/B
          switch works.
        </p>
      ) : null}

      {/*
        Both numbers stand on screen, because they are the proof of the
        synchronization: if B is not shifted by the offset, it is visible at a
        glance.
      */}
      <dl className={`grid grid-cols-2 gap-2 text-muted ${MICRO_LABEL_CLASS}`}>
        <div>
          <dt>POINT A / QUERY</dt>
          <dd data-testid="position-a" className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {playhead.toFixed(2)}
          </dd>
        </div>
        <div>
          <dt>POINT B / CANDIDATE</dt>
          <dd data-testid="position-b" className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
            {positionB.toFixed(2)}
          </dd>
        </div>
      </dl>

      {querySpan && candidateSpan ? (
        <p className="text-xs text-muted">
          Common span: query {formatTimecodeTenths(querySpan[0])} to {formatTimecodeTenths(querySpan[1])},
          candidate {formatTimecodeTenths(candidateSpan[0])} to {formatTimecodeTenths(candidateSpan[1])}.
        </p>
      ) : null}
    </div>
  );
}

export default AbPlayer;
