from core import analytics as an
from core import taxonomy as tx
from core.skill import Tool, obj_schema
from skills._common import market_arg, sources_for


def _in_market(row_market, market):
    return market in (None, "London") or row_market == market or tx.MARKET_PARENT.get(row_market) == market \
        or tx.top_market(row_market) == market


def get_pipeline(ctx, args):
    market = market_arg(args["market"])[0] if args.get("market") else None
    rows = [r for r in ctx.store.q("SELECT * FROM pipeline ORDER BY expected_completion")
            if _in_market(r["submarket"], market)]
    if args.get("status"):
        rows = [r for r in rows if r["status"] == args["status"]]
    if not rows:
        return {"summary": f"No tracked schemes{' in ' + market if market else ''}.", "data": []}
    lines = [f"**Development pipeline{' - ' + market if market else ''}** ({len(rows)} schemes)"]
    for r in rows:
        who = f", pre-let to {r['prelet_party']}" if r["prelet_party"] else ""
        lines.append(f"- {r['scheme']} ({r['submarket']}): {int(r['size_sqft']):,} sq ft, {r['status']}{who}, "
                     f"due {an.period_label(r['expected_completion'])}")
    spec = sum(r["size_sqft"] for r in rows if r["status"] == "speculative")
    lines.append(f"\nSpeculative space: {spec:,.0f} sq ft.")
    stats = []
    for m in ([tx.top_market(market)] if market and market != "London" else tx.TOP_MARKETS[1:]):
        snap = an.snapshot(ctx.store, m, "prelet_share_under_construction_pct")
        if snap:
            stats.append(f"{m}: {snap['value']:.1f}% of space under construction pre-let ({an.period_label(snap['period'])})")
    if stats:
        lines.append("\nMarket context: " + "; ".join(stats) + ".")
    return {"summary": "\n".join(lines), "data": rows, "sources": sources_for(ctx.store, [r["source_id"] for r in rows])}


def get_deals(ctx, args):
    market = market_arg(args["market"])[0] if args.get("market") else None
    rows = [r for r in ctx.store.q("SELECT * FROM deals ORDER BY period DESC, size_sqft DESC")
            if _in_market(r["submarket"], market)]
    if args.get("deal_type"):
        kinds = {"leasing": ("letting", "pre-let", "sublease")}.get(args["deal_type"], (args["deal_type"],))
        rows = [r for r in rows if r["deal_type"] in kinds]
    rows = rows[: args.get("limit", 10)]
    if not rows:
        return {"summary": "No matching deals.", "data": []}
    lines = [f"**Recent deals{' - ' + market if market else ''}**"]
    for r in rows:
        if r["deal_type"] == "investment":
            terms = f"£{r['price_gbp_m']:.0f}m" + (f" at {r['yield_pct']:.2f}% yield" if r["yield_pct"] else "")
            lines.append(f"- {an.period_label(r['period'])} investment: {r['building']} ({r['submarket']}) bought by {r['party']} for {terms}")
        else:
            rent = f" at £{r['rent_psf']:.2f}/sq ft" if r["rent_psf"] else ""
            lines.append(f"- {an.period_label(r['period'])} {r['deal_type']}: {r['party']} took {int(r['size_sqft']):,} sq ft at "
                         f"{r['building']} ({r['submarket']}){rent}")
    return {"summary": "\n".join(lines), "data": rows, "sources": sources_for(ctx.store, [r["source_id"] for r in rows])}


TOOLS = [
    Tool("get_pipeline", "Office schemes under construction (speculative or pre-let) with size and expected completion.",
         obj_schema({"market": {"type": "string"}, "status": {"type": "string", "enum": ["speculative", "pre-let"]}}),
         get_pipeline),
    Tool("get_deals", "Recent leasing (letting, pre-let, sublease) and investment transactions.",
         obj_schema({"market": {"type": "string"}, "deal_type": {"type": "string", "enum": ["leasing", "letting", "pre-let", "investment"]},
                     "limit": {"type": "integer"}}), get_deals),
]
