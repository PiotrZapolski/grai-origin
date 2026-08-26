/**
 * Tests of screens E1 (the input) and E2 (the live pipeline).
 *
 * DOM cleanup between tests is done by `tests/setup.ts` - with `globals: false`
 * @testing-library/react does not register it by itself.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";

import type { StreamEvent } from "../lib/contracts";
import { ExampleButtons } from "../components/input/ExampleButtons";
import { UrlInput } from "../components/input/UrlInput";
import { Waveform } from "../components/input/Waveform";
import AnalysisStage from "../components/app/AnalysisStage";
import { EMPTY_RESULTS } from "../components/app/envelopes";
import StepMap from "../components/app/StepMap";
import {
  chapterId,
  groupIntoChapters,
  runFinished,
  collapseToRows,
} from "../components/pipeline/chapters";
import type { PipelineEvent } from "../components/pipeline/stages";
import { useJobStream } from "../components/pipeline/useJobStream";

/**
 * `useJobStream` is the only piece of these two screens with real asynchronous
 * state and a lifecycle, so we replace `streamJob` from lib/api with a mock that
 * hands control to the test: it decides when an event arrives, when an error
 * does, and checks whether the handle was closed.
 */
const { streamJobMock } = vi.hoisted(() => ({ streamJobMock: vi.fn() }));
vi.mock("../lib/api", () => ({ streamJob: streamJobMock }));

interface Listener {
  jobId: string;
  onEvent: (event: StreamEvent) => void;
  onError?: (error: Error) => void;
  close: ReturnType<typeof vi.fn>;
}

const streams: Listener[] = [];

beforeEach(() => {
  streams.length = 0;
  streamJobMock.mockReset();
  streamJobMock.mockImplementation(
    (jobId: string, onEvent: Listener["onEvent"], onError?: Listener["onError"]) => {
      const listener: Listener = { jobId, onEvent, onError, close: vi.fn() };
      streams.push(listener);
      return { close: listener.close };
    },
  );
});

function event(
  stage: string,
  status: string,
  detail: Record<string, unknown> = {},
  level = 1,
): StreamEvent {
  return { stage, level, status, detail } as StreamEvent;
}

const events = [
  { stage: "ingest", level: 1, status: "done", detail: { duration: 184.2, windows: 37 } },
  { stage: "fingerprint", level: 1, status: "done", detail: { hashes: 4812 } },
  { stage: "shortlist", level: 1, status: "done", detail: { from: 12, to: 8, corpus: 4128 } },
  { stage: "transcript", level: 2, status: "gated",
    detail: { reason: "asr_confidence", next: "separation" } },
];

