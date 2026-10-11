# Features in detail

The reviewer guide is the [README](../README.md); this page is the long version of what each part does.

An AI agent that helps a commercial real estate business team monitor the London office market:
prime and Grade A rents, vacancy, take-up, supply pipeline, submarkets, macro drivers and news.

It is **one shared tool for the whole business team**, not a set of role dashboards. It is built around
the three jobs the brief names: stay ahead of the market, support decisions, and produce reports.

| Job | Where | What the team gets |
|---|---|---|
| **Monitor** (stay ahead, spot risks early) | Monitor | A freshness strip, the team summary and ranked "what changed" signal cards: numbers line (before → after · change), why it matters, source chips, Add to brief. Toggle **Whole team** or **For you**. The team view is the day's pick (alerts and flagged figures always, then the best of the rest, one card per story, at most two per measure or submarket), the rest folded by category below, and a New chip on what arrived since you last looked; news leaves Monitor when it stops being active (30 days, 60 for deals) but stays in the library. Side panels: Share a link or tip (one box; the agent files it), Alerts (rules in your own words, parsed live; yours until you press Share with team), Team activity (only what colleagues chose to share). Hide for me hides a signal from your own views. |
| **Decide** (ask, compare, drill down) | Ask Copilot | Ask anything from any page: a floating button at the bottom right of every page (also Ctrl+K, or the / key) opens the side panel (about 500px, the page stays visible beside it); Ask Copilot in the left navigation is the full page. The conversation is laid out the way people know from ChatGPT: a bar at the top that stays put while you scroll (what the Copilot is looking at, History, New chat), a centred 760px thread (your question as a light bubble on the right, the answer as plain text with no avatar or frame, a folded "Worked through N steps" line above it and its sources under it), and the chat box pinned at the bottom with a one-line reminder that every number links to its source. A new chat opens on a greeting with example questions as pills ("Set up my focus" is the first). It knows the page you are on, or the signal you asked from. The answer streams in as the model writes it, with a status line naming each tool as it starts; while it writes, the send button becomes Stop; the thread follows the output while you are at the bottom and stays put when you scroll up to read (a round ↓ button above the chat box brings you back); the cursor returns to the box after each answer. Under each answer a row of small buttons: Copy, thumbs up / down, Ask again, Share to team; the latest answer's row stays, older rows appear when the pointer is over that answer. No login: the first visit asks who you are (pick a team name or type one) and the browser remembers it in a cookie, so a refresh or a bookmark brings back the same person and their last conversation. Conversations are saved under your name and stay private: History (top right of the chat) lists them to resume, New chat starts a clean one with its own context. Only a shared answer appears in Team activity, with your name and the time; "Shared to team · Undo" takes it out. The example questions appear only on a new chat; after an answer the Copilot offers its own follow-up questions as buttons. It answers in the language you ask in (English by default, Chinese for a Chinese question). The input box is pinned to the bottom of the page and of the side panel. Every number comes from a tool with its source. If you ask about a publisher the library has no figures from ("what does Savills say…") or an area it does not track (Shoreditch), it says so first and names the nearest covered submarket. |
| **Report** (board and IC) | Team brief | Anyone can press Add to brief on a signal. One brief serves the board and the investment committee: the headline, London's key numbers, the evidence table for the team's submarkets (rents, rent-free, vacancy, Grade A vacancy, yields, investment), what changed grouped into what supports the case and what puts it at risk, quotable deals, market talk and macro, every figure footnoted to its source. The brief is written once per state of the data: opening the page again reads it back with "Written … · the data has not changed since", and only new data, a changed pick of signals, or **Write again** calls the model. Download it as a research note, **Word** (.docx) or **PDF**, laid out like a broker's research report in the Nan Fung co-brand: a navy cover with the headline, key takeaways, KPI tiles, the key-numbers table, the submarket evidence table, three charts, the signals with why each matters, our deals and market deals, numbered sources and an important-information page; every figure keeps its [n]. The PDF is LibreOffice's rendering of the same .docx, so the two never differ, and both are made once per brief in the background (`skills/market_brief/report.py`, kept under `data/exports/briefs/`; see [docs/brief-report.md](brief-report.md)). Or press **Build slides**: the slides stay folded: one **Build slides** button beside the two downloads, which reads **Slides** once a deck exists and shows its status as a tooltip and a floating slide editor opens over the page, laid out like a presentation app (thumbnails with page numbers on the left, the chosen slide large in the middle, the Copilot on the right). While it builds you watch the storyline being planned (the Copilot's reasoning streams into the chat column), every slide first appears as a hatched "Planned: layout" frame, and each thumbnail fills in as that slide is laid out; **Stop** keeps what is built. In the editor the conversation column is the same Copilot as everywhere else in the app (the same saved chats under the person's name, streamed with a Stop, the action row under each answer, follow-ups, History) and it changes the deck by conversation, in English or Chinese ("make slide 2's title shorter", "需要多兩頁", "add a slide on investment", "remove the deals slide", "swap slides 2 and 3", "theme forest"): the Copilot revises the spec and builds again, and without a model the same plain commands are applied by rules (`core/deck_edit.py`). A deck may grow to 12 slides in the editor; slides carry ids, so the Copilot may not drop a slide nobody asked to drop (a revision that would is held back with Apply / Keep buttons), and every reply describes the deck as it was actually built, from the difference between the old and the new spec by id, never from the model's own account. Several commands go in one message ("刪第3頁，然後換森林主題"), "this slide" means the selected one, charts take a range, submarkets or a type ("只顯示最近四季的空置率", "only West End Core and City Core", "as a line chart"), a theme can be named by colour or audience ("for a client update"), "shorten to 4 slides" drops the weakest stories, and a figure that is not in the data is refused with the current value in the instruction's language ("47.3% 不在本週數據裡（目前空置率 8.0%）"). Every state is kept as a version: **Undo** and the version list in the header go back without a rebuild, and the theme control rebuilds an edited deck on the new theme instead of planning it again. When the Copilot fails to answer, the rule editor stands in and says so. Every AI job carries on in the background when you switch pages, close the editor or reload: the Copilot's answer, a deck being built or edited, and the brief being written. Coming back shows the finished result, or picks the stream up from its first word (the Slides button reads "Slides · working…" meanwhile). Only **Stop** ends a run, and it kills the Node process behind it; a new request that finds an earlier one still running waits its turn and says so instead of hanging silently, and the status line shows the seconds passing. A deck build or edit stops after 10 minutes (`PI_DECK_TIMEOUT`). The bar under the big slide moves a slide up or down or removes it, the cover and sources stay first and last, a deck never drops under three slides, and a figure that is not in the data is refused as always. Every change re-renders the pages and updates **Download .pptx** and **PDF** at once. The deck is built once per data state and theme and kept under `data/exports/decks/`; when only the layout code changes the same storyline is laid out again without asking the Copilot; the thumbnails, theme, downloads and conversation are all inside the editor window, nothing is shown on the page itself; the preview needs LibreOffice and poppler on the server, both in the Docker image; without them the editor shows the slide outline and the .pptx. Coming back to the page with the same data shows the same deck without building again; **Build again** forces a new plan. The deck is a 3-12 slide (3-6 when first planned) editable PowerPoint on one of five house themes (navy-gold, editorial-cream, data-white, charcoal-amber, forest-cream) built by python-pptx from the library, with native charts, KPI tiles, so-what bands and signal cards. The storyline is not a fixed template: the Copilot reads this week's data and a ranked list of story candidates (alert lines crossed, biggest moves, gaps to the long-term average, new deals) and decides which 1-4 topics get a slide, which layout each gets and why; the why is written into the slide notes and shown under "Why these slides". Without a model a rule-picked plan from the same candidates is used and labelled as the fallback. The Copilot can also write the whole storyline on request ("make the brief into slides", "a client update deck on the forest theme"): it picks the theme and layouts and writes the titles, so-what lines and notes; any number in its text that is not in the data is refused, and a post-build check reports overflow, overlaps and leftover text so the model fixes and rebuilds. See [docs/brief-deck.md](brief-deck.md). |
| Shared data | Sources | One library for the whole team, three kinds of source, each shown as a coloured dot with a text label. Open data is collected automatically; uploaded reports come from anyone on the team; **internal data** is the company's own lettings, leases and valuations, recorded from a sentence to the Copilot, a photo (lease page, WhatsApp screenshot), a PDF or a spreadsheet, all through the same agent into one deal record. Pieces arrive separately and are merged by property and floor; drafts list their missing fields; the recorder confirms; each record is internal-only or quotable, and the brief lists "Our deals" apart from "Market deals" (only quotable records reach the brief, since it may go to the investment committee). See [docs/internal-data.md](internal-data.md). Cards for the gathering round, adding a source (the agent proposes how it will be collected after reading its terms), the information agent, and what needs a person. |
| Guide | Help | How to use the app, page by page, with annotated 16:9 screenshots. The guide is `assets/help/help.md` (and `help.zh-TW.md` when present) with its images in `assets/help/screenshots/`; until it is there the page shows a short outline. "About this installation" at the bottom names the data period, the Copilot engine and the PDF reader, which used to sit in the sidebar. |

