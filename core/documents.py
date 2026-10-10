"""Extracts market figures from agency research PDFs and checks them against
what is already stored, so an analyst only reviews the differences.

With an LLM key, each data page is rendered to an image and read by a vision model
(tables, dashboards and charts included). Every figure then goes through three checks:
  1. evidence: found in that page's text layer, or else marked "read from the image" and
     left for a person to confirm against a screenshot of the page;
  2. range: outside a plausible range for its metric -> flagged;
  3. sources: compared with what other publishers reported for the same period.
Nothing is saved until a person confirms. Without a key, a rule-based text extractor is used.
"""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
import re
from pathlib import Path

from . import analytics as an
from . import taxonomy as tx

PUBLISHERS = ["Knight Frank", "CBRE", "JLL", "Savills", "Cushman & Wakefield", "Colliers", "BNP Paribas",
              "Avison Young", "Carter Jonas", "Gerald Eve", "Newmark", "Lambert Smith Hampton"]
_NUM = r"£?\s?([\d,]+(?:\.\d+)?)\s?(%|m|bn|psf|per sq ft|/sq ft|months)?"


RANGES = {  # plausible values for central London offices; outside these a figure is flagged
    "prime_rent_psf": (15, 300), "vacancy_pct": (1.5, 30), "new_refurb_vacancy_pct": (0, 30),  # London has never been below ~2% vacant
    "take_up_msqft": (0, 25), "availability_msqft": (0, 60), "active_requirements_msqft": (0, 30),
    "under_construction_msqft": (0, 40), "under_construction_spec_msqft": (0, 30),
    "investment_gbp_bn": (0, 40), "prime_yield_pct": (2, 12), "rent_free_months": (0, 48),
    "prelet_share_under_construction_pct": (0, 100),
}
DATA_WORDS = re.compile(r"take-?up|vacancy|availability|prime rent|yield|rent[- ]free|under construction|"
                        r"investment|pipeline|requirements|sq ft", re.I)
LONG_SIDE_PX = 2000      # vision models downscale beyond ~2,500 px; this keeps small print legible
PAGES_PER_CALL = 4
VISION_PARALLEL = 4      # page batches read at the same time
MAX_PAGES = 24


def pdf_pages(path: str | Path) -> list[str]:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def pdf_text(path: str | Path) -> str:
    return "\n".join(pdf_pages(path))


def page_png(path: str | Path, page_no: int, long_side: int = LONG_SIDE_PX) -> bytes:
    """Render one page (1-based) to PNG, scaled so its long side is about long_side pixels."""
    import io

    import pdfplumber
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[page_no - 1]
        img = page.to_image(resolution=72 * long_side / max(page.width, page.height)).original
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def data_pages(pages: list[str]) -> list[int]:
    """Pages worth reading: those that mention a market measure, plus pages with almost no text
    layer (dashboards and charts drawn as images). Disclaimers and contact pages are skipped."""
    keep = [i + 1 for i, t in enumerate(pages) if DATA_WORDS.search(t) or len(t.strip()) < 200]
    return keep[:MAX_PAGES]


def detect_period(text: str) -> str | None:
    m = re.search(r"\bQ([1-4])\s?(20\d\d)\b", text) or re.search(r"\b(20\d\d)\s?Q([1-4])\b", text)
    if m:
        a, b = m.groups()
        return f"{b}Q{a}" if len(a) == 1 else f"{a}Q{b}"
    m = re.search(r"\bH([12])\s?(20\d\d)\b", text)
    return f"{m.group(2)}Q{2 if m.group(1) == '1' else 4}" if m else None


_PUBLISHER_HINTS = {"bnp": "BNP Paribas", "bnppre": "BNP Paribas", "knightfrank": "Knight Frank", "kf": "Knight Frank",
                    "cbre": "CBRE", "jll": "JLL", "savills": "Savills", "cushman": "Cushman & Wakefield",
                    "cw": "Cushman & Wakefield", "colliers": "Colliers", "avisonyoung": "Avison Young",
                    "carterjonas": "Carter Jonas", "geraldeve": "Gerald Eve", "newmark": "Newmark", "lsh": "Lambert Smith Hampton"}


