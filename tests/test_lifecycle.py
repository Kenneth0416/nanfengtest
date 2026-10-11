"""Information lifecycle (research/information-lifecycle.md, section 11): states, half-lives, housekeeping,
incremental scoring and Monitor's daily pick, all with a fixed `today` so the results repeat."""
import os
import time
from datetime import date, timedelta

import pytest

from core import lifecycle as lc
from core.app import App
from core.gather import find_matches, rescore_all
from core.models import NewsItem
from core.signals import SignalEngine
from core.store import Store

TODAY = date(2026, 10, 11)


def news(i, days_ago, category="other", importance=4, **kw):
    d = (TODAY - timedelta(days=days_ago)).isoformat()
    return NewsItem(id=f"n{i}", title=kw.pop("title", f"Story {i} in the City"), body="", url=f"https://x/{i}",
                    source="Wire", published=d, category=category, importance=importance,
                    markets=kw.pop("markets", ["City Core"]), discovered=f"{d} 09:00", **kw)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    os.environ["LLM_PROVIDER"] = "offline"
    a = App(live=False)
    a.store = a.ctx.store = Store(tmp_path_factory.mktemp("db") / "t.db")
    a.refresh()
    return a


def test_state_for_each_kind_of_information():
    r = lc.DEFAULTS
    assert lc.state_for(news(1, 1), TODAY, r["news"], "news") == "new"
    assert lc.state_for(news(2, 20), TODAY, r["news"], "news") == "active"
    assert lc.state_for(news(3, 60), TODAY, r["news"], "news") == "cooling"
    assert lc.state_for(news(4, 200), TODAY, r["news"], "news") == "archived"
    deal = news(5, 45, "investment_deal")
    assert lc.kind_of(deal) == "deal_news" and lc.state_for(deal, TODAY) == "active"
    tip = NewsItem(id="t1", title="Heard a floor is under offer", body="", url="", source="Tip (Broker call)",
                   published=(TODAY - timedelta(days=15)).isoformat(),
                   shared_by=[{"who": "Kenneth", "how": "Broker call", "when": (TODAY - timedelta(days=15)).isoformat()}])
    assert lc.kind_of(tip) == "tip" and lc.state_for(tip, TODAY) == "expired"
    tip.also_reported = [{"source": "Wire", "url": "https://x", "published": (TODAY - timedelta(days=1)).isoformat()}]
    assert lc.state_for(tip, TODAY) == "new", "a published report revives the tip, from the report's day"
    assert lc.freshness("series", 500) == 1.0 and lc.freshness("news", 7) == 0.5 and lc.freshness("news", 7000) == 0.05


def test_old_databases_gain_the_columns_and_live_filter_works(tmp_path):
    db = tmp_path / "old.db"
    import sqlite3, json
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE news (id TEXT PRIMARY KEY, data TEXT, published TEXT)")
    for i, days in enumerate((1, 20, 60, 200)):
        n = news(i, days)
        con.execute("INSERT INTO news VALUES (?,?,?)", (n.id, json.dumps(n.__dict__), n.published))
    con.commit(); con.close()
    s = Store(db)  # migrations, indexes and the back-fill run on open
    assert s.q("SELECT COUNT(*) AS c FROM news WHERE category IS NULL OR story_id IS NULL")[0]["c"] == 0
    assert len(s.news()) == 4, "nothing is lost"
    assert lc.advance(s, {}, TODAY) == {"active": 1, "cooling": 1, "archived": 1}  # n0 is new already
    assert {n.id for n in s.news(states=lc.LIVE)} == {"n0", "n1"}
    plan = " ".join(r["detail"] for r in s.q("EXPLAIN QUERY PLAN SELECT data FROM news WHERE state IN ('new','active') ORDER BY published DESC"))
    assert "news_state_published" in plan


def test_half_life_ranking_and_live_window(app):
    s = app.store
    for n in (news(101, 3, title="Fresh letting in Soho", markets=["Soho"]), news(102, 20, title="Older letting in Soho", markets=["Soho"]),
              news(103, 20, "investment_deal", title="Deal 20 days old in Fitzrovia", markets=["Fitzrovia"]),
              news(104, 40, title="Forty-day story in Mayfair", markets=["Mayfair"])):
        n.state = lc.state_for(n, TODAY)
        s.add_news(n)
    eng = SignalEngine(s, app.config, TODAY)
    ranked = [x.title for x in eng.for_role("team")]
    assert ranked.index("Fresh letting in Soho") < ranked.index("Older letting in Soho")
    sig = {x.title: x for x in eng.all_signals()}
    assert eng._recency(sig["Deal 20 days old in Fitzrovia"]) > eng._recency(sig["Older letting in Soho"])
    assert "Forty-day story in Mayfair" not in sig, "cooling stories leave Monitor"
    assert s.news_item("n104").title == "Forty-day story in Mayfair", "but the Copilot still finds them"


