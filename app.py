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

import copy
import hashlib
import html
import json
import re
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from core import analytics as an
from core import preview as _preview
from core import deck_edit as _de
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
from skills.market_brief import report as _report
from core.signals import SignalEngine
from core.summary import is_tip, team_summary
from skills.watchlist_alerts.tools import parse_rule

HERE = Path(__file__).resolve().parent
if not (HERE / "assets").is_dir():  # run through a launcher elsewhere: the project is the working directory
    HERE = Path.cwd()
BRAND = HERE / "assets" / "brand"  # the app logo (direction A, skyline) and the Nan Fung co-brand; see assets/brand/README.md
st.set_page_config(page_title="London Office Market Agent", page_icon=str(BRAND / "favicon-32.png"), layout="wide")
KIND_LABEL = {"metric_move": "Market data", "vs_long_term": "vs long-term average", "news": "News",
              "pipeline": "New supply", "macro": "Macro", "data_quality": "Data check", "alert": "Your alert"}
KIND_FOLD = {"metric_move": "Market data", "vs_long_term": "vs long-term average", "pipeline": "New supply",
             "macro": "Macro", "data_quality": "Figures to check", "flight_to_quality": "Grade A vs the rest",
             "demand": "Demand and liquidity", "alert": "Alerts"}
NOT_PEOPLE = {"auto", "cli", "scheduler", "guest", "agent", "team", "poc seed", "auto-update"}

# ---------------------------------------------------------------- look (from the prototype)
# The Copilot conversation follows ChatGPT's layout (research/copilot-chat-layout.md): a fixed top bar, a centred
# scrolling thread, a fixed chat box; SCOPE is the page or the side panel.
CHAT_CSS = r"""
/* Copilot thread (SCOPE): no avatars; the reader's question is a light bubble on the right, the answer is plain text */
SCOPE [data-testid="stChatMessageAvatarUser"], SCOPE [data-testid="stChatMessageAvatarAssistant"],
SCOPE [data-testid="stChatMessageAvatarCustom"] { display:none; }
SCOPE [data-testid="stChatMessage"] { background:transparent; padding:0; gap:0; margin:0 0 20px 0; }
SCOPE [data-testid="stChatMessage"]:last-child { margin-bottom:0; }
SCOPE [data-testid="stChatMessage"]:has(> [data-testid="stChatMessageAvatarUser"]) { justify-content:flex-end; margin-bottom:12px; }
SCOPE [data-testid="stChatMessage"]:has(> [data-testid="stChatMessageAvatarUser"]) > [data-testid="stChatMessageContent"]
  { flex:0 1 auto; max-width:75%; background:var(--sunk); color:var(--ink); border-radius:18px; padding:10px 16px; }
SCOPE [data-testid="stChatMessageContent"] { width:100%; }
SCOPE [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] { font-size:16px; line-height:1.65; color:var(--ink); }
SCOPE [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] p { font-size:16px; line-height:1.65; }
SCOPE [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] table { display:block; overflow-x:auto; max-width:100%; }
/* the work line above an answer ("Worked through 3 steps", or the live status): a quiet line, no box */
SCOPE [data-testid="stChatMessage"] [data-testid="stExpander"] details { border:none; background:transparent; }
SCOPE [data-testid="stChatMessage"] [data-testid="stExpander"] summary { padding:2px 0; font-size:13px; color:var(--ink3); }
SCOPE [data-testid="stChatMessage"] [data-testid="stExpander"] summary:hover { color:var(--ink); }
SCOPE [data-testid="stChatMessage"] [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] p { font-size:13px; color:inherit; }
SCOPE [data-testid="stChatMessage"] [data-testid="stExpanderDetails"] { padding:0 0 4px 0; }
/* sources line under an answer */
SCOPE .loa-srcs { border-top:1px solid var(--line); margin-top:10px; padding-top:8px; font-size:12px; color:var(--ink3); }
SCOPE .loa-srcs > span { margin-right:6px; }
/* action row: 32px borderless icon buttons; the latest answer's row stays, older rows appear on hover */
SCOPE [class*="st-key-acts_"] { opacity:0; transition:opacity .15s; margin-left:-6px; }
SCOPE [data-testid="stChatMessage"]:hover [class*="st-key-acts_"], SCOPE [class*="st-key-acts_last_"] { opacity:1; }
SCOPE [class*="st-key-acts_"] button, SCOPE .loa-copy { width:32px; height:32px; min-height:32px; padding:0; border:none;
  border-radius:6px; background:transparent; color:var(--ink3); display:inline-flex; align-items:center; justify-content:center; }
SCOPE [class*="st-key-acts_"] button:hover, SCOPE .loa-copy:hover { background:var(--sunk); color:var(--ink); }
SCOPE [class*="st-key-acts_"] button[kind="primary"] { background:var(--accent-soft); color:var(--accent); }
SCOPE [class*="st-key-acts_"] button [data-testid="stIconMaterial"] { font-size:18px; }
SCOPE [class*="st-key-acts_"] [data-testid="stPopover"] > button { width:32px; height:32px; min-height:32px; padding:0; border:none; }
SCOPE [class*="st-key-acts_"] [data-testid="stPopover"] > button [data-testid="stIconMaterial"] { font-size:18px; }
SCOPE [class*="st-key-acts_"] [data-testid="stPopover"] > button svg { display:none; }
SCOPE .loa-copy { cursor:pointer; vertical-align:middle; }
SCOPE .loa-copy.done { color:var(--open); }
SCOPE .loa-shared { font-size:12px; color:var(--ink3); margin-left:4px; }
SCOPE [class*="st-key-acts_"] [class*="st-key-undo"] button { width:auto; padding:0 8px; font-size:12px; }
/* follow-up and example questions: left-aligned pills */
SCOPE [data-testid="stPills"] button { border-radius:999px; font-size:13.5px; }
SCOPE .loa-fu { font-size:12px; color:var(--ink3); margin:2px 0 2px 0; }
/* the chat box: 12px corners, a light shadow, a round send button */
SCOPE [data-testid="stChatInput"] { border-radius:12px; box-shadow:0 2px 12px rgba(15,26,42,.06); border-color:var(--line); }
SCOPE [data-testid="stChatInput"]:focus-within { border-color:var(--accent); }
SCOPE [data-testid="stChatInputSubmitButton"] { border-radius:50%; }
SCOPE [data-testid="stChatInputSubmitButton"]:not(:disabled) { background:var(--accent); color:#fff; }
SCOPE [data-testid="stChatInputSubmitButton"]:disabled { background:var(--sunk); color:var(--ink3); }
/* while an answer is being written the Stop button sits where the send button was (the script places it) */
SCOPE [class*="st-key-stop_"] button { width:32px; height:32px; min-height:32px; padding:0; border-radius:50%;
  background:var(--ink); color:#fff; border:none; }
SCOPE [class*="st-key-stop_"] button [data-testid="stIconMaterial"] { font-size:18px; }
SCOPE [class*="st-key-stop_"] button:hover { background:var(--accent); color:#fff; }
/* the top bar stays at the top of the scrolling area */
SCOPE [class*="st-key-cp_top_"], SCOPE [data-testid="stLayoutWrapper"]:has(> [class*="st-key-cp_top_"])
  { position:sticky; top:0; z-index:20; background:var(--bg); }
SCOPE [class*="st-key-cp_top_"] { padding:10px 0 8px 0; margin-bottom:4px; }
SCOPE [class*="st-key-cp_top_"] { flex-wrap:nowrap !important; }
SCOPE [class*="st-key-cp_top_"] > .stElementContainer:has(> .stHtml) { flex:1 1 auto; width:auto !important; min-width:0; }
SCOPE [class*="st-key-cp_top_"] > .stElementContainer:has(> .stHtml) .loa-cp-title { flex-wrap:nowrap; overflow:hidden; }
SCOPE [class*="st-key-cp_top_"] .loa-cp-title .loa-chip { overflow:hidden; text-overflow:ellipsis; max-width:260px; }
SCOPE .loa-cp-title { font-size:16px; font-weight:700; color:var(--ink); display:flex; align-items:center; gap:10px; flex-wrap:wrap; line-height:32px; }
SCOPE .loa-cp-title .loa-chip { margin:0; font-weight:400; line-height:20px; background:var(--surface); border:1px solid var(--line); }
SCOPE .loa-cp-title small { font-size:12px; font-weight:400; color:var(--ink3); }
SCOPE [class*="st-key-cp_top_"] button, SCOPE [class*="st-key-cp_top_"] [data-testid="stPopover"] > button { min-height:32px; height:32px; padding:0 10px; font-size:13px; }
/* empty state: a greeting in the middle of the space, the example questions under it */
SCOPE [class*="st-key-cp_empty_"] { min-height:calc(100vh - 300px); display:flex; flex-direction:column; justify-content:center; }
SCOPE .loa-cp-hello { font-size:24px; font-weight:700; color:var(--ink); line-height:1.3; }
SCOPE .loa-ctx-line { display:none; margin:-4px 0 8px 0; }
SCOPE .loa-ctx-line .loa-chip { background:var(--surface); border:1px solid var(--line); margin:0; }
SCOPE .loa-cp-sub { font-size:15px; color:var(--ink2); margin:6px 0 14px 0; padding-bottom:14px; border-bottom:1px solid var(--line); }
"""
PAGE_CSS = r"""
/* ---- Copilot page: a centred 760px thread between a fixed top bar and the fixed chat box (ChatGPT's three bands) */
body:has(.loa-cp-page) [data-testid="stMainBlockContainer"] { max-width:808px; margin:0 auto; padding-top:8px; padding-bottom:8px; }
body:has(.loa-cp-page) [data-testid="stBottomBlockContainer"] { max-width:808px; margin:0 auto; padding-top:8px; }
/* Streamlit's own top strip is gone on every page: no Deploy, no three-dot menu, no running-man; the header is
   see-through and only its sidebar-expand button still takes clicks */
header[data-testid="stHeader"] { background:transparent; pointer-events:none; box-shadow:none; }
header[data-testid="stHeader"] * { pointer-events:auto; }
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stDecoration"], [data-testid="stStatusWidget"]
  { display:none !important; }  /* stToolbar itself stays: it holds the sidebar-expand button */
/* with the strip gone, content starts near the top instead of under a 6rem reservation */
[data-testid="stMainBlockContainer"] { padding-top:1.5rem; }
[data-testid="stSidebarUserContent"] { padding-top:1.5rem; }  /* the logo lines up with the main area's top */
[data-testid="stSidebarHeader"] { position:absolute; top:6px; right:4px; height:auto; min-height:0; padding:0; z-index:2; }  /* the collapse button floats beside the logo */
@media (max-width:760px) { [data-testid="stMainBlockContainer"] { padding-top:3.5rem; } }  /* room for the expand button */
body:has(.loa-cp-page) .loa-notice { margin:0 0 4px 0; }
body:has(.loa-cp-page) [data-testid="stBottomBlockContainer"]::after, div[data-testid="stDialog"] .stElementContainer:has(> .stChatInput)::after
  { content:"Copilot can be wrong. Every number links to its source; check the ones marked \26A0.";
    display:block; text-align:center; font-size:11.5px; color:var(--ink3); padding-top:6px; }
/* the side panel: about 500px, its own top bar instead of the dialog's title */
div[data-testid="stDialog"] section > h2, div[data-testid="stDialog"] section > button:first-child { display:none; }
div[data-testid="stDialog"] section > div { padding-top:0; }
div[data-testid="stDialog"] [class*="st-key-cp_top_"], div[data-testid="stDialog"] [data-testid="stLayoutWrapper"]:has(> [class*="st-key-cp_top_"]) { background:var(--surface); top:-1px; }
div[data-testid="stDialog"] [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"],
div[data-testid="stDialog"] [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] p { font-size:15px; }
div[data-testid="stDialog"] [data-testid="stChatMessage"]:has(> [data-testid="stChatMessageAvatarUser"]) > [data-testid="stChatMessageContent"] { max-width:85%; }
div[data-testid="stDialog"] [class*="st-key-cp_empty_"] { min-height:calc(100vh - 260px); }
div[data-testid="stDialog"] .loa-cp-hello { font-size:22px; }
.st-key-fab_close button { width:32px; height:32px; min-height:32px; padding:0; border-radius:6px; }
/* the floating "jump to latest" button: a round arrow just above the chat box */
.loa-latest { position:fixed; z-index:1000; width:32px; height:32px; border-radius:50%; border:1px solid var(--line); background:#fff;
  color:var(--ink); display:none; align-items:center; justify-content:center; cursor:pointer; box-shadow:0 2px 8px rgba(15,26,42,.15); padding:0; }
.loa-latest:hover { background:var(--sunk); }
@media (hover:none) { [class*="st-key-acts_"] { opacity:1 !important; } }
@media (max-width:760px) {
  body:has(.loa-cp-page) [class*="st-key-cp_top_"] { padding-left:44px; }
  body:has(.loa-cp-page) [data-testid="stChatMessage"]:has(> [data-testid="stChatMessageAvatarUser"]) > [data-testid="stChatMessageContent"] { max-width:85%; }
  body:has(.loa-cp-page) [data-testid="stBottomBlockContainer"] { padding-bottom:max(8px, env(safe-area-inset-bottom)); }
  [class*="st-key-cp_top_"] button span[data-testid="stMarkdownContainer"] { display:none; }
  /* the context chip leaves the bar for its own line under it; the name goes (it is in the sidebar) */
  [class*="st-key-cp_top_"] .loa-cp-title small, [class*="st-key-cp_top_"] .loa-cp-title .loa-chip { display:none; }
  .loa-ctx-line { display:block; }
}
"""
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
.loa-notice { font-size:12px; color:var(--ink3); border-bottom:1px solid var(--line); padding:0 0 6px 0; margin:-8px 0 14px 0; }
.loa-me { display:flex; align-items:center; gap:6px; font-size:14px; color:var(--ink); }
.loa-logo { display:block; width:212px; max-width:100%; height:auto; margin:6px 0 2px 0; }
.loa-logo-cap { font-size:12px; color:var(--ink3); margin:0 0 10px 0; }
.loa-builtfor { margin:18px 0 4px 0; border-bottom:1px solid var(--line); padding-bottom:12px; }
.loa-builtfor .loa-kicker { margin-bottom:8px; }
.loa-builtfor img { display:block; width:118px; height:auto; }
.loa-cobrand { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; border-bottom:1px solid var(--line); padding:4px 0 12px 0; margin:4px 0 12px 0; }
.loa-cobrand img { display:block; width:420px; max-width:70%; height:auto; }
.loa-cobrand span { font-size:12px; color:var(--ink3); white-space:nowrap; }
@media (max-width:640px) { .loa-logo { width:168px; } .loa-builtfor img { width:72px; } }
/* Copilot floating button: bottom right of every page, above the content; gone while the panel is open */
.st-key-fab_copilot { position:fixed; right:max(20px, env(safe-area-inset-right)); bottom:max(20px, env(safe-area-inset-bottom));
  z-index:1001; width:auto !important; }
