import re

from core import taxonomy as tx
from core import focus as focus_mod
from core.signals import SignalEngine
from core.skill import Tool, obj_schema
from skills._common import sources_for, METRIC_ENUM, market_arg, metric_arg


def _focus(ctx, user):
    return ctx.store.focus(user) or focus_mod.defaults(ctx.config)


def update_focus(ctx, args):
    """Change what the user's Home page shows, from their own words."""
    changes = focus_mod.parse_command(args["request"])
    if not changes:
        return {"summary": "I couldn't tell which submarkets or measures to change. Try e.g. "
                           "'more Fitzrovia, less macro' or 'only rents and vacancy'.", "data": None}
    new = focus_mod.apply(_focus(ctx, ctx.role), changes)
    ctx.store.save_focus(ctx.role, new)
    return {"summary": f"Updated your focus: {focus_mod.describe(changes)}. Your 'For you' view now follows it "
                       "(Undo is available in the app).", "data": new}


def propose_setup(ctx, args):
    """Draft a personal setup from a one-sentence job description. Saves nothing."""
    p = focus_mod.propose(args["description"], ctx.store, ctx.llm)
    ctx.store.set_pending_setup(ctx.role, p)
    f = p["focus"]
    lines = ["**Proposed setup** (nothing is saved until you apply it)",
             f"- Submarkets: {', '.join(f['markets']) or 'all of London'}",
             f"- Measures: {', '.join(focus_mod.MEASURES[m] for m in f['measures'])}",
             f"- Home: {focus_mod.BUDGETS[f['budget']]} · Brief: {focus_mod.BRIEF_FORMATS[f['brief_format']]}",
             *[f"- Alert: {r['label']} ({r['why']})" for r in p["rules"]]]
    return {"summary": "\n".join(lines), "data": p}


def apply_setup(ctx, args):
    """Apply the setup proposed last; only call after the user confirms."""
    p = ctx.store.pending_setup(ctx.role)
    if not p:
        return {"summary": "There is no proposed setup to apply. Describe your job first.", "data": None}
    applied = focus_mod.apply_setup(ctx.store, ctx.role, p)
    ctx.store.set_pending_setup(ctx.role, None)
    return {"summary": f"Applied: your 'For you' view now follows this setup, and {len(applied['rule_ids'])} "
                       "alert(s) were added to the team watchlist.", "data": applied}


def get_signals(ctx, args):
    engine = SignalEngine(ctx.store, ctx.config)
    scope = args.get("scope", "team")
    if args.get("kind") or scope == "team":
        sigs = engine.for_role("team")
    else:  # the asking person's own focus
        sigs = engine.for_focus(ctx.role, {**_focus(ctx, ctx.role), "budget": "all"})
    if args.get("kind"):
        sigs = [s for s in sigs if s.kind == args["kind"]]
    sigs = sigs[: args.get("limit", 6)]
    lines = [f"**Top signals {'for the whole team' if scope == 'team' else 'for you'}**"]
    for s in sigs:
        arrow = {"up": "▲", "down": "▼"}.get(s.direction, "•")
        warn = f" **{s.flag}**" if s.flag else ""
        lines.append(f"- {arrow} **{s.title}**: {s.detail}{warn} _Why it matters: {s.why}_")
    return {"summary": "\n".join(lines), "data": [s.to_dict() for s in sigs],
            "sources": sources_for(ctx.store, [e.source_id for s in sigs for e in s.evidence])
            + [{"title": e.text, "url": e.url} for s in sigs for e in s.evidence if e.url and not e.source_id]}


def add_watch_rule(ctx, args):
    market, _ = market_arg(args["market"])
    metric = metric_arg(args["metric"])
    op = args.get("operator", ">")
    value = float(args["value"])
    label = args.get("label") or f"{market} {tx.METRICS[metric]['label'].lower()} {op} {tx.fmt_value(metric, value)}"
    team = bool(args.get("share_with_team"))
    rid = ctx.store.add_watch_rule("team" if team else ctx.role, market, metric, op, value, label, ctx.role)
    return {"summary": (f"Team alert #{rid} saved: {label}. It is checked every time data refreshes and shows for "
                        "the whole team." if team else
                        f"Alert #{rid} saved for you: {label}. It is checked every time data refreshes and fires in "
                        "your 'For you' view; 'Share with team' on Monitor gives it to everyone."),
            "data": {"id": rid, "market": market, "metric": metric, "op": op, "value": value}}


def parse_rule(text: str) -> dict | None:
    """'tell me when Canary Wharf vacancy goes above 10%' -> rule fields."""
    markets = tx.find_markets(text, use_postcodes=False)
    metrics = tx.find_metrics(text)
    num = re.search(r"(-?[\d.]+)\s*(%|psf|£)?", text.replace("£", ""))
    if not (markets and metrics and num):
        return None
    low = text.lower()
    op = "<" if any(w in low for w in ["below", "under", "less than", "drops", "falls", "lower than", "<"]) else ">"
    return {"market": markets[0], "metric": metrics[0], "operator": op, "value": float(num.group(1))}


def list_watch_rules(ctx, args):
    rules = ctx.store.watch_rules("team")
    if not rules:
        return {"summary": "No team alerts yet.", "data": []}
    return {"summary": "**Team alerts**\n" + "\n".join(f"- #{r['id']} {r['label']}" + (f" (added by {r['author']})"
            if r.get("author") else "") for r in rules), "data": rules}


TOOLS = [
    Tool("get_signals", "Ranked 'what changed' cards for the whole team (scope team) or for the person asking, "
         "using their own focus (scope me).",
         obj_schema({"scope": {"type": "string", "enum": ["team", "me"]},
                     "kind": {"type": "string", "enum": ["metric_move", "vs_long_term", "news", "pipeline", "macro", "data_quality", "alert"]},
                     "limit": {"type": "integer"}}), get_signals),
    Tool("add_watch_rule", "Save an alert that fires when a metric crosses a threshold in a market. It belongs to "
         "the asking person unless they ask for the whole team (share_with_team).",
         obj_schema({"market": {"type": "string"}, "metric": {"type": "string", "enum": METRIC_ENUM},
                     "operator": {"type": "string", "enum": [">", "<", ">=", "<="]}, "value": {"type": "number"},
                     "label": {"type": "string"}, "share_with_team": {"type": "boolean"}},
                    ["market", "metric", "operator", "value"]), add_watch_rule),
    Tool("update_focus", "Change which submarkets and measures the asking person's For you view covers, or how many "
         "signals they see, from a request such as 'more Fitzrovia and less macro' or 'only the top 3'.",
         obj_schema({"request": {"type": "string"}}, ["request"]), update_focus),
    Tool("propose_setup", "Draft the asking person's focus (submarkets, measures, how much 'For you' shows, alert "
         "rules) from the user's one-sentence description of their job. Saves nothing; show it and ask to apply.",
         obj_schema({"description": {"type": "string"}}, ["description"]), propose_setup),
    Tool("apply_setup", "Apply the setup proposed by propose_setup. Call only after the user says yes.",
         obj_schema({}), apply_setup),
    Tool("list_watch_rules", "List the current user's watch rules.", obj_schema({}), list_watch_rules),
]
