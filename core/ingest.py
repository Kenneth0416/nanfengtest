"""Connector -> classifier -> store pipeline."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .classifier import Classifier, news_id
from .skill import Context


CLASSIFY_WORKERS = 6




def ingest_items(ctx: Context, items: list, connector_id: str = "") -> dict:
    """Classify and store items. Returns counts per detected kind and warnings.

    News the library already holds is skipped before any model call (a round used to re-send every
    stored story to the model), and the new stories are classified a few at a time in parallel."""
    clf: Classifier = ctx.classifier
    counts, warnings, observations = Counter(), [], []
    fresh = []
    for item in items:
        if not item.payload and (item.text or item.title) and ctx.store.news_item(news_id(item)):
            counts["news_already_held"] += 1
        else:
            fresh.append(item)
    news = [it for it in fresh if not it.payload and (it.text or it.title)]
    with ThreadPoolExecutor(max_workers=CLASSIFY_WORKERS) as pool:
        classified = dict(zip((id(it) for it in news), pool.map(clf.classify, news)))
    for item in fresh:
        c = classified.get(id(item)) or clf.classify(item)
        counts[c.kind] += 1
        warnings += c.warnings
        if c.kind == "observation":
            observations.append(c.record)
        elif c.kind == "deal":
            ctx.store.add_deal(c.record)
        elif c.kind == "pipeline":
            ctx.store.add_pipeline(c.record)
        elif c.kind == "macro":
            ctx.store.add_macro(c.record)
        elif c.kind == "source":
            ctx.store.add_source(c.record)
        elif c.kind == "news":
            add_news(ctx, c.record)
    if observations:
        ctx.store.add_observations(observations)
    return {"connector": connector_id, "counts": dict(counts), "warnings": warnings}


def add_news(ctx: Context, item) -> None:
    """New stories only: a story already held keeps its team credits; the same story from another
    outlet is merged into the first one ("also reported by") instead of showing twice."""
    from . import gather
    if ctx.store.news_item(item.id):
        return
    matches = gather.find_matches(ctx.store, item, limit=1)
    same = matches[0]["id"] if matches and matches[0]["score"] >= gather.merge_at(ctx.config) else None
    gather.save(ctx.store, item, merge_into=same)


def refresh(ctx: Context, connectors: list) -> list[dict]:
    """Run every enabled connector. A failing source never blocks the others."""
    reports = []
    for conn in connectors:
        try:
            items = conn.fetch()
            rep = ingest_items(ctx, items, conn.id)
            detail = ", ".join(f"{v} {k}" for k, v in rep["counts"].items()) or "no new items"
            ctx.store.set_status(conn.id, "ok", detail)
        except Exception as e:
            rep = {"connector": conn.id, "counts": {}, "warnings": [], "error": str(e)}
            ctx.store.set_status(conn.id, "unavailable", str(e)[:200])
        reports.append(rep)
    from .gather import rescore_all
    rescore_all(ctx.store, ctx.config)
    return reports
