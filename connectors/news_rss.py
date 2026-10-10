"""Live news from RSS feeds (Google News search feeds by default)."""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import requests

from core.models import RawItem
from core.skill import Connector as Base

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-GB&gl=GB&ceid=GB:en"


class Connector(Base):
    id = "news_rss"

    def fetch(self) -> list[RawItem]:
        feeds = [GOOGLE_NEWS.format(q=quote_plus(q + " when:30d")) for q in self.options.get("queries", [])]
        feeds += self.options.get("feeds", [])
        max_age = timedelta(days=self.options.get("max_age_days", 30))
        now = datetime.now(timezone.utc)
        items, seen, errors = [], set(), []
        for url in feeds:
            try:
                resp = requests.get(url, timeout=self.options.get("timeout", 10),
                                    headers={"User-Agent": "Mozilla/5.0 (london-office-agent PoC)"})
                resp.raise_for_status()
            except Exception as e:
                errors.append(str(e))
                continue
            for e in feedparser.parse(resp.content).entries[: self.options.get("per_feed", 15)]:
                title = html.unescape(e.get("title", "")).strip()
                if not title or title.lower() in seen:
                    continue
                seen.add(title.lower())
                published = ""
                if e.get("published_parsed"):
                    dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
                    if now - dt > max_age:
                        continue
                    published = dt.strftime("%Y-%m-%d")
                summary = re.sub(r"<[^>]+>", " ", html.unescape(e.get("summary", "")))
                source = e.get("source", {}).get("title", "") if isinstance(e.get("source"), dict) else ""
                items.append(RawItem(connector=self.id, title=title, text=re.sub(r"\s+", " ", summary).strip(),
                                     url=e.get("link", ""), published=published, source=source or "RSS"))
        if not items and errors:
            raise ConnectionError(f"All feeds failed: {errors[0][:120]}")
        return items
