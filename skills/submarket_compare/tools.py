from core import analytics as an
from core import taxonomy as tx
from core.skill import Tool, obj_schema
from skills._common import METRIC_ENUM, market_arg, metric_arg, sources_for

DEFAULT_METRICS = ["prime_rent_psf", "vacancy_pct", "new_refurb_vacancy_pct", "take_up_msqft",
                   "availability_msqft", "active_requirements_msqft", "prime_yield_pct", "rent_free_months"]


def compare_markets(ctx, args):
    markets = [market_arg(m)[0] for m in args.get("markets", [])][:5]
    if len(markets) < 2:
        raise ValueError("Give at least two markets to compare.")
    metrics = [metric_arg(m) for m in args.get("metrics", [])] or DEFAULT_METRICS
    header = "| Metric | " + " | ".join(markets) + " |"
    lines, data, src = [header, "|---" * (len(markets) + 1) + "|"], [], []
    for metric in metrics:
        cells = []
        for market in markets:
            used, _ = an.resolve_for_metric(ctx.store, market, metric)
            snap = an.snapshot(ctx.store, used, metric)
            if snap:
                cells.append(f"{tx.fmt_value(metric, snap['value'])} ({an.period_label(snap['period'])})"
                             + ("*" if used != market else ""))
                data.append({"market": market, "metric": metric, "value": snap["value"],
                             "period": snap["period"], "market_used": used})
                src.append(snap["source_id"])
            else:
                cells.append("-")
        if any(c != "-" for c in cells):
            lines.append(f"| {tx.METRICS[metric]['label']} | " + " | ".join(cells) + " |")
    foot = "\n\n\\* prime rent for the core submarket" if any(d["market_used"] != d["market"] for d in data) else ""
    chart_metric = metrics[0]
    vals = [next((d["value"] for d in data if d["market"] == m and d["metric"] == chart_metric), None) for m in markets]
    return {"summary": "\n".join(lines) + foot, "data": data, "sources": sources_for(ctx.store, src),
            "chart": {"type": "bar", "title": tx.METRICS[chart_metric]["label"], "unit": tx.METRICS[chart_metric]["unit"],
                      "x": markets, "series": [{"name": tx.METRICS[chart_metric]["label"], "values": vals}]}}


def rank_submarkets(ctx, args):
    metric = metric_arg(args.get("metric", "vacancy_pct"))
    latest = an.latest_period(ctx.store)
    rows = [r for r in ctx.store.observations(metric=metric) if r["period"] == latest
            and r["market"] not in tx.TOP_MARKETS]
    best = {}
    for r in rows:
        best.setdefault(r["market"], r)
    ranked = sorted(best.values(), key=lambda r: -r["value"])
    if args.get("order") == "asc":
        ranked.reverse()
    top = ranked[: args.get("limit", 10)]
    lines = [f"**{tx.METRICS[metric]['label']} by submarket, {an.period_label(latest)}**"]
    lines += [f"{i}. {r['market']}: {tx.fmt_value(metric, r['value'])}" for i, r in enumerate(top, 1)]
    return {"summary": "\n".join(lines), "data": top,
            "sources": sources_for(ctx.store, [r["source_id"] for r in top]),
            "chart": {"type": "bar", "title": f"{tx.METRICS[metric]['label']} by submarket", "unit": tx.METRICS[metric]["unit"],
                      "x": [r["market"] for r in top], "series": [{"name": an.period_label(latest), "values": [r["value"] for r in top]}]}}


TOOLS = [
    Tool("compare_markets", "Compare 2-5 markets/submarkets across metrics (defaults to rent, vacancy, take-up, supply, demand, yield, incentives).",
         obj_schema({"markets": {"type": "array", "items": {"type": "string"}},
                     "metrics": {"type": "array", "items": {"type": "string", "enum": METRIC_ENUM}}}, ["markets"]),
         compare_markets),
    Tool("rank_submarkets", "Rank all submarkets on one metric for the latest quarter.",
         obj_schema({"metric": {"type": "string", "enum": METRIC_ENUM}, "order": {"type": "string", "enum": ["desc", "asc"]},
                     "limit": {"type": "integer"}}, ["metric"]), rank_submarkets),
]