describe("E2 analysis stage", () => {
  /**
   * The stage mounted the way `app/page.tsx` does it: the stream collapsed into
   * rows, the rows grouped into chapters, one chapter in frame.
   */
  function stage(streamEvents: readonly PipelineEvent[], id?: string) {
    const chapters = groupIntoChapters(collapseToRows(streamEvents));
    const chapter =
      (id === undefined
        ? chapters[chapters.length - 1]
        : chapters.find((item) => item.id === id)) ?? null;
    return render(
      <AnalysisStage
        chapter={chapter}
        events={streamEvents as StreamEvent[]}
        entry={null}
        results={EMPTY_RESULTS}
        queryDuration={null}
      />,
    );
  }

  /** A caption from the fact list of the stage, that is, a `<dt>` - not a counter label. */
  function factCaption(container: HTMLElement, pattern: RegExp): HTMLElement {
    const found = Array.from(container.querySelectorAll("dt")).find((dt) =>
      pattern.test(dt.textContent ?? ""),
    );
    expect(found).toBeDefined();
    return found as HTMLElement;
  }

  it("every stage shows what it produced", () => {
    stage(events, "fingerprint");
    expect(screen.getByText(/4,812/)).toBeInTheDocument();
  });

  it("shows two numbers and both of them are labelled", () => {
    // The Global Constraint from section 13.2: candidates are not the corpus
    const { container } = stage(events, "commonality");
    expect(screen.getByText(/8 of 12/)).toBeInTheDocument();
    expect(screen.getByText(/4,128 works/)).toBeInTheDocument();
    expect(factCaption(container, /commonality corpus/i)).toBeInTheDocument();
  });

  it("each of the two numbers hangs by its own caption", () => {
    // The mere presence of both numbers in the DOM is not enough: the whole point
    // of this screen is that the viewer has no way of confusing them. So we check
    // the caption-value pair, not two independent strings.
    const { container } = stage(events, "commonality");

    const candidatesCaption = factCaption(container, /candidates after shortlist/i);
    expect(candidatesCaption.nextElementSibling?.tagName).toBe("DD");
    expect(candidatesCaption.nextElementSibling?.textContent).toBe("8 of 12");

    const corpusCaption = factCaption(container, /commonality corpus/i);
    expect(corpusCaption.nextElementSibling?.tagName).toBe("DD");
    expect(corpusCaption.nextElementSibling?.textContent).toMatch(/^4,128 works$/);

    // Swapping the two values around is the most dangerous possible fault of this screen.
    expect(candidatesCaption.nextElementSibling?.textContent).not.toMatch(/4,128/);
  });

  it("a gated stage is content, not an error", () => {
    // A rejection by the gate has a **reason** and a **next step** on the stage,
    // not an error message: it is a more interesting moment than a step that
    // simply succeeded.
    const { container } = stage(events, "lyrics");
    expect(factCaption(container, /reason/i).nextElementSibling?.textContent).toMatch(/threshold/i);
    expect(factCaption(container, /next step/i).nextElementSibling?.textContent).toMatch(
      /separation/i,
    );
    expect(container.textContent).toMatch(/gate/i);
  });

  it("technical values in the fixed-width typeface", () => {
    const { container } = stage(events, "fingerprint");
    expect(container.querySelector(".font-mono")).toBeTruthy();
  });

  it("a stage outside the dictionary does not take the stage down", () => {
    stage([{ stage: "rhythm", level: 3, status: "done", detail: { bpm: 128 } }]);
    expect(screen.getByText(/128/)).toBeInTheDocument();
  });
});

/**
 * Lime is the "something is happening here right now" signal, not an ornament
 * (Global Constraint 11). On the live screen it is carried by the **step map**:
 * exactly one step at a time and not a single one once the run has finished.
 */
describe("E2 step map", () => {
  function map(
    streamEvents: readonly PipelineEvent[],
    finished: boolean,
    streamError: Error | null = null,
  ) {
    return render(
      <StepMap
        chapters={groupIntoChapters(collapseToRows(streamEvents))}
        activeId={null}
        onSelect={() => {}}
        finished={finished}
        streamError={streamError}
      />,
    );
  }

  it("lime only on the active step", () => {
    const { container } = map(events, false);
    expect(container.querySelectorAll("[data-accent='true']").length).toBe(1);
    expect(container.querySelectorAll(".text-accent").length).toBe(1);
  });

  it("the final verdict puts the lime out - there is no active step any more", () => {
    const { container } = map(
      [
        ...events,
        { stage: "verdict", level: 2, status: "final", detail: { class: "EXCERPT_WORK" } },
      ],
      true,
    );
    expect(container.querySelectorAll("[data-accent='true']").length).toBe(0);
    expect(container.querySelectorAll(".text-accent").length).toBe(0);
  });

  it("a broken stream puts the lime out instead of pulsing forever", () => {
    // A step glowing after the stream broke claims that something is being
    // computed. Nothing is. The `current` state stays, because that is where the
    // run really stopped - only the signal itself disappears.
    const { container } = map(
      events,
      false,
      new Error("The job stream was interrupted"),
    );
    expect(container.querySelectorAll("[data-state='current']").length).toBe(1);
    expect(container.querySelectorAll("[data-accent='true']").length).toBe(0);
    expect(container.querySelectorAll(".text-accent").length).toBe(0);
  });

  it("a failure does not get the active step signal", () => {
    const { container } = map(
      [{ stage: "melodic", level: 2, status: "failed", detail: { reason: "no notes" } }],
      false,
    );
    expect(container.querySelectorAll("[data-state='current']").length).toBe(1);
    expect(container.querySelectorAll("[data-accent='true']").length).toBe(0);
    expect(container.querySelectorAll(".text-accent").length).toBe(0);
  });

  it("a step that has not happened is not clickable", () => {
    const { container } = map(events, false);
    const future = container.querySelectorAll("[data-state='future']");
    expect(future.length).toBeGreaterThan(0);
    future.forEach((step) => expect((step as HTMLButtonElement).disabled).toBe(true));
  });
});

