"""The team brief as a research note: a Word document laid out like a broker's research report (navy cover with
the co-brand lockup, key takeaways, KPI tiles, the key-numbers table, charts, the signals, deals, sources and an
important-information page), and the same document as a PDF converted by LibreOffice, so the two never differ.

The text is the brief exactly as the page shows it (the cached Markdown, so no model is called again); the
charts are drawn from the library by matplotlib. Every figure keeps its [n], which points to the Sources list."""
from __future__ import annotations

import io
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "assets" / "brand"
NAVY, INK, MUTED, GOLD, RULE, PANEL = "1B3A5C", "1F2A44", "6B7385", "B9781A", "D9D6CC", "F3F1EA"
BLUE, GOOD, BAD = "3A62A8", "2E7D4F", "A8322A"
HEAD, BODY, CJK = "Cambria", "Calibri", "Microsoft JhengHei"
REF = re.compile(r"\[(\d+|internal)\]")


def unref(text: str) -> str:
    """Text without its [n] references or the space before each, so 'average [1].' reads 'average.'."""
    return re.sub(r"\s*\[(?:\d+|internal)\]", "", text or "").strip()
_LOCK = threading.Lock()


# ------------------------------------------------------------------------------------------- the brief, parsed
# The brief's parts are found by what they hold, with their usual names (English or Chinese) as the first guess,
# so a renamed heading, a reordered brief or a model-written one still lays out: the first table is the key
# numbers, a list of [n] lines is the sources, the first prose is the headline.
HEADLINE_NAMES = re.compile(r"headline|summary|overview|takeaway|摘要|重點|要點|概覽|總結|概要|标题|標題", re.I)
NUMBERS_NAMES = re.compile(r"key (numbers|figures|data)|numbers|figures|market data|數據|数据|數字|关键|關鍵", re.I)
SOURCES_NAMES = re.compile(r"^(sources?|references?|notes|footnotes|來源|来源|資料來源|参考|參考)", re.I)
SRC_LINE = re.compile(r"^\s*\[(\d+)\]")


@dataclass
class Brief:
    title: str = ""
    sub: str = ""
    sections: list[tuple[str, list[str]]] = field(default_factory=list)  # the rest, as written: (heading, lines)
    headline: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)  # the section holding the key-numbers table
    sources: list[str] = field(default_factory=list)
    caveat: str = ""

    def section(self, name: str) -> list[str]:
        return next((lines for h, lines in self.sections if h.lower().startswith(name.lower())), [])


def _is_table(line: str) -> bool:
    return line.strip().startswith("|") and line.strip().count("|") >= 2


def _prose(lines: list[str]) -> list[str]:
    return [ln for ln in lines if ln.strip() and not _is_table(ln) and not ln.strip().startswith(("- ", "* ", "_"))]


def parse(md: str) -> Brief:
    b, cur, pre = Brief(), None, []
    for line in (md or "").splitlines():
        if re.match(r"^#\s", line) and not b.title:
            b.title = line.lstrip("#").strip()
        elif re.match(r"^##\s", line) or (cur is None and re.match(r"^###\s", line)):
            cur = (line.lstrip("#").strip(), [])
            b.sections.append(cur)
        elif re.match(r"^###\s", line):  # a sub-heading stays inside its section
            cur[1].append(line)
        elif cur is None:
            pre.append(line)
        else:
            cur[1].append(line)
    pre = [ln for ln in pre if ln.strip()]
    if pre:
        b.sub = next((ln.strip().strip("_") for ln in pre if ln.strip().startswith("_")), "")
        rest = [ln for ln in pre if ln.strip().strip("_") != b.sub]
        if rest:  # prose before the first heading: it is the opening, so it leads like a headline
            b.sections.insert(0, ("Headline", rest))
    secs = b.sections

    def is_sources(h, lines):
        refs = [ln for ln in lines if SRC_LINE.match(ln)]
        body = [ln for ln in lines if ln.strip() and not ln.strip().startswith("_")]
        return bool(refs) and (bool(SOURCES_NAMES.search(h)) or len(refs) >= max(1, 0.6 * len(body)))
    src = next((i for i, (h, ln) in enumerate(secs) if is_sources(h, ln)), None)
    if src is not None:
        lines = secs[src][1]
        b.sources = [SRC_LINE.sub(lambda m: f"[{m.group(1)}]", ln.strip()) for ln in lines if SRC_LINE.match(ln)]
        b.caveat = " ".join(ln.strip().strip("_ ") for ln in lines if ln.strip().startswith("_"))
    left = [i for i in range(len(secs)) if i != src]
    num = next((i for i in left if NUMBERS_NAMES.search(secs[i][0]) and any(_is_table(x) for x in secs[i][1])),
               next((i for i in left if any(_is_table(x) for x in secs[i][1])), None))
    head = next((i for i in left if i != num and HEADLINE_NAMES.search(secs[i][0]) and _prose(secs[i][1])),
                next((i for i in left if i != num and _prose(secs[i][1])), None))
    b.headline = _prose(secs[head][1]) if head is not None else []
    b.numbers = secs[num][1] if num is not None else []
    b.sections = [secs[i] for i in left if i not in (head, num)]
    return b


def table_rows(lines: list[str]) -> list[list[str]]:
    """A Markdown table as rows of cells, every row as wide as the header (short rows padded, long rows trimmed);
    an escaped pipe (backslash, bar) stays inside its cell."""
    rows = []
    for ln in lines:
        if not _is_table(ln):
            continue
        cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", ln.strip().strip("|"))]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    if not rows:
        return []
    width = len(rows[0])
    return [(r + [""] * width)[:width] for r in rows]


def columns(head: list[str]) -> dict:
    """Which column is which, by the header's words, falling back to the brief's usual order."""
    want = {"market": r"market|submarket|area|市場|市场|地區|区域|子市場",
            "metric": r"metric|measure|indicator|指標|指标|項目",
            "latest": r"latest|value|current|figure|最新|數值|数值|現值",
            "period": r"period|quarter|date|as of|期|季|日期",
            "change": r"change|move|vs|變動|变动|變化|变化|升跌"}
    found = {}
    for key, pat in want.items():
        i = next((n for n, h in enumerate(head) if re.search(pat, h, re.I) and n not in found.values()), None)
        if i is not None:
            found[key] = i
    for n, key in enumerate(("market", "metric", "latest", "period", "change")):
        if key not in found and len(head) == 5 and n not in found.values():
            found[key] = n
    return found


