"""Discovers skills and connectors listed in config.yaml.

Adding a capability = drop a folder in skills/ (SKILL.md + tools.py) or a
module in connectors/, then list it in config.yaml. Nothing in core changes.
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import yaml

from .skill import Context, Skill, Tool


def load_config(root: Path) -> dict:
    with open(root / "config.yaml") as f:
        return yaml.safe_load(f)


def _frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        return yaml.safe_load(fm) or {}, body.strip()
    return {}, text


def load_skills(root: Path, enabled: list[str]) -> list[Skill]:
    skills = []
    for name in enabled:
        folder = root / "skills" / name
        meta, body = _frontmatter((folder / "SKILL.md").read_text())
        spec = importlib.util.spec_from_file_location(f"skills.{name}.tools", folder / "tools.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        skills.append(Skill(name=meta.get("name", name), description=meta.get("description", ""),
                            instructions=body, tools=list(getattr(module, "TOOLS", [])), path=folder))
    return skills


def load_connectors(ctx: Context, entries: list[dict]) -> list:
    out = []
    for entry in entries:
        if not entry.get("enabled", True):
            continue
        module = importlib.import_module(entry["module"])
        conn = module.Connector(ctx, entry.get("options", {}))
        conn.id = entry.get("id", conn.id)
        out.append(conn)
    return out


def all_tools(skills: list[Skill]) -> dict[str, Tool]:
    return {t.name: t for s in skills for t in s.tools}
