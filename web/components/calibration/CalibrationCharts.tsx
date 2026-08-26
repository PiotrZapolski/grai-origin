import type { ReactNode } from "react";
import type { CalibrationInfo, ProbabilityStatus, VerdictClass } from "../../lib/contracts";
import { formatPercent } from "../../lib/format";
import {
  HEADING_CLASS,
  MICRO_LABEL_CLASS,
  TECHNICAL_VALUE_CLASS,
  VERDICT_LABELS,
} from "../../lib/theme";

/**
 * Screen E9 - calibration (sections 10.3, 10.4, 10.5).
 *
 * The heart of the message: the score of a similarity function is not a
 * confidence. Instead of "87 percent similarity" the screen says "confidence 94
 * percent, the threshold calibrated on 500 pairs, at this level the system is
 * wrong in 6 cases out of 100".
 *
 * Two rules keep this screen in check:
 *
 * 1. **Missing data is a message, not an empty chart.** `calibration === null`
 *    means the model does not exist yet (level 1), so the screen says it is
 *    waiting. Axes with no points would suggest a measurement that never
 *    happened.
 * 2. **Classes without a model are named outright.** `LYRICS` and
 *    `EXCERPT_WORK` have no model and never will, because the catalogue holds no
 *    original-adaptation pairs. A system saying "I have no data here" is a
 *    stronger argument than a system pretending to have it everywhere.
 *
 * The charts are drawn directly in SVG. A ROC and a reliability diagram are a
 * dozen or so points each, so a charting library would be a dependency with no
 * work to do.
 */

/** A point of the ROC curve: the false alarm rate and the hit rate. */
export interface RocPoint {
  fpr: number;
  tpr: number;
}

/** A bucket of the calibration curve: declared confidence against observed. */
export interface ReliabilityBin {
  predicted: number;
  observed: number;
  count: number;
}

/**
 * The points of the charts. The API contract does not carry them (section 12
 * knows only `model_version`, `trained_on` and `precision_at_threshold`), so they
 * arrive separately, from the calibration artifact. The absence of this object is
 * a valid state.
 */
export interface CalibrationCurves {
  auc?: number | null;
  roc: RocPoint[];
  reliability: ReliabilityBin[];
}

export interface CalibrationChartsProps {
  calibration: CalibrationInfo | null;
  curves?: CalibrationCurves | null;
  /** The confidence of the match being shown, if the screen accompanies a verdict. */
  probability?: number | null;
  probabilityStatus?: ProbabilityStatus;
  /** Classes without a model. By default the two from section 10.4. */
  uncalibratedClasses?: VerdictClass[];
  className?: string;
}

const DEFAULT_UNCALIBRATED: VerdictClass[] = ["LYRICS", "EXCERPT_WORK"];

/** The reason for the missing model per class. A label instead of removing the class from the product. */
const UNCALIBRATED_REASON: Partial<Record<VerdictClass, string>> = {
  LYRICS:
    "In the catalogue translations are separate works, so original-adaptation pairs simply do not exist. The class stays in the product, because it answers a real legal question: reworking the lyrics is a different right from a cover.",
  EXCERPT_WORK:
    "The longest_common_run threshold is written in by hand, not learned. Compositional borrowing has no paired examples in the catalogue.",
};

/* -------------------------------------------------------------------------- */
/* Drawing                                                                    */
/* -------------------------------------------------------------------------- */

const PAD = 14;
const SIZE = 86;

/** A normalized 0..1 value into an SVG coordinate. The Y axis grows upwards, as on a chart. */
function px(value: number): number {
  return PAD + Math.min(Math.max(value, 0), 1) * SIZE;
}

function py(value: number): number {
  return PAD + SIZE - Math.min(Math.max(value, 0), 1) * SIZE;
}

