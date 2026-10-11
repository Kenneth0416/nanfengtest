"""The team's focus: which submarkets and measures the team covers and how much Home shows.

config.yaml (team.focus) is the starting point. The team changes it by describing itself to the
Copilot (propose_setup, then apply_setup) or with one line ("more Fitzrovia, less macro").
"""
from __future__ import annotations

import re

from . import taxonomy as tx

MEASURES = {
    "rents": "Rents", "incentives": "Incentives", "vacancy": "Vacancy", "demand": "Demand",
    "supply": "Supply", "investment": "Investment & yields", "occupier_news": "Occupier news",
    "macro": "Macro", "data_quality": "Data checks",
}
BUDGETS = {"3": "3 signals (2 min)", "5": "5 signals (5 min)", "all": "Everything"}

# A lens is a focus template: it only changes ranking weights and the "for you" line on each card.
LENSES = {"team": "Whole team", "investor": "Investment", "asset_manager": "Asset management",
          "analyst": "Research", "executive": "Leadership"}
LENS_WHY = {
    "investor": {"rents": "Feeds rental growth assumptions in your underwriting.",
                 "incentives": "Changes net effective rent, so check it against your exit yield.",
                 "vacancy": "Moves letting risk on the assets you are pricing.",
                 "investment": "Comparable evidence for pricing and liquidity.",
                 "macro": "Shifts financing costs and the yields buyers will accept.",
                 "supply": "Future competition for the assets you might buy."},
    "asset_manager": {"rents": "Sets the evidence for your next rent reviews and renewals.",
                      "incentives": "Tells you how much rent-free tenants will expect.",
                      "vacancy": "Competing space for your tenants to move to.",
                      "supply": "New buildings your tenants could leave for.",
                      "demand": "How many occupiers are looking, and how hard you can push terms."},
    "executive": {"rents": "Drives portfolio income and valuations.", "vacancy": "Signals leasing risk across the fund.",
                  "investment": "Liquidity if the fund needs to sell.", "macro": "Debt costs and valuation pressure."},
    "analyst": {"data_quality": "Fix before the figure goes into the quarterly report."},
}

METRIC_MEASURE = {
    "prime_rent_psf": "rents", "rent_free_months": "incentives",
    "vacancy_pct": "vacancy", "new_refurb_vacancy_pct": "vacancy", "availability_msqft": "vacancy",
    "take_up_msqft": "demand", "active_requirements_msqft": "demand",
    "under_construction_msqft": "supply", "under_construction_spec_msqft": "supply",
    "prelet_share_under_construction_pct": "supply",
    "investment_gbp_bn": "investment", "prime_yield_pct": "investment",
}
NEWS_MEASURE = {"investment_deal": "investment", "development_pipeline": "supply", "macro_policy": "macro"}

# Longest phrases first so "rent-free" is not read as "rent".
_MEASURE_WORDS = sorted({
    "rent-free": "incentives", "rent free": "incentives", "incentives": "incentives", "incentive": "incentives",
    "rents": "rents", "rent": "rents", "vacancy": "vacancy", "availability": "vacancy",
    "demand": "demand", "take-up": "demand", "take up": "demand", "leasing": "demand", "requirements": "demand",
    "supply": "supply", "pipeline": "supply", "development": "supply", "construction": "supply",
    "investment": "investment", "yields": "investment", "yield": "investment", "capital markets": "investment",
    "occupier news": "occupier_news", "news": "occupier_news", "occupiers": "occupier_news",
    "macro": "macro", "interest rates": "macro", "bank rate": "macro", "economy": "macro",
    "data quality": "data_quality", "data checks": "data_quality", "conflicts": "data_quality",
}.items(), key=lambda kv: -len(kv[0]))

_VERBS = [("only", r"only show|show only|just show|only"),
          ("add", r"show me more|more of|more on|(?<!tell me )more(?! about)|add|include|also watch|focus on"),
          ("remove", r"less|fewer|hide|stop showing|don't show|do not show|no more|drop|remove|without")]
_VERB_RE = re.compile(r"\b(" + "|".join(p for _, p in _VERBS) + r")\b", re.I)


def measure_of(s) -> str:
    if s.kind == "data_quality":
        return "data_quality"
    if s.kind == "pipeline":
        return "supply"
    if s.kind == "macro":
        return "macro"
    if s.kind == "news":
        return NEWS_MEASURE.get(s.category, "occupier_news")
    return METRIC_MEASURE.get(s.metric, "vacancy")


def in_markets(s, markets: list[str]) -> bool:
    """A signal counts if it is about a chosen market, inside one, or London-wide context above one."""
    if not markets or not s.markets:
        return True
    for m in s.markets:
        if m in markets:
            return True
        for f in markets:
            if _is_within(m, f) or _is_within(f, m):
                return True
    return False


