"""Detects what each incoming item is and tags it.

Structured rows are recognised by their shape (observation, deal, pipeline,
macro, source). Free text is treated as news: it gets a category, the markets
and themes it touches, a sentiment for office landlords/investors and an
importance score. Rules always run; when an LLM is configured it refines the
news tags and the rules act as the fallback.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from . import taxonomy as tx
from .models import NewsItem, Observation, RawItem


@dataclass
class Classified:
    kind: str                     # observation | deal | pipeline | macro | source | news | unknown
    record: Any
    warnings: list[str] = field(default_factory=list)


_SHAPES = [
    ("observation", {"period", "market", "metric", "value"}),
    ("deal", {"deal_type", "party", "building"}),
    ("pipeline", {"scheme", "expected_completion"}),
    ("macro", {"indicator", "value", "date"}),
    ("source", {"source_id", "publisher"}),
]

_POSITIVE = ["takes", "signs", "signed", "pre-let", "pre-lets", "commits", "record", "rebound", "rebounded",
             "best quarter", "falls to", "fell to", "drops to", "rises to 14", "robust", "strong", "buys",
             "acquired", "expands", "undersupplied", "edges down"]
_NEGATIVE = ["slows", "slowed", "volatility", "dented", "dent", "softened", "rises to 1", "hands back",
             "release", "sublet", "downsiz", "vacates", "exits", "distress", "falls in value", "weaker",
             "speculative", "higher than a year earlier"]


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def extract_size_sqft(text: str) -> int | None:
    m = re.findall(r"([\d,]+(?:\.\d+)?)\s*(m)?\s*sq\.?\s*ft", text, flags=re.I)
    sizes = [_num(v) * (1_000_000 if mil else 1) for v, mil in m]
    deal_sizes = [s for s in sizes if 1_000 <= s < 2_000_000]
    return int(max(deal_sizes)) if deal_sizes else None


def extract_value_gbp_m(text: str) -> float | None:
    m = re.search(r"£\s?([\d,.]+)\s?(m|bn)\b", text, flags=re.I)
    if not m:
        return None
    v = _num(m.group(1))
    return v * 1000 if m.group(2).lower() == "bn" else v


def news_id(item) -> str:
    return item.meta.get("id") or hashlib.sha1((item.url + item.title).encode()).hexdigest()[:12]


class Classifier:
    def __init__(self, llm=None, use_llm: bool = True):
        self.llm = llm if (llm and use_llm and llm.available) else None

    def classify(self, item: RawItem) -> Classified:
        if item.payload:
            return self._classify_row(item)
        if item.text or item.title:
            return Classified("news", self.classify_news(item))
        return Classified("unknown", item)

    # -- structured rows ----------------------------------------------------
    def _classify_row(self, item: RawItem) -> Classified:
        row = {k: (v.strip() if isinstance(v, str) else v) for k, v in item.payload.items()}
        keys = {k for k, v in row.items() if v not in (None, "")}
        for kind, needed in _SHAPES:
            if needed <= keys:
                break
        else:
            return Classified("unknown", row, [f"Unrecognised row shape: {sorted(keys)}"])
        warnings: list[str] = []
        if kind == "observation":
            market, exact = tx.resolve_market(row["market"])
            if market is None:
                return Classified("unknown", row, [f"Unknown market '{row['market']}'"])
            if not exact:
                warnings.append(f"'{row['market']}' mapped to '{market}' - boundaries may differ")
            if row["metric"] not in tx.METRICS:
                return Classified("unknown", row, [f"Unknown metric '{row['metric']}'"])
            lta = row.get("lta")
            rec = Observation(period=row["period"], market=market, metric=row["metric"], value=float(row["value"]),
                              lta=float(lta) if lta not in (None, "") else None,
                              source_id=row.get("source_id", item.connector), note=row.get("note", "") or "")
            return Classified("observation", rec, warnings)
        if kind in ("deal", "pipeline"):
            field_name = "submarket"
            market, exact = tx.resolve_market(row.get(field_name, ""))
            if market:
                row[field_name] = market
            for k in ("size_sqft", "rent_psf", "price_gbp_m", "yield_pct"):
                if k in row:
                    row[k] = float(row[k]) if row[k] not in (None, "") else None
            return Classified(kind, row, warnings)
        if kind == "macro":
            row["value"] = float(row["value"])
            row.setdefault("unit", ""); row.setdefault("note", ""); row.setdefault("source_id", item.connector)
        return Classified(kind, row, warnings)

    # -- free text ----------------------------------------------------------
    def classify_news(self, item: RawItem) -> NewsItem:
        text = f"{item.title}. {item.text}"
        low = f" {text.lower()} "
        scores = {cat: sum(low.count(k) for k in kws) for cat, kws in tx.NEWS_CATEGORIES.items()}
        # Headline verbs are the strongest clue for deals.
        title_low = item.title.lower()
        if any(k in title_low for k in ["buys", "acquire", "sells", "for £"]):
            scores["investment_deal"] += 3
        if any(k in title_low for k in ["takes", "signs", "pre-let", "commits", "lets "]):
            scores["leasing_deal"] += 3
        category = max(scores, key=scores.get) if max(scores.values()) > 0 else "other"
        themes = [t for t, kws in tx.THEMES.items() if any(k in low for k in kws)]
        markets = tx.find_markets(text)
        pos = sum(low.count(k) for k in _POSITIVE)
        neg = sum(low.count(k) for k in _NEGATIVE)
        sentiment = "positive" if pos > neg else "negative" if neg > pos else "neutral"
        size = extract_size_sqft(text)
        value = extract_value_gbp_m(text)
        importance = {"macro_policy": 3, "market_stats": 3, "investment_deal": 2, "leasing_deal": 2,
                      "development_pipeline": 2}.get(category, 1)
        if size and size >= 100_000:
            importance += 1
        if size and size >= 250_000:
            importance += 1
        if value and value >= 200 and category == "investment_deal":
            importance += 1 if value < 500 else 2
        if "record" in low or "best quarter" in low:
            importance += 1
        news = NewsItem(
            id=news_id(item),
            title=item.title, body=item.text, url=item.url, source=item.source, published=item.published,
            category=category, markets=markets, themes=themes, sentiment=sentiment,
            importance=min(importance, 5), size_sqft=size, value_gbp_m=value)
        if self.llm:
            self._refine_with_llm(news)
        return news

    def _refine_with_llm(self, news: NewsItem):
        prompt = (
            "Classify this London office market news item for a commercial real estate investment team.\n"
            f"Title: {news.title}\nBody: {news.body}\n\n"
            "Return JSON with keys: category (one of " + ", ".join(tx.CATEGORY_LABELS) + "), "
            "markets (list of London office submarkets mentioned, e.g. 'City Core', 'Canary Wharf', 'West End Core'), "
            "themes (subset of " + ", ".join(tx.THEMES) + "), "
            "sentiment (positive/negative/neutral for office landlords and investors), "
            "importance (1-5, where 5 means the business team must know today)."
        )
        try:
            out = self.llm.complete_json(prompt)
        except Exception:
            return  # rules result stands
        if not isinstance(out, dict):
            return
        if out.get("category") in tx.CATEGORY_LABELS:
            news.category = out["category"]
        mk = [tx.resolve_market(m)[0] for m in out.get("markets", []) if isinstance(m, str)]
        if any(mk):
            news.markets = list(dict.fromkeys(m for m in mk if m))
        th = [t for t in out.get("themes", []) if t in tx.THEMES]
        if th:
            news.themes = th
        if out.get("sentiment") in ("positive", "negative", "neutral"):
            news.sentiment = out["sentiment"]
        if isinstance(out.get("importance"), (int, float)):
            news.importance = max(1, min(5, int(out["importance"])))
        news.classified_by = "llm"
