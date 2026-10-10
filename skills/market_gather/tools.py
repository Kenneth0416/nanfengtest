from core import follow, gather
from core import taxonomy as tx
from core.skill import Tool, obj_schema

HOW = {"type": "string", "enum": gather.HOW, "description": "Where the colleague got it"}


def _item(ctx, args):
    n = gather.classify(ctx, args.get("title") or gather.first_sentence(args.get("text", "")), args.get("text", ""),
                        args.get("url", ""), args.get("source", ""), args.get("published", ""))
    # The agent may correct the rule-based classification.
    if args.get("category") in tx.CATEGORY_LABELS:
        n.category = args["category"]
    if args.get("markets"):
        n.markets = [m for m in (tx.resolve_market(x)[0] for x in args["markets"]) if m] or n.markets
    if args.get("importance"):
        n.importance = max(1, min(5, int(args["importance"])))
    return n


def share_tip(ctx, args):
    text = args.get("text", "")
    if not args.get("url") and not gather.looks_like_market_news(text):
        return {"summary": "Not filed: that is not market news (no submarket, building, occupier, deal, figure or "
                           "market event in it). Following a source, a confirmation or a status line is not a tip.",
                "data": {"filed": False}}
    res = gather.process_share(ctx, args.get("text", ""), args.get("url", ""), args.get("how", "Other"), ctx.role)
    ctx.store.log("share", ctx.role, gather.describe(res, ctx.role))
    head = (f"Same story as **{res['title']}**, which the team already had: merged and credited to "
            f"{', '.join(res['shared_by'])}." if res["merged"] else f"New for the team: **{res['title']}**.")
    return {"summary": f"{head} Hot {res['hot']}/100: {res['why_hot'] or 'routine'}. {res['note']}".strip(), "data": res}


def list_inbox(ctx, args):
    rows = ctx.store.inbox("new")
    if not rows:
        return {"summary": "The team inbox is empty.", "data": []}
    return {"summary": "\n".join(f"- #{r['id']} {r['shared_by']} ({r['how']}): {r['text'][:120]} {r['url']}" for r in rows),
            "data": rows}


def read_link(ctx, args):
    # The Pi gatherer fetches the page itself and passes the HTML; the Python engine fetches here.
    page = gather.parse_page(args["html"], args["url"]) if args.get("html") else gather.read_link(args["url"])
    return {"summary": f"**{page['title']}** ({page['site'] or args['url']}, {page['published'] or 'no date'})\n"
                       f"{page['description']}\n\n{page['text'][:1500]}", "data": page}


def classify_item(ctx, args):
    n = _item(ctx, args)
    return {"summary": f"{tx.CATEGORY_LABELS.get(n.category, n.category)}; markets {', '.join(n.markets) or 'London-wide'}; "
                       f"themes {', '.join(n.themes) or '-'}; {n.sentiment}; importance {n.importance}/5",
            "data": {k: getattr(n, k) for k in ("category", "markets", "themes", "sentiment", "importance",
                                                "size_sqft", "value_gbp_m")}}


def find_matches(ctx, args):
    m = gather.find_matches(ctx.store, _item(ctx, args))
    if not m:
        return {"summary": "No similar story in the library: this is new.", "data": []}
    return {"summary": "\n".join(f"- {x['id']} score {x['score']} ({', '.join(x['why']) or 'weak'}): {x['title']} "
                                 f"({x['source']}, {x['published']})" for x in m), "data": m}


def save_item(ctx, args):
    n = _item(ctx, args)
    who = args.get("shared_by") or (ctx.role if args.get("inbox_id") is None and ctx.role != "team" else "")
    share = {"who": who, "how": args.get("how", "Other"), "when": gather._now(), "note": args.get("text", "")[:300],
             "url": args.get("url", "")} if who else None
    saved, merged = gather.save(ctx.store, n, share, args.get("merge_into"))
    res = {"id": saved.id, "title": saved.title, "merged": merged, "shared_by": [s["who"] for s in saved.shared_by],
           "category": saved.category, "hot": saved.hot}
    if args.get("inbox_id"):
        ctx.store.close_inbox(int(args["inbox_id"]), saved.id)
    if who:
        ctx.store.log("share", who, gather.describe(res, who))
    return {"summary": ("Merged into " if merged else "Saved as ") + f"{saved.id}: {saved.title}", "data": res}


