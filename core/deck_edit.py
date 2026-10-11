"""Editing a built deck by instruction when the Copilot is offline, and the checks that keep the Copilot's edits
honest. `apply` understands plain commands in English or Chinese (remove, move, swap, retitle, so-what, add
slides from this week's stories, shorten to N slides, change the theme, chart range and type, undo, export) and
batches of them; what it cannot do it says, in the instruction's language, instead of doing something else.
`describe` states what changed between two specs by slide id, so a reply always matches the deck that was built."""
from __future__ import annotations

import copy
import re

THEME_WORDS = {"forest": "forest-cream", "green": "forest-cream", "charcoal": "charcoal-amber", "amber": "charcoal-amber",
               "dark": "charcoal-amber", "navy": "navy-gold", "gold": "navy-gold", "editorial": "editorial-cream",
               "cream": "editorial-cream", "white": "data-white", "data white": "data-white",
               "森林": "forest-cream", "綠": "forest-cream", "绿": "forest-cream", "炭": "charcoal-amber", "深色": "charcoal-amber",
               "黑": "charcoal-amber", "琥珀": "charcoal-amber", "海軍": "navy-gold", "海军": "navy-gold", "深藍": "navy-gold",
               "深蓝": "navy-gold", "藍": "navy-gold", "蓝": "navy-gold", "金": "navy-gold", "米": "editorial-cream", "白": "data-white"}
# who the deck is for -> the house theme made for them (themes.json use_for)
AUDIENCE_THEMES = {"client": "forest-cream", "customer": "forest-cream", "客戶": "forest-cream", "客户": "forest-cream",
                   "investment committee": "data-white", "ic pack": "data-white", "for the ic": "data-white", "投委會": "data-white",
                   "投委会": "data-white", "投資委員會": "data-white", "投资委员会": "data-white", "research": "editorial-cream",
                   "研究報告": "editorial-cream", "研究报告": "editorial-cream", "on screen": "charcoal-amber", "screen": "charcoal-amber",
                   "投影": "charcoal-amber", "board": "navy-gold", "董事會": "navy-gold", "董事会": "navy-gold"}
# what a slide is about, in the words people use -> the story key the planner ranks
TOPIC_WORDS = {"capital": ("investment", "capital", "volume", "投資", "投资", "資本", "资本", "成交額", "成交额"),
               "rents": ("rent", "租金", "租"),
               "demand": ("demand", "requirement", "需求", "requirements"),
               "deals": ("deal", "letting", "成交", "交易", "租賃", "租赁"),
               "occupiers": ("vacancy", "occupier", "take-up", "take up", "空置", "去化", "承租"),
               "macro": ("bank rate", "interest rate", "macro", "interest", "利率", "宏觀", "宏观", "央行")}
CHART_WORDS = {"rents": ("rent", "租金"), "vacancy": ("vacancy", "空置"), "take_up": ("take-up", "take up", "去化"),
               "investment": ("investment", "投資", "投资")}
SUBMARKETS = ['West End', 'City & Southbank', 'Docklands & Stratford', 'West End Core', 'Soho', 'Marylebone', 'Fitzrovia', 'Midtown',
              'Bloomsbury', "King's Cross/Euston", "King's Cross", 'Euston', 'Paddington', 'Victoria', 'Strand/Covent Garden', 'Covent Garden',
              'Knightsbridge/Chelsea', 'Knightsbridge', 'Chelsea', 'White City', 'City Core', 'Clerkenwell/Farringdon', 'Clerkenwell',
              'Farringdon', 'Aldgate/Whitechapel', 'Aldgate', 'Southbank Core', 'Southbank', 'Vauxhall/Battersea', 'Vauxhall', 'Battersea',
              'Canary Wharf', 'Rest of Docklands', 'Stratford', 'Docklands']
MIN_SLIDES, MAX_SLIDES = 3, 12
HELP = ("I can change this deck by instruction without the Copilot: `remove slide 3`, `move slide 4 to 2`, "
        "`swap slides 2 and 3`, `retitle slide 2 \"Vacancy keeps falling\"`, `set the so-what of slide 2 to \"…\"`, "
        "`add a slide on rents` (or investment, demand, deals, Bank Rate: anything in this week's stories), "
        "`add two slides`, `add a statement slide \"…\"`, `shorten to 4 slides`, `theme forest`, `last 4 quarters on slide 2`, "
        "`undo`. Several at once: `remove slide 3, then theme forest`. Chinese works too. Titles must not carry figures "
        "that are not in the data.")
HELP_ZH = ("沒有 Copilot 時我能照指令改這份簡報：「刪第 3 頁」「第 4 頁移到第 2 頁」「對調第 2 和第 3 頁」「第 2 頁標題改成「空置率持續下降」」"
           "「第 2 頁的 so-what 改成「…」」「加一頁講租金」（或投資、需求、成交、利率：本週故事裡有的題目）「多兩頁」"
           "「加一頁陳述「…」」「精簡成 4 頁」「換森林主題」「第 2 頁只顯示最近四季」「撤銷」。可以一次多句：「刪第 3 頁，然後換森林主題」。"
           "標題不能寫資料裡沒有的數字。")
_ORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "last": -1, "a": 1, "an": 1, "another": 1,
        "一": 1, "兩": 2, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "最後": -1, "最后": -1}
_NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|first|second|third|fourth|fifth|sixth|last|[一兩两二三四五六七八九十]|最後|最后)"
_SPLIT = re.compile(r"\s*(?:，然後|，再|、再|然後|接著|接着|；|;|, then |, and then | and then | then |，並且|，并且|，也)\s*")
_THIS = re.compile(r"\b(this|the current|the selected) (slide|page|one)\b|這一?頁|这一?页|本頁|本页|此頁|此页|目前這頁|當前頁|当前页", re.I)


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


