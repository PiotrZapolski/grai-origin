import { describe, it, expect } from "vitest";
import {
  ACCENT_CLASSES,
  MICRO_LABEL_CLASS,
  TECHNICAL_VALUE_CLASS,
  VERDICT_LABELS,
  theme,
} from "../lib/theme";
import { VERDICT_CLASSES } from "../lib/contracts";

describe("visual system", () => {
  it("every evidence class has a label", () => {
    for (const verdictClass of VERDICT_CLASSES) {
      expect(VERDICT_LABELS[verdictClass]).toBeTruthy();
    }
  });

  it("lime is a signal, not decoration", () => {
    // Global Constraint 11: the accent only for classes that are a signal
    expect(ACCENT_CLASSES.length).toBeLessThan(VERDICT_CLASSES.length / 2);
    expect(ACCENT_CLASSES).not.toContain("NONE");
    expect(ACCENT_CLASSES).not.toContain("COMMON");
  });

  it("the labels are uppercase", () => {
    for (const label of Object.values(VERDICT_LABELS)) {
      expect(label).toBe(label.toUpperCase());
    }
  });

  it("technical values get the fixed-width typeface", () => {
    // Section 13.1: numeric results, timecodes and hashes. A fixed pitch is the
    // signal that a number comes from a measurement and is not decoration, so
    // cutting font-mono out of the token has to raise a red flag.
    expect(TECHNICAL_VALUE_CLASS.split(/\s+/)).toContain("font-mono");
    // A micro-label is not a technical value: uppercase and tracking, not monospace.
    expect(MICRO_LABEL_CLASS.split(/\s+/)).not.toContain("font-mono");
    expect(MICRO_LABEL_CLASS).toContain("uppercase");
  });

  it("the background is darker than the surface of the cards", () => {
    const brightness = (hex: string) =>
      parseInt(hex.slice(1, 3), 16) + parseInt(hex.slice(3, 5), 16) + parseInt(hex.slice(5, 7), 16);
    expect(brightness(theme.bg)).toBeLessThan(brightness(theme.surface));
  });
});
