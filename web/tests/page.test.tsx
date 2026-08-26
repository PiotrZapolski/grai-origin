/**
 * Integration test of the main page: the full run from choosing the material to
 * the final verdict, on a mocked stream.
 *
 * The tests of the individual screens are in the other files and are not
 * repeated here. What can be checked **only on the assembled page** is four
 * things:
 *
 * 1. the verdict lifts without a reload and **without losing its DOM node** -
 *    card E3 remembers the previous class only as long as it lives, so
 *    unmounting it between level 1 and level 2 would erase the whole trace of
 *    the lift;
 * 2. the bars of screen E5 receive numbers that **are not next to the ranking
 *    entry** - they travel exclusively in the detector envelopes on the stream;
 * 3. a criterion with no 0..1 quantity in the contract (melody) **gets no bar**,
 *    only a worded state;
 * 4. clicking an entry in the ranking switches the evidence and the criteria to
 *    another candidate.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type {
  AnalyzeResult,
  Candidate,
  DetectorEnvelope,
  RankingEntry,
  StreamEvent,
} from "../lib/contracts";
import Page from "../app/page";
import { isWebUrl, releaseDate } from "../components/verdict/SourceLink";

/* -------------------------------------------------------------------------- */
/* Environment mocks                                                          */
/* -------------------------------------------------------------------------- */

vi.mock("wavesurfer.js", () => ({
  default: {
    create: () => ({ setTime: vi.fn(), setOptions: vi.fn(), destroy: vi.fn(), on: vi.fn() }),
  },
}));

const { analyzeMock, getResultMock, streamJobMock } = vi.hoisted(() => ({
  analyzeMock: vi.fn(),
  getResultMock: vi.fn(),
  streamJobMock: vi.fn(),
}));

// The rest of the module stays real: `ResultNotReadyError` and `API_BASE` are
// used by the page, and replacing them with mocks would test the mock instead of
// the page.
vi.mock("../lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/api")>();
  return {
    ...original,
    analyze: analyzeMock,
    getResult: getResultMock,
    streamJob: streamJobMock,
  };
});

interface Listener {
  jobId: string;
  onEvent: (event: StreamEvent) => void;
  onError?: (error: Error) => void;
  close: ReturnType<typeof vi.fn>;
}

const streams: Listener[] = [];

/** The result the next call to `/result` will return. The test swaps it on the fly. */
let currentResult: AnalyzeResult;

beforeAll(() => {
  // jsdom does not play audio. The A/B panel reaches for these three fields and
  // without them it would fall over instead of playing.
  for (const [name, value] of [
    ["currentTime", 0],
    ["play", vi.fn(() => Promise.resolve())],
    ["pause", vi.fn()],
    ["load", vi.fn()],
  ] as const) {
    Object.defineProperty(HTMLMediaElement.prototype, name, {
      writable: true,
      configurable: true,
      value,
    });
  }
});

beforeEach(() => {
  streams.length = 0;
  analyzeMock.mockReset();
  getResultMock.mockReset();
  streamJobMock.mockReset();

  analyzeMock.mockResolvedValue("job_demo");
  currentResult = preliminaryResult();
  getResultMock.mockImplementation(async () => currentResult);
  streamJobMock.mockImplementation(
    (jobId: string, onEvent: Listener["onEvent"], onError?: Listener["onError"]) => {
      const listener: Listener = { jobId, onEvent, onError, close: vi.fn() };
      streams.push(listener);
      return { close: listener.close };
    },
  );
});

/* -------------------------------------------------------------------------- */
/* Data matching section 12                                                   */
/* -------------------------------------------------------------------------- */

function candidate(data: Partial<Candidate> & Pick<Candidate, "id" | "name" | "artist">): Candidate {
  return {
    shs_performance_id: null,
    source_url: `https://example.com/${data.id}`,
    audio_path: `data/audio/${data.id}.wav`,
    published: null,
    published_source: null,
    license: "unknown",
    instrumental: false,
    language: "en",
    lyrics_path: null,
    audio_url: null,
    ...data,
  };
}

const CAND_07 = candidate({
  id: "cand_07",
  name: "Loose Change",
  artist: "Halcyon Trio",
  source_url: "https://youtube.com/watch?v=g0bZtf5MCzY",
  published: "1977-05-20",
  published_source: "manual",
  license: "all_rights_reserved",
});