def detect_publisher(text: str, filename: str = "") -> str:
    """The publisher from the text layer, or from the file name when the name is only in the cover image
    (BNPPRECentralLondonOfficeMarketUpdateQ32025.pdf)."""
    head = text[:3000].lower()
    for p in PUBLISHERS:
        if p.lower() in head:
            return p
    name = re.sub(r"[^a-z]", " ", Path(filename).stem.lower()) if filename else ""
    compact = name.replace(" ", "")
    for hint, p in _PUBLISHER_HINTS.items():
        if re.search(rf"\b{hint}\b", name) or compact.startswith(hint):
            return p
    return "Unknown publisher"


def _value(metric: str, raw: str, suffix: str | None) -> float | None:
    v = float(raw.replace(",", ""))
    unit = tx.METRICS[metric]["unit"]
    if unit == "m sq ft" and v > 1000:      # given in sq ft
        v = v / 1_000_000
    if unit == "£bn" and suffix == "m":
        v = v / 1000
    return round(v, 3)


def extract_rules(text: str) -> list[dict]:
    """Line-based extractor for 'Metric: value' and 'Market metric value' lines."""
    out, current = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        markets = tx.find_markets(line, use_postcodes=False)
        metrics = tx.find_metrics(line)
        nums = re.findall(_NUM, line)
        if markets and not metrics and len(line) < 60:
            current = line.rstrip(":")         # a section heading
            continue
        if not metrics or not nums:
            continue
        market_text = None
        if markets:
            for alias_line in [line]:
                market_text = re.split(r"[:\-–]| prime| vacancy| take| rent", alias_line, maxsplit=1, flags=re.I)[0]
        market_text = market_text or current
        if not market_text:
            continue
        metric = metrics[0]
        # take the first number after the metric word
        after = line.lower().split(tx.METRICS[metric]["aliases"][0], 1)[-1] if tx.METRICS[metric]["aliases"][0] in line.lower() else line
        m = re.search(_NUM, after) or re.search(_NUM, line)
        if not m:
            continue
        out.append({"market_text": market_text.strip(), "metric": metric,
                    "value": _value(metric, m.group(1), m.group(2)), "line": line})
    return out


VISION_PROMPT = (
    "These are pages {pages} of a London office market research report. Each image is followed by that "
    "page's text layer, which may be empty for charts. Extract every London office market figure for the "
    "report's own period. Return a JSON list of objects with keys:\n"
    "  market_text: the market name exactly as printed\n"
    "  metric: one of " + ", ".join(tx.METRICS) + "\n"
    "  value: a number in the metric's unit (" + "; ".join(f"{k}={v['unit']}" for k, v in tx.METRICS.items()) + ")\n"
    "  page: the page number\n"
    "  where: the table, column, chart or paragraph it is in\n"
    "  label_status: 'explicit' if the figure is labelled on the page, 'inferred' if you inferred what it is "
    "(for example an unlabelled column)\n"
    "  evidence: the exact words or numbers printed next to it\n"
    "Do not compute or estimate figures that are not printed. Return [] if there are none."
)


