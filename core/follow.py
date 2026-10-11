"""Anyone on the team can follow a new information source. The agent checks the source's terms first:

  auto    the terms allow automated collection: it joins the feeds the agent collects every day
          (an RSS feed in full; a web page as headlines and links only)
  upload  the terms restrict automated collection or AI use, or they could not be read: the team is
          reminded to upload each new issue, and the agent never fetches it

Followed sources are shared: everyone sees them, and everyone gets the reminders.
The fetching (robots.txt, the page, its terms page) is done by the Pi tool `check_source_terms`
(pi_engine/info_agent.ts) or by `fetch_evidence` below; `assess` only reads what was fetched.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlparse

UA = "Mozilla/5.0 (london-office-agent PoC)"
CADENCE_DAYS = {"daily": 1, "weekly": 7, "monthly": 31, "quarterly": 92, "half-yearly": 183, "annual": 366}

# Open Government Licence publishers: free to collect and reuse with attribution.
OPEN_DOMAINS = ("gov.uk", "bankofengland.co.uk", "ons.gov.uk", "london.gov.uk", "nomisweb.co.uk",
                "cityoflondon.gov.uk", "data.gov.uk", "voa.gov.uk")
# Agency and data-vendor research: licensed to the reader. Knight Frank's terms bar AI-platform use
# outright; for the others we assume the same until a person reads their terms (an inference).
LICENSED_DOMAINS = ("knightfrank.", "savills.", "cbre.", "jll.", "cushmanwakefield.", "bnpparibas",
                    "colliers.", "costar.", "egi.co.uk", "estatesgazette.", "avisonyoung.", "lsh.co.uk",
                    "realestate.bnpparibas", "propertyweek.")
NAMES = {  # common names a colleague might type instead of a link
    "savills market watch": ("Savills", "https://www.savills.co.uk/research_articles/", "monthly"),
    "savills": ("Savills", "https://www.savills.co.uk/research_articles/", "quarterly"),
    "knight frank": ("Knight Frank", "https://www.knightfrank.co.uk/research", "quarterly"),
    "cbre": ("CBRE", "https://www.cbre.co.uk/insights", "quarterly"),
    "jll": ("JLL", "https://www.jll.co.uk/en/trends-and-insights/research", "quarterly"),
    "cushman": ("Cushman & Wakefield", "https://www.cushmanwakefield.com/en/united-kingdom/insights", "quarterly"),
    "bnp paribas": ("BNP Paribas Real Estate", "https://www.realestate.bnpparibas.co.uk/market-research", "quarterly"),
    "colliers": ("Colliers", "https://www.colliers.com/en-gb/research", "quarterly"),
    "city of london": ("City of London Corporation", "https://www.cityoflondon.gov.uk/services/planning", "quarterly"),
    "gla": ("Greater London Authority", "https://data.london.gov.uk/", "weekly"),
}
_BAN = re.compile(r"[^.]{0,200}\b(prohibit\w*|not permitted|may not|must not|shall not|forbid\w*|without (our|the) "
                  r"(prior )?(written )?(consent|permission))\b[^.]{0,200}\b(scrap\w*|crawl\w*|robots?|spider|automated|"
                  r"text and data mining|data mining|artificial intelligence|machine learning|AI\b|large language)"
                  r"[^.]{0,200}\.?", re.I)
_BAN_REV = re.compile(r"[^.]{0,200}\b(scrap\w*|crawl\w*|robots?|automated|text and data mining|artificial "
                      r"intelligence|machine learning|AI\b)[^.]{0,120}\b(prohibit\w*|not permitted|forbid\w*|"
                      r"is not allowed|are not allowed)[^.]{0,120}\.?", re.I)


_ASK = re.compile(r"(?i)^(please\s+)?(can you\s+|could you\s+)?(follow|add|track|watch|subscribe to)\b\s*")


def resolve(text: str) -> dict:
    """A link, or a name we know ('Savills Market Watch'). Returns name, publisher, url, cadence. The asking
    words are not part of the name: "Follow Savills Market Watch" is named "Savills Market Watch"."""
    text = text.strip()
    url = re.search(r"https?://\S+", text)
    if url:
        u = url.group(0).rstrip(").,")
        name = _ASK.sub("", text.replace(url.group(0), "").strip()).strip(" -:")
        return {"name": name or _publisher(u), "publisher": _publisher(u), "url": u, "cadence": ""}
    name = _ASK.sub("", text).strip(" -:") or text
    low = name.lower()
    for key in sorted(NAMES, key=len, reverse=True):
        if key in low:
            pub, u, cadence = NAMES[key]
            return {"name": name if len(name) < 80 else pub, "publisher": pub, "url": u, "cadence": cadence}
    return {"name": name, "publisher": "", "url": "", "cadence": ""}


def _publisher(url: str) -> str:
    host = urlparse(url).netloc.removeprefix("www.")
    for key, (pub, u, _) in NAMES.items():
        if urlparse(u).netloc.removeprefix("www.") == host:
            return pub
    return host


def robots_allows(robots: str, url: str, agent: str = "*") -> bool:
    """Minimal robots.txt check for the URL's path under the given user agent group."""
    path = urlparse(url).path or "/"
    allowed, group = True, False
    best = -1
    for line in robots.splitlines():
        line = line.split("#")[0].strip()
        if ":" not in line:
            continue
        key, val = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            group = val == agent or val == "*"
        elif group and key in ("allow", "disallow") and val and path.startswith(val) and len(val) > best:
            best, allowed = len(val), key == "allow"
    return allowed