def _pages(text: str, total: int, sel: int | None = None) -> list[int]:
    """Every slide number named: 'slides 2 and 3', '第2和第3頁', '2、3、5 頁', 'the last slide', 'this slide'."""
    out = []
    if _THIS.search(text) and sel:
        out.append(sel)
    if re.search(r"\b(the )?last (slide|page)\b|最後一?[頁页張张]|最后一?[頁页張张]", text, re.I):
        out.append(total)
    for m in re.finditer(rf"(slides?|pages?)\s*(?:number\s*)?((?:{_NUM}\s*(?:,|and|&|、|和|與|与|及|to|-|–|~)?\s*)+)", text, re.I):
        chunk = m.group(2)
        plural = m.group(1).lower().endswith("s")
        r = re.findall(r"\d+", chunk)
        ranged = (re.search(r"[-–~]", chunk) or (plural and re.search(r"\bto\b", chunk))) and len(r) == 2 and int(r[0]) < int(r[1])
        if ranged:
            out.extend(range(int(r[0]), int(r[1]) + 1))
        else:
            out.extend(n for tok in re.findall(_NUM, chunk, re.I) if (n := _n(tok)))
    for m in re.finditer(rf"((?:第?\s*{_NUM}\s*[頁页張张]?\s*(?:、|和|與|与|及|跟|還有|还有|,|，|到|至|~)?\s*)+)[頁页張张]", text):
        chunk = m.group(0)
        if "第" not in chunk and not re.search(r"[、和與与及跟，,到至~]", chunk):
            continue
        toks = [n for tok in re.findall(_NUM, chunk) if (n := _n(tok))]
        if re.search(r"到|至|~", chunk) and len(toks) == 2:
            out.extend(range(toks[0], toks[1] + 1))
        else:
            out.extend(toks)
    for m in re.finditer(rf"(first|second|third|fourth|fifth|sixth)\s+(?:slide|page)", text, re.I):
        out.append(_n(m.group(1)))
    out = [total if n == -1 else n for n in out]
    return list(dict.fromkeys(n for n in out if n and 1 <= n <= total))


def _find(spec: dict, text: str, sel: int | None = None) -> int | None:
    """One slide: by number, 'this slide', the last slide, or by what it is about ('the rents slide')."""
    slides = spec["slides"]
    pages = _pages(text, len(slides), sel)
    if pages:
        return pages[0]
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


def _quotes(text: str) -> list[str]:
    return [q.strip() for q in re.findall(r"[\"“”「『]([^\"“”」』]{1,})[\"“”」』]", text)]


def _quoted(text: str) -> str:
    q = _quotes(text)
    if q:
        return q[0]
    m = re.search(r"(?:改成|改為|改为|叫做|叫|寫成|写成|換成|换成)\s*(.+)$", text.strip().rstrip("。."))
    if m and is_zh(text):
        return m.group(1).strip().strip("\"'「」")
    m = re.search(r"\b(?:to|as|:)\s+(.+)$", text.strip().rstrip("."), re.I)
    return m.group(1).strip().strip("\"'") if m else ""


def _topic(text: str) -> str | None:
    t = text.lower()
    return next((k for k, words in TOPIC_WORDS.items() if any(w in t for w in words)), None)


def _markets(low: str) -> list[str]:
    """Submarkets named in the text, longest names first so 'West End Core' does not also count as 'West End'."""
    found = [m for m in sorted(SUBMARKETS, key=len, reverse=True) if m.lower() in low]
    rest = low
    out = []
    for m in found:
        if m.lower() in rest:
            out.append(m)
            rest = rest.replace(m.lower(), " ")
    return out


def _submarket(text: str) -> str | None:
    t = text.lower()
    return next((m for m in sorted(SUBMARKETS, key=len, reverse=True) if m.lower() in t), None)


def asks_removal(text: str) -> bool:
    """Whether an instruction gives leave to drop slides: remove, replace, or make the deck shorter."""
    return bool(re.search(r"\b(remove|delete|drop|take out|cut|replace|swap out|shorter|shorten|trim|merge|condense|fewer|"
                          r"cut down|minutes?)\b", text, re.I)
                or re.search(r"刪|删|移除|去掉|拿掉|取代|換掉|换掉|精簡|精简|縮短|缩短|合併|合并|濃縮|浓缩|只要|分鐘|分钟|減少|减少", text)
                or re.search(rf"(?:成|到|留)\s*{_NUM}\s*[頁页張张]|to {_NUM} slides", text))


def _how_many(text: str, default: int = 1) -> int:
    m = re.search(rf"\b{_NUM}\s+(?:more\s+|new\s+|extra\s+)?(?:slides?|pages?)\b", text, re.I) \
        or re.search(rf"(?:多|加|增加|新增|補|补|留|成|到|要)\s*{_NUM}\s*[頁页張张]", text)
    if m:
        n = _n(m.group(1))
        return n if n and n > 0 else default
    return default


def _theme_for(text: str) -> str | None:
    low = text.lower()
    for k, v in AUDIENCE_THEMES.items():
        if k in low:
            return v
    for k, v in sorted(THEME_WORDS.items(), key=lambda kv: -len(kv[0])):
        if k in low:
            return v
    return None


