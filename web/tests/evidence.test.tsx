/**
 * Screen E4 - the evidence. Section 13.2 of the specification.
 *
 * Four panels, but one more important than all the others put together: the time
 * overlay with A/B listening. The brief demands a way to check, and for audio the
 * only real verification is the ear.
 *
 * `wavesurfer.js` and `HTMLMediaElement` do not work in jsdom, so they are mocked
 * here. The assertions concern **the synchronization logic**, not the fact that a
 * mock was called: the test has to catch an A/B button that switches to the wrong
 * position.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { Alignment } from "../lib/contracts";
import { AbPlayer, candidatePosition } from "../components/evidence/AbPlayer";
import { formatTimecodeTenths } from "../lib/format";
import { WaveOverlay, offsetFromAlignment, spanPercent } from "../components/evidence/WaveOverlay";
import {
  SimilarityMatrix,
  chordSimilarityMatrix,
} from "../components/evidence/SimilarityMatrix";
import { LyricsDiff, readSpan } from "../components/evidence/LyricsDiff";
import { PianoRoll, readNgram, notesFromIntervals } from "../components/evidence/PianoRoll";

/* -------------------------------------------------------------------------- */
/* Environment mocks                                                          */
/* -------------------------------------------------------------------------- */

// vi.mock is hoisted to the top of the file, so an ordinary constant from this
// scope would be in the temporal dead zone when the factory is called.
// vi.hoisted lifts it along with the mock.
const { createdWaves } = vi.hoisted(() => ({
  createdWaves: [] as Array<Record<string, unknown>>,
}));

vi.mock("wavesurfer.js", () => {
  return {
    default: {
      create: (options: Record<string, unknown>) => {
        createdWaves.push(options);
        return {
          setTime: vi.fn(),
          setOptions: vi.fn(),
          destroy: vi.fn(),
          on: vi.fn(() => () => undefined),
        };
      },
    },
  };
});

beforeAll(() => {
  // jsdom does not implement playback. We replace the three fields AbPlayer uses
  // so that `currentTime` behaves like an ordinary property: it carries the whole
  // synchronization, so the test has to see it.
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
  createdWaves.length = 0;
});

const queryAudio = () => screen.getByTestId("query-audio") as HTMLAudioElement;
const candidateAudio = () => screen.getByTestId("candidate-audio") as HTMLAudioElement;
const abButton = () => screen.getByRole("button", { name: /A\/B/i });

/* -------------------------------------------------------------------------- */
/* A/B listening                                                              */
/* -------------------------------------------------------------------------- */

