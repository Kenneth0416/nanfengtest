# London Office Market Agent (PoC)

An AI agent that helps a commercial real estate business team monitor the London office market:
prime and Grade A rents, vacancy, take-up, supply pipeline, submarkets, macro drivers and news.

It is **one shared tool for the whole business team**, not a set of role dashboards. It is built around
the three jobs the brief names: stay ahead of the market, support decisions, and produce reports.

| Job | Where | What the team gets |
|---|---|---|
| **Monitor** (stay ahead, spot risks early) | Monitor | A freshness strip, the team summary and ranked "what changed" signal cards: numbers line (before → after · change), why it matters, source chips, Add to brief. Toggle **Whole team** or **For you**. The team view is the day's pick (alerts and flagged figures always, then the best of the rest, one card per story, at most two per measure or submarket), the rest folded by category below, and a New chip on what arrived since you last looked; news leaves Monitor when it stops being active (30 days, 60 for deals) but stays in the library. Side panels: Share a link or tip (one box; the agent files it), Alerts (rules in your own words, parsed live; yours until you press Share with team), Team activity (only what colleagues chose to share). Hide for me hides a signal from your own views. |
| **Decide** (ask, compare, drill down) | Ask Copilot | Ask anything from any page: a floating button at the bottom right of every page (also Ctrl+K, or the / key) opens the side panel; Ask Copilot in the left navigation is the full page. It knows the page you are on, or the signal you asked from. The answer streams in as the model writes it, with a status line naming each tool as it starts; the thread follows the output while you are at the bottom and stays put when you scroll up to read (a "↓ Latest" button brings you back); the cursor returns to the box after each answer. No login: the first visit asks who you are (pick a team name or type one) and the browser remembers it in a cookie, so a refresh or a bookmark brings back the same person and their last conversation. Conversations are saved under your name and stay private: History (top right of the chat) lists them to resume, New chat starts a clean one with its own context. Each answer has a Share to team button; only a shared answer appears in Team activity, with your name and the time, and Unshare takes it out. The example questions appear only on a new chat; after an answer the Copilot offers its own follow-up questions as buttons. It answers in the language you ask in (English by default, Chinese for a Chinese question). The input box is pinned to the bottom of the page and of the side panel. Every number comes from a tool with its source. If you ask about a publisher the library has no figures from ("what does Savills say…") or an area it does not track (Shoreditch), it says so first and names the nearest covered submarket. |
| **Report** (board and IC) | Team brief | Anyone can press Add to brief on a signal. The brief is written as a board summary or an IC paper section, with every figure footnoted to its source. Copy as Markdown, download it, or use the Slides panel (**Build slides**, then **Download .pptx**): a 3-6 slide editable PowerPoint on one of five house themes (navy-gold, editorial-cream, data-white, charcoal-amber, forest-cream) built by python-pptx from the library, with native charts, KPI tiles, so-what bands and signal cards. The storyline is not a fixed template: the Copilot reads this week's data and a ranked list of story candidates (alert lines crossed, biggest moves, gaps to the long-term average, new deals) and decides which 1-4 topics get a slide, which layout each gets and why; the why is written into the slide notes and shown under "Why these slides". Without a model a rule-picked plan from the same candidates is used and labelled as the fallback. The Copilot can also write the whole storyline on request ("make the brief into slides", "a client update deck on the forest theme"): it picks the theme and layouts and writes the titles, so-what lines and notes; any number in its text that is not in the data is refused, and a post-build check reports overflow, overlaps and leftover text so the model fixes and rebuilds. See [docs/brief-deck.md](docs/brief-deck.md). |
| Shared data | Sources | One library for the whole team, three kinds of source, each shown as a coloured dot with a text label. Open data is collected automatically; uploaded reports come from anyone on the team; **internal data** is the company's own lettings, leases and valuations, recorded from a sentence to the Copilot, a photo (lease page, WhatsApp screenshot), a PDF or a spreadsheet, all through the same agent into one deal record. Pieces arrive separately and are merged by property and floor; drafts list their missing fields; the recorder confirms; each record is internal-only or quotable, and the brief lists "Our deals" apart from "Market deals" (the IC paper gets quotable records only). See [docs/internal-data.md](docs/internal-data.md). Cards for the gathering round, adding a source (the agent proposes how it will be collected after reading its terms), the information agent, and what needs a person. |

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
Copilot keeps its chat model. The default is Xiaomi MiMo-V2.6-Flash through its OpenAI-compatible API,
two pages per call with JSON-schema output: `export MIMO_API_KEY=...`. Without that key PDFs use the chat
model; without any key, or if the vision call fails, a rule-based text extractor is used instead.
`python scripts/eval_extraction.py <folder of PDFs named by source_id>` scores the extractor against the
hand-curated seed figures (recall, precision, and how many pre-ticked figures were right).

