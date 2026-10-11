"""Editing a built deck by instruction when the Copilot is offline, and the checks that keep the Copilot's edits
honest: a few plain commands on the spec (remove, move, swap, retitle, add slides from this week's stories, change
the theme), in English or Chinese, applied by rules; and a description of what actually changed between two specs,
so the reply always matches the deck that was built."""
from __future__ import annotations

import copy
import re

THEME_WORDS = {"forest": "forest-cream", "green": "forest-cream", "charcoal": "charcoal-amber", "amber": "charcoal-amber",
               "dark": "charcoal-amber", "navy": "navy-gold", "gold": "navy-gold", "editorial": "editorial-cream",
               "cream": "editorial-cream", "white": "data-white", "data white": "data-white",
               "森林": "forest-cream", "綠": "forest-cream", "绿": "forest-cream", "炭": "charcoal-amber", "深色": "charcoal-amber",
               "黑": "charcoal-amber", "琥珀": "charcoal-amber", "海軍": "navy-gold", "海军": "navy-gold", "藍": "navy-gold",
               "蓝": "navy-gold", "金": "navy-gold", "米": "editorial-cream", "白": "data-white"}
# what a slide is about, in the words people use -> the story key the planner ranks
TOPIC_WORDS = {"capital": ("investment", "capital", "volume", "投資", "投资", "資本", "资本", "成交額", "成交额"),
               "rents": ("rent", "租金", "租"),
               "demand": ("demand", "requirement", "需求", "requirements"),
               "deals": ("deal", "letting", "成交", "交易", "租賃", "租赁"),
               "occupiers": ("vacancy", "occupier", "take-up", "take up", "空置", "去化", "承租"),
               "macro": ("bank rate", "rate", "macro", "interest", "利率", "宏觀", "宏观", "央行")}
MIN_SLIDES, MAX_SLIDES = 3, 12
HELP = ("I can change this deck by instruction without the Copilot: `remove slide 3`, `move slide 4 to 2`, "
        "`swap slides 2 and 3`, `retitle slide 2 \"Vacancy keeps falling\"`, `set the so-what of slide 2 to \"…\"`, "
        "`add a slide on rents` (or investment, demand, deals, Bank Rate: anything in this week's stories), "
        "`add two slides`, `add a statement slide \"…\"`, `theme forest`. Chinese works too: 刪第3頁、第4頁移到第2頁、"
        "第2頁標題改成「…」、多兩頁、加一頁講租金、換森林主題. Titles must not carry figures that are not in the data.")
HELP_ZH = ("沒有 Copilot 時我能照指令改這份簡報：「刪第 3 頁」「第 4 頁移到第 2 頁」「對調第 2 和第 3 頁」「第 2 頁標題改成「空置率持續下降」」"
           "「第 2 頁的 so-what 改成「…」」「加一頁講租金」（或投資、需求、成交、利率：本週故事裡有的題目）「多兩頁」"
           "「加一頁陳述「…」」「換森林主題」。標題不能寫資料裡沒有的數字。")
_ORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "last": -1, "a": 1, "an": 1, "another": 1,
        "一": 1, "兩": 2, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "最後": -1, "最后": -1}
_NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|first|second|third|fourth|fifth|sixth|last|[一兩两二三四五六七八九十]|最後|最后)"


def is_zh(text: str) -> bool:
    return bool(re.search(r"[㐀-鿿]", text))


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
    """A slide by number ('slide 3', 'the third slide', '第3頁', 'the last slide') or by what it is about."""
    slides = spec["slides"]
    m = (re.search(rf"\b(?:slide|page)\s*(?:number\s*)?{_NUM}\b", text, re.I)
         or re.search(rf"\b(first|second|third|fourth|fifth|sixth|last)\s+(?:slide|page)\b", text, re.I)
         or re.search(rf"第\s*{_NUM}\s*[頁页張张]", text)
         or re.search(r"(最後|最后)一?[頁页張张]", text))
    if m:
        n = _n(m.group(1))
        if n == -1:
            return len(slides)
        return n if n and 1 <= n <= len(slides) else None
    t = text.lower()
    for key, words in TOPIC_WORDS.items():
        if any(w in t for w in words):
            i = next((i for i, s in enumerate(slides, 1) if (s.get("key") or "") == key), None)
            if i:
                return i
    for i, s in enumerate(slides, 1):
        words = {(s.get("key") or "").lower().replace("_", " ")} | set((s.get("title") or "").lower().split())
        if any(w and len(w) > 3 and re.search(rf"\b{re.escape(w)}\b", t) for w in words):
            return i
    return None