describe("E4 A/B listening", () => {
  it("switches the source while keeping the position", () => {
    // Section 13.2: the only real verification for audio is the ear.
    render(<AbPlayer queryUrl="/q.wav" candidateUrl="/c.wav" offset={51.7} />);
    expect(screen.getByTestId("active-source").textContent).toBe("A");
    fireEvent.click(abButton());
    expect(screen.getByTestId("active-source").textContent).toBe("B");
    fireEvent.click(abButton());
    expect(screen.getByTestId("active-source").textContent).toBe("A");
  });

  it("point B is shifted by the alignment offset", () => {
    render(<AbPlayer queryUrl="/q.wav" candidateUrl="/c.wav" offset={51.7} />);
    fireEvent.click(abButton());
    expect(Number(screen.getByTestId("position-b").textContent)).toBeCloseTo(51.7, 1);
  });

  it("switching sets the candidate at the shared point, not at zero", () => {
    render(<AbPlayer queryUrl="/q.wav" candidateUrl="/c.wav" offset={51.7} />);
    fireEvent.click(abButton());
    expect(candidateAudio().currentTime).toBeCloseTo(51.7, 3);
  });

  it("a start in query_span lands exactly in candidate_span", () => {
    // This is the invariant of the product: the jury clicks A/B and hears the
    // same moment.
    render(
      <AbPlayer
        queryUrl="/q.wav"
        candidateUrl="/c.wav"
        offset={51.7}
        querySpan={[12.4, 31.8]}
        candidateSpan={[64.1, 83.5]}
        queryDuration={184.2}
      />,
    );
    expect(Number(screen.getByTestId("position-a").textContent)).toBeCloseTo(12.4, 2);
    fireEvent.click(abButton());
    expect(candidateAudio().currentTime).toBeCloseTo(64.1, 1);
  });

  it("moving the slider moves both sources by the same difference", () => {
    render(
      <AbPlayer queryUrl="/q.wav" candidateUrl="/c.wav" offset={51.7} queryDuration={184.2} />,
    );
    fireEvent.change(screen.getByLabelText(/listening point/i), { target: { value: "20" } });
    expect(queryAudio().currentTime).toBeCloseTo(20, 3);

    fireEvent.click(abButton());
    expect(Number(screen.getByTestId("position-b").textContent)).toBeCloseTo(71.7, 1);
    expect(candidateAudio().currentTime).toBeCloseTo(71.7, 1);
  });

  it("coming back to A returns to the same place in the query", () => {
    render(
      <AbPlayer queryUrl="/q.wav" candidateUrl="/c.wav" offset={51.7} queryDuration={184.2} />,
    );
    fireEvent.change(screen.getByLabelText(/listening point/i), { target: { value: "20" } });
    fireEvent.click(abButton());
    fireEvent.click(abButton());
    expect(queryAudio().currentTime).toBeCloseTo(20, 3);
  });

  it("exactly one source plays at a time", () => {
    render(<AbPlayer queryUrl="/q.wav" candidateUrl="/c.wav" offset={51.7} />);
    fireEvent.click(screen.getByRole("button", { name: /^(play|pause)$/i }));
    expect(queryAudio().dataset.playing).toBe("true");
    expect(candidateAudio().dataset.playing).toBe("false");

    fireEvent.click(abButton());
    expect(queryAudio().dataset.playing).toBe("false");
    expect(candidateAudio().dataset.playing).toBe("true");
  });

  it("without a known length the slider is disabled rather than lying about its range", () => {
    render(<AbPlayer queryUrl="/q.wav" candidateUrl="/c.wav" offset={51.7} />);
    expect(screen.getByLabelText(/listening point/i)).toBeDisabled();
  });

  it("the candidate position does not fall below zero with a negative offset", () => {
    expect(candidatePosition(10, 51.7)).toBeCloseTo(61.7, 3);
    expect(candidatePosition(3, -51.7)).toBe(0);
  });

  it("the timecode is readable to a human", () => {
    expect(formatTimecodeTenths(51.7)).toBe("0:51.7");
    expect(formatTimecodeTenths(184.2)).toBe("3:04.2");
  });
});

/* -------------------------------------------------------------------------- */
/* Time overlay                                                               */
/* -------------------------------------------------------------------------- */

const alignment: Alignment = {
  query_span: [12.4, 31.8],
  candidate_span: [64.1, 83.5],
  transposition: 2,
  tempo_ratio: 1.06,
};

describe("E4 time overlay", () => {
  it("the offset is computed from the starts of both spans", () => {
    expect(offsetFromAlignment(alignment)).toBeCloseTo(51.7, 3);
  });

  it("without an alignment there is no offset and nobody invents one", () => {
    expect(offsetFromAlignment(null)).toBeNull();
    expect(
      offsetFromAlignment({
        query_span: null,
        candidate_span: null,
        transposition: -3,
        tempo_ratio: 0.98,
      }),
    ).toBeNull();
  });

  it("the span highlight is computed as a percentage of the length", () => {
    const span = spanPercent([12.4, 31.8], 184.2);
    expect(span).not.toBeNull();
    expect(span?.left).toBeCloseTo(6.732, 2);
    expect(span?.width).toBeCloseTo(10.532, 2);
  });

  it("a span longer than the recording is clipped to the frame", () => {
    const span = spanPercent([100, 400], 184.2);
    expect(span?.left).toBeCloseTo(54.29, 1);
    expect((span?.left ?? 0) + (span?.width ?? 0)).toBeCloseTo(100, 3);
  });

  it("draws two waves and highlights the common span on both", async () => {
    render(
      <WaveOverlay
        queryUrl="/q.wav"
        candidateUrl="/c.wav"
        queryDuration={184.2}
        candidateDuration={198.0}
        alignment={alignment}
      />,
    );

    await waitFor(() => expect(createdWaves.map((o) => o.url)).toEqual(["/q.wav", "/c.wav"]));

    const querySpanNode = screen.getByTestId("query-common-span");
    const candidateSpanNode = screen.getByTestId("candidate-common-span");
    expect(querySpanNode.style.left.startsWith("6.73")).toBe(true);
    expect(candidateSpanNode.style.left.startsWith("32.37")).toBe(true);
  });

  it("without an alignment it says so outright and does not fake synchronization", async () => {
    render(
      <WaveOverlay
        queryUrl="/q.wav"
        candidateUrl="/c.wav"
        queryDuration={184.2}
        alignment={null}
      />,
    );
    expect(screen.getByText(/no time alignment for this candidate/i)).toBeInTheDocument();
    expect(screen.queryByTestId("query-common-span")).toBeNull();
    // Listening stays, because it is the evidence. Only without an offset.
    fireEvent.click(abButton());
    expect(Number(screen.getByTestId("position-b").textContent)).toBeCloseTo(0, 3);
  });

  it("the playback marker follows the slider", () => {
    render(
      <WaveOverlay
        queryUrl="/q.wav"
        candidateUrl="/c.wav"
        queryDuration={184.2}
        candidateDuration={198.0}
        alignment={alignment}
      />,
    );
    fireEvent.change(screen.getByLabelText(/listening point/i), { target: { value: "92.1" } });
    expect(screen.getByTestId("query-marker").style.left.startsWith("50")).toBe(true);
  });
});

