from core import taxonomy as tx
from core.models import RawItem
from core.skill import Tool, obj_schema
from skills._common import market_arg


def _fmt(n):
    tags = ", ".join(n.markets[:3]) or "London-wide"
    themes = f"; themes: {', '.join(n.themes)}" if n.themes else ""
    return (f"- **{n.title}** ({n.published}, {n.source}) - {tx.CATEGORY_LABELS.get(n.category, n.category)}, "
            f"{tags}, importance {n.importance}/5, {n.sentiment}{themes}")


def search_news(ctx, args):
    items = ctx.store.news()
    if args.get("market"):
        market = market_arg(args["market"])[0]
        items = [n for n in items if market in n.markets or any(tx.top_market(m) == market or
                 tx.MARKET_PARENT.get(m) == market for m in n.markets)]
    if args.get("category"):
        items = [n for n in items if n.category == args["category"]]
    if args.get("theme"):
        items = [n for n in items if args["theme"] in n.themes]
    if args.get("query"):
        words = [w for w in args["query"].lower().split() if len(w) > 2]
        items = [n for n in items if any(w in (n.title + " " + n.body).lower() for w in words)]
    if args.get("min_importance"):
        items = [n for n in items if n.importance >= args["min_importance"]]
    items = items[: args.get("limit", 8)]
    if not items:
        return {"summary": "No matching news.", "data": []}
    return {"summary": "**News**\n" + "\n".join(_fmt(n) for n in items),
            "data": [n.__dict__ for n in items],
            "sources": [{"title": n.title, "url": n.url} for n in items]}


def classify_text(ctx, args):
    n = ctx.classifier.classify_news(RawItem(connector="user", title=args.get("title", ""), text=args.get("text", "")))
    return {"summary": "**Classification**\n" + _fmt(n) + f"\n(classified by {n.classified_by})", "data": n.__dict__}


TOOLS = [
    Tool("search_news", "Search classified office market news by market, category, theme, keyword or importance.",
         obj_schema({"query": {"type": "string"}, "market": {"type": "string"},
                     "category": {"type": "string", "enum": list(tx.CATEGORY_LABELS)},
                     "theme": {"type": "string", "enum": list(tx.THEMES)},
                     "min_importance": {"type": "integer"}, "limit": {"type": "integer"}}), search_news),
    Tool("classify_text", "Classify a pasted headline or article: category, markets, themes, sentiment, importance.",
         obj_schema({"title": {"type": "string"}, "text": {"type": "string"}}, ["title"]), classify_text),
]
