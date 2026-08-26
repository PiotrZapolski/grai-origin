# GRAI - Brand Sheet (based on grai.fm)

> Note: this describes the visual system of the **actual grai.fm site**
> (screenshots from August 2026).
> It differs from the style described in `brief-GRAI.md` (there: dark
> background, heavy white sans-serif, lime as the only accent, circle motif).
> These are two different visual languages for the same brand - see the section
> "Discrepancy with the brief" at the bottom.

## Logo / wordmark

- The word "grai" (lowercase), in a bubbly, graffiti-style lettering - thick, "inflated" letters.
- Fill: bright lime green (acid chartreuse, around `#C6F135`), with a black/dark outline.
- Extra flourish: a small star next to the letter "g".
- This is the only genuinely "logotype-like", playful element of the site - everything else is far more restrained.
- Note: on `jobs.grai.fm` (an external Ashby widget) the logo appears in a different, simpler outline variant - that subpage is not fully rebranded.

## Color

| Role | Description | Approximate color |
|---|---|---|
| Page background | very light, warm grey (not pure white) | ~`#F0EFED` |
| Content cards | pure white, heavily rounded corners, subtle shadow, lifted above the background | `#FFFFFF` |
| Primary accent | lime green - used sparingly (logo, small accents) | ~`#C6F135` |
| Accent 1 (highlight) | peach/coral - background under a highlighted word in a heading | pastel coral |
| Accent 2 (highlight) | lavender/violet - background under a second highlighted word | pastel violet |
| Body text | black/near-black on a light background | `#111111`-`#000000` |
| Secondary text | grey (navigation links, dates, footer) | greys |

The rule: lime is a signal/accent, not a background. The pastel highlights
(coral, lavender) are used like a highlighter - a slightly rotated rectangle
under one specific word, never as large areas of color.

## Typography

Two different type families, strongly contrasting with each other:

1. **Display / headline** - large, heavy, italic, condensed (visible in "Terms of Service", "Press", the quotations in the Manifesto). Editorial, magazine-like, strongly expressive.
2. **Text / UI** - a neutral, humanist sans-serif for body copy, navigation, buttons. Regular weight, generous line-height, black text on a light background.

## UI components

- Buttons and fields are fully rounded (pill-shaped): black button ("I'm in"), white text field (e.g. "your email").
- Footer navigation as grey pill links: "manifesto", "jobs", "press", "partners" (the last one is sometimes greyed out/inactive - the section is not ready yet).
- A repeating footer pattern on every subpage:
  - a "home" pill in the center,
  - "copyright, 2026" in the bottom left corner,
  - "terms" / "privacy" in the bottom right corner,
  - a cookies icon in the corner.
- Top right corner: tiktok / discord / linkedin links as plain grey text (no icons).
- Content cards: white, large corner radius, subtle shadow - they "float" above the light grey page background.

## Photography and graphic accents

- Lifestyle photographs, natural framing (e.g. a person dancing in headphones).
- On the Press page: photographs with a dark gradient at the bottom and a bold italic title laid over the image, source plus date underneath (small, grey/green text).
- Informal, "scrapbook" extras: a handwritten post-it style note (e.g. "GRAI's team on repeat rn") pointing at an illustrated album cover thumbnail - it adds a loose, community feel.

## Tone of voice (copy)

- Informal, conversational, written in lowercase: "we're building new ways to listen and respond through music", "want in early? leave your email - the first drop's on us".
- The manifesto is written in short, almost poetic sentences, built on repetition and contrast.
- Signed by name by the three co-founders, with their role underneath (CEO, Co-founder / CTO, Co-founder / President, Co-Founder).

## Site structure (what is visible in the navigation)

- `/` - home page: logo, tagline, early-access sign-up form, footer with links.
- `/manifesto` - the brand manifesto (text on a white card plus a section with quotations over a photo of the sky).
- `/press` - press mentions as cards with an image and a headline quotation.
- `jobs.grai.fm` - job openings (external Ashby widget, simplified branding).
- `/terms`, `/privacy` - legal documents, the same footer and heading face, but a simpler layout.

## Discrepancy with the hackathon brief

`brief-GRAI.md` (case GRAI x VIBESTARS) describes a different visual system:
a near-black background with an olive cast, a single acid lime accent, a very
heavy white sans-serif in the headings, lime micro-labels in all caps, rounded
cards lighter than the background, a large-circle motif in the background, and
a breadcrumb footer "GRAI x VIBESTARS / CASE 03 / 0X".

That is an entirely different mood from the light, pastel, bubbly grai.fm site
described above - dark, "dashboard-like", more technical versus light, playful,
community-oriented.

**A decision for the team to make:** which one should the demo follow - the
branding from the official site (light, lime plus pastels, bubble logo) or the
branding from the hackathon brief materials (dark, strong sans-serif, circle
motif)? Worth settling before UI work begins, to avoid reworking styles halfway
through.
