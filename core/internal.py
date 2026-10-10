"""Internal data (🔵): the company's own lettings, leases and valuations, kept apart from market data.

One record shape whatever the route (a sentence to the Copilot, a photo, a PDF, a spreadsheet row):
  property, floor_area, tenant, rent, term, rent_free, date, counterparty   the eight fields people see
  submarket, confidentiality (internal | quotable), recorded_by [[who, how, when]], originals [paths],
  missing [fields], status (draft | confirmed), confidence, ext (external comparison)

Pieces arrive separately and are merged by property (+ floor): empty fields are filled, nothing is
overwritten, every contributor is credited. See docs/internal-data.md.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from . import taxonomy as tx

FIELDS = ["property", "floor_area", "tenant", "rent", "term", "rent_free", "date", "counterparty"]
LABELS = {"property": "Property", "floor_area": "Floor / area", "tenant": "Tenant", "rent": "Rent", "term": "Term",
          "rent_free": "Rent-free", "date": "Date", "counterparty": "Counterparty"}
LEVELS = {"internal": "🔵 Internal only", "quotable": "🔵 Quotable externally"}
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


# ----------------------------------------------------------------------------- parsing a sentence
_FLOOR = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+floor\b|\b(ground|lower ground|mezzanine|penthouse)\s+floor\b|"
                    r"\bfloors?\s+(\d{1,2}(?:\s*(?:-|to|&|and)\s*\d{1,2})?)\b|\b(part\s+\d{1,2}(?:st|nd|rd|th)\s+floor)\b", re.I)
_AREA = re.compile(r"\b([\d,]{3,9})\s*(?:sq\.?\s?ft|sqft|square feet|ft²)\b", re.I)
_RENT = re.compile(r"£\s?(\d{1,3}(?:\.\d{1,2})?)\s*(?:psf|per sq\.? ?ft|/sq ?ft|a sq ft|per foot)?(?!\s?(?:m\b|bn\b|k\b))", re.I)
_TERM = re.compile(r"\b(\d{1,2})[- ]?(?:year|yr)s?\b(?:\s+(?:term|lease))?|\bterm\s+(?:of\s+)?(\d{1,2})\b", re.I)
_FREE = re.compile(r"\b(\d{1,2}(?:\.\d)?)\s*months?(?:'|’)?\s*(?:rent[- ]free|free)|\brent[- ]free\s*(?:of|period(?:\s+of)?|:)?\s*(\d{1,2}(?:\.\d)?)\s*months?", re.I)
_NAME = r"([A-Z][\w&'.\-()]{1,40}(?:\s+[\w&'.\-()]{1,40}){0,4}?)"
_STOP = r"(?=\s*(?:,|\.|;|\bat\b|\bfor\b|\bon\b|\bwith\b|\bin\b|£|\d|$))"
_TENANT = re.compile(r"\b(?:let|leased|signed|pre-let|prelet)\b(?:\s+to|[^.;:]{0,80}?\bto)\s+" + _NAME + _STOP + "|"
                     r"\btenant:?\s+" + _NAME + _STOP + "|"
                     r"\b([A-Z][\w&'.\-]{1,30}(?:\s+[A-Z&][\w&'.\-]{1,30}){0,3})\s+(?:took|takes|has taken|signed for|leased|agreed)\b")
_CPTY = re.compile(r"\b(landlord|owner|vendor|purchaser|buyer|agent)[:\s]+" + _NAME + _STOP, re.I)
_DATE = re.compile(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s+(\d{4}))?\b|"
                   r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?\b|"
                   r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})/(\d{1,2})/(\d{4})\b", re.I)
_PROP = re.compile(r"\b(\d{1,4}[A-Za-z]?(?:-\d{1,4})?\s+[A-Z][\w'.\-]+(?:\s+(?:[A-Z][\w'.\-]+|of|&))*?\s+"
                   r"(?:Street|St|Square|Sq|Road|Rd|Lane|Place|Pl|Court|Wharf|Gate|Bishopsgate|Row|Walk|Yard|Circus|"
                   r"Gardens|Avenue|Ave|Hill|Quay|Fields|Crescent|Terrace|Bridge|Embankment|Broadgate|Churchill Place))\b|"
                   r"\b((?:The\s+)?[A-Z][\w'.\-]+\s+(?:Building|House|Tower|Centre|Center|Plaza|Exchange|Hall|Court|Square|Wharf|Place|Yard)"
                   r"(?:,\s*[A-Z][\w'.\- ]+)?)\b")
_POSTCODE = re.compile(r"\b(?:EC|WC|SW|SE|NW|N|E|W)\d[A-Z\d]?(?:\s?\d[A-Z]{2})?\b")


def _title(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" ,.;")


def parse_date(text: str, today: date | None = None) -> str:
    """'2 Oct 2026', 'Oct 2, 2026', '2026-10-02', '2/10/2026', 'today', 'yesterday', 'just/this week' -> ISO date."""
    today = today or date.today()
    low = text.lower()
    if re.search(r"\b(today|this morning|this afternoon)\b", low):
        return today.isoformat()
    if "yesterday" in low:
        return (today - timedelta(days=1)).isoformat()
    m = _DATE.search(text)
    if not m:
        return ""
    g = m.groups()
    try:
        if g[0]:
            return date(int(g[2] or today.year), MONTHS.index(g[1].lower()[:3]) + 1, int(g[0])).isoformat()
        if g[3]:
            return date(int(g[5] or today.year), MONTHS.index(g[3].lower()[:3]) + 1, int(g[4])).isoformat()
        if g[6]:
            return date(int(g[6]), int(g[7]), int(g[8])).isoformat()
        return date(int(g[11]), int(g[10]), int(g[9])).isoformat()
    except ValueError:
        return ""


def parse_deal_text(text: str, today: date | None = None) -> dict:
    """Rule-based reading of one sentence about one of our deals. Fields it cannot find stay empty."""
    t = " " + re.sub(r"\s+", " ", text).strip() + " "
    d: dict = {k: "" for k in FIELDS}
    if (m := _FLOOR.search(t)):
        if m.group(1):
            n = int(m.group(1))
            d["floor_area"] = f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')} floor"
        elif m.group(2):
            d["floor_area"] = f"{m.group(2).lower()} floor"
        elif m.group(3):
            d["floor_area"] = f"floors {m.group(3)}"
        else:
            d["floor_area"] = m.group(4).lower()
    if (m := _AREA.search(t)):
        d["floor_area"] = (d["floor_area"] + ", " if d["floor_area"] else "") + f"{m.group(1)} sq ft"
    if (m := _RENT.search(t)):
        d["rent"] = f"£{float(m.group(1)):.2f} psf"
    if (m := _TERM.search(t)):
        d["term"] = f"{m.group(1) or m.group(2)} years"
    if (m := _FREE.search(t)):
        d["rent_free"] = f"{m.group(1) or m.group(2)} months"
    if (m := _TENANT.search(t)):
        d["tenant"] = _title(m.group(1) or m.group(2) or m.group(3))
    if (m := _CPTY.search(t)):
        d["counterparty"] = f"{m.group(1).capitalize()}: {_title(m.group(2))}".replace("From: ", "")
    d["date"] = parse_date(t, today)
    if (m := _PROP.search(t)):
        d["property"] = _title(m.group(1) or m.group(2))
    elif (m := re.search(r"\b(\d{1,4}\s+[A-Z][\w'.\-]+(?:\s+[A-Z][\w'.\-]+)?)\b", t)):
        d["property"] = _title(m.group(1))
    if d["tenant"] and d["property"] and d["tenant"].lower() in d["property"].lower():
        d["tenant"] = ""
    d["submarket"] = submarket_of(t)
    return d


def submarket_of(text: str) -> str:
    """The team's submarket for a property, from aliases ("Bishopsgate", "Canary Wharf") and postcodes."""
    hits = [m for m in tx.find_markets(text) if m not in tx.TOP_MARKETS]
    if hits:
        return hits[0]
    low = text.lower()
    for word, mk in (("bishopsgate", "City Core"), ("liverpool street", "City Core"), ("broadgate", "City Core"),
                     ("cheapside", "City Core"), ("fenchurch", "City Core"), ("leadenhall", "City Core"), ("gresham", "City Core"), ("triton square", "King's Cross/Euston"), ("regent's place", "King's Cross/Euston"),
                     ("canada square", "Canary Wharf"), ("cabot square", "Canary Wharf"), ("churchill place", "Canary Wharf"),
                     ("oxford street", "West End Core"), ("berkeley square", "West End Core"), ("hanover square", "West End Core"),
                     ("howland street", "Fitzrovia"), ("kingsway", "Midtown"), ("chancery lane", "Midtown")):
        if word in low:
            return mk
    top = [m for m in tx.find_markets(text) if m in tx.TOP_MARKETS and m != "London"]
    return top[0] if top else ""