def test_rescore_and_matching_stay_fast_with_ten_thousand_stories(tmp_path):
    s = Store(tmp_path / "big.db")
    cats = ["leasing_deal", "investment_deal", "other", "supply"]
    for i in range(10_000):
        n = news(i, i % 400, cats[i % 4], title=f"Occupier {i} takes {i % 90 + 1},000 sq ft at {i} Example Street",
                 markets=[["City Core", "Soho", "Mayfair"][i % 3]], size_sqft=(i % 90 + 1) * 1000)
        n.state = lc.state_for(n, TODAY)
        s.add_news(n, commit=False)
    s.db.commit()
    t = time.perf_counter()
    rescore_all(s, {}, TODAY)
    assert time.perf_counter() - t < 5
    probe = news(99999, 2, "leasing_deal", title="Occupier 4 takes 5,000 sq ft at 4 Example Street")

    def best(window):  # best of three runs, so a busy machine does not decide the result
        times = []
        for _ in range(3):
            t = time.perf_counter()
            found = find_matches(s, probe, config={"lifecycle": {"match_window_days": window}}, today=TODAY)
            times.append(time.perf_counter() - t)
        return min(times), found

    windowed, m = best(120)
    everything, _ = best(10_000)
    # the window, not the machine, keeps matching quick: it compares a fraction of the library, so it is clearly
    # faster than comparing every story, and still well under a second on a slow machine
    assert any(x["id"] == "n4" and x["score"] >= 0.9 for x in m)
    assert windowed < 0.7 * everything and windowed < 1, (windowed, everything)


def test_housekeep_is_idempotent_deletes_nothing_and_revives_merged_stories(tmp_path):
    s = Store(tmp_path / "h.db")
    cfg = {"lifecycle": {}, "digest": {"team_size": 5}}
    for i, days in enumerate((1, 10, 50, 100)):
        s.add_news(news(i, days))
    a = lc.housekeep(s, cfg, TODAY)
    states = {r["id"]: r["state"] for r in s.q("SELECT id, state FROM news")}
    assert states == {"n0": "new", "n1": "active", "n2": "cooling", "n3": "cooling"}
    b = lc.housekeep(s, cfg, TODAY)
    assert b["moved"] == {} and {r["id"]: r["state"] for r in s.q("SELECT id, state FROM news")} == states
    assert sum(r["kind"] == "housekeep" for r in s.activity(20)) == 1, "a quiet run leaves no line"
    before = s.q("SELECT COUNT(*) AS c FROM news")[0]["c"]
    lc.housekeep(s, cfg, TODAY + timedelta(days=200))
    assert all(r["state"] == "archived" for r in s.q("SELECT state FROM news")) and s.q("SELECT COUNT(*) AS c FROM news")[0]["c"] == before
    # a cooling story that a new outlet reports comes back to active on the next run
    lc.housekeep(s, cfg, TODAY)
    n2 = s.news_item("n2")
    n2.also_reported.append({"source": "Other Wire", "url": "https://y", "published": (TODAY - timedelta(days=3)).isoformat()})
    s.add_news(n2)
    lc.housekeep(s, cfg, TODAY)
    assert s.q("SELECT state FROM news WHERE id='n2'")[0]["state"] == "active"


def test_digest_shows_a_story_once_with_diversity_and_always_the_alerts(app):
    s = app.store
    cfg = app.config
    deal = news(201, 1, "investment_deal", importance=5, title="Barclays buys 1 Churchill Place, Canary Wharf, for £750m",
                markets=["Canary Wharf"], value_gbp_m=750)
    deal.also_reported = [{"source": f"Outlet {k}", "url": f"https://o/{k}", "published": deal.published} for k in range(3)]
    deal.state = "new"
    s.add_news(deal)
    for k in range(6):
        n = news(210 + k, 1, "leasing_deal", importance=5, title=f"Tenant {k} takes space in Canary Wharf", markets=["Canary Wharf"])
        n.state = "new"
        s.add_news(n)
    s.add_watch_rule("team", "London", "vacancy_pct", "<", 50, "London vacancy below 50%", "Sarah")  # fires on any data
    eng = SignalEngine(s, cfg, TODAY)
    d = eng.digest(5, user="Kenneth")
    titles = [x.title for x in d["picked"]]
    assert sum("Barclays buys" in t for t in titles) <= 1
    assert sum("Canary Wharf" in (x.markets[0] if x.markets else "") for x in d["picked"] if x.kind != "alert") <= 2
    assert any(x.kind == "alert" for x in d["picked"]), "an alert is always in the pick"
    assert len(d["picked"]) == 5 and d["rest"] and sum(d["folded"].values()) == len(d["rest"])
    # 'new since you last looked' counts only what arrived between two visits
    s.mark_seen("Kenneth", f"{TODAY.isoformat()} 08:00:00")
    late = news(230, 0, importance=5, title="Late story in Soho", markets=["Soho"])
    late.discovered = f"{TODAY.isoformat()} 09:00"
    late.state = "new"
    s.add_news(late)
    d2 = eng.digest(5, user="Kenneth")
    assert d2["new_since"] >= 1 and all(x.discovered <= f"{TODAY.isoformat()} 08:00:00" or x.title == "Late story in Soho"
                                       for x in d2["picked"] + d2["rest"] if x.discovered and x.discovered > f"{TODAY.isoformat()} 08:00:00")
