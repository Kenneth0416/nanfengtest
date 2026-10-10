"""SQLite store for normalised data, user settings and feedback."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .models import NewsItem, Observation

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (source_id TEXT PRIMARY KEY, publisher TEXT, title TEXT,
    period TEXT, url TEXT, definition_note TEXT);
CREATE TABLE IF NOT EXISTS observations (period TEXT, market TEXT, metric TEXT, value REAL, lta REAL,
    source_id TEXT, note TEXT, UNIQUE(period, market, metric, source_id, value));
CREATE TABLE IF NOT EXISTS deals (period TEXT, deal_type TEXT, party TEXT, building TEXT, submarket TEXT,
    size_sqft REAL, rent_psf REAL, price_gbp_m REAL, yield_pct REAL, note TEXT, source_id TEXT,
    UNIQUE(period, party, building, deal_type));
CREATE TABLE IF NOT EXISTS pipeline (scheme TEXT PRIMARY KEY, submarket TEXT, size_sqft REAL,
    expected_completion TEXT, status TEXT, prelet_party TEXT, note TEXT, source_id TEXT);
CREATE TABLE IF NOT EXISTS macro (date TEXT, indicator TEXT, value REAL, unit TEXT, source_id TEXT,
    note TEXT, UNIQUE(date, indicator));
CREATE TABLE IF NOT EXISTS news (id TEXT PRIMARY KEY, data TEXT, published TEXT);
CREATE TABLE IF NOT EXISTS watch_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, market TEXT,
    metric TEXT, op TEXT, value REAL, label TEXT);
CREATE TABLE IF NOT EXISTS feedback (signal_id TEXT, role TEXT, vote INTEGER, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS user_focus (user TEXT, data TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS brief_items (signal_id TEXT PRIMARY KEY, data TEXT, added_by TEXT,
    ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS team_log (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, author TEXT, text TEXT,
    answer TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS checked (signal_id TEXT PRIMARY KEY, checked_by TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, url TEXT, how TEXT,
    shared_by TEXT, status TEXT DEFAULT 'new', result TEXT DEFAULT '', ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS followed (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, publisher TEXT, url TEXT UNIQUE,
    kind TEXT, channel TEXT, cadence TEXT, licence TEXT, reason TEXT, quote TEXT, terms_url TEXT, added_by TEXT,
    seen TEXT DEFAULT '[]', ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS staged (path TEXT PRIMARY KEY, analysis TEXT, staged_for TEXT, engine TEXT,
    ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS connector_status (connector TEXT PRIMARY KEY, status TEXT, detail TEXT,
    ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS internal_deals (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, property TEXT,
    status TEXT, confidentiality TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP, updated TEXT DEFAULT CURRENT_TIMESTAMP);
"""

# Shared library: every source records how it arrived (auto feed or a colleague's upload), and every
# figure can be flagged by anyone and settled by anyone.
MIGRATIONS = [
    ("watch_rules", "author TEXT DEFAULT ''"),
    ("sources", "channel TEXT DEFAULT 'auto'"),        # auto | upload
    ("sources", "licence TEXT DEFAULT ''"),
    ("sources", "uploaded_by TEXT DEFAULT ''"),
    ("sources", "uploaded_at TEXT DEFAULT ''"),
    ("sources", "file_hash TEXT DEFAULT ''"),
    ("observations", "status TEXT DEFAULT 'ok'"),      # ok | flagged | rejected
    ("observations", "flag TEXT DEFAULT ''"),
    ("observations", "flagged_by TEXT DEFAULT ''"),
    ("observations", "resolved_by TEXT DEFAULT ''"),
]
SOURCE_COLS = ("source_id", "publisher", "title", "period", "url", "definition_note", "channel", "licence",
               "uploaded_by", "uploaded_at", "file_hash")
