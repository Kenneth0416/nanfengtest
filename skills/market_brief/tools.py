import hashlib
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


def team_focus(config) -> dict:
    """The one view every team output uses (brief text, Word/PDF and slides): the team's default focus, never
    the reader's own, so the brief lists the same submarkets wherever it is read."""
    focus = focus_mod.defaults(config)
    return {**focus, "markets": list(focus.get("markets") or tx.TOP_MARKETS[1:])}


def plain_words(text: str) -> str:
    """Model phrasing a reader would trip over, put plainly: 'two unpre-let speculative schemes' becomes
    'two speculative schemes with no pre-lets'."""
    return re.sub(r"\bun-?pre-?let(?:ted)?\s+((?:speculative\s+)?(?:schemes?|buildings?|offices?|space))",
                  lambda m: f"{m.group(1)} with no pre-let{'s' if m.group(1).endswith('s') else ''}", text, flags=re.I)


def nice_date(iso: str) -> str:
    """2026-06-18 as 18 Jun 2026, the way dates read everywhere else in the brief."""
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d %b %Y").lstrip("0")
    except ValueError:
        return str(iso)


def _signal(d: dict) -> Signal:
    d = {k: v for k, v in d.items() if k != "added_by"}
    d["evidence"] = [Evidence(**e) for e in d.get("evidence", [])]
    return Signal(**d)


def _figure(ctx, notes, market, metric):
    """(value with its [n], short change, period label, flagged warning) for one figure, or None."""
    snap = an.snapshot(ctx.store, market, metric)
    if not snap:
        return None
    unit = tx.METRICS[metric]["unit"]
    chg = f"{snap['change']:+.2f}{'pp' if unit == '%' else ''}" if snap["change"] is not None else ""
    ref = an.source_ref(ctx.store, snap["source_id"])
    flag = " (flagged)" if snap["status"] == "flagged" else ""
    value = f"{tx.fmt_value(metric, snap['value'])}{flag} {notes.ref(ref['title'], ref['url'], snap['source_id'])}"
    warn = f"{market} {tx.METRICS[metric]['label'].lower()}: {an.warning(snap)}" if flag else ""
    return {"value": value, "change": chg, "period": an.period_label(snap["period"]),
            "prev": an.period_label(snap["prev_period"]) if snap["change"] is not None else "", "warn": warn}


