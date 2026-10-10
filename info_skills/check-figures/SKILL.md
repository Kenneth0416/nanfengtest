---
name: check-figures
description: The three checks every figure goes through before it reaches the team, and what happens to figures that fail.
---
`check_figures(path, figures, period, publisher)` runs, for every figure:
1. Evidence: the number is printed in that page's text layer. If the page has no text layer (a chart or
   dashboard) it is "image only" and needs a person to look at the page screenshot.
2. Range: the value is plausible for its measure (for example vacancy 0-30%, prime yield 2-12%).
3. Sources: it is compared with what the library holds for the same submarket, measure and period.
   Differences are usually definitions; they are flagged, not "corrected".

A figure passes only if it is in the page text, its label was printed (not inferred) and its value is
plausible. Then:
- `stage_figures` (a colleague's upload): passed figures are pre-ticked; the colleague reviews the rest.
- `save_figures` (an automatic source): passed figures are shared as they are; the rest are shared
  flagged and go to the team's "Needs a person" queue, where anyone can mark them right or wrong.
Never describe a flagged figure as checked, and never drop a figure silently.
