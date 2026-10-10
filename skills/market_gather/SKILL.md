---
name: market_gather
description: Gathers market information for the team. Colleagues share links and tips (from a broker call, LinkedIn, an article); the agent reads them, classifies them, merges them with the same story if the team already has it, credits who shared it and scores how hot it is. Also runs open-data collection and checks agency research pages for new report titles.
---
When someone says they heard something, saw a post or pastes a link ("a broker told me Google is
looking for 200,000 sq ft in King's Cross", "have a look at https://..."), call share_tip with their
words and the link. It credits them and tells the whole team. Only market news is a tip: following a
source, a confirmation or a status line ("Following Property Week") is never passed to share_tip.

A gathering round, step by step (the Pi gatherer runs this daily; you can run it on request):
1. list_inbox: links and tips colleagues shared that nobody has processed yet.
2. For each: read_link if there is a link (only that page, once), classify_item, then find_matches.
   A match with score of 0.55 or more, or one you judge to be the same event (same company, building,
   size or price), is the same story: save_item with merge_into set to its id. Otherwise save_item as new.
   Always pass shared_by, how and inbox_id so the colleague is credited and the inbox item is closed.
3. score_hotness for each saved story. Report the score with its reasons, never the score alone.
4. collect_open_data, then check_report_index: if a new agency report title appears that nobody has
   uploaded, say which one so a colleague can upload it (the agent never downloads it).
5. Finish with what is new and hot, who shared what, and anything unverified (a tip with no source).
