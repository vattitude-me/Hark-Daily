"""Briefing sections and the built-in source catalog (app/catalog/sources.json, shared with the Android app)."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote, quote_plus

_CATALOG = json.loads((Path(__file__).parent / "catalog" / "sources.json").read_text(encoding="utf-8"))

# "topic" is what the host says when a section starts ("First, the top stories from across Canada.").
# The "First / Next / And finally" comes from the section's position in each briefing.
SECTIONS = {s["key"]: {k: v for k, v in s.items() if k != "key"} for s in _CATALOG["sections"]}

DEFAULT_STORIES = {k: s["stories"] for k, s in SECTIONS.items()}

BUILTIN_SOURCES = _CATALOG["sources"]


def local_sources(city: str) -> list[dict]:
    """News for the user's city: Google News for anywhere, plus local outlets for the cities we know."""
    city = (city or "").split(",")[0].strip()
    if not city:
        return []
    local = _CATALOG["local"]
    key = city.lower()
    key = local["aliases"].get(key, key)
    picks = [*local["cities"].get(key, []), *local["everywhere"]]
    return [{"name": s["name"].replace("{city}", city), "url": s["url"].replace("{city}", quote(city)),
             "section": "local", "weight": s.get("weight", 1.0)} for s in picks]


def follow_url(query: str) -> str:
    """A news search feed for a name or topic."""
    return _CATALOG["follow"]["url"].replace("{query}", quote_plus(query.strip()))


def is_follow_url(url: str) -> bool:
    return url.startswith(_CATALOG["follow"]["url"].split("?")[0])