**Market aspects the brief names, and where each one lives.** Prime rents, vacancy, take-up, availability,
requirements, investment, yields and rent-free periods are metrics in the library with a long-term average
each; **Grade A** is covered by new/refurbished vacancy (per submarket, every quarter) and by a named Grade A
rent metric that fills from uploaded reports (the seed's public source quotes prime only). The **supply
pipeline** lists schemes with size, status (pre-let or speculative), pre-let party and due quarter, from
agency reports plus public developer announcements (sourced and marked "verify"); the City of London and
GLA planning feeds are listed as planned connectors. **Demand drivers** are signals, not just news tags:
a flight-to-quality detector compares Grade A with overall vacancy in each market and ranks the widest or
widening gaps, news is themed (flight to quality, ESG, hybrid working, tech and AI, financial services,
legal), and the Bank Rate and labour market come from open data. Submarkets follow the agency taxonomy
(West End, City & Southbank, Docklands & Stratford and 21 submarkets, with Midtown and Fringe mapped).

**Personal view without splitting the team.** "For you" is built by the agent: press Set up my focus
and describe your job in one sentence. The Copilot proposes submarkets, measures, how much to show,
whose "why it matters" wording to add (investment, asset management, research or leadership) and team
alerts set just beyond today's values. Nothing is saved until you press Apply, and Undo reverts it.
Later tweaks are one line ("more Fitzrovia, less macro"). Hide (thumbs down) hides a signal for you only. The same
steps are agent tools (`propose_setup`, `apply_setup`, `update_focus`).

**One shared data library, two ways in.**
- **Open data, collected automatically**: open data whose licence allows it (Bank of England, news RSS; ONS as a
  seed snapshot). Each feed shows its licence, cadence, last run, status and next run, and anyone can press
  **Check for new data now**. The app collects on start-up when the last run is more than a day old; a
  daily timer on the server runs `main.py refresh` and `main.py gather`. Nomis, City of London, GLA, VOA, EPC and listed
  landlords' results are listed as planned feeds and are not built in this PoC.
- **Uploaded by the team**: agency reports whose terms bar automated collection or AI use (Knight
  Frank, Savills, BNP Paribas). Anyone uploads the PDF they can access; the agent reads and checks it.
  Figures that pass every check are shared as they are. The rest are shared flagged unless the uploader
  ticks "I checked it", and stay usable, with the warning, until anyone settles them. The same file, or the
  same publisher and quarter, uploaded again shows "Kenneth already uploaded it on 10 Oct" and adds nothing.
- Every figure shows how it arrived: "Open data · collected automatically" or "Uploaded by Kenneth ·
  2026-10-10". Anyone can press **Looks wrong** on a signal to flag its number for the team. The
  Copilot and the team brief carry the same flag and channel.
- **Needs a person** is one queue for the team: flagged figures (Right / Wrong) and figures that
  disagree between sources. Uploads, flags, checks and auto-updates all appear in team activity. Copilot
  conversations stay private to the person who asked: each answer has a **Share to team** button (with an optional
  one-line reason), and only a shared answer appears in team activity, with the sharer's name, time, charts and
  sources; a colleague can continue it in their own Copilot, and only the sharer can unshare it. Alerts work the
  same way: an alert belongs to the person who set it and fires in their 'For you' view until they share it.
- Monitor's **freshness bar** shows when open data last came in, the latest report and who uploaded it,
  how many items need a person, and a nudge when an expected report is probably out but nobody has
  uploaded it (`expected_reports` in config.yaml).

**Anyone can follow a new source.** In Sources → Follow a new source, paste a link (a page, an RSS
feed, a publisher's research page) or type a name ("Savills Market Watch"), or tell the Copilot "follow
…". The agent reads the site's robots.txt and terms first. Open Government Licence publishers and sources
whose terms raise no objection join Open data, collected automatically (an RSS feed in full; a web page as
headlines and links only). If robots.txt or the terms restrict automated collection or AI use, or the
terms cannot be read, the source becomes upload-only: the agent never fetches it, and Monitor reminds
the whole team when a new issue is due. Agency and data-vendor research is treated as restricted until a
person reads its terms (an assumption, based on Knight Frank's). The verdict shows its reason and the
sentence from the terms it rests on. Followed sources are shared by the whole team, with who added them.

**The whole team gathers, the agent files.** Anyone can drop a link or something they heard (a broker
call, a LinkedIn post, a newsletter) into **Share a link or tip** on Monitor, or just tell the Copilot
("I heard from a broker that…"). The agent reads the link, classifies the story, checks whether the team
already has the same story (same companies, figures and wording) and either merges it, crediting the
colleague, or adds it as new. A tip with no published source shows as **Unverified tip** until a link or a
second source arrives. Every story gets a **hot** score from 0 to 100 with its reasons: importance, how
many outlets and colleagues mention it, how new it is, whether it is the largest deal of its kind in 12
months and whether it is in the team's focus. The same story from two news feeds is merged too ("also
reported by").

**One information agent, built with the Pi SDK.** Collecting, reading and filing are done by one Pi
agent, the **market-info** extension (`pi_engine/info_agent.ts`). It handles web pages, news and RSS,
PDFs, spreadsheets, open-data APIs and colleagues' tips, and it picks a playbook per input from
`info_skills/`:

| Skill | For |
|---|---|
| check-terms | a new source: robots.txt and terms decide automatic (open data) or upload-only |
| fetch-source | getting a link once: page, feed, PDF or spreadsheet |
| dedupe | the same file, the same quarter or the same story is never added twice |
| read-pdf | agency reports, dashboards, listed landlords' results: choose pages, read them as images |
| read-table | CSV, Excel and JSON from open-data portals |
| read-article | news, posts and tips: classify, merge, credit, score how hot it is |
| map-submarkets | a publisher's market names to the team's submarkets, with boundary notes |
| check-figures | the three checks; failures are saved flagged for the team's review queue |

The agent sees each skill's name and description and loads the full playbook with `load_skill` when it
needs it, so a new kind of material is a new folder with a `SKILL.md`, not new code. Network work runs
inside Pi (`fetch_source`, `follow_source`, `check_report_index`, `load_skill`). Each parsing step is a
small tool from the `info_processing` and `market_gather` skills (`pdf_overview`, `read_pdf_pages`,
`map_markets`, `check_figures`, `stage_figures`, `save_figures`, `read_table`, `save_series`,
`classify_item`, `find_matches`, `save_item`, `score_hotness`...). The agent decides the order and adapts
it to the document; the figure checks always run in the same code. An upload shows the chain of skills it
went through. The agent is installed in the Copilot, runs every uploaded report, and runs a daily round
(`python main.py gather`): the team inbox, open data and new report titles. Every tool call is committed
before it runs, so a crashed run resumes without filing anything twice.

**Reading agency PDFs.** In Sources → Uploaded by the team, each data page is rendered to an image
(about 2,500 px on the long side) and read by a vision model, together with the page's text layer, so
tables, dashboards and charts are all read. The model returns each figure with its page, where it was
(table, column or chart), whether its label was printed or inferred, and the words next to it. Then:
1. **Evidence check**: the figure must appear in that page's text layer. If the page has no text layer
   (a chart or dashboard) or the figure is not in it, it is marked for a person, with a screenshot of the page.
2. **Range check**: values outside a plausible range for the metric are flagged.
3. **Source check**: figures are compared with what other publishers reported for the same period.
Figures that pass every check are shared as they are; the others are shared flagged until someone checks them.
The PDF reader is its own setting (`vision` in config.yaml), so it can be a cheap vision model while the
Copilot keeps its chat model. The PDF reader's default is Xiaomi MiMo-V2.6-Flash through its OpenAI-compatible API,
two pages per call with JSON-schema output: `export MIMO_API_KEY=...`. Without that key PDFs use the chat
model; without any key, or if the vision call fails, a rule-based text extractor is used instead.
`python scripts/eval_extraction.py <folder of PDFs named by source_id>` scores the extractor against the
hand-curated seed figures (recall, precision, and how many pre-ticked figures were right).

## Look and feel

The Copilot conversation follows [docs/copilot-chat-layout.md](copilot-chat-layout.md), a study of how ChatGPT
lays out a chat (what is fixed at the top and bottom, what scrolls, where the actions sit) and what this app keeps
that ChatGPT does not have: the context chip, the sources line under every answer, Share to team.

The slide editor follows the "Slides builder" section of the same design tokens: a floating window 24px in from
every edge (full screen on a phone, where the thumbnails become a strip), a 52px header with the theme switch,
the build status, Stop or Build again, Download .pptx and PDF; thumbnails, the stage with its bar (previous /
next, n / N, why this slide, move up / down, remove) and the Copilot column with the conversation layout above.
Screens: [slides-building.png](screenshots/slides-building.png) (Planned frames filling in one by one),
[slides-editor.png](screenshots/slides-editor.png), [slides-edited.png](screenshots/slides-edited.png)
(after "Remove slide 3" and a move up), [slides-confirm.png](screenshots/slides-confirm.png) (a revision
that would drop a slide, held back with Apply / Keep), [slides-versions.png](screenshots/slides-versions.png)
(after a batch, an undo, a chart range and a theme change: Undo and the version list in the header),
[slides-editor-phone.png](screenshots/slides-editor-phone.png).

The app carries its own logo (direction A, "Skyline": `assets/brand/`) at the top of the sidebar, the Nan Fung
Group mark under a "Built for" label at the foot of the sidebar, the co-brand lockup on the Team brief page and at
the top right of every deck cover, and the small app icon beside the slide number on content slides; the browser
tab shows the favicon. The Nan Fung logo is the official SVG from nanfung.com, embedded unchanged; it is a
trademark of Nan Fung Group and is used here only for this interview proof of concept and its sample decks
(placement rules and the full note: `assets/brand/README.md`).

The app follows the team's design tokens (`prototype/design-tokens.md`): slate neutrals, one navy accent
(`#1B3A5C`) for primary buttons, links and selected states, amber (`#B9781A`) as the only highlight, and four
low-saturation semantic colours that mean one thing each: green for open data collected automatically, amber
for a report a colleague uploaded, blue for internal data, red for anything that needs a person. A source
tier is always a coloured dot plus a text label, never colour alone. Light mode only, tabular numerals
everywhere a figure appears.

No emoji anywhere: icons are [Lucide](https://lucide.dev) (MIT), inlined in `core/icons.py` so nothing is
fetched at runtime. `icon(name, size)` paints an icon in the text colour through a CSS mask, because
`st.html` strips inline `<svg>`. Streamlit's own widgets (buttons, page links, the popover) accept only
Material Symbols, so those use the closest Material name via `material(name)`; both are 1.75-stroke line
icons of the same size, so the two sets read as one. The deck themes and the brief use the same words
(Open data, Uploaded, Internal, Flagged) in place of the old coloured circles.

## Information lifecycle

Nothing is deleted; information changes state as it ages, so the Copilot and search can still find an old story
while Monitor shows only what is live. States: **new → active → cooling → archived**, plus **expired** for a
colleague's tip that never found a published source and **superseded** for an agency report replaced by the next
edition. The periods live in `config.yaml` under `lifecycle:` (news: fresh 2 days, active 30, archived after 180,
half-life 7 days; deal news 7 / 60 / 180 / 14; tips 2 / 14 / 180 / 5 with 14 days to find a source; data series
never decay, the latest period decides). Ranking uses the half-life, so a story from three days ago outranks the
same story from twenty days ago. `python main.py housekeep` is the daily tidy-up (also run at the end of every
`refresh`): it advances states, re-scores only the live stories (the biggest deals looked up once, one commit),
builds the day's digest and leaves one line in team activity when anything moved; running it twice changes
nothing the second time. A new story is compared with stories published within 120 days of its own date, the
same category first, so merging stays quick with years of news. Monitor's team view is the digest: alerts,
flagged figures and today's data always, then the best of the rest with one card per story and at most two per
measure or submarket; everything else folds under one line by category, and a "New" chip marks what arrived since
you last looked. Design: `research/information-lifecycle.md`.