## Try it in three steps

```bash
git clone https://github.com/Kenneth0416/nanfengtest.git && cd nanfengtest
cp .env.example .env              # add MIMO_API_KEY (or an Anthropic / OpenAI key) for the Copilot; optional
docker compose up                 # Python + Node 22 + Pi Durable in one image; then open http://localhost:8501
```

Three things to try first: on Monitor, press **Add to brief** on two signals and open **Team brief**; press
**Build slides** there and download the deck; ask the Copilot *"Compare Midtown and City Core"* or *"What are the
main downside risks right now?"*. Without a key, everything except the Copilot, PDF reading and gathering
rounds still works (they are plain Python over the database) and the Copilot says it is offline.

> **Data notice.** The seed figures in `reference/seed/` are restated from Knight Frank's public London office
> research so the PoC has something real to show. Knight Frank's website terms do not permit automated
> collection or AI use of its content, which is why the app itself classifies Knight Frank as an "upload only"
> source and never fetches it. The seed data is therefore **for evaluating this PoC only**; a production
> version would run on the team's own subscribed reports (uploaded by a licensed user), licensed feeds
> (CoStar, EGi, agency data services) and the open data the connectors collect. The BNP Paribas sample PDF
> in `reference/samples/` shows the "swap the source" path working.

## Quick start without Docker

```bash
pip install -r requirements.txt
streamlit run app.py              # web app (recommended); dashboards, brief and slides need no key
python main.py chat                 # or the command line
pytest -q tests                     # the Copilot tests skip (not fail) until Node 22 + `npm ci` are present
```

### Running the agent (Pi Durable)

