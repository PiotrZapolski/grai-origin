/**
 * Tests of the evidence visualizations from `components/viz/`.
 *
 * All these components share one rule and it is that rule that is examined here:
 * **they draw exclusively what really arrived**. The tests therefore check the
 * states of absence above all - whether a panel without a matrix says the matrix
 * is missing instead of drawing anything, and whether a panel without an offset
 * distribution refrains from turning it into a pretty shape. A chart out of
 * nothing is a worse fault in this product than an empty panel, because it
 * undermines every other number on screen.
 *
 * `HTMLCanvasElement.getContext` does not exist in jsdom, so we substitute a mock
 * 2D context. The point is that the drawing code really runs and the test catches
 * an exception in the drawing loop, not that pixels get checked.
 */
import { beforeAll, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import type { StreamEvent } from "../lib/contracts";
import { AlignmentMatrix } from "../components/viz/AlignmentMatrix";
import { AlignmentRibbon, spanShare } from "../components/viz/AlignmentRibbon";
import { OffsetHistogram } from "../components/viz/OffsetHistogram";
import { StreamChronograph, stageLanes } from "../components/viz/StreamChronograph";
import { VerdictLift, changesBetweenVerdicts } from "../components/viz/VerdictLift";
import {
  readSpikes,
  readPath,
  dominantIndex,
  pathSlope,
  pathSegments,
  scale,
  dominantShare,
  pathExtent,
} from "../components/viz/geometry";

beforeAll(() => {
  const mockContext = () => ({
    setTransform: () => undefined,
    clearRect: () => undefined,
    beginPath: () => undefined,
    moveTo: () => undefined,
    lineTo: () => undefined,
    stroke: () => undefined,
    save: () => undefined,
    restore: () => undefined,
    setLineDash: () => undefined,
    drawImage: () => undefined,
    fillRect: () => undefined,
    arc: () => undefined,
    fill: () => undefined,
    putImageData: () => undefined,
    createImageData: (w: number, h: number) => ({
      data: new Uint8ClampedArray(w * h * 4),
      width: w,
      height: h,
    }),
    imageSmoothingEnabled: true,
    strokeStyle: "",
    fillStyle: "",
    lineWidth: 1,
    lineCap: "butt",
    lineJoin: "miter",
  });
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
    configurable: true,
    value: mockContext,
  });
});

/* -------------------------------------------------------------------------- */
/* Geometry                                                                   */
/* -------------------------------------------------------------------------- */

describe("evidence geometry", () => {
  it("the alignment path is read only from pairs of numbers", () => {
    expect(readPath([[0, 0], [1, 2]])).toEqual([
      { q: 0, c: 0 },
      { q: 1, c: 2 },
    ]);
    // Rubbish in the contract has no right to turn into a point with coordinate zero.
    expect(readPath([["a", 1], [2], null, [3, "b"]])).toEqual([]);
    expect(readPath(null)).toEqual([]);
    expect(readPath([[0, Number.NaN]])).toEqual([]);
  });

  it("the extent of the board comes from the path, and an empty path gives zero", () => {
    expect(pathExtent([{ q: 0, c: 0 }, { q: 4, c: 7 }])).toEqual({
      queryFrames: 5,
      candidateFrames: 8,
    });
    expect(pathExtent([])).toEqual({ queryFrames: 0, candidateFrames: 0 });
  });

  it("the slope of a vertical segment does not pretend to be one", () => {
    const segments = pathSegments([{ q: 0, c: 0 }, { q: 0, c: 3 }, { q: 2, c: 5 }]);
    expect(segments[0].slope).toBeNull();
    expect(segments[1].slope).toBe(1);
  });

  it("the slope of the whole path comes from the endpoints, not from a mean of quotients", () => {
    // A mean of the segment slopes would give 1.5 here; the quotient of the
    // increments gives 1.25, which is what the picture shows as the angle of the
    // path.
    expect(pathSlope([{ q: 0, c: 0 }, { q: 2, c: 4 }, { q: 4, c: 5 }])).toBe(1.25);
    expect(pathSlope([{ q: 1, c: 1 }])).toBeNull();
  });

  it("a scale with a zero domain returns the middle instead of dividing by zero", () => {
    expect(scale(5, 0, 10, 0, 100)).toBe(50);
    expect(scale(3, 3, 3, 0, 80)).toBe(40);
  });

  it("the histogram spikes reject input that cannot be trusted", () => {
    expect(readSpikes([{ offset: 0.5, count: 12 }])).toEqual([{ offset: 0.5, count: 12 }]);
    expect(readSpikes([])).toBeNull();
    expect(readSpikes([{ offset: 0.5 }])).toBeNull();
    expect(readSpikes([{ offset: 0.5, count: -1 }])).toBeNull();
    expect(readSpikes("not an array")).toBeNull();
  });

  it("the dominant spike and its share are computed from the distribution", () => {
    const spikes = [
      { offset: 0, count: 2 },
      { offset: 1, count: 14 },
      { offset: 2, count: 4 },
    ];
    expect(dominantIndex(spikes)).toBe(1);
    expect(dominantShare(spikes)).toBeCloseTo(14 / 20, 5);
    expect(dominantShare([])).toBeNull();
  });
});

