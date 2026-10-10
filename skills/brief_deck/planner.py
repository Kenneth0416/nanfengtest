"""What this week's data says is worth a slide, and a storyline built from it.

stories(d, focus, rules) ranks candidate slides from the deck data: every one carries the reason it is a
candidate ("vacancy crossed the team's 8.5% alert line", "investment 36% below the long-term average") and
a score, so two weeks with different data give different lists. The Copilot reads them and decides; without
a model, plan_spec() turns the top candidates into a spec (the fallback the UI labels as rule-picked).
Nothing here invents a figure: every number comes from deck_data and is checked again at build time.
"""
from __future__ import annotations

from core import taxonomy as tx

BIG_PP = 0.4          # a vacancy move (percentage points) big enough to lead a slide
LTA_GAP = 15          # % away from the long-term average that is worth saying
MIN_CONTENT, MAX_CONTENT = 1, 4


def _k(d: dict) -> dict:
    return {x["metric"]: x for x in d.get("kpis") or []}


def _crossed(rules: list[dict], market: str, metric: str, value: float, prev: float | None) -> dict | None:
    """A team alert rule this figure crossed on the latest move."""
    for r in rules or []:
        if r.get("metric") != metric or (r.get("market") or market) != market or r.get("value") is None:
            continue
        lim = float(r["value"])
        now = {">": value > lim, ">=": value >= lim, "<": value < lim, "<=": value <= lim}.get(r.get("op"), False)
        was = {">": prev > lim, ">=": prev >= lim, "<": prev < lim, "<=": prev <= lim}.get(r.get("op"), False) \
            if prev is not None else False
        if now and not was:
            return r
    return None