def _quoted(text: str) -> str:
    m = re.search(r"[\"“”「『]([^\"“”」』]{2,})[\"“”」』]", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:改成|改為|改为|叫做|叫|為|为)\s*(.+)$", text.strip().rstrip("。."))
    if m and is_zh(text):
        return m.group(1).strip().strip("\"'「」")
    m = re.search(r"\b(?:to|as|:)\s+(.+)$", text.strip().rstrip("."), re.I)
    return m.group(1).strip().strip("\"'") if m else ""


def _topic(text: str) -> str | None:
    t = text.lower()
    return next((k for k, words in TOPIC_WORDS.items() if any(w in t for w in words)), None)


def asks_removal(text: str) -> bool:
    return bool(re.search(r"\b(remove|delete|drop|take out|cut|replace|swap out)\b", text, re.I)
                or re.search(r"刪|删|移除|去掉|拿掉|取代|換掉|换掉", text))


def _how_many(text: str) -> int:
    m = re.search(rf"\b{_NUM}\s+(?:more\s+|new\s+|extra\s+)?(?:slides?|pages?)\b", text, re.I) \
        or re.search(rf"(?:多|加|增加|新增|補|补)\s*{_NUM}\s*[頁页張张]", text)
    if m:
        n = _n(m.group(1))
        return n if n and n > 0 else 1
    return 1


