"""Shared vocabulary: markets, metrics, themes and news categories.

Every connector, skill and the classifier map raw text onto these canonical
names, so data from different publishers can be compared like for like.
"""
from __future__ import annotations

import re

# --- Markets ---------------------------------------------------------------
# Canonical market -> parent. "London" follows Knight Frank's definition
# (West End + City & Southbank + Docklands & Stratford).
MARKET_PARENT = {
    "London": None,
    "West End": "London",
    "City & Southbank": "London",
    "Docklands & Stratford": "London",
    "West End Core": "West End", "Soho": "West End", "Marylebone": "West End",
    "Fitzrovia": "West End", "Midtown": "West End", "Bloomsbury": "West End",
    "King's Cross/Euston": "West End", "Paddington": "West End", "Victoria": "West End",
    "Strand/Covent Garden": "West End", "Knightsbridge/Chelsea": "West End",
    "White City": "West End",
    "City Core": "City & Southbank", "Clerkenwell/Farringdon": "City & Southbank",
    "Aldgate/Whitechapel": "City & Southbank", "Southbank Core": "City & Southbank",
    "Vauxhall/Battersea": "City & Southbank",
    "Canary Wharf": "Docklands & Stratford", "Rest of Docklands": "Docklands & Stratford",
    "Stratford": "Docklands & Stratford",
}
TOP_MARKETS = ["London", "West End", "City & Southbank", "Docklands & Stratford"]
# Prime rents are quoted for the core submarket of each market.
CORE_SUBMARKET = {"West End": "West End Core", "City & Southbank": "City Core",
                  "Docklands & Stratford": "Canary Wharf"}

# alias -> (canonical market, exact match?). Non-exact aliases are a different
# boundary from the canonical market, so figures need a definition warning.
_ALIASES = {
    "central london": ("London", False), "london": ("London", True),
    "west end": ("West End", True), "west end core": ("West End Core", True),
    "mayfair": ("West End Core", False), "st james's": ("West End Core", False),
    "st james": ("West End Core", False),
    "city & southbank": ("City & Southbank", True), "city and southbank": ("City & Southbank", True),
    "city of london": ("City & Southbank", False), "the city": ("City & Southbank", False),
    "city": ("City & Southbank", False), "city core": ("City Core", True),
    "square mile": ("City Core", False),
    "docklands & stratford": ("Docklands & Stratford", True), "docklands": ("Docklands & Stratford", False),
    "canary wharf": ("Canary Wharf", True), "rest of docklands": ("Rest of Docklands", True),
    "stratford": ("Stratford", True), "midtown": ("Midtown", True), "holborn": ("Midtown", False),
    "king's cross": ("King's Cross/Euston", False), "kings cross": ("King's Cross/Euston", False),
    "euston": ("King's Cross/Euston", False), "king's cross/euston": ("King's Cross/Euston", True),
    "southbank": ("Southbank Core", False), "south bank": ("Southbank Core", False),
    "southbank core": ("Southbank Core", True),
    "fitzrovia": ("Fitzrovia", True), "soho": ("Soho", True), "marylebone": ("Marylebone", True),
    "paddington": ("Paddington", True), "victoria": ("Victoria", True), "bloomsbury": ("Bloomsbury", True),
    "farringdon": ("Clerkenwell/Farringdon", False), "clerkenwell": ("Clerkenwell/Farringdon", False),
    "aldgate": ("Aldgate/Whitechapel", False), "whitechapel": ("Aldgate/Whitechapel", False),
    "battersea": ("Vauxhall/Battersea", False), "vauxhall": ("Vauxhall/Battersea", False),
    "nine elms": ("Vauxhall/Battersea", False), "white city": ("White City", True),
    "knightsbridge": ("Knightsbridge/Chelsea", False), "chelsea": ("Knightsbridge/Chelsea", False),
    "covent garden": ("Strand/Covent Garden", False), "strand": ("Strand/Covent Garden", False),
    "aldwych": ("Strand/Covent Garden", False),
}
for _m in MARKET_PARENT:
    _ALIASES.setdefault(_m.lower(), (_m, True))

