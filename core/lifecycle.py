"""Information lifecycle: nothing is deleted, items change state as they age.

States: new -> active -> cooling -> archived, plus expired (a colleague's words that never found a published
source) and, for agency reports, superseded by the next edition. The periods per kind live in config.yaml
under `lifecycle:`; `state_for` and `freshness` are pure functions so they are easy to test with a fixed day.
Design: /mnt/project-files/research/information-lifecycle.md (MVP section 11).
"""
from __future__ import annotations

from datetime import date

from .models import NewsItem

DEFAULTS = {
    "news": {"fresh_days": 2, "active_days": 30, "archive_days": 180, "half_life_days": 7},
    "deal_news": {"fresh_days": 7, "active_days": 60, "archive_days": 180, "half_life_days": 14},
    "tip": {"fresh_days": 2, "active_days": 14, "archive_days": 180, "half_life_days": 5, "verify_days": 14},
    "series": {"decay": False},
    "agency_report": {"decay": False, "superseded": "next_period"},
}
LIVE = ("new", "active")            # what Monitor shows
STATES = ("new", "active", "cooling", "archived", "expired")
DEAL_CATEGORIES = ("leasing_deal", "investment_deal")


def rules(config: dict, kind: str) -> dict:
    """The lifecycle rule for one kind of information, config over defaults."""
    return {**DEFAULTS.get(kind, DEFAULTS["news"]), **(config.get("lifecycle", {}).get(kind) or {})}


def kind_of(item: NewsItem) -> str:
    """tip: a colleague's words with no published source; deal_news: a letting or sale; else news."""
    if item.shared_by and not item.url and not item.also_reported:
        return "tip"
    if item.category in DEAL_CATEGORIES:
        return "deal_news"
    return "news"


def _day(s: str) -> date | None:
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def last_activity(item: NewsItem) -> date | None:
    """The last day the story moved: published, or a later report of it, or a colleague sharing it."""
    days = [_day(item.published)] + [_day(r.get("published", "")) for r in item.also_reported] \
        + [_day(s.get("when", "")) for s in item.shared_by]
    days = [d for d in days if d]
    return max(days) if days else _day(item.discovered)


def state_for(item: NewsItem, today: date, rule: dict | None = None, kind: str | None = None) -> str:
    """Where one story is in its life on `today`. Age counts from the last report of it, so a cooling story
    that a new outlet picks up comes back to active."""
    kind = kind or kind_of(item)
    rule = rule or DEFAULTS[kind]
    when = last_activity(item)
    if when is None:
        return "new"
    age = (today - when).days
    if kind == "tip" and age > rule.get("verify_days", 14) and not item.url and not item.also_reported:
        return "expired"  # a tip has two weeks to find a published source
    if age <= rule["fresh_days"]:
        return "new"
    if age <= rule["active_days"]:
        return "active"
    if age <= rule["archive_days"]:
        return "cooling"
    return "archived"


def valid_until(item: NewsItem, today: date, rule: dict) -> str:
    """The day a story leaves the active set, for the record."""
    when = last_activity(item) or today
    return date.fromordinal(when.toordinal() + rule["active_days"]).isoformat()


def freshness(kind: str, age_days: int, rule: dict | None = None) -> float:
    """0.05-1.0: a half-life per kind (news 7 days, deals 14, tips 5); data series do not decay, whether a
    figure is the latest period decides for them."""
    rule = rule or DEFAULTS.get(kind, DEFAULTS["news"])
    if rule.get("decay") is False or "half_life_days" not in rule:
        return 1.0
    return max(0.05, 0.5 ** (max(0, age_days) / rule["half_life_days"]))


def advance(store, config: dict, today: date) -> dict:
    """Move every story to the state its age says; writes only what changed. Returns counts per new state."""
    counts: dict[str, int] = {}
    for item, row in store.news_rows():
        kind = kind_of(item)
        rule = rules(config, kind)
        state = state_for(item, today, rule, kind)
        if state != row.get("state"):
            store.set_news_state(item.id, state, today.isoformat(), valid_until(item, today, rule), commit=False)
            counts[state] = counts.get(state, 0) + 1
    store.db.commit()
    return counts


def housekeep(store, config: dict, today: date | None = None) -> dict:
    """The daily tidy-up: advance states, re-score only the live stories, build today's digest, and leave one
    line in team activity when anything moved. Running it twice on the same day changes nothing the second time."""
    from .gather import rescore_all
    from .signals import SignalEngine
    today = today or date.today()
    moved = advance(store, config, today)
    rescore_all(store, config, today=today)
    digest = SignalEngine(store, config, today).digest(config.get("digest", {}).get("team_size", 5))
    store.save_digest(today.isoformat(), {"picked": [s.to_dict() for s in digest["picked"]],
                                          "rest": [s.id for s in digest["rest"]], "folded": digest["folded"]})
    if moved:
        words = {"archived": "archived", "expired": "expired", "cooling": "cooling", "active": "back to active", "new": "new"}
        store.log("housekeep", "Housekeeping", ", ".join(f"{n} {words[s]}" for s, n in sorted(moved.items())))
    return {"moved": moved, "digest": digest}