OBS_COLS = ("period", "market", "metric", "value", "lta", "source_id", "note", "status", "flag", "flagged_by")


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The web app, the scheduled collection job and the Pi bridge write to the same file: WAL lets
        # readers carry on during a write, and the busy timeout makes a second writer wait, not fail.
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        for table, col in MIGRATIONS:  # older databases gain the shared-library columns
            try:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        self.db.commit()

    # -- writes -------------------------------------------------------------
    def add_source(self, row: dict):
        vals = {k: row.get(k) or "" for k in SOURCE_COLS}
        vals["channel"] = vals["channel"] or "auto"
        if vals["channel"] == "upload" and not vals["uploaded_at"]:  # keep the first upload time on a re-load
            old = self.q("SELECT uploaded_at FROM sources WHERE source_id=?", (vals["source_id"],))
            vals["uploaded_at"] = (old and old[0]["uploaded_at"]) or self.q("SELECT datetime('now') AS t")[0]["t"]
        self.db.execute(f"INSERT OR REPLACE INTO sources ({','.join(SOURCE_COLS)}) "
                        f"VALUES ({','.join(':' + k for k in SOURCE_COLS)})", vals)
        self.db.commit()

    def add_observations(self, obs: list[Observation], flags: list[str] | None = None, by: str = "") -> int:
        """flags[i] non-empty saves that figure as flagged (usable, shown with a warning) until someone settles it."""
        rows = []
        for i, o in enumerate(obs):
            flag = (flags or [""] * len(obs))[i]
            rows.append({**asdict(o), "status": "flagged" if flag else "ok", "flag": flag, "flagged_by": by if flag else ""})
        cur = self.db.executemany(f"INSERT OR IGNORE INTO observations ({','.join(OBS_COLS)}) "
                                  f"VALUES ({','.join(':' + k for k in OBS_COLS)})", rows)
        self.db.commit()
        return cur.rowcount

    def flag_observation(self, rowid: int, reason: str, by: str):
        """Anyone can say 'this number looks wrong'. It stays usable, with a warning, until someone settles it."""
        self.db.execute("UPDATE observations SET status='flagged', flag=?, flagged_by=?, resolved_by='' WHERE rowid=?",
                        (reason, by, rowid))
        self.db.commit()

    def resolve_observation(self, rowid: int, by: str, keep: bool = True):
        self.db.execute("UPDATE observations SET status=?, resolved_by=? WHERE rowid=?",
                        ("ok" if keep else "rejected", by, rowid))
        self.db.commit()

    def add_deal(self, row: dict):
        self.db.execute("INSERT OR IGNORE INTO deals VALUES (:period,:deal_type,:party,:building,:submarket,"
                        ":size_sqft,:rent_psf,:price_gbp_m,:yield_pct,:note,:source_id)", row)
        self.db.commit()

    def add_pipeline(self, row: dict):
        self.db.execute("INSERT OR REPLACE INTO pipeline VALUES (:scheme,:submarket,:size_sqft,"
                        ":expected_completion,:status,:prelet_party,:note,:source_id)", row)
        self.db.commit()

    def add_macro(self, row: dict):
        self.db.execute("INSERT OR REPLACE INTO macro VALUES (:date,:indicator,:value,:unit,:source_id,:note)", row)
        self.db.commit()

    def add_news(self, item: NewsItem):
        self.db.execute("INSERT OR REPLACE INTO news VALUES (?,?,?)",
                        (item.id, json.dumps(asdict(item)), item.published))
        self.db.commit()

    def set_status(self, connector: str, status: str, detail: str = ""):
        self.db.execute("INSERT OR REPLACE INTO connector_status (connector,status,detail) VALUES (?,?,?)",
                        (connector, status, detail))
        self.db.commit()

    def add_watch_rule(self, role, market, metric, op, value, label, author: str = "") -> int:
        cur = self.db.execute("INSERT INTO watch_rules (role,market,metric,op,value,label,author) VALUES (?,?,?,?,?,?,?)",
                              (role, market, metric, op, value, label, author))
        self.db.commit()
        return cur.lastrowid

    def delete_watch_rule(self, rule_id: int):
        self.db.execute("DELETE FROM watch_rules WHERE id=?", (rule_id,))
        self.db.commit()

    def save_focus(self, user: str, focus: dict):
        """Every change is a new row, so Undo is just dropping the latest one."""
        self.db.execute("INSERT INTO user_focus (user, data) VALUES (?, ?)", (user, json.dumps(focus)))
        self.db.commit()

    def focus(self, user: str) -> dict | None:
        r = self.q("SELECT data FROM user_focus WHERE user=? ORDER BY rowid DESC LIMIT 1", (user,))
        return json.loads(r[0]["data"]) if r else None

    def undo_focus(self, user: str):
        self.db.execute("DELETE FROM user_focus WHERE rowid = (SELECT MAX(rowid) FROM user_focus WHERE user=?)", (user,))
        self.db.commit()

    def reset_focus(self, user: str):
        self.db.execute("DELETE FROM user_focus WHERE user=?", (user,))
        self.db.commit()

    def set_pending_setup(self, user: str, proposal: dict | None):
        """A setup the agent proposed but the user has not applied yet (kept beside the focus rows)."""
        self.db.execute("DELETE FROM user_focus WHERE user=?", (f"{user}#pending",))
        if proposal:
            self.db.execute("INSERT INTO user_focus (user, data) VALUES (?, ?)", (f"{user}#pending", json.dumps(proposal)))
        self.db.commit()

    def pending_setup(self, user: str) -> dict | None:
        return self.focus(f"{user}#pending")

    # -- shared team state ------------------------------------------------------
    def add_to_brief(self, signal: dict, added_by: str):
        self.db.execute("INSERT OR REPLACE INTO brief_items (signal_id, data, added_by) VALUES (?,?,?)",
                        (signal["id"], json.dumps(signal), added_by))
        self.db.commit()

    def remove_from_brief(self, signal_id: str):
        self.db.execute("DELETE FROM brief_items WHERE signal_id=?", (signal_id,))
        self.db.commit()

    def brief_items(self) -> list[dict]:
        return [{**json.loads(r["data"]), "added_by": r["added_by"]}
                for r in self.q("SELECT * FROM brief_items ORDER BY ts, rowid")]

    def log(self, kind: str, author: str, text: str, answer: str = ""):
        self.db.execute("INSERT INTO team_log (kind, author, text, answer) VALUES (?,?,?,?)", (kind, author, text, answer))
        self.db.commit()

    def activity(self, limit: int = 8) -> list[dict]:
        return self.q("SELECT * FROM team_log ORDER BY id DESC LIMIT ?", (limit,))

    def mark_checked(self, signal_id: str, by: str):
        self.db.execute("INSERT OR REPLACE INTO checked (signal_id, checked_by) VALUES (?,?)", (signal_id, by))
        self.db.commit()

    def checked(self) -> dict[str, str]:
        return {r["signal_id"]: r["checked_by"] for r in self.q("SELECT * FROM checked")}

    def add_feedback(self, signal_id: str, role: str, vote: int):
        self.db.execute("INSERT INTO feedback (signal_id, role, vote) VALUES (?,?,?)", (signal_id, role, vote))
        self.db.commit()

    # -- reads --------------------------------------------------------------
    def q(self, sql: str, params=()) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def sources(self) -> dict[str, dict]:
        return {r["source_id"]: r for r in self.q("SELECT * FROM sources")}

    def observations(self, market=None, metric=None) -> list[dict]:
        """Rejected figures are kept for the record but never used."""
        sql, params = "SELECT rowid, * FROM observations WHERE status != 'rejected'", []
        if market:
            sql += " AND market=?"; params.append(market)
        if metric:
            sql += " AND metric=?"; params.append(metric)
        return self.q(sql + " ORDER BY period", params)

    def news(self) -> list[NewsItem]:
        return [NewsItem(**json.loads(r["data"])) for r in self.q("SELECT data FROM news ORDER BY published DESC")]

    def watch_rules(self, role=None) -> list[dict]:
        if role:
            return self.q("SELECT * FROM watch_rules WHERE role=? ORDER BY id", (role,))
        return self.q("SELECT * FROM watch_rules ORDER BY id")

    def hidden_signals(self, role: str) -> set[str]:
        return {r["signal_id"] for r in self.q("SELECT signal_id FROM feedback WHERE role=? AND vote<0", (role,))}

    def liked_signals(self, role: str) -> set[str]:
        return {r["signal_id"] for r in self.q("SELECT signal_id FROM feedback WHERE role=? AND vote>0", (role,))}

    # -- team inbox: links and tips colleagues share, waiting for the gatherer ---------------------
    def add_to_inbox(self, text: str, url: str, how: str, shared_by: str) -> int:
        cur = self.db.execute("INSERT INTO inbox (text, url, how, shared_by) VALUES (?,?,?,?)",
                              (text, url, how, shared_by))
        self.db.commit()
        return cur.lastrowid

    def inbox(self, status: str | None = "new") -> list[dict]:
        if status:
            return self.q("SELECT * FROM inbox WHERE status=? ORDER BY id", (status,))
        return self.q("SELECT * FROM inbox ORDER BY id DESC")

    def close_inbox(self, item_id: int, result: str):
        self.db.execute("UPDATE inbox SET status='done', result=? WHERE id=?", (result, item_id))
        self.db.commit()

    def stage(self, path: str, analysis: dict, staged_for: str, engine: str = ""):
        """An upload read by the information agent, waiting for the uploader's review."""
        self.db.execute("INSERT OR REPLACE INTO staged (path, analysis, staged_for, engine) VALUES (?,?,?,?)",
                        (str(Path(path).resolve()), json.dumps(analysis, default=str), staged_for, engine))
        self.db.commit()

    def staged(self, path: str) -> dict | None:
        rows = self.q("SELECT * FROM staged WHERE path=?", (str(Path(path).resolve()),))
        return {**json.loads(rows[0]["analysis"]), "engine": rows[0]["engine"]} if rows else None

    def news_item(self, news_id: str) -> NewsItem | None:
        rows = self.q("SELECT data FROM news WHERE id=?", (news_id,))
        return NewsItem(**json.loads(rows[0]["data"])) if rows else None

    def flagged(self) -> list[dict]:
        return self.q("SELECT o.rowid, o.*, s.publisher, s.title, s.channel, s.uploaded_by, s.uploaded_at "
                      "FROM observations o LEFT JOIN sources s USING (source_id) WHERE o.status='flagged' "
                      "ORDER BY s.uploaded_at DESC, o.period, o.market")

    def uploads(self) -> list[dict]:
        """Reports colleagues uploaded, newest first, with how many figures each added and how many are flagged."""
        return self.q("SELECT s.*, SUM(o.status != 'rejected') AS figures, SUM(o.status='flagged') AS to_check "
                      "FROM sources s LEFT JOIN observations o USING (source_id) WHERE s.channel='upload' "
                      "GROUP BY s.source_id ORDER BY s.uploaded_at DESC, s.period DESC")

    def find_upload(self, file_hash: str = "", publisher: str = "", period: str = "") -> dict | None:
        """The same file, or the same publisher's report for the same quarter, uploaded before."""
        rows = []
        if file_hash:
            rows = self.q("SELECT * FROM sources WHERE file_hash=? AND file_hash!=''", (file_hash,))
        if not rows and publisher and period:
            rows = self.q("SELECT * FROM sources WHERE channel='upload' AND publisher=? AND period=?",
                          (publisher, period))
        return rows[0] if rows else None

    # 🔵 internal records (core/internal.py): the company's own deals, one JSON document each
    def internal_deals(self) -> list[dict]:
        out = []
        for r in self.q("SELECT id, data FROM internal_deals ORDER BY updated DESC, id DESC"):
            d = json.loads(r["data"])
            d["id"] = r["id"]
            out.append(d)
        return out

    def internal_deal(self, deal_id: int) -> dict | None:
        r = self.q("SELECT id, data FROM internal_deals WHERE id=?", (deal_id,))
        if not r:
            return None
        d = json.loads(r[0]["data"])
        d["id"] = r[0]["id"]
        return d

    def save_internal_deal(self, d: dict) -> int:
        body = json.dumps({k: v for k, v in d.items() if k != "id"})
        if d.get("id"):
            self.db.execute("UPDATE internal_deals SET data=?, property=?, status=?, confidentiality=?, "
                            "updated=datetime('now') WHERE id=?",
                            (body, d.get("property", ""), d.get("status", "draft"), d.get("confidentiality", "internal"), d["id"]))
            self.db.commit()
            return d["id"]
        cur = self.db.execute("INSERT INTO internal_deals (data, property, status, confidentiality) VALUES (?,?,?,?)",
                              (body, d.get("property", ""), d.get("status", "draft"), d.get("confidentiality", "internal")))
        self.db.commit()
        d["id"] = cur.lastrowid
        return d["id"]

    def delete_internal_deal(self, deal_id: int):
        self.db.execute("DELETE FROM internal_deals WHERE id=?", (deal_id,))
        self.db.commit()

    def statuses(self) -> list[dict]:
        return self.q("SELECT * FROM connector_status ORDER BY connector")
