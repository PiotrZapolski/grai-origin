"use client";

import { useCallback, useEffect, useState } from "react";
import type { DragEvent, FormEvent } from "react";

import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";
import { ExampleButtons } from "./ExampleButtons";
import type { Example } from "./examples";
import { canComputePeaks, peaksFromUrl, peaksFromFile } from "./peaks";
import { Waveform } from "./Waveform";

export interface InputSelection {
  /** What goes to `POST /api/analyze`. For a file - its name. */
  url: string;
  /** The file dropped onto the screen, or `null` when an address was given. */
  file: File | null;
  /** The chosen example, when the material came from a button. */
  example: Example | null;
  candidateSet: string;
}

export interface UrlInputProps {
  onSubmit: (selection: InputSelection) => void;
  /** Locked while an analysis is running. */
  busy?: boolean;
  candidateSet?: string;
  /**
   * Whether to show the three prepared cases under the address field.
   *
   * Off during the show: the owner plays a cover from YouTube out loud and
   * pastes its address, so the example buttons pull the eye away from the only
   * thing the viewer is meant to understand - that the system is given the same
   * address they heard a moment ago. On everywhere else, because examples from
   * local files are the only safeguard against there being no wifi in the room
   * (section 14).
   */
  showExamples?: boolean;
  className?: string;
}

/** An address the browser can read samples from: the same origin. */
function isLocalUrl(url: string): boolean {
  return url.startsWith("/") || url.startsWith("data/") || url.startsWith("./");
}

/**
 * Screen E1 - the input.
 *
 * Three ways to supply material: an address, a file dropped onto the frame and
 * one of the three prepared examples. **The waveform appears the moment the
 * material is chosen, before the analysis starts** (section 13.2) - the
 * component does not wait for the backend, it computes the samples locally
 * whenever they can be computed.
 *
 * The component does not call the API itself. It hands the choice over through
 * `onSubmit`, because submitting the job and moving to screen E2 belongs to the
 * page, not to a text field.
 *
 * The show version is this same component with `showExamples={false}` - it used
 * to stand next to it as `components/app/MaterialInput`, because there was no
 * prop here for turning the examples off. One input in the repository, not two.
 */
export function UrlInput({
  onSubmit,
  busy = false,
  candidateSet = "demo_01",
  showExamples = true,
  className = "",
}: UrlInputProps) {
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [example, setExample] = useState<Example | null>(null);
  const [peaks, setPeaks] = useState<number[] | null>(null);
  const [dragging, setDragging] = useState(false);

  const source = file ? file.name : url.trim();
  const assetUrl = example ? example.assetUrl : url.trim();

  /*
    Samples are computed from a file immediately, and from an address only when
    it lies on the same origin - that is, for the examples from
    `web/public/examples/`. A remote address is not attempted at all: the browser
    would bounce off CORS anyway, and a request known in advance to end in an
    error is noise in the console during the show. The Web Audio check comes
    **before** anything else, so in an environment without it there is no network
    traffic.
  */
  useEffect(() => {
    if (!canComputePeaks()) return;
    let active = true;
    const controller = new AbortController();

    if (file) {
      peaksFromFile(file).then((result) => {
        if (active) setPeaks(result);
      });
    } else if (assetUrl.length > 0 && isLocalUrl(assetUrl)) {
      peaksFromUrl(assetUrl, undefined, controller.signal).then((result) => {
        if (active) setPeaks(result);
      });
    }

    return () => {
      active = false;
      controller.abort();
    };
  }, [file, assetUrl]);

  const takeFile = useCallback((chosen: File | null) => {
    setFile(chosen);
    setExample(null);
    setPeaks(null);
    if (chosen) setUrl("");
  }, []);

  const takeExample = useCallback((chosen: Example) => {
    setExample(chosen);
    setFile(null);
    setPeaks(null);
    setUrl(chosen.queryUrl);
  }, []);

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer?.files?.[0] ?? null;
    if (dropped) takeFile(dropped);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (source.length === 0 || busy) return;
    onSubmit({
      url: file ? file.name : url.trim(),
      file,
      example,
      candidateSet: example ? example.candidateSet : candidateSet,
    });
  };

  return (
    <div className={`flex flex-col gap-6 ${className}`}>
      {/*
        `noValidate` and a text field instead of `type="url"` are **a condition
        for the example buttons to work** here, not cosmetics. An example gives a
        local path (`data/queries/...`), because section 14 requires the demo to
        run from files rather than from the network. A field of type `url` would
        treat such a path as a `typeMismatch`, the browser would block the form
        submission and the only safeguard against there being no wifi in the room
        would stop working. On the backend side `AnalyzeRequest.url` is an
        ordinary string and accepts a relative path without objection.
      */}
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-3 sm:flex-row">
        <input
          type="text"
          inputMode="url"
          name="url"
          value={url}
          onChange={(event) => {
            setUrl(event.target.value);
            setFile(null);
            setExample(null);
            setPeaks(null);
          }}
          placeholder={
            showExamples ? "https://... or a local path" : "https://youtube.com/watch?v=..."
          }
          aria-label="Recording address"
          disabled={busy}
          className={`w-full rounded-md border border-muted/30 bg-bg px-4 py-3 text-text placeholder:text-muted/60 ${TECHNICAL_VALUE_CLASS}`}
        />
        <button
          type="submit"
          disabled={busy || source.length === 0}
          className={`rounded-full border border-muted/40 px-6 py-3 text-text disabled:opacity-40 ${MICRO_LABEL_CLASS}`}
        >
          Analyze
        </button>
      </form>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`rounded-card border border-dashed p-4 text-center ${
          dragging ? "border-text" : "border-muted/30"
        }`}
      >
        <p className={`${MICRO_LABEL_CLASS} text-muted`}>
          or drop an audio file onto this frame
        </p>
        <input
          type="file"
          accept="audio/*,video/*"
          aria-label="Material file"
          onChange={(event) => takeFile(event.target.files?.[0] ?? null)}
          className="mt-2 w-full text-xs text-muted file:mr-3 file:rounded-md file:border file:border-muted/40 file:bg-transparent file:px-3 file:py-1 file:text-muted"
        />
      </div>

      {source.length > 0 ? (
        <Waveform
          source={source}
          peaks={peaks}
          label={file ? "Local file" : example ? "Local example" : "Material to examine"}
        />
      ) : null}

      {showExamples ? (
        <div className="flex flex-col gap-3">
          <p className={`${MICRO_LABEL_CLASS} text-muted`}>Prepared cases</p>
          <ExampleButtons onSelect={takeExample} selectedId={example?.id ?? null} />
        </div>
      ) : null}
    </div>
  );
}

export default UrlInput;
