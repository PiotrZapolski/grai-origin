/**
 * Screen E3 - the verdict. Sections 4, 10.5, 12 and 13.2 of the specification.
 *
 * The heart of this screen: the verdict arrives **twice** and the class can
 * change in between. The card has to lift without reloading the screen, not
 * blink.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import type { CalibrationInfo } from "../lib/contracts";
import {
  VerdictCard,
  calibrationSentence,
  type VerdictEntry,
} from "../components/verdict/VerdictCard";

const preliminary: VerdictEntry = {
  verdict_class: "VERSION",
  probability: 0.71,
  probability_status: "uncalibrated",
  candidate: {
    id: "cand_07",
    name: "Loose Change",
    artist: "Halcyon Trio",
    source_url: "https://youtube.com/watch?v=g0bZtf5MCzY",
    published: "1977-05-20",
    published_source: "metadata_registry",
  },
  explanation: "Harmony and lyrics agree, the fingerprint does not hit.",
};

const calibration: CalibrationInfo = {
  model_version: "lr_v3",
  trained_on: 500,
  precision_at_threshold: 0.95,
};

describe("E3 verdict", () => {
  it("shows the badge of the evidence class", () => {
    render(<VerdictCard entry={preliminary} status="partial" />);
    expect(screen.getByText("SAME WORK")).toBeInTheDocument();
  });

  it("shows the source: the name and the artist", () => {
    render(<VerdictCard entry={preliminary} status="partial" />);
    expect(screen.getByText("Loose Change")).toBeInTheDocument();
    expect(screen.getByText("Halcyon Trio")).toBeInTheDocument();
  });

  it("distinguishes a calibrated threshold from a hand-written one", () => {
    // Global Constraint 7 / section 10.5: an uncalibrated number has no right to
    // look the same as a calibrated one.
    render(<VerdictCard entry={preliminary} status="partial" />);
    expect(screen.getByText(/preliminary threshold|no calibration data/i)).toBeInTheDocument();
    expect(screen.getByTestId("confidence").dataset.probabilityStatus).toBe("uncalibrated");
  });

  it("for a calibrated threshold shows the number of pairs and of mistakes per hundred", () => {
    render(
      <VerdictCard
        entry={{ ...preliminary, probability: 0.94, probability_status: "calibrated" }}
        status="final"
        calibration={calibration}
      />,
    );
    expect(screen.getByText(/500 pairs/)).toBeInTheDocument();
    expect(screen.getByText(/5 cases out of 100/)).toBeInTheDocument();
    expect(screen.queryByText(/preliminary threshold/i)).toBeNull();
    expect(screen.getByTestId("confidence").dataset.probabilityStatus).toBe("calibrated");
  });

  it("the card lifts once the final verdict arrives", () => {
    // Section 12: the verdict appears twice and the class can change.
    const { rerender } = render(<VerdictCard entry={preliminary} status="partial" />);
    rerender(
      <VerdictCard
        entry={{
          ...preliminary,
          verdict_class: "EXACT",
          probability: 0.94,
          probability_status: "calibrated",
        }}
        status="final"
        calibration={calibration}
      />,
    );
    expect(screen.getByText("IDENTICAL RECORDING")).toBeInTheDocument();
    expect(screen.queryByText("SAME WORK")).toBeNull();
  });

  it("the lift is visible and says where from and to", () => {
    const { rerender } = render(<VerdictCard entry={preliminary} status="partial" />);
    expect(screen.queryByTestId("lift")).toBeNull();

    rerender(
      <VerdictCard
        entry={{
          ...preliminary,
          verdict_class: "EXACT",
          probability: 0.94,
          probability_status: "calibrated",
        }}
        status="final"
        calibration={calibration}
      />,
    );

    const trace = screen.getByTestId("lift");
    // The previous class stays in the sentence about the lift, but not as a
    // separate badge - one verdict is meant to stand on screen, not two.
    expect(trace.textContent).toContain("SAME WORK");
    expect(trace.textContent).toContain("IDENTICAL RECORDING");
    expect(trace.textContent).toContain("71%");
    expect(trace.textContent).toContain("94%");
  });

  it("lifts without a reload: the same DOM node stays in place", () => {
    // "Without reloading the screen" means: React updates the card rather than
    // mounting it anew. If it mounted it, the lift animation would blink.
    const { container, rerender } = render(<VerdictCard entry={preliminary} status="partial" />);
    const before = container.querySelector("[data-testid='verdict-card']");
    expect(before?.getAttribute("data-lifted")).toBe("false");

    rerender(
      <VerdictCard
        entry={{ ...preliminary, verdict_class: "EXACT", probability: 0.94 }}
        status="final"
      />,
    );
    const after = container.querySelector("[data-testid='verdict-card']");
    expect(after).toBe(before);
    expect(after?.getAttribute("data-lifted")).toBe("true");
  });

  it("the COMMON class does not get lime", () => {
    const { container } = render(
      <VerdictCard entry={{ ...preliminary, verdict_class: "COMMON" }} status="final" />,
    );
    expect(container.querySelector("[data-accent='true']")).toBeNull();
  });

  it("the NONE class does not get lime", () => {
    const { container } = render(
      <VerdictCard entry={{ ...preliminary, verdict_class: "NONE" }} status="final" />,
    );
    expect(container.querySelector("[data-accent='true']")).toBeNull();
  });

  it("the EXACT class gets lime", () => {
    const { container } = render(
      <VerdictCard entry={{ ...preliminary, verdict_class: "EXACT" }} status="final" />,
    );
    expect(container.querySelector("[data-accent='true']")).not.toBeNull();
  });

  it("shows one sentence of reasoning", () => {
    render(<VerdictCard entry={preliminary} status="partial" />);
    expect(screen.getByText(/the fingerprint does not hit/)).toBeInTheDocument();
  });

  it("a missing probability shows a worded state, not a zero", () => {
    // Zero would mean "definitely not". A missing number means "we have nothing
    // to state".
    render(
      <VerdictCard entry={{ ...preliminary, probability: null }} status="partial" />,
    );
    expect(screen.getByTestId("confidence").textContent).not.toContain("0%");
    expect(screen.getByTestId("confidence").textContent).toMatch(/no number/i);
  });

  it("says outright which execution level this is", () => {
    const { rerender } = render(<VerdictCard entry={preliminary} status="partial" />);
    expect(screen.getByTestId("verdict-stage").textContent).toMatch(/preliminary/i);
    rerender(<VerdictCard entry={preliminary} status="final" />);
    expect(screen.getByTestId("verdict-stage").textContent).toMatch(/final/i);
  });
});

describe("the calibration sentence", () => {
  it("names an uncalibrated threshold outright", () => {
    expect(calibrationSentence("uncalibrated", calibration)).toMatch(/preliminary threshold/i);
  });

  it("a calibrated threshold converts precision into mistakes per hundred", () => {
    const sentence = calibrationSentence("calibrated", calibration);
    expect(sentence).toContain("500");
    expect(sentence).toContain("5 cases out of 100");
  });

  it("calibrated without a metric does not invent a number", () => {
    const sentence = calibrationSentence("calibrated", {
      model_version: "lr_v3",
      trained_on: 500,
      precision_at_threshold: null,
    });
    expect(sentence).toContain("500");
    expect(sentence).not.toMatch(/cases out of 100/);
  });

  it("calibrated without a model admits the metrics are missing", () => {
    expect(calibrationSentence("calibrated", null)).toMatch(/unavailable/i);
  });
});