/* -------------------------------------------------------------------------- */
/* Harmonic similarity matrix                                                 */
/* -------------------------------------------------------------------------- */

describe("E4 harmonic matrix", () => {
  it("a missing key in evidence means 'waiting', not an empty matrix", () => {
    // Level 1 sends two keys, not four.
    render(<SimilarityMatrix status={undefined} path={[]} />);
    expect(screen.getByText(/has not computed this candidate yet/i)).toBeInTheDocument();
    expect(screen.queryByTestId("matrix-grid")).toBeNull();
  });

  it("a status other than ok shows a worded state with the reason", () => {
    render(<SimilarityMatrix status="failed" reason="no chromagram path" path={[]} />);
    expect(screen.getByText(/no chromagram path/)).toBeInTheDocument();
    expect(screen.queryByTestId("matrix-grid")).toBeNull();
  });

  it("chord similarity tells the same chord, the same root and a foreign one apart", () => {
    const matrix = chordSimilarityMatrix(["C", "G"], ["C", "Cm", "Am"]);
    expect(matrix[0][0]).toBe(1);
    expect(matrix[0][1]).toBe(0.5);
    expect(matrix[0][2]).toBe(0);
    expect(matrix[1][0]).toBe(0);
  });

  it("a sharp and a flat belong to the name of the chord root", () => {
    expect(chordSimilarityMatrix(["F#m"], ["F#"])[0][0]).toBe(0.5);
    expect(chordSimilarityMatrix(["Bb"], ["B"])[0][0]).toBe(0);
  });

  it("draws the alignment path on the cells of the matrix", () => {
    render(
      <SimilarityMatrix
        status="ok"
        path={[
          [0, 0],
          [1, 1],
          [2, 3],
        ]}
        queryChords={["C", "G", "Am", "F"]}
        candidateChords={["C", "G", "F", "Am"]}
        qmax={0.63}
      />,
    );
    const grid = screen.getByTestId("matrix-grid");
    expect(grid.querySelectorAll("[data-path='true']")).toHaveLength(3);
    expect(
      within(grid).getByTestId("cell-0-0").getAttribute("data-value"),
    ).toBe("1");
  });

  it("without chords it shows the path alone and says the matrix is missing", () => {
    render(
      <SimilarityMatrix
        status="ok"
        path={[
          [0, 0],
          [1, 1],
        ]}
      />,
    );
    expect(screen.getByText(/the alignment path\s+alone/i)).toBeInTheDocument();
    expect(screen.getByTestId("matrix-grid").querySelectorAll("[data-path='true']"))
      .toHaveLength(2);
  });
});

/* -------------------------------------------------------------------------- */
/* Lyrics with highlighting                                                   */
/* -------------------------------------------------------------------------- */

const lyricsSpan = {
  query: [41.0, 46.2],
  candidate: [12.8, 18.1],
  text: "we were counting paper streets",
};

