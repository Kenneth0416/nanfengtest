---
name: read-pdf
description: Read figures from any PDF (agency market reports, dashboards, listed landlords' results, planning reports) by choosing the pages and reading them as images with the vision model.
---
1. `dedupe` first.
2. `pdf_overview(path)`: see which pages hold data. Pages marked "image only" are charts, dashboards or
   scans; they still hold figures and must be read as images.
3. `read_pdf_pages(path, pages)` on EVERY data page (the suggested list is a start; add pages the
   overview shows as tables or dashboards; skip contacts, disclaimers and methodology). Always, even when
   the page has a readable text layer: charts, dashboards and KPI tiles hold figures the text layer does
   not, and a report read from its text alone misses them. The vision model returns each figure with its
   page, where it was and whether its label was printed or inferred. Never collect figures with
   `pdf_page_text`; it is for one sentence of context around a figure already read.
4. Adapt to the document:
   - Agency market reports: headline figures are often on a dashboard page as images, and tables may
     have unlabelled columns. Mark inferred labels as inferred; never guess silently.
   - Listed landlords' results: London office measures are ERV growth, occupancy (vacancy = 100 -
     occupancy), valuation yield and lettings. Use the company's own definitions and say so in `where`.
   - If two pages give different values for the same figure (text vs dashboard), keep both; check-figures
     will flag the conflict.
   - Use `pdf_page_text` when a figure needs its surrounding sentence.
5. `map-submarkets` for every market name, then `check-figures`.
6. A colleague's upload: `stage_figures` (they review and publish). An automatic source: `save_figures`.
   Pass `steps` (e.g. ["dedupe", "read-pdf", "map-submarkets", "check-figures"]) and `method`.
