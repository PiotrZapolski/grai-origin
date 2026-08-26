"use client";

/**
 * Audio addresses for the A/B listen of screen E4.
 *
 * The panel gets an address **only when we really have one**. The backend
 * attaches the address to the result only after checking that the file is on
 * disk, so a missing value here means "there is nothing to play", not "we do not
 * know yet". Substituting anything as a placeholder would be a prop in an
 * evidentiary tool, which is exactly what the whole product forbids.
 */

import { useEffect, useState } from "react";

import { API_BASE } from "../../lib/api";
import type { Candidate, QueryInfo } from "../../lib/contracts";
import type { InputSelection } from "../input/UrlInput";

/**
 * A relative address from the API response turned into an address for the
 * browser.
 *
 * `API_BASE` is often empty (the same origin) and then changes nothing. When the
 * frontend sits at a different address than the API, without this prefix
 * `<audio>` would look for the file on its own origin and get a 404.
 */
export function fullUrl(url: string | null | undefined): string | null {
  if (typeof url !== "string" || url.length === 0) return null;
  return url.startsWith("/") ? `${API_BASE}${url}` : url;
}

/** The address of the candidate recording, or `null`. The API layer adds the field, not the manifest. */
export function audioUrlForCandidate(candidate: Candidate | null | undefined): string | null {
  return fullUrl(candidate?.audio_url ?? null);
}

/**
 * The address of the input material.
 *
 * The address from the result takes precedence: it is the very file that went
 * through ingest, and the server serves it with range request support, so
 * seeking to a synchronized point works at all. A local source (a file dropped
 * onto the screen, the asset of a prepared example) is the fallback for a room
 * with no network.
 */
export function useQueryAudioUrl(
  query: QueryInfo | null,
  selection: InputSelection | null,
): string | null {
  const [local, setLocal] = useState<string | null>(null);

  useEffect(() => {
    if (selection?.example) {
      setLocal(selection.example.assetUrl);
      return;
    }

    const file = selection?.file ?? null;
    if (
      file !== null &&
      typeof URL !== "undefined" &&
      typeof URL.createObjectURL === "function"
    ) {
      const objectUrl = URL.createObjectURL(file);
      setLocal(objectUrl);
      // An object URL keeps the file in the tab's memory until the end of the
      // session, so we release it together with the choice of material.
      return () => URL.revokeObjectURL(objectUrl);
    }

    setLocal(null);
    return;
  }, [selection]);

  return fullUrl(query?.waveform_url ?? null) ?? local;
}
