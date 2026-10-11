"""Builds the shared application context used by the CLI and the web app."""
from __future__ import annotations

import os
from pathlib import Path

from .classifier import Classifier
from .ingest import refresh
from .llm import get_llm, get_vision
from .registry import all_tools, load_config, load_connectors, load_skills
from .skill import Context
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


class App:
    def __init__(self, root: Path = ROOT, live: bool | None = None):
        self.root = root
        self.config = load_config(root)
        self.llm = get_llm(self.config.get("llm", {}))
        self.vision = get_vision(self.config.get("vision", {}), self.llm)  # reads PDF pages
        self.store = Store(root / self.config.get("database", "data/agent.db"))
        self.ctx = Context(store=self.store, config=self.config, llm=self.llm, vision=self.vision, root=root,
                           classifier=Classifier(self.llm, self.config["llm"].get("classify_news_with_llm", True)))
        self.ctx.app = self
        self.skills = load_skills(root, self.config["skills"])
        self.tools = all_tools(self.skills)
        self.connectors = load_connectors(self.ctx, self.config["connectors"])
        self.live = os.getenv("AGENT_OFFLINE") != "1" if live is None else live

    def refresh(self, by: str = "Auto-update") -> list[dict]:
        """Collect every open-data feed. Logged to team activity so everyone sees when data last came in."""
        conns = self.connectors if self.live else [c for c in self.connectors if c.id == "seed_research"]
        reports = refresh(self.ctx, conns)
        names = {f.get("connector"): f["name"] for f in self.config.get("feeds", [])}
        # The curated seed snapshot (figures restated from public reports) is loaded, not collected: it is never
        # counted as data that came in today, so the activity line only names the live connectors.
        parts = [f"{names.get(r['connector'], r['connector'])} "
                 + ("failed" if r.get("error") else f"{sum(r['counts'].values())} items")
                 for r in reports if r["connector"] != "seed_research"]
        self.store.log("auto", by, ("collected open data: " + "; ".join(parts)) if parts
                       else "loaded the PoC seed snapshot (no live feeds in this run)")
        self.seed_internal()
        return reports

    def seed_internal(self):
        """Three demo internal records (reference/seed/internal_deals.json) when the team has none yet, so the
        Sources page and the brief show the inside / outside split from the first run."""
        from .internal import finish, load_json, compare_external
        path = self.root / "reference" / "seed" / "internal_deals.json"
        if self.store.internal_deals() or not path.exists():
            return
        for d in load_json(path):
            d = finish(d)
            d["originals"] = []
            d["ext"] = compare_external(self.store, d)
            self.store.save_internal_deal(d)

    def refresh_if_due(self) -> list[dict] | None:
        """Safety net for the daily timer: collect open data when the app starts and the last run is stale."""
        from .library import auto_due
        return self.refresh() if auto_due(self.store, self.config) else None

    def skill_text(self, name: str) -> str:
        sk = next((s for s in self.skills if s.name == name), None)
        return f"{sk.description}\n\n{sk.instructions}" if sk else ""

    def info_manifest(self) -> dict:
        """What the Pi information agent needs: its instructions, the skill catalogue and where files go."""
        from skills.info_processing.tools import list_skills
        return {"system": self.skill_text("market_gather") + "\n\n" + self.skill_text("info_processing"),
                "skills": list_skills(self.ctx, {})["data"], "skills_dir": str(self.root / "info_skills"),
                "report_index": self.config.get("report_index", [])}

    def focus(self, user: str) -> dict:
        """The user's own focus, or their role preset if they have not changed anything."""
        from .focus import defaults
        return self.store.focus(user) or defaults(self.config, user)

    def ensure_data(self):
        if not self.store.q("SELECT 1 FROM observations LIMIT 1"):
            self.refresh()
        else:
            self.refresh_if_due()

    def call(self, tool: str, args: dict, role: str | None = None) -> dict:
        if role:
            self.ctx.role = role
        return self.tools[tool].handler(self.ctx, args)
