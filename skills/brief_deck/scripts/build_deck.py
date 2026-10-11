"""Render a team-brief deck from a slide spec onto one of the themed templates.

    python3 build_deck.py --data brief.json [--spec spec.json] [--theme navy-gold] --out deck.pptx

brief.json is what the PoC's `brief_deck_data` tool returns in `data` (figures, series, cards, footnotes).
spec.json is the storyline the agent writes (references/storyline.md); without it the default spec is used.
Themes and their colours are in themes/themes.json; each has templates/<theme>.pptx with thirteen layouts.

The spec chooses theme, layouts, order, eyebrows, titles, labels, takeaways, so-what lines and notes.
Figures never come from the spec: charts, tables, KPI cards, signal cards and footnotes are named by key
({"chart": "vacancy"}) and drawn from brief.json, and any number in spec text that brief.json does not
contain is refused (check_text). In a title or statement, *words in asterisks* take the theme's accent.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import uuid
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt, Emu

HERE = Path(__file__).resolve().parent.parent
BRAND = HERE.parent.parent / "assets" / "brand"  # the app logo and the Nan Fung co-brand (python-pptx takes PNG, not SVG)


def brand_marks(slide, layout_name: str, prs):
    """The co-brand lockup (app logo | Nan Fung Group) at the top right of the cover, on the transparent
    render so it sits on every theme's dark cover, and the small app icon beside the slide number on content
    slides. Both are skipped quietly when the files are not there, so a copy without assets still builds."""
    right = prs.slide_width - Inches(0.7)
    if layout_name == "Cover":
        png = BRAND / "cobrand-nanfung-on-dark@2x.png"
        if png.exists():
            pic = slide.shapes.add_picture(str(png), 0, Inches(0.38), height=Inches(0.62))
            pic.left = right + Inches(0.12) - pic.width  # the render carries its own clear space
            pic.name = "co-brand"
    elif layout_name not in ("Section",):
        png = BRAND / "app-icon-1024.png"
        if png.exists():
            pic = slide.shapes.add_picture(str(png), Inches(11.6), Inches(7.06), height=Inches(0.3))
            pic.name = "app icon"
THEMES = json.loads((HERE / "themes" / "themes.json").read_text())
DEFAULT_THEME = "navy-gold"
LAYOUTS = ["Cover", "Section", "Statement", "Hero number", "Stat row", "Chart + takeaway", "Two charts",
           "Chart + table", "Numbered pillars", "Timeline", "Signal cards", "Sources", "Title only"]
CHARTS = ["vacancy", "take_up", "rents", "investment"]
TABLES = ["yields", "evidence", "deals"]
HEROES = ["vacancy_pct", "take_up_msqft", "investment_gbp_bn", "active_requirements_msqft", "bank_rate"]
MIN_SLIDES, MAX_SLIDES = 3, 12  # a brief plans 3-6; the slide editor may grow one to 12
PLAN_MAX = 6
SO_WHAT_LAYOUTS = {"Hero number", "Stat row", "Chart + takeaway", "Two charts", "Chart + table", "Numbered pillars",
                   "Timeline", "Title only"}
KEYS = ("chart", "table", "metric")  # values under these name data, they are not text the agent wrote
# Source tiers are a coloured dot and a text label, never an emoji (prototype/design-tokens.md).
TIERS = {"open": "2E7D55", "uploaded": "B9781A", "internal": "2F6FBF", "flagged": "B4452E"}
TIER_LABELS = {"open": "Open data", "uploaded": "Uploaded", "internal": "Internal", "flagged": "Flagged"}
# Internal or placeholder wording that must never reach a cover; the builder falls back to cover_line().
COVER_PLACEHOLDER = re.compile(r"none added yet|top team signals|\(none\)|no signals (yet|added)|placeholder|lorem",
                               re.I)


def cover_line(date: str, period: str = "") -> str:
    """The cover's fallback subtitle: what it is and its period, e.g. "Team brief · figures to Q2 2026 · 10 Oct 2026"."""
    return "  ·  ".join(x for x in ("Team brief", f"figures to {period}" if period else "", date) if x)


def clean_cover_text(v, fallback: str):
    """A cover string (or list of sentences) with placeholder phrases removed; the fallback when nothing is left."""
    if isinstance(v, list):
        kept = [x for x in v if isinstance(x, str) and x.strip() and not COVER_PLACEHOLDER.search(x)]
        return kept or [fallback]
    if not isinstance(v, str) or not v.strip() or COVER_PLACEHOLDER.search(v):
        return fallback
    return v


def rgb(h):
    return RGBColor.from_string(h)


# ----------------------------------------------------------------------------- guardrail
NUM = re.compile(r"\d+(?:[.,]\d+)*")
CJK = re.compile(r"[\u3400-\u9fff]")
CJK_FONT = "Microsoft JhengHei"  # Noto Sans CJK TC on Linux renders in its place
PERIOD = re.compile(r"\b(?:Q[1-4]\s*20\d\d|20\d\d|H[12]\s*20\d\d)\b|20\d\d\s*年|第?[1-4一二三四]季", re.I)
SERIES = ("vacancy", "take_up")  # the time series; a title quotes their latest value unless it names the period
CHART_TYPES = {"line": XL_CHART_TYPE.LINE_MARKERS, "bar": XL_CHART_TYPE.BAR_CLUSTERED, "column": XL_CHART_TYPE.COLUMN_CLUSTERED}