function ChartFrame({
  chart,
  title,
  xLabel,
  yLabel,
  children,
}: {
  chart: string;
  title: string;
  xLabel: string;
  yLabel: string;
  children: ReactNode;
}) {
  return (
    <figure className="rounded-inner border border-muted/20 p-4">
      <figcaption className={`text-muted ${MICRO_LABEL_CLASS}`}>{title}</figcaption>
      <svg
        data-chart={chart}
        role="img"
        aria-label={title}
        viewBox={`0 0 ${PAD * 2 + SIZE} ${PAD * 2 + SIZE}`}
        className="mt-3 w-full text-muted"
      >
        {/* The axes. The colour comes from currentColor, so the printed report inverts them along with the text. */}
        <line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(0)} stroke="currentColor" strokeWidth={0.6} />
        <line x1={px(0)} y1={py(0)} x2={px(0)} y2={py(1)} stroke="currentColor" strokeWidth={0.6} />
        {/* The reference diagonal: a random model on the ROC, perfect calibration on the reliability chart. */}
        <line
          x1={px(0)}
          y1={py(0)}
          x2={px(1)}
          y2={py(1)}
          stroke="currentColor"
          strokeWidth={0.5}
          strokeDasharray="2 2"
          opacity={0.5}
        />
        {children}
      </svg>
      <p className={`mt-2 text-muted ${MICRO_LABEL_CLASS}`}>
        {xLabel} / {yLabel}
      </p>
    </figure>
  );
}

function RocChart({ points, auc }: { points: RocPoint[]; auc?: number | null }) {
  const path = points.map((p) => `${px(p.fpr)},${py(p.tpr)}`).join(" ");
  return (
    <div>
      <ChartFrame
        chart="roc"
        title="ROC curve"
        xLabel="false alarms"
        yLabel="hits"
      >
        <polyline points={path} fill="none" stroke="currentColor" strokeWidth={1.4} className="text-text" />
        {points.map((p, i) => (
          <circle key={i} cx={px(p.fpr)} cy={py(p.tpr)} r={1.4} fill="currentColor" className="text-text" />
        ))}
      </ChartFrame>
      <p className="mt-2 text-sm text-muted">
        AUC{" "}
        <span className={TECHNICAL_VALUE_CLASS}>
          {typeof auc === "number" ? auc.toFixed(2) : "none"}
        </span>
      </p>
    </div>
  );
}

