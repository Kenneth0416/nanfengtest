"""Plain data records that move between connectors, the classifier and skills."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RawItem:
    """Anything a connector produces before it has been classified.

    `payload` holds a structured row (CSV, API); `text` holds free text (news,
    PDF). The classifier decides what the item is from its content.
    """
    connector: str
    payload: dict[str, Any] | None = None
    text: str = ""
    title: str = ""
    url: str = ""
    published: str = ""
    source: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    period: str            # e.g. "2026Q2"
    market: str            # canonical market
    metric: str            # key in taxonomy.METRICS
    value: float
    source_id: str
    lta: float | None = None   # long-term average, when published
    note: str = ""


@dataclass
class NewsItem:
    id: str
    title: str
    body: str
    url: str
    source: str
    published: str
    category: str = "other"
    markets: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    sentiment: str = "neutral"   # for office landlords/investors: positive | negative | neutral
    importance: int = 1          # 1-5
    size_sqft: int | None = None
    value_gbp_m: float | None = None
    classified_by: str = "rules"
    # Team gathering: who shared it, which other outlets carried the same story, when the agent first
    # saw it, and how hot it is (0-100) with the reasons.
    shared_by: list[dict] = field(default_factory=list)   # {who, how, when, note, url}
    also_reported: list[dict] = field(default_factory=list)  # {source, url, published}
    discovered: str = ""
    hot: int = 0
    why_hot: str = ""
    story_id: str = ""           # the story this item belongs to (its own id, or the one it was merged into)
    state: str = "new"           # lifecycle: new | active | cooling | archived | expired


@dataclass
class Evidence:
    text: str
    source_id: str = ""
    url: str = ""


@dataclass
class Signal:
    kind: str
    title: str
    detail: str
    why: str
    severity: int                      # 1 low - 3 high
    direction: str = "flat"            # up | down | flat
    tone: str = "neutral"              # positive | negative | neutral (for landlords/investors)
    markets: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    metric: str = ""                   # set when the signal is about one metric
    category: str = ""                 # news category, for news signals
    roles: dict[str, float] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    as_of: str = ""
    obs_id: int | None = None          # the stored figure behind it, so anyone can flag it
    hot: int = 0                       # news: 0-100, with the reasons in why_hot
    why_hot: str = ""
    shared_by: list[dict] = field(default_factory=list)  # colleagues who shared it
    discovered: str = ""
    story: str = ""                    # news: the story id, so a digest shows one card per story
    flag: str = ""                     # set while a colleague's flag on that figure is unresolved
    before: str = ""                   # the figure before the change, as shown on the card ("8.5%")
    after: str = ""                    # the figure now ("8.0%")
    change: str = ""                   # the change, short ("-0.5 pt QoQ")
    context: str = ""                  # one more fact for the numbers line ("down from 9.9% in Q1 2024")
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha1(f"{self.kind}|{self.title}".encode()).hexdigest()[:10]

    def to_dict(self) -> dict:
        return asdict(self)