def extract_vision(llm, path: str | Path, pages: list[str], wanted: list[int] | None = None) -> list[dict]:
    """Render the data pages (or the pages asked for) to images and have a vision model read them,
    a few pages per call."""
    wanted = [n for n in (wanted or data_pages(pages)) if 0 < n <= len(pages)][:MAX_PAGES]
    per_call = getattr(llm, "pages_per_call", PAGES_PER_CALL)
    long_side = getattr(llm, "long_side", LONG_SIDE_PX)
    batches = [wanted[i:i + per_call] for i in range(0, len(wanted), per_call)]

    # Pages are rendered here, one at a time: the PDF renderer is not thread-safe. Only the model calls
    # run in parallel; a 13-page report is 7 calls of 45-170 s each, which in parallel fit the agent's time limit.
    jobs = []
    for batch in batches:
        images = [page_png(path, n, long_side) for n in batch]
        text = "\n\n".join(f"--- Page {n} text layer ---\n{pages[n - 1][:6000] or '(none)'}" for n in batch)
        jobs.append((VISION_PROMPT.format(pages=", ".join(map(str, batch))) + "\n\n" + text, images))
    with ThreadPoolExecutor(max_workers=max(1, getattr(llm, "parallel", VISION_PARALLEL))) as pool:
        results = list(pool.map(lambda j: llm.complete_json_images(*j), jobs))
    out: list[dict] = []
    for batch, rows in zip(batches, results):
        for r in rows or []:
            if isinstance(r, dict) and r.get("metric") in tx.METRICS and r.get("market_text"):
                try:
                    r["value"] = float(r["value"])
                    r["page"] = int(r.get("page") or batch[0])
                except (TypeError, ValueError):
                    continue
                r["line"] = r.get("evidence", "")
                out.append(r)
    return out


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def found_in_text(value: float, metric: str, text: str) -> bool:
    """The figure (or the same figure in sq ft / £m) is printed in the page's text layer."""
    unit = tx.METRICS[metric]["unit"]
    scales = [1.0] + ([1e6, 1e3] if unit == "m sq ft" else [1e3] if unit == "£bn" else [])
    return any(abs(n - value * k) <= max(1e-6, abs(value * k) * 1e-4) for n in _numbers(text) for k in scales)


def check(r: dict, pages: list[str]) -> tuple[str, list[str]]:
    """Evidence and range checks. Returns (status, flags); status is verified, image or not_found."""
    flags = []
    page_text = pages[r["page"] - 1] if r.get("page") and 0 < r["page"] <= len(pages) else "\n".join(pages)
    if found_in_text(r["value"], r["metric"], page_text):
        status = "verified"
    elif len(_numbers(page_text)) < 3:  # no usable text layer: a chart, dashboard or scan
        status = "image"
        flags.append(f"Read from the page image only (p.{r.get('page', '?')}); check against the screenshot.")
    else:
        status = "not_found"
        flags.append(f"Not found in the text of p.{r.get('page', '?')}; it may come from a chart. Check the screenshot.")
    if r.get("label_status") == "inferred":
        flags.append(f"Label inferred by the model ({r.get('where', 'unlabelled')}); confirm what it measures.")
    lo, hi = RANGES.get(r["metric"], (float("-inf"), float("inf")))
    if not lo <= r["value"] <= hi:
        flags.append(f"Outside the plausible range {lo}-{hi} {tx.METRICS[r['metric']]['unit']}.")
        status = "implausible"  # whatever the page says, this is not the figure it is labelled as
    return status, flags


_GRADE_A = re.compile(r"\bgrade[ -]?a\b|\bnew (and|&|/) ?refurb|\bprime (space )?vacan|\bnew space\b", re.I)


def grade_a_metric(r: dict) -> str:
    """'Grade A availability 2.8%' read as vacancy_pct is the new/refurbished rate, a different series."""
    if r.get("metric") == "vacancy_pct" and _GRADE_A.search(
            " ".join(str(r.get(k, "")) for k in ("market_text", "where", "evidence", "line"))):
        return "new_refurb_vacancy_pct"
    return r.get("metric", "")


def extract_llm(llm, text: str) -> list[dict]:
    prompt = (
        "Extract London office market figures from this research report text.\n"
        "Return a JSON list of objects with keys market_text (the market name exactly as written), "
        "metric (one of: " + ", ".join(tx.METRICS) + "), value (number in the metric's unit: "
        + "; ".join(f"{k}={v['unit']}" for k, v in tx.METRICS.items())
        + "), line (the sentence it came from). Only include figures for the report's own period.\n\n"
        + text[:30000])
    out = llm.complete_json(prompt)
    return [o for o in (out or []) if isinstance(o, dict) and o.get("metric") in tx.METRICS]


