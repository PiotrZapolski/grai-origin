"use client";

import Badge from "../Badge";
import Footer from "../Footer";
import LegalPanel from "../legal/LegalPanel";
import CalibrationCharts, { type CalibrationCurves } from "../calibration/CalibrationCharts";
import type { AnalyzeResult, RankingEntry, RightsLayer } from "../../lib/contracts";
import { formatPercent, formatTimecode } from "../../lib/format";
import {
  BRAND,
  HEADING_CLASS,
  MICRO_LABEL_CLASS,
  TECHNICAL_VALUE_CLASS,
  theme,
} from "../../lib/theme";

/**
 * Screen E10 - the case file, that is, the report of the result in the branding
 * of the brief.
 *
 * The report is **a page for printing**, not a PDF generator: the file format is
 * deliberately out of scope, and the browser will save this page to PDF better
 * than an attached library would. The whole difference sits in `@media print`.
 *
 * The layout ends with the breadcrumb `GRAI ORIGIN / CASE 03 / CASE FILE` - the
 * jury sees the visual language of their own brief coming back as a product.
 */

export interface CaseFileProps {
  result: AnalyzeResult;
  /** The name of the examined material, if the frontend knows it (E1 knows a URL or a file). */
  queryTitle?: string;
  /** The timestamp the report was generated at. Passed from outside so the report is reproducible. */
  generatedAt?: string;
  curves?: CalibrationCurves | null;
  className?: string;
}

const SCREEN = "CASE FILE";

const LAYER_LABELS: Record<RightsLayer, string> = {
  phonogram: "phonogram",
  work: "work",
  performance: "artistic performance",
};

/**
 * The print stylesheet. The screen is dark, because that is what the product
 * looks like; the page is white, because an evidence report goes into a file and
 * has to be legible once printed. Lime loses contrast on white, so in print the
 * signal is carried by a frame and by the weight of the typeface, not by colour -
 * a high risk flag still stands out from the rest.
 */
const PRINT_CSS = `
@media print {
  @page { margin: 16mm; }
  .origin-casefile {
    background: ${theme.text};
    color: ${theme.bg};
    max-width: none;
  }
  .origin-casefile * {
    background: transparent !important;
    color: ${theme.bg} !important;
    border-color: ${theme.muted} !important;
  }
  .origin-casefile [data-accent="true"] {
    border-color: ${theme.bg} !important;
    border-width: 2px !important;
    font-weight: 900 !important;
  }
  .origin-casefile [data-print-hide="true"] { display: none !important; }
  .origin-casefile section, .origin-casefile article { break-inside: avoid; }
}
`;

function formatProbability(entry: RankingEntry): string {
  if (entry.probability === null) return "none";
  const value = formatPercent(entry.probability);
  return entry.probability_status === "calibrated" ? value : `${value} (preliminary threshold)`;
}

function handlePrint() {
  if (typeof window !== "undefined" && typeof window.print === "function") {
    window.print();
  }
}

