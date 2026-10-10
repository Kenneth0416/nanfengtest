"""What the library does not cover, so the Copilot says so instead of answering a different question.

Two gaps matter in practice: a publisher the team has no figures from ("what does Savills say…"),
and a London area outside the submarket list ("Shoreditch").
"""
from __future__ import annotations

import re

from . import taxonomy as tx
from .documents import PUBLISHERS

_PUBLISHER_ALIASES = {p.lower(): p for p in PUBLISHERS}
_PUBLISHER_ALIASES.update({"cushman": "Cushman & Wakefield", "c&w": "Cushman & Wakefield", "bnp": "BNP Paribas",
                           "jones lang": "JLL", "kf": "Knight Frank"})

# Areas people ask about that the submarket list does not have, with the nearest submarket(s) it does.
NEAREST = {
    "shoreditch": ["Clerkenwell/Farringdon", "Aldgate/Whitechapel"],
    "hoxton": ["Clerkenwell/Farringdon"], "old street": ["Clerkenwell/Farringdon"],
    "tech city": ["Clerkenwell/Farringdon", "Aldgate/Whitechapel"],
    "liverpool street": ["City Core"], "spitalfields": ["Aldgate/Whitechapel"],
    "london bridge": ["Southbank Core"], "bankside": ["Southbank Core"], "waterloo": ["Southbank Core"],
    "southwark": ["Southbank Core"], "islington": ["King's Cross/Euston"], "camden": ["King's Cross/Euston"],
    "hammersmith": ["White City"], "mayfair": ["West End Core"],
    "croydon": [], "hammersmith & fulham": ["White City"], "wembley": [], "richmond": [], "chiswick": [],
}


def publisher_gaps(question: str, store) -> list[str]:
    q = question.lower()
    asked = {p for alias, p in _PUBLISHER_ALIASES.items() if re.search(rf"\b{re.escape(alias)}\b", q)}
    held = {s.get("publisher") for s in store.sources().values()}
    followed = {r["publisher"]: r["name"] for r in store.q("SELECT name, publisher FROM followed")}
    notes = []
    for p in sorted(asked - held):
        if p in followed:
            notes.append(f"The team follows {followed[p]}, but nobody has uploaded a {p} report yet, so the library "
                         f"has no {p} figures. Anyone can upload one on 🗂️ Sources.")
        else:
            notes.append(f"The library has no {p} figures yet. Anyone can upload a {p} report on 🗂️ Sources, "
                         f"or ask me to follow {p}.")
    if notes and held - {"Bank of England", "Office for National Statistics"}:
        others = ", ".join(sorted(held - {"Bank of England", "Office for National Statistics", None}))
        notes.append(f"Below are the figures the library does hold ({others}).")
    return notes


def area_gaps(question: str) -> list[str]:
    q = question.lower()
    covered = tx.find_markets(question)
    notes = []
    for area, near in NEAREST.items():
        if not re.search(rf"\b{re.escape(area)}\b", q):
            continue
        if area == "mayfair":  # covered through the West End Core, with a boundary warning
            continue
        name = area.title()
        if near:
            notes.append(f"I don't have {name} figures: it is not one of the submarkets the library tracks. "
                         f"The nearest covered submarket{'s are' if len(near) > 1 else ' is'} {' and '.join(near)}.")
        else:
            notes.append(f"I don't have {name} figures: the library covers central London submarkets only.")
        if covered and not any(m in near for m in covered):
            notes[-1] += f" The figures below are for {', '.join(covered)}, which you also mentioned."
    return notes


def note(question: str, store) -> str:
    """One short paragraph, or '' when the question is fully covered."""
    return " ".join(area_gaps(question) + publisher_gaps(question, store))