const CAND_11 = candidate({
  id: "cand_11",
  name: "Paper Streets",
  artist: "The Meridian",
  published: "2009-03-14",
  published_source: "manual",
});

const CAND_02 = candidate({
  id: "cand_02",
  name: "Riverbend Theme",
  artist: "Nadia Kwon",
  // A manifest with no page address. A dead link would be worse than none.
  source_url: "",
  published: "1994-11-02",
  published_source: "manual",
  license: "cc-by-3.0",
  instrumental: true,
  language: null,
});

function entry(data: Partial<RankingEntry> & Pick<RankingEntry, "rank" | "candidate">): RankingEntry {
  return {
    verdict_class: "NONE",
    verdict_layer: null,
    probability: null,
    probability_status: "uncalibrated",
    evidence: {},
    alignment: null,
    commonality: null,
    legal: {
      rights_layer: [],
      risk_flags: [],
      recognizability: null,
      modification: null,
      license_status: "unknown",
      required_attribution: null,
      disclaimer: "Technical signal, not legal advice.",
    },
    explanation: "",
    ...data,
  };
}

const ALIGNMENT = {
  query_span: [12.4, 31.8] as [number, number],
  candidate_span: [64.1, 83.5] as [number, number],
  transposition: 2,
  tempo_ratio: 1.06,
};

/** Level 1: two detectors out of four. A missing key means "not measured yet". */
function preliminaryResult(): AnalyzeResult {
  return {
    status: "partial",
    completed_levels: [1],
    query: { duration: 184.2, waveform_url: null, transcript: [] },
    calibration: null,
    ranking: [
      entry({
        rank: 1,
        candidate: CAND_07,
        verdict_class: "VERSION",
        verdict_layer: "work",
        probability: 0.71,
        probability_status: "uncalibrated",
        evidence: {
          fingerprint: { status: "ok", reason: null },
          harmonic: { status: "ok", reason: null },
        },
        alignment: ALIGNMENT,
        commonality: { mean_idf: 8.4, corpus_frequency: 3, corpus_size: 4128 },
      }),
      entry({
        rank: 2,
        candidate: CAND_02,
        verdict_class: "COMMON",
        probability: 0.35,
        evidence: {
          fingerprint: { status: "ok", reason: null },
          harmonic: { status: "ok", reason: null },
        },
        commonality: { mean_idf: 2.1, corpus_frequency: 1877, corpus_size: 4128 },
      }),
      entry({
        rank: 3,
        candidate: CAND_11,
        verdict_class: "NONE",
        probability: 0.12,
        evidence: {
          fingerprint: { status: "ok", reason: null },
          harmonic: { status: "ok", reason: null },
        },
      }),
    ],
  };
}

