"""Plug-in contracts for skills and connectors."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Context:
    """What every tool handler and connector receives."""
    store: Any
    config: dict
    llm: Any
    root: Path
    vision: Any = None                 # the model that reads PDF pages (see config.yaml vision)
    classifier: Any = None
    role: str = "team"
    app: Any = None                    # the running App, for tools that trigger collection


@dataclass
class Tool:
    """One callable capability. Handlers return a dict with at least `summary`
    (markdown a human can read), plus optional `data`, `sources` and `chart`."""
    name: str
    description: str
    parameters: dict
    handler: Callable[[Context, dict], dict]
    read_only: bool = True             # write tools are never replayed after a crash (Pi Durable)


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    tools: list[Tool] = field(default_factory=list)
    path: Path | None = None


class Connector:
    """Base class for data sources. `fetch` returns RawItems; the classifier
    decides what each item is, so a connector never writes to the store."""
    id = "base"

    def __init__(self, ctx: Context, options: dict | None = None):
        self.ctx = ctx
        self.options = options or {}

    def fetch(self) -> list:
        raise NotImplementedError


def obj_schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}
