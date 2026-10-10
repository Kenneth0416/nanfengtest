---
name: info_processing
description: Reads any incoming material for the team library (PDF reports, web pages and articles, spreadsheets and open-data tables, company results) one step at a time, checks every figure and files it. Used by the information agent; the playbooks are in info_skills/.
---
Pick the playbook for the material with load_skill (check-terms, fetch-source, read-pdf, read-table,
read-article, map-submarkets, check-figures, dedupe) and follow it. Never save a figure that has not
been through check_figures: figures that fail a check are saved with ⚠ for a person, never dropped
silently and never quoted as checked.