/** Level 2: the class of the first entry changes and the whole ranking reorders. */
function finalResult(audio = false): AnalyzeResult {
  const withAudio = (item: Candidate): Candidate =>
    audio ? { ...item, audio_url: `/api/audio/candidate/${item.id}?set=demo_01` } : item;

  return {
    status: "final",
    completed_levels: [1, 2],
    query: {
      duration: 184.2,
      waveform_url: audio ? "/api/jobs/job_demo/audio" : null,
      transcript: [
        { word: "hold", start: 18.2, end: 18.5 },
        { word: "the", start: 18.5, end: 18.7 },
        { word: "line", start: 18.7, end: 19.2 },
      ],
    },
    calibration: { model_version: "lr_v3", trained_on: 500, precision_at_threshold: 0.95 },
    ranking: [
      entry({
        rank: 1,
        candidate: withAudio(CAND_07),
        verdict_class: "EXCERPT_WORK",
        verdict_layer: "work",
        probability: 0.94,
        probability_status: "calibrated",
        evidence: {
          fingerprint: { status: "ok", reason: null },
          harmonic: { status: "ok", reason: null },
          melodic: { status: "ok", reason: null },
          lyrics: { status: "ok", reason: null },
        },
        alignment: ALIGNMENT,
        commonality: { mean_idf: 8.4, corpus_frequency: 3, corpus_size: 4128 },
        legal: {
          rights_layer: ["work"],
          risk_flags: ["recognizable_excerpt"],
          recognizability: 0.72,
          modification: 0.35,
          license_status: "all_rights_reserved",
          required_attribution: null,
          disclaimer: "Technical signal, not legal advice.",
        },
        explanation: "The query overlaps with the entry Loose Change over 12.4 s - 31.8 s.",
      }),
      entry({
        rank: 2,
        candidate: withAudio(CAND_11),
        verdict_class: "LYRICS",
        verdict_layer: "work",
        probability: 0.58,
        probability_status: "calibrated",
        evidence: {
          fingerprint: { status: "ok", reason: null },
          harmonic: { status: "ok", reason: null },
          melodic: { status: "ok", reason: null },
          lyrics: { status: "ok", reason: null },
        },
        commonality: { mean_idf: 6.9, corpus_frequency: 12, corpus_size: 4128 },
      }),
      entry({
        rank: 3,
        candidate: withAudio(CAND_02),
        verdict_class: "COMMON",
        probability: 0.35,
        probability_status: "calibrated",
        evidence: {
          fingerprint: { status: "ok", reason: null },
          harmonic: { status: "ok", reason: null },
          melodic: { status: "failed", reason: "note extraction returned no track at all" },
          lyrics: { status: "not_applicable", reason: "instrumental" },
        },
        commonality: { mean_idf: 2.1, corpus_frequency: 1877, corpus_size: 4128 },
      }),
    ],
  };
}

/* -------------------------------------------------------------------------- */
/* Stream                                                                     */
/* -------------------------------------------------------------------------- */

function event(
  stage: string,
  level: number,
  status: string,
  detail: Record<string, unknown> = {},
): StreamEvent {
  return { stage, level, status, detail } as StreamEvent;
}

const FINGERPRINT_ENVELOPE: DetectorEnvelope = {
  detector: "fingerprint",
  status: "ok",
  reason: null,
  results: [
    {
      detector: "fingerprint",
      candidate_id: "cand_07",
      status: "ok",
      reason: null,
      matched_hashes: 341,
      peak_ratio: 0.31,
      query_span: [12.4, 31.8],
      candidate_span: [64.1, 83.5],
      offset: 51.7,
      repetitions: 1,
      transform: { tempo: 1.06, pitch: 2 },
    },
    {
      detector: "fingerprint",
      candidate_id: "cand_11",
      status: "ok",
      reason: null,
      matched_hashes: 22,
      peak_ratio: 0.03,
      query_span: null,
      candidate_span: null,
      offset: null,
      repetitions: 0,
      transform: null,
    },
  ],
};

const HARMONIC_ENVELOPE: DetectorEnvelope = {
  detector: "harmonic",
  status: "ok",
  reason: null,
  results: [
    {
      detector: "harmonic",
      candidate_id: "cand_07",
      status: "ok",
      reason: null,
      qmax_score: 0.63,
      transposition: 2,
      tempo_ratio: 1.06,
      alignment_path: [
        [0, 0],
        [1, 1],
        [2, 3],
      ],
      coverage: 0.58,
      chord_sequence: ["C", "G", "Am", "F"],
    },
    {
      detector: "harmonic",
      candidate_id: "cand_11",
      status: "ok",
      reason: null,
      qmax_score: 0.22,
      transposition: 0,
      tempo_ratio: 1,
      alignment_path: [],
      coverage: 0.19,
      chord_sequence: ["Dm", "Bb", "F", "C"],
    },
  ],
};

const LYRICS_ENVELOPE: DetectorEnvelope = {
  detector: "lyrics",
  status: "ok",
  reason: "the transcript was accepted only after source separation",
  results: [
    {
      detector: "lyrics",
      candidate_id: "cand_07",
      status: "ok",
      reason: null,
      jaccard: 0.24,
      semantic_sim: 0.31,
      matched_spans: [{ query: [18.2, 21.0], candidate: [70.0, 72.8], text: "hold the line" }],
      asr_confidence: 0.78,
      language: "en",
      used_separation: true,
    },
    {
      detector: "lyrics",
      candidate_id: "cand_11",
      status: "ok",
      reason: null,
      jaccard: 0.51,
      semantic_sim: 0.68,
      matched_spans: [
        { query: [41.0, 46.2], candidate: [12.8, 18.1], text: "we were counting paper streets" },
      ],
      asr_confidence: 0.78,
      language: "en",
      used_separation: true,
    },
  ],
};

