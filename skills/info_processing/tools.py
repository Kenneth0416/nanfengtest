"""Parsing tools for the information agent. Each does one step, so the agent can adapt the order to
the material: a dashboard PDF, a table on page 9, a CSV from an open-data API, a results statement."""
import io
import re
from pathlib import Path

from core import documents as docs
from core import internal as I
from core import taxonomy as tx
from core.skill import Tool, obj_schema

ROOT = Path(__file__).resolve().parent.parent.parent
FIGURE = {"type": "object", "properties": {
    "market_text": {"type": "string"}, "metric": {"type": "string", "enum": list(tx.METRICS)},
    "value": {"type": "number"}, "page": {"type": "integer"}, "where": {"type": "string"},
    "label_status": {"type": "string", "enum": ["explicit", "inferred"]}, "evidence": {"type": "string"}},
    "required": ["market_text", "metric", "value"]}
FIGS = {"path": {"type": "string"}, "figures": {"type": "array", "items": FIGURE},
        "period": {"type": "string", "description": "e.g. 2026Q2"}, "publisher": {"type": "string"},
        "method": {"type": "string", "description": "how the figures were read, e.g. 'vision model, pages 2-4'"}}


def _local(path: str) -> Path:
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    if not p.exists():
        raise ValueError(f"No file at {path}. Fetch it first with fetch_source.")
    return p


def list_skills(ctx, args):
    out = []
    for f in sorted((ROOT / "info_skills").glob("*/SKILL.md")):
        meta = dict(re.findall(r"^(\w+):\s*(.+)$", f.read_text().split("---")[1], re.M))
        out.append({"name": meta.get("name", f.parent.name), "description": meta.get("description", "")})
    return {"summary": "\n".join(f"- {s['name']}: {s['description']}" for s in out), "data": out}


def load_skill(ctx, args):
    f = ROOT / "info_skills" / re.sub(r"[^a-z0-9-]", "", args["name"].lower()) / "SKILL.md"
    if not f.exists():
        return {"summary": f"No skill '{args['name']}'. " + list_skills(ctx, {})["summary"], "data": None}
    return {"summary": f.read_text().split("---", 2)[2].strip(), "data": {"name": args["name"]}}


def fetch_source(ctx, args):
    """fetch-source: HTML comes back as text; files (PDF, CSV, Excel, JSON) are saved under data/fetched.
    The Pi tool does the download and passes the body in; the Python engine downloads here."""
    import base64
    import hashlib
    url = args["url"]
    body = base64.b64decode(args["body_b64"]) if args.get("body_b64") else None
    content_type = args.get("content_type", "")
    if body is None:
        import requests
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (london-office-agent PoC)"})
        r.raise_for_status()
        body, content_type = r.content, r.headers.get("content-type", "")
    low = url.lower().split("?")[0]
    ext = next((e for e, k in ((".pdf", "pdf"), (".csv", "csv"), (".xlsx", "spreadsheet"), (".xls", "excel"),
                                (".json", "json")) if low.endswith(e) or k in content_type), "")
    if ext:
        folder = ROOT / "data" / "fetched"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{hashlib.sha256(body).hexdigest()[:12]}{ext}"
        path.write_bytes(body)
        return {"summary": f"Saved {ext[1:].upper()} to {path.relative_to(ROOT)} ({len(body) // 1024} KB).",
                "data": {"path": str(path.relative_to(ROOT)), "type": ext[1:]}}
    from core import gather
    page = gather.parse_page(body.decode("utf-8", "replace"), url)
    kind = "feed" if "xml" in content_type or body.lstrip()[:5] == b"<?xml" else "html"
    return {"summary": f"{kind.upper()}: **{page['title']}** ({page['site'] or url}, {page['published'] or 'no date'})\n"
                       f"{page['description']}\n\n{page['text'][:3000]}", "data": {**page, "type": kind}}