def _is_within(child: str, parent: str) -> bool:
    p = tx.MARKET_PARENT.get(child)
    while p:
        if p == parent:
            return True
        p = tx.MARKET_PARENT.get(p)
    return False


def defaults(config: dict, user: str = "team") -> dict:
    preset = config.get("team", {}).get("focus", {})
    return {"markets": list(preset.get("markets", [])), "measures": list(preset.get("measures", MEASURES)),
            "budget": str(preset.get("budget", "5")), "lens": preset.get("lens", "team")}


def for_you(s, lens: str) -> str:
    return LENS_WHY.get(lens, {}).get(measure_of(s), "")


def _measures_in(text: str) -> list[str]:
    found, t = [], text.lower()
    for word, key in _MEASURE_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", t):
            found.append(key)
            t = re.sub(rf"\b{re.escape(word)}\b", " ", t)
    return list(dict.fromkeys(found))


def parse_command(text: str) -> list[tuple[str, str, str]] | None:
    """'show me more Fitzrovia and less macro' -> [('add','market','Fitzrovia'), ('remove','measure','macro')].
    Returns None when the text is not a request to change the focus."""
    t = text.strip()
    if re.search(r"\b(above|below|over|under|exceeds?)\s+[£$]?\d", t, re.I):
        return None  # a threshold is a watch rule, not a focus change
    changes: list[tuple[str, str, str]] = []
    if re.search(r"\b(just|only) (the )?(top )?3\b|\btop 3\b|\bkeep it short\b", t, re.I):
        changes.append(("set", "budget", "3"))
    elif re.search(r"\b(show|give) me (everything|all signals)\b|\ball signals\b", t, re.I):
        changes.append(("set", "budget", "all"))
    parts = _VERB_RE.split(t)
    for i in range(1, len(parts) - 1, 2):
        verb = parts[i].lower()
        action = next(a for a, p in _VERBS if re.fullmatch(p, verb, re.I))
        segment = parts[i + 1]
        for m in tx.find_markets(segment):
            changes.append((action, "market", m))
        for k in _measures_in(segment):
            changes.append((action, "measure", k))
    return changes or None


def apply(focus: dict, changes: list[tuple[str, str, str]]) -> dict:
    new = {**focus, "markets": list(focus["markets"]), "measures": list(focus["measures"])}
    for action, field, value in changes:
        if field == "budget":
            new[field] = value
            continue
        key = "markets" if field == "market" else "measures"
        if action == "only":
            new[key] = [v for a, f, v in changes if a == "only" and f == field]
        elif action == "add" and value not in new[key]:
            new[key].append(value)
        elif action == "remove":
            new[key] = [v for v in new[key] if v != value]
    return new


def describe(changes) -> str:
    words = {"add": "More", "remove": "Less", "only": "Only"}
    out = []
    for action, field, value in changes:
        if field == "budget":
            out.append(f"Home shows {BUDGETS[value].lower()}")
        else:
            out.append(f"{words[action]} {MEASURES.get(value, value) if field == 'measure' else value}")
    return "; ".join(dict.fromkeys(out))


# -- agent-created setup ----------------------------------------------------
# "I run acquisitions in the City and Midtown and present to IC monthly" -> a proposed focus plus alert
# rules, shown as a card. Nothing is saved until the user presses Apply.
_JOB_CUES = [
    (r"\bmanag\w*|landlord|buildings?\b|offices? in\b|portfolio|leasing|let(ting)?s?\b|tenants? leav", ["rents", "incentives", "vacancy", "supply", "occupier_news"]),
    (r"acqui|invest|buy|fund|capital|yield|valuation|ic\b|committee", ["investment", "rents", "vacancy", "macro"]),
    (r"research|analyst|data|report(s|ing)? (on|for)|quarterly report", list(MEASURES)),
    (r"board|ceo|\bhead\b|director|leadership|exec|strategy", ["rents", "vacancy", "demand", "investment", "macro"]),
    (r"occupier|tenant|broker|agency|advis", ["demand", "rents", "incentives", "occupier_news"]),
    (r"develop|construction|refurb|scheme", ["supply", "demand", "rents"]),
]


