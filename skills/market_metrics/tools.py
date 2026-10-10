from core import analytics as an
from core import taxonomy as tx
from core.skill import Tool, obj_schema
from skills._common import MARKET_ENUM, METRIC_ENUM, market_arg, metric_arg, sources_for


def get_metric_trend(ctx, args):
    market, note = market_arg(args.get("market"))
    metric = metric_arg(args.get("metric", "vacancy_pct"))
    market, core_note = an.resolve_for_metric(ctx.store, market, metric)
    s = an.series(ctx.store, market, metric)
    if not s:
        return {"summary": f"No {tx.METRICS[metric]['label'].lower()} data for {market} yet.", "data": []}
    label = tx.METRICS[metric]["label"]
    cur, first = s[-1], s[0]
    lines = [f"**{label}, {market}**: {tx.fmt_value(metric, cur['value'])} in {an.period_label(cur['period'])}."]
    if len(s) > 1:
        prev = s[-2]
        lines.append(f"Previous reading {tx.fmt_value(metric, prev['value'])} ({an.period_label(prev['period'])}); "
                     f"{tx.fmt_value(metric, first['value'])} at the start of the series ({an.period_label(first['period'])}).")
    if cur["lta"] is not None:
        gap = cur["value"] - cur["lta"]
        lines.append(f"Long-term average {tx.fmt_value(metric, cur['lta'])} ({'above' if gap > 0 else 'below'} by "
                     f"{abs(gap):.2f} {tx.METRICS[metric]['unit']}).")
    alts = [a for p in s for a in p["alternatives"]]
    if alts:
        lines.append(f"Note: {len(alts)} reading(s) disagree with the primary source; see data quality signals.")
    for n in (an.warning(cur), note, core_note, cur["note"]):
        if n:
            lines.append(f"_{n}_")
    return {
        "summary": " ".join(lines),
        "data": [{"period": p["period"], "value": p["value"], "lta": p["lta"], "source_id": p["source_id"]} for p in s],
        "sources": sources_for(ctx.store, [p["source_id"] for p in s]),
        "chart": {"type": "line", "title": f"{label}: {market}", "unit": tx.METRICS[metric]["unit"],
                  "x": [an.period_label(p["period"]) for p in s],
                  "series": [{"name": market, "values": [p["value"] for p in s]}]
                  + ([{"name": "Long-term average", "values": [p["lta"] for p in s]}] if any(p["lta"] for p in s) else [])},
    }


def market_snapshot(ctx, args):
    market, note = market_arg(args.get("market"))
    rows, src, flagged = [], [], []
    for metric in tx.METRICS:
        m, _ = an.resolve_for_metric(ctx.store, market, metric)
        snap = an.snapshot(ctx.store, m, metric)
        if not snap:
            continue
        rows.append({"metric": tx.METRICS[metric]["label"],
                     "value": tx.fmt_value(metric, snap["value"]) + (" (flagged)" if snap["status"] == "flagged" else ""),
                     "period": an.period_label(snap["period"]),
                     "change": None if snap["change"] is None else round(snap["change"], 2),
                     "long_term_avg": None if snap["lta"] is None else tx.fmt_value(metric, snap["lta"]),
                     "market_used": m})
        src.append(snap["source_id"])
        if snap["status"] == "flagged":
            flagged.append(snap)
    if not rows:
        return {"summary": f"No data for {market}.", "data": []}
    warns = [f"{tx.METRICS[sn['metric']]['label']}: {an.warning(sn)}" for sn in flagged]
    table = "\n".join(f"| {r['metric']} | {r['value']} | {r['period']} | {r['long_term_avg'] or '-'} |" for r in rows)
    return {"summary": f"**Snapshot: {market}** {note}\n\n| Metric | Latest | Period | Long-term avg |\n|---|---|---|---|\n{table}"
                       + "".join(f"\n\n_{w}_" for w in warns),
            "data": rows, "sources": sources_for(ctx.store, src)}


TOOLS = [
    Tool("get_metric_trend", "Time series, latest value, change and long-term average for one metric in one market.",
         obj_schema({"market": {"type": "string", "description": "Market or submarket, e.g. 'West End', 'City Core', 'Canary Wharf'. Known: " + ", ".join(MARKET_ENUM)},
                     "metric": {"type": "string", "enum": METRIC_ENUM}}, ["market", "metric"]),
         get_metric_trend),
    Tool("market_snapshot", "Latest value of every tracked metric for one market or submarket.",
         obj_schema({"market": {"type": "string"}}, ["market"]), market_snapshot),
]