def allowed_numbers(data: dict) -> set[str]:
    out: set[str] = set()

    def add(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            for f in (f"{x:g}", f"{x:.1f}", f"{x:.2f}", f"{round(x)}", f"{x:,.0f}"):
                out.add(f.lstrip("-"))
        else:
            out.update(NUM.findall(str(x)))

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        else:
            add(o)
    walk(data)
    out.update(str(i) for i in range(1, 13))  # slide numbers, "six signals", "01" eyebrows
    out.update(f"{i:02d}" for i in range(1, 13))
    out.update(str(len(v)) for v in data.values() if isinstance(v, list))  # "20 submarkets in the library"
    return out


def latest_data(data: dict) -> dict:
    """The data with each time series cut to its latest point: what a title or so-what may quote without
    naming a period (9.9% was Q1 2024's vacancy; a headline that says 9.9% without saying so misleads)."""
    return {k: (v[-1:] if k in SERIES and isinstance(v, list) and v else v) for k, v in data.items()}


def check_text(text: str, data: dict, headline: bool = False) -> list[str]:
    ok = allowed_numbers(latest_data(data) if headline and not PERIOD.search(text) else data)
    return [n for n in NUM.findall(text) if n not in ok and n.replace(",", "") not in ok]


def refused_numbers(spec: dict, data: dict) -> list[dict]:
    """Structured: [{slide, where, numbers, text}] for every number the data does not carry (titles and so-whats
    may only quote the latest values unless they name the period)."""
    out = []
    for i, s in enumerate(spec.get("slides") or [], 1):
        for k in ("title", "so_what", "notes", "eyebrow", "why"):
            t = s.get(k)
            if isinstance(t, str) and t != "auto":
                bad = check_text(t, data, headline=k in ("title", "so_what"))
                if bad:
                    out.append({"slide": i, "where": k, "numbers": bad, "text": t})
    return out


def spec_text(spec: dict) -> list[tuple[str, str]]:
    """(where, text) for every string the agent wrote."""
    out = []
    for i, s in enumerate(spec["slides"], 1):
        for k in ("title", "notes", "eyebrow", "so_what", "why"):
            if isinstance(s.get(k), str) and s[k] != "auto":
                out.append((f"slide {i} {k}", s[k]))
        for name, v in (s.get("fill") or {}).items():
            out += [(f"slide {i} {name}", t) for t in strings(v)]
    return out


def strings(v):
    """Every string in a fill value (paragraphs, runs, pillar and step dicts), except data keys and "auto"."""
    if isinstance(v, str):
        return [] if v == "auto" else [v]
    if isinstance(v, dict):
        return [t for k, x in v.items() if k not in KEYS for t in strings(x)]
    if isinstance(v, (list, tuple)):
        return [t for x in v for t in strings(x)]
    return []


def validate(spec: dict, data: dict) -> list[str]:
    errs = []
    slides = spec.get("slides") or []
    if spec.get("theme", DEFAULT_THEME) not in THEMES:
        errs.append(f"unknown theme {spec.get('theme')!r}; use one of {', '.join(THEMES)}")
    if not MIN_SLIDES <= len(slides) <= MAX_SLIDES:
        errs.append(f"{len(slides)} slides; a brief has {MIN_SLIDES} to {MAX_SLIDES}")
    if slides and slides[0].get("layout") != "Cover":
        errs.append("the first slide must use the Cover layout")
    if slides and slides[-1].get("layout") != "Sources":
        errs.append("the last slide must use the Sources layout")
    for i, s in enumerate(slides, 1):
        if s.get("layout") not in LAYOUTS:
            errs.append(f"slide {i}: unknown layout {s.get('layout')!r}; use one of {', '.join(LAYOUTS)}")
        if s.get("so_what") and s.get("layout") not in SO_WHAT_LAYOUTS:
            errs.append(f"slide {i}: so_what goes on {', '.join(sorted(SO_WHAT_LAYOUTS))} only")
        if s.get("layout") == "Title only" and not any(
                (isinstance(v, dict) and "table" in v) or (k == "table" and isinstance(v, str)) for k, v in (s.get("fill") or {}).items()):
            errs.append(f"slide {i}: Title only needs a table in fill ({{\"table\": {{\"table\": \"evidence\"}}}}); "
                        "otherwise the slide is empty")
        if len(s.get("title") or "") > 95:
            errs.append(f"slide {i}: title is {len(s['title'])} characters; keep it under 90")
        for name, v in (s.get("fill") or {}).items():
            if name in ("table", "chart") and isinstance(v, str):
                v = {name: v}  # shorthand {"table": "evidence"} is accepted
            if isinstance(v, dict) and v.get("table") == "evidence" and not data.get("evidence"):
                errs.append(f"slide {i}: the evidence table is empty for this data (no submarkets in focus); "
                            "use a chart or a yields table instead")
            if isinstance(v, dict) and "chart" in v and v["chart"] not in CHARTS:
                errs.append(f"slide {i}: unknown chart {v['chart']!r}; use one of {', '.join(CHARTS)}")
            if isinstance(v, dict) and "chart" in v:
                if "last" in v and not (isinstance(v["last"], int) and 2 <= v["last"] <= 20):
                    errs.append(f"slide {i}: chart 'last' is a number of periods from 2 to 20")
                if "markets" in v and not (isinstance(v["markets"], list) and v["markets"] and all(isinstance(m, str) for m in v["markets"])):
                    errs.append(f"slide {i}: chart 'markets' is a list of submarket names")
                if "type" in v and v["type"] not in CHART_TYPES:
                    errs.append(f"slide {i}: chart 'type' is one of {', '.join(CHART_TYPES)}")
            if isinstance(v, dict) and "table" in v and v["table"] not in TABLES:
                errs.append(f"slide {i}: unknown table {v['table']!r}; use one of {', '.join(TABLES)}")
            if isinstance(v, dict) and "metric" in v and v["metric"] not in HEROES:
                errs.append(f"slide {i}: unknown hero metric {v['metric']!r}; use one of {', '.join(HEROES)}")
            if name == "stats" and v != "auto":
                if not (isinstance(v, list) and 2 <= len(v) <= 4 and all(m in HEROES for m in v)):
                    errs.append(f"slide {i}: stats is \"auto\" or two to four of {', '.join(HEROES)}")
            if name == "pillars" and not (isinstance(v, list) and len(v) == 3 and all(
                    isinstance(x, dict) and x.get("head") for x in v)):
                errs.append(f"slide {i}: pillars is a list of three {{head, body}}")
            if name == "steps" and v != "auto" and not (isinstance(v, list) and 2 <= len(v) <= 5 and all(
                    isinstance(x, dict) and x.get("when") and x.get("head") for x in v)):
                errs.append(f"slide {i}: steps is \"auto\" or a list of two to five {{when, head, body}}")
    for r in refused_numbers(spec, data):
        errs.append(f"slide {r['slide']} {r['where']}: numbers not in the data: {', '.join(r['numbers'])}"
                    + (" (a title or so-what quotes the latest value; name the period to quote an earlier one)"
                       if r["where"] in ("title", "so_what") else ""))
    return errs


# ----------------------------------------------------------------------------- helpers
def chg_text(k):
    if not k or k.get("change") is None:
        return ""
    unit = "pp" if k["metric"].endswith("_pct") else ""
    sign = "+" if k["change"] > 0 else ("−" if k["change"] < 0 else "±")
    return f"{sign}{abs(k['change']):.2f}{unit} vs {k['prev_period']}"


def put(ph, paras, size=None, color=None):
    """Fill a text frame. paras: str | list[str | list[(text, opts)]]; keeps the template's styling
    unless opts override it."""
    tf = ph.text_frame
    tf.clear()
    tf.word_wrap = True
    paras = [paras] if isinstance(paras, str) else paras
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        for chunk, o in ([(para, {})] if isinstance(para, str) else para):
            r = p.add_run()
            r.text = chunk
            f = r.font
            if o.get("size", size):
                f.size = Pt(o.get("size", size))
            if o.get("color", color):
                f.color.rgb = rgb(o.get("color", color))
            if "bold" in o:
                f.bold = o["bold"]
            if "italic" in o:
                f.italic = o["italic"]
            if o.get("font"):
                f.name = o["font"]
            if CJK.search(chunk):
                rpr = r._r.get_or_add_rPr()
                ea = rpr.find(qn("a:ea"))
                if ea is None:
                    ea = rpr.makeelement(qn("a:ea"), {})
                    rpr.append(ea)
                ea.set("typeface", CJK_FONT)


EMPH = re.compile(r"\*([^*]+)\*")


def emphasis(text: str, theme: dict) -> list:
    """One paragraph of runs: *words* in the theme's accent, italic or bold by the theme's style."""
    style = {"color": theme["colors"]["accent"]}
    style["italic" if theme["style"]["emphasis"] == "italic" else "bold"] = True
    parts = EMPH.split(text)
    return [[(t, style if i % 2 else {}) for i, t in enumerate(parts) if t]]


def area(ph):
    return ph.left, ph.top, ph.width, ph.height


def fit_size(text: str, base: float, ph) -> float | None:
    """The largest point size (not above the template's) at which the text wraps inside its box, assuming an
    average glyph half the point size wide and lines 1.2 times the size tall. None when the base size fits."""
    width_pt, height_pt = Emu(ph.width).pt, Emu(ph.height).pt
    size = base
    while size > 18:
        lines = max(1, math.ceil(len(text) * size * 0.5 / width_pt))
        if lines * size * 1.2 <= height_pt:
            return None if size == base else size
        size -= 2
    return size


def drop(ph):
    ph._element.getparent().remove(ph._element)


class Painter:
    """Charts, tables and components in one theme's colours."""

    def __init__(self, theme: str, d: dict):
        self.t = THEMES[theme]
        self.c = self.t["colors"]
        self.band = self.c.get("band", self.c["dark"])  # so-what band and table header; raised on dark themes
        self.d = d

    def dot(self, slide, x, y, tier, size=Pt(7)):
        """A small filled oval in the tier colour, drawn just before a label (x, y: the label's left and top)."""
        o = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, size, size)
        o.fill.solid()
        o.fill.fore_color.rgb = rgb(TIERS[tier])
        o.line.fill.background()
        o.name = f"tier dot {tier}"
        return o

    def legend(self, slide, x, y, tiers):
        """One row of tier dots and labels (the provenance key on the Sources slide)."""
        c = self.c
        texts = {"open": "Open data, collected automatically", "uploaded": "Uploaded by a colleague under the team's own access",
                 "internal": "Internal, our own records"}
        for tier in tiers:
            self.dot(slide, x, y + Inches(0.05), tier)
            w = Pt(len(texts[tier]) * 4.6 + 12)
            tb = slide.shapes.add_textbox(x + Pt(10), y - Inches(0.04), w, Inches(0.25))
            tb.text_frame.margin_left = tb.text_frame.margin_right = 0
            put(tb, [[(texts[tier], {"size": 9, "color": c["muted"]})]])
            x += Pt(10) + w + Inches(0.2)

    # charts -------------------------------------------------------------
    def style(self, chart, legend=False):
        c = self.c
        chart.has_title = False
        chart.font.size = Pt(10)
        chart.font.name = self.t["fonts"]["body"]
        chart.font.color.rgb = rgb(c["muted"])
        chart.has_legend = legend
        if legend:
            chart.legend.position = XL_LEGEND_POSITION.TOP
            chart.legend.include_in_layout = False
        va = chart.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = rgb(c["rule"])
        va.format.line.fill.background()
        chart.category_axis.format.line.color.rgb = rgb(c["rule"])
        chart.category_axis.tick_labels.font.size = Pt(9)

    def bars(self, chart, fmt, highlight=(), horizontal=False):
        c = self.c
        self.style(chart)
        plot = chart.plots[0]
        plot.gap_width = 60
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.number_format, dl.number_format_is_linked = fmt, False
        dl.font.size, dl.font.color.rgb = Pt(9), rgb(c["ink"])
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        ser = plot.series[0]
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = rgb(c["series1"])
        for i in highlight:
            ser.points[i].format.fill.solid()
            ser.points[i].format.fill.fore_color.rgb = rgb(c["series2"])
        chart.value_axis.tick_labels.number_format = fmt
        chart.value_axis.tick_labels.number_format_is_linked = False
        if horizontal:
            chart.category_axis.reverse_order = True
            chart.value_axis.has_major_gridlines = False
            chart.value_axis.visible = False

    def chart(self, ph, key, opts=None):
        d, c = self.d, self.c
        opts = opts or {}
        cd = CategoryChartData()

        def pick(rows, by_market):
            if opts.get("last") and not by_market:
                rows = rows[-int(opts["last"]):]
            if opts.get("markets") and by_market:
                want = [m.lower() for m in opts["markets"]]
                rows = [r for r in rows if r["market"].lower() in want] or rows
            return rows
        if key == "vacancy" and opts.get("type") in ("bar", "column"):
            rows = pick(d["vacancy"], False)
            cd.categories = [r["period"] for r in rows]
            cd.add_series("Vacancy", [r["value"] for r in rows])
            self.bars(ph.insert_chart(CHART_TYPES[opts["type"]], cd).chart, '0.0"%"', highlight=[len(rows) - 1],
                      horizontal=opts["type"] == "bar")
        elif key == "vacancy":
            rows = pick(d["vacancy"], False)
            cd.categories = [r["period"] for r in rows]
            vals = [r["value"] for r in rows]
            cd.add_series("Vacancy", vals)
            chart = ph.insert_chart(XL_CHART_TYPE.LINE_MARKERS, cd).chart
            self.style(chart)
            ser = chart.plots[0].series[0]
            ser.smooth = False
            ser.format.line.color.rgb, ser.format.line.width = rgb(c["series1"]), Pt(2.25)
            ser.marker.size = 8
            ser.marker.format.fill.solid()
            ser.marker.format.fill.fore_color.rgb = rgb(c["series1"])
            for i in (0, len(vals) - 1):  # label only the first and the latest point
                dl = ser.points[i].data_label
                dl.position = XL_LABEL_POSITION.ABOVE
                dl.text_frame.text = f"{vals[i]:.1f}%"
                dl.text_frame.paragraphs[0].runs[0].font.size = Pt(10)
                dl.text_frame.paragraphs[0].runs[0].font.bold = i > 0
            va = chart.value_axis
            va.tick_labels.number_format, va.tick_labels.number_format_is_linked = '0.0"%"', False
            va.minimum_scale, va.maximum_scale = max(0, round(min(vals) - 1)), round(max(vals) + 1)
        elif key == "take_up" and opts.get("type") == "line":
            rows = pick(d["take_up"], False)
            cd.categories = [r["period"] for r in rows]
            cd.add_series("Take-up", [r["value"] for r in rows])
            chart = ph.insert_chart(XL_CHART_TYPE.LINE_MARKERS, cd).chart
            self.style(chart)
            ser = chart.plots[0].series[0]
            ser.format.line.color.rgb, ser.format.line.width = rgb(c["series1"]), Pt(2.25)
        elif key == "take_up":
            rows = pick(d["take_up"], False)
            cd.categories = [r["period"] for r in rows]
            cd.add_series("Take-up", [r["value"] for r in rows])
            self.bars(ph.insert_chart(CHART_TYPES.get(opts.get("type", "column"), XL_CHART_TYPE.COLUMN_CLUSTERED), cd).chart,
                      "0.00", highlight=[len(rows) - 1], horizontal=opts.get("type") == "bar")
        elif key == "rents":
            rows = pick(d["rents"], True)[:14]
            cd.categories = [r["market"] for r in rows]
            cd.add_series("Prime rent", [r["value"] for r in rows])
            self.bars(ph.insert_chart(CHART_TYPES.get(opts.get("type", "bar"), XL_CHART_TYPE.BAR_CLUSTERED), cd).chart, '"£"0.00',
                      highlight=[i for i, r in enumerate(rows) if r["change"]], horizontal=opts.get("type", "bar") == "bar")
        elif key == "investment":
            rows = pick(d["investment"], True)
            cd.categories = [r["market"] for r in rows]
            cd.add_series(rows[0]["period"], [r["value"] for r in rows])
            cd.add_series("Long-term average", [r["lta"] or 0 for r in rows])
            chart = ph.insert_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, cd).chart
            self.style(chart, legend=True)
            plot = chart.plots[0]
            plot.gap_width, plot.overlap = 70, -8
            plot.has_data_labels = True
            plot.data_labels.number_format, plot.data_labels.number_format_is_linked = '"£"0.00', False
            plot.data_labels.font.size = Pt(9)
            for ser, col in zip(plot.series, (c["series1"], c["series2"])):
                ser.format.fill.solid()
                ser.format.fill.fore_color.rgb = rgb(col)
            chart.value_axis.tick_labels.number_format = '"£"0.0'
            chart.value_axis.tick_labels.number_format_is_linked = False

    # tables -------------------------------------------------------------
    def table(self, slide, key, x, y, w):
        d, c = self.d, self.c
        if key == "yields":
            rows = [("PRIME YIELD", "LATEST", "CHANGE")] + [
                (yv["market"], f"{yv['text']} {yv['ref']}", chg_text(yv) or "n/a") for yv in d["yields"]]
            if d.get("macro"):
                m = d["macro"]
                rows.append(("Bank Rate", f"{m['text']} {m['ref']}", f"as of {m['as_of']}"))
            widths = (1.9, 1.3, 1.33)
        else:  # evidence: the team's submarkets x the investment-case metrics
            ev = d.get("evidence") or []
            head = ["SUBMARKET"] + [cl["label"].upper() for cl in ev[0]["cells"]] if ev else ["SUBMARKET"]
            rows = [tuple(head)] + [tuple([r["market"]] + [cl["text"] for cl in r["cells"]]) for r in ev]
            widths = None
        if key == "deals":  # our deals (internal, confirmed, quotable only) above market deals (uploaded)
            rows = [("DEAL", "TENANT", "RENT", "TERM", "RENT-FREE", "WHEN", "SOURCE")]
            rows += [(x["property"], x["tenant"], x["rent"] or "-", x["term"] or "-", x["rent_free"] or "-", x["date"] or "-",
                      "Internal" + (", quotable" if x["level"] == "quotable" else " only")) for x in d.get("our_deals") or []]
            tiers = ["internal"] * len(d.get("our_deals") or [])
            rows += [(x["property"], x["tenant"], x["rent"] or "-", "-", "-", x["period"], f"Uploaded {x['ref']}")
                     for x in d.get("market_deals") or []]
            tiers += ["uploaded"] * len(d.get("market_deals") or [])
            if len(rows) == 1:
                rows.append(("No confirmed deals", "", "", "", "", "", ""))
            widths = [3.0, 2.4, 1.3, 1.1, 1.3, 1.2, 1.8]
        tbl = slide.shapes.add_table(len(rows), len(rows[0]), x, y, w, Inches(0.42) * len(rows)).table
        if key == "deals" and len(rows) > 1 and widths:  # a tier dot before each SOURCE label
            col_x = x + Inches(sum(widths[:-1]))
            for r_i, tier in enumerate(tiers, 1):
                tbl.cell(r_i, len(rows[0]) - 1).margin_left = Inches(0.25)
                self.dot(slide, col_x + Inches(0.09), y + Inches(0.42) * r_i + Inches(0.09), tier)  # level with top-anchored text
        if self.t["background"].startswith("solid dark"):  # the default table style draws white grid lines
            tbl._tbl.tblPr.find(qn("a:tableStyleId")).text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
        if widths:
            for i, wd in enumerate(widths):
                tbl.columns[i].width = Inches(wd)
        for r_i, row in enumerate(rows):
            for col, val in enumerate(row):
                cell = tbl.cell(r_i, col)
                cell.text = val
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(self.band if r_i == 0 else (c["card"] if r_i % 2 else c["panel"]))
                for p in cell.text_frame.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(9 if r_i == 0 else 10)
                        run.font.bold = r_i == 0
                        run.font.color.rgb = rgb(c["on_dark"] if r_i == 0 else c["ink"])

    # components ---------------------------------------------------------
    def kpi_tiles(self):
        d, c = self.d, self.c
        k = {x["metric"]: x for x in d["kpis"]}
        tiles = [x for x in (k.get("vacancy_pct"), k.get("take_up_msqft"), k.get("investment_gbp_bn")) if x]
        if d.get("macro"):
            m = d["macro"]
            tiles.append({"label": m["label"], "text": m["text"], "ref": m["ref"], "sub": f"as of {m['as_of']}",
                          "flagged": False})
        elif "active_requirements_msqft" in k:
            tiles.append(k["active_requirements_msqft"])
        out = []
        for t in tiles[:4]:
            sub = t.get("sub") or chg_text(t)
            if t.get("vs_lta_pct") is not None and t.get("metric") != "vacancy_pct":
                sub += f" · {t['vs_lta_pct']:+d}% vs LTA"
            out.append([
                [((t["label"] + (f" · {t['period']}" if t.get("period") else "")).upper(),
                  {"size": 9, "bold": True, "color": c["on_dark_muted"]})],
                [(t["text"], {"size": 30, "bold": True, "font": self.t["fonts"]["head"], "color": c["on_dark"]}),
                 (" (flagged)" if t["flagged"] else "", {"size": 10, "color": c["on_dark_muted"]}),
                 (" " + t["ref"], {"size": 10, "color": c["on_dark_muted"]})],
                [(sub, {"size": 10, "color": c["on_dark_muted"]})]])
        return out

    def hero(self, metric):
        """(figure, caption, context paragraphs) for the Hero number layout."""
        d = self.d
        if metric == "bank_rate" and d.get("macro"):
            m = d["macro"]
            return f"{m['text']}", f"BANK RATE · AS OF {m['as_of']}", [f"Bank of England Bank Rate {m['ref']}."]
        k = next((x for x in d["kpis"] if x["metric"] == metric), None)
        if not k:
            return "", "", []
        ctx = [f"{chg_text(k)} {k['ref']}".strip()]
        if k.get("vs_lta_pct") is not None and metric != "vacancy_pct":
            ctx.append(f"{k['vs_lta_pct']:+d}% against the long-term average.")
        if k["flagged"]:
            ctx.insert(0, "Flagged by a colleague, not yet checked.")
        return k["text"], f"{k['label']} · {k['period']}".upper() + (" · FLAGGED" if k["flagged"] else ""), ctx

    def stats(self, metrics):
        """(figure, caption, context) per cell of the Stat row; "auto" is the Cover's four KPIs."""
        if metrics == "auto":
            k = {x["metric"] for x in self.d["kpis"]}
            metrics = [m for m in ("vacancy_pct", "take_up_msqft", "investment_gbp_bn") if m in k]
            metrics.append("bank_rate" if self.d.get("macro") else "active_requirements_msqft")
        out = []
        for m in metrics[:4]:
            fig, cap, ctx = self.hero(m)
            if fig:
                out.append((fig, cap, " ".join(ctx)))
        return out

    def timeline(self, slide, phs, steps):
        """Fill the step placeholders and draw the line and one node per step."""
        c = self.c
        if steps == "auto":  # the last five quarters of vacancy and take-up
            take = {r["period"]: r for r in self.d["take_up"]}
            steps = [{"when": r["period"].upper(), "head": f"Vacancy {r['value']:.1f}%",
                      "body": (f"Take-up {take[r['period']]['value']:.2f}m sq ft " if r["period"] in take else "")
                      + r["ref"]} for r in self.d["vacancy"][-5:]]
        xs = []
        for i, st in enumerate(steps[:5], 1):
            xs.append(phs[f"step{i}_when"].left)
            put(phs.pop(f"step{i}_when"), st["when"].upper())
            put(phs.pop(f"step{i}_head"), st["head"])
            if st.get("body"):
                put(phs.pop(f"step{i}_body"), st["body"])
        y = Inches(3.02)
        ln = slide.shapes.add_connector(1, xs[0] + Inches(0.09), y, xs[-1] + Inches(0.09), y)
        ln.line.color.rgb, ln.line.width = rgb(c["rule"]), Pt(1.5)
        for i, x in enumerate(xs):
            dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y - Inches(0.09), Inches(0.18), Inches(0.18))
            dot.fill.solid()
            dot.fill.fore_color.rgb = rgb(c["accent"] if i == len(xs) - 1 else c["bg"])
            dot.line.color.rgb, dot.line.width = rgb(c["accent"]), Pt(1.5)

    def tone(self, t):
        """Mark, kicker word and colour for a card: the cards read as the case for and against."""
        c = self.c
        return {"positive": ("▲", "SUPPORTS THE CASE", c["good"]),
                "negative": ("▼", "RISKS TO THE CASE", c["bad"])}.get(
            t, ("●", "CONTEXT", c["neutral"]))

    def cards(self):
        """Up to six signal cards, what supports the case before what puts it at risk, as in the written brief."""
        rank = {"positive": 0, "negative": 1}
        return sorted(self.d["signals"][:6], key=lambda cd: rank.get(cd["tone"], 2))

    def card(self, cd):
        c = self.c
        mark, word, col = self.tone(cd["tone"])
        detail = cd["detail"] if len(cd["detail"]) < 180 else cd["detail"][:177].rsplit(" ", 1)[0] + "…"
        return [[(f"{mark} {word}", {"size": 9, "bold": True, "color": col}),
                 (("  " + cd["flag"]) if cd.get("flag") else "", {"size": 9, "color": TIERS["flagged"]})],
                [(cd["title"], {"size": 12, "bold": True, "color": c["ink"], "font": self.t["fonts"]["head"]})],
                [(detail + " " + cd["refs"], {"size": 9})],
                [(cd["why"], {"size": 9, "italic": True, "color": c["muted"]})]]

    def card_edge(self, slide, ph, cd):
        x, y, w, _ = area(ph)
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x - Inches(0.14), y - Inches(0.1), w + Inches(0.25),
                                     Inches(0.05))
        bar.fill.solid()
        bar.fill.fore_color.rgb = rgb(self.tone(cd["tone"])[2])
        bar.line.fill.background()

    def hide_card_frame(self, slide, ph):
        """The card frames are drawn on the layout; an unused one is covered in the page colour."""
        x, y, w, h = area(ph)
        cover = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x - Inches(0.16), y - Inches(0.12), w + Inches(0.3),
                                       h + Inches(0.2))
        cover.fill.solid()
        cover.fill.fore_color.rgb = rgb(self.c["bg"])
        cover.line.fill.background()

    def cover_kpis(self, slide, phs, tiles):
        """The cover's KPI block: one tile per KPI with a value, its accent rule above it. The layout draws
        four rules; when fewer tiles have a value the rules are masked in the cover colour and redrawn over
        the tiles that stay, centred on the row, so no rule is ever left with nothing under it."""
        slots = [phs[f"kpi{i}"] for i in range(1, 5) if f"kpi{i}" in phs]
        if not slots:
            return
        for i, tile in enumerate(tiles[:4], 1):
            put(phs.pop(f"kpi{i}"), tile)
        n = min(len(tiles), 4)
        if n == len(slots):
            return
        try:
            bg = str(slide.slide_layout.background.fill.fore_color.rgb)
        except Exception:  # noqa: BLE001
            bg = self.c["dark"]
        x0, top, w, h = area(slots[0])
        x1 = slots[-1].left + slots[-1].width
        gap = (slots[1].left - slots[0].left - w) if len(slots) > 1 else Inches(0.18)
        mask = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x0 - Inches(0.1), top - Inches(0.18), x1 - x0 + Inches(0.2),
                                      Inches(0.16))
        mask.fill.solid()
        mask.fill.fore_color.rgb = rgb(bg)
        mask.line.fill.background()
        mask.name = "kpi rule mask"
        if n == 0:
            return
        left = x0 + ((x1 - x0) - (n * w + (n - 1) * gap)) // 2
        for i in range(n):
            x = left + i * (w + gap)
            slots[i].left, slots[i].top, slots[i].width, slots[i].height = x, top, w, h  # all four: a placeholder
            # inherits its box from the layout, and writing one side alone loses the other three
            ln = slide.shapes.add_connector(1, x, top - Inches(0.1), x + w, top - Inches(0.1))
            ln.line.color.rgb, ln.line.width = rgb(self.c["accent"]), Pt(3)
            ln.name = f"kpi rule {i + 1}"

    def so_what(self, slide, text):
        """The dark band near the foot of a content slide: a label and one sentence (the slide's so-what)."""
        c = self.c
        band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(6.17), Inches(12.13), Inches(0.55))
        band.fill.solid()
        band.fill.fore_color.rgb = rgb(self.band)
        band.line.fill.background()
        tf = band.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Inches(0.2)
        put(band, [[("SO WHAT    ", {"size": 9, "bold": True, "color": c["accent"]}),
                    (text, {"size": 12, "italic": True, "color": c["on_dark"]})]])
        band.text_frame.paragraphs[0].alignment = PP_ALIGN.LEFT

    def sources(self):
        d, c = self.d, self.c
        paras = list(d["footnotes"])
        if d["flagged"]:
            paras += ["", [("FLAGGED FIGURES, NOT YET CHECKED", {"bold": True, "color": c["bad"], "size": 9})],
                      *d["flagged"]]
        paras += ["", [(d["caveat"], {"italic": True, "color": c["muted"]})]]
        return paras

    def talk(self):
        c = self.c
        return [[("MARKET TALK, NOT CONFIRMED   ", {"bold": True, "color": c["bad"], "size": 9}),
                 ("Shared by colleagues; no published source confirms these yet. ", {"italic": True}),
                 (" · ".join(t["title"].removeprefix("Unverified tip: ") for t in self.d["talk"]), {})]]


