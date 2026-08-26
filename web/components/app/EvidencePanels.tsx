"use client";

/**
 * Screen E4 - the evidence for one ranking entry.
 *
 * The four panels from section 13.2 stacked into a column and fed from two
 * sources that have to be stitched together here: statuses arrive next to the
 * ranking entry, and measured values exclusively in the detector envelopes from
 * the stream (section 7.0).
 *
 * The panels get their status **from the ranking entry**, because that status
 * concerns this candidate. `undefined` means the key is absent from the evidence
 * map, that is, the detector has not started - and each of the panels can show
 * that as waiting instead of an empty chart.
 */

import type { QueryInfo, RankingEntry } from "../../lib/contracts";
import { MICRO_LABEL_CLASS, TECHNICAL_VALUE_CLASS } from "../../lib/theme";
import { formatTimecodeTenths } from "../../lib/format";
import LyricsDiff from "../evidence/LyricsDiff";
import PianoRoll from "../evidence/PianoRoll";
import SimilarityMatrix from "../evidence/SimilarityMatrix";
import WaveOverlay, { offsetFromAlignment } from "../evidence/WaveOverlay";
import type { CandidateResults } from "./envelopes";

export interface EvidencePanelsProps {
  entry: RankingEntry;
  query: QueryInfo | null;
  results: CandidateResults;
  /** The address of the input material, or `null` when there is nothing to play. */
  queryAudioUrl: string | null;
  /** The address of the candidate recording, or `null`. */
  candidateAudioUrl: string | null;
  className?: string;
}

/**
 * The overlay without audio.
 *
 * The A/B listen is the most important element of the interface, so its absence
 * is content and not an empty frame: the panel says which side is missing and
 * shows the alignment in numbers, which we have anyway. Two waveforms drawn with
 * no way to listen would pretend to be working evidence.
 */
function OverlayWithoutAudio({
  entry,
  missingQuery,
  missingCandidate,
}: {
  entry: RankingEntry;
  missingQuery: boolean;
  missingCandidate: boolean;
}) {
  const offset = offsetFromAlignment(entry.alignment);
  const missing = [
    missingQuery ? "the input material" : null,
    missingCandidate ? `the recording of entry ${entry.candidate.name}` : null,
  ].filter((part): part is string => part !== null);

  return (
    <section data-testid="overlay-without-audio" className="origin-card flex flex-col gap-4 p-6">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className={`text-muted ${MICRO_LABEL_CLASS}`}>TIME OVERLAY</h3>
        {offset !== null ? (
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>
            OFFSET{" "}
            <span className={`text-text ${TECHNICAL_VALUE_CLASS}`}>{offset.toFixed(2)} s</span>
          </p>
        ) : null}
      </header>

      <p className="text-sm text-muted">
        {`A/B listening is unavailable: the API did not return the address of ${missing.join(" or ")}. `}
        The alignment is computed and stands below, but we do not substitute placeholder audio.
      </p>

      {entry.alignment?.query_span && entry.alignment?.candidate_span ? (
        <p className={`text-sm text-muted ${TECHNICAL_VALUE_CLASS}`}>
          {`query ${formatTimecodeTenths(entry.alignment.query_span[0])} to ${formatTimecodeTenths(
            entry.alignment.query_span[1],
          )} / candidate ${formatTimecodeTenths(entry.alignment.candidate_span[0])} to ${formatTimecodeTenths(
            entry.alignment.candidate_span[1],
          )}`}
        </p>
      ) : (
        <p className="text-sm text-muted">
          This entry has no time alignment, so there is no common span to point at either.
        </p>
      )}
    </section>
  );
}

export function EvidencePanels({
  entry,
  query,
  results,
  queryAudioUrl,
  candidateAudioUrl,
  className = "",
}: EvidencePanelsProps) {
  const evidence = entry.evidence ?? {};
  const hasAudio = queryAudioUrl !== null && candidateAudioUrl !== null;

  return (
    <div className={`flex min-w-0 max-w-full flex-col gap-4 ${className}`}>
      {hasAudio ? (
        <WaveOverlay
          queryUrl={queryAudioUrl}
          candidateUrl={candidateAudioUrl}
          queryDuration={query?.duration ?? null}
          alignment={entry.alignment}
          candidateName={entry.candidate.name}
        />
      ) : (
        <OverlayWithoutAudio
          entry={entry}
          missingQuery={queryAudioUrl === null}
          missingCandidate={candidateAudioUrl === null}
        />
      )}

      <div className="min-w-0 max-w-full overflow-x-auto">
        <SimilarityMatrix
        status={evidence.harmonic?.status}
        reason={evidence.harmonic?.reason ?? null}
        path={results.harmonic?.alignment_path ?? []}
        /*
         * The envelope carries one chord sequence per result, and the result
         * belongs to the candidate. The contract has no sequence for the query,
         * so the panel gets the alignment path alone and says so outright,
         * rather than computing a matrix from one real side and one invented
         * one.
         */
        candidateChords={results.harmonic?.chord_sequence}
        qmax={results.harmonic?.qmax_score ?? null}
        transposition={results.harmonic?.transposition ?? entry.alignment?.transposition ?? null}
        tempoRatio={results.harmonic?.tempo_ratio ?? entry.alignment?.tempo_ratio ?? null}
          coverage={results.harmonic?.coverage ?? null}
        />
      </div>

      <LyricsDiff
        status={evidence.lyrics?.status}
        reason={evidence.lyrics?.reason ?? null}
        spans={results.lyrics?.matched_spans ?? []}
        transcript={query?.transcript ?? []}
        candidateName={entry.candidate.name}
      />

      <div className="min-w-0 max-w-full overflow-x-auto">
        <PianoRoll
        status={evidence.melodic?.status}
        reason={evidence.melodic?.reason ?? null}
        ngrams={results.melodic?.matched_ngrams ?? []}
        longestCommonRun={results.melodic?.longest_common_run ?? null}
          msDistance={results.melodic?.ms_distance ?? null}
        />
      </div>
    </div>
  );
}

export default EvidencePanels;
