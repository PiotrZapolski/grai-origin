/**
 * The three prepared examples of screen E1.
 *
 * Section 14: **every demo case has to work from local files, not from URLs** -
 * that is the only safeguard against there being no internet in the room. Each
 * example therefore has two paths and both of them are local:
 *
 * - `queryUrl` goes to `POST /api/analyze` and is a path in the repository that
 *   ingest reads from the server disk;
 * - `assetUrl` serves the browser alone, for drawing the waveform, and lies on
 *   the same origin, in `web/public/examples/`.
 *
 * None of these addresses reaches the public network. A missing file at
 * `assetUrl` does not break the screen: the waveform stays in its placeholder
 * state.
 *
 * The order is dramaturgical, the same as in section 14: the system works ->
 * the system understands the difference between a work and a phonogram -> the
 * system has judgement.
 */

import type { VerdictClass } from "../../lib/contracts";

export interface Example {
  id: string;
  /** A short name on the button. */
  label: string;
  /** One sentence about what this case proves. */
  description: string;
  /** The class we expect. The label comes from VERDICT_LABELS. */
  expected: VerdictClass;
  /** A local path for the backend. Never an http address. */
  queryUrl: string;
  /** An asset on the same origin, for the waveform in the browser. */
  assetUrl: string;
  candidateSet: string;
}

export const EXAMPLES: readonly Example[] = [
  {
    id: "case-01-exact",
    label: "REUPLOAD",
    description: "The same material uploaded again, after recompression.",
    expected: "EXACT",
    queryUrl: "data/queries/case-01-exact.wav",
    assetUrl: "/examples/case-01-exact.mp3",
    candidateSet: "demo_01",
  },
  {
    id: "case-02-version",
    label: "COVER",
    description: "A different recording of the same work - a different phonogram, the same composition.",
    expected: "VERSION",
    queryUrl: "data/queries/case-02-version.wav",
    assetUrl: "/examples/case-02-version.mp3",
    candidateSet: "demo_01",
  },
  {
    id: "case-05-common",
    label: "TRAP",
    description: "The same progression and tempo, but a different work. The system is meant to reject it.",
    expected: "COMMON",
    queryUrl: "data/queries/case-05-common.wav",
    assetUrl: "/examples/case-05-common.mp3",
    candidateSet: "demo_01",
  },
];