def dedupe_report(ctx, args):
    p = _local(args["path"])
    ident = docs.identify(p)
    dup = ctx.store.find_upload(ident["file_hash"], ident["publisher"], ident["period"] or "")
    if dup:
        return {"summary": f"Duplicate: {dup['uploaded_by'] or 'the agent'} added {dup['publisher']} {dup['period']} "
                           f"on {(dup['uploaded_at'] or '')[:10]}. Stop: do not read or save it again.",
                "data": {"duplicate": True, **dup}}
    return {"summary": f"New: {ident['publisher']} {ident['period'] or '(period not found in text)'}.",
            "data": {"duplicate": False, **ident}}


def pdf_overview(ctx, args):
    p = _local(args["path"])
    pages = docs.pdf_pages(p)
    text = "\n".join(pages)
    rows = []
    for i, t in enumerate(pages, 1):
        kind = ("image only (chart, dashboard or scan)" if len(docs._numbers(t)) < 3
                else "data" if docs.DATA_WORDS.search(t) else "text")
        rows.append({"page": i, "chars": len(t), "numbers": len(docs._numbers(t)), "kind": kind,
                     "first_line": (t.strip().splitlines() or [""])[0][:90]})
    return {"summary": f"{len(pages)} pages; publisher {docs.detect_publisher(text)}; period {docs.detect_period(text)}; "
                       f"suggested pages {docs.data_pages(pages)}\n"
                       + "\n".join(f"p.{r['page']}: {r['kind']}, {r['numbers']} numbers - {r['first_line']}" for r in rows),
            "data": {"pages": rows, "publisher": docs.detect_publisher(text), "period": docs.detect_period(text),
                     "suggested": docs.data_pages(pages)}}


def pdf_page_text(ctx, args):
    pages = docs.pdf_pages(_local(args["path"]))
    n = int(args["page"])
    return {"summary": pages[n - 1][:8000] if 0 < n <= len(pages) else "No such page.", "data": {"page": n}}


_READ_PAGES: dict[tuple, dict] = {}   # (file hash, pages) -> result, so a retried or repeated call costs nothing


def read_pdf_pages(ctx, args):
    """Vision model (MiMo by default) reads the pages as images, with their text layers."""
    p = _local(args["path"])
    key = (docs.file_hash(p), tuple(args.get("pages") or []))
    if key in _READ_PAGES:
        return {**_READ_PAGES[key], "summary": "(already read; same result as before)\n" + _READ_PAGES[key]["summary"]}
    out = _read_pdf_pages(ctx, p, args)
    _READ_PAGES[key] = out
    return out


def _read_pdf_pages(ctx, p, args):
    vision = ctx.vision or ctx.llm
    if not getattr(vision, "available", False):
        pages = docs.pdf_pages(p)
        raw = docs.extract_rules("\n".join(pages[n - 1] for n in args.get("pages") or range(1, len(pages) + 1)))
        for r in raw:
            r["page"] = next((i + 1 for i, t in enumerate(pages) if r["line"] in t), None)
        return {"summary": f"No vision model configured: read {len(raw)} figures from the text layer with rules.",
                "data": {"figures": raw, "method": "rules"}}
    raw = docs.extract_vision(vision, p, docs.pdf_pages(p), args.get("pages"))
    return {"summary": f"{len(raw)} figures read by {vision.model} from pages {args.get('pages') or 'suggested'}:\n"
                       + "\n".join(f"- p.{r['page']} {r['market_text']} {r['metric']} {r['value']} "
                                   f"({r.get('label_status', '?')}, {r.get('where', '')})" for r in raw[:60]),
            "data": {"figures": raw, "method": f"vision model ({vision.model})"}}


def map_markets(ctx, args):
    out = [{"as_written": n, **docs.map_market(n, args.get("metric", ""))} for n in args["names"]]
    return {"summary": "\n".join(f"- {o['as_written']} -> {o['market'] or 'UNKNOWN (drop or ask)'}"
                                 + (f" ({o['note']})" if o["note"] else "") for o in out), "data": out}


def _analysis(ctx, args, steps):
    p = _local(args["path"]) if args.get("path") else None
    pages = docs.pdf_pages(p) if p and p.suffix.lower() == ".pdf" else []
    return docs.build_analysis(ctx.store, p or "agent", pages, args.get("figures", []), args.get("method", "agent"),
                               args.get("period"), args.get("publisher"), steps)


