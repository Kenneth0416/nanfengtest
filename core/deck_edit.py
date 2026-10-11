"""Editing a built deck by instruction when the Copilot is offline: a few plain commands on the spec (remove,
move, retitle, add a slide from this week's stories, change the theme), applied by rules. The Copilot does the
same job with judgement when it is online; this keeps the slide editor's chat useful without a model."""
from __future__ import annotations

import copy
import re

THEME_WORDS = {"forest": "forest-cream", "green": "forest-cream", "charcoal": "charcoal-amber", "amber": "charcoal-amber",
               "dark": "charcoal-amber", "navy": "navy-gold", "gold": "navy-gold", "editorial": "editorial-cream",
               "cream": "editorial-cream", "white": "data-white", "data white": "data-white"}
MIN_SLIDES, MAX_SLIDES = 3, 6
HELP = ("I can change this deck by instruction without the Copilot: `remove slide 3`, `move slide 4 to 2`, "
        "`swap slides 2 and 3`, `retitle slide 2 \"Vacancy keeps falling\"`, `set the so-what of slide 2 to \"…\"`, "
        "`add a slide on rents` (or investment, deals, requirements: anything in this week's stories), "
        "`add a statement slide \"…\"`, `theme forest`. Titles must not carry figures that are not in the data.")

_ORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "first": 1, "second": 2, "third": 3,
        "fourth": 4, "fifth": 5, "sixth": 6, "last": -1}


def _n(tok: str) -> int | None:
    tok = tok.strip().lower()
    return int(tok) if tok.isdigit() else _ORD.get(tok)


def _renumber(spec: dict) -> dict:
    n = 1
    for s in spec["slides"][1:]:
        if s.get("layout") == "Sources":
            continue
        n += 1
        if re.match(r"^\d\d\s+·\s+", s.get("eyebrow") or ""):
            s["eyebrow"] = re.sub(r"^\d\d(\s+·\s+)", f"{n:02d}\\1", s["eyebrow"])
        elif not s.get("eyebrow"):
            s["eyebrow"] = f"{n:02d}  ·  {(s.get('key') or '').replace('_', ' ')}"
    return spec


def _find(spec: dict, text: str) -> int | None:
    """A slide by number ('slide 3', 'the third slide', 'the last slide') or by what it is about ('the rents slide')."""
    slides = spec["slides"]
    m = re.search(r"\b(?:slide|page)\s*(?:number\s*)?(\d+|one|two|three|four|five|six|last)\b", text, re.I) or \
        re.search(r"\b(first|second|third|fourth|fifth|sixth|last)\s+(?:slide|page)\b", text, re.I)
    if m:
        n = _n(m.group(1))
        if n == -1:
            return len(slides)
        return n if n and 1 <= n <= len(slides) else None
    t = text.lower()
    for i, s in enumerate(slides, 1):
        words = {(s.get("key") or "").lower().replace("_", " ")} | set((s.get("title") or "").lower().split())
        if any(w and len(w) > 3 and re.search(rf"\b{re.escape(w)}\b", t) for w in words):
            return i
    return None


