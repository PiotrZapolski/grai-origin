"use client";

/**
 * Motion in the visualizations: one source of truth for the timing and for the
 * concession to `prefers-reduced-motion`.
 *
 * Two rules that this module enforces on every component in `viz/`:
 *
 * 1. **Animation does not delay access to information.** Progress is nothing but
 *    a drawing parameter. Every number that matters stands in the DOM from the
 *    first frame - whoever is waiting for a verdict gets the verdict, not a
 *    transition.
 * 2. **With `prefers-reduced-motion: reduce` progress is 1 straight away.**
 *    There is no shortened animation and no intermediate frame: the picture is
 *    ready.
 */

import { useEffect, useRef, useState } from "react";

/** Whether the user asked for reduced motion. SSR and jsdom return `false`. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);

    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    // Safari before 14 has no addEventListener on MediaQueryList.
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    }
    query.addListener(onChange);
    return () => query.removeListener(onChange);
  }, []);

  return reduced;
}

/**
 * Easing of the start and the end. Without it the matrix starts filling with a
 * jerk, and it is precisely the even growth that is the content here, not an
 * ornament.
 */
export function ease(t: number): number {
  const x = Math.min(1, Math.max(0, t));
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

export interface ProgressOptions {
  /** The duration of a full run in milliseconds. */
  duration: number;
  /**
   * A data marker. Changing the marker starts the run from zero, leaving it
   * unchanged does not restart it - otherwise every render would draw the
   * animation anew.
   */
  key: string;
  /** `false` means: there is nothing to animate, progress stands at 1. */
  enabled?: boolean;
}

/**
 * Progress in 0..1 computed on `requestAnimationFrame`.
 *
 * Returns 1 immediately when the user reduces motion or when `enabled` is
 * `false`. The value is **exclusively** a drawing parameter - it never decides
 * whether some number is in the document.
 */
export function useProgress({ duration, key, enabled = true }: ProgressOptions): number {
  const reduced = useReducedMotion();
  const [progress, setProgress] = useState(1);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled || reduced || duration <= 0) {
      setProgress(1);
      return;
    }
    if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") {
      setProgress(1);
      return;
    }

    const start = performance.now();
    setProgress(0);

    const step = (now: number) => {
      const share = Math.min(1, (now - start) / duration);
      setProgress(share);
      if (share < 1) frame.current = window.requestAnimationFrame(step);
    };
    frame.current = window.requestAnimationFrame(step);

    return () => {
      if (frame.current !== null) window.cancelAnimationFrame(frame.current);
      frame.current = null;
    };
  }, [duration, key, enabled, reduced]);

  return progress;
}

/* -------------------------------------------------------------------------- */
/* Canvas                                                                     */
/* -------------------------------------------------------------------------- */

export interface CanvasOptions {
  /** The duration of a full run in milliseconds. */
  duration: number;
  /** Changing the marker starts the run from zero. */
  key: string;
  /** `false` means: there is nothing to animate, we draw the final state once. */
  enabled?: boolean;
  /**
   * Drawing of a single frame. `progress` runs 0..1 over `duration`, `elapsed`
   * is milliseconds since the start and serves exclusively things that are meant
   * to keep breathing once the run has finished.
   */
  draw: (
    ctx: CanvasRenderingContext2D,
    width: number,
    height: number,
    progress: number,
    elapsed: number,
  ) => void;
  /**
   * Whether the loop should keep running after progress reaches one. We turn
   * this on where the final state is itself alive (the pulsing dominant spike),
   * and only there - a frame per second for no reason is warming up the
   * speaker's laptop.
   */
  pulse?: boolean;
}

/**
 * An animated canvas the size of its container.
 *
 * It takes on four things that would otherwise repeat in every component:
 * measuring the container, pixel density, the `requestAnimationFrame` loop and
 * the concession to `prefers-reduced-motion` (a single frame of the final
 * state).
 *
 * **Drawing does not go through React state.** Progress lives in the loop, so
 * hundreds of points do not cost a single render of the tree - the numbers in
 * the DOM stand independently and are readable from the first frame.
 */
export function useAnimatedCanvas({
  duration,
  key,
  enabled = true,
  draw,
  pulse = false,
}: CanvasOptions) {
  const container = useRef<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const drawRef = useRef(draw);
  const reduced = useReducedMotion();
  const [size, setSize] = useState({ width: 0, height: 0 });

  // The drawing function changes identity on every render, and the loop must not
  // restart because of that.
  drawRef.current = draw;

  useEffect(() => {
    const node = container.current;
    if (!node) return;

    const measure = () => setSize({ width: node.clientWidth, height: node.clientHeight });
    measure();

    if (typeof ResizeObserver !== "function") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const { width, height } = size;
    if (width <= 0 || height <= 0) return;

    const ctx = element.getContext("2d");
    if (!ctx) return;

    const density =
      typeof window !== "undefined" ? Math.min(2, window.devicePixelRatio || 1) : 1;
    element.width = Math.round(width * density);
    element.height = Math.round(height * density);

    const frame = (progress: number, elapsed: number) => {
      ctx.setTransform(density, 0, 0, density, 0, 0);
      ctx.clearRect(0, 0, width, height);
      drawRef.current(ctx, width, height, progress, elapsed);
    };

    const still = !enabled || reduced || duration <= 0;
    if (still || typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") {
      frame(1, duration);
      return;
    }

    let handle = 0;
    const start = performance.now();
    const step = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / duration);
      frame(progress, elapsed);
      if (progress < 1 || pulse) handle = window.requestAnimationFrame(step);
    };
    handle = window.requestAnimationFrame(step);

    return () => window.cancelAnimationFrame(handle);
  }, [duration, key, enabled, reduced, pulse, size]);

  return { container, canvas, size, reduced };
}