def score_hotness(ctx, args):
    n = gather.score(ctx.store, ctx.config, args["id"])
    if not n:
        return {"summary": f"No story {args['id']}.", "data": None}
    return {"summary": f"Hot {n.hot}/100: {n.why_hot or 'routine'}", "data": {"id": n.id, "hot": n.hot, "why": n.why_hot}}


def collect_open_data(ctx, args):
    app = ctx.app  # the connectors live on the app
    reports = app.refresh(by="Gatherer") if app else []
    return {"summary": "; ".join(f"{r['connector']}: {r.get('error') or r['counts']}" for r in reports) or "No feeds.",
            "data": reports}


def check_report_index(ctx, args):
    pages = args.get("pages") or {}  # url -> html, when the Pi gatherer already fetched the pages
    found = gather.check_report_index(ctx.store, ctx.config, fetch=(lambda u: pages[u]) if pages else None)
    new = [f for f in found if "title" in f]
    errs = [f"{f['publisher']} ({f['error']})" for f in found if "error" in f]
    lines = [f"- {f['publisher']} {f['period']}: '{f['title']}' is listed and nobody has uploaded it." for f in new]
    if errs:
        lines.append("Could not read: " + ", ".join(errs))
    return {"summary": "\n".join(lines) or "No new agency report titles.", "data": found}


def follow_source(ctx, args):
    """Check a source's terms and follow it for the whole team (auto or upload)."""
    src = follow.resolve(args.get("source", "") or args.get("url", ""))
    if not src["url"]:
        return {"summary": f"I don't know where '{src['name']}' is published. Paste its link and I'll check its terms.",
                "data": src}
    if args.get("name"):
        src["name"] = args["name"]
    # The Pi tool passes what it fetched (robots, page, terms); otherwise fetch here.
    ev = {k: args[k] for k in ("robots", "page", "content_type", "terms", "terms_url") if k in args}
    if not ev:
        ev = follow.fetch_evidence(src["url"])
        ev.pop("url", None)
    verdict = follow.assess(src["url"], **ev)
    if args.get("propose"):  # show the plan first; nothing is saved until someone adds it for the team
        p = follow.proposal(ctx.store, src, verdict, args.get("cadence", ""))
        return {"summary": f"**{p['name']}**: {'collected automatically' if p['channel'] == 'auto' else 'upload-only'}"
                           f" ({p['licence']}). {p['how']} Adds: {p['adds']}. Nothing is added until you confirm.",
                "data": {**p, "evidence": ev}}
    row = follow.follow(ctx.store, src, verdict, ctx.role, args.get("cadence", ""))
    if row["already"]:
        return {"summary": f"{row['added_by']} already follows **{row['name']}** for the team "
                           f"({'collected automatically' if row['channel'] == 'auto' else 'uploaded by the team'}).",
                "data": row}
    if row["channel"] == "auto":
        head = (f"Following **{row['name']}** for the whole team. The agent collects it {row['cadence']} "
                f"({'feed items' if row['kind'] == 'rss' else 'headlines and links only'}).")
    else:
        head = (f"Following **{row['name']}** for the whole team as upload-only: the agent won't fetch it, and "
                f"the team is reminded to upload each {row['cadence']} issue.")
    why = row["reason"] + (f' Terms: "{row["quote"]}"' if row["quote"] else "")
    return {"summary": f"{head}\n\nWhy: {why}", "data": row}