def stories(d: dict, focus: dict | None = None, rules: list[dict] | None = None) -> list[dict]:
    k = _k(d)
    fmk = set((focus or {}).get("markets") or [])
    out = []

    def add(key, score, reason, layout, fill, title, chart_label="", so_what="", extra=None):
        out.append({"key": key, "score": round(score, 2), "reason": reason, "layout": layout, "fill": fill,
                    "title": title, "chart_label": chart_label, "so_what": so_what, **(extra or {})})

    vac, take, req, inv = k.get("vacancy_pct"), k.get("take_up_msqft"), k.get("active_requirements_msqft"), k.get("investment_gbp_bn")
    if vac and d.get("vacancy"):
        chg = vac.get("change") or 0
        reasons, score = [], 1.0 + min(abs(chg), 2) * 2
        rule = _crossed(rules or [], "London", "vacancy_pct", vac["value"], vac.get("prev"))
        if rule:
            reasons.append(f"crossed the team's alert line ({rule.get('label') or f'{rule['op']} {rule['value']}'})")
            score += 3
        if vac["value"] <= min(r["value"] for r in d["vacancy"]):
            reasons.append(f"the lowest since {d['vacancy'][0]['period']}")
            score += 1.5
        elif vac["value"] >= max(r["value"] for r in d["vacancy"]):
            reasons.append(f"the highest since {d['vacancy'][0]['period']}")
            score += 1.5
        if abs(chg) >= BIG_PP:
            reasons.append(f"moved {chg:+.2f}pp on the quarter")
        if not reasons:
            reasons.append(f"little changed ({chg:+.2f}pp)")
            score -= 1
        verb = "fell" if chg < 0 else "rose" if chg > 0 else "held"
        title = f"Vacancy {verb} to {vac['text']}"
        if take and take.get("vs_lta_pct") is not None and abs(take["vs_lta_pct"]) >= LTA_GAP / 2:
            title += f"; take-up {abs(take['vs_lta_pct'])}% {'above' if take['vs_lta_pct'] > 0 else 'below'} average"
            reasons.append(f"take-up {take['vs_lta_pct']:+d}% vs its long-term average")
            score += 0.5
        hero = rule is not None or abs(chg) >= 1.0
        add("occupiers", score, "Vacancy " + "; ".join(reasons), "Hero number" if hero else "Two charts",
            ({"hero": {"metric": "vacancy_pct"}, "chart_label": "Central London vacancy rate", "chart": {"chart": "vacancy"},
              "source": f"Source {d['vacancy'][-1]['ref']}."} if hero else
             {"left_label": "Central London vacancy rate", "left_chart": {"chart": "vacancy"},
              "right_label": "Take-up, m sq ft" + (f" · long-term average {take['lta']:.2f}" if take and take.get("lta") else ""),
              "right_chart": {"chart": "take_up"},
              "source": f"Source {d['vacancy'][-1]['ref']}. Quarters with no figures in the library are not shown."}),
            title, so_what=(f"Active requirements are up to {req['text']}: demand is still building."
                            if req and (req.get("change") or 0) > 0 else ""))
    if d.get("rents"):
        movers = [r for r in d["rents"] if r.get("change")]
        top = d["rents"][0]
        core = [m for m in movers if m["market"] in fmk] or movers
        score = 0.8 + min(len(movers), 5) * 0.5 + (1.0 if any(m["market"] in fmk for m in movers) else 0)
        reason = (f"{len(movers)} of {len(d['rents'])} submarket rents moved" + (", including " + ", ".join(m["market"] for m in core[:2]) if core else "")
                  if movers else "no prime rent moved this quarter")
        t = f"{top['market']} leads at £{top['value']:g}/sq ft"
        if core:
            m = core[0]
            t += f"; {m['market']} {'up' if m['change'] > 0 else 'down'} £{abs(m['change']):.2f} on the quarter"
        lines = [[("MOVED ON THE QUARTER", {"bold": True, "size": 9})]] + (
            [f"{m['market']}: £{m['value']:.2f} ({m['change']:+.2f}) {m['ref']}" for m in movers[:5]] or ["No submarket rent moved."])
        add("rents", score, "Rents: " + reason, "Chart + takeaway",
            {"chart_label": f"Prime rent, £/sq ft, {top['period']} · highlight = moved", "chart": {"chart": "rents"},
             "takeaway": lines, "source": f"Source {top['ref']}. Fourteen highest shown."}, t,
            so_what=(f"Only {len(movers)} of {len(d['rents'])} submarkets moved: prime rents are holding." if movers
                     else "No prime rent moved on the quarter."))
    if inv and d.get("investment"):
        gap = inv.get("vs_lta_pct")
        score = 1.0 + (min(abs(gap), 60) / 15 if gap is not None else 0) + min(abs(inv.get("change") or 0), 2)
        reason = (f"investment {abs(gap)}% {'below' if gap < 0 else 'above'} the long-term average" if gap is not None and abs(gap) >= LTA_GAP
                  else "investment close to its long-term average")
        if inv.get("change"):
            reason += f", {inv['change']:+.2f}bn on the quarter"
        thin = min((r for r in d["investment"] if r.get("vs_lta_pct") is not None), key=lambda r: r["vs_lta_pct"], default=None)
        t = f"Investment {inv['text']} in {inv['period']}"
        if gap is not None:
            t += f", {abs(gap)}% {'below' if gap < 0 else 'above'} the long-term average"
        add("capital", score, "Capital markets: " + reason, "Chart + table",
            {"chart_label": f"Investment, £bn, {d['investment'][0]['period']} vs long-term average", "chart": {"chart": "investment"},
             "table_label": "Pricing and rates", "table": {"table": "yields"},
             "source": f"London total {inv['text']} {inv['ref']}. Yields are the publisher's prime yields."}, t,
            so_what=(f"{thin['market']} is {abs(thin['vs_lta_pct'])}% below its long-term average: little fresh pricing evidence."
                     if thin and thin["vs_lta_pct"] < 0 else ""))
    if d.get("our_deals") or d.get("deals_filtered"):
        ours = d.get("our_deals") or []
        score = 0.9 + len(ours) * 0.8 + (1.0 if any(x.get("ext") for x in ours) else 0)
        reason = (f"{len(ours)} of our own deals confirmed" + (", one differs from an agency report" if any(x.get("ext") for x in ours) else "")
                  if ours else f"{d.get('deals_filtered')} internal-only record(s) kept out of this pack")
        add("deals", score, "Deals: " + reason, "Title only", {"table": {"table": "deals"}},
            f"Our deals and market deals: {len(ours)} of ours, listed apart from the market" if ours
            else "Market deals; our records are internal only and not shown",
            so_what=next((x["ext"] for x in ours if x.get("ext")), ""))
    if d.get("macro") and d.get("vacancy"):
        m = d["macro"]
        add("macro", 0.6, f"Bank Rate {m['text']} as of {m['as_of']} (context, not a change in the library)", "Hero number",
            {"hero": {"metric": "bank_rate"}, "chart_label": "Central London vacancy rate", "chart": {"chart": "vacancy"},
             "source": f"Bank of England {m['ref']}."}, f"Bank Rate at {m['text']}")
    if req and (req.get("change") or 0) > 0 and abs(req.get("change") or 0) >= 1:
        add("demand", 1.2 + min(req["change"], 4), f"Active requirements up {req['change']:+.2f}m sq ft to {req['text']}",
            "Hero number", {"hero": {"metric": "active_requirements_msqft"}, "chart_label": "Take-up, m sq ft",
                            "chart": {"chart": "take_up"}, "source": f"Source {req['ref']}."},
            f"Demand is building: requirements at {req['text']}",
            so_what="Requirements, not just take-up, are rising: the pipeline of demand is building.")
    out.sort(key=lambda s: -s["score"])
    return out