_TERMS_SEGMENT = re.compile(r"^(terms(-|_)?(and|of|&)?(-|_)?(conditions|use|service|business)?|conditions|legal(-|_)?(notice|notices|information)?"
                            r"|copyright|disclaimer|t-?and-?cs?|tandcs?|tcs|privacy-and-terms|policies)(\.[a-z]+)?$")


def is_terms_url(href: str) -> bool:
    """A real terms page: a short path whose segment is 'terms', 'legal', 'conditions'…, never an article
    whose headline happens to contain 'legal' (/news/2026/10/legal-battle-over-...)."""
    path = urlparse(href).path.lower().rstrip("/")
    segs = [p for p in path.split("/") if p]
    if len(segs) > 3 or any(re.fullmatch(r"\d{4}|\d{1,2}", p) for p in segs):
        return False
    return any(_TERMS_SEGMENT.match(p) for p in segs)


def terms_link(html: str, base: str) -> str:
    for href, _text in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, re.I | re.S):
        full = urljoin(base, href)
        if is_terms_url(full):
            return full
    return ""


def is_feed(content_type: str, body: str) -> bool:
    return "xml" in (content_type or "") or body.lstrip().startswith("<?xml") or "<rss" in body[:500] or "<feed" in body[:500]


def fetch_evidence(url: str, timeout: int = 10) -> dict:
    """What `assess` needs: robots.txt, the page itself and its terms page. Each part may fail."""
    import requests
    h = {"User-Agent": UA}
    root = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    ev = {"url": url, "robots": "", "page": "", "content_type": "", "terms": "", "terms_url": "", "errors": []}
    for key, target in (("robots", root + "/robots.txt"), ("page", url)):
        try:
            r = requests.get(target, timeout=timeout, headers=h)
            if r.ok:
                ev[key] = r.text[:500_000]
                if key == "page":
                    ev["content_type"] = r.headers.get("content-type", "")
        except Exception as e:
            ev["errors"].append(f"{key}: {type(e).__name__}")
    ev["terms_url"] = terms_link(ev["page"], url) if ev["page"] else ""
    if not ev["terms_url"] and urlparse(url).path not in ("", "/"):  # a feed or deep page: the footer is on the home page
        try:
            ev["terms_url"] = terms_link(requests.get(root + "/", timeout=timeout, headers=h).text[:500_000], root + "/")
        except Exception as e:
            ev["errors"].append(f"home: {type(e).__name__}")
    if ev["terms_url"]:
        try:
            ev["terms"] = requests.get(ev["terms_url"], timeout=timeout, headers=h).text[:500_000]
        except Exception as e:
            ev["errors"].append(f"terms: {type(e).__name__}")
    return ev


