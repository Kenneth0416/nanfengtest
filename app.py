"""Team workspace for the London Office Market Agent.  Run: streamlit run app.py

One shared tool for the whole business team, built around three jobs:
  Monitor     what changed, for you or for the whole team
  Copilot     ask anything from any page (Ctrl+K, or its own page)
  Team brief  the signals people added, written up as a board summary or an IC paper section
plus Sources, the team's shared data library: open data the agent collects by itself, and reports any
colleague uploads (when the publisher's terms bar automated collection). Whoever adds or checks a
figure, the whole team sees it, with who and when.

The layout follows the team's design prototype (prototype/index.html): left navigation, a page header
with the Copilot button, signal cards with a numbers line and source chips, and side panels for
sharing, watching rules, what needs a person and team activity.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from core import analytics as an
from core import documents
from core import internal as I
from core import focus as fx
from core import follow
from core import gather
from core import library as lib
from core import taxonomy as tx
from core.app import App
from core.icons import css as icons_css, icon, material, svg as icon_svg
from core.engine import AgentUnavailable, Engine, split_follow_ups
from core.pi_engine import Answer
from skills.brief_deck import tools as _bd
from core.signals import SignalEngine
from core.summary import is_tip, team_summary
from skills.watchlist_alerts.tools import parse_rule

st.set_page_config(page_title="London Office Market Agent", page_icon=":material/apartment:", layout="wide")
KIND_LABEL = {"metric_move": "Market data", "vs_long_term": "vs long-term average", "news": "News",
              "pipeline": "New supply", "macro": "Macro", "data_quality": "Data check", "alert": "Your alert"}
NOT_PEOPLE = {"auto", "cli", "scheduler", "guest", "agent", "team", "poc seed", "auto-update"}

# ---------------------------------------------------------------- look (from the prototype)
st.html("""
<style>
/* Tokens from prototype/design-tokens.md: slate neutrals, navy accent, amber highlight, four semantic colours */
:root { --bg:#F4F6F8; --surface:#FFFFFF; --sunk:#EAEEF2; --line:#D3DAE1; --ink:#0F1A2A; --ink2:#42506A; --ink3:#6B7A90;
        --accent:#1B3A5C; --accent-soft:#E3EAF2; --amber:#B9781A; --amber-soft:#FBF1DE;
        --open:#2E7D55; --open-soft:#E3F1E9; --upl:#B9781A; --upl-soft:#FBF1DE; --int:#2F6FBF; --int-soft:#E4EDF9;
        --flag:#B4452E; --flag-soft:#F7E4DF;
        --navy:var(--accent); --muted:var(--ink3); --soft:var(--sunk); --green:var(--open); --red:var(--flag); --orange:var(--upl); }
.stApp, .stApp * { font-variant-numeric: tabular-nums; }
.loa-ic.flag { color:var(--flag); } .loa-ic.amber { color:var(--amber); } .loa-ic.open { color:var(--open); }
.loa-ic.int { color:var(--int); } .loa-ic.accent { color:var(--accent); } .loa-ic.muted { color:var(--ink3); }
.loa-chip { display:inline-block; padding:2px 9px; border-radius:999px; font-size:12px; line-height:18px;
            background:var(--sunk); color:var(--ink2); margin:0 6px 4px 0; white-space:nowrap; }
.loa-chip.alert { background:var(--flag-soft); color:var(--flag); font-weight:600; }
.loa-chip.warn { background:var(--amber-soft); color:var(--amber); font-weight:600; }
.loa-chip.ok { background:var(--open-soft); color:var(--open); }
.loa-chip.src { background:var(--surface); border:1px solid var(--line); color:var(--ink2); }
.loa-chip.src::before { content:""; display:inline-block; width:8px; height:8px; border-radius:50%;
                        background:var(--upl); margin-right:5px; vertical-align:0; }
.loa-chip.src.auto::before { background:var(--open); } .loa-chip.src.int::before { background:var(--int); }
.loa-chip.int { background:var(--int-soft); color:var(--int); font-weight:600; }
a.loa-chip { text-decoration:none; }
/* source tier: always a coloured dot and a text label */
.loa-tier { display:inline-flex; align-items:center; white-space:nowrap; }
.loa-tier::before { content:""; display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:4px; background:var(--upl); }
.loa-tier.open::before { background:var(--open); } .loa-tier.int::before { background:var(--int); }
.loa-tier.flag::before { background:var(--flag); }
.sb { display:inline-block; font-size:11px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; line-height:16px;
      border:1px solid currentColor; border-radius:3px; padding:0 5px; margin-left:4px; vertical-align:1px; }
.sb.fresh { color:var(--open); } .sb.stale { color:var(--amber); } .sb.verified { color:var(--accent); }
.loa-kicker { font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--ink3); font-weight:600; }
.loa-num { font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace; font-weight:600; font-size:15px; color:var(--ink); }
.loa-nums { margin:2px 0 8px 0; color:var(--ink2); font-size:14px; }
.loa-dir { display:inline-flex; width:26px; height:26px; border-radius:50%; align-items:center; justify-content:center;
           font-weight:700; font-size:14px; margin-right:10px; vertical-align:middle; }
.loa-dir .loa-ic { margin:0; vertical-align:0; }
.loa-dir.pos { background:var(--open-soft); color:var(--open); } .loa-dir.neg { background:var(--flag-soft); color:var(--flag); }
.loa-dir.neu { background:var(--sunk); color:var(--ink2); } .loa-dir.alert { background:var(--amber-soft); color:var(--amber); }
.loa-title { font-size:17px; font-weight:700; color:var(--ink); margin:4px 0 2px 0; line-height:1.3; }
.loa-muted { color:var(--ink3); font-size:13px; } .loa-ink2 { color:var(--ink2); font-size:14px; line-height:1.5; }
.loa-av { display:inline-flex; width:24px; height:24px; border-radius:50%; background:var(--sunk); color:var(--ink2);
          font-size:11px; font-weight:700; align-items:center; justify-content:center; margin-right:-4px;
          border:2px solid var(--surface); vertical-align:middle; }
