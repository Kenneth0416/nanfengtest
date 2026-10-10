# Layouts

Every theme in `themes/themes.json` has a template `templates/<theme>.pptx` with the same thirteen layouts
and placeholder names, so a spec works in any theme.

A spec is `{"theme": "<theme>", "slides": [ ... ]}`. A slide is
`{"layout": "<name>", "eyebrow": "...", "title": "...", "so_what": "...", "notes": "...", "fill": {...}}`.
`fill` maps placeholder names to text (a string or a list of paragraphs), to a key
(`{"chart": ...}`, `{"table": ...}`, `{"metric": ...}`), or to `"auto"` where the table says so.
Placeholders left out are removed, never left empty. `*_label` text is set in tracked uppercase.
In a `title` or `statement`, `*words in asterisks*` take the theme's accent (italic in serif themes).

| Layout | Use for | `fill` placeholders | so_what |
|---|---|---|---|
| **Cover** | slide 1, always | `subtitle`, `headline`, `caveat` (each may be `"auto"`), `kpis: "auto"` (four cards) | no |
| **Section** | a divider in a longer IC pack | `body` | no |
| **Statement** | one sentence for the room, full-bleed dark; at most one per deck | `statement` (or `"auto"`: the first headline sentence), `attribution` (or `"auto"`) | no |
| **Hero number** | one figure carries the message | `hero: {"metric": ...}`, `hero_context` (optional), `chart_label`, `chart`, `source` | yes |
| **Stat row** | the quarter in up to four figures, with the series behind them | `stats: "auto"` (the Cover's four) or a list of 2–4 hero metrics, `chart_label`, `chart`, `source` | yes |
| **Chart + takeaway** | one chart and its so-what beside it | `chart_label`, `chart`, `takeaway`, `source` | yes |
| **Two charts** | two related measures | `left_label`, `left_chart`, `right_label`, `right_chart`, `source` | yes |
| **Chart + table** | a comparison and the exact figures behind it | `chart_label`, `chart`, `table_label`, `table`, `source` | yes |
| **Numbered pillars** | three implications or recommendations under 01 / 02 / 03 | `pillars`: exactly three `{"head", "body"}` | yes |
| **Timeline** | how the market got here, or dates to watch | `steps: "auto"` (last five quarters of vacancy and take-up) or 2–5 `{"when", "head", "body"}` | yes |
| **Signal cards** | what changed and why it matters | `cards: "auto"` (up to six), `talk: "auto"` | no |
| **Sources** | last slide, always | `body: "auto"` (footnotes, ⚠ figures, caveat) | no |
| **Title only** | a full-width table | `table` | yes |

`so_what` is one sentence in a dark band above the source line: the implication for rents, values,
leasing risk or strategy.

## Keys

| Kind | Key | What it draws |
|---|---|---|
| chart | `vacancy` | Central London vacancy by quarter, line, first and latest point labelled |
| chart | `take_up` | take-up by quarter, columns, latest quarter highlighted |
| chart | `rents` | prime rent by submarket, 14 highest, horizontal bars, movers highlighted |
| chart | `investment` | investment by area, this quarter vs long-term average |
| table | `yields` | prime yield by area with change, plus Bank Rate |
| table | `evidence` | IC: submarket x prime rent, rent-free, vacancy, yield, investment |
| hero | `vacancy_pct`, `take_up_msqft`, `investment_gbp_bn`, `active_requirements_msqft`, `bank_rate` | the figure, its caption and change |

Geometry (16:9, 13.333 x 7.5 in) lives in `templates/build_template.js`; the renderer never places
template content by coordinates.