def propose(description: str, store=None, llm=None) -> dict:
    t = description.lower()
    measures: list[str] = []
    for pattern, ms in _JOB_CUES:
        if re.search(pattern, t):
            measures += ms
    measures += _measures_in(description)
    measures = list(dict.fromkeys(measures)) or ["rents", "vacancy", "demand", "supply", "investment", "macro"]
    markets = tx.find_markets(description)
    markets = [m for m in markets if m != "London"]
    if re.search(r"\b(busy|quick|minutes?|glance|headline|short)\b|board|ceo", t):
        budget = "3"
    elif re.search(r"research|analyst|everything|all of it|detail", t):
        budget = "all"
    else:
        budget = "5"
    lens = next((k for k, p in (("asset_manager", r"\bmanag\w*|landlord|buildings?\b|offices? in\b|portfolio|tenant"),
                                ("investor", r"acqui|invest|buy|underwrit|ic\b|committee"),
                                ("analyst", r"research|analyst|data"),
                                ("executive", r"board|ceo|\bhead\b|director|leadership")) if re.search(p, t)), "team")
    reasons = [f"Measures from what you said you do: {', '.join(MEASURES[m] for m in measures)}.",
               f"Submarkets you named: {', '.join(markets)}." if markets else "You named no submarkets, so all of London.",
               f"Home shows {BUDGETS[budget].lower()}."]
    proposal = {"focus": {"markets": markets, "measures": measures, "budget": budget, "lens": lens},
                "rules": _suggest_rules(store, markets, measures) if store else [], "reasons": reasons,
                "made_by": "rules"}
    if llm is not None and getattr(llm, "available", False):
        proposal = _refine_with_llm(llm, description, proposal)
    return proposal


def _suggest_rules(store, markets, measures) -> list[dict]:
    """One alert per named submarket on the measure they care about most, set just beyond today's value."""
    from . import analytics as an
    rules = []
    for m in markets[:3]:
        for metric, op, step in (("vacancy_pct", ">", 1.0), ("prime_rent_psf", "<", -0.05)):
            if METRIC_MEASURE[metric] not in measures:
                continue
            market, _ = an.resolve_for_metric(store, m, metric)
            snap = an.snapshot(store, market, metric)
            if not snap:
                continue
            value = round(snap["value"] + step, 1) if metric == "vacancy_pct" else round(snap["value"] * (1 + step), 2)
            rules.append({"market": market, "metric": metric, "operator": op, "value": value,
                          "label": f"{market} {tx.METRICS[metric]['label'].lower()} {op} {tx.fmt_value(metric, value)}",
                          "why": f"today {tx.fmt_value(metric, snap['value'])}"})
            break
    return rules


def as_sentences(reasons) -> list[str]:
    """The model's reasons as sentences that read one after another: each starts with a capital and ends with a
    full stop, so 'keep the West End focus' and 'Leasing metrics drive ...' never run together."""
    if isinstance(reasons, str):
        reasons = [reasons]
    out = []
    for r in reasons or []:
        r = " ".join(str(r).split()).strip(" -•;,")
        if r:
            out.append(r[0].upper() + r[1:] + ("" if r[-1] in ".!?" else "."))
    return out


def _refine_with_llm(llm, description, proposal) -> dict:
    """Let the model adjust the rule-based draft; only known keys and values survive."""
    try:
        out = llm.complete_json(
            "A London office market user described their job. Adjust this draft setup to fit them. Return JSON with "
            "keys markets, measures, budget, reasons (a list of one-sentence reasons in plain English, each ending with "
            "a full stop, written for the user; do not mention JSON keys or the budget number). "
            f"Allowed markets: {list(tx.MARKET_PARENT)}. Allowed measures: {list(MEASURES)}. "
            f"budget one of {list(BUDGETS)}.\n"
            f"Job: {description}\nDraft: {proposal['focus']}")
        f = {"markets": [m for m in out.get("markets", []) if m in tx.MARKET_PARENT and m != "London"],
             "measures": [m for m in out.get("measures", []) if m in MEASURES] or proposal["focus"]["measures"],
             "budget": out.get("budget") if out.get("budget") in BUDGETS else proposal["focus"]["budget"],
             "lens": proposal["focus"]["lens"]}
        return {**proposal, "focus": f, "reasons": as_sentences(out.get("reasons")) or proposal["reasons"],
                "made_by": "llm"}
    except Exception:
        return proposal


def apply_setup(store, user: str, proposal: dict) -> dict:
    """Save the focus and add the rules as this person's own alerts (they fire in 'For you'; 'Share with team'
    on Monitor makes one the team's); returns what Undo needs."""
    store.save_focus(user, proposal["focus"])
    ids = [store.add_watch_rule(user, r["market"], r["metric"], r["operator"], r["value"], r["label"], user)
           for r in proposal.get("rules", [])]
    return {"rule_ids": ids}


def undo_setup(store, user: str, applied: dict):
    store.undo_focus(user)
    for rid in applied.get("rule_ids", []):
        store.delete_watch_rule(rid)
