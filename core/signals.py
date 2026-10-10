"""Turns data, news and watch rules into ranked 'what changed' cards per role."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from . import analytics as an
from . import taxonomy as tx
from .models import Evidence, Signal

ROLES = ("analyst", "investor", "asset_manager", "executive")


def _w(a, i, m, e):
    return dict(zip(ROLES, (a, i, m, e)))


METRIC_WEIGHTS = {
    "prime_rent_psf": _w(.5, .9, 1.0, .6), "vacancy_pct": _w(.5, .8, .9, .7),
    "new_refurb_vacancy_pct": _w(.5, .7, .9, .4), "take_up_msqft": _w(.5, .7, .6, .8),
    "active_requirements_msqft": _w(.5, .8, .7, .8), "investment_gbp_bn": _w(.4, 1.0, .3, .8),
    "prime_yield_pct": _w(.4, 1.0, .3, .7), "rent_free_months": _w(.4, .6, 1.0, .3),
    "availability_msqft": _w(.5, .6, .7, .5), "prelet_share_under_construction_pct": _w(.4, .6, .8, .3),
    "grade_a_rent_psf": _w(.5, .9, 1.0, .6), "new_refurb_take_up_share_pct": _w(.5, .7, .9, .5),
}
NEWS_WEIGHTS = {
    "leasing_deal": _w(.5, .7, .9, .6), "investment_deal": _w(.5, 1.0, .4, .8),
    "macro_policy": _w(.4, .8, .4, 1.0), "development_pipeline": _w(.5, .7, 1.0, .5),
    "market_stats": _w(.6, .7, .6, .9), "other": _w(.3, .3, .3, .3),
}
NEWS_WHY = {
    "leasing_deal": "Large lettings set rental evidence and show which occupiers are taking space.",
    "investment_deal": "Sets fresh pricing (yield) evidence for valuations and acquisitions.",
    "macro_policy": "Rates and jobs feed directly into yields, debt costs and occupier demand.",
    "development_pipeline": "New supply competes with existing buildings for the same tenants.",
    "market_stats": "Headline market data shifts the narrative for the quarter.",
    "other": "Flagged as relevant to the London office market.",
}
WHY = {
    ("prime_rent_psf", "up"): "Prime rents are rising: supports valuations and stronger terms on new leases and renewals.",
    ("prime_rent_psf", "down"): "Prime rents are falling: pressure on valuations and lease negotiations.",
    ("vacancy_pct", "down"): "Less competing space: landlords gain negotiating power and incentives should tighten.",
    ("vacancy_pct", "up"): "More competing space: expect longer voids and bigger incentives.",
    ("new_refurb_vacancy_pct", "down"): "Grade A space is getting scarcer: flight to quality continues.",
    ("new_refurb_vacancy_pct", "up"): "More Grade A space available: top-end pricing power may ease.",
    ("grade_a_rent_psf", "up"): "Grade A rents are rising: the best space is pricing ahead of the rest of the market.",
    ("grade_a_rent_psf", "down"): "Grade A rents are easing: even the best space is under pressure.",
    ("new_refurb_take_up_share_pct", "up"): "A larger share of lettings is new or refurbished space: flight to quality.",
    ("new_refurb_take_up_share_pct", "down"): "More second-hand space is letting: the quality premium is narrowing.",
    ("take_up_msqft", "up"): "Leasing is running ahead of the long-term average.",
    ("take_up_msqft", "down"): "Leasing is running below the long-term average.",
    ("active_requirements_msqft", "up"): "A deep queue of occupiers is searching: supports take-up in coming quarters.",
    ("active_requirements_msqft", "down"): "Fewer occupiers are searching: future take-up may slow.",
    ("investment_gbp_bn", "up"): "Investment is above trend: more pricing evidence and better liquidity.",
    ("investment_gbp_bn", "down"): "Investment is well below trend: thin liquidity and little pricing evidence.",
    ("prime_yield_pct", "up"): "Yields moving out: lower capital values.",
    ("prime_yield_pct", "down"): "Yields moving in: higher capital values.",
    ("rent_free_months", "up"): "Longer rent-free periods: effective rents are weaker than headlines.",
    ("rent_free_months", "down"): "Shorter rent-free periods: effective rents are improving.",
}


def _flagged(snap: dict) -> dict:
    """Links a signal to its stored figure and carries any open flag on it."""
    return {"obs_id": snap.get("rowid"), "flag": an.warning(snap)}


def _tone(metric: str, direction: str) -> str:
    good = tx.METRICS.get(metric, {}).get("good_when")
    if direction == "flat" or not good:
        return "neutral"
    return "positive" if direction == good else "negative"


class SignalEngine:
    def __init__(self, store, config: dict, today: date | None = None):
        self.store = store
        self.cfg = config.get("signals", {})
        self.today = today or date.today()

    # -- public -------------------------------------------------------------
    def all_signals(self) -> list[Signal]:
        out = []
        for detector in (self.metric_moves, self.demand_and_liquidity, self.flight_to_quality, self.news,
                         self.pipeline, self.macro, self.source_conflicts):
            out += detector()
        return out

    def for_role(self, role: str, watched_markets: list[str] | None = None, limit: int | None = None) -> list[Signal]:
        hidden = self.store.hidden_signals(role)
        liked = self.store.liked_signals(role)
        sigs = self.all_signals() + self.watch_alerts("team")  # alerts are shared by the team
        watched = set(watched_markets or [])
        scored = []
        for s in sigs:
            if s.id in hidden:
                continue
            # The whole team shares one view: average the per-lens weights (investment, asset
            # management, research, leadership) so no single job dominates the feed.
            w = (s.roles.get(role) or (sum(s.roles.values()) / len(s.roles) if s.roles else 0.3)
                 if role == "team" else s.roles.get(role, 0.3))
            score = s.severity * w * self._recency(s) * (1 + s.hot / 100)  # hot news rises
            if watched and any(m in watched or tx.top_market(m) in watched for m in s.markets):
                score *= 1.3
            if s.id in liked:
                score *= 1.2
            scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        ranked = [s for _, s in scored]
        return ranked[:limit] if limit else ranked

    def for_focus(self, user: str, focus: dict) -> list[Signal]:
        """A person's view: rank with their lens, keep their measures and submarkets, drop what they hid,
        cap at their depth."""
        from .focus import measure_of, in_markets
        hidden = self.store.hidden_signals(user)
        ranked = [s for s in self.for_role(focus.get("lens") or "team", focus.get("markets") or [])
                  if s.id not in hidden]
        keep = [s for s in ranked if (s.kind == "alert" or measure_of(s) in focus.get("measures", []))
                and in_markets(s, focus.get("markets") or [])]
        budget = focus.get("budget", "5")
        return keep if budget == "all" else keep[: int(budget)]

    def _recency(self, s: Signal) -> float:
        """Older news and data rank lower: full weight inside 120 days, then fading."""
        if s.kind not in ("news", "metric_move", "vs_long_term"):
            return 1.0
        try:
            when = an.quarter_end(s.as_of) if "Q" in s.as_of else datetime.strptime(s.as_of[:10], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            return 1.0
        age = (self.today - when).days
        return 1.0 if age <= 120 else max(0.4, 1.0 - (age - 120) / 400)

    # -- detectors ----------------------------------------------------------
    def metric_moves(self) -> list[Signal]:
        latest = an.latest_period(self.store)
        out = []
        rules = {"vacancy_pct": 0.4, "new_refurb_vacancy_pct": 0.5, "prime_yield_pct": 0.1, "rent_free_months": 1.5}
        for metric in ["prime_rent_psf", "grade_a_rent_psf", "vacancy_pct", "new_refurb_vacancy_pct", "prime_yield_pct",
                       "rent_free_months"]:
            for market in tx.MARKET_PARENT:
                snap = an.snapshot(self.store, market, metric)
                if not snap or snap["period"] != latest or snap["prev_value"] is None:
                    continue
                is_top = market in tx.TOP_MARKETS
                change = snap["change"]
                if metric == "prime_rent_psf":
                    pct = change / snap["prev_value"] * 100 if snap["prev_value"] else 0
                    if abs(pct) < 0.1:
                        continue
                    sev = 3 if abs(pct) >= 5 else 2 if abs(pct) >= 2 else 1
                    mag = f"{pct:+.1f}%"
                else:
                    if abs(change) < rules[metric] or (not is_top and metric != "prime_rent_psf" and abs(change) < 1.0):
                        continue
                    sev = 3 if abs(change) >= 1.0 else 2 if abs(change) >= 0.6 else 1
                    mag = f"{change:+.1f}{'pp' if tx.METRICS[metric]['unit'] == '%' else ' months'}"
                direction = "up" if change > 0 else "down"
                label = tx.METRICS[metric]["label"]
                detail = (f"{label} in {market}: {tx.fmt_value(metric, snap['value'])} in "
                          f"{an.period_label(snap['period'])}, from {tx.fmt_value(metric, snap['prev_value'])} "
                          f"in {an.period_label(snap['prev_period'])} ({mag}).")
                if snap["lta"] is not None:
                    detail += f" Long-term average: {tx.fmt_value(metric, snap['lta'])}."
                series = an.series(self.store, market, metric)
                first = series[0] if len(series) > 2 else None
                context = (f"{'up' if snap['value'] > first['value'] else 'down'} from "
                           f"{tx.fmt_value(metric, first['value'])} in {an.period_label(first['period'])}"
                           if first and first["value"] != snap["value"] else
                           (f"long-term average {tx.fmt_value(metric, snap['lta'])}" if snap["lta"] is not None else ""))
                ref = an.source_ref(self.store, snap["source_id"])
                weights = dict(METRIC_WEIGHTS.get(metric, _w(.5, .5, .5, .5)))
                if not is_top:
                    weights = {k: v * (0.5 if k == "executive" else 0.85) for k, v in weights.items()}
                if market == "London":
                    sev = min(3, sev + 1)   # London-wide headline numbers matter to everyone
                out.append(Signal(
                    kind="metric_move", title=f"{market} {label.lower()} {'up' if direction == 'up' else 'down'} {mag}",
                    detail=detail, why=WHY.get((metric, direction), ""), severity=sev, direction=direction,
                    tone=_tone(metric, direction), markets=[market], metric=metric, roles=weights, as_of=snap["period"],
                    before=tx.fmt_value(metric, snap["prev_value"]), after=tx.fmt_value(metric, snap["value"]),
                    change=f"{mag} QoQ", context=context,
                    evidence=[Evidence(f"{ref['title']}", snap["source_id"], ref["url"])], **_flagged(snap)))
        return out

    def demand_and_liquidity(self) -> list[Signal]:
        """Latest take-up, requirements and investment against long-term averages."""
        latest = an.latest_period(self.store)
        out = []
        for metric, lo, hi in [("take_up_msqft", 0.75, 1.25), ("active_requirements_msqft", 0.6, 1.5),
                               ("investment_gbp_bn", 0.5, 1.5)]:
            for market in tx.TOP_MARKETS:
                snap = an.snapshot(self.store, market, metric)
                if not snap or snap["period"] != latest or not snap["lta"]:
                    continue
                ratio = snap["value"] / snap["lta"]
                if lo < ratio < hi:
                    continue
                direction = "up" if ratio >= hi else "down"
                sev = 3 if (ratio >= hi * 1.4 or ratio <= lo * 0.6) else 2
                label = tx.METRICS[metric]["label"]
                pct = (ratio - 1) * 100
                ref = an.source_ref(self.store, snap["source_id"])
                out.append(Signal(
                    kind="vs_long_term", title=f"{market} {label.lower()} {pct:+.0f}% vs long-term average",
                    detail=(f"{label} in {market} was {tx.fmt_value(metric, snap['value'])} in "
                            f"{an.period_label(snap['period'])} against a long-term average of "
                            f"{tx.fmt_value(metric, snap['lta'])}."),
                    why=WHY.get((metric, direction), ""), severity=sev, direction=direction,
                    tone=_tone(metric, direction), markets=[market], metric=metric, roles=METRIC_WEIGHTS[metric],
                    as_of=snap["period"], evidence=[Evidence(ref["title"], snap["source_id"], ref["url"])],
                    before=tx.fmt_value(metric, snap["prev_value"]) if snap["prev_value"] is not None else "",
                    after=tx.fmt_value(metric, snap["value"]), change=f"{pct:+.0f}% vs long-term average",
                    context=f"long-term average {tx.fmt_value(metric, snap['lta'])}", **_flagged(snap)))
        return out

    def flight_to_quality(self) -> list[Signal]:
        """Demand driver: Grade A (new/refurbished) vacancy against overall vacancy in each submarket. A gap of
        a point or more means the best space is letting first; a widening gap means the preference is growing."""
        latest = an.latest_period(self.store)
        out = []
        for market in tx.MARKET_PARENT:
            ga, allv = an.snapshot(self.store, market, "new_refurb_vacancy_pct"), an.snapshot(self.store, market, "vacancy_pct")
            if not ga or not allv or ga["period"] != latest or allv["period"] != latest:
                continue
            gap = allv["value"] - ga["value"]
            prev_gap = (allv["prev_value"] - ga["prev_value"]) if ga["prev_value"] is not None and allv["prev_value"] is not None else None
            widening = prev_gap is not None and gap - prev_gap >= 0.3
            # the three big markets always; a submarket only when the gap is wide or growing, so Monitor is not flooded
            if gap < 1.0 or (market not in tx.TOP_MARKETS and not (widening or gap >= 3.0)):
                continue
            ref = an.source_ref(self.store, allv["source_id"])
            out.append(Signal(
                kind="flight_to_quality",
                title=f"{market}: Grade A vacancy {ga['value']:.1f}% against {allv['value']:.1f}% overall"
                      + (", gap widening" if widening else ""),
                detail=(f"New and refurbished space in {market} is {ga['value']:.1f}% vacant against {allv['value']:.1f}% for "
                        f"all space in {an.period_label(latest)}, a gap of {gap:.1f}pp"
                        + (f" (from {prev_gap:.1f}pp the quarter before)" if prev_gap is not None else "") + "."),
                why="Occupiers are concentrating on the best space: Grade A buildings let first while second-hand "
                    "space waits. Supports Grade A rents and the case for refurbishment; raises the risk on older stock.",
                severity=3 if (widening and gap >= 2) else 2 if (widening or gap >= 2) else 1,
                direction="up" if widening else "flat", tone="positive", markets=[market], themes=["flight_to_quality"],
                metric="new_refurb_vacancy_pct", roles=_w(.5, .8, .9, .6), as_of=latest,
                evidence=[Evidence(ref["title"], allv["source_id"], ref["url"])],
                before=f"{prev_gap:.1f}pp gap" if prev_gap is not None else "", after=f"{gap:.1f}pp gap",
                change="Grade A letting ahead of the rest", context=f"overall {allv['value']:.1f}%, Grade A {ga['value']:.1f}%",
                **_flagged(allv)))
        out.sort(key=lambda s: (-s.severity, -float(s.after.split("pp")[0])))
        return out[:5]

    def news(self) -> list[Signal]:
        window = self.cfg.get("news_window_days", 180)
        min_imp = self.cfg.get("news_min_importance", 4)
        out = []
        for n in self.store.news():
            try:
                age = (self.today - datetime.strptime(n.published, "%Y-%m-%d").date()).days
            except ValueError:
                age = 0
            # A story a colleague shared always shows: someone on the team thought it mattered.
            if (n.importance < min_imp and not n.shared_by and n.hot < 60) or age > window:
                continue
            credit = ""
            if n.shared_by:
                credit = " Shared by " + ", ".join(f"{s['who']} ({s['how'].lower()})" for s in n.shared_by) + "."
            if n.also_reported:
                credit += " Also reported by " + ", ".join(r["source"] for r in n.also_reported) + "."
            # Same rule as the hotness score: a colleague's words with no link and no outlet carrying it.
            unverified = bool(n.shared_by) and not n.url and not n.also_reported
            ev = [Evidence(f"{n.source} ({n.published})", "", n.url)] if not unverified else []
            ev += [Evidence(f"{s['who']}, {s['how'].lower()} ({s['when'][:10]})", "", s.get("url", ""))
                   for s in n.shared_by]
            out.append(Signal(
                kind="news", title=("Unverified tip: " if unverified else "") + n.title,
                detail=(n.body if n.body != n.title else "") + credit,
                why=NEWS_WHY.get(n.category, ""),
                severity=3 if n.importance >= 5 or n.hot >= 70 else 2, tone=n.sentiment, markets=n.markets,
                themes=n.themes, category=n.category,
                roles=NEWS_WEIGHTS.get(n.category, NEWS_WEIGHTS["other"]), as_of=n.published,
                evidence=ev, hot=n.hot, why_hot=n.why_hot, shared_by=n.shared_by, discovered=n.discovered))
        return out

    def pipeline(self) -> list[Signal]:
        horizon = self.cfg.get("pipeline_horizon_quarters", 6)
        today_q = f"{self.today.year}Q{(self.today.month - 1) // 3 + 1}"
        y, q = self.today.year, (self.today.month - 1) // 3 + 1
        q += horizon
        y += (q - 1) // 4
        end_q = f"{y}Q{(q - 1) % 4 + 1}"
        out = []
        for p in self.store.q("SELECT * FROM pipeline WHERE status='speculative'"):
            if not (today_q <= p["expected_completion"] <= end_q):
                continue
            ref = an.source_ref(self.store, p["source_id"])
            out.append(Signal(
                kind="pipeline", title=f"{int(p['size_sqft']):,} sq ft speculative scheme due {an.period_label(p['expected_completion'])} in {p['submarket']}",
                detail=f"{p['scheme']} ({int(p['size_sqft']):,} sq ft) is under construction without a pre-let and "
                       f"is expected to complete in {an.period_label(p['expected_completion'])}.",
                why="New speculative space will compete for tenants with existing buildings nearby.",
                severity=2 if p["size_sqft"] < 300_000 else 3, direction="up", tone="negative",
                markets=[p["submarket"]], roles=_w(.4, .6, 1.0, .4), as_of=p["expected_completion"],
                after=f"{int(p['size_sqft']) / 1000:,.0f}k sq ft", change="speculative, due " + an.period_label(p["expected_completion"]),
                context="none of it pre-let", evidence=[Evidence(ref["title"], p["source_id"], ref["url"])]))
        return out

    def macro(self) -> list[Signal]:
        rows = self.store.q("SELECT * FROM macro WHERE indicator='bank_rate' ORDER BY date")
        if not rows:
            return []
        last = rows[-1]
        changes = [r for i, r in enumerate(rows) if i == 0 or r["value"] != rows[i - 1]["value"]]
        last_change = changes[-1]
        prev_level = changes[-2]["value"] if len(changes) > 1 else None
        if last_change is last or last_change["date"] == last["date"]:
            verb = "cut to" if prev_level and last["value"] < prev_level else "raised to"
            title = f"Bank of England {verb} {last['value']:.2f}%"
        else:
            title = f"Bank Rate on hold at {last['value']:.2f}% since {last_change['date'][:7]}"
        cuts = sum(1 for a, b in zip(changes, changes[1:]) if b["value"] < a["value"])
        return [Signal(
            kind="macro", title=title,
            detail=f"Latest reading {last['date']}: {last['value']:.2f}%. {cuts} cuts since {changes[0]['date'][:7]} "
                   f"(from {changes[0]['value']:.2f}%). {last.get('note') or ''}".strip(),
            why="Bank Rate drives debt costs and the yields investors require on offices.",
            severity=2, tone="neutral", markets=["London"], themes=["interest_rates"],
            roles=_w(.4, .9, .4, 1.0), as_of=last["date"],
            before=f"{prev_level:.2f}%" if prev_level is not None else "", after=f"{last['value']:.2f}%",
            change=f"{cuts} cut{'s' if cuts != 1 else ''} since {changes[0]['date'][:7]}", context=f"as of {last['date']}",
            evidence=[Evidence("Bank of England Bank Rate", "BOE_IADB", "https://www.bankofengland.co.uk/boeapps/database/")])]

    def source_conflicts(self) -> list[Signal]:
        """Same period/market/metric reported with different values, plus series
        whose definition changed between editions."""
        rows = self.store.q("SELECT * FROM observations WHERE status != 'rejected'")
        groups = defaultdict(list)
        for r in rows:
            groups[(r["period"], r["market"], r["metric"])].append(r)
        sources = self.store.sources()
        out = []
        for (period, market, metric), obs in groups.items():
            values = {o["value"] for o in obs}
            if len(values) < 2:
                continue
            label = tx.METRICS[metric]["label"]
            parts = [f"{tx.fmt_value(metric, o['value'])} ({sources.get(o['source_id'], {}).get('publisher', o['source_id'])}"
                     f"{': ' + o['note'] if o['note'] else ''})" for o in obs]
            notes = [sources.get(o["source_id"], {}).get("definition_note", "") for o in obs]
            out.append(Signal(
                kind="data_quality", title=f"Figures disagree: {market} {label.lower()}, {an.period_label(period)}",
                detail="Reported values: " + "; ".join(parts) + ".",
                why="Check definitions before quoting either number. " + " ".join(n for n in set(notes) if n),
                severity=2, tone="neutral", markets=[market], metric=metric, roles=_w(1.0, .3, .2, .1), as_of=period,
                evidence=[Evidence(sources.get(o["source_id"], {}).get("title", o["source_id"]), o["source_id"],
                                   sources.get(o["source_id"], {}).get("url", "")) for o in obs]))
        for old, new in tx.DEFINITION_SUCCESSORS.items():
            old_p = self.store.q("SELECT MAX(period) p FROM observations WHERE metric=?", (old,))[0]["p"]
            new_p = self.store.q("SELECT MIN(period) p FROM observations WHERE metric=?", (new,))[0]["p"]
            if old_p and new_p and new_p > old_p:
                out.append(Signal(
                    kind="data_quality", title=f"Definition change: {tx.METRICS[old]['label']} becomes {tx.METRICS[new]['label'].lower()}",
                    detail=f"Up to {an.period_label(old_p)} the publisher reported total space under construction; from "
                           f"{an.period_label(new_p)} it reports speculative space only. The two series are kept apart.",
                    why="Comparing across the break would show a false fall in the development pipeline.",
                    severity=1, roles=_w(.9, .3, .2, .1), markets=["London"], metric=new, as_of=new_p))
        return out

    def watch_alerts(self, role: str) -> list[Signal]:
        out = []
        for rule in self.store.watch_rules(role):
            market, note = an.resolve_for_metric(self.store, rule["market"], rule["metric"])
            snap = an.snapshot(self.store, market, rule["metric"])
            if not snap:
                continue
            v, t = snap["value"], rule["value"]
            hit = {">": v > t, "<": v < t, ">=": v >= t, "<=": v <= t}.get(rule["op"], False)
            if not hit:
                continue
            ref = an.source_ref(self.store, snap["source_id"])
            out.append(Signal(
                kind="alert", title=f"Alert: {rule['label']}",
                detail=f"{tx.METRICS[rule['metric']]['label']} in {market} is {tx.fmt_value(rule['metric'], v)} "
                       f"({an.period_label(snap['period'])}), which meets your rule ({rule['op']} "
                       f"{tx.fmt_value(rule['metric'], t)}). {note}".strip(),
                why="You asked to be told when this threshold is crossed.", severity=3, markets=[market], metric=rule["metric"],
                roles={role: 1.5}, as_of=snap["period"],
                after=tx.fmt_value(rule["metric"], v), change=f"your rule: {rule['op']} {tx.fmt_value(rule['metric'], t)}",
                context=an.period_label(snap["period"]),
                evidence=[Evidence(ref["title"], snap["source_id"], ref["url"])], **_flagged(snap)))
        return out