def _text(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def assess(url: str, robots: str = "", page: str = "", content_type: str = "", terms: str = "",
           terms_url: str = "", errors: list | None = None) -> dict:
    """Decide the channel from the evidence, with the reason and the sentence it rests on."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    feed = is_feed(content_type, page)
    kind = "rss" if feed else "page"
    base = {"kind": kind, "terms_url": terms_url, "quote": ""}
    if any(host == d or host.endswith("." + d) for d in OPEN_DOMAINS):
        return {**base, "channel": "auto", "licence": "Open Government Licence",
                "reason": "A UK public body publishing under the Open Government Licence: free to collect and reuse."}
    if robots and not robots_allows(robots, url):
        return {**base, "channel": "upload", "licence": "robots.txt disallows automated access",
                "reason": "The site's robots.txt asks automated tools not to fetch this page."}
    words = _text(terms)
    m = _BAN.search(words) or _BAN_REV.search(words)
    if m:
        return {**base, "channel": "upload", "licence": "Terms restrict automated collection or AI use",
                "quote": m.group(0).strip()[:300],
                "reason": "The terms restrict automated collection or AI use, so colleagues upload each issue."}
    if any(d in host for d in LICENSED_DOMAINS):
        return {**base, "channel": "upload", "licence": "Licensed research (assumed restricted)",
                "reason": "Agency or data-vendor research is licensed to the reader; treated like Knight Frank, "
                          "whose terms bar AI-platform use, until a person reads these terms."}
    if not page:
        return {**base, "channel": "upload", "licence": "Could not be checked",
                "reason": "The page could not be read" + (f" ({', '.join(errors)})" if errors else "")
                          + ", so it is treated as upload-only until someone checks the terms."}
    if feed:
        return {**base, "channel": "auto", "licence": "Public feed (headlines and links only)",
                "reason": "A public RSS/Atom feed with no restriction found: the agent collects headlines and links."}
    if words:
        return {**base, "channel": "auto", "licence": "No restriction found in the terms (headlines and links only)",
                "reason": "No clause against automated collection or AI use in the terms; the agent watches the "
                          "page for new headlines and keeps only titles and links."}
    return {**base, "channel": "upload", "licence": "No terms found",
            "reason": "No terms page was found, so it is treated as upload-only until someone checks."}


def proposal(store, src: dict, verdict: dict, cadence: str = "") -> dict:
    """What following this source would mean, shown before anyone adds it for the team:
    licence, how it is read (the skill chain), how often, and what it adds to the library."""
    from .documents import PUBLISHERS
    auto = verdict["channel"] == "auto"
    cadence = cadence or src.get("cadence") or ("daily" if auto else "quarterly")
    if auto:
        chain = ["check-terms", "fetch-source", "read-article", "dedupe"]
        how = (f"The agent fetches the {'feed' if verdict['kind'] == 'rss' else 'page'} {cadence}, keeps headlines "
               "and links only, files each story and merges it with one the team already has.")
    else:
        chain = ["check-terms", "team uploads", "dedupe", "read-pdf", "map-submarkets", "check-figures"]
        how = (f"The agent never fetches it. The team is reminded to upload each {cadence} issue; the agent then "
               "reads every page and checks each figure before sharing it.")
    pub = src.get("publisher") or src.get("name", "")
    if any(p.lower() in pub.lower() for p in PUBLISHERS):
        adds = f"{pub} figures (vacancy, take-up, rents, yields, pipeline) alongside the other agencies'"
    elif verdict.get("licence") == "Open Government Licence":
        adds = "official data series and releases"
    else:
        adds = "news and deals in News and tips, merged with stories the team already has"
    held = {s.get("publisher") for s in store.sources().values()}
    if pub and pub in held:
        adds += f" (the library already has some {pub} figures)"
    return {**src, **verdict, "cadence": cadence, "chain": chain, "how": how, "adds": adds}


def follow(store, src: dict, verdict: dict, user: str, cadence: str = "") -> dict:
    """Add the source for the whole team, or return the existing entry if someone already follows it."""
    old = store.q("SELECT * FROM followed WHERE url=?", (src["url"],)) if src.get("url") else []
    if old:
        return {**old[0], "already": True}
    cadence = cadence or src.get("cadence") or ("daily" if verdict["channel"] == "auto" else "quarterly")
    store.db.execute("INSERT INTO followed (name, publisher, url, kind, channel, cadence, licence, reason, quote, "
                     "terms_url, added_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (src["name"], src.get("publisher") or src["name"], src["url"], verdict["kind"], verdict["channel"],
                      cadence, verdict["licence"], verdict["reason"], verdict.get("quote", ""),
                      verdict.get("terms_url", ""), user))
    store.db.commit()
    row = store.q("SELECT * FROM followed WHERE url=?", (src["url"],))[0]
    store.log("follow", user, f"followed {row['name']}: "
              + ("collected automatically" if row["channel"] == "auto" else "the team uploads each issue")
              + f" ({row['licence'].lower()})")
    return {**row, "already": False}


def headlines(html: str, base: str, limit: int = 15) -> list[tuple[str, str]]:
    """Titles and links on a page: what the agent keeps from a followed web page."""
    out, seen = [], set()
    for href, text in re.findall(r"<a[^>]+href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", html, re.I | re.S):
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()
        if 30 <= len(t) <= 180 and t.lower() not in seen:
            seen.add(t.lower())
            out.append((t, urljoin(base, href)))
    return out[:limit]


def due_uploads(store, today: date | None = None) -> list[dict]:
    """Upload-only sources the team follows whose next issue is probably out but nobody has uploaded."""
    today = today or date.today()
    out = []
    for f in store.q("SELECT * FROM followed WHERE channel='upload'"):
        days = CADENCE_DAYS.get(f["cadence"], 92)
        ups = [u for u in store.uploads() if u["publisher"] == f["publisher"]]
        last = max((u["uploaded_at"] or "")[:10] for u in ups) if ups else ""
        # Nothing uploaded yet: ask for the latest issue straight away; then once per cadence.
        if not last or (today - date.fromisoformat(last)).days >= days:
            out.append({"name": f["name"], "publisher": f["publisher"], "cadence": f["cadence"],
                        "last": last, "added_by": f["added_by"]})
    return out


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
