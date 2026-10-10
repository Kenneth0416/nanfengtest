import re
from datetime import date

from core import analytics as an
from core import internal as I
from core import focus as focus_mod
from core import taxonomy as tx
from core.models import Evidence, Signal
from core.signals import SignalEngine
from core.summary import is_tip, team_summary
from core.skill import Tool, obj_schema

KEY_NUMBERS = [("London", "vacancy_pct"), ("London", "take_up_msqft"), ("London", "active_requirements_msqft"),
               ("London", "investment_gbp_bn"), ("West End Core", "prime_rent_psf"), ("City Core", "prime_rent_psf"),
               ("Canary Wharf", "prime_rent_psf"), ("West End", "prime_yield_pct"), ("City & Southbank", "prime_yield_pct")]
IC_METRICS = ["prime_rent_psf", "grade_a_rent_psf", "rent_free_months", "vacancy_pct", "new_refurb_vacancy_pct",
              "prime_yield_pct", "investment_gbp_bn"]


class Footnotes:
    """Numbers every source once, so each figure in the brief carries [n]."""
    def __init__(self, store=None):
        self.items: list[tuple[str, str]] = []
        self.channel: dict[tuple[str, str], str] = {}  # how each source reached the team library
        self.store = store

    def ref(self, title: str, url: str = "", source_id: str = "") -> str:
        key = (title, url or "")
        if key not in self.items:
            self.items.append(key)
        if source_id and self.store is not None and key not in self.channel:
            prov = an.source_ref(self.store, source_id).get("provenance", "")
            self.channel[key] = prov
        return f"[{self.items.index(key) + 1}]"

    def markdown(self) -> list[str]:
        return [f"[{i}] {t}" + (f" ({self.channel[(t, u)]})" if self.channel.get((t, u)) else "")
                + (f" - {u}" if u else "") for i, (t, u) in enumerate(self.items, 1)]


def _signal(d: dict) -> Signal:
    d = {k: v for k, v in d.items() if k != "added_by"}
    d["evidence"] = [Evidence(**e) for e in d.get("evidence", [])]
    return Signal(**d)


