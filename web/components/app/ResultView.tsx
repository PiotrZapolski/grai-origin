"use client";

/**
 * The result view: the cover, the verdict card and the tabs with the details.
 *
 * This is the punchline of the whole show, so it gets the full frame, and the
 * evidence, the criteria, the ranking and the supplementary screens drop into
 * tabs below it.
 *
 * **The view is mounted from the first verdict onwards and never disappears.**
 * The page hides it with a class rather than unmounting it - card E3 is what
 * remembers where the verdict was lifted from and to (section 12), and
 * unmounting would erase that trace along with the whole level 1 versus level 2
 * narrative. For the same reason every tab panel is mounted at once and switched
 * by a class: the scroll position and the state of the A/B listen survive a
 * change of tab.
 *
 * The chosen ranking entry and the chosen tab are the state of **this** view.
 * The page has nothing to say about it, so it does not hold it.
 */

import { useEffect, useMemo, useState } from "react";

import type { AnalyzeResult, RankingEntry } from "../../lib/contracts";
import { MICRO_LABEL_CLASS } from "../../lib/theme";
import CriteriaBars, { type CriterionEvidence } from "../criteria/CriteriaBars";
import RankingList from "../ranking/RankingList";
import Cover from "../verdict/Cover";
import { SourceAddresses } from "../verdict/SourceLink";
import VerdictCard from "../verdict/VerdictCard";
import type { InputSelection } from "../input/UrlInput";
import { audioUrlForCandidate, useQueryAudioUrl } from "./audio";
import type { DetectorEnvelopes } from "./envelopes";
import { candidateResults, criterionScores } from "./envelopes";
import EvidencePanels from "./EvidencePanels";
import ScreenFrame from "./ScreenFrame";
import SecondaryTabs from "./SecondaryTabs";

type Tab = "evidence" | "criteria" | "ranking" | "more";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "evidence", label: "EVIDENCE" },
  { id: "criteria", label: "CRITERIA" },
  { id: "ranking", label: "RANKING" },
  { id: "more", label: "MORE" },
];

/**
 * The evidence map in the shape screen E5 wants.
 *
 * This transcription is the single place where the `undefined` of the contract's
 * index signature drops out. A key that is not there does not appear here with
 * an empty value: for screen E5 a missing key means "not measured yet" and that
 * has to cross the boundary without a change of meaning.
 */
function evidenceForCriteria(entry: RankingEntry | null): Record<string, CriterionEvidence> {
  const map: Record<string, CriterionEvidence> = {};
  if (entry === null) return map;
  for (const [key, item] of Object.entries(entry.evidence ?? {})) {
    if (item) map[key] = { status: item.status, reason: item.reason };
  }
  return map;
}

export interface ResultViewProps {
  /** The job the result belongs to. A change clears the chosen entry and tab. */
  jobId: string | null;
  /** The latest state of the result: partial after level 1, final after level 2. */
  result: AnalyzeResult | null;
  /** The first entry of the ranking, if there is one yet. */
  best: RankingEntry | null;
  /** The detector envelopes gathered from the stream - the numbers only travel this way. */
  envelopes: DetectorEnvelopes;
  /** The material chosen on screen E1. The A/B listen takes the query address from it. */
  selection: InputSelection | null;
  queryTitle: string;
  generatedAt: string | null;
  className?: string;
}