# ----------------------------------------------------------------------------- the record
def norm_property(s: str) -> str:
    s = _POSTCODE.sub(" ", s or "").lower()
    s = re.sub(r"\b(the|at|building)\b", " ", s)
    s = re.sub(r"\b(street|st)\b", "st", s)
    s = re.sub(r"\b(square|sq)\b", "sq", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_ORDINALS = {w: str(i) for i, w in enumerate(["ground", "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
                                              "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth",
                                              "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth"])}


def norm_floor(s: str) -> str:
    s = re.sub(r"\b(" + "|".join(_ORDINALS) + r")\b", lambda m: _ORDINALS[m.group(1).lower()] if m.group(1).lower() != "ground" else "ground", s or "", flags=re.I)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*floor|\bfloors?\s*(\d{1,2})|\b(ground|lower ground|mezzanine|penthouse)", s or "", re.I)
    return (m.group(1) or m.group(2) or m.group(3)).lower() if m else ""


def same_deal(a: dict, b: dict) -> bool:
    """Same property (+ floor when both say one); a different date or tenant on both sides means a different deal."""
    if not a.get("property") or not b.get("property"):
        return False
    pa, pb = norm_property(a["property"]), norm_property(b["property"])
    if not (pa == pb or pa in pb or pb in pa):
        return False
    fa, fb = norm_floor(a.get("floor_area", "")), norm_floor(b.get("floor_area", ""))
    if fa and fb and fa != fb:
        return False
    if a.get("date") and b.get("date") and a["date"] != b["date"]:
        return False
    ta, tb = (a.get("tenant") or "").lower(), (b.get("tenant") or "").lower()
    if ta and tb and ta not in tb and tb not in ta and "confidential" not in ta + tb:
        return False
    return True


def finish(d: dict) -> dict:
    d["missing"] = [k for k in FIELDS if not d.get(k)]
    d.setdefault("confidentiality", "internal")
    d.setdefault("recorded_by", [])
    d.setdefault("originals", [])
    d.setdefault("confidence", "high")
    d.setdefault("ext", None)
    if d.get("status") != "confirmed":
        d["status"] = "draft"
    return d


def record(store, fields: dict, who: str, how: str, original: str | Path | None = None, confidence: str = "high",
           when: str | None = None) -> dict:
    """File one piece of information about one of our deals: merged into the record it belongs to, or new.
    Returns {"deal": record, "merged": bool, "filled": [fields filled on a merge]}."""
    when = when or date.today().isoformat()
    fields = {k: (v or "").strip() if isinstance(v, str) else (v or "") for k, v in fields.items() if k in FIELDS + ["submarket"]}
    if not fields.get("submarket") and fields.get("property"):
        fields["submarket"] = submarket_of(fields["property"])
    existing = next((x for x in store.internal_deals() if same_deal(x, fields)), None)
    if existing:
        filled = [k for k in FIELDS + ["submarket"] if fields.get(k) and not existing.get(k)]
        for k in filled:
            existing[k] = fields[k]
        existing["recorded_by"].append([who, how, when])
        if original:
            existing["originals"].append(str(original))
        if confidence == "low":
            existing["confidence"] = "low"
        existing["status"] = "draft" if existing.get("status") != "confirmed" or filled else existing["status"]
        if filled and existing.get("status") == "confirmed":
            existing["status"] = "draft"  # new information: the recorder confirms again
        d = finish(existing)
        d["ext"] = compare_external(store, d)
        store.save_internal_deal(d)
        return {"deal": d, "merged": True, "filled": filled}
    d = finish({**{k: "" for k in FIELDS}, **fields, "recorded_by": [[who, how, when]],
                "originals": [str(original)] if original else [], "confidence": confidence, "status": "draft"})
    d["ext"] = compare_external(store, d)
    store.save_internal_deal(d)
    return {"deal": d, "merged": False, "filled": []}


def compare_external(store, d: dict) -> dict | None:
    """An agency report in the library that names the same building with a rent: shown beside the record,
    never used to change it."""
    if not d.get("property"):
        return None
    key = norm_property(d["property"])
    tokens = [t for t in key.split() if len(t) > 2]
    for r in store.q("SELECT d.*, s.title FROM deals d LEFT JOIN sources s USING (source_id) WHERE d.rent_psf IS NOT NULL "
                     "ORDER BY d.period DESC"):
        b = norm_property(r["building"] or "")
        if key and (key in b or b in key or (tokens and all(t in b for t in tokens))):
            ours = _rent_value(d.get("rent", ""))
            theirs = float(r["rent_psf"])
            return {"source": r.get("title") or r["source_id"], "rent": f"£{theirs:.2f} psf", "period": r["period"],
                    "differs": ours is not None and abs(ours - theirs) > 0.05,
                    "text": (f"Also reported externally: {r.get('title') or r['source_id']} shows £{theirs:.2f} psf against our "
                             f"{d.get('rent') or 'rent not recorded'}; our record is kept, difference noted for the brief."
                             if ours is not None and abs(ours - theirs) > 0.05 else
                             f"Also reported externally: {r.get('title') or r['source_id']} shows £{theirs:.2f} psf, the same as ours.")}
    return None


def _rent_value(s: str) -> float | None:
    m = re.search(r"(\d{1,3}(?:\.\d{1,2})?)", s or "")
    return float(m.group(1)) if m else None


def confirm(store, deal_id: int, who: str) -> dict:
    d = store.internal_deal(deal_id)
    d["status"] = "confirmed"
    d["confirmed_by"] = who
    store.save_internal_deal(d)
    return d


def set_confidentiality(store, deal_id: int, level: str, who: str) -> dict:
    if level not in LEVELS:
        raise ValueError(f"level is one of {', '.join(LEVELS)}")
    d = store.internal_deal(deal_id)
    d["confidentiality"] = level
    d.setdefault("recorded_by", []).append([who, f"marked {level}", date.today().isoformat()])
    store.save_internal_deal(d)
    return d


def one_line(d: dict) -> str:
    bits = [d.get("tenant") or "Tenant not recorded"]
    if d.get("rent"):
        bits.append(d["rent"])
    if d.get("term"):
        bits.append(d["term"])
    if d.get("rent_free"):
        bits.append(f"{d['rent_free']} rent-free")
    if d.get("floor_area"):
        bits.append(d["floor_area"])
    s = f"{d['property']}. " + ", ".join(bits)
    if d.get("date"):
        s += f" ({d['date']})"
    return s


def market_deals(store, limit: int = 5) -> list[dict]:
    """The latest period's leasing deals from agency reports (🟠), for the 'Market deals' list beside ours."""
    rows = store.q("SELECT d.*, s.title, s.url FROM deals d LEFT JOIN sources s USING (source_id) "
                   "WHERE d.deal_type IN ('letting', 'pre-let', 'sublease') ORDER BY d.period DESC, d.size_sqft DESC")
    if not rows:
        return []
    latest = rows[0]["period"]
    out = []
    for r in [x for x in rows if x["period"] == latest][:limit]:
        text = f"{r['party']} took {int(r['size_sqft'] or 0):,} sq ft at {r['building']}"
        if r.get("rent_psf"):
            text += f" at £{r['rent_psf']:.2f} psf"
        out.append({"property": r["building"], "tenant": r["party"], "rent": f"£{r['rent_psf']:.2f} psf" if r.get("rent_psf") else "",
                    "size": f"{int(r['size_sqft'] or 0):,} sq ft", "period": r["period"], "submarket": r["submarket"],
                    "source_id": r["source_id"], "title": r.get("title") or r["source_id"], "url": r.get("url") or "", "text": text})
    return out


def for_brief(store, fmt: str) -> dict:
    """Confirmed records for the brief; the IC paper gets only quotable ones and says how many were left out."""
    done = [d for d in store.internal_deals() if d.get("status") == "confirmed"]
    ours = [d for d in done if fmt != "ic" or d.get("confidentiality") == "quotable"]
    return {"ours": ours, "filtered": len(done) - len(ours)}


# ----------------------------------------------------------------------------- photo / PDF / table
DEAL_PROMPT = (
    "This image is an internal document about one of our own office deals in London: a lease front page, heads of "
    "terms, a letting report, or a screenshot of a message. Read it and return JSON "
    "{\"deal\": {\"property\": \"\", \"floor_area\": \"\", \"tenant\": \"\", \"rent\": \"\", \"term\": \"\", "
    "\"rent_free\": \"\", \"date\": \"\", \"counterparty\": \"\"}, \"confidence\": \"high|medium|low\", "
    "\"notes\": \"\"}. Rules: copy what is printed (rent as '£72.50 psf', term as '10 years', rent-free as "
    "'24 months', area as '18,400 sq ft', date as YYYY-MM-DD); leave a field empty when the image does not show it; "
    "never guess. Say in notes what the document is and anything unclear.")

TABLE_COLUMNS = {"property": ("property", "building", "address", "asset"), "floor_area": ("floor", "area", "unit", "sq ft", "size"),
                 "tenant": ("tenant", "occupier", "lessee"), "rent": ("rent", "psf", "headline rent"),
                 "term": ("term", "lease term", "years"), "rent_free": ("rent free", "rent-free", "incentive"),
                 "date": ("date", "completion", "signed"), "counterparty": ("counterparty", "landlord", "owner", "agent")}


def deal_from_images(llm, images: list[bytes], hint: str = "") -> dict:
    """The vision model reads a photo, screenshot or PDF page as one deal; {} when no model can see."""
    if not getattr(llm, "available", False) or not images:
        return {}
    prompt = DEAL_PROMPT + (f"\nContext from the person: {hint}" if hint else "")
    if hasattr(llm, "read_json_images"):
        out = llm.read_json_images(prompt, images)
    else:
        out = llm.complete_json_images(prompt, images)
    if isinstance(out, list):  # a model that answered with the figures list shape
        out = {}
    if not isinstance(out, dict):
        return {}
    deal = out.get("deal") if isinstance(out.get("deal"), dict) else {k: out.get(k, "") for k in FIELDS}
    fields = {k: str(deal.get(k) or "").strip() for k in FIELDS}
    if fields.get("date"):
        fields["date"] = parse_date(fields["date"]) or fields["date"]
    return {"fields": fields, "confidence": out.get("confidence") or "medium", "notes": out.get("notes", "")}


def images_of(path: str | Path) -> list[bytes]:
    """A photo as it is (PNG/JPEG bytes), or the first pages of a PDF rendered to PNG."""
    from . import documents
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        pages = documents.pdf_pages(p)
        return [documents.page_png(p, n, 1800) for n in range(1, min(len(pages), 3) + 1)]
    return [p.read_bytes()]


def deals_from_rows(rows: list[dict]) -> list[dict]:
    """Map spreadsheet rows to deal fields by column name (case-insensitive, first match wins)."""
    out = []
    for r in rows:
        low = {str(k).strip().lower(): ("" if v is None or str(v).strip().lower() in ("nan", "none", "nat") else str(v))
               for k, v in r.items()}
        d = {}
        for field, names in TABLE_COLUMNS.items():
            col = next((c for c in low if any(n in c for n in names)), None)
            if col:
                d[field] = low[col].strip()
        if d.get("date"):
            d["date"] = parse_date(d["date"]) or d["date"]
        if d.get("rent") and not d["rent"].startswith("£"):
            try:
                d["rent"] = f"£{float(d['rent'].replace(',', '')):.2f} psf"
            except ValueError:
                pass
        if d.get("property"):
            out.append(d)
    return out


def load_json(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text())