/**
 * Collapsing the stream into screen rows. The rules from sections 4 and 12 are
 * checked on the function itself, because it is what carries them - every E2
 * screen receives a finished result.
 */
describe("E2 run of events", () => {
  function run(streamEvents: readonly PipelineEvent[]): string[] {
    return collapseToRows(streamEvents).map((row) => `${row.stage}:${row.status}`);
  }

  it("a stage in progress is replaced by its result, not duplicated", () => {
    const rows = collapseToRows([
      { stage: "harmonic", level: 1, status: "running", detail: {} },
      { stage: "harmonic", level: 1, status: "done", detail: { best_qmax: 0.63 } },
    ]);
    expect(rows.length).toBe(1);
    expect(rows[0].detail.best_qmax).toBe(0.63);
  });

  it("the gate stays a step of its own once the stage reaches its end", () => {
    // The gate is a moment of the narrative, not a transitional state: when the
    // transcript finally succeeds, the viewer still has to see why the system
    // started separation.
    expect(
      run([
        { stage: "transcript", level: 2, status: "gated",
          detail: { reason: "asr_confidence", next: "separation" } },
        { stage: "transcript", level: 2, status: "done",
          detail: { words: 47, used_separation: true } },
      ]),
    ).toEqual(["transcript:gated", "transcript:done"]);
  });

  it("a retry after the gate lands under the gate, not above it", () => {
    // Section 4: lyrics -> the gate rejected it -> demucs -> retry. A real engine
    // may precede the gate with a `running` state, so the gate has to take the
    // place of its own transitional state and the result of the retry has to land
    // below it. Otherwise the narrative reads in the opposite order to the run.
    expect(
      run([
        { stage: "transcript", level: 2, status: "running", detail: {} },
        { stage: "transcript", level: 2, status: "gated",
          detail: { reason: "asr_confidence", next: "separation" } },
        { stage: "separation", level: 2, status: "running", detail: { model: "htdemucs" } },
        { stage: "separation", level: 2, status: "done", detail: { seconds: 12.8 } },
        { stage: "transcript", level: 2, status: "running", detail: {} },
        { stage: "transcript", level: 2, status: "done",
          detail: { words: 47, used_separation: true } },
      ]),
    ).toEqual(["transcript:gated", "separation:done", "transcript:done"]);
  });

  it("the preliminary and the final verdict stay two separate rows", () => {
    // Section 4: the stage plus level pair is the key, because `verdict` arrives twice.
    expect(
      run([
        { stage: "verdict", level: 1, status: "partial", detail: { class: "VERSION" } },
        { stage: "verdict", level: 2, status: "final", detail: { class: "EXCERPT_WORK" } },
      ]),
    ).toEqual(["verdict:partial", "verdict:final"]);
  });
});