def check_figures(ctx, args):
    a = _analysis(ctx, args, None)
    lines = [f"- {'✓' if c['suggest_keep'] else '⚠'} {c['market']} {tx.METRICS[c['metric']]['label']} "
             f"{tx.fmt_value(c['metric'], c['value'])} [{c['status']}] {' '.join(c['flags'])}" for c in a["candidates"]]
    passed = sum(c["suggest_keep"] for c in a["candidates"])
    return {"summary": f"{passed} of {len(a['candidates'])} pass all three checks.\n" + "\n".join(lines),
            "data": a["candidates"]}


def stage_figures(ctx, args):
    """For a colleague's upload: keep the checked figures for them to review and publish in Sources."""
    a = _analysis(ctx, args, args.get("steps"))
    ctx.store.stage(str(_local(args["path"])), a, ctx.role, "Pi information agent")
    passed = sum(c["suggest_keep"] for c in a["candidates"])
    return {"summary": f"Staged {len(a['candidates'])} figures for {ctx.role} to review ({passed} passed every check).",
            "data": {"figures": len(a["candidates"]), "passed": passed}}


def save_figures(ctx, args):
    """For automatic sources (open data, public filings): save now. Passed figures are shared as they
    are; the rest are shared with ⚠ for anyone to check."""
    a = _analysis(ctx, args, args.get("steps"))
    if args.get("path") and docs.duplicate_of(ctx.store, _local(args["path"])):
        return {"summary": "Already in the library; nothing saved.", "data": None}
    res = docs.save_document(ctx.store, a, channel=args.get("channel", "auto"), user=ctx.role,
                             licence=args.get("licence", ""))
    ctx.store.log("auto" if args.get("channel", "auto") == "auto" else "upload", "Information agent",
                  f"filed {a['publisher']} {a['period']}: {res['saved']} figures, {res['flagged']} to check")
    return {"summary": f"Saved {res['saved']} figures as {res['source_id']}; {res['flagged']} marked ⚠ for a person.",
            "data": res}


def read_table(ctx, args):
    import pandas as pd
    src = args["source"]
    if src.startswith("http"):
        import requests
        r = requests.get(src, timeout=20, headers={"User-Agent": "Mozilla/5.0 (london-office-agent PoC)"})
        r.raise_for_status()
        data, name = r.content, src.split("?")[0]
    else:
        p = _local(src)
        data, name = p.read_bytes(), p.name
    low = name.lower()
    if low.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(data), sheet_name=args.get("sheet") or 0)
    elif low.endswith(".json"):
        df = pd.json_normalize(pd.read_json(io.BytesIO(data)).to_dict("records"))
    else:
        df = pd.read_csv(io.BytesIO(data), skiprows=args.get("skiprows", 0))
    head = df.head(args.get("rows", 8))
    return {"summary": f"{len(df)} rows; columns: {', '.join(map(str, df.columns))}\n\n{head.to_csv(index=False)}",
            "data": {"columns": list(map(str, df.columns)), "rows": len(df), "head": head.astype(str).to_dict("records")}}


def save_series(ctx, args):
    """Time-series points from open data (e.g. a Bank of England or ONS series) into the library."""
    sid = args["source_id"]
    ctx.store.add_source({"source_id": sid, "publisher": args.get("publisher", ""), "title": args.get("title", sid),
                          "url": args.get("url", ""), "channel": "auto",
                          "licence": args.get("licence", "Open Government Licence")})
    n = 0
    for r in args["rows"]:
        ctx.store.add_macro({"date": str(r["date"])[:10], "indicator": r["indicator"], "value": float(r["value"]),
                             "unit": r.get("unit", ""), "source_id": sid, "note": r.get("note", "")})
        n += 1
    ctx.store.log("auto", "Information agent", f"filed {n} points of {args.get('title', sid)}")
    return {"summary": f"Saved {n} points as {sid}.", "data": {"saved": n}}


