"""The team's shared data library: open-data feeds the agent collects, and reports colleagues upload.

Everything here is read-only bookkeeping over the store, used by Monitor's freshness bar and Sources."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import analytics as an

CADENCE_DAYS = {"hourly": 1 / 24, "daily": 1, "weekly": 7, "monthly": 30, "quarterly": 91,
                "half-yearly": 182, "annual": 365}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # store times are naive UTC


def _ts(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def when(s: str | None, today: date | None = None) -> str:
    """'today 07:00', 'yesterday 18:20' or '3 Oct' (store times are UTC)."""
    t = _ts(s)
    if not t:
        return "never"
    today = today or _utcnow().date()
    if t.date() == today:
        return f"today {t:%H:%M} UTC"
    if t.date() == today - timedelta(days=1):
        return f"yesterday {t:%H:%M} UTC"
    return f"{t:%-d %b %Y}"


def feeds(store, config: dict) -> list[dict]:
    """Every open-data feed with its licence, cadence, last run and next run."""
    status = {s["connector"]: s for s in store.statuses()}
    out = []
    for f in config.get("feeds", []):
        st = status.get(f.get("connector", ""), {})
        last = _ts(st.get("ts"))
        days = CADENCE_DAYS.get(f.get("cadence", "daily"), 1)
        if not f.get("connector"):
            state = f.get("note", "Planned")
        elif not st:
            state = "Not run yet"
        elif st["status"] == "ok":
            state = "OK" + (f" ({f['note']})" if f.get("note") else "")
        else:
            state = f"Failed: {st.get('detail', '')[:80]}"
        out.append({**f, "status": state, "last": when(st.get("ts")) if st else ("never" if f.get("connector") else "-"),
                    "next": f"{(last + timedelta(days=days)):%-d %b %H:%M} UTC" if last and f.get("connector") else "-"})
    # Each source a colleague followed, collected by the followed_sources connector.
    fs = status.get("followed_sources", {})
    for r in store.q("SELECT * FROM followed WHERE channel='auto' ORDER BY ts"):
        out.append({"name": r["name"], "publisher": f"{r['publisher']} · added by {r['added_by']}",
                    "licence": r["licence"], "cadence": r["cadence"], "connector": "followed_sources",
                    "status": ("OK" if fs.get("status") == "ok" else "Failed" if fs else "Not run yet"),
                    "last": when(fs.get("ts")) if fs else "never", "next": "-"})
    return out


def last_auto_update(store) -> dict | None:
    rows = store.q("SELECT * FROM team_log WHERE kind='auto' ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else None


def auto_due(store, config: dict) -> bool:
    last = last_auto_update(store)
    hours = config.get("auto_update_hours", 24)
    return not last or _utcnow() - _ts(last["ts"]) > timedelta(hours=hours)


def latest_upload(store) -> dict | None:
    ups = [u for u in store.uploads() if u.get("period")]
    return max(ups, key=lambda u: (u["period"], u["uploaded_at"])) if ups else None


def _quarters_back(today: date, n: int = 2) -> list[str]:
    y, q = today.year, (today.month - 1) // 3  # q = the last completed quarter (0 means Q4 last year)
    out = []
    for _ in range(n):
        if q == 0:
            y, q = y - 1, 4
        out.append(f"{y}Q{q}")
        q -= 1
    return out


def due_reports(store, config: dict, today: date | None = None) -> list[dict]:
    """Expected agency reports that are probably out but nobody has uploaded (newest quarter only),
    plus the next one coming up."""
    today = today or date.today()
    have = {(u["publisher"], u["period"]) for u in store.uploads()}
    out = []
    for exp in config.get("expected_reports", []):
        for period in _quarters_back(today):
            due = an.quarter_end(period) + timedelta(days=exp.get("lag_days", 30))
            if (exp["publisher"], period) in have:
                break  # the newest one we hold; older gaps are not worth a nudge
            if due <= today:
                out.append({"publisher": exp["publisher"], "period": period, "due": due, "missing": True})
                break
            out.append({"publisher": exp["publisher"], "period": period, "due": due, "missing": False})
    return out
