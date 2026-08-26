/**
 * Tests of screens E8 (the legal panel), E9 (calibration) and E10 (the case file).
 *
 * The three screens sit in one file, because that is how the division of work was
 * set: task 21 touches `web/tests/legal.test.tsx` alone and three component
 * directories.
 */
import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { LegalPanel } from "../components/legal/LegalPanel";
import { CalibrationCharts } from "../components/calibration/CalibrationCharts";
import { CaseFile } from "../components/casefile/CaseFile";
import type { AnalyzeResult, Candidate, Legal, RankingEntry } from "../lib/contracts";

// Vitest runs with `globals: false`, so @testing-library/react has no way to
// register its own cleanup by itself. Without this line the second render in the
// file sees the DOM of the first and every getByText ends in "found multiple".
afterEach(cleanup);

/* -------------------------------------------------------------------------- */
/* E8                                                                         */
/* -------------------------------------------------------------------------- */

describe("E8 legal panel", () => {
  it("always shows the note that this is not legal advice", () => {
    render(<LegalPanel legal={{ rights_layer: [], risk_flags: [],
      license_status: "unknown", required_attribution: null,
      disclaimer: "Technical signal, not legal advice." }} />);
    expect(screen.getByText(/not legal advice/i)).toBeInTheDocument();
  });

  it("an unknown license is the absence of information, not the absence of restrictions", () => {
    // Constraint 9 from the specification
    render(<LegalPanel legal={{ rights_layer: [], risk_flags: [],
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    expect(screen.getByText(/no information/i)).toBeInTheDocument();
    expect(screen.queryByText(/permitted|allowed/i)).toBeNull();
  });

  it("an open license yields a ready-made attribution text to copy", () => {
    render(<LegalPanel legal={{ rights_layer: ["phonogram"], risk_flags: [],
      license_status: "cc-by-4.0", required_attribution: "Work X, author Y, CC BY 4.0",
      disclaimer: "x" }} />);
    expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
  });

  it("a high risk flag gets lime", () => {
    const { container } = render(<LegalPanel legal={{ rights_layer: ["phonogram"],
      risk_flags: ["recognizable_excerpt"], license_status: "unknown",
      required_attribution: null, disclaimer: "x" }} />);
    expect(container.querySelector("[data-accent='true']")).toBeTruthy();
  });

  it("a possible pastiche is a borderline case, not a green light", () => {
    // Section 11.2: the pastiche exception requires human judgement, so the flag
    // gets neither lime (it is not a signal about a recording) nor silence.
    const { container } = render(<LegalPanel legal={{ rights_layer: ["phonogram"],
      risk_flags: ["possible_pastiche"], license_status: "unknown",
      required_attribution: null, disclaimer: "x" }} />);
    expect(container.querySelector("[data-accent='true']")).toBeNull();
    expect(screen.getByText("BORDERLINE CASE")).toBeInTheDocument();
  });

  it("rights_layer is a list, so VERSION shows both layers", () => {
    // Section 11.1: the rightsholders and the terms of protection differ per layer.
    render(<LegalPanel legal={{ rights_layer: ["work", "performance"], risk_flags: [],
      recognizability: null, modification: null, license_status: "unknown",
      required_attribution: null, disclaimer: "x" }} />);
    expect(screen.getByText("WORK")).toBeInTheDocument();
    expect(screen.getByText("ARTISTIC PERFORMANCE")).toBeInTheDocument();
  });

  it("the recognizability and modification indicators are described, not raw", () => {
    render(<LegalPanel legal={{ rights_layer: ["phonogram"], risk_flags: [],
      recognizability: 0.78, modification: 0.41, license_status: "unknown",
      required_attribution: null, disclaimer: "x" }} />);
    expect(screen.getByText("0.78")).toBeInTheDocument();
    expect(screen.getByText("0.41")).toBeInTheDocument();
    expect(screen.getByText(/criterion applied by a court/i)).toBeInTheDocument();
  });

  it("a flag outside the dictionary is shown raw, with no invented interpretation", () => {
    render(<LegalPanel legal={{ rights_layer: [], risk_flags: ["new_flag_from_backend"],
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    expect(screen.getByText("new_flag_from_backend")).toBeInTheDocument();
  });

  it("a flag outside the dictionary does not get an invented legal basis", () => {
    // A legal basis stands next to every KNOWN flag. Attaching a provision to a
    // flag the panel does not understand would be worse than not having one.
    const { container } = render(<LegalPanel legal={{ rights_layer: [],
      risk_flags: ["new_flag_from_backend"], license_status: "unknown",
      required_attribution: null, disclaimer: "x" }} />);
    const flag = container.querySelector("[data-flag='new_flag_from_backend']");
    expect(flag?.querySelector("[data-basis='true']")).toBeNull();
  });

  it("a recognizable excerpt refers to Pelham I with its case number", () => {
    // Section 11.2: the recognizability of a sample to the ear is a legal
    // criterion, not a metaphor. The panel has to say what it flows from.
    const { container } = render(<LegalPanel legal={{ rights_layer: ["phonogram"],
      risk_flags: ["recognizable_excerpt"], recognizability: 0.78, modification: 0.41,
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    const flag = container.querySelector("[data-flag='recognizable_excerpt']");
    expect(flag?.textContent).toContain("Pelham I");
    expect(flag?.textContent).toContain("C-476/17");
    expect(flag?.textContent).toContain("29 July 2019");
    expect(flag?.querySelector("[data-basis='true']")).toBeTruthy();
  });

  it("a possible pastiche refers to Pelham II and lists the three cumulative conditions", () => {
    const { container } = render(<LegalPanel legal={{ rights_layer: ["phonogram"],
      risk_flags: ["possible_pastiche"], recognizability: 0.78, modification: 0.41,
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    const flag = container.querySelector("[data-flag='possible_pastiche']");
    expect(flag?.textContent).toContain("Pelham II");
    expect(flag?.textContent).toContain("C-590/23");
    expect(flag?.textContent).toContain("14 April 2026");
    expect(flag?.textContent).toContain("art. 5(3)(k)");
    expect(flag?.textContent).toContain("evocation");
    expect(flag?.textContent).toContain("perceptible difference");
    expect(flag?.textContent).toContain("artistic dialogue");
    expect(flag?.querySelectorAll("ol > li")).toHaveLength(3);
  });

  it("a flag carries a number only when the contract brought one", () => {
    // The indicators are computed for the EXCERPT class. With empty fields the
    // flag stays with its description alone instead of substituting an invented
    // value.
    const { container } = render(<LegalPanel legal={{ rights_layer: ["phonogram"],
      risk_flags: ["recognizable_excerpt"], recognizability: null, modification: null,
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    const flag = container.querySelector("[data-flag='recognizable_excerpt']");
    expect(flag?.textContent).not.toContain("recognizability indicator:");
  });

  it("a common element and a lyrics overlap refer to art. 2 of the act", () => {
    const { container } = render(<LegalPanel legal={{ rights_layer: [],
      risk_flags: ["common_element", "lyrics_overlap"], license_status: "unknown",
      required_attribution: null, disclaimer: "x" }} />);
    const common = container.querySelector("[data-flag='common_element']");
    expect(common?.textContent).toContain("Art. 2(4)");
    expect(common?.textContent).toContain("inspiration by another person's work");
    const lyrics = container.querySelector("[data-flag='lyrics_overlap']");
    expect(lyrics?.textContent).toContain("Art. 2(1)");
  });

  it("every known flag has a legal basis, without exception", () => {
    const known = ["recognizable_excerpt", "possible_pastiche", "common_element",
      "lyrics_overlap"];
    for (const flag of known) {
      const { container } = render(<LegalPanel legal={{ rights_layer: [],
        risk_flags: [flag], license_status: "unknown", required_attribution: null,
        disclaimer: "x" }} />);
      const li = container.querySelector(`[data-flag='${flag}']`);
      expect(li?.querySelector("[data-basis='true']")).toBeTruthy();
      cleanup();
    }
  });

  it("no rights layer refers to art. 2(4), because that is what the COMMON class looks like", () => {
    // COMMON and NONE arrive with an empty rights_layer. The panel has to say
    // that inspiration is not a derivative work rather than stay silent.
    render(<LegalPanel legal={{ rights_layer: [], risk_flags: [],
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    expect(screen.getByText(/is not regarded as a derivative work/i)).toBeInTheDocument();
  });

  it("every rights layer says who holds the rights and what it follows from", () => {
    // Section 11.1: three separate subjects of protection, three different holders.
    const { container } = render(<LegalPanel legal={{
      rights_layer: ["phonogram", "work", "performance"], risk_flags: [],
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    const phonogram = container.querySelector("[data-rights-layer='phonogram']");
    expect(phonogram?.textContent).toContain("The phonogram producer");
    expect(phonogram?.textContent).toContain("Detector A");
    expect(phonogram?.textContent).toContain("chapter 11");
    const work = container.querySelector("[data-rights-layer='work']");
    expect(work?.textContent).toContain("The composer");
    expect(work?.textContent).toContain("Art. 1");
    const performance = container.querySelector("[data-rights-layer='performance']");
    expect(performance?.textContent).toContain("The performer");
    for (const layer of ["phonogram", "work", "performance"]) {
      expect(
        container.querySelector(`[data-rights-layer='${layer}'] [data-basis='true']`),
      ).toBeTruthy();
    }
  });

  it("VERSION says outright that it touches two layers at once", () => {
    render(<LegalPanel legal={{ rights_layer: ["work", "performance"], risk_flags: [],
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    expect(screen.getByText(/what the VERSION class looks like/i)).toBeInTheDocument();
  });

  it("says outright that it does not measure artistic dialogue", () => {
    // The strongest point of the legal layer: of the three conditions of pastiche
    // the system measures two. The section is unconditional, so it stands even
    // with no flag at all.
    const { container } = render(<LegalPanel legal={{ rights_layer: [], risk_flags: [],
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    const notMeasured = container.querySelectorAll("[data-criterion='not-measured']");
    expect(notMeasured).toHaveLength(1);
    expect(notMeasured[0].textContent).toContain("artistic dialogue");
    expect(container.querySelectorAll("[data-criterion='measured']")).toHaveLength(2);
    expect(screen.getByText(/does not measure and never will/i)).toBeInTheDocument();
  });

  it("says that the CJEU ruled out examining the subjective intent of the creator", () => {
    render(<LegalPanel legal={{ rights_layer: [], risk_flags: [],
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    expect(screen.getByText(/subjective intent/i)).toBeInTheDocument();
    expect(screen.getByText(/objectively\s+recognizable/i)).toBeInTheDocument();
  });

  it("the indicators carry a legal basis, not just a number", () => {
    const { container } = render(<LegalPanel legal={{ rights_layer: ["phonogram"],
      risk_flags: [], recognizability: 0.78, modification: 0.41,
      license_status: "unknown", required_attribution: null, disclaimer: "x" }} />);
    const text = container.textContent ?? "";
    expect(text).toContain("C-476/17");
    expect(text).toContain("C-590/23");
  });

  it("the note stands next to the case numbers and reserves what they are not", () => {
    // The stronger the references, the greater the reason to say outright that
    // this is a technical signal and not an opinion.
    render(<LegalPanel legal={{ rights_layer: ["phonogram"],
      risk_flags: ["recognizable_excerpt"], recognizability: 0.78, modification: 0.41,
      license_status: "unknown", required_attribution: null,
      disclaimer: "Technical signal, not legal advice." }} />);
    expect(screen.getByRole("note")).toHaveTextContent(/not legal advice/i);
    expect(screen.getByText(/neither an assessment of this case nor legal advice/i))
      .toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */
/* E9                                                                         */
/* -------------------------------------------------------------------------- */

const CURVES = {
  auc: 0.93,
  roc: [
    { fpr: 0, tpr: 0 },
    { fpr: 0.05, tpr: 0.62 },
    { fpr: 0.2, tpr: 0.9 },
    { fpr: 1, tpr: 1 },
  ],
  reliability: [
    { predicted: 0.1, observed: 0.08, count: 120 },
    { predicted: 0.5, observed: 0.46, count: 140 },
    { predicted: 0.9, observed: 0.93, count: 90 },
  ],
};

describe("E9 calibration", () => {
  it("with no calibration data it says it is waiting instead of drawing an empty chart", () => {
    const { container } = render(<CalibrationCharts calibration={null} />);
    expect(screen.getByText(/waiting for calibration data/i)).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeNull();
  });

  it("instead of a similarity percentage it gives the confidence, the threshold and the rate of mistakes", () => {
    // Section 10.5
    render(
      <CalibrationCharts
        calibration={{ model_version: "lr_v3", trained_on: 500, precision_at_threshold: 0.94 }}
        curves={CURVES}
        probability={0.94}
        probabilityStatus="calibrated"
      />,
    );
    expect(screen.getByText("94%")).toBeInTheDocument();
    expect(screen.getByText(/500 pairs/i)).toBeInTheDocument();
    expect(screen.getByText(/6 cases out of 100/i)).toBeInTheDocument();
  });

  it("draws the ROC curve and the reliability diagram without a library", () => {
    const { container } = render(
      <CalibrationCharts
        calibration={{ model_version: "lr_v3", trained_on: 500, precision_at_threshold: 0.94 }}
        curves={CURVES}
      />,
    );
    expect(container.querySelector("svg[data-chart='roc']")).toBeTruthy();
    expect(container.querySelector("svg[data-chart='reliability']")).toBeTruthy();
  });

  it("classes without a model get an explicit 'preliminary threshold, no calibration data'", () => {
    // Section 10.4: LYRICS and EXCERPT_WORK have no model and never will.
    render(
      <CalibrationCharts
        calibration={{ model_version: "lr_v3", trained_on: 500, precision_at_threshold: 0.94 }}
        curves={CURVES}
      />,
    );
    expect(screen.getAllByText(/preliminary threshold, no calibration data/i).length)
      .toBeGreaterThan(0);
    expect(screen.getByText("LYRICS OVERLAP")).toBeInTheDocument();
    expect(screen.getByText("COMPOSITION EXCERPT")).toBeInTheDocument();
  });

  it("the model exists but the curves are missing - it does not invent points", () => {
    const { container } = render(
      <CalibrationCharts
        calibration={{ model_version: "lr_v3", trained_on: 500, precision_at_threshold: null }}
      />,
    );
    expect(container.querySelector("svg")).toBeNull();
    expect(screen.getByText(/sent no curve points/i)).toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */
/* E10                                                                        */
/* -------------------------------------------------------------------------- */

const CANDIDATE: Candidate = {
  id: "c1",
  name: "Night Shift",
  artist: "Nadia Kwon",
  shs_performance_id: null,
  source_url: "https://example.org/night-shift",
  audio_path: "data/audio/c1.wav",
  audio_url: null,
  published: "1998-04-11",
  published_source: "metadata_registry",
  license: "unknown",
  instrumental: false,
  language: "en",
  lyrics_path: null,
};

const LEGAL: Legal = {
  rights_layer: ["phonogram"],
  risk_flags: ["recognizable_excerpt"],
  recognizability: 0.78,
  modification: 0.41,
  license_status: "unknown",
  required_attribution: null,
  disclaimer: "Technical signal, not legal advice.",
};

const ENTRY: RankingEntry = {
  rank: 1,
  candidate: CANDIDATE,
  verdict_class: "EXCERPT_PHONOGRAM",
  verdict_layer: "phonogram",
  probability: 0.94,
  probability_status: "calibrated",
  evidence: { fingerprint: { status: "ok", reason: null } },
  alignment: { query_span: [12, 18], candidate_span: [40, 46], transposition: null, tempo_ratio: null },
  commonality: { mean_idf: 7.2, corpus_frequency: 3, corpus_size: 4128 },
  legal: LEGAL,
  explanation: "The same excerpt of the recording at a different tempo.",
};

const RESULT: AnalyzeResult = {
  status: "final",
  completed_levels: [1, 2],
  query: { duration: 183.4, waveform_url: null, transcript: [] },
  ranking: [ENTRY],
  calibration: { model_version: "lr_v3", trained_on: 500, precision_at_threshold: 0.94 },
};

describe("E10 case file", () => {
  it("ends with the breadcrumb from the brief", () => {
    render(<CaseFile result={RESULT} />);
    // The brand name and the case number come back in the report header too, so
    // what counts is presence, not uniqueness. The last crumb is only in the footer.
    expect(screen.getAllByText("GRAI ORIGIN").length).toBeGreaterThan(0);
    expect(screen.getAllByText("CASE 03").length).toBeGreaterThan(0);
    expect(screen.getByText("CASE FILE")).toBeInTheDocument();
  });

  it("carries the legal layer of the leading match together with the note", () => {
    render(<CaseFile result={RESULT} />);
    expect(screen.getByText(/not legal advice/i)).toBeInTheDocument();
    expect(screen.getAllByText("PHONOGRAM").length).toBeGreaterThan(0);
  });

  it("is a page for printing, not a file generator", () => {
    const { container } = render(<CaseFile result={RESULT} />);
    expect(screen.getByRole("button", { name: /print/i })).toBeInTheDocument();
    const style = container.querySelector("style");
    expect(style?.textContent).toContain("@media print");
  });

  it("an empty ranking does not pretend to be a report with a verdict", () => {
    render(<CaseFile result={{ ...RESULT, ranking: [] }} />);
    expect(screen.getByText(/no matches/i)).toBeInTheDocument();
  });
});