def apply(instruction: str, spec: dict, stories: list[dict] | None = None, sel: int | None = None) -> tuple[dict | None, str]:
    """(revised spec, what was done) or (None, why not / a question / an answer). Several instructions in one
    sentence are applied in turn and reported one by one. Special results: {"undo": n|"first"} to go back a
    version, {"switch": "ic"|"board"} to rebuild in another format. Never changes `spec` in place."""
    parts = [p for p in _SPLIT.split(instruction.strip()) if p.strip()]
    if len(parts) <= 1:
        return _apply_one(instruction, spec, stories, sel)
    cur, lines, changed = spec, [], False
    zh = is_zh(instruction)
    for p in parts:
        new, said = _apply_one(p, cur, stories, sel)
        if isinstance(new, dict) and ("undo" in new or "switch" in new):
            return new, said
        if new:
            cur, changed = new, True
            lines.append(("✓ " if not zh else "✓ ") + said)
        else:
            lines.append(("✗ " if not zh else "✗ ") + (f"\"{p}\": " if len(parts) > 1 else "") + said)
    return (cur if changed else None), "\n".join(lines)


def _apply_one(instruction: str, spec: dict, stories: list[dict] | None, sel: int | None) -> tuple[dict | None, str]:
    spec = copy.deepcopy(spec)
    slides = spec["slides"]
    total = len(slides)
    t = instruction.strip()
    low = t.lower()
    zh = is_zh(t)

    def T(en, cn):
        return cn if zh else en

    def title(i):
        return slides[i - 1].get("title", "")

    def is_sources(i):
        return slides[i - 1].get("layout") == "Sources"

    def locked(i):
        if i == 1:
            return T("The cover stays first: it carries the headline and the KPIs.", "封面固定在第 1 頁：它載有標題與四個 KPI。")
        if is_sources(i):
            alt = total - 1
            return T(f"The Sources slide stays last (every figure's [n] points to it). To shorten the deck, remove slide {alt} "
                     f"(\"{title(alt)}\") instead.", f"Sources 頁固定在最後一頁（每個數字的 [n] 都指向它）。要縮短簡報，請改刪第 {alt} 頁「{title(alt)}」。")
        return ""

    pages = _pages(t, total, sel)
    # --- undo / versions ------------------------------------------------------------------------------
    if (m := re.search(r"\b(?:restore|go back to|back to)\s+(?:version|v)\s*(\d+)\b", low) or re.search(r"回到第\s*(\d+)\s*版", t)):
        return {"undo": ("version", int(m.group(1)))}, T(f"Going back to version {m.group(1)}.", f"回到第 {m.group(1)} 版。")
    if re.search(r"\b(undo|revert|go back|roll ?back|previous version|last version)\b", low) or re.search(r"撤銷|撤销|復原|复原|還原|还原|回到上一|回上一步|退回", t):
        first = bool(re.search(r"\b(first|original|initial)\b", low) or re.search(r"初版|最初|第一版|原版", t))
        return {"undo": "first" if first else 1}, T("Going back " + ("to the first version." if first else "one step."),
                                                      "回到" + ("初版。" if first else "上一版。"))
    if re.search(r"回到初版|回到原版|回到最初", t) or re.search(r"\b(back to|restore) the (first|original) (version|deck)\b", low):
        return {"undo": "first"}, T("Going back to the first version.", "回到初版。")
    # --- export / format -----------------------------------------------------------------------------
    if re.search(r"\b(export|download|save)\b.*\b(pdf|pptx|powerpoint)\b|\bas (a )?pdf\b", low) or re.search(r"(匯出|导出|下載|下载|給我|给我).*(pdf|pptx|ppt|檔|档)", t):
        return None, T("Download .pptx and PDF are the two buttons at the top of this window; both carry the deck as it is now.",
                       "視窗頂端的 Download .pptx 和 PDF 兩個按鈕就是匯出，內容是目前這一版。")
    if re.search(r"4\s*[:：]\s*3|\bsquare\b|直式|portrait", low):
        return None, T("Only 16:9 is available: the five house templates are widescreen.", "只有 16:9：五個房屋主題模板都是寬螢幕。")
    if re.search(r"\b(ic|investment committee) (version|pack|format)\b|\bmake (it |an? )?ic\b|\bfor the ic\b", low) or re.search(r"(投委會|投委会|IC)\s*版|做一個\s*IC|做成\s*IC", t):
        return {"switch": "ic"}, T("Switching to the IC pack (data-white) and building it from the same data.", "改成投委會版（data-white），用同一份資料建置。")
    if re.search(r"\bboard (version|pack|format)\b", low) or re.search(r"(董事會|董事会|board)\s*版", t):
        return {"switch": "board"}, T("Switching to the board pack and building it from the same data.", "改成董事會版，用同一份資料建置。")
    # --- questions about the deck ----------------------------------------------------------------------
    if re.search(r"\b(where|which).*(from|source|come)\b|\bsource of\b", low) or re.search(r"從哪|从哪|來源|来源|出處|出处|哪裡來|哪里来", t):
        i = _find(spec, t, sel) or sel
        if i:
            s = slides[i - 1]
            src = ((s.get("fill") or {}).get("source") or "").strip()
            refs = sorted(set(re.findall(r"\[\d+\]", " ".join(str(v) for v in [s.get("title"), s.get("notes"), src, s.get("so_what")]))))
            return None, T(f"Slide {i} draws on {src or 'the library figures'}{' (' + ', '.join(refs) + ')' if refs else ''}. "
                           "Every [n] is listed on the Sources slide with the report and its link; nothing on the slide was typed by hand.",
                           f"第 {i} 頁的數字來自 {src or '資料庫的數據'}{'（' + '、'.join(refs) + '）' if refs else ''}。"
                           "每個 [n] 都列在 Sources 頁，對應報告與連結；頁面上沒有手打的數字。")
        return None, T("Every figure carries [n]; the Sources slide lists each report and its link. Which slide do you mean?",
                       "每個數字都帶 [n]，Sources 頁列出每份報告與連結。你問的是哪一頁？")
    # --- vague: ask what to change rather than guess ----------------------------------------------------
    if re.search(r"\b(make it better|improve|is wrong|not right|looks? (bad|off|wrong)|fix (it|this))\b", low) or re.search(r"不對|不对|改好|弄好|做得更好|更好一點|更好一点|有問題|有问题|怪怪", t):
        i = _find(spec, t, sel) or sel
        if i:
            return None, T(f"What should change on slide {i} (\"{title(i)}\"): the title, the so-what, the chart, or should it go?",
                           f"第 {i} 頁「{title(i)}」要改哪裡：標題、結論（so-what）、圖表，還是刪掉？")
        return None, T("Which slide, and what should change: a title, a so-what, a chart, the order or the theme?",
                       "哪一頁、改什麼：標題、結論、圖表、順序還是主題？")
    adding = bool(re.search(r"\b(add|insert|new slide|another slide|include|more slides?|extra slides?)\b", low)
                  or re.search(r"新增|加一|加入|多.{0,2}[頁页張张]|增加|補一|补一|再加|加[一兩两二三四五]?[頁页張张]", t))
    # --- shorten to N -----------------------------------------------------------------------------------
    if (re.search(r"\b(shorten|shorter|condense|trim|cut (it )?down|fewer slides|minutes?)\b", low) and not re.search(r"\btitle\b|標題", low)) \
            or re.search(r"精簡|精简|濃縮|浓缩|縮短|缩短|減到|减到|只要\s*\d|只留", t) and not re.search(r"標題|标题", t):
        keep = _how_many(t, 0)
        want = keep if keep >= MIN_SLIDES else max(MIN_SLIDES, total - 2)
        if want >= total:
            return None, T(f"The deck already has {total} slides.", f"簡報已經是 {total} 頁了。")
        score = {c["key"]: c.get("score", 0) for c in (stories or [])}
        fixed = {"Cover", "Sources", "Signal cards"}
        cands = sorted((i for i in range(1, total + 1) if slides[i - 1].get("layout") not in fixed),
                       key=lambda i: score.get(slides[i - 1].get("key"), 0))
        gone = sorted(cands[:total - want], reverse=True)
        if not gone:
            return None, T("Only the cover, the signal cards and the sources are left; nothing more to cut.", "只剩封面、訊號卡和來源頁，沒有可刪的了。")
        names = "; ".join(f"\"{title(i)}\"" for i in gone)
        for i in gone:
            slides.pop(i - 1)
        return _renumber(spec), T(f"Cut to {len(slides)} slides: removed {names} (the weakest stories this week).",
                                  f"精簡到 {len(slides)} 頁：刪了 {names}（本週分數最低的故事）。")
    # --- remove ------------------------------------------------------------------------------------------
    if not adding and (re.search(r"\b(remove|delete|drop|take out|cut)\b", low) or re.search(r"刪|删|移除|去掉|拿掉", t)):
        if not pages:
            i = _find(spec, t, sel)
            pages = [i] if i else []
        if not pages:
            if (tp := _topic(t)):
                return None, T(f"There is no slide on {tp.replace('_', ' ')} in this deck, so nothing was removed.",
                               f"簡報裡沒有講 {tp.replace('_', ' ')} 的頁，所以沒有刪。")
            return None, T("Which slide? Say its number, for example `remove slide 3`.", "要刪哪一頁？請說頁碼，例如「刪第 3 頁」。")
        for i in pages:
            if (why := locked(i)):
                return None, why
        if total - len(pages) < MIN_SLIDES:
            return None, T(f"A brief keeps at least {MIN_SLIDES} slides.", f"簡報至少保留 {MIN_SLIDES} 頁。")
        names = "; ".join(f"{i} \"{title(i)}\"" for i in pages)
        names_zh = "和".join(f"第 {i} 頁「{title(i)}」" for i in pages)
        for i in sorted(pages, reverse=True):
            slides.pop(i - 1)
        return _renumber(spec), T(f"Removed slide{'s' if len(pages) > 1 else ''} {names}.", f"已刪{names_zh}。")
    # --- swap ---------------------------------------------------------------------------------------------
    if re.search(r"\bswap\b|\bexchange\b|\bswitch (the )?(places|positions)\b", low) or re.search(r"對調|对调|調換|调换|交換|交换|互換|互换|換位置|换位置|換個位置|换个位置", t):
        if len(pages) != 2 or 1 in pages:
            return None, T("Give two slide numbers after the cover, for example `swap slides 2 and 3`.", "請給封面之後的兩個頁碼，例如「對調第 2 和第 3 頁」。")
        a, b = pages
        if is_sources(a) or is_sources(b):
            return None, locked(a if is_sources(a) else b)
        slides[a - 1], slides[b - 1] = slides[b - 1], slides[a - 1]
        return _renumber(spec), T(f"Swapped slides {a} and {b}.", f"已對調第 {a} 頁和第 {b} 頁。")
    # --- move ---------------------------------------------------------------------------------------------
    if re.search(r"\bmove\b|\bput\b.*\b(first|front|end|last|before|after)\b", low) or re.search(r"移到|移至|搬到|放到|移動到|移动到|往前|往後|往后|放最前|放最後|放最后|提到", t):
        a = pages[0] if pages else (_find(spec, t, sel) or sel)
        if not a or not 2 <= a <= total:
            return None, T("Which slide moves? For example `move slide 4 to 2`.", "要移哪一頁？例如「第 4 頁移到第 2 頁」。")
        if is_sources(a):
            return None, locked(a)
        last_content = total - 1 if is_sources(total) else total
        if re.search(r"\b(front|first|top|beginning)\b", low) or re.search(r"最前|開頭|开头|第一", t):
            b = 2
        elif re.search(r"\b(end|last|back|bottom)\b", low) or re.search(r"最後|最后|末尾|結尾|结尾", t):
            b = last_content
        elif re.search(r"\bup\b", low) or re.search(r"往前|往上|提前", t):
            b = a - 1
        elif re.search(r"\bdown\b", low) or re.search(r"往後|往后|往下", t):
            b = a + 1
        elif len(pages) >= 2:
            b = pages[1] + (1 if re.search(r"\bafter\b|之後|之后|後面|后面", low) else 0)
        else:
            return None, T("Where to? For example `move slide 4 to 2`.", "移到哪裡？例如「第 4 頁移到第 2 頁」。")
        b = min(max(b, 2), last_content)
        s = slides.pop(a - 1)
        slides.insert(b - 1, s)
        return _renumber(spec), T(f"Moved \"{s.get('title', '')}\" to position {b}.", f"已把「{s.get('title', '')}」移到第 {b} 頁。")
    # --- retitle (several at once allowed) ------------------------------------------------------------------
    quotes = _quotes(t)
    pair_re = rf"(?:slides?|pages?|第)\s*{_NUM}\s*[頁页張张]?\D{{0,40}}?[\"“「『]([^\"”」』]+)[\"”」』]"
    title_words = re.search(r"\b(retitle|rename|title|headline|call)\b", low) or re.search(r"標題|标题|改名|題目|题目", t)
    other_words = re.search(r"\b(so.?what|takeaway|subtitle|sub-title|conclusion|notes?)\b", low) or re.search(r"結論|结论|重點句|重点句|副標|副标|備註|备注|講稿|讲稿|陳述|陈述", t)
    if (title_words or (quotes and not other_words and len(re.findall(pair_re, t, re.I)) >= 1)) and not adding:
        if re.search(r"\b(shorter|shorten|short|punchier|simpler|snappier|concise)\b", low) or re.search(r"短|精簡|精简|簡短|简短|簡潔|简洁", t) and not quotes:
            i = _find(spec, t, sel) or sel
            return None, T(f"Shortening a title needs the Copilot (it rewrites the wording and keeps the figures). "
                           f"Offline, give the new title yourself: `retitle slide {i or 2} \"…\"`.",
                           f"改短標題要由 Copilot 重寫（保留數字）。離線時請直接給新標題：「第 {i or 2} 頁標題改成「…」」。")
        pairs = [(_n(m.group(1)), m.group(2).strip()) for m in re.finditer(pair_re, t, re.I)]
        pairs = [(i, q) for i, q in pairs if i and 1 <= i <= total] or ([(_find(spec, t, sel), quotes[0])] if quotes else [])
        if not pairs or not all(i and q for i, q in pairs):
            new = _quoted(t)
            i = _find(spec, t, sel)
            if i and new:
                pairs = [(i, new)]
            else:
                return None, T("Say which slide and the new title in quotes, for example `retitle slide 2 \"Vacancy keeps falling\"`.",
                               "請說哪一頁和新標題（用引號），例如「第 2 頁標題改成「空置率持續下降」」。")
        for i, q in pairs:
            slides[i - 1]["title"] = q
        return spec, T("; ".join(f"Slide {i} is now titled \"{q}\"" for i, q in pairs) + ".",
                       "；".join(f"第 {i} 頁的標題已改成「{q}」" for i, q in pairs) + "。")
    # --- so-what / notes --------------------------------------------------------------------------------------
    if re.search(r"\b(so.?what|takeaway|subtitle|sub-title|conclusion)\b", low) or re.search(r"結論|结论|重點句|重点句|副標|副标|so-what", t):
        i = _find(spec, t, sel) or sel
        new = _quoted(t)
        if not i or not new:
            return None, T("Say which slide and the text in quotes, for example `set the so-what of slide 2 to \"…\"`.",
                           "請說哪一頁和文字（用引號），例如「第 2 頁的 so-what 改成「…」」。")
        slides[i - 1]["so_what"] = new
        return spec, T(f"Slide {i}'s so-what now reads \"{new}\".", f"第 {i} 頁的 so-what 已改成「{new}」。")
    if (re.search(r"\bnotes?\b", low) or re.search(r"備註|备注|講稿|讲稿", t)) and (_find(spec, t, sel) or sel) and _quoted(t):
        i = _find(spec, t, sel) or sel
        slides[i - 1]["notes"] = _quoted(t)
        return spec, T(f"Slide {i}'s speaker notes were replaced.", f"第 {i} 頁的講者備註已換掉。")
    # --- charts: replace, range, type -----------------------------------------------------------------------------
    chart_slide = _pages(t, total, sel)[0] if _pages(t, total, sel) else None
    if not chart_slide:
        ck = next((key for key, words in CHART_WORDS.items() if any(w in low for w in words)), None)
        chart_slide = next((i for i, s in enumerate(slides, 1) if ck and any(isinstance(v, dict) and v.get("chart") == ck for v in (s.get("fill") or {}).values())), None)
    chart_slide = chart_slide or _find(spec, t, sel) or sel
    chart_ish = (re.search(r"\b(chart|graph)\b|圖表|图表|圖|图", low)
                 or re.search(rf"(?:last|latest|past|recent)\s+{_NUM}\s*(?:quarters?|periods?|years?)|最近\s*{_NUM}\s*[季年期]|近\s*{_NUM}\s*[季年期]", low)
                 or re.search(r"\b(line|bar|column)\b|折線|折线|長條|长条|柱狀|柱状|橫條|横条", low)
                 or (re.search(r"\bonly\b|只看|只顯示|只显示|只留", low) and any(m.lower() in low for m in SUBMARKETS)))
    if chart_ish and chart_slide and not adding:
        s = slides[chart_slide - 1]
        fills = [(k, v) for k, v in (s.get("fill") or {}).items() if isinstance(v, dict) and "chart" in v]
        if not fills:
            return None, T(f"Slide {chart_slide} has no chart to change (layout {s.get('layout')}).", f"第 {chart_slide} 頁沒有圖表可改（版面 {s.get('layout')}）。")
        done = []
        if (m := re.search(rf"(?:last|latest|past|recent)\s+{_NUM}\s*(?:quarters?|periods?|years?)|最近\s*{_NUM}\s*[季年期]|近\s*{_NUM}\s*[季年期]", low)):
            n = _n(m.group(1) or m.group(2) or m.group(3) or "")
            n = n * 4 if n and re.search(r"years?|年", m.group(0)) else n
            if n and 2 <= n <= 20:
                for k, v in fills:
                    v["last"] = n
                done.append(T(f"last {n} periods", f"最近 {n} 期"))
        if (want := _markets(low)):
            for k, v in fills:
                v["markets"] = want
            done.append(T(f"only {', '.join(want)}", f"只看 {'、'.join(want)}"))
        if (m := re.search(r"\b(line|bar|column)\b|折線|折线|長條|长条|柱狀|柱状|橫條|横条", low)):
            kind = {"折線": "line", "折线": "line", "長條": "bar", "长条": "bar", "橫條": "bar", "横条": "bar", "柱狀": "column", "柱状": "column"}.get(m.group(0), m.group(0))
            for k, v in fills:
                v["type"] = kind
            done.append(T(f"{kind} chart", {"line": "折線圖", "bar": "橫條圖", "column": "柱狀圖"}[kind]))
        new_key = next((key for key, words in CHART_WORDS.items() if any(w in low for w in words)), None)
        if new_key and (re.search(r"\b(replace|swap|change|use|show|switch)\b", low) or re.search(r"換成|换成|改成|改用|換|换", t)) and not done:
            k, v = fills[0]
            v["chart"] = new_key
            label = {"rents": "PRIME RENT, £/SQ FT", "vacancy": "CENTRAL LONDON VACANCY RATE", "take_up": "TAKE-UP, M SQ FT", "investment": "INVESTMENT, £BN"}[new_key]
            lk = k.replace("chart", "label") if "chart" in k else "chart_label"
            if lk in (s.get("fill") or {}) or k == "chart":
                s["fill"][lk if lk in s["fill"] else "chart_label"] = label
            done.append(T(f"the {new_key.replace('_', '-')} chart", f"{new_key} 圖表"))
        if done:
            return spec, T(f"Slide {chart_slide}'s chart now shows {', '.join(done)}. The title still describes the earlier chart; retitle it if needed.",
                           f"第 {chart_slide} 頁的圖表已改為{'、'.join(done)}。標題仍是原來的，需要的話請改標題。")
        return None, T("For a chart I can change its range (`last 4 quarters`), its markets (`only West End Core and City Core`), "
                       "its type (`as a line chart`) or swap it for the rents, vacancy, take-up or investment chart.",
                       "圖表可以改範圍（「最近四季」）、分區（「只看 West End Core 和 City Core」）、類型（「改成折線圖」），或換成租金／空置率／去化／投資圖。")
    # --- theme --------------------------------------------------------------------------------------------------
    theme = _theme_for(t)
    if theme and (re.search(r"\b(theme|style|colou?r|palette|look|suitable|for (a|the|our))\b", low) or re.search(r"主題|主题|配色|風格|风格|顏色|颜色|換成|换成|改成|適合|适合|給|给", t)):
        if theme == spec.get("theme"):
            return None, T(f"The deck is already on {theme}.", f"簡報已經是 {theme} 主題了。")
        spec["theme"] = theme
        return spec, T(f"Theme changed to {theme}.", f"主題已換成 {theme}。")
    if re.search(r"\btheme\b", low) or re.search(r"主題|主题|配色", t):
        return None, T("Themes: navy-gold (board), forest-cream (clients), charcoal-amber (on screen), editorial-cream (research), data-white (IC).",
                       "可選主題：navy-gold（董事會）、forest-cream（客戶）、charcoal-amber（投影）、editorial-cream（研究報告）、data-white（投委會）。")
    # --- add ---------------------------------------------------------------------------------------------------
    if adding:
        topic = _topic(t)
        sub = _submarket(t)
        quoted = _quoted(t) if re.search(r"\bstatement\b|\bsaying\b|陳述|陈述|一句|[\"“「『]", t) else ""
        if not quoted and (m := re.search(r"\b(?:saying|stating|that says|that reads|reading)\s+(.+)$", t, re.I)
                           or re.search(r"(?:陳述|陈述|寫著|写着|寫上|写上|說)\s*[:：]?\s*(.+)$", t)):
            quoted = m.group(1).strip().strip("。.")
        counted = bool(re.search(rf"\b{_NUM}\s+(?:more\s+|new\s+|extra\s+)?(?:slides?|pages?)\b|\b(?:a|another|one more|an extra) (?:slide|page)\b|\bmore slides?\b", low)
                       or re.search(rf"(?:多|加|增加|新增|補|补|再加)\s*{_NUM}?\s*[頁页張张]", t))
        if re.search(r"\blogo\b|商標|商标|標誌|标志", low):
            return None, T("The logo is already on every slide: the co-brand lockup top right of the cover and the app icon beside the slide number elsewhere.",
                           "每一頁都已經有 logo：封面右上是聯名標誌，其他頁的頁碼旁有 app 圖示。")
        if re.search(r"\b(source line|footnote|citation|references?)\b|來源|来源|腳註|脚注|註腳|注脚", low) and not topic:
            return None, T("Every figure already carries [n], and the Sources slide at the end lists each report with its link.",
                           "每個數字都已經帶 [n]，最後的 Sources 頁列出每份報告與連結。")
        if re.search(r"\byields?\b|收益率|殖利率", low):
            i = next((i for i, s in enumerate(slides, 1) if any(isinstance(v, dict) and v.get("table") == "yields" for v in (s.get("fill") or {}).values())), None)
            if i:
                return None, T(f"The yields table is already on slide {i} (\"{title(i)}\"). To add a capital-markets slide, say `add a slide on investment`.",
                               f"收益率表已在第 {i} 頁「{title(i)}」。要加資本市場頁請說「加一頁講投資」。")
            topic = "capital"
        if re.search(r"\bpipeline\b|\bsupply\b|供應|供应|新供|開發|开发|在建", low) and not topic:
            return None, T("There is no pipeline story in this week's data, so I cannot add a slide on it without inventing figures.",
                           "本週資料裡沒有供應／pipeline 的故事，加這一頁就得編數字，所以沒有加。")
        if sub and not topic and not quoted:
            return None, T(f"There is no single-submarket slide: the deck's charts cover all of London (the rents chart includes {sub}). "
                           f"For a {sub} comparison, ask the Copilot on its own page.",
                           f"沒有單一分區的頁：簡報的圖表涵蓋整個倫敦（租金圖含 {sub}）。要看 {sub} 的比較，請到 Copilot 主頁問。")
        if not (counted or topic or quoted):
            return None, T("I can add slides from this week's stories (`add a slide on investment`, `add two slides`) or a statement slide "
                           "(`add a statement slide \"…\"`); that request is not one of them.",
                           "我可以從本週故事加頁（「加一頁講投資」「多兩頁」）或加陳述頁（「加一頁陳述「…」」）；這個要求不在其中。")
        want = _how_many(t)
        room = MAX_SLIDES - total
        if room <= 0:
            return None, T(f"A deck holds at most {MAX_SLIDES} slides; remove one first.", f"一份簡報最多 {MAX_SLIDES} 頁，請先刪一頁。")
        want = min(want, room)
        at = total - 1 if slides[-1].get("layout") == "Sources" else total  # before the sources slide
        if at > 1 and slides[at - 1].get("layout") == "Signal cards":
            at -= 1  # keep 'what changed' as the closing content slide
        if (m := re.search(r"\b(?:after|before)\s+(?:slide|page)\s*(\d+)", low) or re.search(r"第\s*(\d+)\s*[頁页張张]\s*(之?[前後后])", t)
                or re.search(r"(?:放在|放到|作為|作为|當|当)\s*第\s*(\d+)\s*[頁页張张]", t) or re.search(r"\bas slide (\d+)\b|\bat position (\d+)\b", low)):
            num = int(next(g for g in m.groups() if g and g.isdigit()))
            after = "after" in m.group(0) or m.group(0).endswith(("後", "后"))
            at = min(max(num + (1 if after else 0) - 1, 1), len(slides))
        if quoted:
            s = {"key": f"statement_{at}", "layout": "Statement", "eyebrow": "", "title": quoted,
                 "notes": quoted, "why": "Added in the slide editor.", "fill": {}}
            slides.insert(at, s)
            return _renumber(spec), T(f"Added a statement slide at position {at + 1}: \"{quoted}\".", f"已在第 {at + 1} 頁加入陳述頁「{quoted}」。")
        have = {s.get("key") for s in slides}
        pool = [c for c in (stories or []) if c.get("key") not in have]
        if topic and topic in have:
            i = next(i for i, s in enumerate(slides, 1) if s.get("key") == topic)
            return None, T(f"The deck already has a slide on that: slide {i}, \"{title(i)}\".", f"簡報裡已經有這個題目：第 {i} 頁「{title(i)}」。")
        if topic and not any(c["key"] == topic for c in pool):
            names = ", ".join(c["key"].replace("_", " ") for c in pool) or T("none left", "沒有了")
            return None, T(f"Nothing in this week's stories matches that. Stories not yet in the deck: {names}.",
                           f"本週的故事裡沒有這個題目。還沒放進簡報的故事：{names}。")
        if not pool:
            return None, T("Every story from this week's data is already in the deck; nothing to add without inventing figures.",
                           "本週資料裡的故事都已經在簡報裡了，再加就得編數字，所以沒有加。")
        picks = ([next(c for c in pool if c["key"] == topic)] if topic else []) + [c for c in pool if c["key"] != topic]
        added = []
        for c in picks[:want]:
            s = {"key": c["key"], "layout": c["layout"], "eyebrow": "", "title": c["title"], "why": c.get("reason", ""),
                 "so_what": c.get("so_what", ""), "notes": (c.get("reason") or "") + ".", "fill": c.get("fill") or {}}
            slides.insert(at + len(added), s)
            added.append(s)
        short = ""
        if len(added) < want:
            short = T(f" Only {len(added)} of the {want} asked for: this week's data has no more stories.",
                      f" 你要 {want} 頁，但本週資料只剩 {len(added)} 個故事可加。")
        lines = "; ".join(f"{at + i + 1}. \"{s['title']}\" ({s['layout']})" for i, s in enumerate(added))
        return _renumber(spec), T(f"Added {len(added)} slide{'s' if len(added) != 1 else ''}: {lines}.{short}",
                                  f"已新增 {len(added)} 頁：{lines}。{short}")
    if re.search(r"\b(translate|in chinese|into chinese|in english|tone|conservative|optimistic|cautious|wording|rewrite|rephrase)\b", low) \
            or re.search(r"翻譯|翻译|中文|英文|語氣|语气|保守|樂觀|乐观|措辭|措辞|改寫|改写|口吻", t):
        return None, T("Rewording, translating or changing the tone needs the Copilot (it rewrites the text and keeps every figure); "
                       "it is offline on this server. Offline I can retitle a slide with the words you give me.",
                       "改寫措辭、翻譯或改語氣要由 Copilot 做（它重寫文字並保留每個數字），目前 Copilot 離線。離線時我可以用你給的字改標題。")
    return None, T(HELP, HELP_ZH)


