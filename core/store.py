"""SQLite store for normalised data, user settings and feedback."""
from __future__ import annotations

import json
import uuid
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
CREATE TABLE IF NOT EXISTS digest (day TEXT PRIMARY KEY, data TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS user_seen (user TEXT PRIMARY KEY, last_seen TEXT);
CREATE TABLE IF NOT EXISTS watch_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, market TEXT,
    metric TEXT, op TEXT, value REAL, label TEXT);
CREATE TABLE IF NOT EXISTS feedback (signal_id TEXT, role TEXT, vote INTEGER, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS answer_votes (message_id INTEGER, role TEXT, vote INTEGER, ts TEXT DEFAULT CURRENT_TIMESTAMP,
                                          PRIMARY KEY (message_id, role));
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
CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, owner TEXT, title TEXT DEFAULT '',
    created TEXT DEFAULT CURRENT_TIMESTAMP, updated TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, role TEXT, content TEXT,
    trace TEXT DEFAULT '', engine TEXT DEFAULT '', ts TEXT DEFAULT CURRENT_TIMESTAMP);
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
    ("team_log", "ref TEXT DEFAULT ''"),               # a shared Copilot answer: the chat_messages id it came from
    ("team_log", "note TEXT DEFAULT ''"),              # the sharer's one-line reason ("IC needs this")
    # information lifecycle: real columns on news so Monitor's queries filter by state without parsing JSON
    ("news", "state TEXT DEFAULT 'new'"),
    ("news", "valid_until TEXT"),
    ("news", "state_changed TEXT"),
    ("news", "category TEXT"),
    ("news", "importance INTEGER"),
    ("news", "hot INTEGER"),
    ("news", "markets TEXT"),
    ("news", "discovered TEXT"),
    ("news", "story_id TEXT"),
    ("observations", "state TEXT DEFAULT 'active'"),
]
INDEXES = [
    "CREATE INDEX IF NOT EXISTS news_state_published ON news (state, published)",
    "CREATE INDEX IF NOT EXISTS news_category_published ON news (category, published)",
    "CREATE INDEX IF NOT EXISTS news_story ON news (story_id)",
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
        # Copilot answers logged before sharing became a choice (no ref) must not stay public
        self.db.execute("DELETE FROM team_log WHERE kind = 'ask' AND (ref IS NULL OR ref = '')")
        self.db.execute("DELETE FROM team_log WHERE kind = 'setup' OR (kind = 'brief' AND (text LIKE 'built the team brief%' "
                        "OR text LIKE 'rewrote the team brief%'))")
        self.db.commit()
        for sql in INDEXES:
            self.db.execute(sql)
        self._backfill_news()
        self.db.commit()

    def _backfill_news(self):
        """Older databases hold news as JSON only: fill the real columns once from it."""
        rows = self.q("SELECT id, data FROM news WHERE category IS NULL OR story_id IS NULL")
        for r in rows:
            d = json.loads(r["data"])
            self.db.execute("UPDATE news SET category=?, importance=?, hot=?, markets=?, discovered=?, story_id=?, "
                            "state=COALESCE(state, 'new') WHERE id=?",
                            (d.get("category", "other"), d.get("importance", 1), d.get("hot", 0),
                             json.dumps(d.get("markets", [])), d.get("discovered", ""), d.get("story_id") or r["id"], r["id"]))

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

    def add_news(self, item: NewsItem, commit: bool = True):
        """Insert or update one story: the JSON and the real columns Monitor filters on. A batch (a collection
        round) passes commit=False and commits once at the end."""
        item.story_id = item.story_id or item.id
        self.db.execute("INSERT OR REPLACE INTO news (id, data, published, state, valid_until, state_changed, category, "
                        "importance, hot, markets, discovered, story_id) VALUES (?,?,?,?,"
                        "(SELECT valid_until FROM news WHERE id=?),(SELECT state_changed FROM news WHERE id=?),?,?,?,?,?,?)",
                        (item.id, json.dumps(asdict(item)), item.published, item.state, item.id, item.id, item.category,
                         item.importance, item.hot, json.dumps(item.markets), item.discovered, item.story_id))
        if commit:
            self.db.commit()

    def set_news_state(self, news_id: str, state: str, changed: str, valid_until: str = "", commit: bool = True):
        """Lifecycle: the state column and the copy inside the JSON move together."""
        self.db.execute("UPDATE news SET state=?, state_changed=?, valid_until=?, "
                        "data=json_set(data, '$.state', ?) WHERE id=?", (state, changed, valid_until, state, news_id))
        if commit:
            self.db.commit()

    def news_rows(self) -> list[tuple[NewsItem, dict]]:
        """Every story with its lifecycle columns, for housekeeping."""
        return [(NewsItem(**json.loads(r["data"])), r) for r in self.q("SELECT * FROM news ORDER BY published DESC")]

    def save_digest(self, day: str, data: dict):
        self.db.execute("INSERT OR REPLACE INTO digest (day, data) VALUES (?,?)", (day, json.dumps(data)))
        self.db.commit()

    def digest(self, day: str) -> dict | None:
        r = self.q("SELECT data FROM digest WHERE day=?", (day,))
        return json.loads(r[0]["data"]) if r else None

    def last_seen(self, user: str) -> str:
        r = self.q("SELECT last_seen FROM user_seen WHERE user=?", (user,))
        return r[0]["last_seen"] if r else ""

    def mark_seen(self, user: str, when: str):
        self.db.execute("INSERT OR REPLACE INTO user_seen (user, last_seen) VALUES (?,?)", (user, when))
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

    def share_watch_rule(self, rule_id: int):
        """A personal alert becomes the team's: it then shows and fires for everyone."""
        self.db.execute("UPDATE watch_rules SET role='team' WHERE id=?", (rule_id,))
        self.db.commit()

    def unhide_signals(self, role: str):
        self.db.execute("DELETE FROM feedback WHERE role=? AND vote<0", (role,))
        self.db.commit()

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

    # -- saved Copilot chats: each person's conversations survive a refresh and can be resumed ------------
    def new_chat(self, owner: str, title: str = "") -> str:
        chat_id = uuid.uuid4().hex[:12]
        self.db.execute("INSERT INTO chats (id, owner, title) VALUES (?,?,?)", (chat_id, owner, title[:80]))
        self.db.commit()
        return chat_id

    def add_chat_message(self, chat_id: str, role: str, content: str, trace: list | None = None, engine: str = "") -> int:
        cur = self.db.execute("INSERT INTO chat_messages (chat_id, role, content, trace, engine) VALUES (?,?,?,?,?)",
                              (chat_id, role, content, json.dumps(trace) if trace else "", engine))
        self.db.execute("UPDATE chats SET updated = CURRENT_TIMESTAMP, title = CASE WHEN title = '' AND ? = 'user' "
                        "THEN ? ELSE title END WHERE id = ?", (role, content[:80], chat_id))
        self.db.commit()
        return cur.lastrowid

    # -- sharing: a Copilot answer reaches the team only when its owner shares it -------------------------
    def share_answer(self, message_id: int, by: str, note: str = ""):
        """Put one answer (with the question before it) in team activity, as a conscious choice by the person
        who asked, with an optional one-line reason; sharing twice does nothing."""
        if self.shared_by(message_id):
            return
        m = self.q("SELECT * FROM chat_messages WHERE id = ?", (message_id,))
        if not m or m[0]["role"] != "assistant":
            return
        q = self.q("SELECT content FROM chat_messages WHERE chat_id = ? AND id < ? AND role = 'user' ORDER BY id DESC LIMIT 1",
                   (m[0]["chat_id"], message_id))
        self.db.execute("INSERT INTO team_log (kind, author, text, answer, ref, note) VALUES ('ask',?,?,?,?,?)",
                        (by, q[0]["content"] if q else "", m[0]["content"][:4000], str(message_id), note[:200]))
        self.db.commit()

    def shared_answer(self, ref: str) -> dict | None:
        """The shared chat message itself (content, trace, engine), so the charts and sources travel with it."""
        r = self.q("SELECT * FROM chat_messages WHERE id = ?", (ref,))
        return {**r[0], "trace": json.loads(r[0]["trace"]) if r[0]["trace"] else []} if r else None

    def unshare_answer(self, message_id: int):
        self.db.execute("DELETE FROM team_log WHERE kind = 'ask' AND ref = ?", (str(message_id),))
        self.db.commit()

    def shared_by(self, message_id: int) -> dict | None:
        """{author, ts} when this answer is in team activity, else None."""
        r = self.q("SELECT author, ts FROM team_log WHERE kind = 'ask' AND ref = ? LIMIT 1", (str(message_id),))
        return r[0] if r else None

    def chats(self, owner: str, limit: int = 30) -> list[dict]:
        """A person's conversations, newest first, only those with a message (an empty new chat is not listed)."""
        return self.q("SELECT c.*, COUNT(m.id) AS messages FROM chats c JOIN chat_messages m ON m.chat_id = c.id "
                      "WHERE c.owner = ? GROUP BY c.id ORDER BY MAX(m.id) DESC LIMIT ?", (owner, limit))

    def chat_messages(self, chat_id: str) -> list[dict]:
        return [{**r, "trace": json.loads(r["trace"]) if r["trace"] else []}
                for r in self.q("SELECT * FROM chat_messages WHERE chat_id = ? ORDER BY id", (chat_id,))]

    def activity(self, limit: int = 8) -> list[dict]:
        """What the team did, newest first. Auto-updates would drown it, so only the latest one is kept."""
        rows = self.q("SELECT * FROM team_log WHERE kind != 'auto' ORDER BY id DESC LIMIT ?", (limit,))
        rows += self.q("SELECT * FROM team_log WHERE kind = 'auto' ORDER BY id DESC LIMIT 1")
        return sorted(rows, key=lambda r: -r["id"])[:limit]

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

    def news(self, states: tuple | list | None = None, since: str | None = None, category: str | None = None) -> list[NewsItem]:
        """Stories newest first. With no filter everything comes back (archived and expired included, so the
        Copilot and search still find old stories); Monitor asks for states=('new', 'active')."""
        where, params = [], []
        if states:
            where.append(f"state IN ({','.join('?' * len(states))})")
            params += list(states)
        if since:
            where.append("published >= ?")
            params.append(since)
        if category:
            where.append("category = ?")
            params.append(category)
        sql = "SELECT data FROM news" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY published DESC"
        return [NewsItem(**json.loads(r["data"])) for r in self.q(sql, params)]

    def watch_rules(self, role=None) -> list[dict]:
        if role:
            return self.q("SELECT * FROM watch_rules WHERE role=? ORDER BY id", (role,))
        return self.q("SELECT * FROM watch_rules ORDER BY id")

    def hidden_signals(self, role: str) -> set[str]:
        return {r["signal_id"] for r in self.q("SELECT signal_id FROM feedback WHERE role=? AND vote<0", (role,))}

    def liked_signals(self, role: str) -> set[str]:
        return {r["signal_id"] for r in self.q("SELECT signal_id FROM feedback WHERE role=? AND vote>0", (role,))}

    # -- thumbs up / down on a Copilot answer (one vote per person per answer; 0 clears it) ------------
    def vote_answer(self, message_id: int, role: str, vote: int):
        if vote == 0:
            self.db.execute("DELETE FROM answer_votes WHERE message_id=? AND role=?", (message_id, role))
        else:
            self.db.execute("INSERT OR REPLACE INTO answer_votes (message_id, role, vote) VALUES (?,?,?)",
                            (message_id, role, 1 if vote > 0 else -1))
        self.db.commit()

    def answer_vote(self, message_id: int, role: str) -> int:
        r = self.q("SELECT vote FROM answer_votes WHERE message_id=? AND role=?", (message_id, role))
        return r[0]["vote"] if r else 0

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

    # internal records (core/internal.py): the company's own deals, one JSON document each
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
