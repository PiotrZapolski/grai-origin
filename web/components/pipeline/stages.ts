/**
 * The dictionary of pipeline stages and the translation of `detail` into facts
 * for screen E2.
 *
 * The rule of the screen: **every step shows what it produced, not that it is
 * running** (section 13.2). A step in progress that has nothing yet at least
 * names the activity it is performing - because that is exactly what separates a
 * "spinner" from a "show".
 *
 * On the Python side `stage` is an ordinary string and `detail` is a dictionary
 * of arbitrary content (section 12). Every unknown field therefore has a fallback
 * path here: it goes to the bottom of the row as a key-value pair instead of
 * disappearing.
 */

import type { StageStatus, StreamEvent } from "../../lib/contracts";
import { isVerdictClass } from "../../lib/contracts";
import { VERDICT_LABELS } from "../../lib/theme";
import {
  formatNumber,
  formatPercent,
  formatSeconds,
  formatValue,
  readableKey,
  shortenHash,
} from "../../lib/format";

/**
 * An event exactly as it comes off the wire. `status` is deliberately looser
 * than `StageStatus`: the engine may add a state that the dictionary of section
 * 12 does not have yet, and the screen has to survive it instead of taking the
 * show down.
 */
export interface PipelineEvent extends Omit<StreamEvent, "status"> {
  status: StageStatus | (string & {});
}

/** One measured value in a stage row. */
export interface Fact {
  label: string;
  value: string;
  /** Technical values go in the fixed-width typeface (section 13.1). */
  mono?: boolean;
  /** The full content, when `value` is an abbreviation. */
  title?: string;
}

export interface StageDescription {
  headline: string | null;
  facts: Fact[];
}

export const STAGE_LABELS: Record<string, string> = {
  ingest: "INGEST",
  fingerprint: "ACOUSTIC FINGERPRINT",
  harmonic: "HARMONY",
  shortlist: "SHORTLIST",
  commonality: "COMMONALITY",
  verdict: "VERDICT",
  transcript: "TRANSCRIPT",
  separation: "SOURCE SEPARATION",
  melodic: "MELODY",
};

/**
 * The status label. `gated` is not called "gate rejected" here but "confidence
 * check", because this is the moment in which the system judges itself - and
 * none of these states is a failure.
 */
export const STATUS_LABELS: Record<string, string> = {
  running: "IN PROGRESS",
  done: "DONE",
  partial: "PRELIMINARY",
  final: "FINAL",
  gated: "CONFIDENCE CHECK",
  failed: "FAILED",
};

/** What a step that has produced nothing yet is doing. */
const ACTIVITIES: Record<string, string> = {
  ingest: "Fetches the material, brings it to a single format and cuts it into windows.",
  fingerprint: "Computes the acoustic fingerprint of the query and looks for it in the index.",
  harmonic: "Compares the chord progression of the query against the candidates.",
  shortlist: "Narrows the candidate set down to those worth examining more deeply.",
  commonality: "Checks in the corpus how frequent the pattern it found really is.",
  verdict: "Assembles the detector evidence into a single evidence class.",
  transcript: "Recognizes the lyrics and measures its own confidence.",
  separation: "Separates the vocal from the backing track to give the transcript a clean signal.",
  melodic: "Looks for the longest common sequence of intervals.",
};

/** Gate reason codes in the language of the room. */
const REASONS: Record<string, string> = {
  asr_confidence: "transcript confidence below the threshold",
  instrumental: "the material is instrumental",
  no_lyrics: "the candidate has no lyrics",
  short_query: "the material is too short for this detector",
};

const NEXT_STEPS: Record<string, string> = {
  separation: "source separation",
  transcript: "transcript retry",
  melodic: "symbolic melody",
  fingerprint: "acoustic fingerprint",
  harmonic: "harmony",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage.toUpperCase();
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status.toUpperCase();
}