def file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identify(path: str | Path) -> dict:
    """Publisher, period and file hash from the text layer: cheap, so a duplicate is caught before any model call."""
    text = "\n".join(pdf_pages(path))
    return {"publisher": detect_publisher(text, str(path)), "period": detect_period(text), "file_hash": file_hash(path)}


def duplicate_of(store, path: str | Path) -> dict | None:
    """The earlier upload of the same file, or of the same publisher's report for the same quarter."""
    ident = identify(path)
    return store.find_upload(ident["file_hash"], ident["publisher"], ident["period"] or "")


def map_market(market_text: str, metric: str = "") -> dict:
    """map-submarkets: a publisher's market name -> our taxonomy, with a note when it is not exact."""
    market, exact = tx.resolve_market(market_text)
    note = ""
    if market and metric == "prime_rent_psf" and market in tx.CORE_SUBMARKET:
        market, exact = tx.CORE_SUBMARKET[market], False
    if market and not exact:
        note = f"'{market_text}' mapped to '{market}': the publisher's boundary may differ."
    return {"market": market, "exact": exact, "note": note}


def check_figures(store, raw: list[dict], pages: list[str], period: str | None) -> list[dict]:
    """check-figures: the three checks on every figure (evidence in the page text, plausible range,
    other sources for the same period). Returns review candidates; only figures that pass are pre-ticked."""
    sources = store.sources()
    candidates = []
    seen: dict[tuple, list[float]] = {}
    for r in raw:
        if r.get("metric") not in tx.METRICS:
            continue
        mapped = map_market(r["market_text"], r["metric"])
        market = mapped["market"]
        if not market:
            continue
        metric = grade_a_metric(r)
        r = {**r, "metric": metric}
        value = float(r["value"])
        if any(same_figure(metric, value, v) for v in seen.get((market, metric), [])):
            continue  # the same figure printed on a dashboard (9.9%) and in the text (9.91%): one row, not two
        seen.setdefault((market, metric), []).append(value)
        status, flags = check(r, pages)
        if mapped["note"]:
            flags.append(mapped["note"])
        stored = [o for o in store.observations(market=market, metric=metric) if o["period"] == period]
        compare = None
        if stored:
            s = stored[0]
            pub = sources.get(s["source_id"], {}).get("publisher", s["source_id"])
            diff = r["value"] - s["value"]
            compare = {"value": s["value"], "publisher": pub, "source_id": s["source_id"], "diff": round(diff, 3)}
            tol = 0.2 if tx.METRICS[metric]["unit"] == "%" else abs(s["value"]) * 0.03
            if abs(diff) > tol:
                flags.append(f"Differs from {pub} ({tx.fmt_value(metric, s['value'])}) by "
                             f"{diff:+.2f} {tx.METRICS[metric]['unit']}. Likely a definition difference; check before quoting.")
        # Pre-tick only figures found in the text layer, with a known label and a plausible value.
        suggest = status == "verified" and r.get("label_status") != "inferred" and not any("plausible" in f for f in flags)
        candidates.append({"market": market, "market_text": r["market_text"], "metric": metric,
                           "value": r["value"], "line": r.get("line", r.get("evidence", "")), "page": r.get("page"),
                           "where": r.get("where", ""), "status": status, "suggest_keep": suggest,
                           "stored": compare, "flags": flags})
    # Four different "London investment volumes" in one report are a quarter, a half, a year to date and a
    # forecast: nobody can tell which is which from the number alone, so none is shared unchecked.
    for c in candidates:
        others = seen.get((c["market"], c["metric"]), [])
        if len(others) > 1:
            c["flags"].append(f"This report gives {len(others)} different values for {c['market']} "
                              f"{tx.METRICS[c['metric']]['label'].lower()}; check which period each one is "
                              f"(quarter, year to date, forecast) before keeping it.")
            c["suggest_keep"] = False
    return candidates