def read_photo(ctx, args):
    """read-photo: the vision model reads a photo, screenshot or short PDF as one of our deals."""
    p = _local(args["path"])
    vision = ctx.vision or ctx.llm
    out = I.deal_from_images(vision, I.images_of(p), args.get("hint", ""))
    if not out:
        return {"summary": "No vision model is configured, so the image could not be read. File it with "
                           "save_internal_deal using the fields the colleague said, with original = this path; "
                           "the photo stays beside the record for a person to read.",
                "data": {"fields": {}, "confidence": "low", "notes": "no vision model", "path": str(p)}}
    found = {k: v for k, v in out["fields"].items() if v}
    return {"summary": f"Read by {getattr(vision, 'model', 'the vision model')} ({out['confidence']} confidence): "
                       + (", ".join(f"{I.LABELS[k]} {v}" for k, v in found.items()) or "no deal fields visible")
                       + (f". {out['notes']}" if out.get("notes") else "")
                       + f". Missing: {', '.join(I.LABELS[k] for k in I.FIELDS if k not in found) or 'nothing'}.",
            "data": {**out, "path": str(p)}}


def save_internal_deal(ctx, args):
    fields = args.get("fields") or {}
    if not fields.get("property"):
        return {"summary": "The record needs at least the property. Ask the colleague which building it is.",
                "data": {"recorded": False}}
    res = I.record(ctx.store, fields, ctx.role, args.get("how") or "photo", args.get("original"),
                   args.get("confidence") or "medium")
    d = res["deal"]
    ctx.store.log("internal", ctx.role, (f"added a {args.get('how') or 'photo'} to our record for {d['property']}"
                                         + (f" (filled {', '.join(res['filled'])})" if res["filled"] else ""))
                  if res["merged"] else f"recorded an internal deal from a {args.get('how') or 'photo'}: {d['property']}")
    return {"summary": (f"Merged into the existing record for {d['property']} (same property and floor); filled "
                        f"{', '.join(I.LABELS[k] for k in res['filled']) or 'nothing new'}." if res["merged"]
                        else f"New internal record for {d['property']}.")
                       + (f" Missing: {', '.join(I.LABELS[k] for k in d['missing'])}." if d["missing"] else " Complete.")
                       + (f" {d['ext']['text']}" if d.get("ext") else ""),
            "data": {"recorded": True, "merged": res["merged"], "deal": d}}


def deals_from_table(ctx, args):
    """read-table for 🔵 internal spreadsheets: one record per row, merged where the team already has the deal."""
    head = read_table(ctx, {"source": args["path"], "sheet": args.get("sheet"), "rows": 500,
                            "skiprows": args.get("skiprows", 0)})
    rows = I.deals_from_rows(head["data"]["head"])
    made, merged = 0, 0
    for r in rows:
        res = I.record(ctx.store, r, ctx.role, f"spreadsheet {Path(args['path']).name}", args["path"])
        merged += res["merged"]
        made += not res["merged"]
    ctx.store.log("internal", ctx.role, f"uploaded {Path(args['path']).name}: {len(rows)} rows, {merged} matched existing "
                                        f"records, {made} new")
    return {"summary": f"{len(rows)} deal rows: {merged} merged into records the team already had, {made} new"
                       + (f"; {head['data']['rows'] - len(rows)} rows had no property and were skipped." if head['data']['rows'] > len(rows) else "."),
            "data": {"rows": len(rows), "merged": merged, "new": made}}


POINT = {"type": "object", "properties": {"date": {"type": "string"}, "indicator": {"type": "string"},
         "value": {"type": "number"}, "unit": {"type": "string"}, "note": {"type": "string"}},
         "required": ["date", "indicator", "value"]}

