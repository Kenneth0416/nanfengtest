---
name: brief_deck
description: Turn the London office team brief into a 3-6 slide PowerPoint on one of five house themes, every figure footnoted. Use for "make the brief into slides", "PPT for Monday's meeting", "board deck", "IC slides", "export the brief as pptx", "client update deck".
when-to-use: slides, deck, PowerPoint, pptx, presentation, board pack, IC paper slides, client update
argument-hint: board | ic
allowed-tools: brief_deck_data, brief_deck_guide, build_brief_pptx
license: Apache-2.0
metadata:
  author: london-office-agent
  short-description: Team brief as an editable PowerPoint
---
# Brief deck

Python owns every figure, chart and footnote. You own the storyline: theme, layouts, order and words.
Call `brief_deck_guide` for the notes a step needs instead of guessing: `storyline` (always, before a
spec), `layouts` (placeholders and keys), `style` (themes), `example` / `showcase` (complete specs).

## Steps

1. **Get the data.** `brief_deck_data` with `format` = `board` (default) or `ic` ("investment committee").
   It lists this week's ranked **stories**: what stands out and why (a vacancy move past an alert line,
   investment far from its long-term average, rents that moved, our own deals, a jump in requirements),
   each with a suggested layout. You decide which deserve a slide this week (1-4 content slides), in what
   order, with which chart or table: a week with no capital-markets move gets no capital-markets slide.
   Prefer what moved most and what touches the focus of the person asking.
2. **Pick a theme.** `navy-gold` for the team and the board (default), `editorial-cream` for a research
   note to a wider audience, `data-white` for an IC pack or a dense analyst deck (IC default),
   `charcoal-amber` for a deal discussion on a screen, `forest-cream` for a client or owner update.
3. **Write the spec** `{theme, slides: [...]}` following the `storyline` guide: Cover first, Sources
   last, 3-6 slides, one finding per title (under 90 characters, sentence case, `*asterisks*` round the
   word to stress), one `so_what` sentence on content slides, two or three sentences of `notes` each,
   and a `why` on every slide: the reason this week's data earned it (it is written into the notes).
   Charts, tables, KPI tiles, hero figures, signal cards and footnotes are named by key in `fill`
   (`{"chart": "vacancy"}`, `{"table": "yields"}`, `{"metric": "vacancy_pct"}`, `"auto"`), never typed in.
   Write figures and periods exactly as the data gives them.
4. **Build.** `build_brief_pptx` with `format`, `spec` (and `theme` to override). Without a spec the
   rule-based planner picks the storyline from the same stories; that is the fallback for when no model
   runs, so when you are asked for the deck, write the spec yourself.
5. **If it refuses or reports `problems`**, it names each one ("numbers not in the data: 6.5", "unknown
   layout", "text may overflow in takeaway", "text boxes overlap"). Fix exactly those and build again.
   Never round a figure differently or compute a new one to get past the check.
6. **Reply** with the download link and one line per slide title. Say that market talk is unconfirmed
   and that flagged figures are not yet checked, when there are any.

## Layouts (fill placeholders)

Cover: `subtitle`, `headline`, `caveat` ("auto"), `kpis: "auto"` · Section: `body` · Statement:
`statement` ("auto" = first headline sentence), `attribution` · Hero number: `hero: {"metric"}`,
`hero_context`, `chart_label`, `chart`, `source` · Stat row: `stats` ("auto" or 2-4 metrics),
`chart_label`, `chart`, `source` · Chart + takeaway: `chart_label`, `chart`, `takeaway`, `source` ·
Two charts: `left_label`, `left_chart`, `right_label`, `right_chart`, `source` · Chart + table:
`chart_label`, `chart`, `table_label`, `table`, `source` · Numbered pillars: `pillars` (exactly three
{head, body}) · Timeline: `steps` ("auto" or 2-5 {when, head, body}) · Signal cards: `cards: "auto"`,
`talk: "auto"` · Sources: `body: "auto"` · Title only: `table`.

Keys: charts `vacancy`, `take_up`, `rents`, `investment`; tables `yields`, `evidence` (IC); hero metrics
`vacancy_pct`, `take_up_msqft`, `investment_gbp_bn`, `active_requirements_msqft`, `bank_rate`.
`so_what` goes on Hero number, Stat row, Chart + takeaway, Two charts, Chart + table, Numbered pillars,
Timeline and Title only.

Outside the PoC: `python scripts/build_deck.py --data brief.json [--spec spec.json] [--theme navy-gold]
--out deck.pptx`, then `python scripts/check_deck.py deck.pptx --data brief.json`, then render the slides
to images and look at every one before calling it done.