def same_figure(metric: str, a: float, b: float) -> bool:
    """The same number printed twice with different rounding: 9.9% and 9.91%, £2.0bn and £2.02bn."""
    tol = 0.06 if tx.METRICS[metric]["unit"] == "%" else max(abs(b) * 0.012, 1e-9)
    return abs(a - b) <= tol


def build_analysis(store, path, pages: list[str], raw: list[dict], method: str, period: str | None = None,
                   publisher: str | None = None, steps: list[str] | None = None) -> dict:
    text = "\n".join(pages)
    period = period or detect_period(text)
    return {"file": str(path), "period": period, "publisher": publisher or detect_publisher(text, str(path)), "method": method,
            "file_hash": file_hash(path), "candidates": check_figures(store, raw, pages, period),
            "chars": len(text), "pages": len(pages),
            "steps": steps or ["dedupe", "read-pdf", "map-submarkets", "check-figures"]}


def analyse_document(store, llm, path: str | Path) -> dict:
    """Fixed-step version of the information agent's read-pdf skill: read, map, check. Nothing is
    written to the store here. The Pi information agent runs the same tools but chooses the pages,
    the reading method and how to treat odd layouts itself."""
    pages = pdf_pages(path)
    raw, method = [], "rules"
    if getattr(llm, "available", False):
        try:
            raw, method = extract_vision(llm, path, pages), f"vision model ({llm.model})"
        except Exception as e:  # budget, outage, or a model without image input
            method = f"rules (vision model failed: {type(e).__name__})"
    if method.startswith("rules"):
        raw = extract_rules("\n".join(pages))
        for r in raw:  # rules read the text layer, so the page is the one the line is on
            r["page"] = next((i + 1 for i, t in enumerate(pages) if r["line"] in t), None)
    return build_analysis(store, path, pages, raw, method)


def save_document(store, analysis: dict, accepted: list[int] | None = None, confirmed: list[int] | None = None,
                  user: str = "", licence: str = "", channel: str = "upload") -> dict:
    """Publish an upload to the whole team. Figures that passed every check are saved as they are; the rest
    of the kept figures are saved flagged (usable, shown with ⚠) until anyone checks them, unless the
    uploader already checked them here (`confirmed`). Unkept figures are dropped."""
    from .models import Observation
    period = analysis["period"]
    pub = analysis["publisher"]
    source_id = re.sub(r"[^A-Z0-9]+", "_", f"{pub} {Path(analysis['file']).stem} {period}".upper()).strip("_")
    store.add_source({"source_id": source_id, "publisher": pub, "title": f"{pub}: {Path(analysis['file']).name}",
                      "period": period, "url": "", "definition_note": f"Extracted with {analysis['method']}.",
                      "channel": channel, "uploaded_by": (user or "a colleague") if channel == "upload" else "",
                      "file_hash": analysis.get("file_hash", ""),
                      "licence": licence or ("Uploaded by a colleague under the team's own access" if channel == "upload"
                                             else "Open data")})
    accepted = range(len(analysis["candidates"])) if accepted is None else accepted
    confirmed = set(confirmed or [])
    obs, flags = [], []
    for i in accepted:
        c = analysis["candidates"][i]
        ok = c.get("suggest_keep", True) or i in confirmed
        obs.append(Observation(period=period, market=c["market"], metric=c["metric"], value=c["value"],
                               source_id=source_id, note=("Checked by the uploader. " if i in confirmed else "")
                               + ("; ".join(c["flags"]) if not ok else "")[:300]))
        flags.append("" if ok else ("; ".join(c["flags"]) or "Did not pass the automatic checks")[:300])
    store.add_observations(obs, flags, by="the automatic check")
    return {"source_id": source_id, "saved": len(obs), "flagged": sum(bool(f) for f in flags)}
