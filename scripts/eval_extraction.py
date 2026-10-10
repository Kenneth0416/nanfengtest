"""Score PDF extraction against hand-curated figures.

Put the reports in one folder, each named by its source_id in reference/seed/sources.csv
(for example KF_SPOT_2026Q2.pdf), then run:

    python scripts/eval_extraction.py path/to/pdfs [--truth reference/seed/observations.csv]

For each report it extracts figures with the configured model (or the rule-based extractor with no
key) and compares them with the curated rows for that source_id:
  recall     share of curated figures the extractor found with the same value
  precision  share of extracted figures that match a curated figure
  pre-ticked share of pre-ticked (passed every check) figures that are correct
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import documents  # noqa: E402
from core.app import App  # noqa: E402


def close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.011, abs(b) * 0.005)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("folder")
    p.add_argument("--truth", default=str(Path(__file__).resolve().parent.parent / "reference/seed/observations.csv"))
    a = p.parse_args(argv)
    truth = defaultdict(list)
    with open(a.truth) as f:
        for r in csv.DictReader(f):
            truth[r["source_id"]].append((r["market"], r["metric"], float(r["value"])))
    app = App(live=False)
    app.ensure_data()
    totals = defaultdict(int)
    print(f"{'report':<22}{'curated':>8}{'found':>7}{'extracted':>10}{'correct':>8}{'pre-ticked ok':>15}")
    for pdf in sorted(Path(a.folder).glob("*.pdf")):
        want = truth.get(pdf.stem)
        if not want:
            print(f"{pdf.stem:<22} skipped: no curated rows for this source_id")
            continue
        got = documents.analyse_document(app.store, app.llm, pdf)["candidates"]
        hit = lambda c: any(c["market"] == m and c["metric"] == k and close(c["value"], v) for m, k, v in want)
        found = sum(any(c["market"] == m and c["metric"] == k and close(c["value"], v) for c in got) for m, k, v in want)
        correct = sum(hit(c) for c in got)
        ticked = [c for c in got if c.get("suggest_keep")]
        ticked_ok = sum(hit(c) for c in ticked)
        for key, n in (("curated", len(want)), ("found", found), ("extracted", len(got)), ("correct", correct),
                       ("ticked", len(ticked)), ("ticked_ok", ticked_ok)):
            totals[key] += n
        print(f"{pdf.stem:<22}{len(want):>8}{found:>7}{len(got):>10}{correct:>8}{f'{ticked_ok}/{len(ticked)}':>15}")
    if totals["curated"]:
        print(f"\nRecall {totals['found'] / totals['curated']:.0%} · precision "
              f"{totals['correct'] / max(totals['extracted'], 1):.0%} · pre-ticked correct "
              f"{totals['ticked_ok'] / max(totals['ticked'], 1):.0%} · method: {app.llm.name}")


if __name__ == "__main__":
    main()