# ----------------------------------------------------------------------------- default storyline
def default_spec(d: dict, theme: str | None = None) -> dict:
    """The storyline (references/storyline.md) with rule-based titles, so the brief exports without an agent:
    occupiers, the submarket evidence table, rents, capital markets, deals, signals and sources, kept to six."""
    theme = theme or DEFAULT_THEME
    k = {x["metric"]: x for x in d["kpis"]}
    slides = [{"key": "cover", "layout": "Cover", "eyebrow": "LONDON OFFICE MARKET  ·  " + d["date"].upper(),
               "title": d["title"], "notes": "Headline: " + " ".join(d["headline"]),
               "fill": {"subtitle": d["picked_by"], "headline": d["headline"], "kpis": "auto", "caveat": d["caveat"]}}]
    n = 1
    vac, take = k.get("vacancy_pct"), k.get("take_up_msqft")
    if vac and d["vacancy"]:
        n += 1
        t = f"Vacancy {'fell' if (vac['change'] or 0) < 0 else 'rose'} to {vac['text']}"
        if vac["value"] <= min(r["value"] for r in d["vacancy"]):
            t += f", the lowest since {d['vacancy'][0]['period']}"
        if take and take.get("vs_lta_pct") is not None:
            t += f"; take-up {abs(take['vs_lta_pct'])}% {'above' if take['vs_lta_pct'] > 0 else 'below'} average"
        req = k.get("active_requirements_msqft")
        slides.append({"key": "occupiers", "layout": "Two charts", "eyebrow": f"{n:02d}  ·  OCCUPIERS", "title": t,
                       "notes": "Vacancy: " + ", ".join(f"{r['period']} {r['value']}%" for r in d["vacancy"]) + ".",
                       "so_what": (f"Active requirements are up to {req['text']}: demand is still building."
                                   if req and (req.get("change") or 0) > 0 else ""),
                       "fill": {"left_label": "CENTRAL LONDON VACANCY RATE", "left_chart": {"chart": "vacancy"},
                                "right_label": "TAKE-UP, M SQ FT" + (f"  ·  LONG-TERM AVERAGE {take['lta']:.2f}"
                                                                    if take and take.get("lta") else ""),
                                "right_chart": {"chart": "take_up"},
                                "source": f"Source {d['vacancy'][-1]['ref']}. Quarters with no figures in the "
                                          "library are not shown."}})
    if d.get("evidence"):
        n += 1
        slides.append({"key": "evidence", "layout": "Title only", "eyebrow": f"{n:02d}  ·  MARKET EVIDENCE",
                       "title": "Market evidence for the team's submarkets",
                       "notes": "The submarket evidence table, as in the written brief.",
                       "fill": {"table": {"table": "evidence"}}})
    if d["rents"]:
        n += 1
        top = d["rents"][0]
        core = ("West End Core", "City Core", "Canary Wharf")
        movers = sorted((r for r in d["rents"] if r["change"]), key=lambda r: r["market"] not in core)
        t = f"{top['market']} leads at £{top['value']:g}/sq ft"
        t += (f"; {movers[0]['market']} {'up' if movers[0]['change'] > 0 else 'down'} "
              f"£{abs(movers[0]['change']):.2f} on the quarter") if movers else "; no core rent moved on the quarter"
        take_lines = [[("MOVED ON THE QUARTER", {"bold": True, "size": 9})]] + (
            [f"{r['market']}: {chg_text(r)} to £{r['value']:.2f} {r['ref']}" for r in movers]
            or ["No submarket rent moved."]) + [
            "", [("SPREAD", {"bold": True, "size": 9})],
            f"Top {top['market']} £{top['value']:.2f}, bottom {d['rents'][-1]['market']} "
            f"£{d['rents'][-1]['value']:.2f}, {len(d['rents'])} submarkets in the library."]
        slides.append({"key": "rents", "layout": "Chart + takeaway", "eyebrow": f"{n:02d}  ·  RENTS", "title": t,
                       "so_what": (f"Only {len(movers)} of {len(d['rents'])} submarkets moved: prime rents are holding."
                                   if movers else "No prime rent moved on the quarter."),
                       "notes": "; ".join(f"{r['market']} £{r['value']:.2f}" for r in d["rents"]),
                       "fill": {"chart_label": f"PRIME RENT, £/SQ FT, {top['period'].upper()}  ·  HIGHLIGHT = MOVED",
                                "chart": {"chart": "rents"}, "takeaway": take_lines,
                                "source": f"Source {top['ref']}. Fourteen highest shown."}})
    inv = k.get("investment_gbp_bn")
    if inv and d["investment"]:
        n += 1
        t = f"Investment {inv['text']} in {inv['period']}"
        if inv.get("vs_lta_pct") is not None:
            t += f", {abs(inv['vs_lta_pct'])}% {'below' if inv['vs_lta_pct'] < 0 else 'above'} the long-term average"
        thin = min((r for r in d["investment"] if r.get("vs_lta_pct") is not None), key=lambda r: r["vs_lta_pct"],
                   default=None)
        slides.append({"key": "capital", "layout": "Chart + table", "eyebrow": f"{n:02d}  ·  CAPITAL MARKETS",
                       "title": t,
                       "so_what": (f"{thin['market']} is {abs(thin['vs_lta_pct'])}% below its long-term average: "
                                   "little fresh pricing evidence." if thin and thin["vs_lta_pct"] < 0 else ""),
                       "notes": "; ".join(f"{r['market']} {r['text']} vs LTA £{r['lta']}bn" for r in d["investment"]),
                       "fill": {"chart_label": f"INVESTMENT, £BN, {d['investment'][0]['period'].upper()} "
                                               "VS LONG-TERM AVERAGE",
                                "chart": {"chart": "investment"}, "table_label": "PRICING AND RATES",
                                "table": {"table": "yields"},
                                "source": f"London total {inv['text']} ({chg_text(inv)}) {inv['ref']}. "
                                          "Yields are the publisher's prime yields."}})
    if d.get("our_deals") or d.get("deals_filtered"):
        n += 1
        ours = d.get("our_deals") or []
        t = (f"Our deals and market deals: {len(ours)} of ours, listed apart from the market" if ours
             else "Market deals; our records are internal only and not shown")
        note = f"{d['deals_filtered']} internal-only record(s) left out of the brief. " if d.get("deals_filtered") else ""
        slides.append({"key": "deals", "layout": "Title only", "eyebrow": f"{n:02d}  ·  DEALS",
                       "title": t, "so_what": next((x["ext"] for x in ours if x.get("ext")), ""),
                       "notes": note + "Our deals are internal: " + ("; ".join(f"{x['property']} {x['rent']}" for x in ours) or "none")
                                + ". Market deals come from uploaded agency reports.",
                       "fill": {"table": {"table": "deals"}}})
    n += 1
    slides.append({"key": "signals", "layout": "Signal cards", "eyebrow": f"{n:02d}  ·  WHAT CHANGED",
                   "title": "What supports the case, and what puts it at risk",
                   "notes": "\n".join(f"- {c['title']}: {c['detail']} {c['refs']}" for c in d["signals"]),
                   "fill": {"cards": "auto", "talk": "auto"}})
    slides.append({"key": "sources", "layout": "Sources", "eyebrow": "SOURCES", "title": "Sources and caveats",
                   "notes": "Every figure carries [n]; this list maps each to its source.", "fill": {"body": "auto"}})
    while len(slides) > PLAN_MAX:  # keep within six: drop rents first (the deals slide is rent evidence), then capital
        drop = next((i for i, s in enumerate(slides) if s.get("key") in ("rents", "capital")), len(slides) - 3)
        slides.pop(drop)
    n = 1
    for s in slides[1:-1]:  # eyebrow numbers follow the slides that stayed
        n += 1
        s["eyebrow"] = re.sub(r"^\d\d  ·  ", f"{n:02d}  ·  ", s["eyebrow"])
    return {"theme": theme, "slides": slides}


