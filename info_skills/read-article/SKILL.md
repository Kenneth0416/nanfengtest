---
name: read-article
description: File news, newsletters, press releases, LinkedIn posts and colleagues' tips as stories: classify, merge with the same story, credit who shared it, score how hot it is.
---
1. If you only have a link, `fetch_source` it. If a colleague wrote what they heard, use their words.
2. `classify_item(title, text)`: category, submarkets, themes, sentiment, importance, size and price.
   Correct it if it is clearly wrong (a requirement is a leasing story; a results statement is market
   statistics) by passing category or markets to `save_item`.
3. `dedupe` with `find_matches`. Same story -> `save_item(merge_into=...)`; otherwise `save_item` new.
   Always pass `shared_by`, `how` and `inbox_id` for a colleague's item so they are credited.
4. `score_hotness(id)` and report the reasons, not just the number.
5. A tip with no published source stays "unverified" until a link or a second source arrives. Never
   turn a rumour into a market figure: tips are stories, not data points.