describe("E4 lyrics", () => {
  it("reads a span from a loose dictionary and rejects rubbish", () => {
    expect(readSpan(lyricsSpan)).toEqual({
      query: [41.0, 46.2],
      candidate: [12.8, 18.1],
      text: "we were counting paper streets",
    });
    expect(readSpan({ text: "no times" })).toBeNull();
    expect(readSpan({ query: ["a", "b"], text: "wrong types" })).toBeNull();
    expect(readSpan(null)).toBeNull();
  });

  it("a detector that has not run says it is waiting", () => {
    render(<LyricsDiff status={undefined} spans={[]} />);
    expect(screen.getByText(/has not computed this candidate yet/i)).toBeInTheDocument();
    expect(screen.queryByTestId("query-column")).toBeNull();
  });

  it("an instrumental candidate gets a reason, not a zero", () => {
    render(
      <LyricsDiff status="not_applicable" reason="the candidate is instrumental" spans={[]} />,
    );
    expect(screen.getByText(/the candidate is instrumental/)).toBeInTheDocument();
    expect(screen.queryByTestId("query-column")).toBeNull();
  });

  it("highlights the common phrases in both columns", () => {
    render(
      <LyricsDiff
        status="ok"
        spans={[lyricsSpan]}
        transcript={[
          { word: "hold", start: 18.2, end: 18.5 },
          { word: "we", start: 41.0, end: 41.2 },
          { word: "were", start: 41.2, end: 41.5 },
        ]}
      />,
    );
    const queryColumn = screen.getByTestId("query-column");
    const shared = queryColumn.querySelectorAll("[data-shared='true']");
    expect(shared).toHaveLength(2);
    expect(Array.from(shared).map((node) => node.textContent)).toEqual(["we", "were"]);
    expect(within(screen.getByTestId("candidate-column")).getByText(/paper streets/))
      .toBeInTheDocument();
  });

  it("clicking a phrase seeks playback to its place", () => {
    const seek = vi.fn();
    render(<LyricsDiff status="ok" spans={[lyricsSpan]} onSeek={seek} />);

    fireEvent.click(within(screen.getByTestId("query-column")).getByText(/paper streets/));
    expect(seek).toHaveBeenCalledWith(41.0, "query");

    fireEvent.click(within(screen.getByTestId("candidate-column")).getByText(/paper streets/));
    expect(seek).toHaveBeenCalledWith(12.8, "candidate");
  });

  it("clicking a transcript word seeks to its start", () => {
    const seek = vi.fn();
    render(
      <LyricsDiff
        status="ok"
        spans={[lyricsSpan]}
        transcript={[{ word: "counting", start: 41.5, end: 42.1 }]}
        onSeek={seek}
      />,
    );
    fireEvent.click(screen.getByText("counting"));
    expect(seek).toHaveBeenCalledWith(41.5, "query");
  });
});

/* -------------------------------------------------------------------------- */
/* Melody                                                                     */
/* -------------------------------------------------------------------------- */

describe("E4 melody", () => {
  it("intervals add up into a sequence of pitches", () => {
    expect(notesFromIntervals([2, 2, -3, 5, -2])).toEqual([0, 2, 4, 1, 6, 4]);
    expect(notesFromIntervals([])).toEqual([0]);
  });

  it("reads an n-gram from a loose dictionary", () => {
    expect(
      readNgram({ query_start: 14.1, candidate_start: 65.8, n: 5, intervals: [2, 2, -3, 5, -2] }),
    ).toEqual({ queryStart: 14.1, candidateStart: 65.8, n: 5, intervals: [2, 2, -3, 5, -2] });
    expect(readNgram({ query_start: 14.1 })).toBeNull();
    expect(readNgram({ intervals: ["x"], query_start: 1, candidate_start: 2 })).toBeNull();
  });

  it("a detector that has not run says it is waiting", () => {
    render(<PianoRoll status={undefined} ngrams={[]} />);
    expect(screen.getByText(/has not computed this candidate yet/i)).toBeInTheDocument();
    expect(screen.queryByTestId("pianoroll")).toBeNull();
  });

  it("a failure on one candidate shows the reason", () => {
    render(
      <PianoRoll
        status="failed"
        reason="note extraction returned no track at all"
        ngrams={[]}
      />,
    );
    expect(screen.getByText(/note extraction/)).toBeInTheDocument();
  });

  it("draws the common interval sequence for both recordings", () => {
    render(
      <PianoRoll
        status="ok"
        longestCommonRun={11}
        ngrams={[
          { query_start: 14.1, candidate_start: 65.8, n: 5, intervals: [2, 2, -3, 5, -2] },
        ]}
      />,
    );
    const notes = screen.getByTestId("pianoroll").querySelectorAll("[data-testid='note']");
    // Six pitches times two recordings.
    expect(notes).toHaveLength(12);

    const queryNotes = Array.from(notes).filter((n) => n.getAttribute("data-source") === "query");
    expect(queryNotes.map((n) => n.getAttribute("data-pitch"))).toEqual([
      "0",
      "2",
      "4",
      "1",
      "6",
      "4",
    ]);
    // A higher note lies higher in the picture.
    const y = queryNotes.map((n) => Number(n.getAttribute("y")));
    expect(y[1]).toBeLessThan(y[0]);
    expect(screen.getByText(/11/)).toBeInTheDocument();
  });
});
