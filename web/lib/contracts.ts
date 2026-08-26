/**
 * Mirror types of the API contracts.
 *
 * **The source of truth is `src/origin/contracts.py`, not this file.** Every
 * field below is transcribed by hand from that module, and the real payload
 * shapes can be inspected in `src/origin/api/mock.py`. A change on the Python
 * side requires a change here and the other way round.
 *
 * The frontend imports nothing from Python - the only contact point is HTTP and
 * SSE.
 *
 * The rule when transcribing: what pydantic has as `X | None` is `X | null`
 * here; what has a default value is **always present on the wire**
 * (model_dump emits the full set of fields), so it does not get a question
 * mark.
 */

/* -------------------------------------------------------------------------- */
/* Dictionaries                                                               */
/* -------------------------------------------------------------------------- */

/** Section 7.0. The same dictionary governs the envelope and a single result. */
export const DETECTOR_STATUSES = ["ok", "not_applicable", "gated", "failed"] as const;
export type DetectorStatus = (typeof DETECTOR_STATUSES)[number];

/**
 * Eight evidence classes. Section 3 splits `EXCERPT` into two variants, because
 * they have different legal consequences and different exposure to the
 * commonality filter. Plain `EXCERPT` is not a valid value - the notation
 * `EXCERPT/phonogram` in the text of the specification is a human-readable
 * form.
 */
export const VERDICT_CLASSES = [
  "EXACT",
  "MODIFIED",
  "VERSION",
  "EXCERPT_PHONOGRAM",
  "EXCERPT_WORK",
  "LYRICS",
  "COMMON",
  "NONE",
] as const;
export type VerdictClass = (typeof VERDICT_CLASSES)[number];

/**
 * The rights layer. Section 11.1: the rightsholders and the terms of protection
 * differ for each of them, so the same number means something else.
 *
 * There is no "none" value here. An absent layer is written as `null` and that
 * is exactly what the backend sends for `COMMON` and `NONE`.
 */
export const RIGHTS_LAYERS = ["phonogram", "work", "performance"] as const;
export type RightsLayer = (typeof RIGHTS_LAYERS)[number];

/** Section 5.5: a YouTube upload date is not a release date and is forbidden. */
export const PUBLISHED_SOURCES = ["manual", "metadata_registry"] as const;
export type PublishedSource = (typeof PUBLISHED_SOURCES)[number];

/** Section 10.5: the UI must visually distinguish these two states. */
export const PROBABILITY_STATUSES = ["calibrated", "uncalibrated"] as const;
export type ProbabilityStatus = (typeof PROBABILITY_STATUSES)[number];

export const RESULT_STATUSES = ["partial", "final", "failed"] as const;
export type ResultStatus = (typeof RESULT_STATUSES)[number];

export const STAGE_STATUSES = ["running", "done", "partial", "final", "gated", "failed"] as const;
export type StageStatus = (typeof STAGE_STATUSES)[number];

/**
 * The four criteria of screen E5: recording, harmony, melody, lyrics. No rhythm
 * and no video - there is no detector behind them, and a bar without a detector
 * is a prop.
 */
export const DETECTOR_KEYS = ["fingerprint", "harmonic", "melodic", "lyrics"] as const;
export type DetectorKey = (typeof DETECTOR_KEYS)[number];

/**
 * The discriminant of the union over detector results. `generic` is given to
 * the base result, which carries no measurement fields at all.
 */
export const DETECTOR_TAGS = [
  "fingerprint",
  "harmonic",
  "lyrics",
  "melodic",
  "generic",
] as const;
export type DetectorTag = (typeof DETECTOR_TAGS)[number];

/* -------------------------------------------------------------------------- */
/* Detector results, section 7.0                                              */
/* -------------------------------------------------------------------------- */

/**
 * The shared part of a result for one candidate.
 *
 * When `status` is anything other than `ok`, the Python contract **forbids** the
 * presence of any measurement field: `not_applicable` and `gated` are not zero.
 * The frontend therefore receives nothing but nulls and has to show a worded
 * state, not a number.
 */
export interface DetectorResultBase {
  detector: DetectorTag;
  candidate_id: string;
  status: DetectorStatus;
  reason: string | null;
}

/** The base result, with no measurement fields. */
export interface GenericDetectorResult extends DetectorResultBase {
  detector: "generic";
}

/** Detector A - acoustic fingerprint. */
export interface FingerprintResult extends DetectorResultBase {
  detector: "fingerprint";
  matched_hashes: number | null;
  peak_ratio: number | null;
  query_span: [number, number] | null;
  candidate_span: [number, number] | null;
  offset: number | null;
  repetitions: number;
  transform: Record<string, number> | null;
}

/** Detector B - harmonic similarity. Also reports tempo_ratio. */
export interface HarmonicResult extends DetectorResultBase {
  detector: "harmonic";
  qmax_score: number | null;
  transposition: number | null;
  tempo_ratio: number | null;
  alignment_path: Array<[number, number]>;
  coverage: number | null;
  chord_sequence: string[];
}

