import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { CriteriaBars } from "../components/criteria/CriteriaBars";

// vitest.config.ts has `globals: false`, so @testing-library/react does not
// register its own cleanup and the next tests in the file would render on the
// leftovers of the previous ones. Without this the "previous screen" counts as
// the current one.
afterEach(cleanup);

describe("E5 breakdown by criterion", () => {
  it("has exactly four criteria", () => {
    // D5: no rhythm and no video - there is no detector behind them
    render(<CriteriaBars evidence={{}} />);
    expect(screen.getAllByTestId("criterion-bar")).toHaveLength(4);
    expect(screen.queryByText(/rhythm/i)).toBeNull();
    expect(screen.queryByText(/video/i)).toBeNull();
  });

  it("not_applicable shows a worded state, not a zero", () => {
    // Global Constraint 4
    render(<CriteriaBars evidence={{
      lyrics: { status: "not_applicable", reason: "instrumental" } }} />);
    expect(screen.getByText(/not applicable/i)).toBeInTheDocument();
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("gated shows the rejection by the gate", () => {
    render(<CriteriaBars evidence={{
      lyrics: { status: "gated", reason: "asr_confidence" } }} />);
    expect(screen.getByText(/gate/i)).toBeInTheDocument();
  });

  it("shows the commonality indicator next to every bar", () => {
    render(<CriteriaBars evidence={{ harmonic: { status: "ok", qmax_score: 0.7 } }}
                         commonality={{ corpus_frequency: 1240, corpus_size: 4128 }} />);
    expect(screen.getByText(/1,240 works of the corpus/)).toBeInTheDocument();
  });
});