/* -------------------------------------------------------------------------- */
/* Harmonic matrix                                                            */
/* -------------------------------------------------------------------------- */

const PATH: Array<[number, number]> = [[0, 0], [1, 1], [2, 3], [3, 4], [4, 6], [5, 7]];

describe("alignment matrix", () => {
  it("a missing key in the evidence is not a zero but waiting", () => {
    render(<AlignmentMatrix status={undefined} path={[]} />);
    expect(screen.getByTestId("alignment-matrix").getAttribute("data-state")).toBe("not-started");
    expect(screen.getByText(/a missing result is not zero/i)).toBeInTheDocument();
  });

  it("a status other than ok shows a worded state, not an empty board", () => {
    const { container } = render(
      <AlignmentMatrix status="not_applicable" reason="the candidate is instrumental" path={PATH} />,
    );
    expect(screen.getByText(/the candidate is instrumental/i)).toBeInTheDocument();
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("without a matrix and without a path the panel says there is nothing to draw", () => {
    const { container } = render(<AlignmentMatrix status="ok" path={[]} />);
    expect(screen.getByTestId("alignment-matrix").getAttribute("data-state")).toBe("no-data");
    expect(container.querySelector("canvas")).toBeNull();
  });

  it("the path alone is drawn on the board and the panel admits the matrix is missing", () => {
    render(<AlignmentMatrix status="ok" path={PATH} qmax={0.63} coverage={0.58} />);
    const panel = screen.getByTestId("alignment-matrix");
    expect(panel.getAttribute("data-matrix")).toBe("none");
    expect(panel.getAttribute("data-path-points")).toBe("6");
    expect(screen.getByText(/the background of the board\s+stays empty|the background of the board stays empty/i))
      .toBeInTheDocument();
    expect(screen.getByTestId("matrix-board")).toBeInTheDocument();
  });

  it("with a matrix the panel stops explaining itself and shows the heatmap", () => {
    const matrix = [
      [0.1, 0.2, 0.9],
      [0.4, 0.8, 0.3],
      [0.9, 0.1, 0.2],
    ];
    render(<AlignmentMatrix status="ok" path={[[0, 0], [1, 1], [2, 2]]} matrix={matrix} />);
    expect(screen.getByTestId("alignment-matrix").getAttribute("data-matrix")).toBe("present");
    expect(screen.queryByText(/the background of the board stays empty/i)).toBeNull();
  });

  it("the path slope is described as a derivative, not as a separate measurement", () => {
    render(<AlignmentMatrix status="ok" path={PATH} />);
    expect(screen.getByTestId("path-slope")).toBeInTheDocument();
    expect(screen.getByText(/a derivative of the\s+path from the contract|a derivative of the path from the contract/i))
      .toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */
/* Offset histogram                                                           */
/* -------------------------------------------------------------------------- */

describe("histogram of offset differences", () => {
  it("without a distribution no histogram comes into being", () => {
    const { container } = render(
      <OffsetHistogram status="ok" matchedHashes={512} peakRatio={0.46} repetitions={3} offset={43.8} />,
    );
    expect(screen.getByTestId("offset-histogram").getAttribute("data-distribution")).toBe("none");
    expect(screen.getByText(/did not arrive in the evidence/i)).toBeInTheDocument();
    expect(container.querySelectorAll("[data-spike]").length).toBe(0);
    // Only the numbers that really arrived stay on screen.
    expect(screen.getByText("512")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("the noise threshold is drawn on the scale, not merely described", () => {
    render(<OffsetHistogram status="ok" peakRatio={0.46} matchedHashes={512} />);
    expect(screen.getByTestId("noise-threshold")).toBeInTheDocument();
  });

  it("with a distribution the dominant spike is the only element in the accent", () => {
    const { container } = render(
      <OffsetHistogram
        status="ok"
        bins={[
          { offset: -0.4, count: 3 },
          { offset: 0.0, count: 41 },
          { offset: 0.4, count: 5 },
        ]}
        peakRatio={0.82}
        repetitions={1}
      />,
    );
    expect(screen.getByTestId("offset-histogram").getAttribute("data-distribution")).toBe("present");
    expect(container.querySelectorAll("[data-spike='dominant']").length).toBe(1);
    expect(container.querySelectorAll("[data-spike='background']").length).toBe(2);
  });

  it("a rejection by the gate shows the reason, not a zero bar", () => {
    const { container } = render(
      <OffsetHistogram status="gated" reason="confidence below the threshold" bins={[{ offset: 0, count: 9 }]} />,
    );
    expect(screen.getByText(/confidence below the threshold/i)).toBeInTheDocument();
    expect(container.querySelectorAll("[data-spike]").length).toBe(0);
  });
});

/* -------------------------------------------------------------------------- */
/* Verdict lift                                                               */
/* -------------------------------------------------------------------------- */

function event(stage: string, status: string, level = 2): StreamEvent {
  return { stage, level, status, detail: {} } as StreamEvent;
}

describe("verdict lift", () => {
  it("the reasoning comes from the events between one verdict and the other", () => {
    const stream = [
      event("harmonic", "done", 1),
      event("verdict", "partial", 1),
      event("transcript", "gated"),
      event("melodic", "running"),
      event("melodic", "done"),
      event("verdict", "final"),
      event("commonality", "done", 1),
    ];
    // A step in progress has contributed nothing yet, and whatever arrived after
    // the final verdict could not have changed it.
    expect(changesBetweenVerdicts(stream)).toEqual(["transcript", "melody"]);
  });

  it("without two verdicts there is nothing to justify", () => {
    expect(changesBetweenVerdicts([event("verdict", "partial", 1)])).toEqual([]);
  });

  it("a change of class is visible as a transition, not a swapped string", () => {
    render(
      <VerdictLift
        currentClass="VERSION"
        currentProbability={0.94}
        probabilityStatus="calibrated"
        previousClass="NONE"
        previousProbability={0.12}
        changedBy={["transcript", "melody"]}
      />,
    );
    expect(screen.getByTestId("verdict-lift").getAttribute("data-lifted")).toBe("true");
    expect(screen.getByTestId("previous-class")).toBeInTheDocument();
    expect(screen.getByTestId("previous-marker")).toBeInTheDocument();
    expect(screen.getByText(/transcript, melody/i)).toBeInTheDocument();
  });

  it("the first verdict does not pretend to be a lift", () => {
    render(
      <VerdictLift currentClass="VERSION" currentProbability={0.71} probabilityStatus="uncalibrated" />,
    );
    expect(screen.getByTestId("verdict-lift").getAttribute("data-lifted")).toBe("false");
    expect(screen.queryByTestId("previous-marker")).toBeNull();
    expect(screen.getByText(/^raw, not calibrated$/i)).toBeInTheDocument();
  });

  it("a missing probability does not turn into a zero", () => {
    render(
      <VerdictLift currentClass="NONE" currentProbability={null} probabilityStatus="uncalibrated" />,
    );
    expect(screen.queryByTestId("current-marker")).toBeNull();
    expect(screen.getByText(/^none$/i)).toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */
/* Alignment ribbon                                                           */
/* -------------------------------------------------------------------------- */

describe("ribbon of the common span", () => {
  it("the share of a span is clipped to the length of the recording", () => {
    expect(spanShare([10, 20], 100)).toEqual({ from: 0.1, to: 0.2 });
    expect(spanShare([90, 200], 100)).toEqual({ from: 0.9, to: 1 });
    expect(spanShare(null, 100)).toBeNull();
    expect(spanShare([1, 2], null)).toBeNull();
  });

  it("without an alignment on both sides the ribbon does not appear", () => {
    render(
      <AlignmentRibbon
        alignment={{ query_span: [1, 2], candidate_span: null, transposition: null, tempo_ratio: null }}
        queryDuration={100}
        candidateDuration={100}
      />,
    );
    expect(screen.getByTestId("alignment-ribbon").getAttribute("data-ribbon")).toBe("none");
    expect(screen.queryByTestId("ribbon")).toBeNull();
  });

  it("without samples the wave does not pretend to be a measurement", () => {
    render(
      <AlignmentRibbon
        alignment={{ query_span: [10, 20], candidate_span: [60, 70], transposition: null, tempo_ratio: 1.06 }}
        queryDuration={180}
        candidateDuration={180}
      />,
    );
    expect(screen.getByTestId("ribbon")).toBeInTheDocument();
    expect(screen.getByTestId("query-wave").getAttribute("data-measured")).toBe("false");
    expect(screen.getByText(/does not come from a measurement/i)).toBeInTheDocument();
  });

  it("with samples it draws as many bars as it was given", () => {
    const { container } = render(
      <AlignmentRibbon
        alignment={{ query_span: [10, 20], candidate_span: [60, 70], transposition: null, tempo_ratio: null }}
        queryPeaks={[0.2, 0.5, 0.9, 0.4]}
        candidatePeaks={[0.1, 0.3]}
        queryDuration={100}
        candidateDuration={100}
      />,
    );
    expect(container.querySelectorAll("[data-testid='query-wave'] [data-bar]").length).toBe(4);
    expect(container.querySelectorAll("[data-testid='candidate-wave'] [data-bar]").length).toBe(2);
  });
});

/* -------------------------------------------------------------------------- */
/* Chronograph                                                                */
/* -------------------------------------------------------------------------- */

describe("run chronograph", () => {
  it("events present at mount are not a measurement of the run", () => {
    render(
      <StreamChronograph
        events={[
          { stage: "ingest", level: 1, status: "done", detail: {} },
          { stage: "fingerprint", level: 1, status: "done", detail: {} },
          { stage: "harmonic", level: 1, status: "done", detail: {} },
        ]}
      />,
    );
    expect(screen.getByTestId("chronograph").getAttribute("data-measurement")).toBe("none");
    expect(screen.getByText(/nothing to\s+measure the run from|nothing to measure the run from/i))
      .toBeInTheDocument();
  });

  it("a stage lane runs from its first to its last event", () => {
    const events = [
      { stage: "harmonic", level: 1, status: "running", detail: {} },
      { stage: "harmonic", level: 1, status: "done", detail: {} },
      { stage: "verdict", level: 1, status: "partial", detail: {} },
    ];
    const lanes = stageLanes(events, [0, 400, 900]);
    expect(lanes.length).toBe(2);
    expect(lanes[0]).toMatchObject({ stage: "harmonic", from: 0, to: 400, status: "done" });
    expect(lanes[1]).toMatchObject({ stage: "verdict", from: 900, to: 900 });
  });

  it("the preliminary and the final verdict are two separate lanes, because their levels differ", () => {
    const lanes = stageLanes(
      [
        { stage: "verdict", level: 1, status: "partial", detail: {} },
        { stage: "verdict", level: 2, status: "final", detail: {} },
      ],
      [100, 800],
    );
    expect(lanes.length).toBe(2);
    expect(lanes.map((lane) => lane.level)).toEqual([1, 2]);
  });
});