def plan_spec(d: dict, theme: str | None = None, focus: dict | None = None, rules: list[dict] | None = None) -> dict:
    """A storyline from this week's stories, without a model: the strongest candidates get a slide each."""
    from build_deck import DEFAULT_THEME, MAX_SLIDES
    theme = theme or ("data-white" if d["format"] == "ic" else DEFAULT_THEME)
    cands = stories(d, focus, rules)
    room = MAX_SLIDES - 2 - (1 if d.get("signals") else 0) - (1 if d["format"] == "ic" and d.get("evidence") else 0)
    strong = [c for c in cands if c["score"] >= 1.5][:min(room, MAX_CONTENT)] or cands[:MIN_CONTENT]
    slides = [{"key": "cover", "layout": "Cover", "eyebrow": "London office market  ·  " + d["date"], "title": d["title"],
               "why": "The headline and the four KPIs open every brief.", "notes": "Headline: " + " ".join(d["headline"]),
               "fill": {"subtitle": d["picked_by"], "headline": d["headline"], "kpis": "auto", "caveat": d["caveat"]}}]
    n = 1
    if d["format"] == "ic" and d.get("evidence"):
        n += 1
        slides.append({"key": "evidence", "layout": "Title only", "eyebrow": f"{n:02d}  ·  Market evidence",
                       "title": "Market evidence for the submarkets in focus", "why": "An IC paper always carries the evidence table.",
                       "notes": "Evidence table for the IC paper.", "fill": {"table": {"table": "evidence"}}})
    for c in strong:
        n += 1
        slides.append({"key": c["key"], "layout": c["layout"], "eyebrow": f"{n:02d}  ·  {c['key'].replace('_', ' ')}",
                       "title": c["title"], "why": c["reason"], "so_what": c.get("so_what", ""),
                       "notes": c["reason"] + ".", "fill": c["fill"]})
    if d.get("signals"):
        n += 1
        slides.append({"key": "signals", "layout": "Signal cards", "eyebrow": f"{n:02d}  ·  What changed",
                       "title": ("What supports the case, and what puts it at risk" if d["format"] == "ic"
                                 else "What changed this week and why it matters"),
                       "why": f"{len(d['signals'])} signal cards the team ranked this week.",
                       "notes": "\n".join(f"- {c['title']}: {c['detail']} {c['refs']}" for c in d["signals"]),
                       "fill": {"cards": "auto", "talk": "auto"}})
    slides.append({"key": "sources", "layout": "Sources", "eyebrow": "Sources", "title": "Sources and caveats",
                   "why": "Every figure carries [n]; this list maps each to its source.", "notes": "Sources.", "fill": {"body": "auto"}})
    return {"theme": theme, "slides": slides, "stories": [{"key": c["key"], "score": c["score"], "reason": c["reason"]} for c in cands]}