export function CaseFile({
  result,
  queryTitle = "Material examined",
  generatedAt,
  curves = null,
  className = "",
}: CaseFileProps) {
  const lead = result.ranking.length > 0 ? result.ranking[0] : null;

  return (
    <article
      className={`origin-casefile mx-auto flex w-full max-w-4xl flex-col gap-6 ${className}`}
      aria-label="Case file"
    >
      <style>{PRINT_CSS}</style>

      <header className="origin-card px-6 py-6">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <p className={`text-text ${MICRO_LABEL_CLASS}`}>{BRAND.name}</p>
            <p className={`mt-1 text-muted ${MICRO_LABEL_CLASS}`}>{BRAND.subtitle}</p>
          </div>
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>{BRAND.caseId}</p>
        </div>
        <h1 className={`mt-5 text-3xl ${HEADING_CLASS}`}>Evidence report</h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          A record of what the system measured: the evidence class, the confidence from the
          model, the rights layer and the flags. This is not a ruling on infringement.
        </p>
        <button
          type="button"
          onClick={handlePrint}
          data-print-hide="true"
          className={`mt-5 rounded-full border border-muted/40 px-5 py-2 text-text ${MICRO_LABEL_CLASS}`}
        >
          Print or save as PDF
        </button>
      </header>

      <section className="origin-card px-6 py-5">
        <h2 className={`text-muted ${MICRO_LABEL_CLASS}`}>Material</h2>
        <dl className="mt-3 grid gap-3 sm:grid-cols-3">
          <div>
            <dt className={`text-muted ${MICRO_LABEL_CLASS}`}>Query</dt>
            <dd className="mt-2 text-sm">{queryTitle}</dd>
          </div>
          <div>
            <dt className={`text-muted ${MICRO_LABEL_CLASS}`}>Length</dt>
            <dd className={`mt-2 text-sm ${TECHNICAL_VALUE_CLASS}`}>
              {formatTimecode(result.query.duration)}
            </dd>
          </div>
          <div>
            <dt className={`text-muted ${MICRO_LABEL_CLASS}`}>Analysis levels</dt>
            <dd className={`mt-2 text-sm ${TECHNICAL_VALUE_CLASS}`}>
              {result.completed_levels.length > 0 ? result.completed_levels.join(", ") : "none"}
            </dd>
          </div>
        </dl>
        {generatedAt && (
          <p className={`mt-4 text-muted ${MICRO_LABEL_CLASS}`}>
            Generated at <span className={TECHNICAL_VALUE_CLASS}>{generatedAt}</span>
          </p>
        )}
        {result.status !== "final" && (
          <p className="mt-4 text-sm leading-relaxed text-muted">
            The report was produced from a result with status{" "}
            <span className={TECHNICAL_VALUE_CLASS}>{result.status}</span>. The analysis was not
            closed at the moment of export.
          </p>
        )}
      </section>

      <section className="origin-card px-6 py-5">
        <h2 className={`text-muted ${MICRO_LABEL_CLASS}`}>Verdict</h2>
        {lead === null ? (
          <p className="mt-3 text-sm leading-relaxed text-text">
            No matches. No candidate crossed the threshold, so the report carries no evidence
            class.
          </p>
        ) : (
          <>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Badge verdict={lead.verdict_class} best />
              <span className={`text-2xl ${HEADING_CLASS}`}>{lead.candidate.name}</span>
              <span className="text-muted">{lead.candidate.artist}</span>
            </div>
            <dl className="mt-4 grid gap-3 sm:grid-cols-3">
              <div>
                <dt className={`text-muted ${MICRO_LABEL_CLASS}`}>Confidence</dt>
                <dd className={`mt-2 text-sm ${TECHNICAL_VALUE_CLASS}`}>
                  {formatProbability(lead)}
                </dd>
              </div>
              <div>
                <dt className={`text-muted ${MICRO_LABEL_CLASS}`}>Leading layer</dt>
                <dd className="mt-2 text-sm">
                  {lead.verdict_layer ? LAYER_LABELS[lead.verdict_layer] : "none"}
                </dd>
              </div>
              <div>
                <dt className={`text-muted ${MICRO_LABEL_CLASS}`}>Source</dt>
                <dd className={`mt-2 break-all text-sm ${TECHNICAL_VALUE_CLASS}`}>
                  {lead.candidate.source_url}
                </dd>
              </div>
            </dl>
            {lead.explanation && (
              <p className="mt-4 text-sm leading-relaxed text-text">{lead.explanation}</p>
            )}
          </>
        )}
      </section>

      {result.ranking.length > 1 && (
        <section className="origin-card px-6 py-5">
          <h2 className={`text-muted ${MICRO_LABEL_CLASS}`}>Remaining matches</h2>
          <ul className="mt-3 flex flex-col gap-2">
            {result.ranking.slice(1).map((entry) => (
              <li
                key={entry.candidate.id}
                className="flex flex-wrap items-center gap-3 border-t border-muted/10 pt-2"
              >
                <span className={`text-muted ${TECHNICAL_VALUE_CLASS}`}>{entry.rank}</span>
                <span className="text-sm">{entry.candidate.name}</span>
                <span className="text-sm text-muted">{entry.candidate.artist}</span>
                <Badge verdict={entry.verdict_class} />
                <span className={`text-sm text-muted ${TECHNICAL_VALUE_CLASS}`}>
                  {formatProbability(entry)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {lead !== null && <LegalPanel legal={lead.legal} />}

      <CalibrationCharts
        calibration={result.calibration}
        curves={curves}
        probability={lead?.probability ?? null}
        probabilityStatus={lead?.probability_status ?? "uncalibrated"}
      />

      <Footer screen={SCREEN} />
    </article>
  );
}

export default CaseFile;