const MELODIC_ENVELOPE: DetectorEnvelope = {
  detector: "melodic",
  status: "ok",
  reason: null,
  results: [
    {
      detector: "melodic",
      candidate_id: "cand_07",
      status: "ok",
      reason: null,
      matched_ngrams: [
        { query_start: 14.1, candidate_start: 65.8, n: 5, intervals: [2, 2, -3, 5, -2] },
      ],
      longest_common_run: 11,
      ms_distance: 0.18,
      used_separation: false,
    },
    {
      detector: "melodic",
      candidate_id: "cand_11",
      status: "ok",
      reason: null,
      matched_ngrams: [{ query_start: 8.0, candidate_start: 3.4, n: 3, intervals: [2, -2, 1] }],
      longest_common_run: 3,
      ms_distance: 0.62,
      used_separation: false,
    },
  ],
};

const LEVEL_1: StreamEvent[] = [
  event("ingest", 1, "done", { duration: 184.2, windows: 37 }),
  event("fingerprint", 1, "running"),
  event("fingerprint", 1, "done", { hashes: 4812, envelope: FINGERPRINT_ENVELOPE }),
  event("harmonic", 1, "running"),
  event("harmonic", 1, "done", { best_qmax: 0.63, envelope: HARMONIC_ENVELOPE }),
  event("shortlist", 1, "done", { from: 12, to: 8, corpus: 4128 }),
  event("commonality", 1, "done", { mean_idf: 8.4 }),
];

const PRELIMINARY_VERDICT = event("verdict", 1, "partial", {
  class: "VERSION",
  probability: 0.71,
  probability_status: "uncalibrated",
  candidate_id: "cand_07",
});

const LEVEL_2: StreamEvent[] = [
  event("transcript", 2, "gated", { reason: "asr_confidence", next: "separation" }),
  event("separation", 2, "done", { seconds: 12.8 }),
  event("transcript", 2, "done", { words: 47, lang: "en", envelope: LYRICS_ENVELOPE }),
  event("melodic", 2, "done", { longest_common_run: 11, envelope: MELODIC_ENVELOPE }),
];

const FINAL_VERDICT = event("verdict", 2, "final", {
  class: "EXCERPT_WORK",
  probability: 0.94,
  probability_status: "calibrated",
  candidate_id: "cand_07",
});

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function emit(list: StreamEvent[]) {
  act(() => {
    for (const item of list) streams[0].onEvent(item);
  });
}

function bar(criterion: string): HTMLElement {
  const element = document.querySelector(
    `[data-testid="criterion-bar"][data-criterion="${criterion}"]`,
  );
  if (element === null) throw new Error(`there is no criterion bar ${criterion}`);
  return element as HTMLElement;
}

function rankingEntry(candidateId: string): HTMLElement {
  const element = document.querySelector(
    `[data-testid="ranking-entry"][data-candidate-id="${candidateId}"]`,
  );
  if (element === null) throw new Error(`there is no ranking entry ${candidateId}`);
  return element as HTMLElement;
}

const COVER_URL = "https://youtube.com/watch?v=8AHCfZTRGiI";