def down_is_good(label: str) -> bool:
    """For an owner of London offices: vacancy, rent-free and yields are better when they fall."""
    return bool(re.search(r"vacan|空置|rent[- ]?free|免租|yield|收益率|回報率", label or "", re.I))


def sentences(text: str) -> list[str]:
    """Sentences in English or Chinese: after . ! ? before a capital, a digit or £; after 。！？ always."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z£\d\"'(])|(?<=[。！？])\s*", (text or "").strip())
    return [p.strip() for p in parts if p and p.strip()]


# ----------------------------------------------------------------------------------------------- docx helpers
# WordprocessingML wants the children of these elements in schema order; Word refuses a file that mixes them up
# (LibreOffice does not mind, so the PDF alone would never show it). _tidy puts them back in order before saving.
_ORDER = {
    "tblPr": "tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing "
             "tblInd tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription",
    "tcPr": "cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark",
    "pPr": "pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs "
           "suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi "
           "adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection "
           "textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange",
    "rPr": "rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid "
           "vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs "
           "em lang eastAsianLayout specVanish oMath",
    "tcBorders": "top start left bottom end right insideH insideV tl2br tr2bl",
    "pBdr": "top left bottom right between bar",
    "tcMar": "top start left bottom end right",
}
_ORDER = {qn(f"w:{k}"): {qn(f"w:{n}"): i for i, n in enumerate(v.split())} for k, v in _ORDER.items()}


def _tidy(root):
    for el in root.iter(*_ORDER):
        rank = _ORDER[el.tag]
        kids = list(el)
        ordered = sorted(kids, key=lambda k: rank.get(k.tag, len(rank)))  # stable: unknowns keep their place at the end
        if ordered != kids:
            for k in kids:
                el.remove(k)
            el.extend(ordered)


def _shade(cell, hex_):
    tcPr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear"), sh.set(qn("w:color"), "auto"), sh.set(qn("w:fill"), hex_)
    tcPr.append(sh)


def _margins(cell, top=0, bottom=0, left=0, right=0):
    tcPr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for k, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        e = OxmlElement(f"w:{k}")
        e.set(qn("w:w"), str(int(v))), e.set(qn("w:type"), "dxa")
        mar.append(e)
    tcPr.append(mar)


def _borders(table, color=RULE, inside_h=True, outer=False, size=4):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        on = (edge == "insideH" and inside_h) or (outer and edge in ("top", "bottom"))
        e.set(qn("w:val"), "single" if on else "nil")
        if on:
            e.set(qn("w:sz"), str(size)), e.set(qn("w:color"), color)
        b.append(e)
    tblPr.append(b)


def _cell_border(cell, edge, color, size=12):
    tcPr = cell._tc.get_or_add_tcPr()
    b = tcPr.find(qn("w:tcBorders"))
    if b is None:
        b = OxmlElement("w:tcBorders")
        tcPr.append(b)
    e = OxmlElement(f"w:{edge}")
    e.set(qn("w:val"), "single"), e.set(qn("w:sz"), str(size)), e.set(qn("w:color"), color)
    b.append(e)


def _fixed(table, widths_mm):
    tbl = table._tbl
    tblPr = tbl.tblPr
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    table.autofit = False
    for row in table.rows:
        for cell, w in zip(row.cells, widths_mm):
            cell.width = Mm(w)
    grid = tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths_mm):
        gc.set(qn("w:w"), str(int(Mm(w).twips)))
    # flush with the text margin: no indent and no default side padding (each cell sets its own)
    ind = OxmlElement("w:tblInd")
    ind.set(qn("w:w"), "0"), ind.set(qn("w:type"), "dxa")
    tblPr.append(ind)
    mar = OxmlElement("w:tblCellMar")
    for k in ("left", "right"):
        e = OxmlElement(f"w:{k}")
        e.set(qn("w:w"), "0"), e.set(qn("w:type"), "dxa")
        mar.append(e)
    tblPr.append(mar)


def _no_split(table):
    """Rows never break across a page."""
    for row in table.rows:
        trPr = row._tr.get_or_add_trPr()
        e = OxmlElement("w:cantSplit")
        trPr.append(e)


def _para_border(p, edge="bottom", color=GOLD, size=8, space=4):
    pPr = p._p.get_or_add_pPr()
    pb = pPr.find(qn("w:pBdr"))
    if pb is None:
        pb = OxmlElement("w:pBdr")
    e = OxmlElement(f"w:{edge}")
    e.set(qn("w:val"), "single"), e.set(qn("w:sz"), str(size)), e.set(qn("w:space"), str(space)), e.set(qn("w:color"), color)
    pb.append(e)
    if pb.getparent() is None:
        pPr.append(pb)


def _keep_next(p):
    p.paragraph_format.keep_with_next = True


def _font(run, name=BODY, size=None, color=None, bold=None, italic=None, caps=False, spacing=None):
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    rf = rPr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rPr.insert(0, rf)
    for k in ("w:ascii", "w:hAnsi", "w:cs"):
        rf.set(qn(k), name)
    rf.set(qn("w:eastAsia"), CJK)
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if caps:
        run.font.all_caps = True
    if spacing is not None:
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:val"), str(int(spacing * 20)))
        rPr.append(sp)
    return run


def _raise(run, half_points=5):
    """A reference raised above the line at a size that stays legible (a true superscript shrinks it to ~5pt)."""
    pos = OxmlElement("w:position")
    pos.set(qn("w:val"), str(half_points))
    run._r.get_or_add_rPr().append(pos)
    return run


def _field(p, code, size=8, color=MUTED):
    for kind, text in (("begin", None), (None, code), ("separate", None), (None, "1"), ("end", None)):
        r = p.add_run()
        _font(r, size=size, color=color)
        if kind:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            r._r.append(fc)
        elif text == code:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = f" {code} "
            r._r.append(it)
        else:
            r.text = text


def nice_dates(text: str) -> str:
    """2026-10-08 as 8 Oct 2026, the date style of the rest of the note."""
    from datetime import date as _d

    def one(m):
        try:
            return _d.fromisoformat(m.group(0)).strftime("%d %b %Y").lstrip("0")
        except ValueError:
            return m.group(0)
    return re.sub(r"(?<![\w/-])\d{4}-\d{2}-\d{2}(?![\w/-])", one, text)


def rich(p, text, size=10, color=INK, bold=False, italic=False, font=BODY, sup=True):
    """Markdown-ish inline text: **bold**, _italic_, [n] as a raised reference in navy (inline when `sup` is
    False, as in a source line)."""
    text = nice_dates(text)
    for chunk in re.split(r"(\*\*[^*]+\*\*|(?<![\w])_[^_]+_(?![\w])|\[\d+\]|\[internal\])", text):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**"):
            _font(p.add_run(chunk[2:-2]), font, size, color, True, italic)
        elif chunk.startswith("_") and chunk.endswith("_") and len(chunk) > 2:
            _font(p.add_run(chunk[1:-1]), font, size, MUTED if not bold else color, bold, True)
        elif REF.fullmatch(chunk):
            r = _font(p.add_run(chunk), BODY, max(size * 0.78, 7.5) if sup else size,
                      NAVY if chunk != "[internal]" else GOLD, True)
            if sup:
                _raise(r)
        else:
            _font(p.add_run(chunk), font, size, color, bold, italic)
    return p


def para(doc_or_cell, text="", size=10, color=INK, bold=False, italic=False, font=BODY, after=4, before=0,
         align=None, line=1.15):
    p = doc_or_cell.add_paragraph()
    pf = p.paragraph_format
    pf.space_after, pf.space_before, pf.line_spacing = Pt(after), Pt(before), line
    if align:
        p.alignment = align
    if text:
        rich(p, text, size, color, bold, italic, font)
    return p


def eyebrow(doc, n, text):
    p = para(doc, before=14, after=2)
    _font(p.add_run(f"{n:02d}  ·  {text}"), BODY, 8, GOLD, True, caps=True, spacing=1.2)
    _keep_next(p)
    return p


def heading(doc, text, size=16, n=None, label=None, new_page=False):
    if n is not None:
        e = eyebrow(doc, n, label or text)
        if new_page:
            e.paragraph_format.page_break_before = True
            e.paragraph_format.space_before = Pt(0)
    p = para(doc, after=8, before=0 if n is not None else 12, line=1.0)
    _font(p.add_run(text), HEAD, size, NAVY)
    _para_border(p, "bottom", RULE, 4, 4)
    _keep_next(p)
    return p


# ------------------------------------------------------------------------------------------------------ charts
def _short(period: str) -> str:
    m = re.match(r"(Q\d)\s+(\d{4})", period or "")
    return f"{m.group(1)}\n'{m.group(2)[2:]}" if m else period


def _qnum(period: str):
    m = re.match(r"Q(\d)\s+(\d{4})", period or "")
    return int(m.group(2)) * 4 + int(m.group(1)) - 1 if m else None


def on_time_axis(data: list[dict]) -> tuple[list[dict | None], list[str]]:
    """The series with one slot per quarter from the first to the last, None where the library has no figure,
    so a missing quarter shows as a gap instead of two quarters drawn next to each other. Also the missing
    quarters' names, for the caption."""
    nums = [_qnum(d.get("period", "")) for d in data]
    if not data or None in nums:
        return list(data), []
    by = dict(zip(nums, data))
    slots = [by.get(q) for q in range(min(nums), max(nums) + 1)]
    names = [f"Q{q % 4 + 1} {q // 4}" for q in range(min(nums), max(nums) + 1)]
    return [d if d is not None else {"period": n, "value": None} for d, n in zip(slots, names)], \
        [n for d, n in zip(slots, names) if d is None]


