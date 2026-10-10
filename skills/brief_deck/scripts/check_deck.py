"""Check a built deck before it goes out:  python3 check_deck.py deck.pptx [--data brief.json]

The QA loop from Grok Build's pptx skill, reimplemented for this deck: assume there are problems and
look for them. Checks slide count (3-6), Cover first and Sources last, empty or leftover placeholder
text, speaker notes on every slide, text likely to overflow its box, text boxes that overlap each
other or run off the slide, fonts used, and (with --data) any number the data does not hold.
Prints a JSON report; exit code 1 if anything fails. Always render and look at the slides as well."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

sys.path.insert(0, str(Path(__file__).parent))
from build_deck import MAX_SLIDES, MIN_SLIDES, check_text  # noqa: E402

CHARS_PER_SQIN = {8: 260, 9: 210, 10: 170, 11: 140, 12: 118, 13: 100, 14: 86, 15: 76, 16: 66, 22: 34, 24: 29,
                  26: 25, 30: 18, 38: 11, 60: 4}
LEFTOVER = re.compile(r"xxxx|lorem|ipsum|click to add|todo", re.I)


def fits(shape) -> bool:
    """Rough capacity check: characters against the box area at the text's most common point size."""
    if not shape.has_text_frame or not shape.text_frame.text.strip():
        return True
    sizes = [r.font.size.pt for p in shape.text_frame.paragraphs for r in p.runs if r.font.size] or [13]
    common = max(set(sizes), key=sizes.count)
    size = min(CHARS_PER_SQIN, key=lambda s: abs(s - common))
    sq_in = Emu(shape.width).inches * Emu(shape.height).inches
    return len(shape.text_frame.text) <= CHARS_PER_SQIN[size] * sq_in * 1.1


def inherited_size(shape) -> float | None:
    """Point size of a placeholder whose runs carry none of their own: read from the layout placeholder."""
    if not shape.is_placeholder:
        return None
    try:
        lp = shape.slide_layout_placeholder if hasattr(shape, "slide_layout_placeholder") else None
    except Exception:  # noqa: BLE001
        lp = None
    if lp is None:
        layout = shape.part.slide_layout if hasattr(shape.part, "slide_layout") else None
        idx = shape.placeholder_format.idx
        lp = next((p for p in (layout.placeholders if layout else []) if p.placeholder_format.idx == idx), None)
    if lp is None:
        return None
    sz = lp._element.xpath(".//a:defRPr/@sz") or lp._element.xpath(".//a:rPr/@sz")
    return int(sz[0]) / 100 if sz else None


def wraps_out(shape) -> bool:
    """Large text (titles, hero figures, KPI tiles): does it need more lines than its box has room for? The
    area check misses this: a 38pt title fits by area and still wraps a second line over the subtitle."""
    width_pt, height_pt = Emu(shape.width).pt, Emu(shape.height).pt
    fallback = inherited_size(shape)
    need, big = 0.0, False
    for para in shape.text_frame.paragraphs:
        text = "".join(r.text for r in para.runs)
        sizes = [r.font.size.pt for r in para.runs if r.font.size] or ([fallback] if fallback else [13])
        size = max(sizes)
        big = big or size >= 20
        lines = max(1, math.ceil(len(text) * size * 0.5 / width_pt)) if text else 1
        need += lines * size * 1.2
    return big and need > height_pt * 1.15


EYEBROW = re.compile(r"^\d{2}\s*[·•]\s*[^a-z]*$|^[^a-z]{1,40}$")  # "03 · EVIDENCE", "SOURCES", labels
CHROME = re.compile(r"^(\d{2} / \d{2}|SO WHAT.*)$", re.S)


def is_content(sh) -> bool:
    """A chart, table, picture, or text that is not the title, eyebrow, a label, the so-what band or page number."""
    if getattr(sh, "has_chart", False) and sh.has_chart or getattr(sh, "has_table", False) and sh.has_table:
        return True
    if sh.shape_type == 13:  # picture
        return True
    if sh.name.lower().startswith(("title", "eyebrow")):
        return False
    if sh.has_text_frame:
        t = sh.text_frame.text.strip()
        return bool(t) and not CHROME.match(t) and not EYEBROW.match(t)
    return False


def box(sh):
    return (sh.left or 0, sh.top or 0, (sh.left or 0) + (sh.width or 0), (sh.top or 0) + (sh.height or 0))


def overlap(a, b) -> bool:
    ax0, ay0, ax1, ay1 = box(a)
    bx0, by0, bx1, by1 = box(b)
    ix, iy = min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0)
    return ix > Emu(91440 * 0.05) and iy > Emu(91440 * 0.05)  # more than 0.05 in both ways


def check(path: str, data: dict | None = None) -> dict:
    prs = Presentation(path)
    W, H = prs.slide_width, prs.slide_height
    problems, fonts, charts = [], set(), 0
    n = len(prs.slides)
    if not MIN_SLIDES <= n <= MAX_SLIDES:
        problems.append(f"{n} slides (want {MIN_SLIDES}-{MAX_SLIDES})")
    names = [s.slide_layout.name for s in prs.slides]
    if names and names[0] != "Cover":
        problems.append("first slide is not the Cover")
    if names and names[-1] != "Sources":
        problems.append("last slide is not Sources")
    for i, s in enumerate(prs.slides, 1):
        for sh in s.placeholders:
            if sh.has_text_frame and not sh.text_frame.text.strip():
                problems.append(f"slide {i}: empty placeholder {sh.name}")
        if not s.has_notes_slide or not s.notes_slide.notes_text_frame.text.strip():
            problems.append(f"slide {i}: no speaker notes")
        texts = [sh for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip()]
        for sh in s.shapes:
            charts += bool(getattr(sh, "has_chart", False) and sh.has_chart)
            x0, y0, x1, y1 = box(sh)
            if x0 < 0 or y0 < 0 or x1 > W + 9144 or y1 > H + 9144:
                problems.append(f"slide {i}: {sh.name} runs off the slide")
        if s.slide_layout.name not in ("Cover", "Section", "Statement") and not any(is_content(sh) for sh in s.shapes):
            problems.append(f"slide {i}: nothing on the slide besides the title (no chart, table or text)")
        for sh in texts:
            fonts.update(r.font.name for p in sh.text_frame.paragraphs for r in p.runs if r.font.name)
            if not fits(sh):
                problems.append(f"slide {i}: text may overflow in {sh.name}")
            elif wraps_out(sh):
                problems.append(f"slide {i}: {sh.name} wraps onto more lines than its box holds; shorten it")
            if LEFTOVER.search(sh.text_frame.text):
                problems.append(f"slide {i}: leftover placeholder text in {sh.name}")
            if data:
                bad = check_text(sh.text_frame.text, data)
                if bad:
                    problems.append(f"slide {i}: numbers not in the data: {', '.join(sorted(set(bad)))}")
        for a_i, a in enumerate(texts):
            for b in texts[a_i + 1:]:
                if overlap(a, b):
                    problems.append(f"slide {i}: text boxes overlap: {a.name} / {b.name}")
    return {"path": path, "slides": n, "layouts": names, "charts": charts, "fonts": sorted(fonts),
            "ok": not problems, "problems": problems}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--data")
    a = ap.parse_args()
    report = check(a.deck, json.loads(Path(a.data).read_text()) if a.data else None)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    sys.exit(0 if report["ok"] else 1)