There is one agent engine: [Pi Durable](https://earendil.com/posts/pi-durable/). The Copilot and the
information agent both run on it. It commits every model turn and tool call to SQLite before showing it,
so if the process dies mid-answer, asking again resumes from the last checkpoint instead of starting over,
and each saved chat keeps its own persistent conversation (one Pi store per person under `data/pi/`, keyed by chat). It needs Node.js 22+, its packages and one key:

```bash
cd pi_engine && npm ci && cd ..
export MIMO_API_KEY=...           # Xiaomi MiMo-V2.6-Flash for everything: Copilot, information agent, PDFs
# or
export ANTHROPIC_API_KEY=...      # uses claude-opus-5-5 (configurable in config.yaml)
# or
export OPENAI_API_KEY=...         # uses gpt-5.5
```

The server must be able to reach the model API (api.xiaomimimo.com for MiMo).

Without them the dashboards, signals, brief and sources still work (they are plain Python over the
database), and the Copilot, uploads and gathering rounds say what is missing instead of answering.

### Running on a server

`docker compose --profile server up -d` adds Caddy (HTTPS, certificate renewal) in front of the app: set
your domain in `deploy/Caddyfile`, put the key in `.env`, and install `deploy/london-agent-collect.timer`
for the daily collection. The app is built to run on a VPS with Node 22, Pi Durable and a shared SQLite database. `reference/`
holds the seed data and the sample PDF and ships with the code; `data/` holds only runtime state
(`agent.db`, Pi Durable's store, uploaded reports), so it can be a mounted volume. SQLite runs in WAL
mode with a busy timeout, so the web app and the scheduled jobs can write at the same time. Schedule
both jobs daily (systemd timer or cron):

```bash
python main.py refresh    # open-data feeds
python main.py gather     # Pi information agent: colleagues' links and tips, open data, new report titles
python main.py housekeep  # lifecycle: advance states, re-score live stories, build the day's digest
```

The Python skills are the tools: Pi Durable calls them through a local HTTP bridge on 127.0.0.1.

## Other commands

```bash
python main.py refresh                  # load seed data + pull live BoE rate and news RSS
python main.py gather                   # one round of the information agent
python main.py process "https://…"      # hand one link or instruction to the information agent
python main.py brief [--ic]             # team brief as markdown (board, or IC paper section)
python main.py brief --pptx [--ic] [--theme forest-cream] [--fixed]   # a 3-6 slide deck under data/exports/, slides chosen by the Copilot from the data (--fixed: rule-picked)
python main.py signals                 # the team's top signals
python main.py ingest reference/samples/sample_bnp_paribas_q2_2025_restated.pdf   # add --save to store
python main.py classify "Visa takes 300,000 sq ft at 1 Canada Square"
python -m pytest -q tests
```

## Architecture

```
connectors/  (pluggable data sources)      skills/  (pluggable agent skills, SKILL.md + tools.py)
  seed_csv     curated research data         market_metrics     trends, snapshots
               (agency reports as uploads)
  boe_rates    Bank of England, live         submarket_compare  side by side, rankings
  news_rss     news feeds, live              supply_and_deals   pipeline, lettings, investment deals
        │                                    macro_watch        Bank Rate, labour market
        ▼                                    news_monitor       search + classify news
  core/classifier.py  detects what each      watchlist_alerts   signal cards, user alert rules
  item is (figure, deal, scheme, macro,      market_brief       team brief (board / IC)
                                             brief_deck         the brief as a PowerPoint: data-driven storyline, 5 themes, 13 layouts
                                             internal_data      our own deals: record, list, confirm, mark quotable
  news) and tags market, theme, sentiment,   report_ingest      PDF extraction + conflict check
                                             market_gather      links/tips, merge, hotness
  importance                                          │
        │                                             ▼
        ▼                                   core/engine.py → Pi Durable (pi_engine/agent.ts)
  core/store.py (SQLite)  ──►  core/signals.py         and info_agent.ts, tools via core/bridge.py
                               ranked cards for team
                                        │
                                        ▼
                         app.py (Streamlit) · main.py (CLI)
```

* **Gathering:** `core/gather.py` (read, classify, match, merge, hotness, report titles),
  `pi_engine/info_agent.ts` (the Pi information agent), `info_skills/` (its playbooks),
  `skills/info_processing` (parsing steps), `pi_engine/common.ts` (bridge and model).
* **Shared library:** `core/library.py` (feeds, freshness, expected reports) and `core/store.py`
  (each source's channel, uploader, upload time and file hash; each figure's status: ok, flagged or rejected).
* **Add a data source:** write `connectors/<name>.py` with a `Connector.fetch()` that returns raw items,
  then list it in `config.yaml`. The classifier decides what each item is; the connector never writes to the store.
* **Add a skill:** create `skills/<name>/SKILL.md` (what it is for) and `tools.py` (a `TOOLS` list), then list it
  in `config.yaml`. The agent's system prompt and tool list are built from these files.

## Look and feel

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

## What is real and what is demo

Every page carries a one-line notice: market figures are restated from public Knight Frank reports (evaluation
only); Bank Rate and news are collected live; the three internal deals and the colleague names are demo data and
say so (a "Demo data" chip). The seed snapshot is loaded, never counted as data collected today; the ONS series
is a seed snapshot, not a live feed; supply items from a report older than two quarters say so and rank lower; the
team summary names the report its long-term averages come from.

## Data

`reference/seed/` holds figures restated from public Knight Frank London office reports (Q1 2024 to Q2 2026,
shown as uploads by "PoC seed", because that is the channel they would use: Knight Frank's terms bar
automated collection and AI use, so the app never fetches from it and the seed is for evaluation only; see
the data notice at the top),
Bank of England and ONS releases, each row linked to its source in `sources.csv`. Some reports have
unlabelled columns; where a mapping was inferred the row says so in `note`. Two deliberate data-quality cases
are kept because they are real: Knight Frank's Q3 2024 report gives London vacancy as both 9.1% and 9.4%, and
its "under construction" series switches from total to speculative-only in Q3 2025. Verify figures against
the originals before external use; a production version would connect to licensed feeds (CoStar, EGi, agency data).

The sample PDF in `reference/samples/` restates BNP Paribas Real Estate's public Q2 2025 figures to show how the
agent maps another publisher's market names and flags where its numbers differ from Knight Frank's.
