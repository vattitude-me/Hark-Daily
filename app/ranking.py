"""Group duplicate headlines across outlets and pick the day's top stories."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .fetcher import Item

STOPWORDS = set("""
a about above after again against all am an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers him his how i
if in into is it its itself just me more most my new no nor not now of off on once only or other our out over own
said same says she should so some such than that the their them then there these they this those through to too
under until up very was we were what when where which while who whom why will with would you your amid after over
report reports news live update updates video watch says year years day week today per cent percent
""".split())

AI_TERMS = re.compile(
    r"\b(ai|a\.i\.|artificial intelligence|openai|anthropic|claude|chatgpt|gpt[- ]?\d*|gemini|llm|llms|deepmind|"
    r"machine learning|neural|nvidia|agent|agents|chatbot|copilot|mistral|cohere|llama|robot|robotics|model|models)\b",
    re.I,
)
LOW_VALUE = re.compile(
    r"(\bdeals?\b|% off|\bsale\b|\bcoupon|best .* (to buy|of 20\d\d)|\bgift guide|\bhands-on\b|\breview:|"
    r"\bpodcast\b|\bnewsletter\b|\bsponsored\b|\bhoroscope)",
    re.I,
)
MAX_AGE = timedelta(hours=48)


@dataclass
class Story:
    lead: Item
    items: list[Item] = field(default_factory=list)
    score: float = 0.0

    @property
    def id(self) -> str:
        return self.lead.id

    @property
    def sources(self) -> list[str]:
        return list(dict.fromkeys(i.source_name for i in self.items))


def tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", title.lower())
    out = set()
    for w in words:
        w = w.strip("'")
        if len(w) < 3 or w in STOPWORDS:
            continue
        if w.endswith("'s"):
            w = w[:-2]
        elif len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


class Rarity:
    """How often each headline word turns up in today's pool: rare words (names, places) mark a story."""

    def __init__(self, titles: list[set[str]]):
        self.n = len(titles)
        self.df: dict[str, int] = {}
        for toks in titles:
            for w in toks:
                self.df[w] = self.df.get(w, 0) + 1
        self.cutoff = max(3, 0.03 * self.n)

    def rare(self, word: str) -> bool:
        return self.df.get(word, 0) <= self.cutoff

    def weight(self, words: set[str]) -> float:
        return sum(math.log(max(self.n, 1) / self.df.get(w, 1)) for w in words)


def similar(a: set[str], b: set[str], rarity: Rarity | None = None) -> bool:
    if not a or not b:
        return False
    common = a & b
    shared = len(common)
    if shared / len(a | b) >= 0.4 or (shared >= 3 and shared / min(len(a), len(b)) >= 0.5):
        return True
    if not rarity or shared < 2:
        return False
    rare = sum(rarity.rare(w) for w in common)
    # "Gemini 4 Argon" inside "Google releases Gemini 4 Argon, its most powerful model yet"
    if common == min(a, b, key=len) and rare == shared:
        return True
    # Different wording around the same rare names: "Google announces Gemini 4 and says..." vs "...Gemini 4 Argon..."
    smaller = min(rarity.weight(a), rarity.weight(b))
    return shared >= 3 and rare >= 2 and smaller > 0 and rarity.weight(common) / smaller >= 0.3


def item_score(item: Item, now: datetime) -> float:
    position = 1 - item.position / max(item.feed_len, 1)
    if item.published:
        hours = max((now - item.published).total_seconds() / 3600, 0)
        recency = max(0.0, 1 - hours / 36)
    else:
        recency = 0.5
    score = item.weight * (1 + 1.2 * position + 1.0 * recency)
    if item.section == "tech":
        if AI_TERMS.search(item.title):
            score += 0.6
    if item.image:
        score += 0.1
    if item.kind == "article":
        score += 10  # a link the user added by hand always makes the cut
    return score


def cluster(items: list[Item], now: datetime, rarity: Rarity | None = None) -> list[Story]:
    scored = sorted(items, key=lambda i: item_score(i, now), reverse=True)
    stories: list[tuple[list[set[str]], Story]] = []
    seen_urls: set[str] = set()
    for item in scored:
        if item.url in seen_urls:
            continue
        seen_urls.add(item.url)
        toks = tokens(item.title)
        matches = [entry for entry in stories if any(similar(toks, t, rarity) for t in entry[0])]
        if not matches:
            stories.append(([toks], Story(lead=item, items=[item], score=item_score(item, now))))
            continue
        # An item that matches two stories shows they are one: fold the later into the first.
        (story_toks, story), *rest = matches
        story_toks.append(toks)
        story.items.append(item)
        for other_toks, other in rest:
            story_toks.extend(other_toks)
            story.items.extend(other.items)
        if rest:
            folded = {id(entry) for entry in rest}
            stories = [entry for entry in stories if id(entry) not in folded]

    result = []
    for _, story in stories:
        outlets = len(story.sources)
        story.score += 0.8 * (outlets - 1)
        # Prefer the version with an image and the richest summary as the card's lead.
        story.lead = max(story.items, key=lambda i: (bool(i.image), len(i.summary), -i.position))
        result.append(story)
    return sorted(result, key=lambda s: s.score, reverse=True)


def select_top(items: list[Item], limits: dict[str, int], now: datetime | None = None,
               heard: list[dict] | None = None) -> dict[str, list[Story]]:
    """`heard` holds story cards from the user's recent briefings; those stories aren't told again."""
    now = now or datetime.now(timezone.utc)
    fresh = [
        i for i in items
        if (i.published is None or now - i.published <= MAX_AGE) and not LOW_VALUE.search(i.title)
    ]
    rarity = Rarity([tokens(i.title) for i in fresh])
    heard_urls = {link["url"] for card in heard or [] for link in card.get("links") or [{"url": card.get("url")}]}
    heard_toks = [t for card in heard or [] if (t := tokens(card.get("original_title") or card.get("headline") or ""))]
    picked: dict[str, list[Story]] = {}
    taken: list[set[str]] = []  # the same story can surface in two sections; tell it once
    # Hand-picked sources claim their stories first, so a duplicate elsewhere is the one dropped.
    for section in sorted(limits, key=lambda k: k not in ("custom", "follow")):
        limit = limits[section]
        if limit <= 0:
            continue
        section_items = [i for i in fresh if i.section == section]
        stories = []
        for story in cluster(section_items, now, rarity):
            toks = tokens(story.lead.title)
            if any(similar(toks, t, rarity) for t in taken):
                continue
            if story.lead.kind != "article" and (
                any(i.url in heard_urls for i in story.items)
                or any(similar(tokens(i.title), t) for i in story.items for t in heard_toks)
            ):
                continue
            taken.append(toks)
            stories.append(story)
            if len(stories) == limit:
                break
        if stories:
            picked[section] = stories
    return {k: picked[k] for k in limits if k in picked}