describe("E1 input", () => {
  it("the waveform appears after pasting an address, before the analysis", () => {
    const onSubmit = vi.fn();
    const { container } = render(<UrlInput onSubmit={onSubmit} />);

    expect(container.querySelector("[data-waveform]")).toBeNull();

    fireEvent.change(screen.getByLabelText(/recording address/i), {
      target: { value: "https://example.com/audio/query.wav" },
    });

    const waveform = container.querySelector("[data-waveform]");
    expect(waveform).not.toBeNull();
    expect(waveform?.getAttribute("data-source")).toBe("https://example.com/audio/query.wav");
    // The waveform comes before the analysis, not after it.
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("sends the address only on the user's request", () => {
    const onSubmit = vi.fn();
    render(<UrlInput onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText(/recording address/i), {
      target: { value: "https://example.com/audio/query.wav" },
    });
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      url: "https://example.com/audio/query.wav",
      file: null,
    });
  });

  it("three prepared examples, each from a local file", () => {
    const onSelect = vi.fn();
    render(<ExampleButtons onSelect={onSelect} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBe(3);

    fireEvent.click(buttons[0]);
    expect(onSelect).toHaveBeenCalledTimes(1);
    const chosen = onSelect.mock.calls[0][0];
    // Section 14: every demo case has to work from local files.
    expect(chosen.queryUrl.startsWith("http")).toBe(false);
    expect(chosen.assetUrl.startsWith("/")).toBe(true);
  });

  it("an example from a local file goes through the form", () => {
    const onSubmit = vi.fn();
    const { container } = render(<UrlInput onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: /reupload/i }));
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0].url).toBe("data/queries/case-01-exact.wav");

    // jsdom does not implement HTML5 constraint validation, so submitting the
    // form in a test would go through even with a `type="url"` field - whereas in
    // a browser a relative path would set `typeMismatch` and the `submit` event
    // would never fire. The example buttons are the only safeguard against there
    // being no network in the room (section 14), so we guard this at the level of
    // the attributes, which in jsdom are real.
    const field = screen.getByLabelText(/recording address/i) as HTMLInputElement;
    expect(field.type).not.toBe("url");
    expect(field.getAttribute("inputmode")).toBe("url");
    const form = container.querySelector("form") as HTMLFormElement;
    expect(form.noValidate).toBe(true);
  });

  it("the waveform draws as many bars as it was given samples", () => {
    const { container } = render(
      <Waveform source="local.wav" peaks={[0.1, 0.4, 0.9, 0.35, 0.2, 0.7]} />,
    );
    expect(container.querySelectorAll("[data-bar]").length).toBe(6);
    expect(container.querySelector("[data-waveform]")?.getAttribute("data-provisional")).toBe(
      "false",
    );
  });

  it("without samples the waveform does not pretend to be a measurement", () => {
    const { container } = render(<Waveform source="https://example.com/a.wav" />);
    const waveform = container.querySelector("[data-waveform]");
    expect(waveform?.getAttribute("data-provisional")).toBe("true");
    expect(screen.getByText(/does not come from a measurement/i)).toBeInTheDocument();
  });
});

describe("E2 job stream", () => {
  it("appends events in order of arrival", () => {
    const { result } = renderHook(() => useJobStream("job-1"));
    expect(streamJobMock).toHaveBeenCalledTimes(1);

    act(() => {
      streams[0].onEvent(event("ingest", "done", { windows: 37 }));
      streams[0].onEvent(event("fingerprint", "done", { hashes: 4812 }));
    });

    expect(result.current.events.map((e) => e.stage)).toEqual(["ingest", "fingerprint"]);
    expect(result.current.finished).toBe(false);
    expect(result.current.latestVerdict).toBeNull();
  });

  it("without a job identifier it does not open a stream", () => {
    const { result } = renderHook(() => useJobStream(null));
    expect(streamJobMock).not.toHaveBeenCalled();
    expect(result.current.events).toEqual([]);
  });

  it("lifts the verdict from preliminary to final", () => {
    const { result } = renderHook(() => useJobStream("job-1"));

    act(() => {
      streams[0].onEvent(event("verdict", "partial", { class: "VERSION" }, 1));
    });
    expect(result.current.latestVerdict?.status).toBe("partial");
    expect(result.current.finished).toBe(false);

    act(() => {
      streams[0].onEvent(event("verdict", "final", { class: "EXCERPT_WORK" }, 2));
    });
    expect(result.current.latestVerdict?.status).toBe("final");
    expect(result.current.finished).toBe(true);
  });

  it("closes the stream on unmount", () => {
    const { unmount } = renderHook(() => useJobStream("job-1"));
    expect(streams[0].close).not.toHaveBeenCalled();
    unmount();
    expect(streams[0].close).toHaveBeenCalledTimes(1);
  });

  it("re-rendering does not open a second stream", () => {
    const { rerender } = renderHook(({ jobId }) => useJobStream(jobId), {
      initialProps: { jobId: "job-1" as string | null },
    });
    rerender({ jobId: "job-1" });
    expect(streamJobMock).toHaveBeenCalledTimes(1);
  });

  it("changing the job closes the previous stream and clears the events", () => {
    const { result, rerender } = renderHook(({ jobId }) => useJobStream(jobId), {
      initialProps: { jobId: "job-1" as string | null },
    });
    act(() => {
      streams[0].onEvent(event("ingest", "done"));
    });
    expect(result.current.events.length).toBe(1);

    rerender({ jobId: "job-2" });

    expect(streams[0].close).toHaveBeenCalledTimes(1);
    expect(streamJobMock).toHaveBeenCalledTimes(2);
    expect(streams[1].jobId).toBe("job-2");
    expect(result.current.events).toEqual([]);
  });

  it("a broken stream reports an error, but the final verdict silences it", () => {
    const { result } = renderHook(() => useJobStream("job-1"));

    act(() => {
      streams[0].onError?.(new Error("The job stream was interrupted"));
    });
    expect(result.current.error?.message).toMatch(/interrupted/i);

    // The stream also ends normally, after the last event. The final verdict has
    // already arrived, so there is nothing to tell the viewer about.
    act(() => {
      streams[0].onEvent(event("verdict", "final", { class: "EXCERPT_WORK" }, 2));
    });
    expect(result.current.error).toBeNull();
  });

  it("an event after unmount no longer sets state", () => {
    const { result, unmount } = renderHook(() => useJobStream("job-1"));
    unmount();
    act(() => {
      streams[0].onEvent(event("ingest", "done"));
    });
    expect(result.current.events).toEqual([]);
  });
});
/**
 * The chapters of the show. Eight moments of the narrative rather than a dozen
 * events - this dictionary feeds both the step map and the analysis stage.
 */
