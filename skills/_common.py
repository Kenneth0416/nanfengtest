"""Helpers shared by skill tool handlers."""
from __future__ import annotations

from core import analytics as an
from core import taxonomy as tx


def market_arg(name: str | None, default: str = "London") -> tuple[str, str]:
    if not name:
        return default, ""
    market, exact = tx.resolve_market(name)
    if not market:
        raise ValueError(f"Unknown market '{name}'. Try one of: {', '.join(list(tx.MARKET_PARENT)[:12])}...")
    note = "" if exact else f"Interpreting '{name}' as {market}."
    return market, note


def metric_arg(name: str) -> str:
    if name in tx.METRICS:
        return name
    found = tx.find_metrics(name or "")
    if not found:
        raise ValueError(f"Unknown metric '{name}'. Options: {', '.join(tx.METRICS)}")
    return found[0]


def sources_for(store, source_ids) -> list[dict]:
    seen, out = set(), []
    for sid in source_ids:
        if sid and sid not in seen:
            seen.add(sid)
            out.append(an.source_ref(store, sid))
    return out


MARKET_ENUM = sorted(tx.MARKET_PARENT)
METRIC_ENUM = sorted(tx.METRICS)