# Postcode districts -> submarket (approximate).
_POSTCODES = [
    (r"\bEC[1][A-Z]?\b", "Clerkenwell/Farringdon"), (r"\bEC[2-4][A-Z]?\b", "City Core"),
    (r"\bE14\b", "Canary Wharf"), (r"\bE(15|20)\b", "Stratford"), (r"\bE1[A-Z]?\b", "Aldgate/Whitechapel"),
    (r"\bW1[A-Z]?\b", "West End Core"), (r"\bWC[12][A-Z]?\b", "Midtown"), (r"\bSW1[A-Z]?\b", "Victoria"),
    (r"\bN1[A-Z]?\b", "King's Cross/Euston"), (r"\bNW1\b", "King's Cross/Euston"), (r"\bSE1\b", "Southbank Core"),
    (r"\bW14\b", "West End"), (r"\bW12\b", "White City"),
]
_ALIAS_RE = sorted(_ALIASES, key=len, reverse=True)


def resolve_market(name: str) -> tuple[str | None, bool]:
    """Map a free-text market name to (canonical market, exact?)."""
    if not name:
        return None, False
    key = name.strip().lower().replace("’", "'")
    if key in _ALIASES:
        return _ALIASES[key]
    for alias in _ALIAS_RE:
        if re.search(rf"\b{re.escape(alias)}\b", key):
            return _ALIASES[alias]
    return None, False


def find_markets(text: str, use_postcodes: bool = True) -> list[str]:
    """All canonical markets mentioned in a piece of text, most specific first."""
    low = " " + text.lower().replace("’", "'") + " "
    hits: dict[str, int] = {}
    taken = low
    for alias in _ALIAS_RE:
        pattern = rf"(?<![a-z]){re.escape(alias)}(?![a-z])"
        m = re.search(pattern, taken)
        if m:
            market = _ALIASES[alias][0]
            hits[market] = min(hits.get(market, m.start()), m.start())
            taken = re.sub(pattern, lambda x: " " * len(x.group(0)), taken)
    found = sorted(hits, key=hits.get)   # order of appearance in the text
    if use_postcodes and not found:
        for pattern, market in _POSTCODES:
            if re.search(pattern, text) and market not in found:
                found.append(market)
    # Drop "London" when something more specific was found.
    if len(found) > 1 and "London" in found:
        found.remove("London")
    return found


def top_market(market: str) -> str:
    while MARKET_PARENT.get(market) not in (None, "London"):
        market = MARKET_PARENT[market]
    return market


# --- Metrics ---------------------------------------------------------------
# good_when: direction that is good news for landlords/investors.
METRICS = {
    "prime_rent_psf": dict(label="Prime rent", unit="£/sq ft", good_when="up",
                           aliases=["prime rent", "rent", "rents", "headline rent"]),
    "grade_a_rent_psf": dict(label="Grade A rent", unit="£/sq ft", good_when="up",
                             aliases=["grade a rent", "grade a rents", "new-build rent", "best-in-class rent"]),
    "vacancy_pct": dict(label="Vacancy rate", unit="%", good_when="down",
                        aliases=["vacancy", "vacancy rate", "vacant", "empty"]),
    "new_refurb_vacancy_pct": dict(label="New/refurb (Grade A) vacancy", unit="%", good_when="down",
                                   aliases=["grade a vacancy", "new vacancy", "new/refurb vacancy", "new space vacancy"]),
    "take_up_msqft": dict(label="Take-up", unit="m sq ft", good_when="up",
                          aliases=["take-up", "take up", "takeup", "leasing", "lettings", "leasing activity"]),
    "availability_msqft": dict(label="Availability", unit="m sq ft", good_when="down",
                               aliases=["availability", "available space", "supply"]),
    "active_requirements_msqft": dict(label="Active requirements", unit="m sq ft", good_when="up",
                                      aliases=["active requirements", "requirements", "demand"]),
    "under_construction_msqft": dict(label="Under construction (total)", unit="m sq ft", good_when="down",
                                     aliases=["under construction", "construction"]),
    "under_construction_spec_msqft": dict(label="Under construction (speculative)", unit="m sq ft", good_when="down",
                                          aliases=["speculative", "spec development"]),
    "investment_gbp_bn": dict(label="Investment volume", unit="£bn", good_when="up",
                              aliases=["investment", "investment volume", "turnover", "capital"]),
    "prime_yield_pct": dict(label="Prime yield", unit="%", good_when="down",
                            aliases=["yield", "yields", "prime yield"]),
    "rent_free_months": dict(label="Rent-free (10-yr lease)", unit="months", good_when="down",
                             aliases=["rent free", "rent-free", "incentive", "incentives"]),
    "new_refurb_take_up_share_pct": dict(label="New/refurbished share of take-up", unit="%", good_when="up",
                                         aliases=["new or refurbished share", "new and refurbished share",
                                                  "grade a share of take-up", "share of take-up"]),
    "prelet_share_under_construction_pct": dict(label="Pre-let share of space under construction", unit="%",
                                                good_when="up", aliases=["pre-let share", "prelet"]),
}
# Series that changed definition between editions of the same publisher.
DEFINITION_SUCCESSORS = {"under_construction_msqft": "under_construction_spec_msqft"}


