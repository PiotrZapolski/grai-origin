import { BRAND, MICRO_LABEL_CLASS } from "../lib/theme";

export interface FooterProps {
  /** The name of the current screen, the last crumb of the breadcrumb. */
  screen: string;
  className?: string;
}

/**
 * The footer with the breadcrumb `GRAI ORIGIN / CASE 03 / <screen>` (section
 * 13.1). The same layout returns in the case file report, so that the jury sees
 * the visual language of their own brief turned into a product.
 */
export function Footer({ screen, className = "" }: FooterProps) {
  const crumbs = [BRAND.name, BRAND.caseId, screen];

  return (
    <footer
      className={`flex items-center gap-2 border-t border-muted/20 px-6 py-4 text-muted ${MICRO_LABEL_CLASS} ${className}`}
    >
      {crumbs.map((crumb, index) => (
        <span key={crumb} className="flex items-center gap-2">
          {index > 0 && (
            <span aria-hidden="true" className="text-muted/60">
              /
            </span>
          )}
          <span>{crumb}</span>
        </span>
      ))}
    </footer>
  );
}

export default Footer;
