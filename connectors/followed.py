"""Sources colleagues chose to follow whose terms allow automated collection (see core/follow.py).

An RSS feed is read in full; a web page is watched for new headlines, keeping only titles and links.
Upload-only sources are never fetched here."""
from __future__ import annotations

import html
import json
import re
from datetime import date

import feedparser
import requests

from core.follow import UA, headlines
from core.models import RawItem
from core.skill import Connector as Base


class Connector(Base):
    id = "followed_sources"

    def fetch(self) -> list[RawItem]:
        store = self.ctx.store
        items, errors = [], []
        rows = store.q("SELECT * FROM followed WHERE channel='auto'")
        for f in rows:
            try:
                resp = requests.get(f["url"], timeout=self.options.get("timeout", 10), headers={"User-Agent": UA})
                resp.raise_for_status()
            except Exception as e:
                errors.append(f"{f['name']}: {type(e).__name__}")
                continue
            seen = set(json.loads(f["seen"] or "[]"))
            if f["kind"] == "rss":
                found = [(html.unescape(e.get("title", "")).strip(), e.get("link", ""),
                          re.sub(r"<[^>]+>", " ", html.unescape(e.get("summary", ""))))
                         for e in feedparser.parse(resp.content).entries[:20]]
            else:
                found = [(t, u, "") for t, u in headlines(resp.text, f["url"])]
            for title, url, summary in found:
                if title and url not in seen:
                    seen.add(url)
                    items.append(RawItem(connector=self.id, title=title, text=summary.strip(), url=url,
                                         source=f["name"], published=date.today().isoformat()))
            store.db.execute("UPDATE followed SET seen=? WHERE id=?", (json.dumps(sorted(seen)[-500:]), f["id"]))
            store.db.commit()
        if rows and not items and len(errors) == len(rows):
            raise ConnectionError(f"All followed sources failed: {errors[0]}")
        return items
