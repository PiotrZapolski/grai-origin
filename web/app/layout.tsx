import type { Metadata } from "next";
import { Fraunces, Inter_Tight, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { BRAND, HEADING_CLASS, MICRO_LABEL_CLASS } from "../lib/theme";

/**
 * The typefaces from section 13.1 were until now **declared in
 * `tailwind.config.ts` but never loaded**: `font-sans` fell back to `system-ui`
 * and `font-mono` to `ui-monospace`. The effect was visible on every heading -
 * `font-black` is weight 900, which the system UI typeface does not have, so the
 * browser either synthesized it or fell back to 700. The "very heavy sans-serif"
 * from the brief was therefore medium.
 *
 * `next/font/google` downloads the files **at build time** and serves them from
 * our own origin, so at runtime there is not a single request to Google and the
 * show does not depend on the network in the room (section 14). That applies to
 * Fraunces as well.
 */
const sans = Inter_Tight({
  subsets: ["latin", "latin-ext"],
  // 400 body, 500 captions, 900 headings. Without weight 900 the whole visual
  // system lost what the brief calls "very heavy".
  weight: ["400", "500", "900"],
  display: "swap",
  variable: "--font-origin-sans",
});

/**
 * The heading typeface from the real grai.fm site.
 *
 * Fraunces is a variable font, so `next/font` takes the whole weight range and
 * it is `.origin-heading` that picks 780 out of it. We load **the italic style
 * only**, because that is the only one that appears in the headings of grai.fm,
 * and the upright would never be used anyway - every kilobyte saved here is a
 * faster first render in the room.
 */
const display = Fraunces({
  subsets: ["latin", "latin-ext"],
  style: ["italic"],
  display: "swap",
  variable: "--font-origin-display",
});

/** Technical values: scores, timecodes, hashes (section 13.1). */
const mono = JetBrains_Mono({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-origin-mono",
});

export const metadata: Metadata = {
  title: `${BRAND.name} - ${BRAND.subtitle}`,
  description: "Establishing the provenance of audio recordings. An evidence class, not a bare number.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-bg font-sans text-text antialiased">
        <div className="origin-circle" aria-hidden="true" />
        <div className="relative z-10 flex min-h-screen flex-col">
          <header className="flex items-baseline gap-3 px-6 py-6">
            <span className={`text-xl ${HEADING_CLASS}`}>{BRAND.name}</span>
            <span className={`text-muted ${MICRO_LABEL_CLASS}`}>{BRAND.subtitle}</span>
          </header>
          <main className="flex-1 px-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
