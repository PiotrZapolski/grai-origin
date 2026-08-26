/**
 * GRAI ORIGIN evidence visualizations.
 *
 * Every component in this directory keeps one rule: **it draws exclusively what
 * was really computed**. Missing data ends in a sentence, not in a pretty shape -
 * because the whole product is sold on the fact that every number on screen is
 * backed by a measurement, and one chart made out of nothing destroys the
 * credibility of all the other numbers at once.
 */

export { AlignmentMatrix, default as AlignmentMatrixDefault } from "./AlignmentMatrix";
export type { AlignmentMatrixProps } from "./AlignmentMatrix";

export { AlignmentRibbon, spanShare } from "./AlignmentRibbon";
export type { AlignmentRibbonProps } from "./AlignmentRibbon";

export { IngestFilm, ingestData } from "./IngestFilm";
export type { IngestData, IngestFilmProps } from "./IngestFilm";

export { MelodyRuler, readNgrams, intervalContour } from "./MelodyRuler";
export type { MelodyRulerProps, MelodyNgram } from "./MelodyRuler";

export { OffsetHistogram, NOISE_THRESHOLD } from "./OffsetHistogram";
export type { OffsetHistogramProps } from "./OffsetHistogram";

export { SieveField, sieveData } from "./SieveField";
export type { SieveData, SieveFieldProps } from "./SieveField";

export { StreamChronograph, stageLanes, useEventClock } from "./StreamChronograph";
export type { StageLane, StreamChronographProps } from "./StreamChronograph";

export { TranscriptGate, lyricsData } from "./TranscriptGate";
export type { LyricsData, TranscriptWordSpan, TranscriptGateProps } from "./TranscriptGate";

export { VerdictLift, verdictClassFromDetail, changesBetweenVerdicts } from "./VerdictLift";
export type { VerdictLiftProps } from "./VerdictLift";

export * from "./geometry";
export { useAnimatedCanvas, useProgress, useReducedMotion, ease } from "./motion";
