---
name: check-terms
description: Decide how a new source may be collected before following it. Reads robots.txt and the terms; picks 🟢 automatic or 🟠 upload-only, with the clause it rests on.
---
Use when someone asks to follow, track or add a source, or pastes a link to a site the team does not follow.

1. Call `follow_source` with the link or the name as the person wrote it (and a cadence if they gave one).
   The Pi tool fetches robots.txt, the page and its terms page; the decision comes back with its reason.
2. Decision rules (applied by the tool; explain them, never override them to "make it work"):
   - UK public bodies under the Open Government Licence: 🟢 automatic.
   - robots.txt disallows the page, or the terms forbid automated access, scraping, text and data
     mining or AI use: 🟠 upload-only. Quote the clause.
   - Agency or data-vendor research (Knight Frank, Savills, CBRE, JLL, Cushman, BNP, Colliers, CoStar,
     EGi): 🟠 until a person reads the terms. Knight Frank's terms bar AI-platform use outright.
   - Terms that cannot be read: 🟠 until someone checks. Unknown is never treated as allowed.
   - A public RSS feed or a page whose terms raise no objection: 🟢, keeping headlines and links only.
3. Tell the person what happens next: 🟢 "collected daily from tomorrow"; 🟠 "the team will be
   reminded to upload each new issue". It is shared with the whole team and logged with their name.