export function ResultView({
  jobId,
  result,
  best,
  envelopes,
  selection,
  queryTitle,
  generatedAt,
  className = "",
}: ResultViewProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("evidence");

  useEffect(() => {
    setSelectedId(null);
    setTab("evidence");
  }, [jobId]);

  const ranking = useMemo(() => result?.ranking ?? [], [result]);
  const selected = ranking.find((entry) => entry.candidate.id === selectedId) ?? best;

  const selectedResults = useMemo(
    () => candidateResults(envelopes, selected?.candidate.id),
    [envelopes, selected],
  );
  const criteriaScores = useMemo(
    () => criterionScores(envelopes, selected?.candidate.id),
    [envelopes, selected],
  );
  const criteriaEvidence = useMemo(() => evidenceForCriteria(selected), [selected]);

  const queryAudioUrl = useQueryAudioUrl(result?.query ?? null, selection);
  const candidateAudioUrl = audioUrlForCandidate(selected?.candidate);

  return (
    <div className={`flex min-h-0 min-w-0 flex-1 flex-col gap-4 ${className}`}>
      {/*
        The cover is the punchline of the whole show, not an icon next to a link:
        the owner pastes a cover version and the system shows the cover art of
        the original. Hence the first place in frame and a width that reads from
        a projector.

        The block is capped at 42vh so the tabs below it stay in frame, and the
        cap is enforced with **its own scrollbar**, never by clipping: on a
        1080p projector the verdict card plus the address of the original run
        past the cap, and the address is the one thing the viewer came for. A
        block that clips would hide it with no way to reach it.
      */}
      <div className="flex min-h-0 min-w-0 shrink-0 flex-col gap-5 overflow-y-auto overflow-x-hidden lg:max-h-[42vh] lg:flex-row">
        {best ? (
          <div className="w-full min-w-0 shrink-0 lg:w-[20rem] xl:w-[26rem]">
            <Cover candidate={best.candidate} />
          </div>
        ) : null}

        <ScreenFrame screen="E3 VERDICT" className="min-w-0 flex-1">
          {best ? (
            /*
              The card carries the address of the original as a part of itself,
              so it does not change position in the tree between level 1 and 2
              and is not mounted again. It is the card that remembers where the
              verdict was lifted from and to.
            */
            <VerdictCard
              entry={best}
              status={result?.status ?? "partial"}
              calibration={result?.calibration ?? null}
            />
          ) : (
            <div className="origin-card p-8">
              <p className={`text-muted ${MICRO_LABEL_CLASS}`}>PRELIMINARY VERDICT / LEVEL 1 OF 2</p>
            </div>
          )}
        </ScreenFrame>
      </div>

      <div role="tablist" aria-label="Result details" className="flex shrink-0 flex-wrap gap-2">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === tab}
            onClick={() => setTab(item.id)}
            className={`rounded-full border px-5 py-2 ${MICRO_LABEL_CLASS} ${
              item.id === tab ? "border-text text-text" : "border-muted/30 text-muted"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/*
        Every panel is mounted at once and switched by a class: thanks to that
        the scroll position and the state of the evidence panels survive a change
        of tab, and the A/B listen does not start over on every return. The
        scrolling happens **inside the panel**, so the page stays still.

        The panel has no minimum height: a floor inside a `100dvh` shell that
        cannot scroll is a floor that pushes the bottom of the evidence out of
        reach on a 720p projector. `min-h-0` lets the panel take what is left
        and scroll the rest.
      */}
      <div
        className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden pr-1"
        data-testid="tab-panel"
      >
        <div className={tab === "evidence" ? "" : "hidden"}>
          <ScreenFrame screen="E4 EVIDENCE" title="Evidence">
            {selected && result ? (
              <EvidencePanels
                entry={selected}
                query={result.query}
                results={selectedResults}
                queryAudioUrl={queryAudioUrl}
                candidateAudioUrl={candidateAudioUrl}
              />
            ) : (
              <p className="rounded-card border border-muted/20 bg-surface p-6 text-sm text-muted">
                The evidence panels open together with the preliminary verdict.
              </p>
            )}
          </ScreenFrame>
        </div>

        <div className={tab === "criteria" ? "" : "hidden"}>
          <ScreenFrame screen="E5 CRITERIA" title="Breakdown by criterion">
            <CriteriaBars
              evidence={criteriaEvidence}
              scores={criteriaScores}
              commonality={selected?.commonality ?? null}
            />
          </ScreenFrame>
        </div>

        <div className={tab === "ranking" ? "" : "hidden"}>
          <ScreenFrame screen="E6 RANKING" title="Ranking">
            {ranking.length > 1 ? (
              <>
                <RankingList
                  entries={ranking}
                  selectedId={selected?.candidate.id ?? null}
                  onSelect={setSelectedId}
                />
                <SourceAddresses
                  candidates={ranking}
                  selectedId={selected?.candidate.id ?? null}
                  className="mt-2"
                />
              </>
            ) : (
              <p className="rounded-card border border-muted/20 bg-surface p-6 text-sm text-muted">
                Beyond the first entry there is nothing to show for now.
              </p>
            )}
          </ScreenFrame>
        </div>

        <div className={tab === "more" ? "" : "hidden"}>
          {result ? (
            <SecondaryTabs
              result={result}
              entry={selected}
              best={best}
              selectedId={selected?.candidate.id ?? null}
              queryTitle={queryTitle}
              generatedAt={generatedAt}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default ResultView;