describe("E2 chapters", () => {
  it("a chapter with no event does not exist", () => {
    // Eight chapters are a plan of the narrative, not eight slots to fill. An
    // empty chapter would claim that something is happening when nothing is.
    const chapters = groupIntoChapters(collapseToRows(events));
    expect(chapters.map((chapter) => chapter.id)).toEqual([
      "ingest",
      "fingerprint",
      "commonality",
      "lyrics",
    ]);
  });

  it("a rejection by the gate stays in its chapter with the reason", () => {
    const chapters = groupIntoChapters(collapseToRows(events));
    const lyrics = chapters.find((chapter) => chapter.id === "lyrics");
    expect(lyrics?.rows.map((row) => row.status)).toEqual(["gated"]);
    expect(lyrics?.rows[0].detail.reason).toBe("asr_confidence");
  });

  it("the shortlist and commonality make up a single chapter", () => {
    const chapters = groupIntoChapters([
      { stage: "shortlist", level: 1, status: "done", detail: { from: 12, to: 8 } },
      { stage: "commonality", level: 1, status: "done", detail: { mean_idf: 8.4 } },
    ]);
    expect(chapters.length).toBe(1);
    expect(chapters[0].id).toBe("commonality");
    expect(chapters[0].rows.length).toBe(2);
  });

  it("the preliminary and the final verdict are two separate chapters", () => {
    // Section 12: the verdict arrives twice and the class can change in between.
    // These are two different moments of the narrative, so they must not be
    // merged into one.
    expect(chapterId("verdict", 1)).toBe("verdict-preliminary");
    expect(chapterId("verdict", 2)).toBe("verdict-final");
  });

  it("a stage outside the dictionary gets a chapter of its own instead of falling off the screen", () => {
    const chapters = groupIntoChapters([
      { stage: "rhythm", level: 3, status: "done", detail: { bpm: 128 } },
    ]);
    expect(chapters.length).toBe(1);
    expect(chapters[0].id).toBe("stage:rhythm");
    expect(chapters[0].rows.length).toBe(1);
  });

  it("the run is ended by the final verdict or by a broken stream", () => {
    const withoutVerdict = [{ stage: "ingest", level: 1, status: "done", detail: {} }];
    expect(runFinished(withoutVerdict, false)).toBe(false);
    expect(runFinished(withoutVerdict, true)).toBe(true);
    expect(
      runFinished(
        [{ stage: "verdict", level: 2, status: "final", detail: {} }],
        false,
      ),
    ).toBe(true);
  });
});