function ReliabilityChart({ bins }: { bins: ReliabilityBin[] }) {
  const path = bins.map((b) => `${px(b.predicted)},${py(b.observed)}`).join(" ");
  const total = bins.reduce((sum, b) => sum + b.count, 0);
  return (
    <div>
      <ChartFrame
        chart="reliability"
        title="Calibration curve"
        xLabel="declared confidence"
        yLabel="observed accuracy"
      >
        <polyline points={path} fill="none" stroke="currentColor" strokeWidth={1.4} className="text-text" />
        {bins.map((b, i) => (
          <circle
            key={i}
            cx={px(b.predicted)}
            cy={py(b.observed)}
            r={1.6}
            fill="currentColor"
            className="text-text"
          />
        ))}
      </ChartFrame>
      <p className="mt-2 text-sm text-muted">
        A point on the diagonal means that the declared confidence matches the observed
        accuracy. The buckets cover{" "}
        <span className={TECHNICAL_VALUE_CLASS}>{total}</span> cases.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                     */
/* -------------------------------------------------------------------------- */

/** 0.94 -> "94%". Confidence is shown as a percentage, because that is how the sentence from 10.5 reads. */
function percent(value: number): string {
  return formatPercent(value);
}

/** Precision 0.94 -> 6 mistakes out of 100. The number a reader really carries away. */
function mistakesPer100(precision: number): number {
  return Math.round((1 - precision) * 100);
}

export function CalibrationCharts({
  calibration,
  curves = null,
  probability = null,
  probabilityStatus = "uncalibrated",
  uncalibratedClasses = DEFAULT_UNCALIBRATED,
  className = "",
}: CalibrationChartsProps) {
  const hasCurves = Boolean(curves && (curves.roc.length > 0 || curves.reliability.length > 0));

  return (
    <article
      className={`origin-card overflow-hidden ${className}`}
      aria-label="Calibration"
    >
      <header className="px-6 pt-6">
        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>Calibration</p>
        <h2 className={`mt-2 text-2xl ${HEADING_CLASS}`}>What this number is worth</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          The score of a similarity function is not a confidence. The confidence comes from a
          model trained on pairs from the catalogue and has a verifiable rate of mistakes.
        </p>
      </header>

      {calibration === null ? (
        <section className="border-t border-muted/20 px-6 py-6">
          {/*
            We deliberately do not draw empty axes here. A chart with no points
            looks like a measurement that came out zero, and this is the absence
            of a measurement.
          */}
          <p className="text-sm leading-relaxed text-text">
            The screen is waiting for calibration data. The model does not exist yet, so the
            numbers next to the matches are raw detector scores, not probabilities.
          </p>
        </section>
      ) : (
        <>
          <section className="border-t border-muted/20 px-6 py-5">
            {probability !== null && probabilityStatus === "calibrated" ? (
              <>
                <p className="flex items-baseline gap-3">
                  <span className={`text-muted ${MICRO_LABEL_CLASS}`}>Confidence</span>
                  <span className={`text-4xl ${TECHNICAL_VALUE_CLASS}`}>
                    {percent(probability)}
                  </span>
                </p>
                <p className="mt-3 text-sm leading-relaxed text-muted">
                  {calibration.precision_at_threshold === null
                    ? `Threshold calibrated on ${calibration.trained_on} pairs from the SecondHandSongs catalogue. The precision at the operating threshold has not been measured yet.`
                    : `Threshold calibrated on ${calibration.trained_on} pairs from the SecondHandSongs catalogue. At this level the system is wrong in ${mistakesPer100(calibration.precision_at_threshold)} cases out of 100.`}
                </p>
              </>
            ) : (
              <p className="text-sm leading-relaxed text-muted">
                {`The calibration model is trained on ${calibration.trained_on} pairs from the SecondHandSongs catalogue.`}
              </p>
            )}

            <dl className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-inner border border-muted/20 p-4">
                <dt className={`text-muted ${MICRO_LABEL_CLASS}`}>Training pairs</dt>
                <dd className={`mt-2 text-xl ${TECHNICAL_VALUE_CLASS}`}>{calibration.trained_on}</dd>
              </div>
              <div className="rounded-inner border border-muted/20 p-4">
                <dt className={`text-muted ${MICRO_LABEL_CLASS}`}>Precision at the threshold</dt>
                <dd className={`mt-2 text-xl ${TECHNICAL_VALUE_CLASS}`}>
                  {calibration.precision_at_threshold === null
                    ? "not measured"
                    : calibration.precision_at_threshold.toFixed(2)}
                </dd>
              </div>
              <div className="rounded-inner border border-muted/20 p-4">
                <dt className={`text-muted ${MICRO_LABEL_CLASS}`}>Model version</dt>
                <dd className={`mt-2 text-xl ${TECHNICAL_VALUE_CLASS}`}>
                  {calibration.model_version}
                </dd>
              </div>
            </dl>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              The operating threshold is chosen for precision, not for recall: a false alarm
              about an infringement costs more than a miss.
            </p>
          </section>

          <section className="border-t border-muted/20 px-6 py-5">
            <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>Charts</h3>
            {hasCurves && curves ? (
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                <RocChart points={curves.roc} auc={curves.auc} />
                <ReliabilityChart bins={curves.reliability} />
              </div>
            ) : (
              <p className="mt-3 text-sm leading-relaxed text-muted">
                The model exists but sent no curve points. Rather than draw them out of the
                threshold alone, the screen leaves this space empty.
              </p>
            )}
          </section>
        </>
      )}

      <section className="border-t border-muted/20 px-6 py-5">
        <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>Classes without calibration</h3>
        <ul className="mt-3 flex flex-col gap-3">
          {uncalibratedClasses.map((verdictClass) => (
            <li
              key={verdictClass}
              data-verdict={verdictClass}
              className="rounded-inner border border-muted/40 px-4 py-3"
            >
              <p className={`text-text ${MICRO_LABEL_CLASS}`}>{VERDICT_LABELS[verdictClass]}</p>
              <p className="mt-2 text-sm font-semibold text-text">
                Preliminary threshold, no calibration data.
              </p>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                {UNCALIBRATED_REASON[verdictClass] ??
                  "The class has no model. The threshold is written in by hand and has no measured rate of mistakes behind it."}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}

export default CalibrationCharts;
