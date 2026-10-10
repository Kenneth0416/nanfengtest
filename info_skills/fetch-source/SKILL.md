---
name: fetch-source
description: Get the content behind a link (web page, RSS feed, PDF, spreadsheet) once, and hand it to the right reading skill.
---
1. Only fetch sources that are automatic (open data), or a single page a colleague shared with you. Never fetch an
   upload-only source: ask a colleague to upload it instead.
2. Call `fetch_source(url)`. It returns the content type and either the page text (HTML), or a saved
   file path (PDF, CSV, Excel, JSON).
3. Route by what came back:
   - PDF -> read-pdf (after dedupe)
   - CSV / Excel / JSON -> read-table
   - HTML article, press release, post -> read-article
   - RSS/Atom -> read-article for each new item
4. If the fetch fails (paywall, 403, timeout), say so plainly. For a colleague's link, still file their
   note with read-article and mark it unverified.
