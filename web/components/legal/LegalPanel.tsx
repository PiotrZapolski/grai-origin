"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import type { Legal, RightsLayer } from "../../lib/contracts";
import { HEADING_CLASS, MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";

/**
 * Screen E8 - the legal panel (section 11 of the specification).
 *
 * The system returns flags and an evidence classification, **never a ruling on
 * infringement**. That is not hedging but positioning: the tool is a triage aid
 * for the legal team, not an adjudicating machine. Hence the six decisions this
 * file implements, none of which may be undone in the next refactor:
 *
 * 1. The note that this is not legal advice is **always visible**, at the top of
 *    the panel, at full contrast. It does not hide behind a disclosure. Ever
 *    since the panel started quoting case numbers, that note has become more
 *    important, not less: a case number tempts the reader to read the panel as
 *    an opinion.
 * 2. Every flag and every rights layer carries the **legal basis** it follows
 *    from. The panel has to say not only what the system found, but what it
 *    flows from.
 * 3. The boundary of the tool is **stated outright**, in a section of its own: of
 *    the three conditions of pastiche the system measures two, and the third it
 *    does not measure and never will. Passing over that in silence would be
 *    pretending to completeness.
 * 4. `license_status: "unknown"` is **the absence of information, never the
 *    absence of restrictions** (section 11.3, constraint 9). An unknown status is
 *    more common than a reserved one, so it has to be an active statement of
 *    ignorance rather than an empty field the user will read as permission.
 * 5. `rights_layer` is **a list** and that carries content: `VERSION` touches
 *    two layers at once, because the rightsholders and the terms of protection
 *    differ for each. Next to every layer the panel shows **who holds the
 *    rights**, not just what the layer is called.
 * 6. An open license yields a **ready-made attribution text** to copy with one
 *    click.
 */

/**
 * The panel accepts a type wider than `Legal` by two indicators, because they
 * come from detector A and for classes outside `EXCERPT` they may not be
 * computed at all. They always arrive on the wire (albeit as `null`), but the
 * component has no reason to demand them from the caller.
 */
export type LegalView = Omit<Legal, "recognizability" | "modification"> &
  Partial<Pick<Legal, "recognizability" | "modification">>;

export interface LegalPanelProps {
  legal: LegalView;
  className?: string;
}

/** The short name of the act. The full version appears once, in the panel footer. */
const ACT = "the Act of 4 February 1994";

interface RightsLayerInfo {
  label: string;
  /** Who holds the rights to this layer. Section 11.1, the table of three subjects of protection. */
  holder: string;
  /** Which detector hits this layer. */
  detectors: string;
  note: string;
  basis: string;
}

/**
 * Section 11.1. Three separate subjects of protection, each with a different
 * rightsholder and a different term of protection. Keeping them apart is not a
 * formality: an identical numeric score from detector A (the phonogram) and from
 * detectors B/C/D (the work) does not mean the same thing, so the panel has no
 * right to merge them into a single message.
 */
const RIGHTS_LAYER_INFO: Record<RightsLayer, RightsLayerInfo> = {
  phonogram: {
    label: "PHONOGRAM",
    holder: "The phonogram producer, usually the label.",
    detectors: "Detector A, the acoustic fingerprint.",
    note: "A specific sound recording, that is, this recording and not the work. A phonogram and a work are two different subjects of protection with different rightsholders.",
    basis: `Subject of a related right, chapter 11 of ${ACT} on copyright and related rights.`,
  },
  work: {
    label: "WORK",
    holder: "The composer and the lyricist, or the publisher after a transfer of rights.",
    detectors: "Detectors B (harmony), C (melody), D (lyrics).",
    note: "The creative layer: melody, harmony, lyrics. It exists independently of who recorded it and when.",
    basis: `Art. 1 of ${ACT} on copyright and related rights.`,
  },
  performance: {
    label: "ARTISTIC PERFORMANCE",
    holder: "The performer.",
    detectors: "No detector of its own, signalled with the VERSION class.",
    note: "The way a particular artist performs: interpretation, arrangement, a live rendition.",
    basis: `Subject of a related right, chapter 11 of ${ACT} on copyright and related rights.`,
  },
};

type Severity = "high" | "borderline" | "info";

/** Which indicator from the contract illustrates a given flag. */
type IndicatorKey = "recognizability" | "modification";

interface FlagInfo {
  label: string;
  severity: Severity;
  note: string;
  /** The provision or judgment the flag follows from. Never empty. */
  basis: string;
  indicator?: IndicatorKey;
  /** The three cumulative conditions of pastiche. Listed only with the pastiche flag. */
  conditions?: string[];
}

const PELHAM_I: FlagInfo = {
  label: "RECOGNIZABLE EXCERPT",
  severity: "high",
  note: "The sample remains recognizable to the ear of an average listener, so taking it may require the consent of the phonogram producer.",
  basis:
    "Pelham I, judgment of the CJEU of 29 July 2019 in case C-476/17: a phonogram producer may prohibit the taking of even a very short sample, unless it was included in the new work in a form modified and unrecognizable to the ear on listening.",
  indicator: "recognizability",
};

const PELHAM_II: FlagInfo = {
  label: "POSSIBLE PASTICHE",
  severity: "borderline",
  note: "The excerpt is heavily modified and set in a new context, so it may fall within the pastiche exception despite remaining recognizable.",
  basis:
    "Pelham II, judgment of the CJEU of 14 April 2026 in case C-590/23, interpreting the pastiche exception of art. 5(3)(k) of the InfoSoc Directive. The exception requires three conditions to be met together:",
  conditions: [
    "evocation: the new work evokes one or more existing works,",
    "perceptible difference: the new work differs clearly from its source,",
    "recognizable artistic dialogue: the new work enters into a creative dialogue with the source work that is recognizable as such.",
  ],
  indicator: "modification",
};

const ART_2_PARA_4: FlagInfo = {
  label: "COMMON ELEMENT",
  severity: "info",
  note: "A pattern frequent in the reference corpus, which points to an element shared across the genre (a chord progression, a rhythm) rather than to the borrowing of protected creative work.",
  basis: `Art. 2(4) of ${ACT}: a work created as a result of inspiration by another person's work is not regarded as a derivative work. Protection covers creative expression, not ideas, the conventions of a genre or an unprotected element.`,
};

const ART_2_PARA_1: FlagInfo = {
  label: "LYRICS OVERLAP",
  severity: "info",
  note: "Reworking lyrics is subject to different rights from a cover. An uncalibrated class, with the threshold written in by hand.",
  basis: `Art. 2(1) of ${ACT}: a derivative of another person's work, including a translation and an adaptation, is the subject of a separate copyright, but disposing of it and using it requires the consent of the author of the original work.`,
};

/**
 * The flag dictionary. The keys come from section 11.3 and are the same values
 * the backend sends. A flag outside the dictionary is shown raw: an invented
 * interpretation would be worse than none, and an invented legal basis would be
 * worse twice over.
 */
const FLAG_INFO: Record<string, FlagInfo> = {
  recognizable_excerpt: PELHAM_I,
  possible_pastiche: PELHAM_II,
  common_element: ART_2_PARA_4,
  lyrics_overlap: ART_2_PARA_1,
};

const SEVERITY_CAPTION: Record<Severity, string> = {
  high: "HIGH RISK",
  borderline: "BORDERLINE CASE",
  info: "A FINDING, NOT AN ALERT",
};

const SEVERITY_STYLE: Record<Severity, string> = {
  // Lime exclusively as a signal (Global Constraint 11): only the high risk flag
  // gets it, because only it demands a human reaction.
  high: "border-accent text-accent",
  borderline: "border-muted/60 text-text",
  info: "border-muted/30 text-muted",
};

/**
 * The translation of the legal criteria from Pelham I/II into technical signals.
 *
 * The third row is the reason this table stands in the interface at all: the
 * system does not measure artistic dialogue and never will. A team that points
 * out the boundary of its own tool is more credible than one that pretends to
 * completeness.
 */
const CRITERIA_MAP: Array<{
  criterion: string;
  signal: string;
  measured: boolean;
}> = [
  {
    criterion: "Evocation and recognizability of the sample to the ear",
    signal: "the recognizability indicator, derived from peak_ratio of detector A",
    measured: true,
  },
  {
    criterion: "Perceptible difference from the source",
    signal: "the modification indicator: key, tempo, filtering, loop length",
    measured: true,
  },
  {
    criterion: "Recognizable artistic dialogue",
    signal: "no technical signal, the judgement belongs to a human",
    measured: false,
  },
];

/** Licenses for which the system generates an attribution instead of a risk flag. */
function isOpenLicense(status: string): boolean {
  const s = status.trim().toLowerCase();
  if (s === "" || s === "unknown") return false;
  return (
    s.startsWith("cc-") ||
    s.startsWith("cc0") ||
    s.startsWith("cc ") ||
    s === "public-domain" ||
    s === "pd"
  );
}

function isUnknownLicense(status: string): boolean {
  const s = status.trim().toLowerCase();
  return s === "" || s === "unknown";
}

/** Two decimal places: the indicator is a measurement, not a percentage from a model. */
function formatIndicator(value: number | null | undefined): string | null {
  return typeof value === "number" ? value.toFixed(2) : null;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-muted/20 px-6 py-5">
      <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** The row of a legal basis. One shape for a flag, a layer and an indicator. */
function Basis({ children }: { children: ReactNode }) {
  return (
    <p
      data-basis="true"
      className="mt-2 border-l border-muted/40 pl-3 text-sm leading-relaxed text-muted"
    >
      <span className={`mr-2 text-muted ${MICRO_LABEL_CLASS}`}>Basis</span>
      {children}
    </p>
  );
}

function Indicator({
  title,
  value,
  note,
  basis,
}: {
  title: string;
  value: string | null;
  note: string;
  basis: string;
}) {
  return (
    <div className="rounded-inner border border-muted/20 p-4">
      <p className={`text-muted ${MICRO_LABEL_CLASS}`}>{title}</p>
      <p className={`mt-2 text-2xl ${TECHNICAL_VALUE_CLASS}`}>
        {value ?? <span className="text-base text-muted">not measured</span>}
      </p>
      <p className="mt-2 text-sm leading-relaxed text-muted">{note}</p>
      <Basis>{basis}</Basis>
    </div>
  );
}

export function LegalPanel({ legal, className = "" }: LegalPanelProps) {
  const [copied, setCopied] = useState(false);

  const attribution = legal.required_attribution;
  const openLicense = isOpenLicense(legal.license_status);
  const unknownLicense = isUnknownLicense(legal.license_status);

  const indicators: Record<IndicatorKey, { label: string; value: string | null }> = {
    recognizability: {
      label: "recognizability indicator",
      value: formatIndicator(legal.recognizability),
    },
    modification: {
      label: "modification indicator",
      value: formatIndicator(legal.modification),
    },
  };

  async function handleCopy() {
    if (!attribution) return;
    const clipboard = typeof navigator !== "undefined" ? navigator.clipboard : undefined;
    if (!clipboard) return;
    try {
      await clipboard.writeText(attribution);
      setCopied(true);
    } catch {
      // Failing silently is right here: the attribution text is on screen to be
      // selected anyway, and a clipboard error message adds nothing to the case.
      setCopied(false);
    }
  }

  return (
    <article
      className={`origin-card overflow-hidden ${className}`}
      aria-label="Legal panel"
    >
      <header className="px-6 pt-6">
        <p className={`text-muted ${MICRO_LABEL_CLASS}`}>Legal layer</p>
        <h2 className={`mt-2 text-2xl ${HEADING_CLASS}`}>
          Flags and evidence classification
        </h2>
        {/*
          The note stands right under the heading, at full text contrast, in a
          frame. It is not grey on grey and does not hide behind a disclosure -
          it is a condition of the honesty of the whole screen, not small print.
        */}
        <p
          role="note"
          className="mt-4 rounded-inner border border-muted/40 px-4 py-3 text-sm font-semibold leading-relaxed text-text"
        >
          {legal.disclaimer}
        </p>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          The assessment of infringement is made by a human. The system indicates what the
          match concerns and how strong the signal is.
        </p>
        {/*
          Ever since the panel started quoting case numbers, the risk of reading it
          as an opinion has grown, so the caveat about the role of these references
          comes immediately under the note.
        */}
        <p className="mt-2 text-sm leading-relaxed text-muted">
          The provisions and judgments cited below show what each signal follows from. They
          are neither an assessment of this case nor legal advice.
        </p>
      </header>

      <Section title="Rights layers">
        {legal.rights_layer.length === 0 ? (
          <div className="rounded-inner border border-muted/20 px-4 py-3">
            <p className="text-sm leading-relaxed text-muted">
              The result touches no rights layer. That is what the COMMON class looks like,
              an element shared across the genre, and NONE, the absence of a significant match
              in the candidate set.
            </p>
            <Basis>{ART_2_PARA_4.basis}</Basis>
          </div>
        ) : (
          <>
            <ul className="flex flex-col gap-3">
              {legal.rights_layer.map((layer) => (
                <li
                  key={layer}
                  data-rights-layer={layer}
                  className="rounded-inner border border-muted/20 px-4 py-3"
                >
                  <p className={`text-text ${MICRO_LABEL_CLASS}`}>
                    {RIGHTS_LAYER_INFO[layer].label}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-muted">
                    {RIGHTS_LAYER_INFO[layer].note}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-text">
                    <span className={`mr-2 text-muted ${MICRO_LABEL_CLASS}`}>Rightsholder</span>
                    {RIGHTS_LAYER_INFO[layer].holder}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-muted">
                    <span className={`mr-2 text-muted ${MICRO_LABEL_CLASS}`}>Detector</span>
                    {RIGHTS_LAYER_INFO[layer].detectors}
                  </p>
                  <Basis>{RIGHTS_LAYER_INFO[layer].basis}</Basis>
                </li>
              ))}
            </ul>
            {legal.rights_layer.length > 1 && (
              <p className="mt-3 text-sm leading-relaxed text-muted">
                The match touches several layers at once. That is what the VERSION class looks
                like: the same work in a different performance touches the composition and the
                lyrics as well as the artistic performance, but not the specific recording. The
                same number means something different in each layer, because the rightsholders
                and the terms of protection differ for each.
              </p>
            )}
          </>
        )}
      </Section>

      <Section title="Risk flags">
        {legal.risk_flags.length === 0 ? (
          <p className="text-sm leading-relaxed text-muted">
            No risk flag has been raised. The absence of a flag is not permission to use the
            material.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {legal.risk_flags.map((flag) => {
              const info = FLAG_INFO[flag];
              const severity: Severity = info ? info.severity : "info";
              const accented = severity === "high";
              const indicator = info?.indicator ? indicators[info.indicator] : null;
              return (
                <li
                  key={flag}
                  data-flag={flag}
                  data-severity={severity}
                  data-accent={accented ? "true" : "false"}
                  className={`rounded-inner border px-4 py-3 ${SEVERITY_STYLE[severity]}`}
                >
                  <p className={MICRO_LABEL_CLASS}>{SEVERITY_CAPTION[severity]}</p>
                  <p className={`mt-2 font-semibold ${info ? "" : TECHNICAL_VALUE_CLASS}`}>
                    {info ? info.label : flag}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-muted">
                    {info
                      ? info.note
                      : "A flag outside the interface dictionary. Shown in raw form, without interpretation and without a legal basis: inventing a provision would be worse than not having one."}
                  </p>
                  {/*
                    A number goes next to a flag only when the contract brought
                    one. For classes outside EXCERPT both indicators are empty and
                    the flag then stays with its description alone, without an
                    invented value.
                  */}
                  {indicator?.value && (
                    <p className="mt-2 text-sm leading-relaxed text-muted">
                      {indicator.label}:{" "}
                      <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>
                        {indicator.value}
                      </span>
                    </p>
                  )}
                  {info && <Basis>{info.basis}</Basis>}
                  {info?.conditions && (
                    <ol className="mt-2 flex list-decimal flex-col gap-1 pl-8 text-sm leading-relaxed text-muted">
                      {info.conditions.map((condition) => (
                        <li key={condition}>{condition}</li>
                      ))}
                    </ol>
                  )}
                  {info?.conditions && (
                    <p className="mt-2 text-sm leading-relaxed text-muted">
                      Whether the three conditions are met together is judged by a human. The
                      system measures the first two and stops before the third.
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section title="What the system does not judge">
        {/*
          The strongest point of the whole legal layer and the easiest to lose in
          the next tidy-up of the screen. The section is unconditional: it stands
          even when no flag was raised, because the boundary of the tool does not
          depend on what happened to be detected.
        */}
        <ul className="flex flex-col gap-2">
          {CRITERIA_MAP.map((row) => (
            <li
              key={row.criterion}
              data-criterion={row.measured ? "measured" : "not-measured"}
              className="flex flex-col gap-1 rounded-inner border border-muted/20 px-4 py-3 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4"
            >
              <span className="text-sm leading-relaxed text-text">{row.criterion}</span>
              <span className="text-sm leading-relaxed text-muted">{row.signal}</span>
              <span className={`shrink-0 ${MICRO_LABEL_CLASS} ${row.measured ? "text-muted" : "text-text"}`}>
                {row.measured ? "Measured" : "Not measured"}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-sm leading-relaxed text-text">
          The third condition of pastiche, a recognizable artistic dialogue, is something the
          system does not measure and never will. It flags the situation as requiring human
          judgement instead of substituting a number for it.
        </p>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          The system does not examine the intent of the creator either. In Pelham II the CJEU
          expressly ruled out examining subjective intent: it is enough that the character of a
          pastiche is objectively recognizable to a person who knows the source work. That is
          precisely why measuring a technical signal makes sense here.
        </p>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Concealed imitation and plagiarism remain outside the scope of the pastiche
          exception, so a high modification indicator is not a green light.
        </p>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          The system does not establish access. The chronology of publication is circumstantial
          evidence, not proof that the author of the new work knew the earlier one.
        </p>
      </Section>

      <Section title="Indicators">
        <div className="grid gap-3 sm:grid-cols-2">
          <Indicator
            title="Recognizability"
            value={formatIndicator(legal.recognizability)}
            note="Derived from peak_ratio of detector A. The higher it is with an unmodified fingerprint, the more recognizable the excerpt is to the ear. This is the translation of a criterion applied by a court into a measurable signal, not a metaphor."
            basis="Pelham I, judgment of the CJEU of 29 July 2019 in case C-476/17: the boundary runs where the sample stops being recognizable to the ear."
          />
          <Indicator
            title="Modification"
            value={formatIndicator(legal.modification)}
            note="The degree of departure from the original: a shift of key, of tempo, spectral filtering, the length of the loop in its new context. High modification with recognizability preserved is a borderline case."
            basis="Pelham II, judgment of the CJEU of 14 April 2026 in case C-590/23: the second condition of pastiche, a perceptible difference of the new work from its source."
          />
        </div>
      </Section>

      <Section title="License">
        {unknownLicense ? (
          <div className="rounded-inner border border-muted/40 px-4 py-3">
            <p className={`text-text ${MICRO_LABEL_CLASS}`}>No information</p>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              The license status is unknown. That does not mean the absence of restrictions,
              only the absence of available metadata. An unestablished status is more common
              than a reserved one, and establishing the rights belongs to the legal team.
            </p>
          </div>
        ) : (
          <div className="rounded-inner border border-muted/20 px-4 py-3">
            <p className={`text-muted ${MICRO_LABEL_CLASS}`}>License status</p>
            <p className={`mt-2 text-lg ${TECHNICAL_VALUE_CLASS}`}>{legal.license_status}</p>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              {openLicense
                ? "An open license. Use is conditional on attribution in the form given."
                : "The status declared in the candidate manifest. The terms are checked by the legal team."}
            </p>
          </div>
        )}

        <p className="mt-3 text-sm leading-relaxed text-muted">
          The license status does not follow from the analysis of the audio. It is a separate
          layer of metadata, independent of whether the system detected a similarity.
        </p>

        {attribution && (
          <div className="mt-3 rounded-inner border border-muted/20 px-4 py-3">
            <p className={`text-muted ${MICRO_LABEL_CLASS}`}>Ready-made attribution text</p>
            <p className={`mt-2 text-sm ${TECHNICAL_VALUE_CLASS}`}>{attribution}</p>
            <button
              type="button"
              onClick={handleCopy}
              aria-label="Copy the attribution text"
              data-print-hide="true"
              className={`mt-3 rounded-inner border border-muted/40 px-4 py-2 text-text ${MICRO_LABEL_CLASS}`}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        )}
      </Section>

      <Section title="Sources of the legal bases">
        <ul className="flex flex-col gap-1 text-sm leading-relaxed text-muted">
          <li>
            The Act of 4 February 1994 on copyright and related rights: art. 1 (the work),
            art. 2 (derivative works and inspiration), chapter 11 (related rights).
          </li>
          <li>
            Directive 2001/29/EC (InfoSoc), art. 5(3)(k): the exception for caricature,
            parody and pastiche.
          </li>
          <li>Judgment of the CJEU of 29 July 2019, C-476/17 (Pelham I).</li>
          <li>Judgment of the CJEU of 14 April 2026, C-590/23 (Pelham II).</li>
        </ul>
      </Section>
    </article>
  );
}

export default LegalPanel;