/** Detector D - lyrics. */
export interface LyricsResult extends DetectorResultBase {
  detector: "lyrics";
  jaccard: number | null;
  semantic_sim: number | null;
  /**
   * `list[dict[str, Any]]` in Python. One entry per common run, carrying
   * `query_len` and `candidate_len` (character lengths), `query_time` and
   * `idf`. The engine never sends the words themselves - lyric text is
   * redacted to a length before the result leaves the process, because these
   * results are dumped whole onto the public SSE stream. Only the mock still
   * carries its own invented `query`, `candidate`, `text` shape.
   */
  matched_spans: Array<Record<string, unknown>>;
  asr_confidence: number | null;
  language: string | null;
  used_separation: boolean;
}

/** Detector C - symbolic melody. */
export interface MelodicResult extends DetectorResultBase {
  detector: "melodic";
  /** `list[dict[str, Any]]` in Python. The mock carries `query_start`, `candidate_start`, `n`, `intervals`. */
  matched_ngrams: Array<Record<string, unknown>>;
  longest_common_run: number;
  ms_distance: number | null;
  /**
   * Whether the query melody was read from the separated vocal track or from
   * the full mix. `false` means detector D's confidence gate passed on the
   * first pass, so no separation existed to share (section 7.4 step 1) and the
   * transcription also heard drums and accompaniment - the distance has to be
   * read with that in mind.
   */
  used_separation: boolean;
}

/** The union discriminated by the `detector` field. Narrow via `result.detector === "harmonic"`. */
export type AnyDetectorResult =
  | FingerprintResult
  | HarmonicResult
  | LyricsResult
  | MelodicResult
  | GenericDetectorResult;

/**
 * The detector envelope. The envelope status covers the run for the **whole
 * query**, the result status covers a single candidate. Both are mandatory
 * (section 7.0).
 *
 * Envelopes reach the frontend in `StreamEvent.detail.envelope`.
 */
export interface DetectorEnvelope {
  detector: string;
  status: DetectorStatus;
  reason: string | null;
  results: AnyDetectorResult[];
}

/* -------------------------------------------------------------------------- */
/* Candidate, section 5.3                                                     */
/* -------------------------------------------------------------------------- */

export interface Candidate {
  id: string;
  name: string;
  artist: string;
  shs_performance_id: string | null;
  source_url: string;
  /** Path on the server disk. Playback uses `audio_url`, not this field. */
  audio_path: string;
  /**
   * The address at which the API will serve this recording for the A/B listen
   * on screen E4. `null` means: the file is not on disk, so there is nothing to
   * play. We do not substitute a placeholder sound - in an evidentiary tool a
   * prop is worse than its absence. The field is always on the wire: in Python
   * it has a default value, and the API layer fills it in for the manifest.
   */
  audio_url: string | null;
  /**
   * The date of first publication from the manifest. `null` is a valid state,
   * not missing data: the chronology rule from 9.3 applies exclusively to
   * candidates that have a date, and only they appear on the axis of screen E7.
   */
  published: string | null;
  published_source: PublishedSource | null;
  license: string;
  instrumental: boolean;
  language: string | null;
  lyrics_path: string | null;
}

/** The `data/candidates/<set_id>.json` manifest. */
export interface CandidateSet {
  set_id: string;
  candidates: Candidate[];
}

/* -------------------------------------------------------------------------- */
/* Components of a ranking entry                                              */
/* -------------------------------------------------------------------------- */

/**
 * Where and how the query was aligned to the candidate.
 *
 * Every field is independently optional: a match based on lyrics alone has no
 * time alignment, and a fingerprint match has no transposition.
 */
export interface Alignment {
  query_span: [number, number] | null;
  candidate_span: [number, number] | null;
  transposition: number | null;
  tempo_ratio: number | null;
}

/** The commonality filter, section 8. The numbers are optional, because there may be no corpus. */
export interface Commonality {
  mean_idf: number | null;
  corpus_frequency: number | null;
  corpus_size: number | null;
}

/** Evidence flags, never a ruling on infringement. Section 11.3. */
export interface Legal {
  /**
   * The full set of rights layers the match concerns. `VERSION` gets
   * `["work", "performance"]` here, because it touches two layers at once,
   * whereas `RankingEntry.verdict_layer` carries only the leading layer.
   */
  rights_layer: RightsLayer[];
  risk_flags: string[];
  recognizability: number | null;
  modification: number | null;
  /** `unknown` means no information, never no restrictions. */
  license_status: string;
  required_attribution: string | null;
  /** Always present. The note that this is not legal advice, for panel E8. */
  disclaimer: string;
}

/**
 * A summary of the envelope next to a ranking entry. The frontend cannot assume
 * that the detector returned a number, so the status is mandatory. There is no
 * field with a numeric result here - the numbers sit in the detector envelopes.
 */