def apply(instruction: str, spec: dict, stories: list[dict] | None = None) -> tuple[dict | None, str]:
    """(revised spec, what was done) or (None, why not / what I can do). Never changes `spec` in place.
    Replies follow the instruction's language."""
    spec = copy.deepcopy(spec)
    slides = spec["slides"]
    t = instruction.strip()
    low = t.lower()
    zh = is_zh(t)

    def T(en, cn):
        return cn if zh else en

    adding = bool(re.search(r"\b(add|insert|new slide|another slide|include|more slides?)\b", low)
                  or re.search(r"新增|加一|加入|多.{0,2}[頁页張张]|增加|補一|补一|再加", t))
    if not adding and (re.search(r"\b(remove|delete|drop|take out|cut)\b", low) or re.search(r"刪|删|移除|去掉|拿掉", t)):
        i = _find(spec, t)
        if not i:
            return None, T("Which slide? Say its number, for example `remove slide 3`.", "要刪哪一頁？請說頁碼，例如「刪第 3 頁」。")
        if i == 1:
            return None, T("The cover stays: it carries the headline and the KPIs.", "封面要留著：它載有標題與四個 KPI。")
        if len(slides) - 1 < MIN_SLIDES:
            return None, T(f"A brief keeps at least {MIN_SLIDES} slides.", f"簡報至少保留 {MIN_SLIDES} 頁。")
        gone = slides.pop(i - 1)
        return _renumber(spec), T(f"Removed slide {i}, \"{gone.get('title', '')}\".", f"已刪第 {i} 頁「{gone.get('title', '')}」。")
    if (m := re.search(rf"\bswap\b.*?{_NUM}\D+{_NUM}", low) or re.search(rf"(?:對調|对调|調換|调换|交換|交换|互換|互换).*?第?\s*{_NUM}\s*[頁页張张]?.*?第?\s*{_NUM}\s*[頁页張张]?", t)):
        a, b = _n(m.group(1)), _n(m.group(2))
        if not (a and b and 1 <= a <= len(slides) and 1 <= b <= len(slides)) or 1 in (a, b):
            return None, T("Give two slide numbers after the cover, for example `swap slides 2 and 3`.", "請給封面之後的兩個頁碼，例如「對調第 2 和第 3 頁」。")
        slides[a - 1], slides[b - 1] = slides[b - 1], slides[a - 1]
        return _renumber(spec), T(f"Swapped slides {a} and {b}.", f"已對調第 {a} 頁和第 {b} 頁。")
    mv = (re.search(rf"\bmove\b.*?(?:slide|page)\s*{_NUM}\b.*?\b(to|before|after|up|down)\b\s*(?:position\s*|slide\s*)?(\d+)?", low)
          or re.search(rf"第\s*{_NUM}\s*[頁页張张]\s*(?:移到|移至|搬到|放到|移動到|移动到|往)\s*(?:第\s*)?(\d+|[一兩两二三四五六七八九十])?\s*[頁页張张]?\s*(前|後|后|上|下)?", t))
    if mv:
        a = _n(mv.group(1))
        if zh:
            dest, word = mv.group(2), (mv.group(3) or "to")
            word = {"前": "before", "後": "after", "后": "after", "上": "up", "下": "down"}.get(word, "to")
        else:
            word, dest = mv.group(2), mv.group(3)
        if not a or not 2 <= a <= len(slides):
            return None, T("Which slide moves? For example `move slide 4 to 2`.", "要移哪一頁？例如「第 4 頁移到第 2 頁」。")
        if word == "up":
            b = a - 1
        elif word == "down":
            b = a + 1
        elif not dest:
            return None, T("Where to? For example `move slide 4 to 2`.", "移到哪裡？例如「第 4 頁移到第 2 頁」。")
        else:
            b = (_n(dest) or 0) + (1 if word == "after" else 0)
            b = min(b, len(slides))
        if b < 2 or b > len(slides):
            return None, T("The cover stays first; a slide can move to positions 2 onwards.", "封面固定在第 1 頁；其他頁可移到第 2 頁之後。")
        s = slides.pop(a - 1)
        slides.insert(b - 1, s)
        return _renumber(spec), T(f"Moved \"{s.get('title', '')}\" to position {b}.", f"已把「{s.get('title', '')}」移到第 {b} 頁。")
    if (re.search(r"\b(retitle|rename|title|call|headline)\b", low) or re.search(r"標題|标题|改名", t)) and not adding:
        i = _find(spec, t)
        new = _quoted(t)
        if not i or not new:
            return None, T("Say which slide and the new title in quotes, for example `retitle slide 2 \"Vacancy keeps falling\"`.",
                           "請說哪一頁和新標題（用引號），例如「第 2 頁標題改成「空置率持續下降」」。")
        slides[i - 1]["title"] = new
        return spec, T(f"Slide {i} is now titled \"{new}\".", f"第 {i} 頁的標題已改成「{new}」。")
    if re.search(r"\b(so.?what|takeaway|subtitle|sub-title)\b", low) or re.search(r"結論|结论|重點句|重点句|副標", t):
        i = _find(spec, t)
        new = _quoted(t)
        if not i or not new:
            return None, T("Say which slide and the text in quotes, for example `set the so-what of slide 2 to \"…\"`.",
                           "請說哪一頁和文字（用引號），例如「第 2 頁的 so-what 改成「…」」。")
        slides[i - 1]["so_what"] = new
        return spec, T(f"Slide {i}'s so-what now reads \"{new}\".", f"第 {i} 頁的 so-what 已改成「{new}」。")
    if (re.search(r"\bnotes?\b", low) or re.search(r"備註|备注|講稿|讲稿", t)) and _find(spec, t) and _quoted(t):
        i = _find(spec, t)
        slides[i - 1]["notes"] = _quoted(t)
        return spec, T(f"Slide {i}'s speaker notes were replaced.", f"第 {i} 頁的講者備註已換掉。")
    if (m := re.search(r"\btheme\b\s*(?:to\s*)?(\w[\w ]*)|\b(forest|charcoal|navy|editorial|data white|cream|amber|gold|dark|white)\b\s*theme", low)) \
            or re.search(r"主題|主题|配色|風格|风格", t):
        want = (m.group(1) or m.group(2) or "").strip() if m else t
        theme = next((v for k, v in THEME_WORDS.items() if k in want.lower()), None)
        if not theme:
            return None, T("Themes: navy-gold, forest-cream, charcoal-amber, editorial-cream, data-white.",
                           "可選主題：navy-gold（海軍藍金）、forest-cream（森林綠）、charcoal-amber（炭黑琥珀）、editorial-cream（米色）、data-white（白）。")
        spec["theme"] = theme
        return spec, T(f"Theme changed to {theme}.", f"主題已換成 {theme}。")
    if adding:
        want = _how_many(t)
        room = MAX_SLIDES - len(slides)
        if room <= 0:
            return None, T(f"A deck holds at most {MAX_SLIDES} slides; remove one first.", f"一份簡報最多 {MAX_SLIDES} 頁，請先刪一頁。")
        want = min(want, room)
        quoted = _quoted(t) if re.search(r"\bstatement\b|\bsaying\b|陳述|陈述|一句|[\"“「『]", t) else ""
        at = len(slides) - 1 if slides[-1].get("layout") == "Sources" else len(slides)  # before the sources slide
        if at > 1 and slides[at - 1].get("layout") == "Signal cards":
            at -= 1  # keep 'what changed' as the closing content slide
        if (m := re.search(r"\b(?:after|before)\s+(?:slide|page)\s*(\d+)", low) or re.search(r"第\s*(\d+)\s*[頁页張张]\s*(之?[前後后])", t)):
            after = "after" in m.group(0) or m.group(0).endswith(("後", "后"))
            at = min(max(int(m.group(1)) + (1 if after else 0) - 1, 1), len(slides))
        if quoted:
            s = {"key": f"statement_{at}", "layout": "Statement", "eyebrow": "", "title": quoted,
                 "notes": quoted, "why": "Added in the slide editor.", "fill": {}}
            slides.insert(at, s)
            return _renumber(spec), T(f"Added a statement slide at position {at + 1}: \"{quoted}\".", f"已在第 {at + 1} 頁加入陳述頁「{quoted}」。")
        have = {s.get("key") for s in slides}
        pool = [c for c in (stories or []) if c.get("key") not in have]
        topic = _topic(t)
        if topic and topic in have:
            return None, T(f"The deck already has a slide on that ({topic.replace('_', ' ')}).", "簡報裡已經有這個題目的一頁了。")
        if topic and not any(c["key"] == topic for c in pool):
            names = ", ".join(c["key"].replace("_", " ") for c in pool) or T("none left", "沒有了")
            return None, T(f"Nothing in this week's stories matches that. Stories not yet in the deck: {names}.",
                           f"本週的故事裡沒有這個題目。還沒放進簡報的故事：{names}。")
        if not pool:
            return None, T("Every story from this week's data is already in the deck.", "本週資料裡的故事都已經在簡報裡了。")
        picks = ([next(c for c in pool if c["key"] == topic)] if topic else []) + [c for c in pool if c["key"] != topic]
        added = []
        for c in picks[:want]:
            s = {"key": c["key"], "layout": c["layout"], "eyebrow": "", "title": c["title"], "why": c.get("reason", ""),
                 "so_what": c.get("so_what", ""), "notes": (c.get("reason") or "") + ".", "fill": c.get("fill") or {}}
            slides.insert(at + len(added), s)
            added.append(s)
        if len(added) < want:
            short = T(f" Only {len(added)} of the {want} asked for: this week's data has no more stories.",
                      f" 你要 {want} 頁，但本週資料只剩 {len(added)} 個故事可加。")
        else:
            short = ""
        lines = "; ".join(f"{at + i + 1}. \"{s['title']}\" ({s['layout']})" for i, s in enumerate(added))
        return _renumber(spec), T(f"Added {len(added)} slide{'s' if len(added) != 1 else ''}: {lines}.{short}",
                                  f"已新增 {len(added)} 頁：{lines}。{short}")
    return None, T(HELP, HELP_ZH)