def generate_brief(ctx, args):
    """The team brief: signals people added on the Monitor page (or the top team signals if none),
    written as a board summary or an IC paper section, every figure footnoted to its source."""
    team = ctx.config.get("team", {})
    focus = ctx.store.focus(ctx.role) or focus_mod.defaults(ctx.config)
    fmt = args.get("format") or "board"
    items = ctx.store.brief_items()
    picked = bool(items)
    sigs = ([_signal(i) for i in items] if picked else SignalEngine(ctx.store, ctx.config).for_role("team"))
    # Colleagues' unconfirmed tips never lead the brief; they go at the end as market talk.
    talk = [s for s in sigs if is_tip(s)][:3]
    sigs = [s for s in sigs if not is_tip(s)][: args.get("limit", 8 if picked else 5)]
    notes = Footnotes(ctx.store)
    up = [s for s in sigs if s.tone == "positive"]
    down = [s for s in sigs if s.tone == "negative"]

    if fmt == "ic":  # market evidence for the submarkets the person asking covers
        markets = focus["markets"] or tx.TOP_MARKETS[1:]
        key = [(m, metric) for m in markets for metric in IC_METRICS]
    else:
        key = KEY_NUMBERS
    rows, seen, flagged = [], set(), []
    for wanted, metric in key:
        market, _ = an.resolve_for_metric(ctx.store, wanted, metric)
        snap = an.snapshot(ctx.store, market, metric) if (market, metric) not in seen else None
        seen.add((market, metric))
        if not snap:
            continue
        chg = ""
        if snap["change"] is not None:
            unit = tx.METRICS[metric]["unit"]
            chg = f"{snap['change']:+.2f}{'pp' if unit == '%' else ''} vs {an.period_label(snap['prev_period'])}"
        ref = an.source_ref(ctx.store, snap["source_id"])
        flag = " (flagged)" if snap["status"] == "flagged" else ""
        rows.append(f"| {market} | {tx.METRICS[metric]['label']} | {tx.fmt_value(metric, snap['value'])}{flag} "
                    f"{notes.ref(ref['title'], ref['url'], snap['source_id'])} | {an.period_label(snap['period'])} | {chg} |")
        if flag:
            flagged.append(f"{market} {tx.METRICS[metric]['label'].lower()}: {an.warning(snap)}")

    headline = " ".join(team_summary(ctx.store, sigs or SignalEngine(ctx.store, ctx.config).for_role("team"))) \
        or "No major changes this week."
    if (vac := an.snapshot(ctx.store, "London", "vacancy_pct")):
        ref = an.source_ref(ctx.store, vac["source_id"])
        headline += " " + notes.ref(ref["title"], ref["url"], vac["source_id"])
    if ctx.llm and getattr(ctx.llm, "available", False) and sigs:
        facts = headline + "\n" + "\n".join(f"- {s.title}: {s.detail}" for s in sigs)
        try:
            headline = ctx.llm.complete(
                f"Write a 3-sentence headline for a {'investment committee paper' if fmt == 'ic' else 'board'} "
                f"on the London office market. Use ONLY these facts and numbers, no others:\n{facts}",
                system="You are a CRE research analyst. Plain English, no hype, no headings or markdown.")
            lines = [line.strip() for line in headline.strip().splitlines() if line.strip()]
            prose = [line for line in lines if not line.startswith("#")]  # drop heading lines the model adds
            headline = " ".join(prose or [re.sub(r"^#+\s*", "", line) for line in lines])
        except Exception:
            pass  # keep the rule-based headline

    def bullet(s):
        arrow = {"positive": "▲", "negative": "▼"}.get(s.tone, "●")
        refs = "".join(notes.ref(e.text, e.url, e.source_id) for e in s.evidence)
        warn = f" **{s.flag}**" if s.flag else ""
        return f"- {arrow} **{s.title}**. {s.detail} {refs}{warn} _{s.why}_"

    title = "IC Paper - London Office Market Section" if fmt == "ic" else f"{team.get('name', 'Team')} - Weekly Brief"
    who = sorted({i["added_by"] for i in items if i.get("added_by")})
    md = [f"# {title}", f"_{date.today():%d %b %Y} · "
          + (f"{len(sigs)} signals chosen by {', '.join(who)}_" if picked else "this week's top signals_"),
          "", "## Headline", headline, "", "## Key numbers", "| Market | Metric | Latest | Period | Change |",
          "|---|---|---|---|---|", *rows,
          *([""] + [f"_{f}_" for f in flagged] if flagged else []), ""]
    if fmt == "ic":
        md += ["## Supports the case", *([bullet(s) for s in up] or ["- Nothing new."]), "",
               "## Risks to the case", *([bullet(s) for s in down] or ["- Nothing new."]), "",
               "## Other context", *([bullet(s) for s in sigs if s not in up and s not in down] or ["- None."])]
    else:
        md += ["## What changed and why it matters", *([bullet(s) for s in sigs] or ["- Nothing new."])]
    ours = I.for_brief(ctx.store, fmt)
    market = I.market_deals(ctx.store)
    if ours["ours"] or ours["filtered"] or market:
        md += ["", "## Our deals (Internal)" if fmt != "ic" else "## Our deals (Internal, quotable only)"]
        md += [f"- **{I.one_line(d)}**" + (f" _{d['ext']['source']} reports {d['ext']['rent']}; our record stands._"
                                            if d.get("ext") and d["ext"].get("differs") else "")
               + " [internal]" for d in ours["ours"]] or ["- None confirmed yet."]
        if ours["filtered"]:
            md.append(f"_{ours['filtered']} internal-only record(s) not included in the IC paper._")
        md += ["", "## Market deals (Uploaded agency reports)"]
        md += [f"- {m['text']} ({an.period_label(m['period'])}) {notes.ref(m['title'], m['url'], m['source_id'])}"
               for m in market] or ["- None in the library for the latest period."]
    if talk:
        md += ["", "## Market talk, not yet confirmed",
               "_Shared by colleagues; no published source confirms these yet. Do not rely on them._",
               *[f"- {s.title.removeprefix('Unverified tip: ')}. {s.detail}" for s in talk]]
    rate = ctx.store.q("SELECT * FROM macro WHERE indicator='bank_rate' ORDER BY date DESC LIMIT 1")
    if rate:
        md += ["", "## Macro", f"Bank Rate {rate[0]['value']:.2f}% (as of {rate[0]['date']}) "
               f"{notes.ref('Bank of England Bank Rate', 'https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp')}."]
    md += ["", "## Sources", *notes.markdown(),
           "", "_Figures restated from public research for this proof of concept; verify against the original before external use._"]
    text = "\n".join(md)
    return {"summary": text, "data": {"markdown": text, "signals": [s.to_dict() for s in sigs]}}


TOOLS = [Tool("generate_brief", "Write the team brief from the signals the team added (or the top team signals), "
              "as a board summary or an IC paper section, with every figure footnoted to its source.",
              obj_schema({"format": {"type": "string", "enum": ["board", "ic"]},
                          "limit": {"type": "integer"}}), generate_brief)]
