from core.skill import Tool, obj_schema


def get_macro(ctx, args):
    rows = ctx.store.q("SELECT * FROM macro ORDER BY date")
    rate = [r for r in rows if r["indicator"] == "bank_rate"]
    lines = []
    if rate:
        last = rate[-1]
        changes = [r for i, r in enumerate(rate) if i == 0 or r["value"] != rate[i - 1]["value"]]
        path = " -> ".join(f"{r['value']:.2f}% ({r['date'][:7]})" for r in changes)
        lines.append(f"**Bank Rate**: {last['value']:.2f}% (as of {last['date']}). Path: {path}.")
    for ind, label in [("unemployment_rate", "Unemployment rate"), ("vacancies_k", "Job vacancies (thousand)")]:
        r = [x for x in rows if x["indicator"] == ind]
        if r:
            lines.append(f"**{label}**: {r[-1]['value']:g} ({r[-1]['date']}). {r[-1]['note'] or ''}")
    lines.append("Read-across: lower rates support office values (yields) and financing; a softer jobs market "
                 "can slow office-using employment growth and leasing demand.")
    return {"summary": "\n".join(lines), "data": rows,
            "sources": [{"title": "Bank of England Bank Rate", "url": "https://www.bankofengland.co.uk/boeapps/database/"},
                        {"title": "ONS labour market overview", "url": "https://www.ons.gov.uk/employmentandlabourmarket"}],
            "chart": {"type": "step", "title": "Bank Rate", "unit": "%", "x": [r["date"] for r in rate],
                      "series": [{"name": "Bank Rate", "values": [r["value"] for r in rate]}]} if rate else None}


TOOLS = [Tool("get_macro", "Bank Rate path and latest UK labour market indicators.", obj_schema({}), get_macro)]
