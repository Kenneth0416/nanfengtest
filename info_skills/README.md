# Information agent skills

Playbooks for the Pi information agent (`pi_engine/info_agent.ts`). The agent sees each skill's name
and description, loads the full playbook with `load_skill` when it needs it, and follows it with the
tools named there. Add a skill by adding a folder with a `SKILL.md`; no code changes.

| Skill | For | Main tools |
|---|---|---|
| check-terms | a new source someone wants to follow | follow_source |
| fetch-source | getting any link: page, feed, PDF, spreadsheet | fetch_source |
| dedupe | before reading anything: is it already in the library? | dedupe_report, find_matches |
| read-pdf | agency reports, results statements, any PDF with figures | pdf_overview, read_pdf_pages, pdf_page_text |
| read-table | CSV / Excel / JSON from open-data portals and APIs | read_table, save_series |
| read-article | news, newsletters, LinkedIn posts, colleagues' tips | classify_item, find_matches, save_item, score_hotness |
| map-submarkets | turning a publisher's market names into the team's submarkets | map_markets |
| check-figures | the three checks before any figure is saved | check_figures, stage_figures, save_figures |
| read-photo | 🔵 our own deals from a photo, screenshot, lease PDF or spreadsheet | read_photo, save_internal_deal, deals_from_table |
