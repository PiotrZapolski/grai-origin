/**
 * GRAI ORIGIN visual system. Section 13.1 of the specification.
 *
 * Source of truth for the tokens. Tailwind reads this file in
 * `tailwind.config.ts`, so there is no second place where these values live.
 */

import type { VerdictClass } from "./contracts";

export const theme = {
  bg: "#0B0C0A",          // near black with an olive cast
  surface: "#141613",     // cards slightly lighter than the background
  text: "#FFFFFF",
  muted: "#8A8F85",
  accent: "#C8FF3D",      // acid lime - EXCLUSIVELY as a signal
} as const;

export const BRAND = {
  name: "GRAI ORIGIN",
  subtitle: "PROVENANCE ENGINE",
  caseId: "CASE 03",
} as const;

/** Evidence classes -> label in the UI. Section 13.2, screen E3. */
export const VERDICT_LABELS = {
  EXACT: "IDENTICAL RECORDING",
  MODIFIED: "MODIFIED RECORDING",
  VERSION: "SAME WORK",
  EXCERPT_PHONOGRAM: "RECORDING EXCERPT",
  EXCERPT_WORK: "COMPOSITION EXCERPT",
  LYRICS: "LYRICS OVERLAP",
  COMMON: "COMMON ELEMENT",
  NONE: "NO MATCH",
} as const;

/**
 * Lime only for classes that are a signal. Global Constraint 11.
 *
 * The set is narrower than the literal wording of section 13.1 ("lime for the
 * best match") and this is a **decision, not an oversight**: lime has to mean
 * "this is the same recording", not "this is the first row of the list", so the
 * best match of class VERSION does not get the accent.
 */
export const ACCENT_CLASSES = ["EXACT", "EXCERPT_PHONOGRAM"] as const;

export type AccentClass = (typeof ACCENT_CLASSES)[number];

/**
 * Whether a class gets the accent. Lime belongs only to signals concerning one
 * specific recording. `COMMON` and `NONE` never get it, because they are not
 * signals but statements, and `EXCERPT_WORK` is a compositional borrowing, not
 * a hit on the phonogram.
 */
export function isAccentClass(verdict: VerdictClass): verdict is AccentClass {
  return (ACCENT_CLASSES as readonly string[]).includes(verdict);
}

/**
 * Tailwind class for technical values: numeric results, timecodes and hashes.
 * A fixed pitch is the signal that a number comes from a measurement and is not
 * decoration. Section 13.1.
 */
export const TECHNICAL_VALUE_CLASS = "font-mono tabular-nums tracking-tight";

/** Micro-label: uppercase, small size, wide tracking. Section 13.1. */
export const MICRO_LABEL_CLASS = "text-[11px] uppercase tracking-[0.22em]";

/**
 * A micro-label that **is a signal**, the only case in which uppercase text
 * gets lime.
 *
 * Section 13.1 reads literally as "micro-labels in uppercase lime", but it
 * collides with Global Constraint 11 ("lime exclusively as a signal, never
 * decoration"), which takes precedence. There are dozens of micro-labels across
 * the screens and most of them are field captions - painting them all lime
 * turns the accent into the colour of secondary text and destroys the signal
 * where it really means something.
 *
 * Decision: a field caption is `MICRO_LABEL_CLASS` in the `muted` colour, and
 * `SIGNAL_LABEL_CLASS` goes exclusively to a label describing the active step,
 * an alert or the best match - the three cases that section 13.1 itself lists
 * as reserved for lime.
 */
export const SIGNAL_LABEL_CLASS = `${MICRO_LABEL_CLASS} text-accent`;

/**
 * Heading: heavy, italic serif with an editorial character.
 *
 * **A hybrid.** The skeleton stays from the hackathon brief (dark background,
 * lime as a signal, the circle motif), but the heading typeface comes from the
 * real grai.fm site, so the demo sounds like **grai** and not like any other
 * dark dashboard. The brief spoke of a "very heavy sans-serif"; the real brand
 * sets its headings in Fraunces italic 780 condensed to 85%. The brand wins.
 *
 * The whole recipe lives in the `.origin-heading` class in `app/globals.css`,
 * because it is five properties at once (family, style, weight, width,
 * tracking) and none of them makes sense without the others. The component adds
 * only the size on top, e.g. `text-4xl ${HEADING_CLASS}`.
 *
 * **Does not apply** to the interface typeface or to technical values: those
 * keep `font-sans` and `TECHNICAL_VALUE_CLASS` respectively.
 */
export const HEADING_CLASS = "origin-heading";