def _quoted(text: str) -> str:
    m = re.search(r"[\"“”']([^\"“”']{3,})[\"“”']", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(?:to|as|:)\s+(.+)$", text.strip().rstrip("."), re.I)
    return m.group(1).strip().strip("\"'") if m else ""


def apply(instruction: str, spec: dict, stories: list[dict] | None = None) -> tuple[dict | None, str]:
    """(revised spec, what was done) or (None, why not / what I can do). Never changes `spec` in place."""
    spec = copy.deepcopy(spec)
    slides = spec["slides"]
    t = instruction.strip()
    low = t.lower()
    if re.search(r"\b(remove|delete|drop|take out|cut)\b", low):
        i = _find(spec, t)
        if not i:
            return None, "Which slide? Say its number, for example `remove slide 3`."
        if i == 1:
            return None, "The cover stays: it carries the headline and the KPIs."
        if len(slides) - 1 < MIN_SLIDES:
            return None, f"A brief keeps at least {MIN_SLIDES} slides."
        gone = slides.pop(i - 1)
        return _renumber(spec), f"Removed slide {i}, \"{gone.get('title', '')}\"."
    if (m := re.search(r"\bswap\b.*?(\d+|one|two|three|four|five|six)\D+(\d+|one|two|three|four|five|six)", low)):
        a, b = _n(m.group(1)), _n(m.group(2))
        if not (a and b and 1 <= a <= len(slides) and 1 <= b <= len(slides)) or 1 in (a, b):
            return None, "Give two slide numbers after the cover, for example `swap slides 2 and 3`."
        slides[a - 1], slides[b - 1] = slides[b - 1], slides[a - 1]
        return _renumber(spec), f"Swapped slides {a} and {b}."
    if (m := re.search(r"\bmove\b.*?(?:slide|page)\s*(\d+|one|two|three|four|five|six)\b.*?\b(?:to|before|after|up|down)\b\s*(?:position\s*|slide\s*)?(\d+)?", low)):
        a = _n(m.group(1))
        word = re.search(r"\b(to|before|after|up|down)\b", low[m.start():]).group(1)
        if not a or not 2 <= a <= len(slides):
            return None, "Which slide moves? For example `move slide 4 to 2`."
        if word == "up":
            b = a - 1
        elif word == "down":
            b = a + 1
        elif not m.group(2):
            return None, "Where to? For example `move slide 4 to 2`."
        else:
            b = int(m.group(2)) + (1 if word == "after" else 0)
            b = min(b, len(slides))
        if b < 2 or b > len(slides):
            return None, "The cover stays first; a slide can move to positions 2 onwards."
        s = slides.pop(a - 1)
        slides.insert(b - 1, s)
        return _renumber(spec), f"Moved \"{s.get('title', '')}\" to position {b}."
    if re.search(r"\b(retitle|rename|title|call|headline)\b", low) and not re.search(r"\badd\b|\bnew slide\b", low):
        i = _find(spec, t)
        new = _quoted(t)
        if not i or not new:
            return None, "Say which slide and the new title in quotes, for example `retitle slide 2 \"Vacancy keeps falling\"`."
        slides[i - 1]["title"] = new
        return spec, f"Slide {i} is now titled \"{new}\"."
    if re.search(r"\b(so.?what|takeaway|subtitle|sub-title)\b", low):
        i = _find(spec, t)
        new = _quoted(t)
        if not i or not new:
            return None, "Say which slide and the text in quotes, for example `set the so-what of slide 2 to \"…\"`."
        slides[i - 1]["so_what"] = new
        return spec, f"Slide {i}'s so-what now reads \"{new}\"."
    if re.search(r"\bnotes?\b", low) and _find(spec, t) and _quoted(t):
        i = _find(spec, t)
        slides[i - 1]["notes"] = _quoted(t)
        return spec, f"Slide {i}'s speaker notes were replaced."
    if (m := re.search(r"\btheme\b\s*(?:to\s*)?(\w[\w ]*)|\b(forest|charcoal|navy|editorial|data white|cream|amber|gold)\b\s*theme", low)):
        want = (m.group(1) or m.group(2) or "").strip()
        theme = next((v for k, v in THEME_WORDS.items() if k in want), None)
        if not theme:
            return None, "Themes: navy-gold, forest-cream, charcoal-amber, editorial-cream, data-white."
        spec["theme"] = theme
        return spec, f"Theme changed to {theme}."
    if re.search(r"\b(add|insert|new slide|another slide|include)\b", low):
        if len(slides) >= MAX_SLIDES:
            return None, f"A brief holds at most {MAX_SLIDES} slides; remove one first."
        at = len(slides) - 1  # before the sources slide
        if slides[-1].get("layout") != "Sources":
            at = len(slides)
        if slides[at - 1].get("layout") == "Signal cards" and at > 1:
            at -= 1  # keep 'what changed' as the closing content slide
        if (m := re.search(r"\b(?:after|before)\s+(?:slide|page)\s*(\d+)", low)):
            at = min(max(int(m.group(1)) + (1 if "after" in m.group(0) else 0) - 1, 1), len(slides))
        quoted = _quoted(t) if re.search(r"\bstatement\b|\bsaying\b|[\"“']", t) else ""
        if quoted:
            s = {"key": f"statement_{at}", "layout": "Statement", "eyebrow": "", "title": quoted,
                 "notes": quoted, "why": "Added in the slide editor.", "fill": {}}
            slides.insert(at, s)
            return _renumber(spec), f"Added a statement slide at position {at + 1}: \"{quoted}\"."
        have = {s.get("key") for s in slides}
        pool = [c for c in (stories or []) if c.get("key") not in have]
        pick = next((c for c in pool if any(w and len(w) > 3 and w in low
                                            for w in [c["key"].lower().replace("_", " ")] + c["key"].lower().split("_")
                                            + (c.get("title") or "").lower().split())), None)
        if not pick and re.search(r"\b(on|about)\b", low):
            names = ", ".join(c["key"].replace("_", " ") for c in pool) or "none left"
            return None, f"Nothing in this week's stories matches that. Stories not yet in the deck: {names}."
        pick = pick or (pool[0] if pool else None)
        if not pick:
            return None, "Every story from this week's data is already in the deck."
        s = {"key": pick["key"], "layout": pick["layout"], "eyebrow": "", "title": pick["title"],
             "why": pick.get("reason", ""), "so_what": pick.get("so_what", ""), "notes": (pick.get("reason") or "") + ".",
             "fill": pick.get("fill") or {}}
        slides.insert(at, s)
        return _renumber(spec), f"Added \"{pick['title']}\" ({pick['layout']}) at position {at + 1}: {pick.get('reason', '')}."
    return None, HELP