TOOLS = [
    Tool("list_skills", "The information agent's playbooks, one per kind of material.", obj_schema({}), list_skills),
    Tool("load_skill", "Load one playbook (check-terms, fetch-source, read-pdf, read-table, read-article, "
         "map-submarkets, check-figures, dedupe) and follow it.", obj_schema({"name": {"type": "string"}}, ["name"]),
         load_skill),
    Tool("fetch_source", "fetch-source: get a link once. Web pages come back as text; PDFs, CSV, Excel and JSON are "
         "saved and their path returned for read-pdf or read-table.",
         obj_schema({"url": {"type": "string"}, "body_b64": {"type": "string"}, "content_type": {"type": "string"}},
                    ["url"]), fetch_source),
    Tool("dedupe_report", "dedupe: is this report already in the library (same file, or same publisher and quarter)?",
         obj_schema({"path": {"type": "string"}}, ["path"]), dedupe_report),
    Tool("pdf_overview", "read-pdf: page-by-page overview of a PDF (text, numbers, image-only pages), publisher, "
         "period and suggested data pages.", obj_schema({"path": {"type": "string"}}, ["path"]), pdf_overview),
    Tool("pdf_page_text", "read-pdf: the text layer of one page, for a sentence of context only. Figures come "
                          "from read_pdf_pages (vision), which also reads charts and dashboards the text layer misses.",
         obj_schema({"path": {"type": "string"}, "page": {"type": "integer"}}, ["path", "page"]), pdf_page_text),
    Tool("read_pdf_pages", "read-pdf: the vision model reads the chosen pages as images (tables, charts, dashboards) "
         "and returns figures with page, location and whether the label was printed or inferred. Pass all the "
         "data pages in ONE call; a repeated call for the same pages returns the earlier result.",
         obj_schema({"path": {"type": "string"}, "pages": {"type": "array", "items": {"type": "integer"}}}, ["path"]),
         read_pdf_pages),
    Tool("map_markets", "map-submarkets: map market names as printed to the team's submarkets, with boundary notes.",
         obj_schema({"names": {"type": "array", "items": {"type": "string"}}, "metric": {"type": "string"}}, ["names"]),
         map_markets),
    Tool("check_figures", "check-figures: run the three checks (in the page text, plausible range, other sources) "
         "on figures before anything is saved.", obj_schema(FIGS, ["figures"]), check_figures),
    Tool("stage_figures", "For a colleague's upload: keep the checked figures for them to review and publish.",
         obj_schema({**FIGS, "steps": {"type": "array", "items": {"type": "string"}}}, ["path", "figures"]),
         stage_figures, read_only=False),
    Tool("save_figures", "For an automatic source: save checked figures now (failed checks are saved with ⚠).",
         obj_schema({**FIGS, "channel": {"type": "string", "enum": ["auto", "upload"]}, "licence": {"type": "string"},
                     "steps": {"type": "array", "items": {"type": "string"}}}, ["figures"]), save_figures, read_only=False),
    Tool("read_table", "read-table: read a CSV, Excel or JSON table from a link or file: columns, row count, first rows.",
         obj_schema({"source": {"type": "string"}, "sheet": {"type": "string"}, "skiprows": {"type": "integer"},
                     "rows": {"type": "integer"}}, ["source"]), read_table),
    Tool("read_photo", "read-photo: the vision model reads a photo, screenshot or short PDF of one of OUR OWN deals "
                       "(lease page, heads of terms, a message) and returns the deal fields it can see.",
         obj_schema({"path": {"type": "string"}, "hint": {"type": "string"}}, ["path"]), read_photo),
    Tool("save_internal_deal", "File one of our deals as a 🔵 internal record (merged into the same property and floor "
                               "if the team already has it). fields: property, floor_area, tenant, rent, term, rent_free, "
                               "date, counterparty; how: 'photo', 'PDF', 'screenshot'; original: the file path.",
         obj_schema({"fields": {"type": "object", "properties": {k: {"type": "string"} for k in I.FIELDS}},
                     "how": {"type": "string"}, "original": {"type": "string"},
                     "confidence": {"type": "string", "enum": ["high", "medium", "low"]}}, ["fields"]),
         save_internal_deal, read_only=False),
    Tool("deals_from_table", "read-table for a spreadsheet of OUR OWN deals: one 🔵 internal record per row (columns "
                             "matched by name: property, floor/area, tenant, rent, term, rent-free, date, counterparty).",
         obj_schema({"path": {"type": "string"}, "sheet": {"type": "string"}, "skiprows": {"type": "integer"}}, ["path"]),
         deals_from_table, read_only=False),
    Tool("save_series", "read-table: save time-series points (date, indicator, value, unit) from open data.",
         obj_schema({"source_id": {"type": "string"}, "publisher": {"type": "string"}, "title": {"type": "string"},
                     "url": {"type": "string"}, "licence": {"type": "string"},
                     "rows": {"type": "array", "items": POINT}}, ["source_id", "rows"]), save_series, read_only=False),
]
