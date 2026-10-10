---
name: dedupe
description: Before reading or saving anything, check whether the library already has it, so nothing is counted twice and the first contributor keeps the credit.
---
- Reports and files: `dedupe_report(path)`. A duplicate is the same file (hash) or the same publisher and
  quarter. If it is a duplicate, stop and say who added it and when. Only read it anyway if the person
  says it is a different report (for example a Spotlight and a full report for the same quarter).
- Stories, tips and articles: `find_matches(title, text)`. A score of 0.55 or more, or the same company,
  building and size or price, is the same story: `save_item` with `merge_into` so the existing story
  gains the new outlet or colleague instead of appearing twice.
- Never merge two different deals because they are in the same submarket.
