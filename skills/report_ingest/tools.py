from core import documents
from core import taxonomy as tx
from core.skill import Tool, obj_schema


def ingest_report(ctx, args):
    if args.get("save") and (dup := documents.duplicate_of(ctx.store, args["path"])):
        return {"summary": f"{dup['uploaded_by'] or 'A colleague'} already uploaded {dup['publisher']} "
                           f"{dup['period']} on {dup['uploaded_at'][:10]}; it is in the team library, so nothing "
                           "was added again.", "data": dup}
    analysis = documents.analyse_document(ctx.store, ctx.vision or ctx.llm, args["path"])
    lines = [f"**{analysis['publisher']} report, period {analysis['period']}** "
             f"({len(analysis['candidates'])} figures extracted with {analysis['method']})"]
    for c in analysis["candidates"]:
        flag = " ⚠ " + " ".join(c["flags"]) if c["flags"] else ""
        lines.append(f"- {c['market']} {tx.METRICS[c['metric']]['label']}: {tx.fmt_value(c['metric'], c['value'])}{flag}")
    if args.get("save"):
        res = documents.save_document(ctx.store, analysis, user=ctx.role)
        lines.append(f"Shared {res['saved']} figures with the team as source {res['source_id']}; "
                     f"{res['flagged']} are marked ⚠ until someone checks them.")
        ctx.store.log("upload", ctx.role, f"uploaded {analysis['publisher']} {analysis['period']}: "
                      f"{res['saved']} figures, {res['flagged']} to check")
    else:
        lines.append("Not saved yet: review the flags, then save.")
    return {"summary": "\n".join(lines), "data": analysis}


TOOLS = [Tool("ingest_report", "Extract figures from a research PDF on disk and compare them with stored data; save=true stores them.",
              obj_schema({"path": {"type": "string"}, "save": {"type": "boolean"}}, ["path"]), ingest_report)]
