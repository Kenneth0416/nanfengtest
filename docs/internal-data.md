# Internal data: a third kind of source

Spec for the PoC, written before the code. Kenneth's ask: separate the company's own deal data from
external data; the pieces arrive in many formats (PDF, photo, a sentence to the Copilot) and must be
tidied into one place. The design follows the coordinator's proposal and prototype v12.

## 1. Three layers, by where the data comes from, not by file format

| Layer | What | Who sees it | Shown as |
|---|---|---|---|
| Open data, collected automatically | open data the licence allows the agent to fetch (Bank of England, news RSS, open-data tables) | the team | green dot |
| Uploaded external reports | agency research a colleague uploads under the team's own access (Knight Frank, Savills…) | the team | orange dot |
| Internal | the company's own lettings, leases and valuations | the team, inside the company only | blue dot, chip "Internal only" or "Quotable externally" |

Internal records never mix with market data: they live in their own table, carry their own
provenance, and are listed under their own heading wherever they appear.

## 2. One entry, any format

PDF (signed lease, heads of terms), photo (lease front page, WhatsApp screenshot), Excel/CSV export,
or one sentence to the Copilot ("We just let 1 Triton Square 4th floor at £95, 10 year term"). Every
route produces the same deal record:

| Route | Who reads it | How |
|---|---|---|
| Tell Copilot | `record_deal` tool (rules parser; the Copilot can pass fields it understood) | property, floor, size, tenant, rent, term, rent-free, date, counterparty from the sentence |
| Photo | `read-photo` playbook, `read_photo` tool | the image goes to the vision model (MiMo) with a deal prompt; the same fields come back |
| PDF | `read-photo` playbook on the first pages, rendered as images | same as photo |
| Excel / CSV | `read-table` playbook, `deals_from_table` tool | one record per row, columns mapped by name |

The Sources page runs the same Python intake without the Pi agent (photo, PDF and table are read by
the vision model directly), so recording works when Pi is not running; the Copilot route goes through Pi.

## 3. The deal record

| Field | Note |
|---|---|
| property, floor_area, tenant, rent, term, rent_free, date, counterparty | the eight the prototype shows; any may be empty |
| submarket | from the property text (taxonomy aliases and postcodes) |
| confidentiality | `internal` (default) or `quotable` |
| recorded_by | list of [person, format, date]: every contribution is credited |
| originals | files kept beside the record (photo, PDF), shown as "View originals (n)" |
| missing | the fields still empty |
| status | `draft` while fields are missing or nobody has confirmed; `confirmed` once the recorder confirms |
| confidence | `high` when every field was printed or said explicitly, `medium` when the parser inferred one, `low` when the vision model reported low confidence |
| ext | the external comparison, when an agency report carries the same deal |

Merging: a new piece is matched on property (normalised: punctuation, "the", postcodes dropped) plus
floor when both give one; if both carry a date or a tenant and they disagree, it is a different deal.
A match fills empty fields only, never overwrites, and adds the contributor to `recorded_by`.

## 4. Inside and outside, never mixed

- Team brief (markdown, Word/PDF and deck): "Our deals (Internal, quotable only)" then "Market deals (Uploaded
  agency reports)", each item footnoted. Only confirmed `quotable` records are listed, with a line "n internal-only
  records not included", because the same brief may go to the investment committee. Draft records are not listed.
- External comparison: when a market deal in the library names the same building with a rent, the
  record shows "Also reported externally: <source> shows £70.00 psf against our £72.50; our record is
  kept, difference noted for the brief", and the brief repeats it in italics.
- Copilot: answers cite internal figures with "Internal only" and never present them as market evidence.

## 5. A person stays in the loop

Every new or merged record goes into the same "Needs a person" queue on Sources as flagged figures.
The recorder confirms their own record by default (anyone can, and who did it shows in team activity).
Originals stay beside the record.

## 6. Out of scope for the PoC

OCR without a vision model (a photo recorded offline stays a draft with the image attached);
access control per person (the whole team sees internal records); valuations beyond free text.