def merge_overrides(spec: dict, overrides: dict) -> dict:
    """The PoC's existing `slides` argument ({key: {title, notes}}) applied to the default spec."""
    spec = copy.deepcopy(spec)
    for s in spec["slides"]:
        o = overrides.get(s.get("key"), {})
        s.update({k: v for k, v in o.items() if k in ("title", "notes", "eyebrow", "so_what", "why", "layout", "fill") and v})
    return spec


# ----------------------------------------------------------------------------- build
def build(d: dict, out: str | Path, spec: dict | None = None, theme: str | None = None) -> dict:
    spec = copy.deepcopy(spec) if spec else default_spec(d, theme)
    if theme:
        spec["theme"] = theme
    spec.setdefault("theme", DEFAULT_THEME)
    for s in spec.get("slides") or []:
        if isinstance(s, dict) and not s.get("id"):  # a stable identity, so an edit is tracked by id, not by title
            s["id"] = "s" + uuid.uuid4().hex[:6]
    errs = validate(spec, d)
    if errs:
        raise ValueError("; ".join(errs))
    paint = Painter(spec["theme"], d)
    prs = Presentation(str(HERE / "templates" / f"{spec['theme']}.pptx"))
    layouts = {l.name: l for l in prs.slide_layouts}
    total = len(spec["slides"])
    auto = {"headline": d["headline"], "caveat": d["caveat"], "subtitle": d["picked_by"]}
    for n, s in enumerate(spec["slides"], 1):
        layout = layouts[s["layout"]]
        by_name = {p.name: p.placeholder_format.idx for p in layout.placeholders}
        slide = prs.slides.add_slide(layout)
        brand_marks(slide, s["layout"], prs)
        present = {p.placeholder_format.idx: p for p in slide.placeholders}
        phs = {name: present[idx] for name, idx in by_name.items() if idx in present}
        fill = {k: (auto[k] if v == "auto" and k in auto else v) for k, v in (s.get("fill") or {}).items()}
        fill = {k: ({k: v} if k in ("table", "chart") and isinstance(v, str) else v) for k, v in fill.items()}
        if s["layout"] == "Cover":  # no internal or placeholder wording on a cover: what it is and its period instead
            line = cover_line(d.get("date", ""), (d.get("kpis") or [{}])[0].get("period", ""))
            s = {**s, "title": clean_cover_text(s.get("title", ""), d.get("title", ""))}
            for k in ("subtitle", "headline", "caveat"):
                if k in fill:
                    fill[k] = clean_cover_text(fill[k], line)
        if "title" in phs:
            ph = phs.pop("title")
            base = paint.t["fonts"].get("cover_size", 38) if s["layout"] == "Cover" else paint.t["fonts"]["title_size"]
            # a long title (the Copilot writes longer ones than the template planned for) shrinks to stay
            # inside its box instead of wrapping over the subtitle
            put(ph, emphasis(s.get("title", ""), paint.t), size=fit_size(s.get("title", ""), base, ph))
        if isinstance(fill.get("statement"), str):
            put(phs.pop("statement"), emphasis(d["headline"][0] if fill["statement"] == "auto" else fill["statement"],
                                               paint.t))
            fill.pop("statement")
            if fill.get("attribution") == "auto":
                fill["attribution"] = f"London office team  ·  {d['date']}"
        if fill.get("stats"):
            for i, (fig, cap, ctx) in enumerate(paint.stats(fill.pop("stats")), 1):
                put(phs.pop(f"stat{i}"), fig)
                put(phs.pop(f"stat{i}_caption"), cap)
                put(phs.pop(f"stat{i}_context"), ctx)
        if fill.get("pillars"):
            for i, pl in enumerate(fill.pop("pillars"), 1):
                put(phs.pop(f"pillar{i}_head"), pl["head"])
                if pl.get("body"):
                    put(phs.pop(f"pillar{i}_body"), pl["body"])
        if fill.get("steps"):
            paint.timeline(slide, phs, fill.pop("steps"))
        if s.get("eyebrow") and "eyebrow" in phs:
            put(phs.pop("eyebrow"), s["eyebrow"].upper())
        if s["layout"] == "Cover":
            tiles = [t for t in paint.kpi_tiles() if t[1][0][0].strip()] if fill.pop("kpis", None) else []
            paint.cover_kpis(slide, phs, tiles)
        if fill.pop("cards", None):
            used = paint.cards()
            for i, c in enumerate(used, 1):
                paint.card_edge(slide, phs[f"card{i}"], c)
                put(phs.pop(f"card{i}"), paint.card(c))
            for i in range(len(used) + 1, 7):  # fewer than six signals: hide the layout's empty card frames
                if f"card{i}" in phs:
                    paint.hide_card_frame(slide, phs[f"card{i}"])
        if fill.get("talk") == "auto":
            fill.pop("talk")
            if d.get("talk"):
                put(phs.pop("talk"), paint.talk())
        if fill.get("body") == "auto" and s["layout"] == "Sources":
            fill.pop("body")
            body = phs.pop("body")
            body.left, body.top, body.width, body.height = body.left, body.top, body.width, Inches(4.8)  # room for the key
            put(body, paint.sources())
            paint.legend(slide, Inches(0.6), Inches(6.76), ["open", "uploaded"] + (["internal"] if d.get("our_deals") else []))
        if isinstance(fill.get("hero"), dict):
            fig, cap, ctx = paint.hero(fill.pop("hero")["metric"])
            # the template's 60pt fits "8.0%"; a figure with a unit ("14.30m sq ft") is scaled to stay on one line
            put(phs.pop("hero"), fig, size=60 if len(fig) <= 7 else max(28, int(60 * 7 / len(fig))))
            put(phs.pop("hero_caption"), cap)
            if "hero_context" not in fill:
                put(phs.pop("hero_context"), ctx)
        for name, v in fill.items():
            if isinstance(v, dict) and "table" in v and name not in phs:  # Title only: under the title
                paint.table(slide, v["table"], Inches(0.6), Inches(1.8), Inches(12.1))
                continue
            ph = phs.pop(name, None)
            if ph is None:
                continue
            if isinstance(v, dict) and "chart" in v:
                paint.chart(ph, v["chart"], v)
            elif isinstance(v, dict) and "table" in v:
                x, y, w, _ = area(ph)
                drop(ph)
                paint.table(slide, v["table"], x, y, w)
            elif name.endswith("_label") and isinstance(v, str):
                put(ph, v.upper())  # labels are tracked uppercase in every theme
            else:
                put(ph, v)
        for ph in phs.values():  # nothing left empty: an unused placeholder shows "Click to add text"
            drop(ph)
        if s.get("so_what"):
            paint.so_what(slide, s["so_what"])
        if s["layout"] not in ("Cover", "Section", "Statement"):
            tb = slide.shapes.add_textbox(Inches(11.7), Inches(7.1), Inches(1.03), Inches(0.25))
            put(tb, [[(f"{n:02d} / {total:02d}", {"size": 8, "color": paint.c["muted"]})]])
            tb.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
        slide.notes_slide.notes_text_frame.text = ((f"Why this slide: {s['why']}\n" if s.get("why") else "") + s.get("notes", "")).strip()
    prs.core_properties.title = d["title"]
    prs.core_properties.author = "London Office Market Agent"
    prs.save(str(out))
    return {"path": str(out), "theme": spec["theme"], "spec": spec,
            "slides": [{"layout": s["layout"], "title": s.get("title", ""), "id": s.get("id")} for s in spec["slides"]]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--spec")
    ap.add_argument("--theme", choices=list(THEMES))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    data = json.loads(Path(a.data).read_text())
    spec = json.loads(Path(a.spec).read_text()) if a.spec else None
    print(json.dumps(build(data, a.out, spec, a.theme), indent=1))
