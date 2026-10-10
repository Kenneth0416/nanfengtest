"""Read helpers over the store: series, latest values and quarter maths."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from . import taxonomy as tx


def quarter_end(period: str) -> date:
    y, q = int(period[:4]), int(period[-1])
    return date(y, q * 3, 30 if q in (2, 3) else 31)


def period_label(period: str) -> str:
    return f"Q{period[-1]} {period[:4]}" if len(period) == 6 and period[4] == "Q" else period


def series(store, market: str, metric: str, publisher: str | None = None) -> list[dict]:
    """One value per period. When several sources report the same period the
    first-loaded (primary) source wins; the others are kept in `alternatives`."""
    rows = store.observations(market=market, metric=metric)
    sources = store.sources()
    by_period: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        r["publisher"] = sources.get(r["source_id"], {}).get("publisher", r["source_id"])
        if publisher and r["publisher"] != publisher:
            continue
        by_period[r["period"]].append(r)
    out = []
    for period in sorted(by_period):
        first, *others = by_period[period]
        first = dict(first)
        first["alternatives"] = [{"value": o["value"], "source_id": o["source_id"], "publisher": o["publisher"],
                                  "note": o["note"], "status": o.get("status", "ok")} for o in others]
        out.append(first)
    return out


def resolve_for_metric(store, market: str, metric: str) -> tuple[str, str]:
    """Rents are published for core submarkets; fall back to them if needed."""
    if store.observations(market=market, metric=metric):
        return market, ""
    core = tx.CORE_SUBMARKET.get(market)
    if core and store.observations(market=core, metric=metric):
        return core, f"{tx.METRICS[metric]['label']} is published for {core}, the prime core of {market}."
    return market, ""


def latest_period(store) -> str:
    row = store.q("SELECT MAX(period) AS p FROM observations")
    return row[0]["p"] if row else ""


def snapshot(store, market: str, metric: str) -> dict | None:
    """Latest value, previous value and long-term average for one series."""
    s = series(store, market, metric)
    if not s:
        return None
    cur = s[-1]
    prev = s[-2] if len(s) > 1 else None
    return {
        "market": market, "metric": metric, "period": cur["period"], "value": cur["value"],
        "lta": cur["lta"], "source_id": cur["source_id"], "note": cur["note"],
        "prev_period": prev["period"] if prev else None, "prev_value": prev["value"] if prev else None,
        "change": round(cur["value"] - prev["value"], 3) if prev else None,
        "alternatives": cur["alternatives"], "rowid": cur.get("rowid"),
        "status": cur.get("status", "ok"), "flag": cur.get("flag", ""), "flagged_by": cur.get("flagged_by", ""),
    }


def warning(row: dict | None) -> str:
    """One line for any flagged figure, so every page and the Copilot carry the same caveat."""
    if not row or row.get("status") != "flagged":
        return ""
    who = f" by {row['flagged_by']}" if row.get("flagged_by") else ""
    return f"⚠ Flagged{who}, not yet checked: {row.get('flag') or 'needs a second look'}"


def provenance(src: dict) -> str:
    """How a figure reached the shared library: an automatic open-data feed or a colleague's upload."""
    if src.get("channel") == "upload":
        when = (src.get("uploaded_at") or "")[:10]
        return f"🟠 Uploaded by {src.get('uploaded_by') or 'a colleague'}" + (f" · {when}" if when else "")
    return "🟢 Open data · collected automatically"


def source_ref(store, source_id: str) -> dict:
    s = store.sources().get(source_id, {})
    return {"source_id": source_id, "title": s.get("title", source_id), "publisher": s.get("publisher", ""),
            "url": s.get("url", ""), "definition_note": s.get("definition_note", ""),
            "channel": s.get("channel", "auto"), "provenance": provenance(s) if s else ""}
