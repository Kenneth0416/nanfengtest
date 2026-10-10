# Style

Themes live in `themes/themes.json`: colours, fonts and a description in the same fields Grok Build's
template taxonomy uses (`color_scheme`, `typography`, `visual_density`, `background`, `accent_elements`,
`mood`) plus `use_for`. Pick by audience and density, not by topic. `style` flags switch the few things
that differ by family: bold or regular titles, italic hero numerals, a top bar, and whether emphasis is
italic or colour; `fonts.label` (optional) sets a monospace eyebrow font, `colors.band` (optional) a raised
so-what band and table header for themes whose content slides are already dark.

| Theme | Family it stands for in Grok's 193 templates |
|---|---|
| navy-gold | navy institutional with gold (59 navy backgrounds, 46 gold accents) |
| editorial-cream | cream editorial with an italic accent word (35 cream backgrounds, 102 italic emphasis) |
| data-white | white corporate, red / blue, data-heavy |
| charcoal-amber | all-dark charcoal or black with amber and monospace labels (49 dark, 73 mono labels) |
| forest-cream | forest green and cream with brass, serif italic numerals (19 green backgrounds) |

Shared design language in every theme: a tracked uppercase eyebrow over a sentence-case action title, a
short accent rule, cards with a coloured top edge, oversized hero figures, a dark so-what band, a tracked
footer with the page number, and a dark cover with four KPI cards.

Charts are native PowerPoint charts. One axis per chart; a single series has no legend; only a few points
carry labels. Each theme's `series1` / `series2` pair passes the colour-vision check on its own background (adjacent
CVD ΔE ≥ 20, contrast ≥ 3:1). `good` / `bad` / `neutral` mark signal tone only, always with ▲ ▼ ● and a
word, and never stand for a chart series.

To add or change a theme: edit `themes/themes.json`, then
`npm i pptxgenjs@3.12.0 && node templates/build_template.js && python3 templates/finalize_template.py`.
