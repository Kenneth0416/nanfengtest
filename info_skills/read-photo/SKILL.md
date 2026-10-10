---
name: read-photo
description: Read one of our own deals from a photo, a screenshot or a short PDF (lease front page, heads of terms, a WhatsApp message) with the vision model and file it as an internal record.
---
1. Only for internal material a colleague gave you (a photo, screenshot, lease or heads-of-terms PDF,
   or a sentence). It is never market data: nothing here goes through check-figures or into observations.
2. `read_photo(path, hint)`: the vision model reads the image (a PDF's first pages are rendered) and
   returns the deal fields it can see, its confidence and a note on what the document is. Pass the
   colleague's words as `hint` when they said anything.
3. `save_internal_deal(fields, how, original, confidence)`: files it. The same property and floor already
   on record is merged (empty fields filled, nothing overwritten, the colleague credited); otherwise a new
   record, a draft when fields are missing. Keep `original` = the path so the photo stays beside the record.
4. Say what was read, what was merged or created, which fields are still missing, and that the recorder
   confirms it on Sources › Internal data. If the tool reports an external comparison, repeat it.
5. A spreadsheet of our deals: `read_table(path)` then `deals_from_table(path, sheet)`, one record per row.
