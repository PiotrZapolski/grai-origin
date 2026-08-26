"use client";

import { MICRO_LABEL_CLASS } from "../../lib/theme";
import { Badge } from "../Badge";
import type { Example } from "./examples";
import { EXAMPLES } from "./examples";

export interface ExampleButtonsProps {
  onSelect: (example: Example) => void;
  examples?: readonly Example[];
  /** Which example is chosen - a highlight of state, not a signal. */
  selectedId?: string | null;
  className?: string;
}

/**
 * The three buttons with the prepared examples (screen E1).
 *
 * Each of them reaches for a local file (section 14), so the show survives a
 * room with no wifi. The buttons are not lime: lime is an evidentiary signal and
 * not an ornament on a toolbar (section 13.1). The expected class is stated
 * outright, so that it is visible that each button demonstrates a **different**
 * capability of the system.
 */
export function ExampleButtons({
  onSelect,
  examples = EXAMPLES,
  selectedId = null,
  className = "",
}: ExampleButtonsProps) {
  return (
    <div className={`grid grid-cols-1 gap-3 sm:grid-cols-3 ${className}`}>
      {examples.map((example) => {
        const selected = example.id === selectedId;
        return (
          <button
            key={example.id}
            type="button"
            data-example={example.id}
            aria-pressed={selected}
            onClick={() => onSelect(example)}
            className={`flex flex-col gap-2 rounded-card border p-4 text-left transition-colors ${
              selected ? "border-text bg-surface" : "border-muted/25 hover:border-muted/60"
            }`}
          >
            <span className={`${MICRO_LABEL_CLASS} text-text`}>{example.label}</span>
            {/*
              The evidence class goes through `Badge`, exactly as everywhere
              else. It used to be bare text here, and the same content looked
              different on the entry screen than on the verdict, the ranking and
              the case file. `best` stays false: this is a promise about an
              example, not a hit.
            */}
            <Badge verdict={example.expected} className="self-start" />
            <span className="text-sm leading-snug text-muted">{example.description}</span>
          </button>
        );
      })}
    </div>
  );
}

export default ExampleButtons;