def describe(old: dict, new: dict, instruction: str = "") -> str:
    """What changed between two specs, by slide id, in the instruction's language: the reply states what the built
    deck actually has rather than what a model says it did."""
    zh = is_zh(instruction)
    os_, ns = old.get("slides", []), new.get("slides", [])
    oid = {s.get("id"): s for s in os_ if s.get("id")}
    nid = {s.get("id"): s for s in ns if s.get("id")}
    added = [s for s in ns if s.get("id") not in oid]
    removed = [s for s in os_ if s.get("id") not in nid]
    parts = []
    if added:
        items = "; ".join(f"{ns.index(s) + 1}. \"{s.get('title', '')}\"" + (f" — {s['why']}" if s.get("why") else "") for s in added)
        parts.append(f"新增 {len(added)} 頁：{items}" if zh else f"Added {len(added)} slide{'s' if len(added) != 1 else ''}: {items}")
    if removed:
        items = "; ".join(f"\"{s.get('title', '')}\"" for s in removed)
        parts.append(f"刪除 {len(removed)} 頁：{items}" if zh else f"Removed {len(removed)} slide{'s' if len(removed) != 1 else ''}: {items}")
    kept_new = [s.get("id") for s in ns if s.get("id") in oid]
    kept_old = [s.get("id") for s in os_ if s.get("id") in nid]
    if kept_new != kept_old:
        parts.append("順序有調整" if zh else "The order changed")
    for i, s in enumerate(ns, 1):
        o = oid.get(s.get("id"))
        if not o:
            continue
        if o.get("title") != s.get("title"):
            parts.append(f"第 {i} 頁標題改為「{s.get('title', '')}」" if zh else f"Slide {i} retitled \"{s.get('title', '')}\"")
        if o.get("so_what") != s.get("so_what"):
            parts.append(f"第 {i} 頁結論改為「{s.get('so_what', '')}」" if zh else f"Slide {i}'s so-what is now \"{s.get('so_what', '')}\"")
        if o.get("fill") != s.get("fill") or o.get("layout") != s.get("layout"):
            oc = [v for v in (o.get("fill") or {}).values() if isinstance(v, dict) and "chart" in v]
            nc = [v for v in (s.get("fill") or {}).values() if isinstance(v, dict) and "chart" in v]
            names = {"rents": ("rents", "租金"), "vacancy": ("vacancy", "空置率"), "take_up": ("take-up", "去化"), "investment": ("investment", "投資")}
            if o.get("layout") != s.get("layout"):
                parts.append(f"第 {i} 頁版面改為 {s.get('layout')}" if zh else f"Slide {i} is now a {s.get('layout')} slide")
            elif [c.get("chart") for c in oc] != [c.get("chart") for c in nc] and nc:
                changed = [c for k, c in enumerate(nc) if k >= len(oc) or oc[k].get("chart") != c.get("chart")] or nc
                what = "、".join(names.get(c.get("chart"), (c.get("chart"), c.get("chart")))[1] for c in changed) if zh else \
                    ", ".join(names.get(c.get("chart"), (c.get("chart"), c.get("chart")))[0] for c in changed)
                parts.append(f"第 {i} 頁的圖表換成{what}圖" if zh else f"Slide {i}'s chart is now the {what} chart")
            elif nc and oc != nc:
                bits = []
                for c in nc:
                    if c.get("last"):
                        bits.append(f"最近 {c['last']} 期" if zh else f"the last {c['last']} periods")
                    if c.get("markets"):
                        bits.append(("只看 " if zh else "only ") + ("、" if zh else ", ").join(c["markets"]))
                    if c.get("type"):
                        bits.append({"line": "折線圖", "bar": "橫條圖", "column": "柱狀圖"}[c["type"]] if zh else f"as a {c['type']} chart")
                parts.append((f"第 {i} 頁的圖表改為" + "、".join(bits)) if zh else (f"Slide {i}'s chart now shows " + ", ".join(bits))
                             if bits else (f"第 {i} 頁的圖表已更新" if zh else f"Slide {i}'s chart changed"))
            else:
                parts.append(f"第 {i} 頁的內容已更新" if zh else f"Slide {i}'s content changed")
        elif o.get("notes") != s.get("notes"):
            parts.append(f"第 {i} 頁的文字已更新" if zh else f"Slide {i}'s text changed")
    if old.get("theme") != new.get("theme"):
        parts.append(f"主題改為 {new.get('theme')}" if zh else f"Theme is now {new.get('theme')}")
    if not parts:
        parts.append("沒有變動" if zh else "Nothing changed")
    tail = f"現在共 {len(ns)} 頁。" if zh else f"The deck now has {len(ns)} slides."
    return ("。".join(parts) + "。" if zh else ". ".join(parts) + ".") + " " + tail