.st-key-fab_copilot button { width:48px; height:48px; min-height:48px; border-radius:50%; padding:0;
  box-shadow:0 4px 16px rgba(15,26,42,.30); }
.st-key-fab_copilot button [data-testid="stIconMaterial"] { font-size:24px; }
body:has(div[data-testid="stDialog"]) .st-key-fab_copilot { display:none; }
/* Copilot side panel: the input box stays at the bottom of the panel while the conversation scrolls above it */
div[data-testid="stDialog"] section > div { display:flex; flex-direction:column; }
div[data-testid="stDialog"] section > div > div[data-testid="stVerticalBlock"],
div[data-testid="stDialog"] section > div > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"],
div[data-testid="stDialog"] section > div > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"]
  { flex:1 0 auto; display:flex; flex-direction:column; }
div[data-testid="stDialog"] .stElementContainer:has(> .stChatInput) { position:sticky; bottom:-20px; margin-top:auto;
  background:#fff; padding:8px 0 20px 0; z-index:5; }
/* the slide editor: a wide floating window, three columns, thumbnails and chat scroll on their own */
div[data-testid="stDialog"]:has(.loa-deck-ed) > div { width:calc(100vw - 48px) !important; max-width:calc(100vw - 48px) !important; height:calc(100vh - 48px); max-height:calc(100vh - 48px); margin:24px auto; border-radius:10px; box-shadow:0 24px 64px rgba(0,0,0,.28); overflow:hidden; }
div[data-testid="stDialog"]:has(.loa-deck-ed) section { width:100% !important; max-width:none !important; max-height:calc(100vh - 48px); overflow-y:auto; }
div[data-testid="stDialog"]:has(.loa-deck-ed) section > div { padding:0 20px 14px 20px; }
@media (max-width:860px) { div[data-testid="stDialog"]:has(.loa-deck-ed) > div { width:100vw !important; max-width:100vw !important; height:100vh; max-height:100vh; margin:0; border-radius:0; }
  div[data-testid="stDialog"]:has(.loa-deck-ed) section { max-height:100vh; }
  div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-deck_top"], div[data-testid="stDialog"]:has(.loa-deck-ed) [data-testid="stLayoutWrapper"]:has(> [class*="st-key-deck_top"]) { flex-wrap:wrap; }
  div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thumbs > div[data-testid="stElementContainer"], div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thumbs > div > div[data-testid="stVerticalBlock"] { flex-direction:row; overflow-x:auto; gap:8px; }
  div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thumbs [data-testid="stLayoutWrapper"]:has(> [class*="st-key-ed_th_"]), div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thumbs .stElementContainer:has(.loa-ed-planned) { flex:0 0 150px; width:150px; min-width:150px; }
  div[data-testid="stDialog"]:has(.loa-deck-ed) [data-testid="stLayoutWrapper"]:has(> [class*="st-key-deck_top"]) { overflow-x:auto; }
  div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thumbs { max-height:none; } }
div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-deck_top"], div[data-testid="stDialog"]:has(.loa-deck-ed) [data-testid="stLayoutWrapper"]:has(> [class*="st-key-deck_top"]) { position:sticky; top:-1px; background:var(--surface); z-index:6; padding:6px 0; flex-wrap:nowrap; }
div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thumbs { max-height:calc(100vh - 170px); overflow-y:auto; padding-right:4px; }
div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thread { max-height:calc(100vh - 270px); overflow-y:auto; padding-right:4px; }
div[data-testid="stDialog"]:has(.loa-deck-ed) .stElementContainer:has(> .stChatInput) { position:static; padding:6px 0 0 0; }
div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thumbs img { border:1px solid var(--line); border-radius:4px; }
div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thumbs .stButton button { justify-content:flex-start; font-size:12px; min-height:28px; padding:2px 8px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_stage img { border:1px solid var(--line); border-radius:6px; box-shadow:0 6px 24px rgba(15,26,42,.12); }
div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_chat [data-testid="stChatMessage"] { padding:6px 0; }
div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-cp_empty_"] { min-height:0; }
div[data-testid="stDialog"]:has(.loa-deck-ed) .loa-cp-hello { font-size:18px; }
div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-ed_th_"] { position:relative; padding:4px 4px 2px 22px; border-radius:6px; gap:2px; }
div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-ed_th_"][class*="_on"] { background:var(--accent-soft, #e8eef7); }
div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-ed_th_"][class*="_on"] img { outline:2px solid var(--accent); outline-offset:0; }
.loa-ed-num { position:absolute; left:6px; top:6px; font-family:var(--f-mono, ui-monospace, monospace); font-size:11px; color:var(--ink3); }
.loa-ed-lay { font-size:11px; color:var(--ink3); line-height:14px; }
.loa-ed-planned { position:relative; padding:4px 4px 2px 22px; }
.loa-ed-frame { aspect-ratio:16/9; border:1px dashed var(--line); border-radius:4px; display:flex; align-items:center; justify-content:center;
  font-size:11px; color:var(--ink3); text-align:center; padding:4px;
  background:repeating-linear-gradient(135deg, var(--sunk, #f3f5f8) 0 6px, #fff 6px 12px); }
.loa-ed-status { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:12.5px; }
.loa-ed-status .loa-ic { margin-right:6px; }
.loa-ic.spin { animation:loa-spin 1s linear infinite; }
@keyframes loa-spin { to { transform:rotate(360deg); } }
.loa-ed-count { font-family:var(--f-mono, ui-monospace, monospace); font-size:12px; color:var(--ink2); white-space:nowrap; }
.loa-ed-why { font-size:12px; line-height:15px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-deck_bar"] { flex-wrap:nowrap; }
div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-deck_bar"] .stButton button { width:30px; height:30px; min-height:30px; padding:0; }
div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-deck_top"] .stButton button, div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-deck_top"] .stDownloadButton button { min-height:32px; height:32px; padding:0 10px; white-space:nowrap; }
div[data-testid="stDialog"]:has(.loa-deck-ed) [class*="st-key-deck_top"] [data-testid="stSegmentedControl"] button { min-height:28px; font-size:12px; }
div[data-testid="stDialog"]:has(.loa-deck-ed) .stElementContainer:has(> .stChatInput) { bottom:-20px; }
@media (max-width:860px) { div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thumbs { max-height:none; } div[data-testid="stDialog"]:has(.loa-deck-ed) .st-key-deck_thread { max-height:42vh; } }
</style>
""")
st.html(f"<style>{icons_css()}</style>")  # the icons themselves (CSS masks: st.html strips inline <svg>)
st.html("<style>" + CHAT_CSS.replace("SCOPE", "body:has(.loa-cp-page)") + CHAT_CSS.replace("SCOPE", 'div[data-testid="stDialog"]')
        + PAGE_CSS + "</style>")


def esc(x) -> str:
    return html.escape(str(x or ""))


def chip(text, kind="", href="") -> str:
    inner = f'<span class="loa-chip {kind}">{esc(text)}</span>'
    return f'<a class="loa-chip {kind}" href="{esc(href)}" target="_blank">{esc(text)}</a>' if href else inner


def kicker(text) -> str:
    return f'<div class="loa-kicker">{esc(text)}</div>'


@st.cache_resource(show_spinner=False)
def brand_img(name: str, cls: str = "", alt: str = "") -> str:
    """An <img> for a file in assets/brand as a data URI (st.html keeps <img>, it strips inline <svg>), so the
    logos never depend on static-file serving. The Nan Fung SVG is embedded exactly as published."""
    import base64
    path = BRAND / name
    mime = "image/svg+xml" if path.suffix == ".svg" else "image/png"
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img class="{cls}" alt="{esc(alt)}" src="data:{mime};base64,{data}">'


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
    app.ensure_data(background=True)  # due open-data collection runs behind the page, not before it
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


# Every chat surface (the Copilot page, its side panel, the slide editor's column) keeps one saved conversation on
# screen in a "slot": "" is the Copilot's, "_deck" the slide editor's. Same store, same owner, same turns shape.
DECK_CHAT_PREFIX = "Slides · "


def open_chat(chat_id: str | None, slot: str = ""):
    """Put one saved chat on screen (None: a new, empty one; its row is created with the first question)."""
    st.session_state["chat_id" + slot] = chat_id
    turns = []
    for m in (app.store.chat_messages(chat_id) if chat_id else []):
        turn = {"role": m["role"], "content": m["content"], "id": m["id"]}
        if m["role"] == "assistant" and m["trace"]:
            turn["answer"] = Answer(m["content"], m["trace"], m["engine"])
        turns.append(turn)
    st.session_state["chat_turns" + slot] = turns


def current_chat(slot: str = "") -> tuple[str | None, list[dict]]:
    """(chat id, turns) of the conversation on screen. After a refresh, or when the name changes, the person's
    latest saved chat comes back, so nothing is lost by reloading the page."""
    owner = chat_owner()
    if st.session_state.get("chat_owner" + slot) != owner:
        st.session_state["chat_owner" + slot] = owner
        latest = [c for c in app.store.chats(owner) if (c["title"] or "").startswith(DECK_CHAT_PREFIX) == bool(slot)][:1]
        open_chat(latest[0]["id"] if latest else None, slot)
    return st.session_state.get("chat_id" + slot), st.session_state.setdefault("chat_turns" + slot, [])


def ensure_chat(slot: str = "", title: str = "") -> str:
    """The id of the chat on screen, creating its row for the first question. The id also names the Copilot's
    conversation in Pi, so each chat keeps its own context and a new chat starts clean."""
    if not st.session_state.get("chat_id" + slot):
        st.session_state["chat_id" + slot] = app.store.new_chat(chat_owner(), title)
    return st.session_state["chat_id" + slot]


def say(role: str, content: str, ans: Answer | None = None, slot: str = "", title: str = ""):
    """Add a turn to the conversation on screen and to the saved chat."""
    chat_id = ensure_chat(slot, title)
    turn = {"role": role, "content": content}
    if ans is not None:
        turn["answer"] = ans
    st.session_state.setdefault("chat_turns" + slot, []).append(turn)
    turn["id"] = app.store.add_chat_message(chat_id, role, content, ans.trace if ans else None, ans.engine if ans else "")


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
        st.html(brand_img("logo-horizontal.svg", "loa-logo", "London Office Market Agent"))
        c = st.columns([2.4, 2.1], vertical_alignment="center")
        c[0].html(f'<div class="loa-me">{ic("user", 15, "accent")}<b>{esc(user)}</b></div>')
        with c[1].popover("Change", width="stretch", help="Who is using this browser: no login, pick a name once"):
            who_card("s", compact=True)
            if user != "Guest" and st.button("Forget me", key="forget_me", type="tertiary"):
                st.session_state["me"] = "Guest"
                st.session_state["me_cleared"] = True
                st.query_params.pop("me", None)
                st.rerun()
        if user != "Guest" and st.query_params.get("me") != user:
            st.query_params["me"] = user
            st.session_state["me_cleared"] = False
        remember_me()
        st.html(kicker("Work"))
        st.page_link(PAGE_OBJ["monitor"], label="Monitor", icon=material("activity"), help="Stay ahead of the market")
        st.page_link(PAGE_OBJ["copilot"], label="Ask Copilot", icon=material("message-square"), help="Judge: ask, compare, drill down")
        st.page_link(PAGE_OBJ["brief"], label=f"Team brief · {brief_count}" if brief_count else "Team brief",
                     icon=material("file-text"), help="Report: board and IC outputs")
        st.page_link(PAGE_OBJ["sources"], label=f"Sources · {to_check} to check" if to_check else "Sources",
                     icon=material("database"), help="Data the agent maintains")
        st.page_link(PAGE_OBJ["help"], label="Help", icon=":material/help:", help="How to use the app, step by step")
        st.html(f"""{kicker("Team")}
<div class="loa-team"><b>{esc(team['name'])}</b><div style="margin:6px 0 0 0">{avatars(colleagues(), user)}</div></div>""")
        st.html(f'<div class="loa-builtfor">{kicker("Built for")}'
                + brand_img("nanfung/nanfung-logo-color.svg", "", "Nan Fung Group") + "</div>")


HELP_DIR = Path(__file__).resolve().parent / "assets" / "help"
HELP_OUTLINE = [  # shown until the illustrated guide is in assets/help/
    ("Monitor", "What changed this week for the team, as signal cards. Each card says what moved, by how much, "
                "and why it matters, with its source. **Add to brief** puts a signal in the team brief; "
                "**Set up my focus** makes a 'For you' view of the submarkets and measures you follow."),
    ("Ask Copilot", "Ask about the market in plain English or Chinese. The answer streams in with every figure "
                    "linked to its source; **Stop** keeps what is written. Your conversations are saved under "
                    "your name, and **Share to team** shows an answer to colleagues."),
    ("Team brief", "The week's brief, written from the signals the team added, as a board summary or an IC paper "
                   "section. **Word** and **PDF** download it as a research note; **Build slides** opens the "
                   "slide editor."),
    ("Slides", "Change the deck by asking (\"swap slides 2 and 3\", \"theme forest\"). **Undo** and the version list "
               "go back; **Download .pptx** and **PDF** take the deck away."),
    ("Sources", "One library for the team: open data collected automatically, reports colleagues upload, and the "
                "company's own deals. Items that need a person to check are counted beside the name."),
]


def help_section(md: str):
    """Markdown with ![caption](screenshots/x.png) images: text as text, each image full width with its caption."""
    for part in re.split(r"(!\[[^\]]*\]\([^)]+\))", md):
        m = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", part.strip())
        if m:
            img = (HELP_DIR / m.group(2)).resolve()
            if img.is_file() and HELP_DIR.resolve() in img.parents:
                st.image(str(img), caption=m.group(1) or None, width="stretch")
        elif part.strip():
            st.markdown(part)


def help_page():
    st.session_state["page"] = "help"
    page_header("Help", "How to use the London Office Market Agent, page by page.")
    langs = {"en": ("English", HELP_DIR / "help.md"), "zh": ("中文", HELP_DIR / "help.zh-TW.md")}
    have = {k: v for k, v in langs.items() if v[1].exists()}
    if have:
        pick = next(iter(have))
        if len(have) > 1:
            pick = st.segmented_control("Language", list(have), format_func=lambda k: have[k][0], key="help_lang",
                                        default=pick, label_visibility="collapsed") or pick
        text = re.sub(r"\A\s*# .*\n", "", have[pick][1].read_text(encoding="utf-8"))  # the page has its own title
        heads = re.findall(r"^## (.+)$", text, flags=re.M)
        if heads:
            st.html('<div class="loa-muted">' + " · ".join(
                f'<a href="#{re.sub(r"[^a-z0-9]+", "-", h.lower()).strip("-")}">{esc(h)}</a>' for h in heads) + "</div>")
        help_section(text)
    else:
        for title, body in HELP_OUTLINE:
            with st.container(border=True):
                st.markdown(f"#### {title}")
                st.markdown(body)
    with st.expander("About this installation"):
        st.caption(f"Data up to {an.period_label(an.latest_period(app.store))}")
        st.caption(f"Copilot engine: {engine.status}")
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
    st.session_state["_in_dialog"] = False  # the page itself is running; a dialog sets it again when it opens
    copilot_fab()
    follow_output()  # the page-level keyboard shortcut ("/") and follow-scrolling need the script on every page
    st.html('<div class="loa-notice">Evaluation PoC: market figures are restated from public Knight Frank reports '
            '(evaluation only, not for AI or commercial use); Bank Rate and news are collected live; internal deals '
            'and colleague names are demo data.</div>')
    st.html(f'<div class="loa-h1">{esc(title)}</div><div class="loa-sub">{esc(subtitle)}</div>')


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


def show_answer(ans, text_done: bool = False, downloads: bool = True):
    """One answer: a quiet 'Worked through N steps' line (the tools, folded), the text, its charts and downloads,
    then the sources line. While the answer streams, the live status line plays the first part."""
    if not text_done:
        if ans.trace:
            tools = list(dict.fromkeys(t["tool"] for t in ans.trace))
            with st.expander(f"Worked through {len(ans.trace)} step{'s' if len(ans.trace) != 1 else ''}", expanded=False):
                st.caption("Tools: " + ", ".join(tools))
        st.markdown(split_follow_ups(ans.text)[0])
    for step in ans.trace:
        chart(step["result"].get("chart"))
        if downloads and step["tool"] == "build_brief_pptx" and (p := (step["result"].get("data") or {}).get("path")) and Path(p).exists():
            st.download_button("Download the slides (.pptx)", Path(p).read_bytes(), file_name=Path(p).name,
                               mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                               key=f"dl{hash(p)}{id(step)}")
    sources = {(s.get("title"), s.get("url")) for step in ans.trace for s in step["result"].get("sources", []) or []}
    if sources:
        st.html('<div class="loa-srcs"><span>Sources</span>'
                + "".join(chip(t, "src auto", u) for t, u in sorted(sources, key=lambda x: x[0] or "")) + "</div>")


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
  function chatBox(c) {
    // the chat box this container scrolls above: the one inside it (the side panel), else the page's own
    const boxes = [...doc.querySelectorAll("[data-testid='stChatInput']")];
    return boxes.filter((b) => c.contains(b)).pop() || boxes.pop();
  }
  function latestButton(c, show) {
    let b = c.__loaLatest;
    if (!b) {
      b = doc.createElement("button");
      b.innerHTML = ARROW;
      b.title = "Jump to latest";
      b.className = "loa-latest";
      b.addEventListener("click", () => { follow.set(c, true); c.scrollTo({ top: c.scrollHeight, behavior: "smooth" }); b.style.display = "none"; });
      doc.body.appendChild(b);
      c.__loaLatest = b;
    }
    if (show) {  // a round arrow 12px above the chat box, centred on it
      const box = chatBox(c);
      const r = box ? box.getBoundingClientRect() : c.getBoundingClientRect();
      b.style.left = Math.round(r.left + r.width / 2 - 16) + "px";
      b.style.top = Math.round((box ? r.top : Math.min(r.bottom, window.innerHeight)) - 44) + "px";
    }
    b.style.display = show ? "inline-flex" : "none";
  }
  // While an answer streams, the Stop button (a Streamlit button inside the answer) is laid over the chat box's
  // send button, so stopping is where sending was; the send button itself is hidden meanwhile.
  function placeStop() {
    const stop = doc.querySelector("[class*='st-key-stop_']");
    const subs = doc.querySelectorAll("[data-testid='stChatInputSubmitButton']");
    const sub = subs[subs.length - 1];
    if (!sub) { return; }
    if (!stop) { sub.style.visibility = ""; return; }
    const r = sub.getBoundingClientRect();
    sub.style.visibility = "hidden";
    stop.style.cssText = "position:fixed;z-index:1002;margin:0;width:" + r.width + "px;height:" + r.height + "px;left:" + r.left + "px;top:" + r.top + "px;";
  }
  window.addEventListener("resize", placeStop);
  // Copy: the button in an answer's action row copies the answer's text (not the work line or the sources)
  doc.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest(".loa-copy");
    if (!btn) { return; }
    const msg = btn.closest("[data-testid='stChatMessage']");
    if (!msg) { return; }
    const parts = [...msg.querySelectorAll("[data-testid='stMarkdown']")]
      .filter((m) => !m.closest("[data-testid='stExpander']") && !m.closest("[class*='st-key-acts_']"))
      .map((m) => m.innerText.trim()).filter(Boolean);
    const text = parts.join("\n\n");
    const done = () => { btn.classList.add("done"); setTimeout(() => btn.classList.remove("done"), 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).then(done, done); }
    else {
      const ta = doc.createElement("textarea"); ta.value = text; doc.body.appendChild(ta); ta.select();
      try { doc.execCommand("copy"); } catch (err) {}
      ta.remove(); done();
    }
  });
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
    placeStop();
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
    if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "k" || e.key === "K")) {  // Ctrl+K: open the Copilot
      const fab = doc.querySelector(".st-key-fab_copilot button");
      if (fab) { e.preventDefault(); fab.click(); }
      return;
    }
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
    core = FOLLOW_CORE.replace("ARROW", json.dumps(icon_svg("arrow-down", 16).replace(' class="loa-ic"', "")), 1)
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


@st.dialog("Copilot", position="right", width="small", on_dismiss="rerun")
def copilot():
    st.session_state["_in_dialog"] = True
    copilot_body()


def _rerun():
    """A fragment rerun inside the side panel or the slide editor when the dialog is running as one, else the
    whole page (a dialog's first run belongs to the page, and the editor reopens from its state)."""
    if st.session_state.get("_in_dialog"):
        try:
            st.rerun(scope="fragment")
        except Exception:  # noqa: BLE001  (not a fragment rerun yet)
            pass
    st.rerun()


def clicked_meanwhile() -> bool:
    """True when the person clicked something inside the side panel or the slide editor while this run is busy.
    Both are dialogs, and Streamlit runs a dialog as a fragment: a click there is queued until the run in
    progress ends instead of interrupting it, so Stop and the close button did nothing until a deck had finished
    building. Long loops ask this between steps and give way (yield_to_clicks); the work itself carries on in
    its own thread and the next run picks it up, or stops it when the click was Stop."""
    try:
        from streamlit.runtime.scriptrunner_utils.script_requests import ScriptRequestType
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
        req = get_script_run_ctx(suppress_warning=True).script_requests
        data = req._rerun_data
        return (req._state == ScriptRequestType.RERUN and bool(data.fragment_id_queue)
                and not data.is_fragment_scoped_rerun and not data.is_auto_rerun)
    except Exception:  # noqa: BLE001  (outside a script run, or Streamlit changed its internals: never give way)
        return False


def yield_to_clicks():
    """End this run now when a click is waiting, so it is handled at once (the click's own rerun follows)."""
    if clicked_meanwhile():
        st.rerun()


SETUP_PILL = "Set up my focus"


def _pick(key: str, target: str = "cp_ask"):
    """A pill was chosen (an example question, a follow-up): it becomes the next question of the surface named
    by `target` (cp_ask: the Copilot; deck_ask: the slide editor), and the pill resets so the same one can be
    chosen again later."""
    v = st.session_state.get(key)
    st.session_state[key] = None
    if v == SETUP_PILL:
        st.session_state["copilot_ctx"] = {"kind": "setup"}
    elif v:
        st.session_state[target] = v


def top_bar(ctx, chat_id, sfx: str):
    """The bar that stays at the top while the thread scrolls: 'Copilot' with what it is looking at on the left;
    History and New chat on the right (the side panel adds the name and a close button, and shows icons only)."""
    looking = {"setup": "setting up your focus", "signal": ctx.get("title", "")}.get(
        ctx["kind"], PAGE_TITLES.get(ctx.get("page", ""), ctx.get("page", "")))
    label = "About" if ctx["kind"] == "signal" else "Looking at"
    panel = sfx == "d"
    with st.container(key=f"cp_top_{sfx}", horizontal=True, vertical_alignment="center", gap="small"):
        who = f"<small>{esc(user)}</small>" if panel and user != "Guest" else ""
        st.html(f'<div class="loa-cp-title">Copilot {who}<span class="loa-chip">{label}: {esc(looking)}</span></div>',
                width="stretch")
        if panel:
            with st.popover("", icon=material("user"), help="Who is asking; change the name", width="content"):
                who_card(sfx, compact=True)
        with st.popover("" if panel else "History", icon=material("history"), help="Your saved conversations",
                        width="content"):
            history_list(chat_id, sfx)
        if st.button("" if panel else "New chat", icon=material("plus"), key=f"newchat_{sfx}",
                     help="Start a clean conversation", width="content"):
            open_chat(None)
            if not panel:
                st.session_state["copilot_ctx"] = {"kind": "page", "page": "copilot"}
            _rerun()
        if panel and st.button("", icon=material("x"), key="fab_close", help="Close · Esc", width="content"):
            st.rerun()  # a full rerun closes the panel; the page underneath keeps its place and the chat is saved
    # on a phone the context chip leaves the bar for its own line under it (it scrolls away with the thread)
    st.html(f'<div class="loa-ctx-line"><span class="loa-chip">{label}: {esc(looking)}</span></div>')


def empty_state(ctx, intro: str, suggestions: list[str], sfx: str):
    """A new chat: a greeting in the middle of the space and the example questions as pills (no message)."""
    name = user if user != "Guest" else "there"
    if ctx["kind"] == "setup":
        head, sub = "Tell me what you do, in one sentence.", intro
    elif ctx["kind"] == "signal":
        head, sub = ctx.get("title", "This signal"), "Ask anything about this signal; every number comes with its source."
    else:
        head = f"Hi {name}. What do you want to know about London offices?"
        sub = "I can see what's on your screen, and every number comes with its source."
    opts = ([SETUP_PILL] if ctx["kind"] == "page" else []) + [q for q in suggestions if q != SETUP_PILL]
    hello_state(head, sub, opts, f"cs_{sfx}_{ctx['kind']}", sfx)


def hello_state(head: str, sub: str, suggestions: list[str], key: str, sfx: str, target: str = "cp_ask"):
    """The empty state every chat surface shares: a greeting, one line of what it does, example questions as
    pills (chosen ones become the next question)."""
    with st.container(key=f"cp_empty_{sfx}"):
        st.html(f'<div class="loa-cp-hello">{esc(head)}</div><div class="loa-cp-sub">{esc(sub)}</div>')
        st.pills("Suggestions", suggestions, key=key, label_visibility="collapsed", on_change=_pick, args=(key, target))


def follow_up_pills(turns: list[dict], sfx: str, target: str = "cp_ask") -> str | None:
    """Under the thread of any chat surface: 'Ask again' after a stopped answer, else the last answer's own
    follow-up questions as pills. Returns a question chosen by Ask again."""
    if not turns or turns[-1]["role"] != "assistant":
        return None
    if turns[-1]["content"].endswith("*Stopped.*") and len(turns) > 1:
        if st.button("Ask again", icon=material("refresh-cw"), key=f"again_{sfx}{len(turns)}"):
            return turns[-2]["content"]
    elif "answer" in turns[-1]:
        _, follow_ups = split_follow_ups(turns[-1]["answer"].text)
        if follow_ups:
            st.html('<div class="loa-fu">Follow up</div>')
            key = f"fu_{sfx}_{len(turns)}"
            st.pills("Follow up", follow_ups, key=key, label_visibility="collapsed", on_change=_pick, args=(key, target))
    return None


def copilot_body(full: bool = False, question: str | None = None, own_input: bool = True):
    """The conversation: a top bar that stays put (what the Copilot is looking at, History, New chat); the saved
    chat in a centred column; the example questions only while the chat is empty; the chat box at the bottom
    (the page passes its own pinned one in `question`; the side panel makes one here)."""
    ctx = st.session_state.get("copilot_ctx", {"kind": "page", "page": "monitor"})
    sfx = "d" if st.session_state.get("_in_dialog") else "p"
    if user == "Guest" and not st.session_state.get("skip_who"):
        who_card(sfx)  # first visit in this browser: pick a name once, no login
        return
    chat_id, turns = current_chat()
    turns = absorb_partial(chat_id, turns)
    top_bar(ctx, chat_id, sfx)
    if ctx["kind"] == "setup":
        intro = ("I'll set up your 'For you' view: submarkets, measures, how much to show and alerts. Nothing "
                 "changes until you press Apply. The team view stays as it is.")
        suggestions = SETUP_EXAMPLES
    elif ctx["kind"] == "signal":
        intro, suggestions = "", SIGNAL_SUGGESTIONS
    else:
        intro = ""
        suggestions = PAGE_SUGGESTIONS.get(ctx.get("page", ""), team["questions"][:4])
    clicked = st.session_state.pop("cp_ask", None)  # a pill, Ask again or the regenerate button chose a question
    thread = st.container()  # the conversation; the chat box sits below it, pinned to the bottom
    sugg = st.empty()  # example questions or follow-ups go here, under the thread, but only when nothing is being asked
    if own_input:
        question = st.chat_input(chat_placeholder(ctx), key="copilot_input", max_chars=2000)
    if not question and not clicked:
        with sugg.container():
            if not turns:  # the examples belong to a new chat; afterwards only the last answer's own follow-ups show
                empty_state(ctx, intro, suggestions, sfx)
            else:
                clicked = follow_up_pills(turns, sfx) or clicked
    question = question or clicked
    if clicked:
        sugg.empty()  # a question is on its way: the pills leave the screen, as a typed question would
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
    return {"setup": "Describe your job in one sentence", "signal": "Ask about this signal"}.get(
        ctx["kind"], "Ask about any London submarket")


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


JOBS: dict[tuple, dict] = {}  # (person, slot) -> the partial of a Copilot run still going; shared by every session


def running_job(slot: str = ""):
    """The partial of this person's run in `slot`, from this session or (after a reload) from the shared table."""
    p = st.session_state.get("partial")
    if p and p.get("slot", "") == slot:
        return p
    r = st.session_state.get("resume" + slot)  # handed over by a run that gave way to a click (the close button)
    if r and r.get("owner") == chat_owner():
        return r
    return JOBS.get((chat_owner(), slot))


def absorb_partial(chat_id, turns, slot: str = ""):
    """After the reader pressed Stop (or clicked elsewhere) while an answer was streaming: keep what was
    written, marked 'Stopped', in the chat it belonged to. Returns the turns on screen, reloaded if that chat."""
    partial = st.session_state.get("partial")
    if not (partial and partial.get("slot", "") == slot):
        partial = JOBS.get((chat_owner(), slot))  # the page was reloaded: the run is still going for this person
        if partial and partial.get("owner") != chat_owner():
            partial = None
    if partial:
        if st.session_state.get("partial") is partial:
            st.session_state.pop("partial")
        JOBS.pop((partial.get("owner"), slot), None)
        stream = partial.get("stream")
        if stream is not None and hasattr(stream, "events") and not st.session_state.get(f"stop_{partial['chat']}"):
            # not a Stop: the page was switched or rerun while the Copilot was working. The run went on in the
            # background; the thread picks it up again from its first event (or shows the finished answer).
            st.session_state["resume" + slot] = partial
            if partial["chat"] != chat_id:
                open_chat(partial["chat"], slot)
                return st.session_state["chat_turns" + slot]
            return turns
        if stream is not None and hasattr(stream, "cancel"):
            stream.cancel()  # the Node run behind it stops too, so the next question starts at once
        app.store.add_chat_message(partial["chat"], "user", partial["q"])
        app.store.add_chat_message(partial["chat"], "assistant", (partial["text"].rstrip() or "(nothing written yet)")
                                   + "\n\n*Stopped.*")
        if partial["chat"] == chat_id:
            open_chat(chat_id, slot)
            return st.session_state["chat_turns" + slot]
    return turns


def action_row(turn, latest: bool, prev_question: str, sfx: str, target: str = "cp_ask"):
    """Under an answer: Copy, thumbs up, thumbs down, Ask again, Share to team, as 32px icon buttons. The latest
    answer's row stays on screen; an older row appears when the pointer is over that answer. An answer stays
    private to the person who asked until they share it; 'Shared to team · Undo' takes it out again."""
    mid = turn.get("id")
    if not mid:
        return
    shared = app.store.shared_by(mid)
    vote = app.store.answer_vote(mid, user)
    with st.container(key=f"acts_{'last_' if latest else ''}{sfx}{mid}", horizontal=True, vertical_alignment="center",
                      gap=None):
        st.html(f'<button class="loa-copy" title="Copy the answer">{ic("copy", 16)}</button>')
        if st.button("", icon=material("thumbs-up"), key=f"up{sfx}{mid}", help="Good answer",
                     type="primary" if vote > 0 else "tertiary"):
            app.store.vote_answer(mid, user, 0 if vote > 0 else 1)
            _rerun()
        if st.button("", icon=material("thumbs-down"), key=f"dn{sfx}{mid}", help="Not useful",
                     type="primary" if vote < 0 else "tertiary"):
            app.store.vote_answer(mid, user, 0 if vote < 0 else -1)
            _rerun()
        if prev_question and st.button("", icon=material("refresh-cw"), key=f"re{sfx}{mid}", type="tertiary",
                                       help="Ask this question again"):
            st.session_state[target] = prev_question
            _rerun()
        if shared:
            st.html(f'<span class="loa-shared">Shared to team · {lib.when(shared["ts"])}</span>')
            if st.button("Undo", key=f"undo{sfx}{mid}", type="tertiary", help="Take this answer out of team activity"):
                app.store.unshare_answer(mid)
                _rerun()
        else:  # the chat on screen is always the viewer's own
            with st.popover("", icon=material("share-2"),
                            help="Share to team: only you can see this answer until you share it; sharing puts the "
                                 "question, the answer, its charts and sources in team activity with your name"):
                note = st.text_input("Why is it worth a look? (optional)", key=f"note{mid}", placeholder="e.g. IC needs this")
                if st.button("Share", key=f"share{mid}", type="primary"):
                    app.store.share_answer(mid, user, note.strip())
                    _rerun()


def thread_view(turns, sfx: str, busy: bool = False, target: str = "cp_ask", downloads: bool = True):
    """The saved turns of any chat surface: user bubbles, answers with their work line, charts, sources and the
    action row (copy, thumbs, ask again, share). `busy`: a new question is being answered under it."""
    for i, turn in enumerate(turns):
        with st.chat_message(turn["role"]):
            if turn["role"] == "user" or "answer" not in turn:
                st.markdown(turn["content"])
            else:
                show_answer(turn["answer"], downloads=downloads)
                prev = turns[i - 1]["content"] if i and turns[i - 1]["role"] == "user" else ""
                action_row(turn, latest=(i == len(turns) - 1 and not busy), prev_question=prev, sfx=sfx, target=target)


def copilot_thread(turns, ctx, question):
    sfx = "d" if st.session_state.get("_in_dialog") else "p"
    thread_view(turns, sfx, busy=bool(question))
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
            hit = cached_deck(fmt, theme)  # the same data never builds twice
            how = hit["data"]["how"] if hit else build_deck_now(fmt, theme)[0]
            hit = hit or cached_deck(fmt, theme)
            if how and hit:
                lines = "\n".join(f"- {line}" for line in hit["data"].get("slides") or [])
                reply = ((f"這台伺服器上 Copilot 離線，所以由規則從本週數據選頁：{fx.BRIEF_FORMATS[fmt]}、{DECK_THEMES[theme]}。"
                          f"數字與來源相同，只是頁面取捨與標題是標準版。要改頁面請到 Team brief 按 Open editor。\n\n" + lines)
                         if _de.is_zh(question) else
                         (f"The Copilot is offline on this server, so rules picked the slides from this week's data: "
                          f"{fx.BRIEF_FORMATS[fmt].lower()}, {DECK_THEMES[theme]}. The numbers and sources are the same; "
                          "the choice of slides and the titles are standard. To change slides, open the editor on Team brief.\n\n" + lines))
                st.markdown(reply)
                st.download_button("Download .pptx", Path(hit["path"]).read_bytes(), key=f"dl_chat_{len(turns)}",
                                   file_name=Path(hit["path"]).name,
                                   mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
                say("user", question)
                say("assistant", reply)
        return
    resume = st.session_state.pop("resume", None)
    if resume and not question:
        question, asked, stream = resume["q"], resume.get("asked") or resume["q"], resume["stream"]
    elif question:
        asked, stream = (f"{question} (About: {ctx['title']}. {ctx['detail']})" if ctx["kind"] == "signal" else question), None
    if question:
        st.session_state["undo_ready"] = False
        # The signal card travels with the question so the agent knows which market and figure "this" means.
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            ans = stream_answer(asked, ensure_chat(), question, stream=stream)
            if ans is None:
                return
            show_answer(ans, text_done=True)
        say("user", question)
        say("assistant", ans.text, ans)
        focus_input()
        _rerun()  # the thread re-renders from the saved chat: follow-up buttons, no raw 'Follow up:' line


FOLLOW_LINE = re.compile(r"\n[ \t]*\**[ \t]*follow", re.I)  # a line that may become the closing 'Follow up:' line
TOOL_WORDS = {"get_signals": "reading this week's signals", "get_metric_trend": "pulling the trend",
              "compare_markets": "comparing submarkets", "generate_brief": "writing the brief",
              "brief_deck_data": "reading the deck data", "build_brief_pptx": "building the slides",
              "record_deal": "recording the deal", "list_our_deals": "listing our deals", "search_news": "searching the news"}


def stream_answer(asked: str, chat_id: str | None = None, question: str = "", stream=None, slot: str = "", **extra):
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
    status = st.status("Starting the Copilot…", expanded=False)
    stream = stream or engine.ask_streaming(asked, user, chat_id)
    tools = []
    label = {"text": "Starting the Copilot…", "since": datetime.now()}

    def show(text):
        label.update(text=text, since=datetime.now())
        status.update(label=text)
    stop = st.empty()
    stop.button("", icon=material("square"), key=f"stop_{chat_id}", type="tertiary",
                help="Stop: keep what has been written so far")
    st.session_state["partial"] = {"q": question or asked, "chat": chat_id, "text": "", "slot": slot, "stream": stream,
                                   "asked": asked, "owner": chat_owner(), "ed": dict(st.session_state.get("deck_ed") or {}), **extra}
    JOBS[(chat_owner(), slot)] = st.session_state["partial"]
    shown = {"text": ""}

    held_box = {"text": "", "line_start": True}  # the tail is held back so the closing 'Follow up:' line never shows

    def pieces():
        for e in stream.events():
            yield_to_clicks()  # Stop, close or a page link pressed in a dialog: handle it now, not at the end
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
                show(f"Working: {TOOL_WORDS.get(e['name'], e['name'].replace('_', ' '))}…")
                status.write(f"→ {e['name']}")
            elif e["event"] == "tick":  # nothing for a second: show the time passing (and let a Stop through)
                secs = int((datetime.now() - label["since"]).total_seconds())
                if secs >= 5:
                    status.update(label=f"{label['text']} {secs // 60}m {secs % 60:02d}s" if secs >= 60 else f"{label['text']} {secs}s")
            elif e["event"] == "reset":
                status.write("Your earlier conversation could not be loaded and was set aside; starting a new one.")
            elif e["event"] == "retry":
                status.write("Taking longer than expected; resuming from the last checkpoint.")
            elif e["event"] == "waiting":
                show("Waiting for your earlier request to finish…")
                status.write("Your earlier request" + (f" ({e['what']})" if e.get("what") else "")
                             + " is still running in the background; this one starts when it is done. Stop abandons the wait.")
    def pieces_then_rest():
        yield from pieces()
        # whatever was held: all of it unless it is the follow-up line (the buttons below take over)
        yield split_follow_ups(held_box["text"])[0] if held_box["text"] else ""
    text = st.write_stream(pieces_then_rest())
    stop.empty()
    st.session_state.pop("partial", None)  # finished: nothing to keep from a stop
    JOBS.pop((chat_owner(), slot), None)
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
                    "".join(f"\n- **Your alert:** {r['label']} ({r['why']})" for r in p["rules"]))
        st.caption(" ".join(p["reasons"]))
        c = st.columns(3)
        if c[0].button("Apply", type="primary", width="stretch", key="apply_setup"):
            st.session_state["applied_setup"] = fx.apply_setup(app.store, user, p)
            st.session_state.pop("proposal")
            say("assistant", "Applied. Monitor now opens on 'For you'"
                f"{', with ' + str(len(p['rules'])) + ' alert(s) of your own (Share with team on Monitor gives one to everyone)' if p['rules'] else ''}. "
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
        out.append(chip("Important", "warn"))
    if getattr(s, "_new", False):
        out.append(chip("New", "ok"))
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


def signal_card(s, i, lens="team", new: bool = False):
    in_brief = {b["id"]: b["added_by"] for b in app.store.brief_items()}
    glyph = ic({"up": "arrow-up", "down": "arrow-down"}.get(s.direction, "arrow-right"), 14)
    cls = "alert" if s.kind == "alert" else {"positive": "pos", "negative": "neg"}.get(s.tone, "neu")
    if s.kind == "alert":
        glyph = ic("bell", 14)
    why = esc(s.why)
    if (extra := fx.for_you(s, lens)):
        why += f' <i class="loa-muted">For you: {esc(extra)}</i>'
    if s.hot >= 60 and s.why_hot:
        why += f'<div class="loa-muted">{esc(s.why_hot)}</div>'
    if s.flag:
        why += f'<div class="loa-muted">{ic("triangle-alert", 13, "flag")}{esc(s.flag)}. Anyone can settle it on Sources.</div>'
    s._new = new  # arrived since this person last looked: a 'New' chip
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
        b = st.columns([1.4, 1.6, 1.4, 1.6], vertical_alignment="center")
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
        if b[2].button("Hide for me", icon=material("eye-off"), key=f"dn{i}{s.id}", type="tertiary",
                       help="Not relevant to you: hides it from your views only"):
            app.store.add_feedback(s.id, user, -1)
            st.toast("Hidden for you. The rest of the team still sees it.")
            st.rerun()
        if s.obs_id and not s.flag:
            with b[3].popover("Looks wrong", icon=material("triangle-alert"), help="Flag this number for the team. It stays usable with a warning "
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
        with st.form("share", clear_on_submit=True, border=False):
            text = st.text_area("What did you see or hear?", height=70, label_visibility="collapsed",
                                placeholder="A link, or what you heard: e.g. a broker says another floor at "
                                            "Triton Square is under offer")
            sent = st.form_submit_button("Share with the team", type="primary", width="stretch")
        if sent and text.strip():
            m = re.search(r"https?://\S+", text)
            url = m.group(0) if m else ""
            how = gather.HOW[2] if url else (gather.HOW[0] if re.search(r"\bbroker|agent\b", text, re.I) else gather.HOW[-1])
            app.store.add_to_inbox(text.replace(url, "").strip() or url, url, how, user)
            with st.spinner("Reading, checking for the same story, scoring…"):
                try:
                    st.success(engine.gather(user).text or "Shared. The information agent filed it; see team activity.")
                except AgentUnavailable as e:
                    st.info(f"Saved to the team inbox. The information agent files it on its next round. ({e})")


def watching_panel():
    """Alerts: a person's own rules fire in their 'For you' view; one becomes the team's only when its owner
    shares it, and only its owner can remove a team rule."""
    with st.container(border=True):
        st.html('<div class="loa-h2" style="font-size:17px">Alerts</div>')
        fired = {s.title for s in signals.watch_alerts("team") + signals.watch_alerts(user)}
        rules = app.store.watch_rules(user) + app.store.watch_rules("team")
        if not rules:
            st.caption("No rules yet. Add one below in your own words; it is yours until you share it.")
        for rr in rules:
            on = f"Alert: {rr['label']}" in fired
            mine = rr["role"] != "team"
            owner = rr.get("author") or ""
            c = st.columns([4, 1.3, 1.3], vertical_alignment="center")
            c[0].html(f'<span class="loa-dot {"red" if on else "green"}"></span><b>{esc(rr["label"])}</b>'
                      f'<div class="loa-muted" style="margin-left:17px">{"Fired" if on else "Not triggered"} · '
                      + ("yours" if mine else "team" + (f", shared by {esc(owner)}" if owner else "")) + "</div>")
            if mine and c[1].button("Share with team", key=f"shr{rr['id']}", type="tertiary",
                                    help="Everyone then sees it and gets the alert"):
                app.store.share_watch_rule(rr["id"])
                app.store.log("alert", user, f"shared the alert '{rr['label']}' with the team")
                st.rerun()
            if (mine or owner in ("", user)) and c[2].button("Remove", key=f"del{rr['id']}", type="tertiary"):
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
            st.rerun()
        st.caption("Your alerts fire in 'For you'; a shared one shows for the whole team. Email and Teams delivery "
                   "come after the PoC.")


def shared_answer_entry(a, when):
    """One shared Copilot answer in team activity: the question, the sharer's reason, the answer with its charts
    and sources; a colleague can carry it into their own Copilot; only the sharer can unshare it."""
    with st.expander(f"{a['author']} shared: {a['text'][:60]}", icon=material("share-2")):
        st.caption(f"Shared by {a['author']} · {when}" + (f" · \"{a['note']}\"" if a.get("note") else ""))
        m = app.store.shared_answer(a.get("ref") or "")
        if not (m or {}).get("content", "").lstrip("*#_ ").startswith(a["text"][:40]):  # unless the answer repeats it
            st.markdown(f"**{a['text']}**")
        if m:
            show_answer(Answer(m["content"], m["trace"], m["engine"]))
        else:
            st.markdown(a["answer"] or "")
        c = st.columns(2)
        if c[0].button("Continue in my Copilot", icon=material("message-square"), key=f"cont{a['id']}", type="tertiary",
                       help="Starts a new conversation of your own with this question and answer in it"):
            chat_id = app.store.new_chat(chat_owner(), a["text"])
            app.store.add_chat_message(chat_id, "user", a["text"])
            app.store.add_chat_message(chat_id, "assistant", m["content"] if m else (a["answer"] or ""),
                                       m["trace"] if m else None, m["engine"] if m else "")
            open_chat(chat_id)
            open_copilot()
        if a["author"] == user and c[1].button("Unshare", icon=material("link-off"), key=f"unsh{a['id']}", type="tertiary"):
            app.store.unshare_answer(int(a["ref"]))
            st.rerun()


def activity_panel():
    with st.container(border=True):
        st.html('<div class="loa-h2" style="font-size:17px">Team activity</div>')
        acts = app.store.activity(8)
        if not acts:
            st.caption("Nothing yet. Uploads, checks, shared alerts, brief picks and the Copilot answers colleagues "
                       "choose to share show here.")
        for a in acts:
            when = lib.when(a.get("ts"))
            if a["kind"] == "auto":
                st.html(f'<div><span class="loa-dot green"></span>Auto-update: {esc(a["text"])}'
                        f'<div class="loa-muted" style="margin-left:17px">{esc(when)}</div></div>')
            elif a["kind"] == "ask":  # a Copilot answer its owner chose to share
                shared_answer_entry(a, when)
            else:
                dot = '<span class="loa-dot blue" style="margin-right:4px"></span>' if a["kind"] == "internal" else ""
                st.html(f'<div style="display:flex;gap:8px;margin:6px 0"><span class="loa-av">'
                        f'{esc(a["author"][:1].upper())}</span><div>{dot}{esc(a["author"])} {esc(a["text"])}'
                        f'<div class="loa-muted">{esc(when)}</div></div></div>')


def freshness_line():
    """Where the team's data stands, in one strip: open data collected by the agent, the latest report a
    colleague uploaded, when news was checked, what waits for a person, and reports probably out but not uploaded."""
    last = lib.last_auto_update(app.store)
    due = [d for d in lib.due_reports(app.store, app.config) if d["missing"]]
    fdue = follow.due_uploads(app.store)
    parts = [f'<span><span class="loa-dot green"></span><b>Auto-updated</b> {esc(lib.when(last["ts"]) if last else "never")}</span>']
    parts.append(f'<span><b>Market data to</b> {esc(an.period_label(an.latest_period(app.store)))}</span>')
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
    from core.summary import lta_source
    for m in ("take_up_msqft", "investment_gbp_bn"):  # the long-term averages may come from an older report
        sid = lta_source(app.store, "London", m)
        if sid and sid not in {s.get("source_id") for s in (vac, inv) if s}:
            ref = an.source_ref(app.store, sid)
            if f"Long-term averages: {ref['title']}" not in [c[0] for c in chips]:
                chips.append((f"Long-term averages: {ref['title']}", ref["channel"], ref["url"]))
    with st.container(border=True):
        st.html(kicker("Team summary")
                + f'<div class="loa-prose">{esc(" ".join(team_summary(app.store, team_sigs)))}</div>'
                + '<div style="margin-top:10px">'
                + "".join(chip(t, "src auto" if ch == "auto" else "src", u) for t, ch, u in chips) + "</div>")


def focus_row(mine, n_hidden: int = 0):
    c = st.columns([5, 1.6], vertical_alignment="center")
    if n_hidden:
        with c[0]:
            if st.button(f"Show {n_hidden} hidden", icon=material("eye"), key="unhide", type="tertiary",
                         help="Signals you hid with 'Hide for me'"):
                app.store.unhide_signals(user)
                st.rerun()
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
    page_header("This week in London offices", f"{date.today():%A %-d %b %Y} · market data to "
                f"{an.period_label(an.latest_period(app.store))} · rates and news to date · shared with the whole team")
    freshness_line()
    hidden = app.store.hidden_signals(user)
    team_sigs = [s for s in signals.for_role("team") if s.id not in hidden]
    dg = signals.digest(app.config.get("digest", {}).get("team_size", 5), user=user, hidden=hidden)
    last_seen = dg["last_seen"]
    if dg["new_since"]:
        st.html(f'<div class="loa-fresh" style="margin-top:-8px">{ic("sparkles", 14, "accent")}<b>{dg["new_since"]} new</b> '
                f'since you last looked ({esc(lib.when(last_seen))})</div>')
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
        focus_row(mine, len(hidden))
        rest = []
        if view == "For you" and mine:
            sigs, lens = signals.diversify(signals.for_focus(user, mine)), mine.get("lens", "team")
        else:
            if view == "For you":
                st.info("You haven't set up your view yet. Press 'Set up my focus' and describe your job in one "
                        "sentence. Meanwhile, here is the whole team's list.")
            # the team view is today's pick: alerts and flagged figures always, then the best of the rest with
            # one card per story and no more than two per measure or submarket; everything else folds below
            sigs, rest, lens = dg["picked"], dg["rest"], "team"
            st.caption(f"Worth a look today: {len(sigs)} of {len(team_sigs)} signals. One card per story, at most "
                       f"two per measure or submarket; the rest fold below.")
        if not sigs:
            st.info("Nothing in your focus changed. Widen it by telling the Copilot, e.g. 'more vacancy'.")
        for i, s in enumerate(sigs):
            signal_card(s, i, lens, new=bool(last_seen and s.discovered and s.discovered > last_seen))
        if rest:
            folded = " · ".join(f"{k} {v}" for k, v in sorted(dg["folded"].items(), key=lambda kv: -kv[1]))
            with st.expander(f"{len(rest)} more: {folded}", icon=material("chevron-down")):
                by_cat: dict[str, list] = {}
                for s in rest:
                    label = tx.CATEGORY_LABELS.get(s.category, s.category) if s.kind == "news" else \
                        KIND_FOLD.get(s.kind, s.kind)
                    by_cat.setdefault(label, []).append(s)
                for label, group in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
                    st.html(kicker(f"{label} · {len(group)}"))
                    for i, s in enumerate(group):
                        signal_card(s, f"r{i}", lens, new=bool(last_seen and s.discovered and s.discovered > last_seen))
        app.store.mark_seen(user, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    with side:
        share_panel()
        watching_panel()
        activity_panel()


# ---------------------------------------------------------------- copilot page
def copilot_page():
    st.session_state["page"] = "copilot"
    st.session_state["_in_dialog"] = False
    if st.session_state.get("copilot_ctx", {}).get("kind") != "setup":  # a setup started from the page carries on
        st.session_state["copilot_ctx"] = {"kind": "page", "page": "copilot"}
    st.html('<span class="loa-cp-page"></span>')  # the stylesheet's hook for the page-only layout rules
    st.html('<div class="loa-notice">Evaluation PoC: market figures are restated from public Knight Frank reports '
            '(evaluation only, not for AI or commercial use); Bank Rate and news are collected live; internal deals '
            'and colleague names are demo data.</div>')
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
            "rules": ("Slides picked by rules" + ("" if engine.ready else " (Copilot offline)"),
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


def brief_fingerprint(fmt: str) -> str:
    """What the brief is made from: the library's data fingerprint, the format, and whether a model writes the
    headline. Same fingerprint, same brief: it is read back instead of written again."""
    return f"{app.store.data_fingerprint()}-{fmt}-{'llm' if getattr(app.llm, 'available', False) else 'rules'}"


def deck_fingerprint(fmt: str, theme: str) -> str:
    return f"{app.store.data_fingerprint()}-{fmt}-{theme}-{'copilot' if engine.ready else 'rules'}"


def cached_deck(fmt: str, theme: str) -> dict | None:
    """The deck built from this data for this format and theme, if its files are still there."""
    fp = deck_fingerprint(fmt, theme)
    hit = app.store.cached("deck", fp)
    if hit and not (hit["path"] and Path(hit["path"]).exists()):
        app.store.forget_cached("deck", fp)  # data/ was cleared: build again when asked
        return None
    return hit


MAX_VERSIONS = 20


def store_deck(fmt, theme, built, how, note, shown, edits=None, versions=None, ver=1, pptx=None):
    """Remember a built deck (its spec, slides, PDF and page images) against the data fingerprint. `versions`
    are the earlier states of this deck (newest last), each with its own files, so Undo needs no rebuild."""
    fp = deck_fingerprint(fmt, built["theme"])
    pptx = pptx or (app.root / "data" / "exports" / "decks" / fp / f"v{ver}" / f"london-office-team-brief-{fmt}-{built['theme']}.pptx")
    data = {"theme": built["theme"], "format": fmt, "how": how, "note": note if how == "rules" and note else "",
            "slides": [f"{s['title']}" + (f" — {w}" if w else "") for s, w in zip(built["slides"], built.get("why") or [])],
            "titles": [s["title"] for s in built["slides"]], "layouts": [s["layout"] for s in built["slides"]],
            "problems": built.get("problems") or [], "spec": built.get("spec"), "edits": edits or [],
            "pdf": shown["pdf"], "pages": shown["pages"], "preview_note": shown["why"],
            "versions": (versions or [])[-MAX_VERSIONS:], "ver": ver}
    app.store.save_cached("deck", fp, data, str(pptx))
    return fp


def deck_version(hit) -> dict:
    """The deck as it is now, kept aside before an edit replaces it: everything Undo needs to bring it back."""
    d = hit["data"]
    return {k: d.get(k) for k in ("theme", "format", "how", "note", "slides", "titles", "layouts", "problems", "spec",
                                   "pdf", "pages", "preview_note", "ver")} | \
        {"path": hit["path"], "instruction": (d.get("edits") or ["build"])[-1], "ts": datetime.now().isoformat(timespec="seconds"),
         "edits": list(d.get("edits") or [])}


def restore_version(fmt, theme, v, versions, instruction=""):
    """Puts an earlier version back as the current deck (its files are still in their own folder)."""
    fp = deck_fingerprint(fmt, v["theme"])
    data = {k: v.get(k) for k in ("theme", "format", "how", "note", "slides", "titles", "layouts", "problems", "spec",
                                   "pdf", "pages", "preview_note", "ver")} | \
        {"edits": list(v.get("edits") or []), "versions": versions[-MAX_VERSIONS:]}
    app.store.save_cached("deck", fp, data, v["path"])
    if v["theme"] != theme:
        app.store.forget_cached("deck", deck_fingerprint(fmt, theme))
    return fp


def deck_folder(fmt, built, ver=1) -> Path:
    """The version's own folder under data/exports/decks/<fingerprint>/v<n>/, with the .pptx copied in."""
    folder = app.root / "data" / "exports" / "decks" / deck_fingerprint(fmt, built["theme"]) / f"v{ver}"
    folder.mkdir(parents=True, exist_ok=True)
    pptx = folder / f"london-office-team-brief-{fmt}-{built['theme']}.pptx"
    pptx.write_bytes(Path(built["path"]).read_bytes())
    return pptx


class EditorUI:
    """Where a build or an edit shows itself inside the slide editor: the header's status text, the thumbnail
    slots (planned first, then each rendered page), the stage, and the Copilot's words in the chat column.
    Outside the editor the plain st.status is all there is."""

    def __init__(self, head_ph=None, thumbs_ph=None, stage_ph=None):
        self.head_ph, self.thumbs_ph, self.stage_ph = head_ph, thumbs_ph, stage_ph
        self._status = None
        self.slots = []

    @property
    def status(self):
        if self._status is None:  # made where the first message lands, so it sits under the streamed answer
            self._status = st.status("Laying out the slides…", expanded=False)
        return self._status

    def say(self, label):
        self.status.update(label=label)
        if self.head_ph is not None:
            self.head_ph.html(f'<div class="loa-muted loa-ed-status">{ic("loader-circle", 13, "spin")}{esc(label)}</div>')

    def plan(self, titles, layouts):
        """The storyline is known: every slide gets a hatched 'Planned' frame before it is laid out."""
        self.slots = []
        if self.thumbs_ph is None:
            return
        box = self.thumbs_ph.container()
        with box:
            for n, (t, lay) in enumerate(zip(titles, layouts), 1):
                slot = st.empty()
                slot.html(f'<div class="loa-ed-planned"><span class="loa-ed-num">{n}</span><div class="loa-ed-frame">'
                          f'Planned: {esc(lay)}</div><div class="loa-ed-lay">{esc(t)}</div></div>')
                self.slots.append(slot)

    def page(self, n, total, path, title, layout):
        self.say(f"Laying out slide {n} of {total}: {layout or title}")
        if n - 1 < len(self.slots):
            with self.slots[n - 1].container():
                st.html(f'<div class="loa-ed-num">{n}</div>')
                st.image(path, width="stretch")
                st.html(f'<div class="loa-ed-lay">{esc(layout)}</div>')
        if self.stage_ph is not None:
            self.stage_ph.image(path, width="stretch")

    def done(self, label, state="complete"):
        self.status.update(label=label, state=state)
        if self.head_ph is not None:
            self.head_ph.html(f'<div class="loa-muted loa-ed-status">{esc(label)}</div>')


def paint_pages(pptx, folder, built, ui: EditorUI, on_page=None) -> dict:
    """The PDF, then one image per slide, each shown the moment it is laid out."""
    titles = [s["title"] for s in built["slides"]]
    layouts = [s["layout"] for s in built["slides"]]
    ui.plan(titles, layouts)
    ui.say("Rendering the deck to PDF…")
    out = {}
    job = threading.Thread(target=lambda: out.update(r=_preview.render_pdf(pptx, folder)), daemon=True)
    job.start()
    while job.is_alive():  # LibreOffice takes a few seconds: stay responsive to Stop and the close button
        job.join(0.2)
        yield_to_clicks()
    pdf, why = out.get("r") or ("", "PDF conversion failed")
    pages = []
    if pdf:
        total = _preview.page_count(pdf)
        for n in range(1, total + 1):
            yield_to_clicks()
            p = _preview.render_page(pdf, n, folder)
            if not p:
                break
            pages.append(p)
            ui.page(n, total, p, titles[n - 1] if n - 1 < len(titles) else "", layouts[n - 1] if n - 1 < len(layouts) else "")
            if on_page:
                on_page({"pdf": pdf, "pages": list(pages), "why": ""})
    return {"pdf": pdf, "pages": pages, "why": why or ("" if pages else "page images need poppler (pdftoppm)")}


def build_deck_now(fmt, theme, ui: EditorUI | None = None, chat_id: str | None = None, stream=None):
    """The Copilot plans the deck from this week's data; without it the rule planner picks from the same stories.
    The .pptx, its PDF and one image per slide are kept under data/exports/decks/<fingerprint>/ and remembered
    against the data fingerprint, so the same data never builds twice. In the slide editor `ui` shows each slide
    as it is laid out, and the Copilot's planning streams like any answer (status line, Stop) into the chat
    column. Returns (how, note, answer)."""
    ui = ui or EditorUI()
    built, how, note, ans = None, "", "", None
    if engine.ready:
        ui.say("The Copilot is reading this week's data and planning the slides…")
        try:
            ans = stream_answer(engine.deck_ask(fmt, theme), chat_id, "Build the slides",
                                stream=stream or engine.build_deck_streaming(fmt, theme, user, chat_id), slot="_deck", kind="build")
            if ans is not None:
                built, how, note = engine.built_deck(ans), "copilot", ans.text
        except AgentUnavailable as e:
            note = str(e)
    if not built:  # fallback: the rule-based planner, still this week's stories, no model
        ui.say("Picking the slides by rules from this week's data…")
        out = app.call("build_brief_pptx", {"format": fmt, "theme": theme}, user)
        built, how = out["data"] if out["data"].get("path") else None, "rules"
        ans = ans or Answer(out["summary"], [{"tool": "build_brief_pptx", "args": {"format": fmt, "theme": theme}, "result": out}], "rules")
        if not built:
            ui.done("Not built", "error")
            st.warning(out["summary"])
            return "", "", None
    pptx = deck_folder(fmt, built, 1)
    store_deck(fmt, theme, built, how, note, {"pdf": "", "pages": [], "why": "rendering"})  # a Stop keeps what is built
    shown = paint_pages(pptx, pptx.parent, built, ui, lambda sh: store_deck(fmt, theme, built, how, note, sh))
    store_deck(fmt, theme, built, how, note, shown)
    ui.done(f"{len(built['slides'])} slides · storyline {'chosen by the Copilot' if how == 'copilot' else 'picked by rules'} "
            "from this week's data")
    app.store.log("brief", user, f"built the team brief slides ({fx.BRIEF_FORMATS[fmt].lower()}, {built['theme']}, "
                                 f"{'storyline by the Copilot' if how == 'copilot' else 'rule-picked storyline'})")
    return how, note, ans


# ---------------------------------------------------------------- slide editor (a floating window)
EDIT_PILLS_ON = ["Make slide 2's title shorter", "Add two more slides", "Swap slides 2 and 3", "Shorten to 4 slides"]
EDIT_PILLS_OFF = ["Remove slide 3", "Add a slide on rents", "Swap slides 2 and 3", "Theme forest"]
APPLY_PENDING, KEEP_PENDING = "Apply that revision", "Keep the deck as it is"
THEME_SHORT = {"navy-gold": "Navy gold", "editorial-cream": "Editorial", "data-white": "Data white",
               "charcoal-amber": "Charcoal", "forest-cream": "Forest"}


def deck_chat_title(fmt, theme) -> str:
    return f"{DECK_CHAT_PREFIX}{fx.BRIEF_FORMATS[fmt]} · {THEME_SHORT.get(theme, theme)}"


def open_deck_editor(fmt, theme, build=False, sel=1):
    """Marks the editor open; deck_panel shows it at the end of the run, and it stays open across reruns until
    closed or dismissed. The conversation about this deck (the same saved chats as the Copilot, under the
    person's name) comes back with it; Build again starts a new one."""
    old = st.session_state.get("deck_ed") or {}
    st.session_state["deck_ed"] = {"fmt": fmt, "theme": theme, "build": build, "sel": sel, "open": True}
    if build or old.get("fmt") != fmt or old.get("theme") != theme or not st.session_state.get("chat_id_deck"):
        title = deck_chat_title(fmt, theme)
        chats = [] if build else [c for c in app.store.chats(chat_owner()) if c["title"] == title]
        open_chat(chats[0]["id"] if chats else None, "_deck")
        st.session_state["chat_owner_deck"] = chat_owner()


def _close_editor():
    if st.session_state.get("deck_ed"):
        st.session_state["deck_ed"]["open"] = False


def _ed_rerun():
    _rerun()


def _deck_theme_pick():
    """The theme control in the header. A deck that has been edited keeps its edits: the same spec is built again
    on the new theme (the path a 'theme forest' instruction takes); an untouched deck opens that theme's own
    build, planning it if it does not exist yet."""
    ed = st.session_state["deck_ed"]
    v = st.session_state.get("ed_theme")
    if v and v != ed["theme"]:
        hit = cached_deck(ed["fmt"], ed["theme"])
        if hit and (hit["data"].get("edits") or hit["data"].get("versions")) and hit["data"].get("spec"):
            st.session_state["deck_ask"] = (f"theme {v}", True)
            return
        ed.update(theme=v, sel=1, build=not cached_deck(ed["fmt"], v), theme_sync=True)
        open_chat(None, "_deck")
        st.session_state["deck_theme_want"] = (ed["fmt"], v)


def deck_history(sfx: str):
    """The person's conversations about slides, newest first; one click brings a conversation back."""
    chats = [c for c in app.store.chats(chat_owner()) if (c["title"] or "").startswith(DECK_CHAT_PREFIX)]
    if not chats:
        st.caption("No conversations about slides yet. They are kept under your name.")
        return
    current = st.session_state.get("chat_id_deck")
    for c in chats:
        if st.button((c["title"] or "Untitled")[:60], key=f"dhist_{sfx}_{c['id']}", width="stretch",
                     help=f"{c['messages']} messages", type="primary" if c["id"] == current else "secondary"):
            open_chat(c["id"], "_deck")
            _ed_rerun()
        st.caption(f"{when(c['updated'])} · {c['messages']} messages")


def adopt_deck(ed, hit, built, instruction, ui: EditorUI, how, note, force=False) -> str:
    """A revised deck came back from the Copilot or the rule editor. If it dropped a slide (by id) that nobody
    asked to drop, it is held back and the person gets Apply / Keep buttons; otherwise the current deck is kept
    as a version, the new one is filed in its own folder, the pages are painted one by one and the reply
    describes what actually changed, slide by slide."""
    fmt, theme = ed["fmt"], ed["theme"]
    d = hit["data"]
    old_spec = d.get("spec")
    zh = _de.is_zh(instruction)
    new_spec = built.get("spec") or {"theme": built["theme"], "slides": [{"title": x["title"], "layout": x["layout"]} for x in built["slides"]]}
    new_ids = {x.get("id") for x in new_spec["slides"]}
    gone = [x for x in (old_spec or {}).get("slides", []) if x.get("id") and x.get("id") not in new_ids]
    if gone and not force and not _de.asks_removal(instruction):
        ui.done("Waiting for your word", "error")
        ed["confirm"] = {"built": built, "instruction": instruction, "how": how, "note": note}
        items = "；".join(f"第 {i} 頁「{x.get('title', '')}」" for i, x in enumerate(old_spec["slides"], 1) if x in gone) if zh else \
            "; ".join(f"slide {i} \"{x.get('title', '')}\"" for i, x in enumerate(old_spec["slides"], 1) if x in gone)
        return (f"這次修改會刪掉你沒有要求刪的頁：{items}。要套用嗎？按下面的「套用」或「保持原樣」。" if zh else
                f"That revision would also drop {items}, which you did not ask for. Apply it anyway, or keep the deck as "
                f"it is? Use the two buttons below.")
    ed.pop("confirm", None)
    versions = list(d.get("versions") or []) + [deck_version(hit)]
    ver = int(d.get("ver") or 1) + 1
    edits = list(d.get("edits") or []) + [instruction]
    pptx = deck_folder(fmt, built, ver)
    keep = lambda sh: store_deck(fmt, theme, built, how, note, sh, edits, versions, ver, pptx)
    shown = paint_pages(pptx, pptx.parent, built, ui, keep)
    keep(shown)
    if built["theme"] != theme:  # the theme changed: the deck now lives under that theme
        app.store.forget_cached("deck", deck_fingerprint(fmt, theme))
        ed.update(theme=built["theme"], theme_sync=True)
        st.session_state["deck_theme_want"] = (fmt, built["theme"])
    ed["sel"] = min(ed.get("sel") or 1, len(built["slides"]))
    ui.done(f"{len(built['slides'])} slides · edited {len(edits)} time{'s' if len(edits) != 1 else ''} in the editor")
    app.store.log("brief", user, f"edited the team brief slides: {instruction[:80]}")
    reply = _de.describe(old_spec, new_spec, instruction) if old_spec else \
        (f"已重建，共 {len(built['slides'])} 頁。" if zh else f"Rebuilt: {len(built['slides'])} slides.")
    if built.get("problems"):
        reply += ("\n\n檢查發現：" if zh else "\n\nThe check flagged: ") + "; ".join(built["problems"])
    return reply


def refusal_text(err: dict, instruction: str) -> str:
    """Why a build was refused, in the instruction's language and with the figure the data does have."""
    zh = _de.is_zh(instruction)
    latest = err.get("latest") or {}
    names = {"vacancy_pct": ("vacancy", "空置率"), "take_up_msqft": ("take-up", "去化量"), "investment_gbp_bn": ("investment", "投資額"),
             "active_requirements_msqft": ("active requirements", "需求量"), "prime_rent": ("prime rent", "租金")}
    lines = []
    hints = {"vacancy_pct": ("vacancy", "空置"), "take_up_msqft": ("take-up", "take up", "去化"), "investment_gbp_bn": ("investment", "投資", "投资"),
             "active_requirements_msqft": ("requirement", "demand", "需求"), "prime_rent": ("rent", "租金")}
    grouped: dict[tuple, dict] = {}
    for r in err.get("refused_numbers") or []:  # the same figure in a slide's title and notes is one refusal
        g = grouped.setdefault((r["slide"], tuple(r["numbers"])), {"slide": r["slide"], "numbers": r["numbers"], "where": [], "text": ""})
        g["where"].append(r["where"])
        g["text"] += " " + (r.get("text") or "")
    wn = {"title": ("title", "標題"), "so_what": ("so-what", "結論"), "notes": ("notes", "備註")}
    for r in grouped.values():
        nums = "、".join(r["numbers"]) if zh else ", ".join(r["numbers"])
        low = r["text"].lower()
        about = {k: v for k, v in latest.items() if any(w in low for w in hints.get(k, ()))} or latest
        now = "；".join(f"目前{names.get(k, (k, k))[1]} {v}" for k, v in about.items()) if zh else \
            "; ".join(f"{names.get(k, (k, k))[0]} is {v}" for k, v in about.items())
        where = ("和".join(wn.get(w, (w, w))[1] for w in r["where"]) if zh else " and ".join(wn.get(w, (w, w))[0] for w in r["where"]))
        lines.append(f"第 {r['slide']} 頁{where}裡的 {nums} 不在本週數據裡（{now}），所以沒有套用。" if zh else
                     f"{nums} in slide {r['slide']}'s {where} is not in this week's data ({now}), so it was not applied.")
    if not lines:
        why = err.get("error") or ""
        lines.append(f"沒有建成：{why}" if zh else f"Not built: {why}")
    if any(r["where"] in ("title", "so_what") for r in err.get("refused_numbers") or []):
        lines.append("標題和結論只接受最新一期的值；要引用舊值請寫明期間，例如「Q1 2024 的 9.9%」。" if zh else
                     "Titles and so-whats quote the latest value; name the period to quote an earlier one (\"9.9% in Q1 2024\").")
    return " ".join(lines)


def rebuild_from_spec(ed, hit, new, instruction, ui: EditorUI, how, note) -> Answer:
    """Builds the revised spec by rules and files it (or explains the refusal)."""
    fmt = ed["fmt"]
    zh = _de.is_zh(instruction)
    ui.say("Building the slides again…")
    out = app.call("build_brief_pptx", {"format": fmt, "theme": new["theme"], "spec": new}, user)
    built = out["data"] if out["data"].get("path") else None
    if not built:
        ui.done("Not built", "error")
        return Answer(refusal_text(out["data"], instruction) if out["data"].get("error") else (f"沒有建成：{out['summary']}" if zh else f"Not built: {out['summary']}"))
    reply = adopt_deck(ed, hit, built, instruction, ui, how, note)
    return Answer(reply, [{"tool": "build_brief_pptx", "args": {"format": fmt, "theme": new["theme"]}, "result": out}], "rules")


def edit_deck(ed, hit, instruction, via_rules, chat_id, ui: EditorUI, stream=None) -> Answer | None:
    """One instruction from the editor's chat (or a stage button): the Copilot revises the spec and builds
    again, streamed like any Copilot answer (status line, Stop); plain commands and the buttons go through the
    rule editor, which also stands in when the Copilot is offline or fails. Undo restores an earlier version
    without a build; 'make an IC version' switches the format. Returns the turn to save, or None after a Stop."""
    fmt, theme = ed["fmt"], ed["theme"]
    d = hit["data"]
    spec = d.get("spec")
    zh = _de.is_zh(instruction)
    sel = ed.get("sel") or 1
    pending = ed.get("confirm")
    if pending and instruction in (APPLY_PENDING, KEEP_PENDING, "套用", "保持原樣"):
        ed.pop("confirm", None)
        if instruction in (KEEP_PENDING, "保持原樣"):
            ui.done("Kept as it was")
            return Answer("好，簡報維持原樣。" if _de.is_zh(pending["instruction"]) else "Kept: the deck is as it was.")
        reply = adopt_deck(ed, hit, pending["built"], pending["instruction"], ui, pending["how"], pending["note"], force=True)
        return Answer(reply, [], "rules")
    ed.pop("confirm", None)
    if not spec:
        return Answer("這份簡報是在編輯器出現之前建的，沒有可改的 spec，請先按 Build again。" if zh else
                      "This deck was built before the editor existed, so I have no spec to change. Press Build again first.")
    how, note = d.get("how", "rules"), d.get("note", "")
    stories = _bd.deck_data(app.ctx, fmt).get("stories") or []
    if len(stories) == 0 and not d.get("slides"):
        return Answer("資料庫還沒有數據，請先在 Sources 更新，再建簡報。" if zh else "The library has no data yet: update it on Sources first, then build.")
    # the rule editor first: undo, format switches and plain commands never need the Copilot
    new, said = _de.apply(instruction, spec, stories, sel)
    if isinstance(new, dict) and "undo" in new:
        versions = list(d.get("versions") or [])
        if not versions:
            ui.done("No earlier version")
            return Answer("這是第一版，沒有更早的版本可以回。" if zh else "This is the first version; there is nothing earlier to go back to.")
        idx = 0 if new["undo"] == "first" else (new["undo"][1] - 1 if isinstance(new["undo"], tuple) else len(versions) - 1)
        idx = min(max(idx, 0), len(versions) - 1)
        v = versions[idx]
        restore_version(fmt, theme, v, versions[:idx], instruction)
        if v["theme"] != theme:
            ed.update(theme=v["theme"], theme_sync=True)
            st.session_state["deck_theme_want"] = (fmt, v["theme"])
        ed["sel"] = min(sel, len(v.get("titles") or [1]))
        ui.done(f"Back to version {v.get('ver', idx + 1)}")
        what = v.get("instruction") or "build"
        return Answer((f"已回到第 {v.get('ver', idx + 1)} 版（{'初版' if what == 'build' else '「' + what + '」之後'}），共 {len(v.get('titles') or [])} 頁。" if zh else
                       f"Back to version {v.get('ver', idx + 1)} ({'the first build' if what == 'build' else 'after \"' + what + '\"'}): "
                       f"{len(v.get('titles') or [])} slides."), [], "rules")
    if isinstance(new, dict) and "switch" in new:
        want = new["switch"]
        if want == fmt:
            return Answer(said)
        ed.update(fmt=want, theme="data-white" if want == "ic" else "navy-gold", build=True, sel=1)
        st.session_state["deck_theme_want"] = (ed["fmt"], ed["theme"])
        open_chat(None, "_deck")
        return Answer(said, [], "rules")
    # a plain command the rule editor understands is applied by rules even with the Copilot on: it is exact,
    # instant, answers in the instruction's language, and never files anything in the library
    if new or (said and "Copilot" not in said and said not in (_de.HELP, _de.HELP_ZH)):
        via_rules = True
    if engine.ready and (not via_rules or stream is not None):
        ans = stream_answer(engine.deck_edit_ask(fmt, theme, spec, instruction, sel), chat_id, instruction,
                            stream=stream or engine.edit_deck_streaming(fmt, theme, spec, instruction, user, chat_id, sel),
                            slot="_deck", kind="edit")
        if ans is None:  # the Copilot failed (a Stop never returns here): the rule editor stands in where it can
            if new:
                out = rebuild_from_spec(ed, hit, new, instruction, ui, how, note)
                out.text = ("Copilot 這次沒回應，已用規則版完成。" if zh else "The Copilot did not answer this time; done by rules instead.") + "\n\n" + out.text
                return out
            return Answer(("Copilot 這次沒回應。" if zh else "The Copilot did not answer this time. ") + said)
        built = engine.built_deck(ans)
        if not built:  # the Copilot explained instead of building (or could not): its words are the answer
            err = next((t["result"].get("data") for t in reversed(ans.trace)
                        if t["tool"] == "build_brief_pptx" and (t["result"].get("data") or {}).get("refused_numbers")), None)
            if err and not all(n in ans.text for r in err["refused_numbers"] for n in r["numbers"]):
                return Answer(refusal_text(err, instruction) + ("\n\n" + ans.text if ans.text.strip() else ""), ans.trace, ans.engine)
            return ans
        reply = adopt_deck(ed, hit, built, instruction, ui, how, note)
        return Answer(reply, ans.trace, ans.engine)
    if not new:
        ui.done("No change")
        return Answer(said)
    return rebuild_from_spec(ed, hit, new, instruction, ui, how, note)


def _ed_ask(instruction, sel=None):
    ed = st.session_state["deck_ed"]
    st.session_state["deck_ask"] = (instruction, True)
    if sel:
        ed["sel"] = sel
    _ed_rerun()


@st.dialog("Slides", width="large", on_dismiss=_close_editor)
def deck_editor():
    """The slides as a floating window laid out like a presentation app: thumbnails with page numbers on the
    left, the chosen slide large in the middle, and on the right the same Copilot conversation as everywhere else
    in the app (saved under the person's name, streamed with a Stop, action row under each answer, follow-ups),
    here about this deck. Build slides opens it too: the Copilot's planning streams into the conversation, every
    slide first appears as 'Planned', and each thumbnail fills in as that slide is laid out."""
    st.session_state["_in_dialog"] = True
    if st.session_state.get("ed_close"):  # closed mid-run: leave the run going for "Slides · working…" to pick up
        _close_editor()
        st.rerun()
    ed = st.session_state.get("deck_ed") or {}
    fmt, theme = ed.get("fmt", "board"), ed.get("theme", "navy-gold")
    sfx = "e"
    st.html('<span class="loa-deck-ed"></span>')
    chat_id, turns = current_chat("_deck")
    turns = absorb_partial(chat_id, turns, "_deck")
    asked = st.session_state.pop("deck_ask", None)  # a pill, Ask again, the regenerate button or a stage button
    if isinstance(asked, str):
        asked = (asked, False)
    resume = st.session_state.pop("resume_deck", None)  # the window was closed or the page switched mid-run
    if resume and resume.get("kind") == "build":
        ed["build"] = True
    elif resume and not asked:
        asked = (resume["q"], False)
    building = bool(ed.get("build"))
    hit = None if building else cached_deck(fmt, theme)
    d = (hit or {}).get("data") or {}
    titles, layouts = d.get("titles") or [], d.get("layouts") or []
    pages = [q for q in d.get("pages") or [] if Path(q).exists()]
    n = len(pages)
    sel = min(max(ed.get("sel") or 1, 1), max(n, 1))
    busy = building or bool(asked)
    # header: name, theme, status, Stop / Build again + Download, history, close
    with st.container(key="deck_top", horizontal=True, vertical_alignment="center", gap="small"):
        st.html(f'<div class="loa-cp-title">{ic("presentation", 18, "accent")}Slides <small>{esc(fx.BRIEF_FORMATS[fmt])}</small></div>',
                width="content")
        if ed.pop("theme_sync", False):
            st.session_state["ed_theme"] = theme  # an instruction or Undo changed the theme: the control follows
        st.segmented_control("Theme", list(THEME_SHORT), format_func=THEME_SHORT.get, key="ed_theme",
                             default=theme, label_visibility="collapsed", on_change=_deck_theme_pick,
                             disabled=busy, width="content")
        head_ph = st.empty()
        if not busy:
            edits = len(d.get("edits") or [])
            head_ph.html(f'<div class="loa-muted loa-ed-status">{n} slides · storyline '
                         f'{"chosen by the Copilot" if d.get("how") == "copilot" else "picked by rules"} from this week\'s data'
                         + (f' · edited {edits} time{"s" if edits != 1 else ""}' if edits else "") + "</div>"
                         if hit else '<div class="loa-muted loa-ed-status">Not built yet</div>')
        if not building:
            if st.button("Build again", icon=material("refresh-cw"), key="ed_rebuild", width="content",
                         help="Plan the deck again from this week's data", disabled=busy):
                ed.update(build=True, sel=1)
                open_chat(None, "_deck")
                _ed_rerun()
            if hit:
                st.download_button("Download .pptx", Path(hit["path"]).read_bytes(), file_name=Path(hit["path"]).name,
                                   mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                   key="ed_dl_pptx", type="primary", icon=material("download"), width="content")
                if d.get("pdf") and Path(d["pdf"]).exists():
                    st.download_button("PDF", Path(d["pdf"]).read_bytes(), file_name=Path(hit["path"]).stem + ".pdf",
                                       mime="application/pdf", key="ed_dl_pdf", width="content")
        versions = d.get("versions") or []
        if hit and not building:
            if st.button("", icon=material("undo-2"), key="ed_undo", width="content", help="Undo the last change",
                         disabled=busy or not versions):
                _ed_ask("undo", sel)
            if versions:
                with st.popover(f"v{d.get('ver', 1)}", help="Earlier versions of this deck", width="content", disabled=busy):
                    st.caption("Click a version to go back to it.")
                    for i, v in enumerate(versions):
                        what = v.get("instruction") or "build"
                        if st.button(f"v{v.get('ver', i + 1)} · {'first build' if what == 'build' else what[:40]}",
                                     key=f"ed_ver_{i}", width="stretch", type="tertiary",
                                     help=f"{len(v.get('titles') or [])} slides · {v.get('ts', '')}"):
                            _ed_ask(f"restore version {v.get('ver', i + 1)}", sel)
        with st.popover("", icon=material("history"), help="Your conversations about slides", width="content"):
            deck_history(sfx)
        if st.button("", icon=material("x"), key="ed_close", help="Close · Esc", width="content"):
            _close_editor()
            st.rerun()
    cols = st.columns([1.05, 3.2, 1.95], gap="medium")
    with cols[0]:
        with st.container(key="deck_thumbs"):
            thumbs_ph = st.empty()
    with cols[1]:
        with st.container(key="deck_stage"):
            stage_ph = st.empty()
            bar_ph = st.empty()
    with cols[2]:
        with st.container(key="deck_chat"):
            thread = st.container(key="deck_thread")
            sugg = st.empty()
            ask_ph = st.empty()
    if hit and not building and not asked and len(pages) < len(titles) and Path(hit["path"]).exists():
        # the window was closed or the page switched while the pages were being rendered: finish them now
        ui = EditorUI(head_ph, thumbs_ph, stage_ph)
        built_like = {"slides": [{"title": t, "layout": l} for t, l in zip(titles, layouts)]}
        shown = paint_pages(Path(hit["path"]), Path(hit["path"]).parent, built_like, ui)
        d.update(pdf=shown["pdf"], pages=shown["pages"], preview_note=shown["why"])
        app.store.save_cached("deck", deck_fingerprint(fmt, theme), d, hit["path"])
        _ed_rerun()
    if not building:
        with thumbs_ph.container():
            if not pages:
                st.caption("No slide images yet" + (f" ({d.get('preview_note')})" if d.get("preview_note") and hit else ""))
            for i, q in enumerate(pages, 1):
                with st.container(key=f"ed_th_{i}_{'on' if i == sel else 'off'}"):
                    st.html(f'<div class="loa-ed-num">{i}</div>')
                    st.image(q, width="stretch")
                    if st.button(layouts[i - 1] if i - 1 < len(layouts) else f"Slide {i}", key=f"ed_pick_{i}",
                                 type="tertiary", width="stretch", help=titles[i - 1] if i - 1 < len(titles) else None):
                        ed["sel"] = i
                        _ed_rerun()
        if pages:
            stage_ph.image(pages[sel - 1], width="stretch")
            spec_slides = (d.get("spec") or {}).get("slides") or []
            why = spec_slides[sel - 1].get("why", "") if sel - 1 < len(spec_slides) else ""
            locked = sel == 1 or (sel == n and sel - 1 < len(layouts) and layouts[sel - 1] == "Sources")
            with bar_ph.container(key="deck_bar", horizontal=True, vertical_alignment="center", gap="small"):
                if st.button("", icon=material("chevron-left"), key="ed_prev", disabled=sel <= 1, width="content", help="Previous"):
                    ed["sel"] = sel - 1
                    _ed_rerun()
                if st.button("", icon=material("chevron-right"), key="ed_next", disabled=sel >= n, width="content", help="Next"):
                    ed["sel"] = sel + 1
                    _ed_rerun()
                st.html(f'<div class="loa-ed-count">{sel} / {n}</div>'
                        f'<div class="loa-muted loa-ed-why">{esc(titles[sel - 1] if sel - 1 < len(titles) else "")}'
                        + (f' · <i>Why this slide: {esc(why)}</i>' if why else "") + "</div>", width="stretch")
                if st.button("", icon=material("arrow-up"), key="ed_up", width="content", help="Move up",
                             disabled=busy or locked or sel <= 2):
                    _ed_ask(f"move slide {sel} up", sel - 1)
                if st.button("", icon=material("arrow-down"), key="ed_down", width="content", help="Move down",
                             disabled=busy or locked or sel >= n - 1):
                    _ed_ask(f"move slide {sel} down", sel + 1)
                if st.button("", icon=material("trash-2"), key="ed_rm", width="content", help="Remove this slide",
                             disabled=busy or locked or n <= 3):
                    _ed_ask(f"remove slide {sel}", max(sel - 1, 1))
        elif hit:
            with stage_ph.container():
                for line in d.get("slides") or []:
                    st.markdown(f"- {line}")
    # the conversation column: the same pieces as the Copilot everywhere (saved turns, action rows, follow-ups,
    # the empty state's pills, a streamed answer with Stop), here about this deck
    question = asked[0] if asked else None
    typed = ask_ph.chat_input("Change this deck…", key="ed_chat_in", disabled=busy, max_chars=2000)
    if typed and not busy:
        st.session_state["deck_ask"] = (typed, False)
        _ed_rerun()
    if not busy:
        with sugg.container():
            if ed.get("confirm"):
                zh_p = _de.is_zh(ed["confirm"].get("instruction", ""))
                with st.container(horizontal=True, gap="small", key="ed_confirm"):
                    if st.button("套用" if zh_p else "Apply", key="ed_apply", type="primary", icon=material("check")):
                        _ed_ask(APPLY_PENDING, sel)
                    if st.button("保持原樣" if zh_p else "Keep as it is", key="ed_keep", icon=material("x")):
                        _ed_ask(KEEP_PENDING, sel)
            elif not turns:
                hello_state("Change the deck by asking.",
                            "Retitle a slide, add or remove one, change the order or the theme. "
                            + ("The Copilot revises the storyline and builds again; every figure stays checked against the data."
                               if engine.ready else "The Copilot is offline, so plain commands are applied by rules."),
                            EDIT_PILLS_ON if engine.ready else EDIT_PILLS_OFF, f"cs_{sfx}", sfx, target="deck_ask")
            elif (again := follow_up_pills(turns, sfx, target="deck_ask")):
                st.session_state["deck_ask"] = again
                _ed_rerun()
    with thread:
        thread_view(turns, sfx, busy=busy, target="deck_ask", downloads=False)  # the header holds the downloads
        title = deck_chat_title(fmt, theme)
        if building:
            ed["build"] = False  # a Stop lands in the idle editor with what is built
            asked_line = f"Build the {fx.BRIEF_FORMATS[fmt].lower()} slides on {THEME_SHORT.get(theme, theme)}"
            with st.chat_message("user"):
                st.markdown(asked_line)
            with st.chat_message("assistant"):
                chat_id = ensure_chat("_deck", title)
                ui = EditorUI(head_ph, thumbs_ph, stage_ph)
                how, note, ans = build_deck_now(fmt, theme, ui, chat_id, resume["stream"] if resume else None)
            hit = cached_deck(fmt, theme)
            if hit and ans is not None:
                label, plain = DECK_MSG[how]
                text = (f"**{label}.** {plain}\n\n"
                        + "\n".join(f"{i}. {line}" for i, line in enumerate(hit["data"].get("slides") or [], 1)))
                say("user", asked_line, slot="_deck", title=title)
                say("assistant", text, Answer(text, ans.trace, ans.engine), slot="_deck")
            ed["sel"] = 1
            _ed_rerun()
        elif asked:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                chat_id = ensure_chat("_deck", title)
                ui = EditorUI(head_ph, thumbs_ph, stage_ph)
                ans = edit_deck(ed, hit, question, asked[1], chat_id, ui, resume["stream"] if resume else None) if hit \
                    else Answer("Build the slides first.")
                if ans is not None:
                    show_answer(ans, text_done=True, downloads=False)
            if ans is not None:
                say("user", question, slot="_deck", title=title)
                say("assistant", ans.text, ans, slot="_deck")
                _ed_rerun()
    components.html(f"<script>/*{len(turns)}-{datetime.now().timestamp()}*/"
                    "const t=parent.document.querySelector('.st-key-deck_thread'); if (t) t.scrollTop=1e6;</script>", height=0)


def deck_button(fmt, col):
    """The slides stay folded: one button beside the Word and PDF downloads. It opens the floating editor, building the deck
    first when none exists for this data; thumbnails, theme, downloads and the conversation all live there."""
    if (w := st.session_state.pop("deck_theme_want", None)) and w[0] == fmt:
        st.session_state[f"deck_theme_{fmt}"] = w[1]  # the editor changed the theme: follow it
    theme = st.session_state.setdefault(f"deck_theme_{fmt}", "data-white" if fmt == "ic" else "navy-gold")
    hit = cached_deck(fmt, theme)
    d = (hit or {}).get("data") or {}
    job = running_job("_deck")
    running = job is not None  # still going, or finished while nobody watched: opening the window shows it
    if running:
        tip = "The slides are being built or changed in the background; open the window to watch"
    elif hit:
        edits = len(d.get("edits") or [])
        tip = (f"{len(d.get('titles') or [])} slides · {DECK_THEMES.get(d['theme'], d['theme'])} · "
               f"{'chosen by the Copilot' if d['how'] == 'copilot' else 'picked by rules'} · built {when(hit['ts'])}"
               + (f" · edited {edits} time{'s' if edits != 1 else ''}" if edits else ""))
    else:
        tip = "Plans a 3-6 slide deck from this week's data; you watch each slide being laid out"
    if col.button("Slides · working…" if running else ("Slides" if hit else "Build slides"), key=f"mk_deck_{fmt}", width="stretch",
                  type="secondary", icon=material("presentation"), help=tip):
        if running:
            ed = st.session_state.get("deck_ed") or dict(job.get("ed") or {}) or {"fmt": fmt, "theme": theme, "sel": 1}
            ed["open"] = True
            st.session_state["deck_ed"] = ed
            if not st.session_state.get("chat_id_deck"):
                open_chat(job.get("chat"), "_deck")
        else:
            open_deck_editor(fmt, theme, build=not hit)


def deck_panel(fmt):
    if (st.session_state.get("deck_ed") or {}).get("open"):
        deck_editor()


def write_brief_in_background(fmt, fp):
    """Writes the brief in a thread of its own and saves it against the data fingerprint; the page shows a
    spinner and looks again every two seconds. Switching pages (or closing the tab) does not stop the writing,
    and coming back shows the brief once it is saved. Returns the cached brief when it is there."""
    jobs = st.session_state.setdefault("bg_jobs", {})
    job = jobs.get(fp)
    if job is None or (not job.is_alive() and not app.store.cached("brief", fp)):
        def work():
            try:
                brief = app.call("generate_brief", {"format": fmt}, user)["summary"]
                app.store.save_cached("brief", fp, brief)
            except Exception as e:  # noqa: BLE001
                app.store.save_cached("brief", fp, f"The brief could not be written: {e}")
        job = jobs[fp] = threading.Thread(target=work, daemon=True, name=f"brief-{fmt}")
        job.start()

    @st.fragment(run_every="2s")
    def poll():
        if app.store.cached("brief", fp):
            st.rerun()
        st.html('<div class="loa-muted">Writing the brief… you can switch pages; it carries on in the background.</div>')
    with st.spinner("Writing the brief…"):
        poll()
    return None


def report_files(fmt, fp, brief):
    """The brief as a research note (.docx, and the same document as .pdf), made in a thread of its own from the
    brief exactly as shown, and kept against the brief's text: opening the page again reads the files back, and
    only new data or "Write again" makes them again. Returns the cached entry, or None while it is being made."""
    key = f"{fp}-{hashlib.sha1(brief.encode()).hexdigest()[:10]}"
    hit = app.store.cached("brief_doc", key)
    d = (hit or {}).get("data") or {}
    if hit and Path(d.get("docx") or "").exists():
        return d
    jobs = st.session_state.setdefault("bg_jobs", {})
    job = jobs.get("doc-" + key)
    if job is None or not job.is_alive():
        def work():
            # a connection of its own: one sqlite connection shared with the page's reruns fails under load
            own = type(app.store)(app.store.path)
            ctx = copy.copy(app.ctx)
            ctx.store = own
            folder = app.root / "data" / "exports" / "briefs" / key
            try:
                out = _report.build(ctx, brief, fmt, folder)
            except Exception as e:  # noqa: BLE001
                out = {"docx": "", "pdf": "", "why": f"The report could not be made: {e}"}
            own.save_cached("brief_doc", key, out, str(folder))
            own.db.close()
        job = jobs["doc-" + key] = threading.Thread(target=work, daemon=True, name=f"brief-doc-{fmt}")
        job.start()
    return None


def report_buttons(fmt, fp, brief, docx_col, pdf_col):
    """Download (.docx) and Download (.pdf) in place of the Markdown download. While the files are being made the
    two buttons wait, greyed out, and the row looks again every second."""
    files = report_files(fmt, fp, brief)
    if files is None:
        @st.fragment(run_every="1s")
        def wait():
            if report_files(fmt, fp, brief) is not None:
                st.rerun()
            st.button("Word…", disabled=True, width="stretch", key="rep_wait_docx", icon=material("file-text"),
                      help="Laying out the research note from this brief")
        with docx_col:
            wait()
        pdf_col.button("PDF…", disabled=True, width="stretch", key="rep_wait_pdf", icon=":material/picture_as_pdf:",
                       help="Laying out the research note from this brief")
        return
    name = "london-office-ic-paper" if fmt == "ic" else "london-office-weekly-brief"
    if files.get("docx"):
        docx_col.download_button(
            "Word", Path(files["docx"]).read_bytes(), file_name=f"{name}.docx", width="stretch",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"dl_docx_{fmt}",
            icon=material("file-text"), help="The research note as an editable Word document, in the house style")
    else:
        docx_col.button("Word", icon=material("file-text"), disabled=True, width="stretch", help=files.get("why") or "")
    if files.get("pdf") and Path(files["pdf"]).exists():
        pdf_col.download_button("PDF", Path(files["pdf"]).read_bytes(), file_name=f"{name}.pdf",
                                mime="application/pdf", width="stretch", key=f"dl_pdf_{fmt}",
                                icon=":material/picture_as_pdf:", help="The same research note as a PDF")
    else:
        pdf_col.button("PDF", icon=":material/picture_as_pdf:", disabled=True, width="stretch", key=f"dl_pdf_off_{fmt}",
                       help=(files.get("why") or "LibreOffice is not installed here")
                       + ". The Word download has the same layout.")


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
                st.rerun()
    else:
        st.info("Nobody has added signals yet, so the brief uses the team's top signals. Use 'Add to brief' on "
                "Monitor to choose them.")
    if st.button("Add more from Monitor", type="tertiary", key="more_from_monitor"):
        goto("monitor")
    row = st.columns([2.6, 0.8, 0.8, 1.1], vertical_alignment="center")
    with row[0]:
        fmt = st.segmented_control("Write it as", list(fx.BRIEF_FORMATS), default="board",
                                   format_func=fx.BRIEF_FORMATS.get, key="brief_fmt") or "board"
        st.caption(FORMAT_HELP[fmt])
    # The brief is written once per state of the data (and format): opening the page again reads it back.
    # Only new data, a changed pick of signals, or "Write again" calls the model.
    fp = brief_fingerprint(fmt)
    hit = None if st.session_state.pop("brief_redo", False) else app.store.cached("brief", fp)
    if not hit:
        hit = write_brief_in_background(fmt, fp)
        if not hit:
            return  # the page polls until the brief is there; switching pages does not stop the writing
    brief, made = hit["data"], hit["ts"]
    if brief.startswith("The brief could not be written"):
        row[1].button("Word", disabled=True, width="stretch", key="dl_docx_off")
        row[2].button("PDF", disabled=True, width="stretch", key="dl_pdf_off")
    else:
        report_buttons(fmt, fp, brief, row[1], row[2])
    deck_button(fmt, row[3])
    deck_panel(fmt)
    with st.container(border=True):
        st.html(f'<div class="loa-cobrand">{brand_img("cobrand-nanfung.svg", "", "London Office Market Agent · Nan Fung Group")}'
                f'<span>{esc(fx.BRIEF_FORMATS[fmt])}</span></div>')
        state = st.columns([5, 1.2], vertical_alignment="center")
        state[0].html(f'<div class="loa-muted">Written {esc(when(made))} · the data has not changed since'
                      + ("" if hit else " (just now)") + "</div>")
        if state[1].button("Write again", key="brief_redo_btn", type="tertiary", icon=material("refresh-cw"),
                           help="Writes the brief again from the same data"):
            st.session_state["brief_redo"] = True
            st.rerun()
        st.markdown(re.sub(r"^(#{1,2}) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", brief, flags=re.M))
        # the chart follows the first picked signal that has a metric; London vacancy when nothing is picked
        lead = next((it for it in items if it.get("metric")), None)
        market = (lead or {}).get("markets", ["London"])[0] if lead else "London"
        chart(app.call("get_metric_trend", {"market": market, "metric": (lead or {}).get("metric") or "vacancy_pct"})["chart"])


# ---------------------------------------------------------------- sources
STATUS = {"verified": "in page text", "image": "image only", "not_found": "not in text (check)",
          "implausible": "outside range (check)"}
FOLLOW_EXAMPLES = ["Follow Savills Market Watch", "Landsec half-year results", "TfL station entries",
                   "https://www.costar.co.uk/news/rss"]
LIB_TABS = ["Collected automatically", "Uploaded reports", "Internal data", "News and tips"]


def overview_line():
    """One line of counts for the three kinds of source; the tabs below hold the detail."""
    feeds = lib.feeds(app.store, app.config)
    live = [f for f in feeds if f.get("connector")]
    ups = app.store.uploads()
    n_up = len(ups)
    # the latest report a colleague uploaded; the seed's restated tables are not someone's upload
    real = [u for u in ups if (u.get("uploaded_by") or "").lower() not in NOT_PEOPLE]
    up = max(real, key=lambda u: u.get("uploaded_at") or "", default=None)
    n_news = len(app.store.news())
    quot = sum(d.get("confidentiality") == "quotable" for d in our_deals)
    st.html('<div class="loa-fresh">'
            f'<span>{tier("open", "Open data")} {len(live)} live feeds · {n_news} news items</span>'
            f'<span>{tier("upl", "Uploaded")} {n_up} reports' + (f', latest {esc(up["publisher"])} {esc(an.period_label(up["period"]))} by {esc(up["uploaded_by"])}' if up else "") + '</span>'
            f'<span>{tier("int", "Internal")} {len(our_deals)} of our deals' + (f", {len(deal_drafts)} draft" if deal_drafts else "")
            + (f", {quot} quotable" if our_deals else "") + '</span></div>')


def gathering_card():
    last = lib.last_auto_update(app.store)
    with st.container(border=True):
        c = st.columns([4, 1.6], vertical_alignment="center")
        c[0].html(f'<b>{ic("refresh-cw", 15, "accent")}Updates</b> <span class="loa-muted">daily on the server · last '
                  f'{esc(lib.when(last["ts"]) if last else "never")}</span>'
                  '<div class="loa-ink2">Collects open data, files what the team shared, looks for new agency '
                  'reports by title (never downloading them) and classifies news.</div>')
        if c[1].button("Update now", type="primary", width="stretch", key="run_round", icon=material("refresh-cw")):
            with st.spinner("Collecting open data…"):
                reports = app.refresh(by=f"Auto-update (run by {user})")
            for r in reports:
                st.toast(f"{r['connector']}: {'failed' if r.get('error') else r['counts']}")
            with st.spinner("Filing what the team shared…"):
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
    with st.expander("Technical: how the agent processes sources"):
        st.html(f'<b>{ic("bot", 15, "accent")}One information-processing agent</b><div class="loa-ink2">The same agent collects and reads '
                'everything: PDFs, web pages, news, spreadsheets and data feeds. It picks the skills each input '
                'needs, so a new kind of source needs a new skill, not a new pipeline.</div><div style="margin-top:8px">'
                + chip(f"This week: {n_pdf} PDFs") + chip(f"{n_news} news items") + chip(f"{n_feeds} data feeds")
                + chip(f"{n_web} web pages followed") + "</div>")
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
    df = pd.DataFrame([{"Feed": f["name"], "What": f.get("what", ""), "Licence": f["licence"], "Updates": f["cadence"],
                        "Last collected": f["last"], "Next": f["next"], "Status": f["status"]}
                       for f in lib.feeds(app.store, app.config)])
    st.dataframe(df, width="stretch", hide_index=True)
    notes = [s for s in app.store.sources().values() if s.get("definition_note")]
    if notes:
        with st.expander(f"Definition notes ({len(notes)}): where a publisher changed what a series measures"):
            for src in notes:
                st.markdown(f"- **{src.get('publisher', '')} {an.period_label(src.get('period', ''))}**: {src['definition_note']}")


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
    if d.get("demo"):  # the three seed records: fictional deals and colleagues, so the inside/outside split shows
        level += chip("Demo data", "warn")
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
    overview_line()
    gathering_card()
    add_source_card()
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
        rows = [{"Published": n.published, "Story": n.title, "Markets": ", ".join(n.markets[:2]), "Source": n.source,
                 "Shared by": ", ".join(x["who"] for x in n.shared_by)} for n in app.store.news()]
        if rows:
            st.dataframe(pd.DataFrame(rows).sort_values("Published", ascending=False), width="stretch", hide_index=True)
        else:
            st.caption("No news yet.")
    agent_card()


# ---------------------------------------------------------------- navigation (left, like the prototype)
PAGE_OBJ = {
    "monitor": st.Page(monitor_page, title="Monitor", icon=material("activity"), default=True),
    "copilot": st.Page(copilot_page, title="Ask Copilot", icon=material("message-square"), url_path="copilot"),
    "brief": st.Page(brief_page, title=f"Team brief · {brief_count}" if brief_count else "Team brief", icon=material("file-text"),
                     url_path="brief"),
    "sources": st.Page(sources_page, title=f"Sources · {to_check} to check" if to_check else "Sources", icon=material("database"),
                       url_path="sources"),
    "help": st.Page(help_page, title="Help", icon=":material/help:", url_path="help"),
}
nav = st.navigation(list(PAGE_OBJ.values()), position="hidden")
sidebar()
nav.run()