def resolve_source(ctx, args):
    src = follow.resolve(args.get("source", ""))
    return {"summary": f"{src['name']}: {src['url'] or 'no known link'}", "data": src}


def list_followed(ctx, args):
    rows = ctx.store.q("SELECT * FROM followed ORDER BY ts DESC")
    if not rows:
        return {"summary": "The team doesn't follow any extra sources yet.", "data": []}
    return {"summary": "\n".join(f"- {r['name']} ({'open data' if r['channel'] == 'auto' else 'uploaded'}, {r['cadence']}, "
                                 f"added by {r['added_by']}): {r['licence']}" for r in rows), "data": rows}


TEXT = {"title": {"type": "string"}, "text": {"type": "string"}, "url": {"type": "string"},
        "source": {"type": "string"}, "published": {"type": "string", "description": "YYYY-MM-DD"},
        "category": {"type": "string", "enum": list(tx.CATEGORY_LABELS)},
        "markets": {"type": "array", "items": {"type": "string"}}, "importance": {"type": "integer"}}

TOOLS = [
    Tool("follow_source", "Follow a new information source for the whole team, from a link or a name ('follow Savills "
         "Market Watch'). Checks its terms first: allowed sources are collected automatically, restricted ones become "
         "upload-only with reminders to the team.",
         obj_schema({"source": {"type": "string", "description": "a link, or the source's name"},
                     "name": {"type": "string"}, "cadence": {"type": "string", "enum": list(follow.CADENCE_DAYS)},
                     "propose": {"type": "boolean", "description": "only show the plan (licence, how it is read, "
                                 "cadence, what it adds); save nothing"}}, ["source"]), follow_source, read_only=False),
    Tool("resolve_source", "Find the web address of a source named in words ('Savills Market Watch').",
         obj_schema({"source": {"type": "string"}}, ["source"]), resolve_source),
    Tool("list_followed", "Sources the team follows, how each is collected, and who added it.", obj_schema({}),
         list_followed),
    Tool("share_tip", "A colleague shares a link or something they heard: read, classify, merge with the same "
         "story or add it, credit them and score how hot it is. Use when someone says they heard or saw something.",
         obj_schema({"text": {"type": "string"}, "url": {"type": "string"}, "how": HOW}), share_tip, read_only=False),
    Tool("list_inbox", "Links and tips colleagues shared that have not been processed yet.", obj_schema({}), list_inbox),
    Tool("read_link", "Read one shared web page: title, site, date, description and main text.",
         obj_schema({"url": {"type": "string"}, "html": {"type": "string"}}, ["url"]), read_link),
    Tool("classify_item", "Classify a story or tip: category, markets, themes, sentiment, importance, size and value.",
         obj_schema(TEXT), classify_item),
    Tool("find_matches", "Find stories the team library already holds that look like the same event, with a score "
         "(0.55 or more means the same story) and why.", obj_schema(TEXT), find_matches),
    Tool("save_item", "Save a story to the shared library, or merge it into an existing one with merge_into. "
         "shared_by and how credit the colleague; inbox_id closes their inbox item.",
         obj_schema({**TEXT, "merge_into": {"type": "string"}, "shared_by": {"type": "string"}, "how": HOW,
                     "inbox_id": {"type": "integer"}}, ["title"]), save_item, read_only=False),
    Tool("score_hotness", "Score how hot a stored story is (0-100) and why: importance, how many sources, who shared "
         "it, how new, biggest of its kind, and whether it is in the team's focus.",
         obj_schema({"id": {"type": "string"}}, ["id"]), score_hotness),
    Tool("collect_open_data", "Collect every open-data feed now (Bank of England, news RSS...).", obj_schema({}),
         collect_open_data, read_only=False),
    Tool("check_report_index", "Check agency research index pages for new London office report titles nobody has "
         "uploaded (titles only; nothing is downloaded).",
         obj_schema({"pages": {"type": "object", "description": "url -> html, if already fetched"}}), check_report_index),
]
