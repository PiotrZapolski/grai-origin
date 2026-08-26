"use client";

/**
 * The entry view (screen E1): the address field filling the whole frame.
 *
 * One thing on screen and nothing besides it. The viewer has to understand that
 * the system is given the same address they heard a moment ago, so everything
 * that pulls the eye away has been removed from here - including the buttons of
 * the prepared cases that `UrlInput` renders everywhere else.
 */

import type { InputSelection } from "../input/UrlInput";
import UrlInput from "../input/UrlInput";
import { HEADING_CLASS, MICRO_LABEL_CLASS } from "../../lib/theme";
import ScreenFrame from "./ScreenFrame";

export interface EntryScreenProps {
  onSubmit: (selection: InputSelection) => void;
  /** Locks the field while the job is being submitted. */
  busy: boolean;
  error: string | null;
  className?: string;
}

export function EntryScreen({ onSubmit, busy, error, className = "" }: EntryScreenProps) {
  return (
    <div
      className={`mx-auto flex w-full max-w-3xl flex-col justify-center overflow-x-hidden ${className}`}
    >
      <ScreenFrame screen="E1 INPUT">
        <div className="origin-card p-8">
          <p className={`text-muted ${MICRO_LABEL_CLASS}`}>Material to examine</p>
          <h1 className={`mt-4 text-4xl ${HEADING_CLASS}`}>Where does this recording come from</h1>
          <p className="mt-4 max-w-2xl text-muted">
            The system returns an evidence class and its reasoning, not a ruling on
            infringement. Every number on screen has a detector behind it.
          </p>
          {/*
            Without the three example buttons: the owner plays a cover from
            YouTube out loud and pastes its address, so the examples pull the eye
            away from the only thing the viewer is meant to understand. Getting
            them back for a room with no wifi is a matter of deleting one prop.
          */}
          <UrlInput className="mt-8" showExamples={false} onSubmit={onSubmit} busy={busy} />
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-card border border-muted/40 bg-surface p-4 text-sm text-text"
          >
            {error}
          </p>
        ) : null}
      </ScreenFrame>
    </div>
  );
}

export default EntryScreen;