.loa-av.me { background:var(--accent); color:#fff; }
.loa-h1 { font-size:30px; font-weight:700; color:var(--ink); margin:0; line-height:1.15; letter-spacing:-.01em; }
.loa-sub { color:var(--ink2); font-size:15px; margin:4px 0 10px 0; }
.loa-fresh { display:flex; flex-wrap:wrap; gap:6px 18px; font-size:13px; color:var(--ink2); padding:8px 0 4px 0;
             border-top:1px solid var(--line); border-bottom:1px solid var(--line); margin-bottom:6px; }
.loa-fresh b { color:var(--ink); }
.loa-big { font-size:20px; font-weight:700; color:var(--ink); margin:2px 0 6px 0; }
.loa-h2 { font-size:19px; font-weight:700; color:var(--ink); margin:6px 0 2px 0; }
.loa-badge { display:inline-block; background:var(--flag); color:#fff; border-radius:999px; font-size:11px;
             font-weight:700; padding:1px 7px; margin-left:6px; vertical-align:middle; }
.loa-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; vertical-align:1px; }
.loa-dot.red { background:var(--flag); } .loa-dot.green { background:var(--open); }
.loa-dot.orange { background:var(--upl); } .loa-dot.amber { background:var(--amber); } .loa-dot.blue { background:var(--int); }
.loa-deal { border:1px solid var(--line); border-left:3px solid var(--int); border-radius:6px; padding:10px 14px; background:var(--surface); margin:6px 0; }
.loa-fields { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:6px 12px; font-size:13px; margin-top:6px; }
.loa-fields small { display:block; color:var(--ink3); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
.loa-fields .empty { color:var(--amber); font-style:italic; }
.loa-banner { background:var(--accent-soft); border-radius:6px; padding:12px 16px; color:var(--ink2); font-size:14px; }
.loa-box { background:var(--sunk); border-radius:6px; padding:8px 12px; margin:4px 0; }
.loa-box .k { font-size:10px; letter-spacing:.08em; text-transform:uppercase; color:var(--ink3); font-weight:600; }
.loa-box .v { font-size:15px; font-weight:600; color:var(--ink); }
.loa-prose { font-size:16px; line-height:1.55; color:var(--ink); }
.loa-team { border:1px solid var(--line); border-radius:6px; padding:12px 14px; font-size:13px; color:var(--ink2); background:var(--surface); }
.loa-team b { color:var(--ink); font-size:14px; }
.loa-brand { display:flex; align-items:center; gap:8px; font-size:17px; font-weight:700; color:var(--ink); margin:4px 0 2px 0; }
.loa-brand .loa-ic { margin:0; color:var(--accent); }
/* Copilot floating button: bottom right of every page, above the content; gone while the panel is open */
.st-key-fab_copilot { position:fixed; right:max(20px, env(safe-area-inset-right)); bottom:max(20px, env(safe-area-inset-bottom));
  z-index:1001; width:auto !important; }
.st-key-fab_copilot button, .st-key-fab_close button { width:48px; height:48px; min-height:48px; border-radius:50%; padding:0;
  box-shadow:0 4px 16px rgba(15,26,42,.30); }
.st-key-fab_copilot button [data-testid="stIconMaterial"], .st-key-fab_close button [data-testid="stIconMaterial"] { font-size:24px; }
body:has(div[data-testid="stDialog"]) .st-key-fab_copilot { display:none; }
/* while the panel is open the same spot holds a white close button, just left of the panel's edge (desktop) */
.st-key-fab_close { position:fixed; bottom:max(20px, env(safe-area-inset-bottom)); right:772px; z-index:1001; width:auto !important; }  /* panel is 752px wide */
.st-key-fab_close button { background:#fff; color:var(--accent); border:1px solid var(--line); }
@media (max-width: 760px) { .st-key-fab_close { display:none; } }
/* Copilot side panel: the input box stays at the bottom of the panel while the conversation scrolls above it */
div[data-testid="stDialog"] section > div { display:flex; flex-direction:column; }
div[data-testid="stDialog"] section > div > div[data-testid="stVerticalBlock"],
div[data-testid="stDialog"] section > div > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"],
div[data-testid="stDialog"] section > div > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"]
  { flex:1 0 auto; display:flex; flex-direction:column; }
div[data-testid="stDialog"] .stElementContainer:has(> .stChatInput) { position:sticky; bottom:-20px; margin-top:auto;
  background:#fff; padding:8px 0 20px 0; z-index:5; }
</style>
""")
st.html(f"<style>{icons_css()}</style>")  # the icons themselves (CSS masks: st.html strips inline <svg>)


def esc(x) -> str:
    return html.escape(str(x or ""))


def chip(text, kind="", href="") -> str:
    inner = f'<span class="loa-chip {kind}">{esc(text)}</span>'
    return f'<a class="loa-chip {kind}" href="{esc(href)}" target="_blank">{esc(text)}</a>' if href else inner


def kicker(text) -> str:
    return f'<div class="loa-kicker">{esc(text)}</div>'


def tier(kind: str, label: str) -> str:
    """A source tier shown as a coloured dot plus its text label: open (data collected automatically),
    upl (a report uploaded by a colleague), int (internal data) or flag (needs a person)."""
    return f'<span class="loa-tier {kind}">{esc(label)}</span>'


def ic(name: str, size: int = 16, cls: str = "") -> str:
    return icon(name, size, cls)


def avatars(names, me="") -> str:
    out = []
    if me:
        out.append('<span class="loa-av me">Me</span>')
    for n in names[:5]:
        out.append(f'<span class="loa-av">{esc(n[:1].upper())}</span>')
    return "".join(out)


@st.cache_resource
def get_app():
    app = App()
    app.ensure_data()
    return app, Engine(app)


app, engine = get_app()
team = app.config["team"]
signals = SignalEngine(app.store, app.config)


def src_chip(e) -> str:
    """One source chip: green dot for open data collected automatically, orange for a colleague's upload."""
    ref = an.source_ref(app.store, e.source_id) if e.source_id else {}
    auto = ref.get("channel", "auto") == "auto"
    return chip(e.text, "src auto" if auto else "src", e.url or ref.get("url", ""))


def colleagues() -> list[str]:
    names = {r["author"] for r in app.store.q("SELECT DISTINCT author FROM team_log")}
    names |= {s.get("uploaded_by") for s in app.store.sources().values()}
    names |= {r["added_by"] for r in app.store.q("SELECT DISTINCT added_by FROM followed")}
    return sorted(n for n in names if n and n.lower() not in NOT_PEOPLE and not n.startswith("Auto-update"))


# ---------------------------------------------------------------- shared state
checks = [s for s in signals.source_conflicts() if s.id not in app.store.checked()]
flagged = app.store.flagged()
our_deals = app.store.internal_deals()
deal_drafts = [d for d in our_deals if d.get("status") != "confirmed"]
to_check = len(checks) + len(flagged) + len(deal_drafts)
brief_count = len(app.store.brief_items())

# ---------------------------------------------------------------- sidebar (own navigation, like the prototype)
# No login: the name lives in the page address (?me=Kenneth) and in a browser cookie, so a refresh, a bookmark or
# a plain visit to the address brings the same person back, with their focus and their saved chats.
st.session_state.setdefault("me", st.query_params.get("me") or st.context.cookies.get("loa_me") or "Guest")
if next_name := st.session_state.pop("me_next", None):  # a name picked on the 'Who's asking?' card last run
    st.session_state["me"] = next_name
user = (st.session_state.get("me") or "Guest").strip() or "Guest"


def remember_me():
    """Browser side of the identity: a cookie with the name typed in the sidebar or picked on the card, read back
    by the app on the next visit (st.context.cookies). Clearing the name in the sidebar forgets it."""
    components.html(f"""<script>(function () {{ try {{
  const name = {json.dumps(user if user != "Guest" else "")}, cleared = {json.dumps(bool(st.session_state.get("me_cleared")))};
  const doc = window.parent.document;
  if (name) doc.cookie = "loa_me=" + encodeURIComponent(name) + "; path=/; max-age=31536000; SameSite=Lax";
  else if (cleared) doc.cookie = "loa_me=; path=/; max-age=0; SameSite=Lax";
}} catch (e) {{}} }})();</script>""", height=0)


def chat_owner() -> str:
    """Whose chats are on screen: the person's name, or for a visitor without a name this browser session only."""
    if user != "Guest":
        return user
    return st.session_state.setdefault("guest_id", "guest-" + hashlib.sha1(str(id(st.session_state)).encode()).hexdigest()[:8])


def open_chat(chat_id: str | None):
    """Put one saved chat on screen (None: a new, empty one; its row is created with the first question)."""
    st.session_state["chat_id"] = chat_id
    turns = []
    for m in (app.store.chat_messages(chat_id) if chat_id else []):
        turn = {"role": m["role"], "content": m["content"]}
        if m["role"] == "assistant" and m["trace"]:
            turn["answer"] = Answer(m["content"], m["trace"], m["engine"])
        turns.append(turn)
    st.session_state["chat_turns"] = turns


def current_chat() -> tuple[str | None, list[dict]]:
    """(chat id, turns) of the conversation on screen. After a refresh, or when the name changes, the person's
    latest saved chat comes back, so nothing is lost by reloading the page."""
    owner = chat_owner()
    if st.session_state.get("chat_owner") != owner:
        st.session_state["chat_owner"] = owner
        latest = app.store.chats(owner, limit=1)
        open_chat(latest[0]["id"] if latest else None)
    return st.session_state.get("chat_id"), st.session_state.setdefault("chat_turns", [])


def ensure_chat() -> str:
    """The id of the chat on screen, creating its row for the first question. The id also names the Copilot's
    conversation in Pi, so each chat keeps its own context and a new chat starts clean."""
    if not st.session_state.get("chat_id"):
        st.session_state["chat_id"] = app.store.new_chat(chat_owner())
    return st.session_state["chat_id"]


def say(role: str, content: str, ans: Answer | None = None):
    """Add a turn to the conversation on screen and to the saved chat."""
    chat_id = ensure_chat()
    turn = {"role": role, "content": content}
    if ans is not None:
        turn["answer"] = ans
    st.session_state.setdefault("chat_turns", []).append(turn)
    app.store.add_chat_message(chat_id, role, content, ans.trace if ans else None, ans.engine if ans else "")


def when(ts: str) -> str:
    """A saved chat's time, short: 14:02 today, else 'Tue 14:02' this week, else '3 Oct'."""
    try:
        t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone()
    except (TypeError, ValueError):
        return ""
    now = datetime.now(t.tzinfo)
    if t.date() == now.date():
        return t.strftime("%H:%M")
    if (now - t).days < 7:
        return t.strftime("%a %H:%M")
    return t.strftime("%-d %b")


def sidebar():
    global user
    with st.sidebar:
        st.html(f'<div class="loa-brand">{ic("building", 20)}London Office Market Agent</div>')
        st.caption("Proof of concept · live data library")
        user = st.text_input("Your name", key="me",
                             help="Used for your own 'For you' view and to show the team who added what").strip() or "Guest"
        if user != "Guest" and st.query_params.get("me") != user:
            st.query_params["me"] = user
            st.session_state["me_cleared"] = False
        elif user == "Guest" and st.query_params.get("me"):
            del st.query_params["me"]  # the name was cleared on purpose: forget it in the browser too
            st.session_state["me_cleared"] = True
        remember_me()
        st.html(kicker("Work"))
        st.page_link(PAGE_OBJ["monitor"], label="Monitor", icon=material("activity"), help="Stay ahead of the market")
        st.page_link(PAGE_OBJ["copilot"], label="Ask Copilot", icon=material("message-square"), help="Judge: ask, compare, drill down")
        st.page_link(PAGE_OBJ["brief"], label=f"Team brief · {brief_count}" if brief_count else "Team brief",
                     icon=material("file-text"), help="Report: board and IC outputs")
        st.page_link(PAGE_OBJ["sources"], label=f"Sources · {to_check} to check" if to_check else "Sources",
                     icon=material("database"), help="Data the agent maintains")
        st.html(f"""{kicker("Team")}
<div class="loa-team"><b>{esc(team['name'])}</b><div style="margin:6px 0 8px 0">{avatars(colleagues(), user)}</div>
One workspace and one set of data. Each person sets their own focus.<br><br>
Anyone can upload a report; the whole team sees it.</div>""")
        st.caption(f"**Data up to:** {an.period_label(an.latest_period(app.store))}")
        with st.expander("Technical details"):
            st.caption(f"Engine: {engine.status}")
            st.caption(f"PDF reader: {app.vision.model if getattr(app.vision, 'available', False) else 'rule-based text reading'}")


def goto(key: str, **state):
    st.session_state.update(state)
    st.switch_page(PAGE_OBJ[key])


def copilot_fab():
    """The Copilot's floating button: fixed at the bottom right of every page except the Copilot page itself, so
    a question is one click away wherever the reader is. Hidden while the side panel is open (its own X
    closes it). The stylesheet positions it by the element's key class (st-key-fab_copilot)."""
    if st.button("", icon=material("message-square"), key="fab_copilot", type="primary",
                 help="Ask Copilot · Ctrl+K or /"):
        open_copilot()


def page_header(title: str, subtitle: str, extra: tuple | None = None):
    copilot_fab()
    follow_output()  # the page-level keyboard shortcut ("/") and follow-scrolling need the script on every page
    c = st.columns([4, 1.6, 1.5] if extra else [4.5, 1.5], vertical_alignment="center")
    c[0].html(f'<div class="loa-h1">{esc(title)}</div><div class="loa-sub">{esc(subtitle)}</div>')
    if extra:
        label, key, target = extra
        if c[1].button(label, key=key, width="stretch"):
            goto(target)
    if c[-1].button("Ask Copilot", icon=material("message-square"), shortcut="ctrl+k", type="primary", width="stretch", key=f"ask_{title[:8]}",
                    help="Shortcut: Ctrl+K"):
        open_copilot()


def chart(spec: dict | None):
    if not spec:
        return
    fig = go.Figure()
    for s in spec["series"]:
        if spec["type"] == "bar":
            fig.add_bar(x=spec["x"], y=s["values"], name=s["name"], marker_color="#1B3A5C")
        else:
            fig.add_scatter(x=spec["x"], y=s["values"], name=s["name"], mode="lines+markers",
                            line_shape="hv" if spec["type"] == "step" else "linear",
                            line=dict(dash="dot", color="#6B7A90") if s["name"] == "Long-term average"
                            else dict(color="#1B3A5C"))
    fig.update_layout(title=spec["title"], yaxis_title=spec.get("unit", ""), height=300,
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h"),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")


def show_answer(ans, text_done: bool = False):
    if not text_done:
        st.markdown(split_follow_ups(ans.text)[0])
    for step in ans.trace:
        chart(step["result"].get("chart"))
        if step["tool"] == "build_brief_pptx" and (p := (step["result"].get("data") or {}).get("path")) and Path(p).exists():
            st.download_button("Download the slides (.pptx)", Path(p).read_bytes(), file_name=Path(p).name,
                               mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                               key=f"dl{hash(p)}{id(step)}")
    sources = {(s.get("title"), s.get("url")) for step in ans.trace for s in step["result"].get("sources", []) or []}
    if sources:
        st.html("".join(chip(t, "src auto", u) for t, u in sorted(sources, key=lambda x: x[0] or "")))
    with st.expander("How I worked this out"):
        st.caption(f"Engine: {ans.engine} · tools: {', '.join(t['tool'] for t in ans.trace) or 'none'}")


# Runs in the page itself (not in the component's iframe, which Streamlit re-creates on every rerun and
# whose observers would die with it): the loader below writes this into a <script> on the parent document once.
FOLLOW_CORE = r"""(function () {
  const doc = document;
  // Follow-the-output scrolling: a chat container scrolls with the answer while the reader is at the bottom.
  // Scroll up to read something older and it stays put; scroll back to the bottom (or send a new question)
  // and it follows again. State is kept per scroll container (the page, or the side panel), so each behaves alone.
  const follow = new WeakMap();
  const NEAR = 48;  // px from the bottom that still counts as "at the bottom"
  function scroller(el) {
    // the outermost scrollable ancestor: the page (section.stMain) for the Copilot page, the dialog's own
    // scroll area for the side panel; inner blocks that merely declare overflow are skipped
    let found = null;
    while (el && el !== doc.body) {
      const st = getComputedStyle(el);
      if (/(auto|scroll)/.test(st.overflowY) && el.scrollHeight > el.clientHeight + 4) { found = el; }
      el = el.parentElement;
    }
    return found || doc.querySelector("section.stMain") || doc.scrollingElement;
  }
  function atBottom(c) { return c.scrollHeight - c.scrollTop - c.clientHeight < NEAR; }
  function isFollowing(c) { return follow.has(c) ? follow.get(c) : true; }
  function latestButton(c, show) {
    let b = c.__loaLatest;
    if (!b) {
      b = doc.createElement("button");
      b.innerHTML = ARROW + " Jump to latest";
      b.className = "loa-latest";
      b.style.cssText = "position:fixed;z-index:1000;border:1px solid #1B3A5C;background:#fff;color:#1B3A5C;display:inline-flex;align-items:center;gap:4px;"
        + "border-radius:999px;padding:5px 14px;font-size:12px;cursor:pointer;box-shadow:0 1px 6px rgba(0,0,0,.2);display:none";
      b.addEventListener("click", () => { follow.set(c, true); c.scrollTo({ top: c.scrollHeight, behavior: "smooth" }); b.style.display = "none"; });
      doc.body.appendChild(b);
      c.__loaLatest = b;
    }
    if (show) {  // float it over the lower middle of the container it belongs to (the page or the side panel)
      const r = c.getBoundingClientRect();
      b.style.left = Math.round(r.left + r.width / 2 - 60) + "px";
      b.style.top = Math.round(Math.min(r.bottom, window.innerHeight) - 56) + "px";
    }
    b.style.display = show ? "inline-block" : "none";
  }
  doc.addEventListener("scroll", (e) => {
    const c = e.target === doc ? doc.scrollingElement : e.target;
    if (!c || !c.scrollHeight) { return; }
    const nowAtBottom = atBottom(c);
    follow.set(c, nowAtBottom);
    if (nowAtBottom && c.__loaLatest) { c.__loaLatest.style.display = "none"; }
  }, true);
  const seen = new Set();
  const observer = new MutationObserver((muts) => {
    seen.clear();
    for (const m of muts) {
      const t = m.target.nodeType === 1 ? m.target : m.target.parentElement;
      if (!t) { continue; }
      const msg = t.closest("[data-testid='stChatMessage']");
      if (!msg) { continue; }
      const c = scroller(msg);
      if (!c || seen.has(c)) { continue; }
      seen.add(c);
      // a new question from the reader always resumes following, wherever they had scrolled to
      for (const n of m.addedNodes) {
        if (n.nodeType === 1 && n.querySelector && n.querySelector("[data-testid='stChatMessageAvatarUser']")) { follow.set(c, true); }
      }
      if (isFollowing(c)) { c.scrollTop = c.scrollHeight; }
      else { latestButton(c, true); }
    }
  });
  observer.observe(doc.body, { childList: true, subtree: true, characterData: true });
  // "/" anywhere outside a text box puts the cursor in the Copilot's input (Ctrl+K opens the side panel)
  doc.addEventListener("keydown", (e) => {
    if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) { return; }
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) { return; }
    const boxes = doc.querySelectorAll("textarea[data-testid='stChatInputTextArea']");
    e.preventDefault();
    if (boxes.length) { boxes[boxes.length - 1].focus(); return; }
    const fab = doc.querySelector(".st-key-fab_copilot button");
    if (fab) { fab.click(); }
  });
})();"""

FOLLOW_JS = """<script>
(function () {
  const doc = window.parent.document;
  if (doc.__loaFollow) { return; }
  doc.__loaFollow = true;
  const s = doc.createElement("script");
  s.textContent = window.frameElement.getAttribute("data-follow");
  doc.body.appendChild(s);
})();
</script>"""


def follow_output():
    """Install the follow-the-output scroll behaviour on every chat surface (once per page load). The code travels
    in the iframe's srcdoc as a data attribute it reads and installs into the page itself."""
    core = FOLLOW_CORE.replace("ARROW", json.dumps(icon_svg("arrow-down", 14)), 1)
    loader = FOLLOW_JS.replace('window.frameElement.getAttribute("data-follow")', "CODE")
    components.html(f"<script>const CODE = {json.dumps(core)};</script>" + loader, height=0)


def focus_input():
    """Put the cursor back in the chat box after an answer, so the next question needs no click."""
    components.html("""<script>(function(){const d=window.parent.document;
      const boxes=d.querySelectorAll("textarea[data-testid='stChatInputTextArea']");
      const b=boxes[boxes.length-1]; if(b){b.focus();}})();</script>""", height=0)


def my_focus() -> dict | None:
    return app.store.focus(user)


# ---------------------------------------------------------------- copilot (side panel or its own page)
PAGE_SUGGESTIONS = {
    "monitor": team["questions"][:2] + ["Show me more Fitzrovia and less macro",
                                        "I heard from a broker that Google is looking for 200,000 sq ft in King's Cross"],
    "copilot": team["questions"][:4],
    "brief": ["Make the brief into slides for Monday's meeting", "Build a client update deck on the forest theme",
              "Draft the market section of the IC paper",
              "What are the main downside risks right now?", "Compare Midtown and City Core"],
    "sources": ["We just let 1 Triton Square 4th floor at £95, 10 year term", "What have we let this quarter?",
                "Which figures disagree between sources?", "Follow Savills Market Watch",
                "Show the latest leasing news on tech and AI occupiers"],
}
PAGE_TITLES = {"monitor": "Monitor", "copilot": "Copilot", "brief": "Team brief", "sources": "Sources"}
SETUP_EXAMPLES = ["I manage offices in Fitzrovia and the City Core and worry about rents and new supply",
                  "I run acquisitions in the City and Midtown and present to the IC monthly",
                  "I head the fund and have three minutes a week"]
SIGNAL_SUGGESTIONS = ["What does this mean for us?", "Show the trend behind this",
                      "How does it compare with other submarkets?"]


def open_copilot(context=None):
    """Context is the page the person is on, a signal card, or setting up their focus."""
    st.session_state["copilot_ctx"] = context or {"kind": "page", "page": st.session_state.get("page", "monitor")}
    copilot()


@st.dialog("Copilot", position="right", width="medium", on_dismiss="rerun")
def copilot():
    st.session_state["_in_dialog"] = True
    if st.button("", icon=material("x"), key="fab_close", help="Close · Esc"):
        st.rerun()  # a full rerun closes the panel; the page underneath keeps its place and the chat is saved
    copilot_body()


def _rerun():
    st.rerun(scope="fragment" if st.session_state.get("_in_dialog") else "app")


def copilot_body(full: bool = False, question: str | None = None, own_input: bool = True):
    """The conversation: a header with what the Copilot is looking at, History and New chat; the saved chat; the
    example questions only while the chat is empty; the input box at the bottom (the page passes its own
    pinned one in `question`; the side panel makes one here)."""
    ctx = st.session_state.get("copilot_ctx", {"kind": "page", "page": "monitor"})
    sfx = "d" if st.session_state.get("_in_dialog") else "p"
    if user == "Guest" and not st.session_state.get("skip_who"):
        who_card(sfx)  # first visit in this browser: pick a name once, no login
        return
    chat_id, turns = current_chat()
    turns = absorb_partial(chat_id, turns)
    head = st.columns([3.2, 1.2, 1.25, 1.25], vertical_alignment="center")
    looking = {"setup": "setting up your focus", "signal": ctx.get("title", "")}.get(
        ctx["kind"], PAGE_TITLES.get(ctx.get("page", ""), ctx.get("page", "")))
    head[0].html(f'<div class="loa-box">Looking at: <b>{esc(looking)}</b></div>')
    with head[1].popover(user if user != "Guest" else "Who?", width="stretch", help="Who is asking; change the name"):
        who_card(sfx, compact=True)
    with head[2].popover("History", width="stretch", help="Your saved conversations"):
        history_list(chat_id, sfx)
    if head[3].button("New chat", width="stretch", key=f"newchat_{sfx}", help="Start a clean conversation"):
        open_chat(None)
        _rerun()
    if ctx["kind"] == "setup":
        intro = ("Tell me what you do in one sentence and I'll set up your 'For you' view: submarkets, measures, "
                 "how much to show and alerts. Nothing changes until you press Apply. The team view stays as it is.")
        suggestions = SETUP_EXAMPLES
    elif ctx["kind"] == "signal":
        intro, suggestions = "", SIGNAL_SUGGESTIONS
    else:
        intro = ("Ask me anything about the London office market. I can see what's on your screen, and every "
                 "number I give you comes with its source. You can also change your own view, e.g. 'more "
                 "Fitzrovia, less macro'.")
        suggestions = PAGE_SUGGESTIONS.get(ctx.get("page", ""), team["questions"][:4])
    clicked = None
    if not turns and intro:
        st.markdown(intro)
    thread = st.container()  # the conversation; the input box sits below it, pinned to the bottom
    sugg = st.empty()  # example questions or follow-ups go here, under the thread, but only when nothing is being asked
    if own_input:
        question = st.chat_input(chat_placeholder(ctx), key="copilot_input", max_chars=2000)
    if not question:
        with sugg.container():
            if not turns:  # the examples belong to a new chat; afterwards only the last answer's own follow-ups show
                cols = [st] * 2
                for i, q in enumerate(suggestions):
                    if cols[i % 2].button(q, key=f"cs{q}", width="stretch"):
                        clicked = q
            elif turns[-1]["role"] == "assistant" and turns[-1]["content"].endswith("*Stopped.*") and len(turns) > 1:
                if st.button("Ask again", icon=material("refresh-cw"), key=f"again{len(turns)}"):
                    clicked = turns[-2]["content"]
            elif turns[-1]["role"] == "assistant" and "answer" in turns[-1]:
                _, follow_ups = split_follow_ups(turns[-1]["answer"].text)
                if follow_ups:
                    st.html(kicker("Follow up"))
                    cols = st.columns(len(follow_ups))
                    for i, q in enumerate(follow_ups):
                        if cols[i].button(q, key=f"fu{len(turns)}_{i}", width="stretch"):
                            clicked = q
    question = question or clicked
    if clicked:
        sugg.empty()  # a question is on its way: the buttons leave the screen, as a typed question would
    follow_output()
    with thread:
        copilot_thread(turns, ctx, question)


def who_card(sfx: str, compact: bool = False):
    """Who's asking: pick a name once (the team's names, or type one); this browser then remembers it, with the
    person's focus and conversations. No login."""
    names = list(dict.fromkeys([*team.get("members", []), *colleagues()]))
    if not compact:
        st.html('<div class="loa-box"><b>Who\'s asking?</b><div class="loa-ink2">No login needed. Pick your name once and '
                'this browser remembers you, your focus and your conversations.</div></div>')
    else:
        st.caption("Asking as " + (user if user != "Guest" else "a guest") + ". Pick another name:")
    cols = st.columns(3) if names else []
    for i, n in enumerate(names):
        if cols[i % 3].button(n, key=f"who_{sfx}_{n}", width="stretch"):
            become(n)
    typed = st.text_input("Or type your name", key=f"who_typed_{sfx}", placeholder="Your name", label_visibility="collapsed")
    c = st.columns(2)
    if c[0].button("Continue", type="primary", key=f"who_go_{sfx}", width="stretch") and typed.strip():
        become(typed.strip())
    if not compact and c[1].button("Skip for now", key=f"who_skip_{sfx}", width="stretch"):
        st.session_state["skip_who"] = True
        _rerun()


def become(name: str):
    """Switch the person on screen; the sidebar, the address and the browser follow on the next run."""
    st.session_state["me_next"] = name  # applied before the sidebar's name box exists on the next run
    st.session_state["me_cleared"] = False
    st.query_params["me"] = name
    st.rerun()


def chat_placeholder(ctx) -> str:
    return {"setup": "Describe your job in one sentence…", "signal": "Ask about this signal…"}.get(
        ctx["kind"], "Ask about any London submarket… (Enter sends, Shift+Enter for a new line)")


def history_list(chat_id, sfx):
    chats = app.store.chats(chat_owner())
    if not chats:
        st.caption("No saved conversations yet. They are kept under your name, so a refresh never loses one.")
        return
    for c in chats:
        label = (c["title"] or "Untitled")[:60]
        current = c["id"] == chat_id
        if st.button(label, key=f"hist_{sfx}_{c['id']}", width="stretch",
                     help=f"{c['messages']} messages", type="primary" if current else "secondary"):
            open_chat(c["id"])
            _rerun()
        st.caption(f"{when(c['updated'])} · {c['messages']} messages")


def absorb_partial(chat_id, turns):
    """After the reader pressed Stop (or clicked elsewhere) while an answer was streaming: keep what was
    written, marked 'Stopped', in the chat it belonged to. Returns the turns on screen, reloaded if that chat."""
    if partial := st.session_state.pop("partial", None):
        app.store.add_chat_message(partial["chat"], "user", partial["q"])
        app.store.add_chat_message(partial["chat"], "assistant", (partial["text"].rstrip() or "(nothing written yet)")
                                   + "\n\n*Stopped.*")
        if partial["chat"] == chat_id:
            open_chat(chat_id)
            return st.session_state["chat_turns"]
    return turns


def copilot_thread(turns, ctx, question):
    for turn in turns:
        with st.chat_message(turn["role"]):
            if turn["role"] == "user" or "answer" not in turn:
                st.markdown(turn["content"])
            else:
                show_answer(turn["answer"])
    if question and ctx["kind"] == "setup":
        say("user", question)
        with st.spinner("Drafting your setup…"):
            st.session_state["proposal"] = fx.propose(question, app.store, app.llm)
        _rerun()
    if st.session_state.get("proposal") and ctx["kind"] == "setup":
        setup_card(st.session_state["proposal"])
    if question and (changes := fx.parse_command(question)):
        # "More Fitzrovia, less macro" changes this person's view instead of asking the agent.
        app.store.save_focus(user, fx.apply(my_focus() or fx.defaults(app.config), changes))
        st.session_state.pop("applied_setup", None)  # Undo now reverts this change only
        reply = f"Done. {fx.describe(changes)} in your 'For you' view. The team view is unchanged."
        say("user", question)
        say("assistant", reply)
        st.session_state["undo_ready"] = True
        _rerun()
    if st.session_state.get("undo_ready") and st.button("Undo that change", icon=material("undo-2"), key="undo_focus"):
        fx.undo_setup(app.store, user, st.session_state.pop("applied_setup", {}))
        st.session_state["undo_ready"] = False
        say("assistant", "Undone. Your previous view is back.")
        _rerun()
    if question and not engine.ready and (want := _bd.deck_request(question)):
        # The Copilot is offline: a request for slides still gets a deck, picked by rules from this week's data.
        fmt, theme = want
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            how, _ = build_deck_now(fmt, theme)
            key = deck_key(fmt)
            if how:
                reply = (f"The Copilot is offline on this server, so rules picked the slides from this week's data: "
                         f"{fx.BRIEF_FORMATS[fmt].lower()}, {DECK_THEMES[theme]}. The numbers and sources are the same; "
                         "the choice of slides and the titles are standard.\n\n"
                         + "\n".join(f"- {line}" for line in st.session_state.get(key + "_slides") or []))
                st.markdown(reply)
                st.download_button("Download .pptx", st.session_state[key], key=f"dl_chat_{len(turns)}",
                                   file_name=f"london-office-team-brief-{fmt}-{theme}.pptx",
                                   mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
                say("user", question)
                say("assistant", reply)
                app.store.log("ask", user, question, reply[:600])
        return
    if question:
        st.session_state["undo_ready"] = False
        # The signal card travels with the question so the agent knows which market and figure "this" means.
        asked = f"{question} (About: {ctx['title']}. {ctx['detail']})" if ctx["kind"] == "signal" else question
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            ans = stream_answer(asked, ensure_chat(), question)
            if ans is None:
                return
            show_answer(ans, text_done=True)
        say("user", question)
        say("assistant", ans.text, ans)
        app.store.log("ask", user, question, ans.text[:600])
        focus_input()
        _rerun()  # the thread re-renders from the saved chat: follow-up buttons, no raw 'Follow up:' line


FOLLOW_LINE = re.compile(r"\n[ \t]*\**[ \t]*follow", re.I)  # a line that may become the closing 'Follow up:' line
TOOL_WORDS = {"get_signals": "reading this week's signals", "get_metric_trend": "pulling the trend",
              "compare_markets": "comparing submarkets", "generate_brief": "writing the brief",
              "brief_deck_data": "reading the deck data", "build_brief_pptx": "building the slides",
              "record_deal": "recording the deal", "list_our_deals": "listing our deals", "search_news": "searching the news"}


def stream_answer(asked: str, chat_id: str | None = None, question: str = ""):
    """Ask the Copilot (continuing the chat `chat_id`) and show the answer as it is written. A Stop button sits
    under the status line while it writes: pressing it keeps what has arrived (marked 'Stopped') and offers
    'Ask again'. A status line names each tool as it starts; the
    text streams in underneath; the tools' charts, sources and download buttons follow when it is done.
    Returns the Answer, or None after showing why there is none."""
    if not engine.ready:
        try:
            engine.ask(asked, user)  # raises PiNotReady with the plain-language message
        except AgentUnavailable as e:
            st.warning(str(e))
            if e.detail:
                with st.expander("Technical details"):
                    st.code(e.detail, language=None)
        return None
    status = st.status("Reading market data…", expanded=False)
    stream = engine.ask_streaming(asked, user, chat_id)
    tools = []
    stop = st.empty()
    stop.button("Stop", icon=material("square"), key=f"stop_{chat_id}", type="tertiary",
                help="Keep what has been written so far and stop")
    st.session_state["partial"] = {"q": question or asked, "chat": chat_id, "text": ""}
    shown = {"text": ""}

    held_box = {"text": "", "line_start": True}  # the tail is held back so the closing 'Follow up:' line never shows

    def pieces():
        for e in stream.events():
            if e["event"] == "delta":
                held = held_box["text"] + e["text"]
                last = None
                for last in FOLLOW_LINE.finditer(held):
                    pass
                if last:
                    cut = last.start()
                elif held_box["line_start"] and FOLLOW_LINE.match("\n" + held):
                    cut = 0
                else:
                    cut = None
                if cut is not None:
                    out, held = held[:cut], held[cut:]
                elif len(held) > 24:
                    out, held = held[:-24], held[-24:]
                else:
                    out = ""
                held_box["text"] = held
                held_box["line_start"] = (cut == 0 and held_box["line_start"]) or out.endswith("\n")
                if out:
                    shown["text"] += out
                    st.session_state["partial"]["text"] = shown["text"]  # what a Stop would keep
                    yield out
            elif e["event"] == "tool":
                tools.append(e["name"])
                status.update(label=f"Working: {TOOL_WORDS.get(e['name'], e['name'].replace('_', ' '))}…")
                status.write(f"→ {e['name']}")
            elif e["event"] == "reset":
                status.write("Your earlier conversation could not be loaded and was set aside; starting a new one.")
            elif e["event"] == "retry":
                status.write("Taking longer than expected; resuming from the last checkpoint.")
    def pieces_then_rest():
        yield from pieces()
        # whatever was held: all of it unless it is the follow-up line (the buttons below take over)
        yield split_follow_ups(held_box["text"])[0] if held_box["text"] else ""
    text = st.write_stream(pieces_then_rest())
    stop.empty()
    st.session_state.pop("partial", None)  # finished: nothing to keep from a stop
    if stream.error is not None:
        status.update(label="Could not finish", state="error")
        e = stream.error
        st.warning(str(e))
        if getattr(e, "detail", ""):
            with st.expander("Technical details"):
                st.code(e.detail, language=None)
        return None
    ans = stream.answer
    status.update(label=f"Done · {len(tools)} tool call{'s' if len(tools) != 1 else ''}" if tools else "Done",
                  state="complete")
    if ans is not None and not (text or "").strip() and ans.text.strip():
        st.markdown(ans.text)  # nothing streamed (a provider without deltas): show the whole answer at once
    return ans


def setup_card(p):
    """The agent's proposed setup for this person. It is only saved when they press Apply."""
    f = p["focus"]
    with st.container(border=True):
        st.markdown("**Proposed setup for you**")
        st.markdown(f"- **Submarkets:** {', '.join(f['markets']) or 'all of London'}\n"
                    f"- **Measures:** {', '.join(fx.MEASURES[m] for m in f['measures'])}\n"
                    f"- **How much:** {fx.BUDGETS[f['budget']]}\n"
                    f"- **'Why it matters' written for:** {fx.LENSES[f.get('lens', 'team')]}" +
                    "".join(f"\n- **Team alert:** {r['label']} ({r['why']})" for r in p["rules"]))
        st.caption(" ".join(p["reasons"]))
        c = st.columns(3)
        if c[0].button("Apply", type="primary", width="stretch", key="apply_setup"):
            st.session_state["applied_setup"] = fx.apply_setup(app.store, user, p)
            st.session_state.pop("proposal")
            app.store.log("setup", user, "set up their 'For you' view")
            say("assistant", "Applied. Monitor now opens on 'For you'"
                f"{', and ' + str(len(p['rules'])) + ' alert(s) are on the team watchlist' if p['rules'] else ''}. "
                "Tell me what to change, e.g. 'less macro'.")
            st.session_state["undo_ready"] = True
            st.session_state["want_view"] = "For you"  # applied on the next full run, before the toggle exists
            st.session_state["copilot_ctx"] = {"kind": "page", "page": "monitor"}  # back to normal questions
            st.rerun()  # closes the panel so Monitor shows the new 'For you' view
        if c[1].button("Discard", width="stretch", key="discard_setup"):
            st.session_state.pop("proposal")
            st.session_state["copilot_ctx"] = {"kind": "page", "page": "monitor"}
            _rerun()
        if c[2].button("Clear my focus", width="stretch", key="reset_setup"):
            app.store.reset_focus(user)
            st.session_state.pop("proposal")
            say("assistant", "Cleared. You see the team view.")
            st.session_state["copilot_ctx"] = {"kind": "page", "page": "monitor"}
            _rerun()


# ---------------------------------------------------------------- signal card
def signal_chips(s) -> str:
    out = []
    if s.kind == "alert":
        out.append(chip(f"Your alert · {s.title.removeprefix('Alert: ')}", "alert"))
    elif s.metric:
        out.append(chip(tx.METRICS[s.metric]["label"]))
    else:
        out.append(chip(tx.CATEGORY_LABELS.get(s.category, KIND_LABEL.get(s.kind, s.kind))
                        if s.kind == "news" else KIND_LABEL.get(s.kind, s.kind)))
    out += [chip(m) for m in s.markets[:3]]
    if s.flag:
        out.append(chip("Check source", "warn"))
    if s.hot >= 60:
        out.append(f'<span class="loa-chip warn">{ic("flame", 12)}Hot {s.hot}</span>')
    if s.shared_by:
        out.append(chip("Shared by " + ", ".join(x["who"] for x in s.shared_by[:2]), "ok"))
    return "".join(out)


def numbers_line(s) -> str:
    if not (s.before or s.after):
        return ""
    parts = []
    if s.before:
        parts.append(f'<span class="loa-num">{esc(s.before)}</span> &nbsp;→&nbsp; ')
    parts.append(f'<span class="loa-num">{esc(s.after)}</span>')
    if s.change:
        parts.append(f" &nbsp;{esc(s.change)}")
    if s.context:
        parts.append(f' &nbsp;·&nbsp; <span class="loa-muted">{esc(s.context)}</span>')
    return f'<div class="loa-nums">{"".join(parts)}</div>'


def signal_card(s, i, lens="team"):
    in_brief = {b["id"]: b["added_by"] for b in app.store.brief_items()}
    glyph = ic({"up": "arrow-up", "down": "arrow-down"}.get(s.direction, "arrow-right"), 14)
    cls = "alert" if s.kind == "alert" else {"positive": "pos", "negative": "neg"}.get(s.tone, "neu")
    if s.kind == "alert":
        glyph = ic("bell", 14)
    why = esc(s.why)
    if (extra := fx.for_you(s, lens)):
        why += f' <i class="loa-muted">For you: {esc(extra)}</i>'
    if s.hot:
        why += f'<div class="loa-muted">{ic("flame", 13, "amber")}{esc(s.why_hot or "routine")}' \
               + (f" · first seen {esc(s.discovered)} UTC" if s.discovered else "") + "</div>"
    if s.flag:
        why += f'<div class="loa-muted">{ic("triangle-alert", 13, "flag")}{esc(s.flag)}. Anyone can settle it on Sources.</div>'
    with st.container(border=True):
        st.html(f"""
<div style="display:flex;align-items:flex-start;gap:4px">
  <span class="loa-dir {cls}">{glyph}</span>
  <div style="flex:1">
    <div>{signal_chips(s)}</div>
    <div class="loa-title">{esc(s.title)}</div>
    {numbers_line(s)}
    <div class="loa-ink2">{esc(s.detail)}</div>
    <div class="loa-ink2" style="margin-top:6px">{why}</div>
    <div style="margin-top:10px">{"".join(src_chip(e) for e in s.evidence)}</div>
  </div>
</div>""")
        b = st.columns([1.4, 1.6, 0.6, 0.6, 1.6], vertical_alignment="center")
        if b[0].button("Ask Copilot", key=f"ask{i}{s.id}", type="tertiary"):
            open_copilot({"kind": "signal", "title": s.title, "detail": s.detail})
        if s.id in in_brief:
            if b[1].button("In team brief", icon=material("check"), key=f"br{i}{s.id}", type="tertiary",
                           help=f"Added by {in_brief[s.id]}. Click to remove"):
                app.store.remove_from_brief(s.id)
                st.rerun()
        elif b[1].button("Add to brief", key=f"br{i}{s.id}", type="tertiary"):
            app.store.add_to_brief(s.to_dict(), user)
            app.store.log("brief", user, f"added '{s.title}' to the team brief")
            st.rerun()
        if b[2].button("", icon=material("thumbs-up"), key=f"up{i}{s.id}", type="tertiary", help="Useful: rank more like this higher for you"):
            app.store.add_feedback(s.id, user, 1)
            st.toast("Thanks, noted.")
        if b[3].button("", icon=material("thumbs-down"), key=f"dn{i}{s.id}", type="tertiary", help="Not relevant to me: hide it from my views"):
            app.store.add_feedback(s.id, user, -1)
            st.toast("Hidden for you. The rest of the team still sees it.")
            st.rerun()
        if s.obs_id and not s.flag:
            with b[4].popover("Looks wrong", icon=material("triangle-alert"), help="Flag this number for the team. It stays usable with a warning "
                                                     "until someone checks it."):
                why_txt = st.text_input("What looks wrong?", key=f"why{i}{s.id}",
                                        placeholder="Doesn't match the PDF; looks like the City figure")
                if st.button("Flag for the team", key=f"flag{i}{s.id}", type="primary"):
                    app.store.flag_observation(s.obs_id, why_txt or "Looks wrong", user)
                    app.store.log("flag", user, f"flagged '{s.title}': {why_txt or 'looks wrong'}")
                    st.rerun()


# ---------------------------------------------------------------- monitor side panels
def share_panel():
    """Anyone can drop in a link or something they heard. The agent files it: reads the link, classifies it,
    merges it with the same story if the team has it, credits the colleague and scores how hot it is."""
    with st.container(border=True):
        st.html(f'<div class="loa-h2" style="font-size:17px">{ic("megaphone", 16, "accent")}Share a link or tip</div>')
        st.caption("Paste a link or write what you heard. It goes into the team inbox; the agent files it with "
                   "your name and merges it if a colleague shared the same thing.")
        with st.form("share", clear_on_submit=True, border=False):
            text = st.text_area("What did you see or hear?", height=70, label_visibility="collapsed",
                                placeholder="e.g. A broker told me 1 Triton Square has another floor under offer…")
            url = st.text_input("Link (optional)", placeholder="https://…")
            how = st.selectbox("Source", gather.HOW)
            sent = st.form_submit_button("Share with the team", type="primary", width="stretch")
        if sent and (text.strip() or url.strip()):
            app.store.add_to_inbox(text.strip(), url.strip(), how, user)
            with st.spinner("Reading, checking for the same story, scoring…"):
                try:
                    st.success(engine.gather(user).text or "Shared. The information agent filed it; see team activity.")
                except AgentUnavailable as e:
                    st.info(f"Saved to the team inbox. The information agent files it on its next round. ({e})")
        shared = [n for n in app.store.news() if n.shared_by][:3]
        for n in shared:
            who = n.shared_by[0]
            st.html(f'<div style="margin-top:8px"><b>{esc(n.title)}</b><div class="loa-muted">Shared by '
                    f'{esc(who["who"])} ({esc(who["how"]).lower()}) · {esc(", ".join(n.markets[:1]) or "London")} · '
                    f'{esc(lib.when(who.get("when")))}</div></div>')


def watching_panel():
    with st.container(border=True):
        st.html('<div class="loa-h2" style="font-size:17px">Watching for the team</div>')
        fired = {s.title for s in signals.watch_alerts("team")}
        rules = app.store.watch_rules("team")
        if not rules:
            st.caption("No rules yet. Add one below in your own words.")
        for rr in rules:
            on = f"Alert: {rr['label']}" in fired
            c = st.columns([5, 1.2], vertical_alignment="center")
            c[0].html(f'<span class="loa-dot {"red" if on else "green"}"></span><b>{esc(rr["label"])}</b>'
                      f'<div class="loa-muted" style="margin-left:17px">{"Fired" if on else "Not triggered"}'
                      + (f" · added by {esc(rr['author'])}" if rr.get("author") else "") + "</div>")
            if c[1].button("Remove", key=f"del{rr['id']}", type="tertiary"):
                app.store.delete_watch_rule(rr["id"])
                st.rerun()
        st.html(kicker("Add a rule in your own words"))
        c = st.columns([3, 1.1], vertical_alignment="bottom")
        text = c[0].text_input("Rule", placeholder="Alert me when City & Southbank vacancy goes above 9%",
                               label_visibility="collapsed", key="rule_text")
        save = c[1].button("Save", width="stretch", type="primary", key="rule_save")
        rule = parse_rule(text) if text else None
        if text and rule:
            st.html(f"""<div style="display:flex;gap:8px;flex-wrap:wrap">
<div class="loa-box" style="flex:1"><div class="k">Measure</div><div class="v">{esc(tx.METRICS[rule['metric']]['label'])}</div></div>
<div class="loa-box" style="flex:1"><div class="k">Submarket</div><div class="v">{esc(rule['market'])}</div></div>
<div class="loa-box" style="flex:1"><div class="k">Condition</div><div class="v">{'above' if rule['operator'] == '>' else 'below'} {rule['value']:g}</div></div>
</div>""")
            snap = an.snapshot(app.store, rule["market"], rule["metric"])
            if snap:
                now_on = snap["value"] > rule["value"] if rule["operator"] == ">" else snap["value"] < rule["value"]
                src = an.source_ref(app.store, snap.get("source_id", ""))
                st.html(f'{chip("Would fire now" if now_on else "Not triggered now", "alert" if now_on else "ok")} '
                        f'Latest {esc(tx.METRICS[rule["metric"]]["label"].lower())} in {esc(rule["market"])} is '
                        f'<span class="loa-num">{esc(tx.fmt_value(rule["metric"], snap["value"]))}</span> '
                        f'({esc(an.period_label(snap["period"]))}).<div style="margin-top:6px">'
                        + (chip(src["title"], "src auto" if src.get("channel", "auto") == "auto" else "src", src.get("url", ""))
                           if src.get("title") else "") + "</div>")
        elif text:
            st.warning("I couldn't find a market, measure and number in that. Try 'City vacancy above 9%'.")
        if save and rule:
            st.success(app.call("add_watch_rule", rule, user)["summary"])
            app.store.log("alert", user, f"added the alert '{text}'")
            st.rerun()
        st.caption("Fired alerts show on Monitor. Email and Teams delivery come after the PoC.")


def needs_a_person_panel():
    with st.container(border=True):
        st.html(f'<div class="loa-h2" style="font-size:17px">Needs a person'
                + (f'<span class="loa-badge">{to_check}</span>' if to_check else "") + "</div>")
        st.caption("Open data arrives by itself and anyone can upload a report. When figures disagree, anyone on "
                   "the team can settle it; until then they show as flagged.")
        if not to_check:
            st.html(f'{chip("Nothing to check", "ok")}')
        for r in flagged[:3]:
            label = tx.METRICS[r["metric"]]["label"].lower()
            c = st.columns([3, 1.3], vertical_alignment="center")
            c[0].html(f'<span class="loa-dot amber"></span><b style="font-size:14px">{esc(r["market"])} {esc(label)}, '
                      f'{esc(an.period_label(r["period"]))}</b><div class="loa-muted" style="margin-left:17px">'
                      f'{esc(an.warning(r).removeprefix("Flagged: "))}</div>')
            if c[1].button(f"Keep {tx.fmt_value(r['metric'], r['value'])}", key=f"keep{r['rowid']}", width="stretch"):
                app.store.resolve_observation(r["rowid"], user, True)
                app.store.log("resolve", user, f"checked {r['market']} {label}: correct")
                st.rerun()
        for s in checks[:3 - min(3, len(flagged))]:
            c = st.columns([3, 1.3], vertical_alignment="center")
            c[0].html(f'<span class="loa-dot amber"></span><b style="font-size:14px">{esc(s.title)}</b>'
                      f'<div class="loa-muted" style="margin-left:17px">{esc(s.detail)}</div>')
            if c[1].button("Review", key=f"rev{s.id}", width="stretch"):
                open_copilot({"kind": "signal", "title": s.title, "detail": s.detail})
        if st.button("Open Sources", key="open_sources"):
            goto("sources")


def activity_panel():
    with st.container(border=True):
        st.html('<div class="loa-h2" style="font-size:17px">Team activity</div>')
        acts = app.store.activity(8)
        if not acts:
            st.caption("Nothing yet. Questions, uploads, checks, alerts and brief picks from the team show here.")
        for a in acts:
            when = lib.when(a.get("ts"))
            if a["kind"] == "auto":
                st.html(f'<div><span class="loa-dot green"></span>Auto-update: {esc(a["text"])}'
                        f'<div class="loa-muted" style="margin-left:17px">{esc(when)}</div></div>')
            elif a["kind"] == "ask":
                with st.expander(f"{a['author']} asked: {a['text'][:60]}"):
                    st.markdown(a["answer"] or "")
            else:
                dot = '<span class="loa-dot blue" style="margin-right:4px"></span>' if a["kind"] == "internal" else ""
                st.html(f'<div style="display:flex;gap:8px;margin:6px 0"><span class="loa-av">'
                        f'{esc(a["author"][:1].upper())}</span><div>{dot}{esc(a["author"])} {esc(a["text"])}'
                        f'<div class="loa-muted">{esc(when)}</div></div></div>')


def freshness_line():
    """Where the team's data stands, in one strip: open data collected by the agent, the latest report a
    colleague uploaded, when news was checked, what waits for a person, and reports probably out but not uploaded."""
    last = lib.last_auto_update(app.store)
    up = lib.latest_upload(app.store)
    due = [d for d in lib.due_reports(app.store, app.config) if d["missing"]]
    fdue = follow.due_uploads(app.store)
    parts = [f'<span><span class="loa-dot green"></span><b>Auto-updated</b> {esc(lib.when(last["ts"]) if last else "never")}</span>']
    if up:
        parts.append(f'<span><span class="loa-dot orange"></span><b>Uploaded</b> {esc(up["publisher"])} '
                     f'{esc(an.period_label(up["period"]))}, by {esc(up["uploaded_by"])} on {esc(up["uploaded_at"][:10])}</span>')
    else:
        parts.append('<span><span class="loa-dot orange"></span><b>No reports uploaded yet</b></span>')
    if our_deals:
        latest = max((d.get("date") or "" for d in our_deals), default="")
        parts.append(f'<span><span class="loa-dot blue"></span><b>Internal</b> {len(our_deals)} of our deals'
                     + (f', latest {esc(latest)}' if latest else "")
                     + (" · internal only" if all(d.get("confidentiality") != "quotable" for d in our_deals)
                        else f" · {sum(d.get('confidentiality') == 'quotable' for d in our_deals)} quotable") + "</span>")
    else:
        parts.append('<span><span class="loa-dot blue"></span><b>Internal</b> none of our deals recorded yet</span>')
    news = app.store.news()
    if news:
        parts.append(f'<span><b>News</b> {len(news)} items, checked {esc(lib.when(last["ts"]) if last else "never")}</span>')
    if to_check:
        parts.append(f'<span>{ic("triangle-alert", 14, "flag")}<b>{to_check} to check</b> on Sources</span>')
    for d in due:
        parts.append(f'<span>{ic("alarm-clock", 14, "amber")}<b>{esc(d["publisher"])} {esc(an.period_label(d["period"]))}</b> may be out; nobody has uploaded it yet</span>')
    for d in fdue:
        parts.append(f'<span>{ic("alarm-clock", 14, "amber")}<b>{esc(d["name"])}</b> ({esc(d["cadence"])}): no issue uploaded'
                     + (f' since {esc(d["last"])}' if d["last"] else " yet") + "</span>")
    c = st.columns([7, 1], vertical_alignment="center") if (due or fdue) else [st]
    c[0].html(f'<div class="loa-fresh">{"".join(parts)}</div>')
    if due or fdue:
        if c[1].button("Upload it", key="due_upload", type="tertiary"):
            goto("sources", want_lib=LIB_TABS[1])


def summary_card(team_sigs):
    vac = an.snapshot(app.store, "London", "vacancy_pct")
    inv = an.snapshot(app.store, "London", "investment_gbp_bn")
    chips = []
    for snap in (vac, inv):
        if snap and snap.get("source_id"):
            ref = an.source_ref(app.store, snap["source_id"])
            if ref["title"] not in [c[0] for c in chips]:
                chips.append((ref["title"], ref["channel"], ref["url"]))
    with st.container(border=True):
        st.html(kicker("Team summary")
                + f'<div class="loa-prose">{esc(" ".join(team_summary(app.store, team_sigs)))}</div>'
                + '<div style="margin-top:10px">'
                + "".join(chip(t, "src auto" if ch == "auto" else "src", u) for t, ch, u in chips) + "</div>")


def focus_row(mine):
    c = st.columns([5, 1.6], vertical_alignment="center")
    if mine:
        chips = [chip(m) for m in mine["markets"]] + [chip(fx.MEASURES[m]) for m in mine["measures"]] \
                + [chip(fx.BUDGETS[mine["budget"]].split(" (")[0])]
        c[0].html('<span class="loa-kicker" style="margin-right:8px">Your focus</span>' + "".join(chips))
        if c[1].button("Change with Copilot", type="tertiary", key="change_focus"):
            open_copilot({"kind": "setup"})
    else:
        c[0].html('<span class="loa-kicker" style="margin-right:8px">Your focus</span>'
                  '<span class="loa-muted">not set up yet: the team view is shown</span>')
        if c[1].button("Set up my focus", icon=material("sparkles"), type="tertiary", key="setup_focus"):
            open_copilot({"kind": "setup"})


def monitor_page():
    st.session_state["page"] = "monitor"
    page_header("This week in London offices", f"{date.today():%A %-d %b %Y} · shared with the whole team",
                (f"Team brief · {brief_count} signals", "to_brief", "brief"))
    freshness_line()
    hidden = app.store.hidden_signals(user)
    team_sigs = [s for s in signals.for_role("team") if s.id not in hidden]
    main, side = st.columns([2.1, 1], gap="medium")
    with main:
        summary_card(team_sigs)
        mine = my_focus()
        st.session_state.setdefault("view", "For you" if mine else "Whole team")
        if (want := st.session_state.pop("want_view", None)):
            st.session_state["view"] = want
        h = st.columns([3, 2], vertical_alignment="center")
        h[0].html('<div class="loa-h2">Signals</div>')
        with h[1]:
            view = st.segmented_control("Show", ["For you", "Whole team"], key="view", label_visibility="collapsed",
                                        format_func=lambda v: f"Whole team · {len(team_sigs)}" if v == "Whole team" else v)
        focus_row(mine)
        if view == "For you" and mine:
            sigs, lens = signals.for_focus(user, mine), mine.get("lens", "team")
        else:
            if view == "For you":
                st.info("You haven't set up your view yet. Press 'Set up my focus' and describe your job in one "
                        "sentence. Meanwhile, here is the whole team's list.")
            sigs, lens = team_sigs[:8], "team"
        if not sigs:
            st.info("Nothing in your focus changed. Widen it by telling the Copilot, e.g. 'more vacancy'.")
        for i, s in enumerate(sigs):
            signal_card(s, i, lens)
    with side:
        share_panel()
        watching_panel()
        needs_a_person_panel()
        activity_panel()


# ---------------------------------------------------------------- copilot page
def copilot_page():
    st.session_state["page"] = "copilot"
    st.session_state["_in_dialog"] = False
    st.session_state["copilot_ctx"] = {"kind": "page", "page": "copilot"}
    c = st.columns([5, 1.2], vertical_alignment="center")
    c[0].html('<div class="loa-h1">Ask Copilot</div><div class="loa-sub">Judge: ask, compare, drill down. '
              'Every number comes with its source.</div>')
    if c[1].button("Set up my focus", icon=material("sparkles"), width="stretch", key="setup_cp"):
        open_copilot({"kind": "setup"})
    # The input box is made here, at page level, so Streamlit pins it to the bottom of the window.
    question = st.chat_input(chat_placeholder(st.session_state["copilot_ctx"]), key="copilot_input", max_chars=2000)
    copilot_body(full=True, question=question, own_input=False)


# ---------------------------------------------------------------- team brief
DECK_THEMES = {"navy-gold": "Navy & gold · team and board", "editorial-cream": "Editorial cream · research note",
               "data-white": "Data white · IC pack", "charcoal-amber": "Charcoal & amber · on screen",
               "forest-cream": "Forest & cream · client update"}


FORMAT_HELP = {"board": "Board summary: 3-6 slides for a reader with three minutes; headline, the moves that matter, what changed.",
               "ic": "IC paper section: adds the evidence table and groups the signals into supports / risks for the investment committee."}
DECK_MSG = {"copilot": ("Slides chosen by the Copilot", "It read this week's data and picked the slides, layouts and titles."),
            "rules": ("Slides picked by rules (Copilot offline)",
                      "The numbers and sources are the same; only the choice of slides and the titles are standard.")}


def theme_swatches() -> str:
    """Five small colour strips so a theme can be chosen by eye, not by name."""
    th = _bd.build_deck.THEMES
    out = []
    for key, label in DECK_THEMES.items():
        c = th[key]["colors"]
        strip = "".join(f'<span style="display:inline-block;width:14px;height:14px;background:#{c[k]};'
                        f'border:1px solid #ccc;margin-right:-1px"></span>' for k in ("dark", "bg", "accent", "series1"))
        out.append(f'<span style="display:inline-block;margin:0 14px 4px 0;font-size:12px;white-space:nowrap">'
                   f'{strip}&nbsp;{esc(label.split(" · ")[0])}</span>')
    return '<div style="line-height:22px">' + "".join(out) + "</div>"


def deck_key(fmt):
    return f"deck_{fmt}"


def build_deck_now(fmt, theme):
    """The Copilot plans the deck from this week's data; without it the rule planner picks from the same stories.
    Returns (how, note) and leaves the file bytes and the slide reasons in session state."""
    key = deck_key(fmt)
    built, how, note = None, "", ""
    if engine.ready:
        with st.spinner("The Copilot is reading this week's data and planning the slides…"):
            try:
                built, ans = engine.build_deck(fmt, theme, user)
                how, note = "copilot", ans.text
            except AgentUnavailable as e:
                note = str(e)
    if not built:  # fallback: the rule-based planner, still this week's stories, no model
        with st.spinner("Building the slides from this week's data…"):
            out = app.call("build_brief_pptx", {"format": fmt, "theme": theme}, user)
        built, how = out["data"] if out["data"].get("path") else None, "rules"
        if not built:
            st.warning(out["summary"])
            return "", ""
    st.session_state[key] = Path(built["path"]).read_bytes()
    st.session_state[key + "_built"] = theme
    st.session_state[key + "_how"] = (how, note if how == "rules" and note else "")
    st.session_state[key + "_slides"] = [f"{s['title']}" + (f" — {w}" if w else "")
                                         for s, w in zip(built["slides"], built.get("why") or [])]
    st.session_state[key + "_problems"] = built.get("problems") or []
    app.store.log("brief", user, f"built the team brief slides ({fx.BRIEF_FORMATS[fmt].lower()}, {theme}, "
                                 f"{'storyline by the Copilot' if how == 'copilot' else 'rule-picked storyline'})")
    return how, note


def deck_panel(fmt):
    """One place for the slides: theme (with swatches), Build, then Download for the theme that was built.
    A theme change after a build hides the stale download until the deck is built again."""
    key = deck_key(fmt)
    with st.container(border=True):
        st.markdown("**Slides**  ·  " + ("the Copilot reads this week's data and picks the slides, layouts and titles"
                                        if engine.ready else "picked by rules from this week's data (Copilot offline)"))
        c = st.columns([2.4, 1.3, 1.3, 2.6], vertical_alignment="bottom")
        theme = c[0].selectbox("Slide theme", list(DECK_THEMES), format_func=DECK_THEMES.get, key=f"deck_theme_{fmt}",
                               index=list(DECK_THEMES).index("data-white" if fmt == "ic" else "navy-gold"),
                               help="Each format remembers its own theme. IC packs default to Data white.")
        if c[1].button("Build slides", key=f"mk_{key}", width="stretch", type="primary" if not st.session_state.get(key) else "secondary",
                       help="Plans a 3-6 slide deck from this week's data; takes a few seconds"):
            build_deck_now(fmt, theme)
        built_theme = st.session_state.get(key + "_built")
        if st.session_state.get(key) and built_theme == theme:
            c[2].download_button("Download .pptx", st.session_state[key],
                                 file_name=f"london-office-team-brief-{fmt}-{built_theme}.pptx",
                                 mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                 key=f"dl_{key}", width="stretch", type="primary")
            how, note = st.session_state.get(key + "_how") or ("", "")
            with c[3]:
                if how:
                    label, plain = DECK_MSG[how]
                    st.html(chip(label, "ok" if how == "copilot" else "warn")
                            + f'<div class="loa-muted">{esc(plain)}</div>'
                            + (f'<div class="loa-muted">{esc(note)}</div>' if note else ""))
                with st.popover("Why these slides"):
                    st.caption(f"{fx.BRIEF_FORMATS[fmt]} · {DECK_THEMES[built_theme]}")
                    for line in st.session_state.get(key + "_slides") or []:
                        st.markdown(f"- {line}")
            for p in st.session_state.get(key + "_problems") or []:
                st.html(f'<div class="loa-muted">{ic("triangle-alert", 13, "flag")}{esc(p)}</div>')
        elif st.session_state.get(key):
            c[3].html(chip("Theme changed", "warn")
                      + f'<div class="loa-muted">Press Build slides to get {esc(DECK_THEMES[theme].split(" · ")[0])}; '
                        f'the last build was {esc(DECK_THEMES[built_theme].split(" · ")[0])}.</div>')
        else:
            c[3].caption("Five house themes, 13 layouts, every number footnoted and checked against the data.")
        st.html(theme_swatches())


def brief_page():
    st.session_state["page"] = "brief"
    page_header("Team brief", "Built from the signals the team added this week. Every number has a footnote.")
    items = app.store.brief_items()
    if items:
        c = st.columns(2)
        for n, it in enumerate(items):
            r = c[n % 2].columns([6, 1], vertical_alignment="center")
            r[0].html(chip(it["title"]) + f'<span class="loa-muted">added by {esc(it["added_by"])}</span>')
            if r[1].button("", icon=":material/close:", type="tertiary", key=f"rm{it['id']}", help="Remove"):
                app.store.remove_from_brief(it["id"])
                st.session_state.pop("brief", None)
                st.rerun()
    else:
        st.info("Nobody has added signals yet, so the brief uses the team's top signals. Use 'Add to brief' on "
                "Monitor to choose them.")
    if st.button("Add more from Monitor", type="tertiary", key="more_from_monitor"):
        goto("monitor")
    row = st.columns([2.6, 1.3, 1.1, 0.9], vertical_alignment="center")
    with row[0]:
        fmt = st.segmented_control("Write it as", list(fx.BRIEF_FORMATS), default="board",
                                   format_func=fx.BRIEF_FORMATS.get, key="brief_fmt") or "board"
        st.caption(FORMAT_HELP[fmt])
    key = (fmt, tuple(it["id"] for it in items))
    rewrite = row[3].button("Rewrite", icon=material("refresh-cw"), key="rewrite", type="tertiary")
    if st.session_state.get("brief_key") != key or rewrite:
        with st.spinner("Writing the brief…"):
            st.session_state["brief"] = app.call("generate_brief", {"format": fmt}, user)["summary"]
            st.session_state["brief_key"] = key
        if rewrite:
            app.store.log("brief", user, f"rewrote the team brief ({fx.BRIEF_FORMATS[fmt].lower()})")
    brief = st.session_state["brief"]
    with row[1].popover("Copy as Markdown", width="stretch"):
        st.code(brief, language="markdown")
    row[2].download_button("Download (.md)", brief, file_name="london-office-team-brief.md", width="stretch")
    deck_panel(fmt)
    with st.container(border=True):
        st.markdown(re.sub(r"^(#{1,2}) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", brief, flags=re.M))
        chart(app.call("get_metric_trend", {"market": "London", "metric": "vacancy_pct"})["chart"])
    c = st.columns([2.2, 4.8], vertical_alignment="center")
    if c[0].button("Ask Copilot for a custom deck", icon=material("sparkles"), type="tertiary", key="deck_copilot",
                   help="Say who it is for, the theme and what to cover; the Copilot writes the storyline and "
                        "checks every number against the data"):
        open_copilot({"kind": "page", "page": "brief"})
    c[1].caption("For a deck the Build button does not give you, e.g. \"a client update on the forest theme that only "
                 "covers Midtown\". Build slides above is the one-click version.")


# ---------------------------------------------------------------- sources
STATUS = {"verified": "in page text", "image": "image only", "not_found": "not in text (check)",
          "implausible": "outside range (check)"}
FOLLOW_EXAMPLES = ["Follow Savills Market Watch", "Landsec half-year results", "TfL station entries",
                   "https://www.costar.co.uk/news/rss"]
LIB_TABS = ["Collected automatically", "Uploaded reports", "Internal data", "News and tips", "Definitions"]


def overview_cards():
    feeds = lib.feeds(app.store, app.config)
    live = [f for f in feeds if f.get("connector")]
    planned = len(feeds) - len(live)
    due = [d for d in lib.due_reports(app.store, app.config) if d["missing"]]
    c = st.columns(3)
    with c[0], st.container(border=True):
        st.html(f'<div><span class="loa-dot green"></span><b>Collected automatically</b></div>'
                f'<div class="loa-big">{len(live)} live feeds · {planned} planned</div>'
                f'<div class="loa-ink2">{esc(", ".join(sorted({f["publisher"] for f in live if f.get("connector") != "followed_sources"})))}. '
                f'Fetched and read by the agent on a schedule.</div>')
        if st.button("See feeds", type="tertiary", key="see_feeds"):
            st.session_state["want_lib"] = LIB_TABS[0]
            st.rerun()
    with c[1], st.container(border=True):
        st.html('<div><span class="loa-dot orange"></span><b>Uploaded by the team</b></div>'
                '<div class="loa-big">Anyone can upload</div>'
                '<div class="loa-ink2">Agency reports whose licence does not allow automated collection (Knight '
                'Frank, Savills, BNP Paribas…). One person uploads, everyone sees it, labelled with who and when.</div>'
                + "".join(f'<div class="loa-ink2" style="margin-top:6px">{ic("alarm-clock", 14, "amber")}<b>{esc(d["publisher"])} '
                          f'{esc(an.period_label(d["period"]))}</b> may be out; nobody has uploaded it yet.</div>'
                          for d in due))
        if st.button("Upload a report", type="tertiary", key="upload_btn"):
            st.session_state["want_lib"] = LIB_TABS[1]
            st.rerun()
    with c[2], st.container(border=True):
        st.html(f'<div><span class="loa-dot blue"></span><b>Internal data</b></div>'
                f'<div class="loa-big">{len(our_deals)} of our deals</div>'
                '<div class="loa-ink2">Our own lettings, leases and valuations. Any format: a PDF, a photo of a lease '
                'page, an Excel export, or just tell Copilot. Stays inside the company, never mixed with market data.</div>'
                + (f'<div class="loa-ink2" style="margin-top:6px"><b>{len(deal_drafts)} draft</b> with fields still missing '
                   'or waiting for the recorder.</div>' if deal_drafts else ""))
        if st.button("Add one of our deals", type="tertiary", key="internal_btn"):
            st.session_state["want_lib"] = LIB_TABS[2]
            st.rerun()


def gathering_card():
    last = lib.last_auto_update(app.store)
    with st.container(border=True):
        c = st.columns([4, 1.6], vertical_alignment="center")
        c[0].html(f'<b>{ic("search", 15, "accent")}Gathering round</b> <span class="loa-muted">runs daily · last '
                  f'{esc(lib.when(last["ts"]) if last else "never")}</span>'
                  '<div class="loa-ink2">One scheduled run: process what the team shared, collect open data, look '
                  'for new agency reports by title (never downloading them), classify news.</div>')
        if c[1].button("Run a gathering round", type="primary", width="stretch", key="run_round"):
            with st.spinner("Gathering…"):
                try:
                    st.session_state["round"] = engine.gather(user)
                except AgentUnavailable as e:
                    st.session_state["round_err"] = (str(e), e.detail)
        if (err := st.session_state.pop("round_err", None)):
            st.warning(err[0])
            if err[1]:
                with st.expander("Technical details"):
                    st.code(err[1], language=None)
        if (rnd := st.session_state.get("round")):
            st.info(rnd.text)
            with st.expander("Technical details"):
                st.caption(f"Engine: {rnd.engine}")


def add_source_card():
    """Anyone adds a source for the whole team. The agent checks its terms and picks the channel."""
    with st.container(border=True):
        st.html(f'<b>{ic("plus", 15, "accent")}Add a source for the team</b><div class="loa-ink2">Paste a link or name what '
                f'you want followed. The agent checks its terms, then either collects it automatically ({tier("open", "Open data")}) '
                f'or reminds the team to upload each new issue ({tier("upl", "Uploaded")}). Everyone gets it.</div>')
        c = st.columns([4, 1.4, 1.3], vertical_alignment="bottom")
        src = c[0].text_input("Link or name", key="follow_src", label_visibility="collapsed",
                              placeholder="e.g. Follow Savills Market Watch, or paste a link")
        cadence = c[1].selectbox("New issues", ["(guess)", *follow.CADENCE_DAYS], label_visibility="collapsed")
        check = c[2].button("Check source", type="primary", width="stretch", key="follow_go")
        ex = st.columns(len(FOLLOW_EXAMPLES))
        for i, e in enumerate(FOLLOW_EXAMPLES):
            if ex[i].button(e, key=f"fx{i}", type="tertiary"):
                src, check = e, True
        if check and src.strip():
            with st.spinner("Checking robots.txt and the terms…"):
                args = {"source": src.strip(), "propose": True, **({} if cadence == "(guess)" else {"cadence": cadence})}
                out = app.call("follow_source", args, user)
            st.session_state.pop("followed", None)
            if "chain" in out["data"]:
                st.session_state["follow_plan"] = out["data"]
            else:
                st.session_state["followed"] = out["summary"]  # e.g. no link found for a name
        if (p := st.session_state.get("follow_plan")):
            follow_card(p)
        if (msg := st.session_state.get("followed")):
            st.info(msg)
        rows = app.store.q("SELECT * FROM followed ORDER BY ts DESC")
        if rows:
            st.html(kicker("Sources the team follows"))
            st.dataframe(pd.DataFrame([{"Source": r["name"], "How": "Open data, automatic" if r["channel"] == "auto" else "Uploaded by the team",
                                        "Cadence": r["cadence"], "Why": r["licence"], "Added by": r["added_by"],
                                        "When": r["ts"][:10], "Link": r["url"]} for r in rows]),
                         width="stretch", hide_index=True,
                         column_config={"Link": st.column_config.LinkColumn("Link", display_text="open")})


def follow_card(p):
    """The agent's plan for a new source, shown before anyone adds it for the whole team."""
    with st.container(border=True):
        auto = p["channel"] == "auto"
        st.html(f'<b>Proposal: follow {esc(p["name"])}</b> '
                + chip("Collected automatically" if auto else "Upload each issue", "ok" if auto else "warn")
                + chip(p["cadence"]) + "".join(chip(c) for c in p["chain"]))
        st.markdown(f"- **Licence:** {p['licence']}. {p['reason']}" + (f' _"{p["quote"]}"_' if p.get("quote") else "")
                    + f"\n- **How it is read:** {p['how']}\n- **What it adds:** {p['adds']}")
        c = st.columns([2, 1, 3])
        if c[0].button("Add for the team", type="primary", width="stretch", key="follow_add"):
            args = {"source": p["url"], "name": p["name"], "cadence": p["cadence"], **p.get("evidence", {})}
            st.session_state["followed"] = app.call("follow_source", args, user)["summary"]
            st.session_state.pop("follow_plan")
            st.rerun()
        if c[1].button("Cancel", width="stretch", key="follow_cancel"):
            st.session_state.pop("follow_plan")
            st.rerun()


def agent_card():
    n_pdf = len(app.store.uploads())
    n_news = len(app.store.news())
    n_feeds = sum(1 for f in lib.feeds(app.store, app.config) if f.get("connector"))
    n_web = len(app.store.q("SELECT 1 FROM followed WHERE channel='auto'"))
    skills = app.info_manifest()["skills"]
    with st.container(border=True):
        st.html(f'<b>{ic("bot", 15, "accent")}One information-processing agent</b><div class="loa-ink2">The same agent collects and reads '
                'everything: PDFs, web pages, news, spreadsheets and data feeds. It picks the skills each input '
                'needs, so a new kind of source needs a new skill, not a new pipeline.</div><div style="margin-top:8px">'
                + chip(f"This week: {n_pdf} PDFs") + chip(f"{n_news} news items") + chip(f"{n_feeds} data feeds")
                + chip(f"{n_web} web pages followed") + "</div>")
        with st.expander(f"Skills it uses ({len(skills)})"):
            st.markdown("\n".join(f"- **{s['name']}**: {s['description']}" for s in skills))


def needs_a_person():
    with st.container(border=True):
        st.html('<div class="loa-h2" style="font-size:18px">Needs a person'
                + (f'<span class="loa-badge">{to_check}</span>' if to_check else "") + "</div>")
        st.caption("Shared with the whole team: anyone can settle these, and who did it shows in team activity.")
        pending = st.session_state.get("analysis")
        if pending:
            st.warning(f"Your upload of {pending['publisher']} is read but not published yet: see the Uploaded reports tab.")
        if not checks and not flagged and not pending and not deal_drafts:
            st.html(chip("Nothing to check", "ok"))
        if deal_drafts:
            mine = [d for d in deal_drafts if any(w == user for w, _, _ in d.get("recorded_by", []))]
            with st.expander(f"Internal: {len(deal_drafts)} of our deal record(s) to confirm"
                             + (f" ({len(mine)} recorded by you)" if mine else ""), expanded=bool(mine)):
                st.caption("The recorder confirms their own record by default; anyone can, and it shows in team activity. "
                           "Drafts are never listed in the brief.")
                for d in deal_drafts:
                    deal_card(d, key="needs")
        by_source: dict[str, list[dict]] = {}
        for f in flagged:
            by_source.setdefault(f["source_id"], []).append(f)
        for sid, rows in by_source.items():
            src = rows[0]
            with st.expander(f"{len(rows)} figure(s) to check from {src['title'] or sid} "
                             f"({an.provenance(src)})", expanded=len(by_source) == 1):
                for r in rows:
                    c = st.columns([5, 1, 1], vertical_alignment="center")
                    c[0].markdown(f"**{r['market']} {tx.METRICS[r['metric']]['label'].lower()}** "
                                  f"{tx.fmt_value(r['metric'], r['value'])} ({an.period_label(r['period'])})  \n"
                                  f":gray[{an.warning(r).removeprefix('Flagged: ')}]")
                    if c[1].button("Right", icon=material("check"), key=f"ok{r['rowid']}", help="Checked against the report: keep it"):
                        app.store.resolve_observation(r["rowid"], user, True)
                        app.store.log("resolve", user, f"checked {r['market']} {tx.METRICS[r['metric']]['label'].lower()} "
                                      f"({src['publisher']}): correct")
                        st.rerun()
                    if c[2].button("Wrong", icon=material("x"), key=f"no{r['rowid']}", help="Remove it from the library for everyone"):
                        app.store.resolve_observation(r["rowid"], user, False)
                        app.store.log("resolve", user, f"removed {r['market']} {tx.METRICS[r['metric']]['label'].lower()} "
                                      f"({src['publisher']}): wrong")
                        st.rerun()
        for s in checks:
            st.html(f'<span class="loa-dot amber"></span><b>{esc(s.title)}</b>'
                    f'<div class="loa-ink2" style="margin-left:17px">{esc(s.detail)}<br>'
                    f'<span class="loa-muted">{esc(s.why)}</span></div>')
            c = st.columns([1.2, 1.2, 4])
            if c[0].button("Mark checked", key=f"chk{s.id}", type="tertiary"):
                app.store.mark_checked(s.id, user)
                app.store.log("resolve", user, f"checked '{s.title}'")
                st.rerun()
            if c[1].button("Ask Copilot", key=f"askchk{s.id}", type="tertiary"):
                open_copilot({"kind": "signal", "title": s.title, "detail": s.detail})


def feeds_tab():
    st.caption("Open data the agent collects by itself, because the licence allows it. A daily timer on the "
               "server runs it, and the app also collects on start-up if the last run is over "
               f"{app.config.get('auto_update_hours', 24)} hours old. Planned feeds are not built in this proof of concept.")
    if st.button("Check for new data now", icon=material("refresh-cw"), key="refresh_now"):
        with st.spinner("Collecting open data…"):
            reports = app.refresh(by=f"Auto-update (run by {user})")
        for r in reports:
            st.toast(f"{r['connector']}: {'failed' if r.get('error') else r['counts']}")
        st.rerun()
    df = pd.DataFrame([{"Feed": f["name"], "What": f.get("what", ""), "Licence": f["licence"], "Updates": f["cadence"],
                        "Last collected": f["last"], "Next": f["next"], "Status": f["status"]}
                       for f in lib.feeds(app.store, app.config)])
    st.dataframe(df, width="stretch", hide_index=True)


def upload_section():
    st.caption("For reports whose terms bar automated collection or AI use (Knight Frank, Savills, BNP Paribas…): "
               "anyone on the team uploads the PDF they can access. The agent turns each data page into an image, "
               "reads it with the vision model and checks every figure against the page text, a plausible range and "
               "what the library already holds. Figures that pass are shared as they are; the rest are shared "
               "as flagged until anyone checks them. Unticked figures are dropped.")
    up = st.file_uploader("PDF report", type=["pdf"])
    sample = app.root / "reference" / "samples" / "sample_bnp_paribas_q2_2025_restated.pdf"
    use_sample = sample.exists() and st.button("Try the sample (BNP Paribas Q2 2025, restated)")
    path = None
    if up:  # kept under data/uploads so page screenshots and re-reads work after a restart
        folder = app.root / "data" / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{hashlib.sha256(up.getvalue()).hexdigest()[:12]}-{Path(up.name).name}"
        path.write_bytes(up.getvalue())
    elif use_sample:
        path = sample
    if path:
        h = documents.file_hash(path)
        if h != st.session_state.get("read_hash"):  # read each file once, not on every rerun
            st.session_state["read_hash"] = h
            st.session_state.pop("analysis", None)
            st.session_state["dup"] = documents.duplicate_of(app.store, path)
            st.session_state["dup_path"] = str(path)
            if not st.session_state["dup"]:
                read_report(path)
    if (dup := st.session_state.get("dup")):
        st.info(f"**{dup['uploaded_by'] or 'A colleague'}** already uploaded {dup['publisher']} "
                f"{an.period_label(dup['period'] or '')} on {dup['uploaded_at'][:10]}. It is in the team library, so "
                "nothing was added again.")
        if st.button("It's a different report: read it anyway"):
            st.session_state.pop("dup")
            read_report(st.session_state["dup_path"])
            st.rerun()
    if (note := st.session_state.pop("agent_note", None)):
        st.info(note)
    analysis = st.session_state.get("analysis")
    if analysis:
        review_upload(analysis)


def read_report(path):
    with st.spinner("The information agent is reading the report: dedupe → read-pdf → map-submarkets → "
                    "check-figures…"):
        try:
            analysis, chain, how = engine.read_upload(path, user)
        except AgentUnavailable as e:
            st.session_state["agent_note"] = str(e)
            return
    if analysis:
        st.session_state["analysis"] = {**analysis, "steps": chain or analysis.get("steps", []), "engine": how}
    else:
        st.session_state["agent_note"] = how  # e.g. the agent found it is a duplicate


def review_upload(analysis):
    cands = analysis["candidates"]
    passed = sum(c.get("suggest_keep", True) for c in cands)
    if analysis.get("steps"):
        st.html(kicker("Skills used") + "".join(chip(x) for x in analysis["steps"]))
    st.markdown(f"**{analysis['publisher']}**, period **{an.period_label(analysis['period'] or '?')}**, "
                f"{len(cands)} figures from {analysis.get('pages', '?')} page(s), read with {analysis['method']}. "
                f"**{passed}** passed every check; **{len(cands) - passed}** will be shared as flagged unless you check "
                "them now.")
    rows = [{"keep": True, "I checked it": False,
             "on publish": "shared" if c.get("suggest_keep", True) else "shared, to check",
             "page": c.get("page"), "check": STATUS.get(c.get("status"), ""),
             "market": c["market"], "as written": c["market_text"],
             "metric": tx.METRICS[c["metric"]]["label"], "value": tx.fmt_value(c["metric"], c["value"]),
             "already held": (f"{tx.fmt_value(c['metric'], c['stored']['value'])} ({c['stored']['publisher']})"
                              if c["stored"] else "-"),
             "flags": " ".join(c["flags"]) or "none"} for c in cands]
    edited = st.data_editor(pd.DataFrame(rows), disabled=[k for k in rows[0] if k not in ("keep", "I checked it")]
                            if rows else True, width="stretch", hide_index=True, key="upload_table")
    # Figures read from charts or not found in the text: show the page so a person can check by eye.
    pages = sorted({c["page"] for c in cands if c.get("page") and c.get("status") != "verified"})
    for n in pages:
        with st.expander(f"Page {n}: check {sum(c.get('page') == n and c.get('status') != 'verified' for c in cands)} "
                         "figure(s) against the page"):
            st.image(documents.page_png(analysis["file"], n, 1400), width="stretch")
    c = st.columns([2, 1, 3])
    if c[0].button("Publish to the team", type="primary", width="stretch"):
        keep = [i for i, k in enumerate(edited["keep"]) if k]
        mine = [i for i, k in enumerate(edited["I checked it"]) if k]
        res = documents.save_document(app.store, analysis, keep, mine, user=user)
        app.store.log("upload", user, f"uploaded {analysis['publisher']} {an.period_label(analysis['period'] or '')}: "
                      f"{res['saved']} figures added, {res['flagged']} to check")
        st.session_state.pop("analysis")
        st.toast(f"Shared {res['saved']} figures with the team ({res['flagged']} flagged).")
        st.rerun()
    if c[1].button("Discard", width="stretch"):
        st.session_state.pop("analysis")
        st.rerun()


def uploads_list():
    st.html(kicker("Reports in the library"))
    ups = app.store.uploads()
    if not ups:
        st.caption("None yet.")
        return
    st.dataframe(pd.DataFrame([{"Report": u["title"], "Period": an.period_label(u["period"] or ""),
                                "Uploaded by": u["uploaded_by"], "When": (u["uploaded_at"] or "")[:16],
                                "Figures": int(u["figures"] or 0), "To check": int(u["to_check"] or 0)} for u in ups]),
                 width="stretch", hide_index=True)


DEAL_IN = {"say": "Tell Copilot", "photo": "Photo", "pdf": "PDF", "xlsx": "Excel / CSV"}


def deal_card(d: dict, key: str = "lib", compact: bool = False):
    """One internal record: the eight fields (missing ones marked), who recorded it, confirm / quoting toggle, originals."""
    draft = d.get("status") != "confirmed"
    status = chip("Draft · fields missing" if d.get("missing") else "Draft · to confirm", "warn") if draft else chip("Confirmed", "ok")
    level = chip(I.LEVELS[d.get("confidentiality", "internal")], "int")
    fields = "".join(f'<div><small>{esc(I.LABELS[k])}</small>{esc(d[k]) if d.get(k) else "<span class=empty>missing</span>"}</div>'
                     for k in I.FIELDS if k != "property")
    by = "; ".join(f"{esc(w)} ({esc(h)}, {esc(t)})" for w, h, t in d.get("recorded_by", []))
    ext = f'<div class="loa-box" style="margin-top:6px">{ic("triangle-alert", 13, "flag")}{esc(d["ext"]["text"])}</div>' if d.get("ext") else ""
    st.html(f'<div class="loa-deal"><div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap">'
            f'<b>{esc(d["property"])}</b> {chip(d["submarket"]) if d.get("submarket") else ""}<span>{status} {level}</span></div>'
            f'<div class="loa-fields">{fields}</div><div class="loa-muted" style="margin-top:6px">Recorded by {by}'
            f' · confidence {esc(d.get("confidence", "high"))}</div>{ext}</div>')
    if compact:
        return
    c = st.columns([1.2, 1.9, 1.8, 3], vertical_alignment="center")
    if draft and c[0].button("Confirm", icon=material("check"), key=f"cf_{key}_{d['id']}", type="tertiary",
                             help="The recorder (or anyone) says the record is right"):
        I.confirm(app.store, d["id"], user)
        app.store.log("internal", user, f"confirmed our record for {d['property']}")
        st.rerun()
    quot = d.get("confidentiality") == "quotable"
    if c[1].button("Mark internal only" if quot else "Allow external quoting", key=f"cq_{key}_{d['id']}", type="tertiary"):
        I.set_confidentiality(app.store, d["id"], "internal" if quot else "quotable", user)
        app.store.log("internal", user, f"marked our record for {d['property']} {'internal only' if quot else 'quotable'}")
        st.toast("Internal only. Filtered out of anything exported." if quot
                 else "Can now be quoted in the IC paper and externally.")
        st.rerun()
    if d.get("originals"):
        with c[2].popover(f"View originals ({len(d['originals'])})"):
            for o in d["originals"]:
                p = Path(o)
                if p.exists() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    st.image(str(p), caption=p.name, width="stretch")
                elif p.exists() and p.suffix.lower() == ".pdf":
                    st.image(documents.page_png(p, 1, 1200), caption=p.name, width="stretch")
                else:
                    st.caption(p.name)
    elif draft and d.get("missing"):
        c[2].caption("Add a photo or a sentence to fill the gaps")


def record_file(path: Path, how: str, hint: str = ""):
    """The Sources-page intake for a photo, PDF or spreadsheet: the same Python the information agent uses."""
    if how == "spreadsheet":
        out = app.call("deals_from_table", {"path": str(path)}, user)
        st.session_state["deal_note"] = out["summary"]
        return
    read = app.call("read_photo", {"path": str(path), "hint": hint}, user)
    fields = (read["data"] or {}).get("fields") or {}
    if hint:
        said = I.parse_deal_text(hint)
        fields = {**{k: v for k, v in said.items() if v}, **{k: v for k, v in fields.items() if v}}
    if not fields.get("property"):
        st.session_state["deal_note"] = (read["summary"] + " Say which building it is in the box above and drop the file again.")
        return
    out = app.call("save_internal_deal", {"fields": fields, "how": how, "original": str(path),
                                          "confidence": (read["data"] or {}).get("confidence", "medium")}, user)
    st.session_state["deal_note"] = read["summary"] + "\n\n" + out["summary"]


def internal_tab():
    st.caption("Our own lettings, leases and valuations. Any format goes through the same agent and comes out as one "
               "deal record; bits can arrive separately and are merged by property and floor. Records stay inside the "
               "company and are listed apart from market data in the brief.")
    with st.container(border=True):
        st.html('<div class="loa-h2" style="font-size:17px"><span class="loa-dot blue"></span>Add one of our deals</div>')
        how = st.segmented_control("How", list(DEAL_IN), default="say", format_func=DEAL_IN.get, key="deal_in",
                                   label_visibility="collapsed") or "say"
        if how == "say":
            with st.form("deal_say", clear_on_submit=True, border=False):
                c = st.columns([5, 1], vertical_alignment="bottom")
                text = c[0].text_input("Tell Copilot", placeholder="e.g. 8 Bishopsgate 12th floor just let at £72.50, "
                                       "10-year term, 24 months rent-free", label_visibility="collapsed")
                if c[1].form_submit_button("Record it", width="stretch", type="primary") and text.strip():
                    out = app.call("record_deal", {"text": text.strip()}, user)
                    st.session_state["deal_note"] = out["summary"]
                    st.rerun()
        else:
            hint = st.text_input("Anything to add (optional)", placeholder="e.g. this is the 12th floor at 8 Bishopsgate",
                                 key=f"deal_hint_{how}")
            types = {"photo": ["png", "jpg", "jpeg", "webp"], "pdf": ["pdf"], "xlsx": ["xlsx", "xls", "csv"]}[how]
            up = st.file_uploader({"photo": "Photo of the lease front page or a WhatsApp screenshot",
                                   "pdf": "Signed lease or heads of terms", "xlsx": "Deals spreadsheet export"}[how],
                                  type=types, key=f"deal_up_{how}")
            sample = app.root / "reference" / "samples" / "lease_front_page_8_bishopsgate.jpg"
            path = None
            if up:
                folder = app.root / "data" / "internal"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{hashlib.sha256(up.getvalue()).hexdigest()[:12]}-{Path(up.name).name}"
                path.write_bytes(up.getvalue())
            elif how == "photo" and sample.exists() and st.button("Try the sample photo (8 Bishopsgate lease page)"):
                path = sample
            if path and str(path) != st.session_state.get("deal_read"):
                st.session_state["deal_read"] = str(path)
                with st.spinner("read-photo: the vision model is reading the image…" if how != "xlsx"
                                else "read-table: reading the rows…"):
                    record_file(path, {"photo": "photo", "pdf": "PDF", "xlsx": "spreadsheet"}[how], hint)
                st.rerun()
        st.html('<div class="loa-muted" style="margin-top:4px">Any format → agent extracts a deal record → draft if fields '
                'are missing → recorder confirms → internal, visible to the team</div>')
        if (note := st.session_state.pop("deal_note", None)):
            st.info(note)
    deals = app.store.internal_deals()
    st.html(kicker(f"Our deals · {len(deals)} records · {sum(d.get('status') != 'confirmed' for d in deals)} draft · "
                   "never mixed with market data"))
    if not deals:
        st.caption("None yet.")
    for d in deals:
        deal_card(d)


def sources_page():
    st.session_state["page"] = "sources"
    page_header("Sources", "Where the team's numbers come from. Open data arrives by itself; agency reports are "
                           "uploaded once, by anyone on the team, for everyone; our own deals stay internal and separate.")
    st.html(f'<div class="loa-banner"><span style="margin-right:12px">{avatars(colleagues(), user)}</span>'
            f'<b>One shared library, three kinds of source.</b> {tier("open", "Open data")}, public and collected automatically · '
            f'{tier("upl", "Uploaded")} external reports · {tier("int", "Internal")}, our own deals and leases, never mixed with market data. Anyone can upload, record a '
            'deal, settle a conflict or flag a number; it all feeds Monitor, Copilot and the team brief.</div>')
    overview_cards()
    gathering_card()
    add_source_card()
    agent_card()
    needs_a_person()
    if (want_lib := st.session_state.pop("want_lib", None)):
        st.session_state["lib_tab"] = want_lib
    t = dict(zip(LIB_TABS, st.tabs(LIB_TABS, key="lib_tab", on_change="rerun")))
    with t[LIB_TABS[0]]:
        feeds_tab()
    with t[LIB_TABS[1]]:
        upload_section()
        uploads_list()
    with t[LIB_TABS[2]]:
        internal_tab()
    with t[LIB_TABS[3]]:
        st.caption("Incoming news and colleagues' tips, classified by category, submarket, theme, sentiment and "
                   "importance. The same story from several outlets or colleagues is merged, with everyone credited.")
        rows = [{"Hot": n.hot, "Story": n.title, "Category": tx.CATEGORY_LABELS.get(n.category, n.category),
                 "Markets": ", ".join(n.markets[:2]), "Source": n.source,
                 "Shared by": ", ".join(f"{x['who']} ({x['how']})" for x in n.shared_by),
                 "Also reported by": ", ".join(r["source"] for r in n.also_reported),
                 "Why hot": n.why_hot, "Published": n.published} for n in app.store.news()]
        if rows:
            st.dataframe(pd.DataFrame(rows).sort_values("Hot", ascending=False), width="stretch", hide_index=True)
        else:
            st.caption("No news yet.")
    with t[LIB_TABS[4]]:
        st.caption("Every figure links back to one of these. Definition notes explain breaks between publishers "
                   "or editions.")
        src = pd.DataFrame(app.store.sources().values())
        st.dataframe(src.drop(columns=["file_hash"], errors="ignore"), width="stretch", hide_index=True)


# ---------------------------------------------------------------- navigation (left, like the prototype)
PAGE_OBJ = {
    "monitor": st.Page(monitor_page, title="Monitor", icon=material("activity"), default=True),
    "copilot": st.Page(copilot_page, title="Ask Copilot", icon=material("message-square"), url_path="copilot"),
    "brief": st.Page(brief_page, title=f"Team brief · {brief_count}" if brief_count else "Team brief", icon=material("file-text"),
                     url_path="brief"),
    "sources": st.Page(sources_page, title=f"Sources · {to_check} to check" if to_check else "Sources", icon=material("database"),
                       url_path="sources"),
}
nav = st.navigation(list(PAGE_OBJ.values()), position="hidden")
sidebar()
nav.run()