/** Chooses the material and waits until the page opens the stream. */
async function chooseMaterial() {
  render(<Page />);
  fireEvent.change(screen.getByLabelText("Recording address"), {
    target: { value: COVER_URL },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
  await waitFor(() => expect(streams.length).toBe(1));
}

/** The full run up to and including the preliminary verdict. */
async function toPreliminaryVerdict() {
  await chooseMaterial();
  emit(LEVEL_1);
  emit([PRELIMINARY_VERDICT]);
  return screen.findByTestId("verdict-card");
}

/** Onwards, up to the final verdict. */
async function toFinalVerdict(audio = false) {
  currentResult = finalResult(audio);
  emit(LEVEL_2);
  emit([FINAL_VERDICT]);
  await waitFor(() =>
    expect(screen.getByTestId("verdict-card").dataset.verdict).toBe("EXCERPT_WORK"),
  );
}

/* -------------------------------------------------------------------------- */
/* Tests                                                                      */
/* -------------------------------------------------------------------------- */

describe("page - the run from material to verdict", () => {
  it("submits the job from the pasted address and opens the stream of that job", async () => {
    await chooseMaterial();
    expect(analyzeMock).toHaveBeenCalledWith(COVER_URL, "demo_01");
    expect(streams[0].jobId).toBe("job_demo");
  });

  it("the stage shows the current step with its numbers before any verdict", async () => {
    await chooseMaterial();
    emit(LEVEL_1);

    // **One** step stands on the stage at a time, the last one that arrived. The
    // numbers come from that step, not from the whole history - the rest is in
    // the map.
    expect(screen.getByText(/8 of 12/)).toBeInTheDocument();
    expect(screen.queryByTestId("verdict-card")).toBeNull();

    // The map is interactive: a click brings the stage back to a step that has
    // already gone by, together with the numbers it produced then.
    const fingerprint = document.querySelector('[data-step="fingerprint"]') as HTMLElement | null;
    expect(fingerprint?.dataset.state).toBe("done");
    fireEvent.click(fingerprint as HTMLElement);
    expect(screen.getByText(/4,812/)).toBeInTheDocument();
  });

  it("the step map tells done, current and future apart", async () => {
    await chooseMaterial();
    emit(LEVEL_1);

    const state = (id: string) =>
      (document.querySelector(`[data-step="${id}"]`) as HTMLElement | null)?.dataset.state;

    expect(state("ingest")).toBe("done");
    expect(state("commonality")).toBe("current");
    expect(state("melodic")).toBe("future");
  });

  it("the lime goes out with the stream, on the map and on the stage alike", async () => {
    // Global Constraint 11 says the accent means "something is being computed
    // right now". `pipeline.test.tsx` checks that on `StepMap` rendered alone,
    // which is exactly how the assembled page came to break it: the map dropped
    // its accent when the stream died and the stage next to it kept a lime
    // "Analysis in progress", telling the room the run was still going.
    await chooseMaterial();
    emit(LEVEL_1);

    // While the run is alive something has to carry the accent, otherwise this
    // test would also pass on a page with no lime anywhere.
    expect(document.querySelectorAll('[data-accent="true"]').length).toBeGreaterThan(0);
    expect(
      screen.getByTestId("analysis-stage").querySelectorAll(".text-accent").length,
    ).toBeGreaterThan(0);

    act(() => {
      streams[0].onError?.(new Error("the stream dropped"));
    });

    await waitFor(() =>
      expect(document.querySelectorAll('[data-accent="true"]')).toHaveLength(0),
    );
    expect(screen.getByTestId("analysis-stage").querySelectorAll(".text-accent")).toHaveLength(
      0,
    );
  });

  it("after the preliminary verdict it shows card E3 with the level 1 class", async () => {
    const card = await toPreliminaryVerdict();
    expect(card.dataset.verdict).toBe("VERSION");
    expect(card.dataset.status).toBe("partial");
    expect(card.dataset.lifted).toBe("false");
    expect(screen.getByTestId("confidence").dataset.probabilityStatus).toBe("uncalibrated");
  });

  it("lifts the verdict without losing the DOM node, despite the change of class", async () => {
    // The heart of section 12: the card has to remember where it lifted from and
    // to, and it remembers that only as long as it lives. Mounting it again would
    // erase the whole trace.
    const card = await toPreliminaryVerdict();
    await toFinalVerdict();

    expect(screen.getByTestId("verdict-card")).toBe(card);
    expect(card.dataset.status).toBe("final");
    expect(card.dataset.lifted).toBe("true");
    expect(screen.getByTestId("lift").textContent).toMatch(/SAME WORK/);
    expect(screen.getByTestId("lift").textContent).toMatch(/COMPOSITION EXCERPT/);
    expect(screen.getByTestId("confidence").dataset.probabilityStatus).toBe("calibrated");
  });
});

describe("page - criteria fed by the detector envelopes", () => {
  it("takes the numbers from the stream, because they are not next to the ranking entry", async () => {
    await toPreliminaryVerdict();
    // peak_ratio 0.31 and qmax_score 0.63 travel exclusively in `detail.envelope`.
    expect(bar("fingerprint").textContent).toMatch(/31%/);
    expect(bar("harmonic").textContent).toMatch(/63%/);
  });

  it("a criterion with no key in the evidence waits instead of showing a zero", async () => {
    await toPreliminaryVerdict();
    expect(bar("melodic").dataset.state).toBe("missing");
    expect(bar("melodic").textContent).toMatch(/not measured yet/);
    expect(bar("melodic").textContent).not.toMatch(/%/);
  });

  it("after level 2 the melody is measured, but still gets no bar", async () => {
    // The contract carries no 0..1 quantity for detector C: there is a count of
    // intervals and an edit distance. A bar would require inventing a scale.
    await toPreliminaryVerdict();
    await toFinalVerdict();
    expect(bar("melodic").dataset.state).toBe("ok");
    expect(bar("melodic").textContent).not.toMatch(/%/);
    expect(bar("lyrics").textContent).toMatch(/24%/);
  });
});

describe("page - the ranking switches the evidence", () => {
  it("clicking an entry moves panels E4 and bars E5 to another candidate", async () => {
    await toPreliminaryVerdict();
    await toFinalVerdict();

    expect(bar("lyrics").textContent).toMatch(/24%/);

    fireEvent.click(rankingEntry("cand_11"));

    // The jaccard of candidate cand_11 is 0.51, not the 0.24 of the first entry.
    await waitFor(() => expect(bar("lyrics").textContent).toMatch(/51%/));
    expect(rankingEntry("cand_11").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("candidate-column").textContent).toMatch(/Paper Streets/);
    // The verdict still describes the first entry - the evidence and the verdict
    // are two different things.
    expect(screen.getByTestId("verdict-card").textContent).toMatch(/Loose Change/);
  });

  it("an entry with status failed shows the reason, not a zero", async () => {
    await toPreliminaryVerdict();
    await toFinalVerdict();

    fireEvent.click(rankingEntry("cand_02"));

    await waitFor(() => expect(bar("melodic").dataset.state).toBe("failed"));
    expect(bar("melodic").textContent).not.toMatch(/%/);
    expect(bar("lyrics").dataset.state).toBe("not_applicable");
  });
});

describe("page - evidence and audio", () => {
  it("without an audio address it says outright that there is no listening", async () => {
    await toPreliminaryVerdict();
    expect(screen.getByTestId("overlay-without-audio").textContent).toMatch(/A\/B listening/);
    expect(screen.queryByTestId("ab-listen")).toBeNull();
  });

  it("with audio addresses it opens A/B listening on the common span", async () => {
    await toPreliminaryVerdict();
    await toFinalVerdict(true);

    expect(await screen.findByTestId("ab-listen")).toBeInTheDocument();
    expect((screen.getByTestId("candidate-audio") as HTMLAudioElement).getAttribute("src")).toBe(
      "/api/audio/candidate/cand_07?set=demo_01",
    );
    expect((screen.getByTestId("query-audio") as HTMLAudioElement).getAttribute("src")).toBe(
      "/api/jobs/job_demo/audio",
    );
    // Listening starts where the evidence starts, not at the beginning of the file.
    expect(screen.getByTestId("position-a").textContent).toBe("12.40");
  });
});

describe("page - the address of the original", () => {
  it("the entry screen no longer offers ready-made examples", () => {
    // The scenario of the show: the cover plays from YouTube out loud, then the
    // address goes here.
    render(<Page />);
    expect(screen.getByLabelText("Recording address")).toBeInTheDocument();
    expect(screen.getByLabelText("Material file")).toBeInTheDocument();
    expect(document.querySelector("[data-example]")).toBeNull();
  });

  it("the verdict carries a clickable address of the original, opened in a new tab", async () => {
    await toPreliminaryVerdict();

    const link = screen.getByTestId("original-link");
    expect(link).toHaveAttribute("href", "https://youtube.com/watch?v=g0bZtf5MCzY");
    expect(link).toHaveAttribute("target", "_blank");
    // Without this the opened tab has access to the window with the analysis result.
    expect(link.getAttribute("rel")).toMatch(/noopener/);
  });

  it("the address shows the release date with its declared source", async () => {
    await toPreliminaryVerdict();
    expect(screen.getByTestId("release-date").textContent).toBe("1977-05-20");
    expect(screen.getByTestId("original-url").textContent).toMatch(
      /not from the video service/,
    );
  });

  it("the address of the original follows the verdict, not the choice in the ranking", async () => {
    await toPreliminaryVerdict();
    await toFinalVerdict();

    fireEvent.click(rankingEntry("cand_11"));

    await waitFor(() => expect(bar("lyrics").textContent).toMatch(/51%/));
    // The verdict describes the first entry, so the address under it is its address.
    expect(screen.getByTestId("original-url").dataset.candidateId).toBe("cand_07");
  });

  it("every ranking entry has its address, and a missing address is named", async () => {
    await toPreliminaryVerdict();

    const addresses = screen.getByTestId("source-urls");
    // The first entry has its own address under the verdict card and is not repeated here.
    expect(addresses.querySelector('[data-candidate-id="cand_07"]')).toBeNull();

    const withoutAddress = addresses.querySelector('[data-candidate-id="cand_02"]');
    expect(withoutAddress?.textContent).toMatch(/no address in the manifest/);
    expect(withoutAddress?.querySelector("a")).toBeNull();

    const withAddress = addresses.querySelector('[data-candidate-id="cand_11"] a');
    expect(withAddress).toHaveAttribute("href", "https://example.com/cand_11");
    expect(withAddress).toHaveAttribute("target", "_blank");
  });

  it("the page address and the file address are two different things", async () => {
    // source_url goes to a human, audio_url to the player. Confusing them would
    // give a link to an API endpoint instead of to the recording on YouTube.
    await toPreliminaryVerdict();
    await toFinalVerdict(true);

    expect(screen.getByTestId("original-link")).toHaveAttribute(
      "href",
      "https://youtube.com/watch?v=g0bZtf5MCzY",
    );
    expect((screen.getByTestId("candidate-audio") as HTMLAudioElement).getAttribute("src")).toBe(
      "/api/audio/candidate/cand_07?set=demo_01",
    );
  });

  it("a date with no declared source does not reach the screen", () => {
    // The same rule as on axis E7: an upload date on a video service is not a
    // release date, so a date with no named provenance is not an argument.
    const withoutSource = { ...CAND_07, published_source: null };
    expect(releaseDate(CAND_07)).toBe("1977-05-20");
    expect(releaseDate(withoutSource)).toBeNull();
    expect(isWebUrl("https://youtube.com/watch?v=x")).toBe(true);
    expect(isWebUrl("data/audio/cand_03.wav")).toBe(false);
    expect(isWebUrl("")).toBe(false);
  });
});

describe("page - supplementary screens and breadcrumbs", () => {
  it("every screen has its own footer with a breadcrumb", async () => {
    await toPreliminaryVerdict();
    for (const screenName of [
      "E1 INPUT",
      "E2 PIPELINE",
      "E3 VERDICT",
      "E4 EVIDENCE",
      "E5 CRITERIA",
      "E6 RANKING",
    ]) {
      const region = screen.getByRole("region", { name: screenName });
      expect(region.textContent).toMatch(/CASE 03/);
      expect(region.textContent).toContain(screenName);
    }
  });

  it("the tabs open the timeline, the legal panel, the calibration and the case file", async () => {
    await toPreliminaryVerdict();
    await toFinalVerdict();

    expect(screen.getByTestId("axis")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "LEGAL PANEL" }));
    // The note that this is not legal advice stands at the top of the panel, always.
    expect(screen.getByRole("note").textContent).toMatch(/not legal advice/);

    fireEvent.click(screen.getByRole("tab", { name: "CALIBRATION" }));
    // "500 pairs" also appears on the verdict card, so we ask about an item that
    // exists only on the calibration screen.
    const pairs = screen.getByText("Training pairs").parentElement;
    expect(pairs?.textContent).toMatch(/500/);

    fireEvent.click(screen.getByRole("tab", { name: "CASE FILE" }));
    expect(screen.getByRole("article", { name: "Case file" })).toBeInTheDocument();
    expect(screen.getByText("Evidence report")).toBeInTheDocument();
  });
});