def generate_brief(ctx, args):
    """The team brief, one document for the board and the investment committee alike: the signals people added
    on the Monitor page (or the top team signals if none), London's key numbers, the evidence table for the
    team's submarkets, what supports the case and what puts it at risk, quotable deals, every figure footnoted."""
    team = ctx.config.get("team", {})
    focus = team_focus(ctx.config)  # one team brief for everyone: the team's view, never the reader's own focus
    items = ctx.store.brief_items()
    picked = bool(items)
    sigs = ([_signal(i) for i in items] if picked else SignalEngine(ctx.store, ctx.config).for_role("team"))
    # Colleagues' unconfirmed tips never lead the brief; they go at the end as market talk.
    talk = [s for s in sigs if is_tip(s)][:3]
    sigs = [s for s in sigs if not is_tip(s)][: args.get("limit", 8 if picked else 5)]
    notes = Footnotes(ctx.store)
    up = [s for s in sigs if s.tone == "positive"]
    down = [s for s in sigs if s.tone == "negative"]
    other = [s for s in sigs if s not in up and s not in down]

    rows, seen, flagged = [], set(), []
    for wanted, metric in KEY_NUMBERS:
        market, _ = an.resolve_for_metric(ctx.store, wanted, metric)
        fig = _figure(ctx, notes, market, metric) if (market, metric) not in seen else None
        seen.add((market, metric))
        if not fig:
            continue
        chg = f"{fig['change']} vs {fig['prev']}" if fig["change"] else ""
        rows.append(f"| {market} | {tx.METRICS[metric]['label']} | {fig['value']} | {fig['period']} | {chg} |")
        flagged += [fig["warn"]] if fig["warn"] else []

    # The evidence table: each of the team's submarkets on the measures an investment case rests on.
    markets = focus["markets"]
    evidence, periods = [], set()
    for metric in IC_METRICS:
        cells = []
        for m in markets:
            market, _ = an.resolve_for_metric(ctx.store, m, metric)
            fig = _figure(ctx, notes, market, metric)
            if fig:
                periods.add(fig["period"])
                flagged += [fig["warn"]] if fig["warn"] and fig["warn"] not in flagged else []
            cells.append(f"{fig['value']}" + (f" ({fig['change']})" if fig["change"] else "") if fig else "n/a")
        if any(c != "n/a" for c in cells):
            evidence.append(f"| {tx.METRICS[metric]['label']} | " + " | ".join(cells) + " |")

    headline = " ".join(team_summary(ctx.store, sigs or SignalEngine(ctx.store, ctx.config).for_role("team"))) \
        or "No major changes this week."
    if (vac := an.snapshot(ctx.store, "London", "vacancy_pct")):
        ref = an.source_ref(ctx.store, vac["source_id"])
        headline += " " + notes.ref(ref["title"], ref["url"], vac["source_id"])
    if ctx.llm and getattr(ctx.llm, "available", False) and sigs:
        facts = headline + "\n" + "\n".join(f"- {s.title}: {s.detail}" for s in sigs)
        prompt = ("Write a 3-sentence headline for the team's weekly brief on the London office market, read by the "
                  f"board and the investment committee. Use ONLY these facts and numbers, no others:\n{facts}")
        system = ("You are a CRE research analyst. Plain English, no hype, no headings or markdown. "
                  "No coined words: write 'speculative schemes with no pre-lets', never 'unpre-let'.")
        # the same facts get the same headline: new code around the brief never asks the model again
        key = hashlib.sha1(f"{getattr(ctx.llm, 'model', '')}|{system}|{prompt}".encode()).hexdigest()[:20]
        hit = ctx.store.cached("headline", key) if not args.get("fresh") else None
        if hit and hit.get("data"):
            headline = hit["data"]
        else:
            try:
                raw = ctx.llm.complete(prompt, system=system)
                lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
                prose = [line for line in lines if not line.startswith("#")]  # drop heading lines the model adds
                headline = plain_words(" ".join(prose or [re.sub(r"^#+\s*", "", line) for line in lines]))
                ctx.store.save_cached("headline", key, headline)
            except Exception:
                pass  # keep the rule-based headline

    def bullet(s):
        arrow = {"positive": "▲", "negative": "▼"}.get(s.tone, "●")
        refs = "".join(notes.ref(e.text, e.url, e.source_id) for e in s.evidence)
        warn = f" **{s.flag}**" if s.flag else ""
        return f"- {arrow} **{s.title}**. {s.detail} {refs}{warn} _{s.why}_"

    title = f"{team.get('name', 'Team')} - Weekly Brief"
    who = sorted({i["added_by"] for i in items if i.get("added_by")})
    md = [f"# {title}", f"_{date.today():%d %b %Y} · "
          + (f"{len(sigs)} signals chosen by {', '.join(who)}_" if picked else "this week's top signals_"),
          "", "## Headline", headline, "", "## Key numbers", "| Market | Metric | Latest | Period | Change |",
          "|---|---|---|---|---|", *rows, ""]
    if evidence:
        when = ", ".join(sorted(periods, key=lambda p: (p[-4:], p)))  # "Q1 2026", by year then quarter
        md += ["## Submarket evidence", "| Metric | " + " | ".join(markets) + " |",
               "|---|" + "---|" * len(markets), *evidence,
               f"_Latest figure for each submarket ({when}); change against the previous quarter in brackets._", ""]
    md += [f"_{f}_" for f in flagged] + ([""] if flagged else [])
    md += ["## What changed and why it matters"]
    if not sigs:
        md += ["- Nothing new."]
    for name, group in (("Supports the case", up), ("Risks to the case", down), ("Other context", other)):
        if group:
            md += ["", f"### {name}", *[bullet(s) for s in group]]
    ours = I.for_brief(ctx.store)
    market = I.market_deals(ctx.store)
    if ours["ours"] or ours["filtered"] or market:
        md += ["", "## Our deals (Internal, quotable only)"]
        md += [f"- **{I.one_line(d)}**" + (f" _{d['ext']['source']} reports {d['ext']['rent']}; our record stands._"
                                            if d.get("ext") and d["ext"].get("differs") else "")
               + " [internal]" for d in ours["ours"]] or ["- None marked quotable yet."]
        if ours["filtered"]:
            md.append(f"_{ours['filtered']} internal-only record(s) not included._")
        md += ["", "## Market deals (Uploaded agency reports)"]
        md += [f"- {m['text']} ({an.period_label(m['period'])}) {notes.ref(m['title'], m['url'], m['source_id'])}"
               for m in market] or ["- None in the library for the latest period."]
    if talk:
        md += ["", "## Market talk, not yet confirmed",
               "_Shared by colleagues; no published source confirms these yet. Do not rely on them._",
               *[f"- {s.title.removeprefix('Unverified tip: ')}. {s.detail}" for s in talk]]
    rate = ctx.store.q("SELECT * FROM macro WHERE indicator='bank_rate' ORDER BY date DESC LIMIT 1")
    if rate:
        md += ["", "## Macro", f"Bank Rate {rate[0]['value']:.2f}% (as of {nice_date(rate[0]['date'])}) "
               f"{notes.ref('Bank of England Bank Rate', 'https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp')}."]
    md += ["", "## Sources", *notes.markdown(),
           "", "_Figures restated from public research for this proof of concept; verify against the original before external use._"]
    text = "\n".join(md)
    return {"summary": text, "data": {"markdown": text, "signals": [s.to_dict() for s in sigs]}}


TOOLS = [Tool("generate_brief", "Write the team brief from the signals the team added (or the top team signals): one "
              "document for the board and the investment committee, with London's key numbers, the evidence table "
              "for the team's submarkets, what supports the case and what puts it at risk, every figure footnoted.",
              obj_schema({"limit": {"type": "integer"},
                          "fresh": {"type": "boolean", "description": "write the headline again even if these "
                                                                     "facts were written up before"}}), generate_brief)]
