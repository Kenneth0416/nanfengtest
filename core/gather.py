"""Team information gathering: links and tips colleagues share, plus the agent's own collection rounds.

Each step is a small function the Pi information agent (`pi_engine/info_agent.ts`) calls as a tool
through the `market_gather` skill:

    read_link -> classify -> find_matches -> save (new item, or merged into the same story) -> hotness

`process_share` chains the same steps for the `share_tip` tool and the tests.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser

from . import taxonomy as tx
from .models import NewsItem, RawItem

MERGE_AT = 0.55          # match score at which a share is treated as the same story
HOW = ["Broker call", "LinkedIn", "Article or newsletter", "Meeting or event", "Other"]
_STOP = set("""that this with from have will were been their they them than then into over about after
before which while where there these those would could should also said says around close near heard
told hear just more most very some such only other being week weeks today yesterday london office offices
market space floor floors deal deals building client clients agent agents broker brokers source sources
according reportedly report reports reported quarter year years month months""".split())


def merge_at(config: dict) -> float:
    return config.get("gather", {}).get("merge_at", MERGE_AT)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


# -- read a shared link ------------------------------------------------------------------------
class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.meta, self.text, self._skip, self._in_title = "", {}, [], 0, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "nav", "footer", "header", "noscript"):
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta" and a.get("content"):
            self.meta[(a.get("property") or a.get("name") or "").lower()] = a["content"]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header", "noscript") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.text.append(data.strip())


def parse_page(html: str, url: str = "") -> dict:
    p = _Page()
    p.feed(html)
    title = p.meta.get("og:title") or p.title.strip()
    published = (p.meta.get("article:published_time") or p.meta.get("date") or "")[:10]
    body = " ".join(t for t in p.text if len(t) > 40)
    return {"url": url, "title": title[:200], "description": p.meta.get("og:description") or p.meta.get("description", ""),
            "published": published, "site": p.meta.get("og:site_name", ""), "text": body[:4000]}


def read_link(url: str, timeout: int = 10) -> dict:
    """Title, description, date and main text of a page a colleague shared (only that page, once)."""
    import requests
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (london-office-agent PoC)"})
    resp.raise_for_status()
    return parse_page(resp.text, url)


# -- classify ----------------------------------------------------------------------------------
def first_sentence(text: str, limit: int = 140) -> str:
    s = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0] + "…"


def classify(ctx, title: str, text: str, url: str = "", source: str = "", published: str = "") -> NewsItem:
    item = RawItem(connector="team", title=title, text=text, url=url, source=source or "Team",
                   published=published or date.today().isoformat())
    n = ctx.classifier.classify_news(item)
    n.id = "t" + hashlib.sha1(f"{url}|{title}|{text}".encode()).hexdigest()[:11]
    return n


# -- the same story? ---------------------------------------------------------------------------
def _stem(w: str) -> str:
    for suf in ("ing", "ers", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def _numbers(text: str) -> set[str]:
    out = set()
    for v, unit in re.findall(r"£?\s?(\d[\d,]*(?:\.\d+)?)\s*(bn|m|k|%|sq)?", text.lower()):
        v = v.replace(",", "")
        if len(v) >= 2 or unit:
            out.add(v.rstrip("0").rstrip(".") if "." in v else v)
    return out


_PLACES = {w for name in tx.MARKET_PARENT for w in re.findall(r"[a-z]+", name.lower())} | {
    "london", "city", "king", "kings", "cross", "square", "street", "road", "court", "house", "place", "wharf"}


def _entities(text: str) -> set[str]:
    """Names of companies and buildings: capitalised words that are not place names or generic words.
    Places are left to the market check, so two deals in the same submarket do not look alike."""
    words = re.findall(r"\b([A-Z][A-Za-z&]+)", text)
    return {w.lower() for w in words if w.lower() not in _STOP and w.lower() not in _PLACES and len(w) > 2}


def _words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP}


def _overlap(a: set, b: set) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def match_score(a: NewsItem, b: NewsItem) -> tuple[float, list[str]]:
    ta, tb = f"{a.title}. {a.body}", f"{b.title}. {b.body}"
    names = _overlap(_entities(ta), _entities(tb))
    nums = _overlap(_numbers(ta), _numbers(tb))
    words = _overlap(_words(a.title or a.body), _words(f"{b.title} {b.body}"))
    score = 0.35 * names + 0.25 * nums + 0.25 * words
    score += 0.1 if a.category == b.category and a.category != "other" else 0
    score += 0.05 if set(a.markets) & set(b.markets) else 0
    why = [w for w, v in (("same names", names), ("same figures", nums), ("same wording", words)) if v >= 0.5]
    return round(score, 2), why


def find_matches(store, item: NewsItem, limit: int = 3) -> list[dict]:
    """Stored stories most like this one, best first."""
    scored = []
    for n in store.news():
        if n.id == item.id:
            continue
        score, why = match_score(item, n)
        if score >= 0.3:
            scored.append({"id": n.id, "title": n.title, "source": n.source, "published": n.published,
                           "score": score, "why": why})
    return sorted(scored, key=lambda m: -m["score"])[:limit]


# -- save --------------------------------------------------------------------------------------
def save(store, item: NewsItem, share: dict | None = None, merge_into: str | None = None) -> tuple[NewsItem, bool]:
    """Store a new story, or merge it into an existing one: the existing story gains the colleague's
    credit or the extra outlet, keeps its first-seen time, and takes the higher importance."""
    if merge_into and (old := store.news_item(merge_into)):
        if share and not any(s["who"] == share["who"] for s in old.shared_by):
            old.shared_by.append(share)
        if not share and item.source != old.source and not any(r["source"] == item.source for r in old.also_reported):
            old.also_reported.append({"source": item.source, "url": item.url, "published": item.published})
        if share and share.get("url") and not old.url:
            old.url = share["url"]
        old.importance = max(old.importance, item.importance)
        store.add_news(old)
        return old, True
    item.discovered = item.discovered or _now()
    if share:
        item.shared_by = [share]
    store.add_news(item)
    return item, False


# -- how hot is it -----------------------------------------------------------------------------
def hotness(store, config: dict, item: NewsItem, today: date | None = None) -> tuple[int, list[str]]:
    """0-100 with the reasons, so 'hot' is never a black box."""
    today = today or date.today()
    score, why = item.importance * 10, []
    if item.importance >= 4:
        why.append(f"importance {item.importance}/5")
    people = len(item.shared_by)
    # A tip with no link is not an outlet of its own; a published story (or a shared link) is.
    outlets = (1 if item.url or not people or "Tip" not in item.source else 0) + len(item.also_reported)
    if outlets + people >= 3:
        score += 20
        why.append(f"{outlets + people} sources mention it")
    elif outlets + people == 2:
        score += 10
        why.append("2 sources mention it")
    if people:
        score += 8
        why.append("shared by " + ", ".join(f"{s['who']} ({s['how'].lower()})" for s in item.shared_by))
    try:  # when it happened; for a tip that is the day it was shared
        age = (today - date.fromisoformat((item.published or item.discovered)[:10])).days
    except ValueError:
        age = 99
    if age <= 2:
        score += 15
        why.append("new in the last 2 days")
    elif age <= 7:
        score += 8
        why.append("new this week")
    # Biggest of its kind in the last 12 months, among deals the library holds.
    one_deal = re.search(r"\b(buys|bought|acquir|sells|sold|pays|takes|signs|pre-lets|commits|let)", item.title, re.I)
    if item.category in ("leasing_deal", "investment_deal") and one_deal and age <= 365:
        since = date.fromordinal(today.toordinal() - 365).isoformat()
        peers = [n for n in store.news() if n.category == item.category and n.id != item.id
                 and since <= n.published <= today.isoformat()]
        attr, label = (("size_sqft", "letting") if item.category == "leasing_deal" else ("value_gbp_m", "deal"))
        v = getattr(item, attr)
        if v and peers and v > max((getattr(n, attr) or 0) for n in peers):
            score += 15
            why.append(f"largest {label} in the last 12 months")
    focus_markets = {m for r in store.q("SELECT data FROM user_focus") for m in _focus_markets(r["data"])}
    focus_markets |= {r["market"] for r in store.watch_rules("team")}
    hit = [m for m in item.markets if m in focus_markets or tx.top_market(m) in focus_markets]
    if hit:
        score += 10
        why.append(f"{', '.join(hit[:2])} is in the team's focus")
    if people and not item.url and not item.also_reported:
        why.append("unverified: no published source yet")
    return min(100, score), why


def _focus_markets(data: str) -> list[str]:
    import json
    try:
        return json.loads(data).get("markets", [])
    except (ValueError, AttributeError):
        return []


def score(store, config: dict, news_id: str) -> NewsItem | None:
    item = store.news_item(news_id)
    if item:
        item.hot, reasons = hotness(store, config, item)
        item.why_hot = "; ".join(reasons)
        store.add_news(item)
    return item


def rescore_all(store, config: dict) -> None:
    """Hotness decays with age and depends on the other stories, so refresh it after each collection."""
    for n in store.news():
        n.hot, reasons = hotness(store, config, n)
        n.why_hot = "; ".join(reasons)
        store.add_news(n)


# -- the whole round for one share -------------------------------------------------------------
_NOT_NEWS = re.compile(r"^\s*(now\s+)?(follow(ing|ed)?|added|subscribed|done|ok)\b", re.I)


def looks_like_market_news(text: str) -> bool:
    """A tip must say something about the market: a submarket, a size or value, or a market event.
    'Following Property Week (upload only)' is a status line, not news."""
    from .classifier import extract_size_sqft, extract_value_gbp_m
    if not text.strip() or _NOT_NEWS.match(text):
        return False
    low = f" {text.lower()} "
    return bool(tx.find_markets(text) or extract_size_sqft(text) or extract_value_gbp_m(text)
                or any(k in low for kws in tx.NEWS_CATEGORIES.values() for k in kws))


def process_share(ctx, text: str = "", url: str = "", how: str = "Other", user: str = "a colleague") -> dict:
    """A colleague shares a link or a tip: read, classify, merge with the same story or add it, score."""
    page, note = {}, ""
    if url:
        try:
            page = read_link(url)
        except Exception as e:  # paywall, blocked network: keep the colleague's words and the link
            note = f"Could not open the link ({type(e).__name__}); used the note instead."
    title = page.get("title") or first_sentence(text or url)
    body = " ".join(x for x in (text, page.get("description", ""), page.get("text", "")[:1500]) if x)
    source = page.get("site") or (re.sub(r"^www\.", "", url.split("/")[2]) if url.count("/") >= 2 else f"Tip ({how})")
    item = classify(ctx, title, body or title, url, source, page.get("published", ""))
    share = {"who": user, "how": how, "when": _now(), "note": text[:300], "url": url}
    matches = find_matches(ctx.store, item)
    same = matches[0] if matches and matches[0]["score"] >= merge_at(ctx.config) else None
    saved, merged = save(ctx.store, item, share, same["id"] if same else None)
    saved = score(ctx.store, ctx.config, saved.id)
    return {"id": saved.id, "title": saved.title, "merged": merged, "match": same, "hot": saved.hot,
            "why_hot": saved.why_hot, "category": saved.category, "markets": saved.markets,
            "shared_by": [s["who"] for s in saved.shared_by], "note": note}


def describe(res: dict, user: str) -> str:
    if res["merged"]:
        who = ", ".join(res["shared_by"])
        return (f"shared news on '{res['title']}': same story as one the team already had, so it was merged "
                f"(now credited to {who}; hot {res['hot']}).")
    return f"shared '{res['title']}' ({tx.CATEGORY_LABELS.get(res['category'], res['category'])}; hot {res['hot']})."


def process_inbox(ctx) -> list[dict]:
    out = []
    for row in ctx.store.inbox("new"):
        res = process_share(ctx, row["text"], row["url"], row["how"], row["shared_by"])
        ctx.store.close_inbox(row["id"], res["id"])
        ctx.store.log("share", row["shared_by"], describe(res, row["shared_by"]))
        out.append(res)
    return out


# -- agency report index pages: titles only, never the PDF ----------------------------------------
def report_titles(html: str) -> list[str]:
    titles = re.findall(r">\s*([^<>]{10,160}?)\s*<", html)
    keep = [t.strip() for t in titles if re.search(r"london", t, re.I) and re.search(r"office", t, re.I)
            and re.search(r"\bQ[1-4]\b|20\d\d", t)]
    return list(dict.fromkeys(keep))


def _period_of(title: str) -> str:
    q = re.search(r"\bQ([1-4])\b", title)
    y = re.search(r"(20\d\d)", title)
    return f"{y.group(1)}Q{q.group(1)}" if q and y else ""


def check_report_index(store, config: dict, fetch=None) -> list[dict]:
    """Reads only the titles on each publisher's research index page and reports the ones for a quarter
    nobody has uploaded yet, so a colleague can download and upload it."""
    import requests
    fetch = fetch or (lambda u: requests.get(u, timeout=10, headers={"User-Agent": "Mozilla/5.0"}).text)
    from .library import _quarters_back
    have: dict[str, str] = {}
    for u in store.uploads():
        have[u["publisher"]] = max(have.get(u["publisher"], ""), u["period"] or "")
    recent = _quarters_back(date.today())[-1]
    out = []
    for idx in config.get("report_index", []):
        try:
            titles = report_titles(fetch(idx["url"]))
        except Exception as e:
            out.append({"publisher": idx["publisher"], "error": type(e).__name__})
            continue
        for t in titles:
            period = _period_of(t)
            if period and period > (have.get(idx["publisher"]) or "") and period >= recent:
                out.append({"publisher": idx["publisher"], "title": t, "period": period, "url": idx["url"]})
    return out