def find_metrics(text: str) -> list[str]:
    low = text.lower()
    hits = []
    for key, spec in sorted(METRICS.items(), key=lambda kv: -max(len(a) for a in kv[1]["aliases"])):
        if any(re.search(rf"\b{re.escape(a)}\b", low) for a in spec["aliases"]) and key not in hits:
            hits.append(key)
    # "grade a vacancy" also matches "vacancy": keep the more specific one only.
    if "new_refurb_vacancy_pct" in hits and "vacancy_pct" in hits and "grade a" in low:
        hits.remove("vacancy_pct")
    if "grade_a_rent_psf" in hits and "prime_rent_psf" in hits and "prime" not in low and "headline" not in low:
        hits.remove("prime_rent_psf")
    return hits


def fmt_value(metric: str, value: float) -> str:
    unit = METRICS.get(metric, {}).get("unit", "")
    if unit == "£/sq ft":
        return f"£{value:,.2f}/sq ft"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "£bn":
        return f"£{value:.2f}bn"
    if unit == "m sq ft":
        return f"{value:.2f}m sq ft"
    return f"{value:g} {unit}".strip()


# --- Themes & news categories ----------------------------------------------
THEMES = {
    "flight_to_quality": ["flight to quality", "new or refurbished", "new and refurbished", "grade a",
                          "best-in-class", "high-quality", "prime space", "new space"],
    "esg": ["esg", "sustainab", "net zero", "net-zero", "epc", "green", "carbon", "breeam"],
    "hybrid_working": ["hybrid", "remote work", "return to office", "office attendance", "work from home", "wfh"],
    "tech_ai": [" ai ", "ai company", "artificial intelligence", "tech", "data ", "software", "openai",
                "anthropic", "databricks", "google", "meta"],
    "financial_services": ["bank", "capital", "investment management", "barclays", "jpmorgan", "jp morgan",
                           "hsbc", "visa", "s&p", "insurance", "squarepoint", "evercore", "ares"],
    "legal": ["law firm", "llp", "freehills", "shearman", "solicitors", "gibson, dunn", "mcdermott", "legal"],
    "interest_rates": ["bank rate", "interest rate", "monetary policy", "mpc", "rate cut", "rate volatility"],
    "supply_shortage": ["undersupply", "undersupplied", "shortage", "constrained", "0.5%", "limited supply"],
    "labour_market": ["unemployment", "employment", "payroll", "jobs", "vacancies fell", "labour market"],
}

NEWS_CATEGORIES = {
    "macro_policy": ["bank of england", "bank rate", "monetary policy", "unemployment", "inflation", "gdp",
                     "ons", "labour market", "payrolled"],
    "investment_deal": ["buys", "bought", "acquire", "acquired", "sells", "sold", "for £", "yield",
                        "investment"],
    "development_pipeline": ["under construction", "speculative", "completion", "complete", "pipeline",
                             "scheme", "refurbishment", "planning", "undersupplied"],
    "leasing_deal": ["takes", "let ", "lets", "letting", "signs", "signed", "pre-let", "pre-lets",
                     "commits", "lease", "sq ft at", "relocat", "taken", "looking for", "in the market for",
                     "requirement for", "under offer at"],
    "market_stats": ["vacancy", "take-up", "availability", "active requirements", "under offer",
                     "investment volumes", "share of take-up"],
}
CATEGORY_LABELS = {
    "leasing_deal": "Leasing deal", "investment_deal": "Investment deal",
    "development_pipeline": "Supply pipeline", "macro_policy": "Macro & policy",
    "market_stats": "Market statistics", "other": "Other",
}