def missing_quarters(data: list[dict]) -> list[str]:
    return on_time_axis(data)[1]


def _chart_png(kind, data, unit="", w=6.6, h=3.0) -> bytes:
    """A chart as a PNG in the house palette. The title and source sit outside it, as figure captions."""
    import logging
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager, rcParams
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    have = {f.name for f in font_manager.fontManager.ttflist}
    fams = ("Calibri", "Carlito", "Noto Sans CJK TC", "Noto Sans CJK SC", "Noto Sans CJK JP", "Microsoft JhengHei",
            "PingFang TC", "WenQuanYi Zen Hei", "DejaVu Sans")  # Chinese market names fall back to a CJK face
    rcParams.update({"font.family": [f for f in fams if f in have] or ["sans-serif"],
                     "font.size": 8.5, "axes.edgecolor": "#" + RULE, "axes.labelcolor": "#" + MUTED,
                     "xtick.color": "#" + MUTED, "ytick.color": "#" + MUTED, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.spines.left": False, "ytick.left": False})
    fig, ax = plt.subplots(figsize=(w, h), dpi=220)
    ax.set_facecolor("white")
    label = {"fontsize": 7.5, "color": "#" + INK, "bbox": {"boxstyle": "square,pad=0.15", "fc": "white", "ec": "none"}}
    if kind in ("line", "column"):
        data, gaps = on_time_axis(data)
        xs = list(range(len(data)))
        ys = [d["value"] for d in data]
        have = [y for y in ys if y is not None]
        lta = [d.get("lta") for d in data if d.get("lta") is not None]
        step = max(1, -(-len(data) // 10))  # at most about ten labels; the latest quarter always named
        ax.set_xticks(xs, [_short(d["period"]) if (len(data) - 1 - i) % step == 0 else "" for i, d in enumerate(data)])
        if kind == "line":
            seg = []  # a missing quarter breaks the line rather than being bridged
            for x, y in zip(xs + [None], ys + [None]):
                if y is None:
                    if seg:
                        ax.plot([a for a, _ in seg], [b for _, b in seg], color="#" + NAVY, lw=2.0, marker="o",
                                ms=3.5, zorder=3)
                    seg = []
                else:
                    seg.append((x, y))
            ax.plot(xs[-1:], ys[-1:], color="#" + GOLD, marker="o", ms=6, zorder=4)
            first = next(i for i, y in enumerate(ys) if y is not None)
            # the first value sits up and to the left of its point and the latest up and to the right, on the side
            # the line does not run, so no segment crosses either label
            for i, dx, ha in ((first, -4, "right"), (len(ys) - 1, 4, "left")):
                ax.annotate(f"{ys[i]:.1f}{unit}", (i, ys[i]), textcoords="offset points", xytext=(dx, 5), ha=ha,
                            va="bottom", fontsize=8, color="#" + INK, fontweight="bold", zorder=6,
                            bbox={"boxstyle": "square,pad=0.1", "fc": "white", "ec": "none", "alpha": 0.85})
            lo, hi = min(have + lta), max(have + lta)
            if hi - lo < 1e-9:  # one quarter, or every quarter the same: give the axis some height
                lo, hi = lo - (abs(lo) * 0.1 or 1), hi + (abs(hi) * 0.1 or 1)
            ax.set_ylim(lo - (hi - lo) * 0.35, hi + (hi - lo) * 0.3)
            for i, y in enumerate(ys):
                if y is None:
                    ax.text(i, lo - (hi - lo) * 0.2, "no\ndata", ha="center", va="center", fontsize=6.5,
                            color="#" + MUTED, style="italic")
        else:
            top = max(have + lta)
            top = top if top > 0 else 1.0  # all zero: still a visible axis
            ax.bar([x for x, y in zip(xs, ys) if y is not None], have, width=0.62, zorder=3,
                   color=["#" + BLUE] * (len(have) - 1) + ["#" + GOLD])
            avg = lta[-1] if lta else None
            for i, v in enumerate(ys):
                if v is None:
                    ax.text(i, top * 0.04, "no\ndata", ha="center", va="bottom", fontsize=6.5, color="#" + MUTED,
                            style="italic")
                    continue
                near = avg is not None and abs(v - avg) < top * 0.06  # a label on the dashed line: lift it clear
                ax.text(i, (max(v, avg) + top * 0.035) if near else v + top * 0.015, f"{v:.2f}", ha="center",
                        va="bottom", zorder=5, fontsize=7.5, color="#" + INK,
                        fontweight="bold" if i == len(ys) - 1 else "normal")
            ax.set_ylim(0, top * 1.18)
        if lta:
            ax.axhline(lta[-1], color="#" + (GOLD if kind == "line" else NAVY), lw=1.1, ls=(0, (4, 3)), zorder=2)
            if kind == "line":  # the column chart names its average in the caption, clear of the bars
                ax.text(-0.3, lta[-1], f"Long-term avg {lta[-1]:.1f}{unit}", va="top", ha="left", zorder=5,
                        **{**label, "color": "#" + GOLD})
        ax.margins(x=0.07 if kind == "column" else 0.11)  # room for the end labels beside the line
        ax.grid(axis="y", color="#" + RULE, lw=0.5)
        ax.tick_params(axis="x", labelsize=6.8, length=0)
        ax.tick_params(axis="y", labelsize=7)
    else:  # horizontal bars by market
        data = sorted([d for d in data if isinstance(d.get("value"), (int, float))], key=lambda d: d["value"])[-12:]
        names = [d["market"] for d in data]
        ys = [d["value"] for d in data]
        moved = [bool(d.get("change")) for d in data]
        ax.barh(names, ys, color=["#" + GOLD if m else "#" + BLUE for m in moved], height=0.62, zorder=3)
        for i, v in enumerate(ys):
            ax.text(v, i, f" {unit}{v:,.2f}" if unit == "£" else f" {v:g}", va="center", fontsize=7.5, color="#" + INK)
        ax.grid(axis="x", color="#" + RULE, lw=0.5)
        ax.set_xlim(0, (max(ys) * 1.15) or 1)
        ax.tick_params(axis="y", labelsize=7.5, length=0)
        ax.tick_params(axis="x", labelsize=7)
        ax.spines["left"].set_visible(True)
    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    return buf.getvalue()


# ------------------------------------------------------------------------------------------- document blocks
def takeaways(doc, hl: str, said: list[str]):
    """The headline, one sentence per line, in a shaded panel with a gold rule; its references follow the last."""
    box = doc.add_table(rows=1, cols=1)
    _fixed(box, [170])
    _no_split(box)
    _borders(box, inside_h=False)
    cell = box.rows[0].cells[0]
    _shade(cell, PANEL)
    _cell_border(cell, "left", GOLD, 24)
    _margins(cell, top=Mm(4).twips, bottom=Mm(3).twips, left=Mm(6).twips, right=Mm(6).twips)
    refs = "".join(f"[{r}]" for r in dict.fromkeys(REF.findall(hl)))
    cell.paragraphs[0].paragraph_format.space_after = Pt(0)
    for i, line in enumerate(said):
        line = unref(line)
        p = cell.paragraphs[0] if i == 0 else para(cell)
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.left_indent = Mm(5)
        p.paragraph_format.first_line_indent = Mm(-5)
        _font(p.add_run("■  "), BODY, 7, GOLD)
        rich(p, line + (" " + refs if refs and i == len(said) - 1 else ""), 10.5, INK, font=BODY)


def _move_colour(change: str, label: str) -> str:
    if not change.startswith(("+", "-")) or re.match(r"[+-]0(\.0+)?(?!\d)", change):
        return INK
    up = change.startswith("+")
    good = (not up) if down_is_good(label) else up
    return GOOD if good else BAD


def tiles_and_table(doc, rows, head, body, col, n):
    """KPI tiles (the first four London rows, or the first four rows) and the key-numbers table, whatever its
    columns are."""
    if not rows:
        return
    get = lambda r, k: r[col[k]] if k in col and col[k] < len(r) else ""  # noqa: E731
    if "latest" in col:
        london = [r for r in body if get(r, "market").strip().lower() in ("london", "central london", "倫敦", "伦敦")]
        tiles = (london or body)[:4]
        if tiles:
            para(doc, after=2)
            kt = doc.add_table(rows=1, cols=len(tiles))
            _fixed(kt, [170 / len(tiles) - 0.01] * len(tiles))
            _no_split(kt)
            _borders(kt, inside_h=False)
            for cell, r in zip(kt.rows[0].cells, tiles):
                _cell_border(cell, "top", GOLD, 18)
                _margins(cell, top=Mm(3).twips, left=Mm(2).twips, right=Mm(3).twips)
                label = get(r, "metric") or get(r, "market")
                _font(cell.paragraphs[0].add_run(label.upper()), BODY, 7, MUTED, True, spacing=0.6)
                p = para(cell, after=0, line=1.0)
                _font(p.add_run(nice_dates(unref(get(r, "latest")))), HEAD, 17, NAVY)
                for m in REF.findall(get(r, "latest")):
                    _raise(_font(p.add_run(f"[{m}]"), BODY, 8.5, NAVY, True), 8)
                chg = get(r, "change")
                colour = _move_colour(chg, label)
                mark = "▲ " if chg.startswith("+") and colour != INK else "▼ " if chg.startswith("-") and colour != INK else "● "
                _font(para(cell, after=0).add_run(mark + (chg or get(r, "period"))), BODY, 8,
                      MUTED if colour == INK else colour)
    n_cols = len(head)
    widths = [32, 46, 32, 20, 40] if n_cols == 5 else [170 / n_cols - 0.01] * n_cols
    heading(doc, "Key numbers", 16, n, "Market data")
    t = doc.add_table(rows=len(rows), cols=n_cols)
    _fixed(t, widths)
    _no_split(t)
    t.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))  # repeats on a new page
    _borders(t, RULE, True, True, 4)
    for ri, r in enumerate(rows):
        label = get(r, "metric") or get(r, "market")
        for ci, txt in enumerate(r):
            cell = t.rows[ri].cells[ci]
            _margins(cell, top=Mm(1.4).twips, bottom=Mm(1.4).twips, left=Mm(2).twips, right=Mm(2).twips)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            if ci == col.get("latest"):
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            if ri == 0:
                _shade(cell, NAVY)
                _font(p.add_run(txt.upper()), BODY, 7.5, "FFFFFF", True, spacing=0.5)
                continue
            if ri % 2 == 0:
                _shade(cell, "F7F6F2")
            colour = _move_colour(txt, label) if ci == col.get("change") else INK
            rich(p, txt, 9, colour, bold=(ci == col.get("latest")))
    p = para(doc, before=3, after=0)
    _font(p.add_run("Change is against the previous quarter; pp = percentage points. Green and red show whether "
                    "the move is good or bad for an owner of London offices."), BODY, 7.5, MUTED, italic=True)


def section_table(doc, rows):
    """Any other table in the brief: a navy header row, the first column as the row label, the rest equal."""
    if not rows:
        return
    n_cols = len(rows[0])
    first = 40 if n_cols > 2 else 85
    widths = [first] + [(170 - first) / (n_cols - 1) - 0.01] * (n_cols - 1) if n_cols > 1 else [170]
    t = doc.add_table(rows=len(rows), cols=n_cols)
    _fixed(t, widths)
    _no_split(t)
    t.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    _borders(t, RULE, True, True, 4)
    for ri, r in enumerate(rows):
        for ci, txt in enumerate(r):
            cell = t.rows[ri].cells[ci]
            _margins(cell, top=Mm(1.4).twips, bottom=Mm(1.4).twips, left=Mm(2).twips, right=Mm(2).twips)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            if ri == 0:
                _shade(cell, NAVY)
                _font(p.add_run(txt.upper()), BODY, 7.5, "FFFFFF", True, spacing=0.5)
                continue
            if ri % 2 == 0:
                _shade(cell, "F7F6F2")
            m = re.match(r"^(.*?)\s*\(([+-][\d.]+(?:pp)?)\)$", txt)  # 'value [n] (+0.50pp)': the move in colour
            if ci and m:
                rich(p, m.group(1), 9, INK)
                _font(p.add_run(f"  {m.group(2)}"), BODY, 8, _move_colour(m.group(2), r[0]))
            else:
                rich(p, txt, 9, NAVY if ci == 0 else INK, bold=(ci == 0))
    if len(rows) <= 15:  # a short table stays on one page with its heading: each row keeps with the next
        for r in t.rows[:-1]:
            for cell in r.cells:
                for p in cell.paragraphs:
                    _keep_next(p)
    para(doc, after=2)


def draw_charts(doc, charts, deck_cite):
    """Vacancy and take-up side by side, then rents full width. A chart that cannot be drawn is left out with a
    line saying so; it never stops the note."""
    def figure(cell_or_doc, i, k, data, caption, unit, ref, width_mm):
        try:
            png = _chart_png(k, data, unit, w=width_mm / 25.4,
                             h=(2.7 if width_mm < 120 else 3.3 if k == "barh" else 2.5))
        except Exception as e:  # noqa: BLE001
            para(cell_or_doc, f"Figure {i}: {caption} could not be drawn ({type(e).__name__}).", 8, MUTED, italic=True)
            return
        p = para(cell_or_doc, after=3, line=1.0)
        _keep_next(p)
        _font(p.add_run(f"Figure {i}   "), BODY, 8.5, GOLD, True)
        _font(p.add_run(caption), BODY, 8.5, NAVY, True)
        lta = [d.get("lta") for d in data if d.get("lta") is not None]
        note = {"line": "Quarter end; gold dashed line: long-term average",
                "column": "Latest quarter in gold" + (f"; dashed line: long-term average {lta[-1]:.2f}" if lta else ""),
                "barh": "Latest quarter; gold: moved since the previous quarter"}[k]
        if k in ("line", "column") and (gone := missing_quarters(data)):
            note += (f". No figure in the library for {' and '.join(gone)}" if len(gone) <= 3
                     else f". No figure in the library for {len(gone)} of these quarters")
        p = para(cell_or_doc, after=4, line=1.0)
        _keep_next(p)
        _font(p.add_run(note), BODY, 7.5, MUTED, italic=True)
        p = para(cell_or_doc, after=0, line=1.0)
        _keep_next(p)
        p.add_run().add_picture(io.BytesIO(png), width=Mm(width_mm - (3 if width_mm < 120 else 0)))
        p = para(cell_or_doc, after=0, before=2, line=1.0)
        _para_border(p, "top", RULE, 4, 2)
        _font(p.add_run("Source: "), BODY, 7.5, MUTED)
        rich(p, deck_cite(ref) or "the team library", 7.5, NAVY, sup=False)
        if k == "line":
            refs = sorted({deck_cite(d.get("ref")) for d in data if d.get("ref")} - {"", deck_cite(ref)},
                          key=lambda x: int(x[1:-1]))
            if refs:
                _font(p.add_run("; earlier quarters "), BODY, 7.5, MUTED)
                rich(p, "".join(refs), 7.5, NAVY, sup=False)

    pair = [c for c in charts if c[0] in ("line", "column")]
    num = 0
    rest = charts
    if len(pair) == 2:  # the two time series side by side, as a research note sets them
        t = doc.add_table(rows=1, cols=3)
        _fixed(t, [82, 6, 82])
        _no_split(t)
        _borders(t, inside_h=False)
        for cell, c in zip((t.rows[0].cells[0], t.rows[0].cells[2]), pair):
            num += 1
            figure(cell, num, *c, 82)
            if len(cell.paragraphs) > 1:
                cell._tc.remove(cell.paragraphs[0]._p)  # the empty first paragraph python-docx adds
        rest = [c for c in charts if c not in pair]
        para(doc, after=8)
    for c in rest:
        num += 1
        figure(doc, num, *c, 170)
        para(doc, after=6)


# ------------------------------------------------------------------------------------------------- the document
def build_docx(md: str, deck: dict, out: Path, team: str = "London office team") -> Path:
    """`md` is the brief as written; `deck` is skills.brief_deck.tools.deck_data (series for the charts)."""
    b = parse(md)
    sources = list(b.sources)

    def key(text: str) -> tuple[str, str]:
        """A source as (title, url): the [n], the '(Uploaded by …)' channel note and the link taken apart."""
        body = re.sub(r"^\s*\[\d+\]\s*", "", text or "")
        title, _, url = body.partition(" - http")
        title = re.sub(r"\s*\((?:Uploaded|Collected|Shared)[^)]*\)\s*$", "", title).strip().lower()
        return title, ("http" + url.strip()) if url else ""

    def cite(title_text: str) -> str:
        """[n] for a source, matched on its whole title (and link when both have one), never on part of a title;
        added to the Sources list when the text did not cite it."""
        t, u = key(title_text)
        for i, src in enumerate(sources, 1):
            st_, su = key(src)
            if t and t == st_ and (not u or not su or u == su):
                return f"[{i}]"
        sources.append(f"[{len(sources) + 1}] {re.sub(r'^\s*\[\d+\]\s*', '', title_text)}")
        return f"[{len(sources)}]"

    def deck_cite(ref: str) -> str:
        m = re.match(r"\[(\d+)\]", ref or "")
        foot = deck.get("footnotes") or []
        return cite(foot[int(m.group(1)) - 1]) if m and int(m.group(1)) <= len(foot) else ""

    doc = Document()
    styles = doc.styles
    st = styles["Normal"]
    st.font.name, st.font.size = BODY, Pt(10)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), CJK)
    date_text = (b.sub.split("·")[0].strip() if b.sub else "")
    rows = table_rows(b.numbers)
    head, body = (rows[0], rows[1:]) if rows else ([], [])
    col = columns(head)
    period = next((r[col["period"]] for r in body[:1] if "period" in col), "")
    dated = [t for t in (date_text, f"Data to {period}" if period else "") if t]  # only the parts the brief gives

    def series(name):  # a chart only when it has numbers to draw
        return [d for d in (deck.get(name) or []) if isinstance(d.get("value"), (int, float))]
    charts = []  # (kind, series, caption, unit, ref of the latest point)
    if (v := series("vacancy")):
        charts.append(("line", v, "Central London vacancy rate (%)", "%", v[-1].get("ref")))
    if (v := series("take_up")):
        charts.append(("column", v, "Central London take-up (m sq ft)", "", v[-1].get("ref")))
    if (v := series("rents")):
        charts.append(("barh", v, "Prime office rent by submarket (£ per sq ft)", "£", v[0].get("ref")))
    for c in charts:  # number the charts' sources now, in reading order
        deck_cite(c[4])
        if c[0] == "line":
            for d in c[1]:
                deck_cite(d.get("ref"))
    hl = " ".join(ln.strip() for ln in b.headline if ln.strip())
    said = sentences(hl)
    report = "London Office Market · Team Brief"
    doc.core_properties.title = report
    doc.core_properties.author = team
    doc.core_properties.subject = "London office market research note"

    # ---- cover: a full-bleed navy band
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Mm(0)
    sec.header_distance = sec.footer_distance = Mm(0)
    band = doc.add_table(rows=1, cols=1)
    band.alignment = WD_TABLE_ALIGNMENT.CENTER
    _fixed(band, [210])
    _borders(band, inside_h=False)
    row = band.rows[0]
    row.height, row.height_rule = Mm(178), WD_ROW_HEIGHT_RULE.AT_LEAST  # grows rather than cuts a long line
    c = row.cells[0]
    _shade(c, NAVY)
    _margins(c, top=Mm(22).twips, left=Mm(22).twips, right=Mm(22).twips, bottom=Mm(14).twips)
    c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    p = c.paragraphs[0]
    p.add_run().add_picture(str(BRAND / "cobrand-nanfung-on-dark@2x.png"), width=Mm(92))
    para(c, after=0, before=0).add_run().add_break()
    for _ in range(5):
        para(c, after=6)
    p = para(c, after=6)
    _font(p.add_run("RESEARCH  ·  TEAM BRIEF"), BODY, 9, GOLD, True, spacing=2)
    p = para(c, after=10, line=1.0)
    _font(p.add_run("London Office Market"), HEAD, 34, "FFFFFF")
    p = para(c, after=18, line=1.0)
    _font(p.add_run("Weekly brief"), HEAD, 22, "C9D1DE", italic=True)
    p = para(c, after=4)
    _para_border(p, "top", GOLD, 12, 10)
    first = unref(said[0]) if said else ""
    if len(first) > 230:  # the cover takes one sentence; a very long one is cut at a word, the page has it all
        first = first[:230].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    if first:
        rich(p, first, 12.5, "FFFFFF", font=HEAD, italic=True)
    p = para(c, after=0, before=10)
    _font(p.add_run("   ·   ".join(dated + [team])), BODY, 9.5, "C9D1DE")

    meta = doc.add_table(rows=1, cols=2)
    _fixed(meta, [126, 84])
    _borders(meta, inside_h=False)
    left, right = meta.rows[0].cells
    for cell in (left, right):
        _margins(cell, top=Mm(16).twips, left=Mm(22).twips, right=Mm(22).twips)
    p = left.paragraphs[0]
    _font(p.add_run("ABOUT THIS NOTE"), BODY, 8, GOLD, True, spacing=1.2)
    para(left, "Built from the signals the team added this week and the figures in the shared library. Every "
               "figure carries a reference [n] to its source, listed at the end.", 9.5, INK, after=6)
    para(left, b.sub.replace("·", " · ") if b.sub else "", 9, MUTED, italic=True, after=0)
    p = right.paragraphs[0]
    _font(p.add_run("CONTENTS"), BODY, 8, GOLD, True, spacing=1.2)
    toc = (["Key takeaways"] if said else []) + (["Key numbers"] if rows else []) + (["Charts"] if charts else []) \
        + [h for h, _ in b.sections] + (["Sources"] if sources else []) + ["Important information"]
    for i, t in enumerate(toc, 1):
        p = para(right, after=1)
        _font(p.add_run(f"{i:02d}  "), BODY, 9, GOLD, True)
        _font(p.add_run(t), BODY, 9, INK)
    p = para(doc, before=0, after=0)
    p.paragraph_format.left_indent = Mm(22)

    # ---- content section with running header and footer
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    sec.top_margin, sec.bottom_margin = Mm(30), Mm(20)
    sec.left_margin = sec.right_margin = Mm(20)
    sec.header_distance, sec.footer_distance = Mm(10), Mm(9)
    sec.header.is_linked_to_previous = False
    sec.footer.is_linked_to_previous = False
    hdr = sec.header
    ht = hdr.add_table(rows=1, cols=2, width=Mm(170))
    _fixed(ht, [80, 90])
    _borders(ht, inside_h=False)
    hl_, hr_ = ht.rows[0].cells
    hl_.paragraphs[0].add_run().add_picture(str(BRAND / "cobrand-nanfung@2x.png"), width=Mm(56))
    hl_.vertical_alignment = hr_.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = hr_.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _font(p.add_run(report.upper()), BODY, 7.5, NAVY, True, spacing=0.8)
    p = para(hr_, after=0, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _font(p.add_run(" · ".join(dated)), BODY, 7.5, MUTED)
    p = hdr.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    _para_border(p, "bottom", GOLD, 8, 1)
    hdr._element.append(p._p)  # the gold rule under the header table
    ft = sec.footer
    p = ft.paragraphs[0]
    _para_border(p, "top", RULE, 4, 4)
    tabs = p.paragraph_format.tab_stops
    tabs.add_tab_stop(Mm(170), alignment=2)
    _font(p.add_run("London Office Market Agent  ·  Prepared for Nan Fung Group  ·  For internal discussion"), BODY, 7.5, MUTED)
    _font(p.add_run("\tPage "), BODY, 7.5, MUTED)
    _field(p, "PAGE", 7.5, NAVY)
    _font(p.add_run(" of "), BODY, 7.5, MUTED)
    _field(p, "NUMPAGES", 7.5, MUTED)

    n = 0
    # ---- key takeaways
    if said:
        n += 1
        heading(doc, "Key takeaways", 18, n, "Summary")
        takeaways(doc, hl, said)
    tiles_and_table(doc, rows, head, body, col, n + 1 if rows else n)
    n += 1 if rows else 0
    flagged = [ln for ln in b.numbers if ln.strip().startswith("_")]
    for f in flagged:
        para(doc, f.strip(), 8, BAD, italic=True, after=2)

    # ---- charts
    if charts:
        n += 1
        heading(doc, "Charts", 16, n, "Trends")
        draw_charts(doc, charts, deck_cite)

    # ---- the remaining sections, as written
    for h, lines in b.sections:
        n += 1
        heading(doc, h, 16, n, {"Submarket": "Evidence", "What changed": "Signals", "Supports": "Signals", "Risks": "Signals", "Other": "Signals",
                                "Our deals": "Internal", "Market deals": "Evidence", "Market talk": "Unconfirmed",
                                "Macro": "Context"}.get(next((k for k in ("Submarket", "What changed", "Supports", "Risks", "Other",
                                                                          "Our deals", "Market deals", "Market talk",
                                                                          "Macro") if h.startswith(k)), ""), "Detail"))
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            i += 1
            if not s:
                continue
            if _is_table(s):  # a table inside a section, e.g. the submarket evidence: drawn whatever its columns
                block = [s]
                while i < len(lines) and _is_table(lines[i]):
                    block.append(lines[i].strip())
                    i += 1
                section_table(doc, table_rows(block))
                continue
            if s.startswith("### "):
                p = para(doc, before=8, after=3)
                _keep_next(p)
                _font(p.add_run(s[4:].strip()), HEAD, 12, NAVY)
                continue
            if s.startswith("- "):
                s = s[2:]
                m = re.match(r"^([▲▼●])\s+\*\*(.+?)\*\*\.?\s*(.*)$", s)
                if m:  # a signal: marker, title, detail [n], _why_
                    arrow, title, rest = m.groups()
                    why = ""
                    if (w := re.search(r"\s_([^_]+)_\s*$", rest)):
                        why, rest = w.group(1), rest[: w.start()]
                    t = doc.add_table(rows=1, cols=2)
                    _fixed(t, [8, 162])
                    _no_split(t)
                    _borders(t, inside_h=False)
                    a, body_c = t.rows[0].cells
                    _margins(a, top=Mm(1).twips)
                    _margins(body_c, top=Mm(0.6).twips, bottom=Mm(2.4).twips, left=Mm(1).twips)
                    _cell_border(body_c, "bottom", RULE, 4)
                    _cell_border(a, "bottom", RULE, 4)
                    pa = a.paragraphs[0]
                    _font(pa.add_run(arrow), BODY, 11, GOOD if arrow == "▲" else BAD if arrow == "▼" else MUTED, True)
                    p = body_c.paragraphs[0]
                    p.paragraph_format.space_after = Pt(2)
                    rich(p, title, 10.5, NAVY, bold=True, font=HEAD)
                    rich(para(body_c, after=2), rest.strip(), 9.5, INK)
                    if why:
                        p = para(body_c, after=0)
                        _font(p.add_run("Why it matters  "), BODY, 7.5, GOLD, True, spacing=0.5)
                        rich(p, why, 9, MUTED, italic=True)
                else:
                    p = para(doc, after=3)
                    p.paragraph_format.left_indent = Mm(5)
                    p.paragraph_format.first_line_indent = Mm(-5)
                    _font(p.add_run("■  "), BODY, 7, GOLD)
                    rich(p, s, 9.5, INK)
            elif s.startswith("_") and s.endswith("_"):
                para(doc, s, 8.5, MUTED, italic=True, after=4)
            else:
                para(doc, s, 10, INK, after=4)

    # ---- sources
    if sources:
        n += 1
        heading(doc, "Sources", 16, n, "References")
    for s in sources:
        m = re.match(r"^\[(\d+)\]\s*(.*)$", s)
        if not m:
            continue
        num, rest = m.groups()
        title_, _, url = rest.partition(" - http")
        p = para(doc, after=3)
        p.paragraph_format.left_indent = Mm(8)
        p.paragraph_format.first_line_indent = Mm(-8)
        _font(p.add_run(f"[{num}]\t"), BODY, 8.5, NAVY, True)
        p.paragraph_format.tab_stops.add_tab_stop(Mm(8))
        _font(p.add_run(nice_dates(title_.strip())), BODY, 8.5, INK)
        if url:
            _font(p.add_run("  http" + url.strip()), BODY, 7.5, BLUE)

    # ---- important information
    n += 1
    heading(doc, "Important information", 16, n, "Disclaimer", new_page=True)
    info = [
        ("About this note", "This research note was generated by the London Office Market Agent, a proof of concept "
         "built for Nan Fung Group's London office team. It summarises the signals the team selected and the figures "
         "in the team's shared library at the date shown."),
        ("Data", (b.caveat or "") + " Market figures are restated from public Knight Frank research reports for "
         "evaluation of this proof of concept only; Knight Frank's terms do not permit the use of their data by AI "
         "systems or for commercial purposes. Bank Rate is from the Bank of England. Internal deals are demonstration "
         "data. Verify every figure against the original source, linked in Sources, before any external use."),
        ("Unconfirmed information", "Market talk shared by colleagues is shown separately and marked unconfirmed; "
         "do not rely on it until a published source confirms it."),
        ("Not advice", "Nothing in this note is investment, legal or tax advice, or an offer or solicitation to buy "
         "or sell any property or security. It is intended for internal discussion within the team and is not for "
         "distribution outside it."),
        ("Trademarks", "The Nan Fung Group name and logo are trademarks of Nan Fung Group, used here only for this "
         "interview proof of concept; their use is not a claim of affiliation or endorsement."),
    ]
    for h, text in info:
        p = para(doc, before=6, after=2)
        _font(p.add_run(h.upper()), BODY, 8, NAVY, True, spacing=0.8)
        para(doc, text, 9, INK, after=4, line=1.25)
    p = para(doc, before=18, after=0)
    p.add_run().add_picture(str(BRAND / "cobrand-nanfung@2x.png"), width=Mm(70))

    _tidy(doc.element)
    for s_ in doc.sections:
        for part in (s_.header, s_.footer):
            if not part.is_linked_to_previous:
                _tidy(part._element)
    zoom = doc.settings.element.find(qn("w:zoom"))
    if zoom is not None and zoom.get(qn("w:percent")) is None:
        zoom.set(qn("w:percent"), "100")
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out


def plain_docx(md: str, out: Path, team: str) -> Path:
    """The safety net: the brief as a plain, still-branded document (header logo, headings, paragraphs, tables),
    used only if the research-note layout meets content it cannot place, so a download never fails."""
    doc = Document()
    doc.styles["Normal"].font.name = BODY
    doc.styles["Normal"].element.rPr.rFonts.set(qn("w:eastAsia"), CJK)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin = sec.right_margin = Mm(20)
    sec.header.paragraphs[0].add_run().add_picture(str(BRAND / "cobrand-nanfung@2x.png"), width=Mm(56))
    lines = (md or "").splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if _is_table(ln):
            block = []
            while i < len(lines) and _is_table(lines[i]):
                block.append(lines[i])
                i += 1
            rows = table_rows(block)
            if rows:
                t = doc.add_table(rows=len(rows), cols=len(rows[0]))
                t.style = "Table Grid"
                for r, row in zip(t.rows, rows):
                    for c, txt in zip(r.cells, row):
                        rich(c.paragraphs[0], txt, 9)
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", ln)
        if m:
            p = para(doc, after=6, before=10)
            _font(p.add_run(m.group(2)), HEAD, {1: 20, 2: 15, 3: 12}[len(m.group(1))], NAVY)
        elif ln.strip():
            para(doc, re.sub(r"^\s*[-*]\s+", "■  ", ln.strip()), 10, INK, after=4)
        i += 1
    para(doc, "Not investment advice. For internal discussion within the team. Figures restated from public research "
              "for evaluation of this proof of concept; verify against the original before external use.", 8, MUTED,
         italic=True, before=12)
    _tidy(doc.element)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out


def build(ctx, md: str, out_dir: Path) -> dict:
    """The .docx and its PDF under out_dir. Returns {"docx", "pdf", "why"}; without LibreOffice there is no PDF
    and `why` says so."""
    from core import preview
    from skills.brief_deck import tools as bd
    deck = bd.deck_data(ctx)
    name = "london-office-team-brief"
    team = ctx.config.get("team", {}).get("name", "London office team")
    out = Path(out_dir) / f"{name}.docx"
    with _LOCK:  # matplotlib's pyplot is not thread-safe, and two pages may ask at once
        try:
            docx = build_docx(md, deck, out, team)
        except Exception as e:  # noqa: BLE001  (content the layout did not expect: still give the reader a file)
            print(f"[report] research-note layout failed, plain layout used: {e!r}", flush=True)
            docx = plain_docx(md, out, team)
    pdf, why = preview.render_pdf(docx, out_dir)
    if pdf:
        final = Path(out_dir) / f"{name}.pdf"
        Path(pdf).replace(final)
        pdf = str(final)
    return {"docx": str(docx), "pdf": pdf, "why": why}
