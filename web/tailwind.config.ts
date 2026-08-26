import type { Config } from "tailwindcss";
import { theme as tokens } from "./lib/theme";

/**
 * Tailwind reads tokens from lib/theme.ts, so colors have a single source of
 * truth. Class names deliberately speak of role, not color: "accent" may
 * only be used where something is a signal (section 13.1).
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: tokens.bg,
        surface: tokens.surface,
        text: tokens.text,
        muted: tokens.muted,
        accent: tokens.accent,
      },
      fontFamily: {
        // A heavy sans-serif antiqua for headings. The `--font-origin-sans`
        // variable is set by `app/layout.tsx` via `next/font/google`; the
        // family name stays as a fallback path, in case someone renders
        // this HTML without the layout.
        sans: ["var(--font-origin-sans)", "Inter Tight", "Inter", "system-ui", "sans-serif"],
        // Headings: an italic serif typeface from grai.fm. The recipe
        // (variant, weight, width, tracking) is carried by `.origin-heading`
        // in globals.css - the family alone, without those four properties,
        // gives an ordinary serif.
        display: ["var(--font-origin-display)", "Georgia", "serif"],
        // Technical values: results, timecodes, hashes.
        mono: [
          "var(--font-origin-mono)",
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
      },
      borderRadius: {
        // Two radii for the whole system and not one more: the card and
        // whatever sits inside it. Previously controls ran on `rounded-md`
        // (6px), while boxes nested inside the card used `rounded-card`
        // (18px), which meant the inner rectangle had the same radius as
        // its own frame.
        //
        // 28px instead of 18px: a strongly rounded card is part of grai.fm's
        // character, not decoration. `inner` stays small, since otherwise a
        // box inside the card would again match the radius of its own outer
        // frame.
        card: "28px",
        inner: "10px",
      },
      letterSpacing: {
        micro: "0.22em",
      },
    },
  },
  plugins: [],
};

export default config;
