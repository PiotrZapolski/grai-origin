import type { ReactNode } from "react";

import Footer from "../Footer";
import { MICRO_LABEL_CLASS } from "../../lib/theme";

export interface ScreenFrameProps {
  /** The last crumb of the breadcrumb, e.g. "E3 VERDICT". */
  screen: string;
  /** A micro-label above the content. Screens with their own heading do not want it. */
  title?: string;
  children: ReactNode;
  className?: string;
}

/**
 * The frame of one screen on the page.
 *
 * Section 13.1 requires the breadcrumb `GRAI ORIGIN / CASE 03 / <screen>` **on
 * every screen**. Since ten screens live on a single page, the breadcrumb cannot
 * be a single one at the bottom: it would then be the caption of the page, not
 * of a screen. Every block therefore gets its own footer, and it is the footer
 * that says which screen the viewer's eye is on.
 */
export function ScreenFrame({ screen, title, children, className = "" }: ScreenFrameProps) {
  return (
    <section aria-label={screen} data-screen={screen} className={`flex min-w-0 max-w-full flex-col ${className}`}>
      {title ? <p className={`mb-4 text-muted ${MICRO_LABEL_CLASS}`}>{title}</p> : null}
      <div className="flex flex-col gap-4">{children}</div>
      <Footer screen={screen} className="mt-6 px-0" />
    </section>
  );
}

export default ScreenFrame;