export interface Evidence {
  status: DetectorStatus;
  reason: string | null;
}

/**
 * The evidence map next to a ranking entry.
 *
 * **A missing key means "not measured yet", not "zero".** Level 1 really sends
 * two keys (`fingerprint`, `harmonic`), the full set of four appears only after
 * level 2. Screen E5 has to show waiting, not the bar of a detector that has
 * not started.
 *
 * In Python this is `dict[str, Evidence]`, so an index signature is more
 * faithful here than a closed set of keys.
 */
export type EvidenceMap = Partial<Record<DetectorKey, Evidence>> & {
  [detector: string]: Evidence | undefined;
};

export interface RankingEntry {
  rank: number;
  candidate: Candidate;
  verdict_class: VerdictClass;
  /**
   * The **leading** layer, deliberately singular. The full set of layers is
   * carried by `legal.rights_layer`. `null` is valid and is exactly what
   * arrives for `COMMON` and `NONE`, which concern no rights layer at all
   * (section 3).
   */
  verdict_layer: RightsLayer | null;
  /** `null` when the system has nothing to state. Zero would mean "definitely not". */
  probability: number | null;
  probability_status: ProbabilityStatus;
  evidence: EvidenceMap;
  alignment: Alignment | null;
  commonality: Commonality | null;
  /** Never `null`: an empty `Legal` is the valid "we know nothing" state. */
  legal: Legal;
  /**
   * Never `null`: in Python this is `str = ""`, and a missing description
   * arrives as an empty string. Allowing `null` here would force the screens to
   * check two states that are one on the wire.
   */
  explanation: string;
}

/* -------------------------------------------------------------------------- */
/* Job result                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * A transcript word. In Python `QueryInfo.transcript` is typed as
 * `list[dict[str, Any]]`; these three keys are what the engine really sends.
 * The index signature leaves room for fields we do not know yet.
 */
export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
  [key: string]: unknown;
}

export interface QueryInfo {
  duration: number;
  waveform_url: string | null;
  transcript: TranscriptWord[];
}

/** Section 10. The absence of this object means: no model exists, the numbers are raw. */
export interface CalibrationInfo {
  model_version: string;
  trained_on: number;
  precision_at_threshold: number | null;
}

export interface AnalyzeResult {
  status: ResultStatus;
  completed_levels: number[];
  query: QueryInfo;
  ranking: RankingEntry[];
  calibration: CalibrationInfo | null;
}

/**
 * The 202 response of `GET /api/jobs/{id}/result`: the job exists, but there is
 * nothing to show yet. This is not an `AnalyzeResult` and must not be read as
 * one.
 */
export interface PendingResult {
  job_id: string;
  status: "pending";
}

/* -------------------------------------------------------------------------- */
/* SSE stream                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * Pipeline stages in order of appearance - they feed the vertical list of E2.
 * The list is **a hint for the UI, not a constraint of the contract**: in
 * Python `stage` is an ordinary string, so the screen has to survive a stage
 * outside this list.
 */
export const PIPELINE_STAGES = [
  "ingest",
  "fingerprint",
  "harmonic",
  "shortlist",
  "commonality",
  "verdict",
  "transcript",
  "separation",
  "melodic",
] as const;
export type PipelineStage = (typeof PIPELINE_STAGES)[number];

export interface StreamEvent {
  stage: string;
  /** 1 - the fast path, 2 - the deepening. The verdict comes from both levels. */
  level: number;
  status: StageStatus;
  detail: Record<string, unknown>;
}

/* -------------------------------------------------------------------------- */
/* Shapes of HTTP requests and responses                                      */
/* -------------------------------------------------------------------------- */

export interface AnalyzeRequest {
  url: string;
  /** On the Python side it defaults to `demo_01`; the client always sends it. */
  candidate_set: string;
}

export interface AnalyzeResponse {
  job_id: string;
}

export interface ExplainRequest {
  job_id: string;
  candidate_id: string;
}

export interface ExplainResponse {
  explanation: string;
}

/** `GET /api/health` - the frontend has to see the difference between the engine and the mock. */
export interface HealthResponse {
  status: string;
  mock: boolean;
  /**
   * The keywords the mock recognises in the query address. Screen E1 builds its
   * examples from them instead of guessing what the mock can do.
   */
  mock_scenarios: string[];
}

/* -------------------------------------------------------------------------- */
/* Type narrowing                                                             */
/* -------------------------------------------------------------------------- */

/** Guards against a typo in the JSON before it reaches the label map. */
export function isVerdictClass(value: unknown): value is VerdictClass {
  return typeof value === "string" && (VERDICT_CLASSES as readonly string[]).includes(value);
}

export function isRightsLayer(value: unknown): value is RightsLayer {
  return typeof value === "string" && (RIGHTS_LAYERS as readonly string[]).includes(value);
}

export function isPipelineStage(value: unknown): value is PipelineStage {
  return typeof value === "string" && (PIPELINE_STAGES as readonly string[]).includes(value);
}
