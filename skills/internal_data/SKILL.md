---
name: internal_data
description: Internal data, the company's own lettings, leases and valuations, kept apart from market data. Records a deal from one sentence ("we just let 1 Triton Square 4th floor at £95, 10 year term"), lists our deals, confirms a record, marks it internal-only or quotable.
---
When someone says the company (we, our, us) let, signed, leased, completed, exchanged or agreed a
deal, call `record_deal` with their sentence (and any fields you understood). It is never a tip:
`share_tip` is for market news heard from outside. One sentence may be only part of the story: the
record is saved as a draft with its missing fields listed, and a later photo, PDF or sentence about
the same property and floor is merged into it, not added as a second record.

- Say what was recorded or merged, which fields are still missing, and that the recorder confirms it
  on the Sources page (Internal data). If the tool reports an external comparison, repeat it.
- `list_our_deals` answers "what have we let", "our deals in the City", "which records are drafts".
- `confirm_deal` when the person who recorded it says it is right; `set_deal_confidentiality` when
  someone says a record may be quoted externally (quotable) or must stay internal.
- Internal records are confidential: in any answer label them Internal only (or quotable) in words, never
  present them as market evidence, and never include an internal-only record in an IC paper.
