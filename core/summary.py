"""Three sentences on where the market is: occupiers, investment, what to watch.

Built from the library's figures (never invented), so the Monitor page and the brief open
with the market itself rather than a count of signals.
"""
from __future__ import annotations

from . import analytics as an
from . import taxonomy as tx


def is_tip(s) -> bool:
    """A colleague's tip that no published source has confirmed yet."""
    return s.title.startswith("Unverified tip: ")


def _lta(store, market: str, metric: str) -> float | None:
    """The most recent long-term average the publisher gave for this series."""
    for row in reversed(an.series(store, market, metric)):
        if row.get("lta") is not None:
            return row["lta"]
    return None


def lta_source(store, market: str, metric: str) -> str:
    """Which source carried that long-term average (often an older report than the latest figure)."""
    for row in reversed(an.series(store, market, metric)):
        if row.get("lta") is not None:
            return row.get("source_id", "")
    return ""


def _move(snap: dict, rising: str, falling: str) -> str:
    if snap["change"] is None or abs(snap["change"]) < 1e-9:
        return "held at"
    return rising if snap["change"] > 0 else falling


def _vs_lta(store, snap: dict) -> str:
    lta = _lta(store, snap["market"], snap["metric"])
    if not lta:
        return ""
    pct = (snap["value"] / lta - 1) * 100
    if abs(pct) < 5:
        return ", close to the long-term average"
    return f", {abs(pct):.0f}% {'above' if pct > 0 else 'below'} the long-term average"


def team_summary(store, signals: list) -> list[str]:
    """[occupier sentence, investment sentence, watch sentence]; any part with no data is left out."""
    out = []
    vac = an.snapshot(store, "London", "vacancy_pct")
    take = an.snapshot(store, "London", "take_up_msqft")
    req = an.snapshot(store, "London", "active_requirements_msqft")
    if vac:
        prev = f" from {vac['prev_value']:.1f}% in {an.period_label(vac['prev_period'])}" if vac["prev_period"] else ""
        s = (f"Central London vacancy {_move(vac, 'rose to', 'fell to')} {vac['value']:.1f}% in "
             f"{an.period_label(vac['period'])}{prev}")
        if take:
            s += f", with take-up of {tx.fmt_value('take_up_msqft', take['value'])}{_vs_lta(store, take)}"
        if req and req["change"]:
            s += (f", and active requirements {'up' if req['change'] > 0 else 'down'} to "
                  f"{tx.fmt_value('active_requirements_msqft', req['value'])}")
        out.append(s + ".")
    inv = an.snapshot(store, "London", "investment_gbp_bn")
    if inv:
        prev = (f" against {tx.fmt_value('investment_gbp_bn', inv['prev_value'])} in "
                f"{an.period_label(inv['prev_period'])}") if inv["prev_period"] else ""
        out.append(f"Investment was {tx.fmt_value('investment_gbp_bn', inv['value'])} in "
                   f"{an.period_label(inv['period'])}{prev}{_vs_lta(store, inv)}.")
    watch = next((s for s in signals if s.tone == "negative" and not is_tip(s) and s.kind != "data_quality"), None)
    if watch:
        names = set(tx.MARKET_PARENT) | set(tx.TOP_MARKETS)
        proper = any(watch.title.startswith(m) for m in names) or watch.title[1:2].isupper() or watch.title[:1].isdigit()
        out.append(f"To watch: {watch.title if proper else watch.title[0].lower() + watch.title[1:]}"
                   + (f" ({', '.join(watch.markets[:2])})" if watch.markets and watch.markets[0] not in watch.title
                      else "") + ".")
    return out