function numberAt(detail: Record<string, unknown>, key: string): number | null {
  const value = detail[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function textAt(detail: Record<string, unknown>, key: string): string | null {
  const value = detail[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Translates one event into the content of a row.
 *
 * Keys recognized by name are described in human terms; the rest of `detail`
 * lands at the bottom of the row in raw form. `envelope` is the only field left
 * out: it is the full set of detector results for screens E4-E5, not a heading
 * for E2.
 */
export function describeStage(event: PipelineEvent): StageDescription {
  const detail = event.detail ?? {};
  const used = new Set<string>(["envelope"]);
  const facts: Fact[] = [];
  let headline: string | null = null;

  const add = (keys: string[], fact: Fact | null) => {
    keys.forEach((key) => used.add(key));
    if (fact) facts.push(fact);
  };

  if (event.status === "gated") {
    // Section 12: a `gated` event carrying `next` is content, not an error.
    headline =
      "The confidence gate rejected the result of this step and pointed to what comes next.";
    const reason = textAt(detail, "reason");
    add(["reason"], reason ? { label: "REASON", value: REASONS[reason] ?? readableKey(reason) } : null);
    const next = textAt(detail, "next");
    add(
      ["next"],
      next ? { label: "NEXT STEP", value: NEXT_STEPS[next] ?? readableKey(next) } : null,
    );
    const confidence = numberAt(detail, "asr_confidence");
    const threshold = numberAt(detail, "threshold");
    if (confidence !== null) {
      add(["asr_confidence", "threshold"], {
        label: "ASR CONFIDENCE",
        value: threshold !== null
          ? `${formatNumber(confidence)} against a threshold of ${formatNumber(threshold)}`
          : formatNumber(confidence),
        mono: true,
      });
    }
  }

  switch (event.stage) {
    case "ingest": {
      const duration = numberAt(detail, "duration");
      add(["duration"], duration !== null
        ? { label: "MATERIAL LENGTH", value: formatSeconds(duration), mono: true }
        : null);
      const windows = numberAt(detail, "windows");
      add(["windows"], windows !== null
        ? { label: "ANALYSIS WINDOWS", value: formatNumber(windows), mono: true }
        : null);
      const hash = textAt(detail, "sha256");
      add(["sha256"], hash
        ? { label: "SHA256", value: shortenHash(hash), mono: true, title: hash }
        : null);
      break;
    }
    case "fingerprint": {
      const hashes = numberAt(detail, "hashes");
      add(["hashes"], hashes !== null
        ? { label: "MATCHED HASHES", value: formatNumber(hashes), mono: true }
        : null);
      break;
    }
    case "harmonic": {
      const qmax = numberAt(detail, "best_qmax");
      add(["best_qmax"], qmax !== null
        ? { label: "BEST QMAX", value: formatNumber(qmax), mono: true }
        : null);
      break;
    }
    case "shortlist": {
      const left = numberAt(detail, "to");
      const before = numberAt(detail, "from");
      const corpus = numberAt(detail, "corpus");
      if (left !== null && before !== null) {
        // Global Constraint from 13.2: these two numbers concern different sets
        // and must not be added up or confused with one another.
        headline =
          "The first number is the set we search in. The second is the set we judge the significance of a find against.";
        add(["to", "from"], {
          label: "CANDIDATES AFTER SHORTLIST",
          value: `${formatNumber(left)} of ${formatNumber(before)}`,
          mono: true,
        });
      }
      add(["corpus"], corpus !== null
        ? {
            label: "COMMONALITY CORPUS",
            value: `${formatNumber(corpus)} works`,
            mono: true,
          }
        : null);
      break;
    }
    case "commonality": {
      const idf = numberAt(detail, "mean_idf");
      add(["mean_idf"], idf !== null
        ? { label: "MEAN IDF", value: formatNumber(idf), mono: true }
        : null);
      const frequency = numberAt(detail, "corpus_frequency");
      const size = numberAt(detail, "corpus_size");
      if (frequency !== null) {
        add(["corpus_frequency", "corpus_size"], {
          label: "THIS PATTERN IN THE CORPUS",
          value: size !== null
            ? `${formatNumber(frequency)} of ${formatNumber(size)} works`
            : `${formatNumber(frequency)} works`,
          mono: true,
        });
      }
      break;
    }
    case "transcript": {
      if (event.status !== "gated") {
        const words = numberAt(detail, "words");
        add(["words"], words !== null
          ? { label: "RECOGNIZED WORDS", value: formatNumber(words), mono: true }
          : null);
        const language = textAt(detail, "lang") ?? textAt(detail, "language");
        add(["lang", "language"], language ? { label: "LANGUAGE", value: language, mono: true } : null);
        const confidence = numberAt(detail, "asr_confidence");
        add(["asr_confidence"], confidence !== null
          ? { label: "ASR CONFIDENCE", value: formatNumber(confidence), mono: true }
          : null);
        if (detail.used_separation === true) {
          used.add("used_separation");
          headline = "The transcript succeeded only after source separation.";
        } else if (detail.used_separation === false) {
          used.add("used_separation");
        }
      }
      break;
    }
    case "separation": {
      const model = textAt(detail, "model");
      add(["model"], model ? { label: "MODEL", value: model, mono: true } : null);
      if (Array.isArray(detail.stems)) {
        add(["stems"], {
          label: "STEMS",
          value: detail.stems.map(formatValue).join(", "),
          mono: true,
        });
      }
      const seconds = numberAt(detail, "seconds");
      add(["seconds"], seconds !== null
        ? { label: "SEPARATION TIME", value: formatSeconds(seconds), mono: true }
        : null);
      break;
    }
    case "melodic": {
      const run = numberAt(detail, "longest_common_run");
      add(["longest_common_run"], run !== null
        ? {
            label: "LONGEST COMMON RUN",
            value: `${formatNumber(run)} intervals`,
            mono: true,
          }
        : null);
      const distance = numberAt(detail, "ms_distance");
      add(["ms_distance"], distance !== null
        ? { label: "MELODIC DISTANCE", value: formatNumber(distance), mono: true }
        : null);
      break;
    }
    case "verdict": {
      const verdictClass = detail.class;
      add(["class"], typeof verdictClass === "string"
        ? {
            label: "EVIDENCE CLASS",
            value: isVerdictClass(verdictClass) ? VERDICT_LABELS[verdictClass] : verdictClass,
          }
        : null);
      const probability = numberAt(detail, "probability");
      add(["probability"], probability !== null
        ? { label: "PROBABILITY", value: formatPercent(probability), mono: true }
        : null);
      const numberStatus = textAt(detail, "probability_status");
      // Section 10.5: a raw and a calibrated number have to differ on screen.
      add(["probability_status"], numberStatus
        ? {
            label: "NUMBER STATUS",
            value: numberStatus === "calibrated" ? "calibrated" : "raw, not calibrated",
          }
        : null);
      const previous = detail.previous_class;
      if (typeof previous === "string") {
        used.add("previous_class");
        used.add("previous_probability");
        headline = `Verdict lifted from class ${
          isVerdictClass(previous) ? VERDICT_LABELS[previous] : previous
        }.`;
      }
      add(["candidate_id"], null);
      break;
    }
    default:
      break;
  }

  if (headline === null && facts.length === 0) {
    headline = ACTIVITIES[event.stage] ?? null;
  }

  // The fallback path for fields the dictionary does not know.
  Object.keys(detail)
    .filter((key) => !used.has(key))
    .forEach((key) => {
      facts.push({
        label: readableKey(key).toUpperCase(),
        value: formatValue(detail[key]),
        mono: true,
      });
    });

  return { headline, facts };
}
