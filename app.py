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
[data-testid="stSidebarUserContent"] { padding-top:0.5rem; }
[data-testid="stSidebarHeader"] { padding:10px 16px 0 16px; height:auto; min-height:0; }  /* just the collapse button */
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
        turn = {"role": m["role"], "content": m["content"], "id": m["id"]}
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
        st.html(brand_img("logo-horizontal.svg", "loa-logo", "London Office Market Agent")
                + '<div class="loa-logo-cap">Prototype · sample data</div>')
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
        st.html(f"""{kicker("Team")}
<div class="loa-team"><b>{esc(team['name'])}</b><div style="margin:6px 0 0 0">{avatars(colleagues(), user)}</div></div>""")
        st.caption(f"**Data up to:** {an.period_label(an.latest_period(app.store))}")
        with st.expander("Technical details"):
            st.caption(f"Engine: {engine.status}")
            st.caption(f"PDF reader: {app.vision.model if getattr(app.vision, 'available', False) else 'rule-based text reading'}")
        st.html(f'<div class="loa-builtfor">{kicker("Built for")}'
                + brand_img("nanfung/nanfung-logo-color.svg", "", "Nan Fung Group") + "</div>")


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


def show_answer(ans, text_done: bool = False):
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
        if step["tool"] == "build_brief_pptx" and (p := (step["result"].get("data") or {}).get("path")) and Path(p).exists():
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
    st.rerun(scope="fragment" if st.session_state.get("_in_dialog") else "app")


SETUP_PILL = "Set up my focus"


def _pick(key: str):
    """A pill was chosen (an example question, a follow-up): it becomes the next question, and the pill resets so
    the same one can be chosen again later."""
    v = st.session_state.get(key)
    st.session_state[key] = None
    if v == SETUP_PILL:
        st.session_state["copilot_ctx"] = {"kind": "setup"}
    elif v:
        st.session_state["cp_ask"] = v


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
    with st.container(key=f"cp_empty_{sfx}"):
        st.html(f'<div class="loa-cp-hello">{esc(head)}</div><div class="loa-cp-sub">{esc(sub)}</div>')
        opts = ([SETUP_PILL] if ctx["kind"] == "page" else []) + [q for q in suggestions if q != SETUP_PILL]
        key = f"cs_{sfx}_{ctx['kind']}"
        st.pills("Suggestions", opts, key=key, label_visibility="collapsed", on_change=_pick, args=(key,))


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
            elif turns[-1]["role"] == "assistant" and turns[-1]["content"].endswith("*Stopped.*") and len(turns) > 1:
                if st.button("Ask again", icon=material("refresh-cw"), key=f"again{len(turns)}"):
                    clicked = turns[-2]["content"]
            elif turns[-1]["role"] == "assistant" and "answer" in turns[-1]:
                _, follow_ups = split_follow_ups(turns[-1]["answer"].text)
                if follow_ups:
                    st.html('<div class="loa-fu">Follow up</div>')
                    key = f"fu_{sfx}_{len(turns)}"
                    st.pills("Follow up", follow_ups, key=key, label_visibility="collapsed", on_change=_pick, args=(key,))
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


def action_row(turn, latest: bool, prev_question: str, sfx: str):
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
            st.session_state["cp_ask"] = prev_question
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


def copilot_thread(turns, ctx, question):
    sfx = "d" if st.session_state.get("_in_dialog") else "p"
    for i, turn in enumerate(turns):
        with st.chat_message(turn["role"]):
            if turn["role"] == "user" or "answer" not in turn:
                st.markdown(turn["content"])
            else:
                show_answer(turn["answer"])
                prev = turns[i - 1]["content"] if i and turns[i - 1]["role"] == "user" else ""
                action_row(turn, latest=(i == len(turns) - 1 and not question), prev_question=prev, sfx=sfx)
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
    stop.button("", icon=material("square"), key=f"stop_{chat_id}", type="tertiary",
                help="Stop: keep what has been written so far")
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
            c[3].caption("Five house themes, 13 layouts, every number footnoted and checked against the data. For a "
                         "deck this button does not give you, ask Copilot: \"a client update on the forest theme that "
                         "only covers Midtown\".")
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
    row = st.columns([3.8, 1.2], vertical_alignment="center")
    with row[0]:
        fmt = st.segmented_control("Write it as", list(fx.BRIEF_FORMATS), default="board",
                                   format_func=fx.BRIEF_FORMATS.get, key="brief_fmt") or "board"
        st.caption(FORMAT_HELP[fmt])
    key = (fmt, tuple(it["id"] for it in items))
    if st.session_state.get("brief_key") != key:  # the text follows the picked signals and the format; same picks, same text
        with st.spinner("Writing the brief…"):
            st.session_state["brief"] = app.call("generate_brief", {"format": fmt}, user)["summary"]
            st.session_state["brief_key"] = key
    brief = st.session_state["brief"]
    row[1].download_button("Download (.md)", brief, file_name="london-office-team-brief.md", width="stretch")
    deck_panel(fmt)
    with st.container(border=True):
        st.html(f'<div class="loa-cobrand">{brand_img("cobrand-nanfung.svg", "", "London Office Market Agent · Nan Fung Group")}'
                f'<span>{esc(fx.BRIEF_FORMATS[fmt])}</span></div>')
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
}
nav = st.navigation(list(PAGE_OBJ.values()), position="hidden")
sidebar()
nav.run()
