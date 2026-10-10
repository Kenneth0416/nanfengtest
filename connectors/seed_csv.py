"""Curated dataset restated from public research reports (see reference/seed/sources.csv).

Rows are handed to the classifier untyped: it recognises observations, deals,
pipeline schemes, macro points and sources from their columns.
"""
from __future__ import annotations

import csv
import json

from core.models import RawItem
from core.skill import Connector as Base


class Connector(Base):
    id = "seed_csv"

    def fetch(self) -> list[RawItem]:
        folder = self.ctx.root / self.options.get("path", "reference/seed")
        items: list[RawItem] = []
        for path in sorted(folder.glob("*.csv")):
            with open(path, newline="") as f:
                items += [RawItem(connector=self.id, payload=row) for row in csv.DictReader(f)]
        news_file = folder / "news.json"
        if news_file.exists():
            for n in json.loads(news_file.read_text()):
                items.append(RawItem(connector=self.id, title=n["title"], text=n["body"], url=n["url"],
                                     published=n["published"], source=n["source"], meta={"id": n["id"]}))
        return items
