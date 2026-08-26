"use client";

/**
 * Screens E7-E10 in tabs, below the verdict and the evidence.
 *
 * The reason is staging, not technical. The show lasts ninety seconds, so the
 * verdict and the evidence have to be visible without searching, while these
 * four screens answer questions **asked one after another, never at once**: who
 * was first, what is the risk, where does that confidence come from, what is
 * left on paper. Stacked one under another they would push the evidence off the
 * screen; in tabs each of them has the full width and is one click away.
 */

import { useState } from "react";

import CalibrationCharts from "../calibration/CalibrationCharts";
import CaseFile from "../casefile/CaseFile";
import Footer from "../Footer";
import LegalPanel from "../legal/LegalPanel";
import Timeline, { datedItems } from "../timeline/Timeline";
import type { AnalyzeResult, RankingEntry } from "../../lib/contracts";
import { MICRO_LABEL_CLASS } from "../../lib/theme";

type Tab = "timeline" | "legal" | "calibration" | "casefile";

const SCREENS: Record<Tab, { label: string; screen: string }> = {
  timeline: { label: "TIMELINE", screen: "E7 TIMELINE" },
  legal: { label: "LEGAL PANEL", screen: "E8 LEGAL PANEL" },
  calibration: { label: "CALIBRATION", screen: "E9 CALIBRATION" },
  casefile: { label: "CASE FILE", screen: "E10 CASE FILE" },
};

const ORDER: Tab[] = ["timeline", "legal", "calibration", "casefile"];

export interface SecondaryTabsProps {
  result: AnalyzeResult;
  /** The entry chosen in the ranking - the legal panel concerns it, not always the first one. */
  entry: RankingEntry | null;
  /** The first entry. It is its confidence that the calibration screen describes. */
  best: RankingEntry | null;
  selectedId: string | null;
  queryTitle: string;
  generatedAt: string | null;
  className?: string;
}

export function SecondaryTabs({
  result,
  entry,
  best,
  selectedId,
  queryTitle,
  generatedAt,
  className = "",
}: SecondaryTabsProps) {
  const [active, setActive] = useState<Tab>("timeline");

  const candidates = result.ranking.map((entryItem) => entryItem.candidate);
  const hasDates = datedItems(candidates).length > 0;

  return (
    <section aria-label="Supplementary screens" className={`flex flex-col ${className}`}>
      <div role="tablist" aria-label="Supplementary screens" className="flex flex-wrap gap-2">
        {ORDER.map((key) => {
          const selected = key === active;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              id={`tab-${key}`}
              aria-selected={selected}
              aria-controls={`panel-${key}`}
              onClick={() => setActive(key)}
              className={`rounded-full border px-5 py-2 ${MICRO_LABEL_CLASS} ${
                selected ? "border-text text-text" : "border-muted/30 text-muted"
              }`}
            >
              {SCREENS[key].label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`panel-${active}`}
        aria-labelledby={`tab-${active}`}
        className="mt-4 flex flex-col gap-4"
      >
        {active === "timeline" ? (
          hasDates ? (
            <Timeline items={candidates} selectedId={selectedId} />
          ) : (
            // The axis does not render itself without dates, so the sentence
            // about the reason belongs to the page. An empty tab would read as a
            // failure, and this is a valid, explainable state.
            <p className="rounded-card border border-muted/20 bg-surface p-6 text-sm text-muted">
              No candidate has a date of first publication in the manifest, so the axis has
              nothing to show. The upload date on a video service is not a release date and
              does not go onto this axis.
            </p>
          )
        ) : null}

        {active === "legal" ? (
          entry ? (
            <LegalPanel legal={entry.legal} />
          ) : (
            <p className="text-sm text-muted">There is no entry to describe.</p>
          )
        ) : null}

        {active === "calibration" ? (
          <CalibrationCharts
            calibration={result.calibration}
            probability={best?.probability ?? null}
            probabilityStatus={best?.probability_status ?? "uncalibrated"}
          />
        ) : null}

        {active === "casefile" ? (
          <CaseFile result={result} queryTitle={queryTitle} generatedAt={generatedAt ?? undefined} />
        ) : null}
      </div>

      {/*
        The case file carries its own footer, because the report is a separate
        document and ends with the breadcrumb once printed as well. A second
        footer under it would be the same caption twice.
      */}
      {active === "casefile" ? null : (
        <Footer screen={SCREENS[active].screen} className="mt-6 px-0" />
      )}
    </section>
  );
}

export default SecondaryTabs;