def describe(old: dict, new: dict, instruction: str = "") -> str:
    """What changed between two specs, in the instruction's language, so the reply states what the built deck
    actually has rather than what a model says it did."""
    zh = is_zh(instruction)
    ot = [s.get("title", "") for s in old.get("slides", [])]
    nt = [s.get("title", "") for s in new.get("slides", [])]
    added = [s for s in new["slides"] if s.get("title", "") not in ot]
    removed = [t for t in ot if t not in nt]
    kept_order = [t for t in nt if t in ot]
    reordered = kept_order != [t for t in ot if t in nt]
    parts = []
    if added:
        items = "; ".join(f"{nt.index(s.get('title', '')) + 1}. \"{s.get('title', '')}\"" + (f" — {s['why']}" if s.get("why") else "") for s in added)
        parts.append((f"新增 {len(added)} 頁：{items}" if zh else f"Added {len(added)} slide{'s' if len(added) != 1 else ''}: {items}"))
    if removed:
        items = "; ".join(f"\"{t}\"" for t in removed)
        parts.append((f"刪除 {len(removed)} 頁：{items}" if zh else f"Removed {len(removed)} slide{'s' if len(removed) != 1 else ''}: {items}"))
    if reordered:
        parts.append("順序有調整" if zh else "The order changed")
    if old.get("theme") != new.get("theme"):
        parts.append((f"主題改為 {new.get('theme')}" if zh else f"Theme is now {new.get('theme')}"))
    if not parts:
        changed = [(i + 1) for i, (a, b) in enumerate(zip(old["slides"], new["slides"]))
                   if a != b and a.get("title") == b.get("title")]
        if changed:
            parts.append((f"第 {', '.join(map(str, changed))} 頁的內容已更新" if zh else
                          f"Slide{'s' if len(changed) > 1 else ''} {', '.join(map(str, changed))} updated"))
        else:
            parts.append("沒有變動" if zh else "Nothing changed")
    tail = f"現在共 {len(nt)} 頁。" if zh else f"The deck now has {len(nt)} slides."
    return ("。".join(parts) + "。" if zh else ". ".join(parts) + ".") + " " + tail
