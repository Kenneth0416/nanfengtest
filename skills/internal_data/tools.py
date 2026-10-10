"""🔵 Internal data tools for the Copilot: record one of our deals from a sentence, list, confirm, mark.
The photo / PDF / spreadsheet routes are in skills/info_processing (read_photo, deals_from_table) and on
the Sources page; all routes end in core.internal.record, so a record has one shape."""
from __future__ import annotations

from core import internal as I
from core.skill import Tool, obj_schema

FIELD_PROPS = {k: {"type": "string"} for k in I.FIELDS}


def _card(d: dict) -> str:
    lines = [f"**{d['property'] or 'Property not named'}**" + (f" · {d['submarket']}" if d.get("submarket") else "")
             + f" · {I.LEVELS[d.get('confidentiality', 'internal')]} · {'confirmed' if d.get('status') == 'confirmed' else 'draft'}"]
    lines += [f"- {I.LABELS[k]}: {d.get(k) or '_missing_'}" for k in I.FIELDS if k != "property"]
    lines.append("- Recorded by: " + "; ".join(f"{w} ({h}, {t})" for w, h, t in d.get("recorded_by", [])))
    if d.get("ext"):
        lines.append(f"- ⚠ {d['ext']['text']}")
    return "\n".join(lines)


def record_deal(ctx, args):
    """One sentence (or the fields the Copilot understood) about one of our deals -> a record, merged if the
    team already has that property and floor."""
    text = args.get("text") or ""
    fields = I.parse_deal_text(text) if text else {}
    for k in I.FIELDS + ["submarket"]:
        if args.get(k):
            fields[k] = args[k]
    if not fields.get("property"):
        return {"summary": "I could not tell which property this is. Say the building (e.g. '8 Bishopsgate, 12th floor') "
                           "and I will record it.", "data": {"recorded": False, "fields": fields}}
    res = I.record(ctx.store, fields, ctx.role, "said to Copilot" if text else "fields from Copilot")
    d = res["deal"]
    ctx.store.log("internal", ctx.role, (f"added to our record for {d['property']} (merged, filled {', '.join(res['filled']) or 'nothing new'})"
                                         if res["merged"] else f"recorded an internal deal: {d['property']}"
                                         + (f" (draft, {len(d['missing'])} fields missing)" if d["missing"] else "")))
    head = (f"Merged into the record the team already had for **{d['property']}** (same property and floor); "
            f"filled {', '.join(I.LABELS[k] for k in res['filled']) or 'nothing new'}."
            if res["merged"] else f"Recorded as one of our deals, 🔵 internal only, visible to the team.")
    if d["missing"]:
        head += f" Still missing: {', '.join(I.LABELS[k] for k in d['missing'])}; a photo of the lease or one more sentence fills them."
    head += f" {ctx.role} confirms it on Sources › 🔵 Internal data."
    return {"summary": head + "\n\n" + _card(d), "data": {"recorded": True, "merged": res["merged"], "deal": d}}


def list_our_deals(ctx, args):
    deals = ctx.store.internal_deals()
    if args.get("status"):
        deals = [d for d in deals if d.get("status") == args["status"]]
    if args.get("submarket"):
        deals = [d for d in deals if args["submarket"].lower() in (d.get("submarket") or "").lower()]
    if not deals:
        return {"summary": "No internal records yet. Anyone can add one: tell me a deal, or drop a photo, PDF or "
                           "spreadsheet on Sources › 🔵 Internal data.", "data": []}
    return {"summary": f"{len(deals)} of our deals (🔵 internal; {sum(d.get('status') == 'draft' for d in deals)} draft):\n\n"
                       + "\n\n".join(_card(d) for d in deals[: args.get("limit", 8)]), "data": deals}


def confirm_deal(ctx, args):
    d = ctx.store.internal_deal(int(args["id"]))
    if not d:
        return {"summary": "No record with that id.", "data": None}
    d = I.confirm(ctx.store, d["id"], ctx.role)
    ctx.store.log("internal", ctx.role, f"confirmed our record for {d['property']}")
    return {"summary": f"Confirmed: {d['property']} ({I.LEVELS[d['confidentiality']]}).", "data": d}


def set_deal_confidentiality(ctx, args):
    d = ctx.store.internal_deal(int(args["id"]))
    if not d:
        return {"summary": "No record with that id.", "data": None}
    d = I.set_confidentiality(ctx.store, d["id"], args["level"], ctx.role)
    ctx.store.log("internal", ctx.role, f"marked our record for {d['property']} {args['level']}")
    return {"summary": f"{d['property']} is now {I.LEVELS[d['confidentiality']]}"
                       + (": it can be quoted in the IC paper and externally." if d["confidentiality"] == "quotable"
                          else ": filtered out of anything exported."), "data": d}


TOOLS = [
    Tool("record_deal", "Record one of OUR OWN deals (a letting, lease, sale or valuation the company did) from the "
                        "person's sentence; pass fields you understood as well. Merged into the existing record for "
                        "the same property and floor; saved as a draft when fields are missing. Never for market news.",
         obj_schema({"text": {"type": "string"}, "submarket": {"type": "string"}, **FIELD_PROPS}), record_deal, read_only=False),
    Tool("list_our_deals", "Our own deal records (🔵 internal): fields, who recorded them, drafts, external comparisons.",
         obj_schema({"status": {"type": "string", "enum": ["draft", "confirmed"]}, "submarket": {"type": "string"},
                     "limit": {"type": "integer"}}), list_our_deals),
    Tool("confirm_deal", "The recorder confirms an internal record is right.", obj_schema({"id": {"type": "integer"}}, ["id"]),
         confirm_deal, read_only=False),
    Tool("set_deal_confidentiality", "Mark an internal record 'quotable' (may be cited externally and in the IC paper) "
                                     "or 'internal' (never leaves the company).",
         obj_schema({"id": {"type": "integer"}, "level": {"type": "string", "enum": ["internal", "quotable"]}}, ["id", "level"]),
         set_deal_confidentiality, read_only=False),
]
