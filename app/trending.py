"""Non-prod trending topic curation and dual-host quirky banter generator.

Picks interesting, quirky, non-vulgar cultural and workplace buzzwords/trends for
morning and evening editions, writes natural dialogue between Matthew and Kelly
reacting to the absurdity of the term, and smoothly pivots into the serious news.

Strict Guardrails:
1. ZERO social media brand names (no TikTok, Reddit, Twitter/X, Instagram, Threads, YouTube).
   Neutral phrasing only: "online", "circulating this week", "the internet", "people are debating".
2. Non-vulgar, family-safe, relatable humor.
3. Matthew & Kelly dynamic: Matthew is grounded, dryly bemused; Kelly is expressive, incredulous,
   quick-witted. Includes paralinguistic voice tags ([laugh], [chuckle], [sigh]).
4. Word cap: 40-55 words total, 4-6 fast-paced turns.
5. Smooth bridge: Never leaves the banter hanging; seamlessly pivots into the real headlines.
6. Non-prod isolation: Runs standalone; does NOT touch live Supabase tables or prod buckets.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Literal

log = logging.getLogger(__name__)

BANNED_SOCIAL_PLATFORMS = frozenset({
    "tiktok", "tik-tok", "twitter", "x.com", "reddit", "instagram", "insta",
    "threads", "facebook", "meta", "youtube", "bluesky", "snapchat", "linkedin",
    "sub-reddit", "subreddit", "tweet", "tweeting", "tiktokers", "redditors",
})

BANNED_VULGARITY = frozenset({
    "nsfw", "sexy", "horny", "vulgar", "swear", "bitch", "damn", "crap",
    "hell", "ass", "dick", "piss", "boob", "drugs", "weed", "stoned",
})

RE_SOCIAL_CLEAN = [
    (re.compile(r"\b(on|from|across)\s+(tiktok|reddit|twitter|x|instagram|threads|facebook)\b", re.I), "online"),
    (re.compile(r"\b(tiktokers|redditors|tweeters)\b", re.I), "people online"),
    (re.compile(r"\b(tiktok|reddit|twitter|instagram)\s+(trend|debate|video|post)\b", re.I), r"\2 online"),
    (re.compile(r"\b(a\s+tweet|a\s+sub-?reddit)\b", re.I), "a discussion online"),
    (re.compile(r"\bviral\s+on\s+[a-z0-9_-]+\b", re.I), "viral online"),
]


@dataclass(frozen=True)
class TrendingTopic:
    topic_id: str
    term: str
    headline: str
    summary: str
    slot: Literal["morning", "evening", "any"]
    category: Literal["workplace", "lifestyle", "habits", "culture"]
    tags: tuple[str, ...] = ()


# Curated catalog of quirky, relatable, non-vulgar trends
CURATED_TRENDS: tuple[TrendingTopic, ...] = (
    # --- MORNING SLOTS: Workplace, morning routines, office culture quirks ---
    TrendingTopic(
        topic_id="coffee-badging",
        term="Coffee Badging",
        headline="Employees Perfecting 'Coffee Badging' at the Office",
        summary="Workers showing up to the office just long enough to grab a coffee, swipe their badge so attendance is logged, and heading home to work remotely.",
        slot="morning",
        category="workplace",
        tags=("office", "remote-work", "humor"),
    ),
    TrendingTopic(
        topic_id="desk-bombing",
        term="Desk Bombing",
        headline="The Sudden Panic Over 'Desk Bombing' in Open Offices",
        summary="Walking right up to a colleague's desk in person to ask a question without sending a chat message or email first, triggering shock among younger workers.",
        slot="morning",
        category="workplace",
        tags=("open-office", "etiquette", "communication"),
    ),
    TrendingTopic(
        topic_id="silent-walking",
        term="Silent Walking",
        headline="People Discovering 'Silent Walking' as a Revolutionary Routine",
        summary="Walking outside without headphones, music, podcasts, or a phone call — what previous generations simply called going for a walk.",
        slot="morning",
        category="habits",
        tags=("wellness", "outdoors", "minimalism"),
    ),
    TrendingTopic(
        topic_id="mouse-jiggler-craze",
        term="Mouse Jiggling",
        headline="The Escalating Arms Race Over Mechanical Mouse Jigglers",
        summary="Remote workers buying motorized gadgets to move their computer mouse every thirty seconds so their work status stays bright green.",
        slot="morning",
        category="workplace",
        tags=("tech", "remote-work", "humor"),
    ),
    TrendingTopic(
        topic_id="fauxductivity",
        term="Fauxductivity",
        headline="The Rise of 'Fauxductivity' and Calendar Blocking",
        summary="Spending an entire morning color-coding to-do lists and scheduling fake 'focus blocks' instead of actually doing the work.",
        slot="morning",
        category="workplace",
        tags=("productivity", "corporate", "satire"),
    ),

    # --- EVENING SLOTS: Unwind, evening habits, lifestyle absurdities ---
    TrendingTopic(
        topic_id="revenge-bedtime",
        term="Revenge Bedtime Procrastination",
        headline="Why Everyone Is Trapped in 'Revenge Bedtime Procrastination'",
        summary="Refusing to go to sleep before midnight to scroll or assemble jigsaw puzzles because the workday stole all daytime freedom.",
        slot="evening",
        category="lifestyle",
        tags=("sleep", "habits", "wellness"),
    ),
    TrendingTopic(
        topic_id="underconsumption-core",
        term="Underconsumption Core",
        headline="The Radical New Concept of Using Things Until They Break",
        summary="People passionately celebrating wearing the same jacket for six years and owning only one water bottle instead of buying twenty.",
        slot="evening",
        category="culture",
        tags=("shopping", "sustainability", "money"),
    ),
    TrendingTopic(
        topic_id="micro-cations",
        term="Micro-cations",
        headline="Packing a Whole Vacation into a Thirty-Six Hour 'Micro-cation'",
        summary="Squeezing flights, sightseeing, and dining into a sprint weekend getaway so no vacation days are sacrificed.",
        slot="evening",
        category="lifestyle",
        tags=("travel", "weekends", "rest"),
    ),
    TrendingTopic(
        topic_id="hurkle-durkling",
        term="Hurkle-Durkling",
        headline="The Resurgence of the Two-Hundred-Year-Old Scots Term 'Hurkle-Durkling'",
        summary="Reviving an 1800s Scottish expression that literally means lounging comfortably in bed long after it is time to get up.",
        slot="evening",
        category="culture",
        tags=("language", "sleep", "history"),
    ),
    TrendingTopic(
        topic_id="dumbphone-revolution",
        term="Dumbphone Renaissance",
        headline="Ditching Smartphones for Old-School Flip Phones",
        summary="People abandoning five-hundred-dollar smartphones for twenty-dollar flip phones that can only call, text, and play Snake.",
        slot="evening",
        category="habits",
        tags=("digital-detox", "tech", "nostalgia"),
    ),
)


# Master fallback dialogue templates for Matthew ("a") and Kelly ("b")
CURATED_DIALOGUES: dict[str, list[tuple[int, str]]] = {
    "coffee-badging": [
        (0, "Kelly, have you heard of 'coffee badging' yet?"),
        (1, "Wait... is that an actual phrase? What does that even mean?"),
        (0, "Showing up to the office, tapping your badge, grabbing a free latte, and quietly heading straight back home. [chuckle]"),
        (1, "[laugh] That is completely unhinged! We really have a corporate buzzword for getting a coffee?"),
        (0, "Apparently we do. But before HR investigates us... let's get into the real news."),
        (1, "Good idea. First up, world headlines."),
    ],
    "desk-bombing": [
        (1, "Matthew, someone told me I committed 'desk bombing' yesterday."),
        (0, "[chuckle] Desk bombing? That sounds like a workplace crime. What did you do?"),
        (1, "I literally just walked over to someone's desk to ask a quick question without sending a message first!"),
        (0, "[laugh] The horror! Talking to a human in person. People have lost their minds."),
        (1, "Clearly. Alright, before anyone desk-bombs us, let's turn to the actual news."),
        (0, "Fair call. Leading off with the top stories today."),
    ],
    "silent-walking": [
        (0, "So there is a new wellness routine online called 'silent walking'."),
        (1, "What makes it 'silent'?"),
        (0, "You walk outside with no headphones, no podcasts, and no music. Just your thoughts."),
        (1, "[sigh] That is literally just walking! Why do we need to rebrand putting one foot in front of the other?"),
        (0, "[chuckle] Because everyone needs a buzzword. Let's check the headlines."),
        (1, "Please. Here are the top stories."),
    ],
    "mouse-jiggler-craze": [
        (1, "Did you see that mechanical mouse jigglers are flying off store shelves?"),
        (0, "Oh yes. Motorized turntables so your computer cursor moves while you make breakfast."),
        (1, "The lengths people go to keep a little chat icon green! [laugh] It is pure comedy."),
        (0, "[chuckle] Modern problems require motorized solutions, apparently. Anyway, before our own status turns yellow... here is the news."),
        (1, "Right to business. Starting with world news."),
    ],
    "fauxductivity": [
        (0, "I learned a new word today, Kelly: 'fauxductivity'."),
        (1, "Let me guess... spending two hours color-coding your inbox instead of working?"),
        (0, "Spot on. Full calendar blocks for 'deep strategic contemplation' while drinking espresso. [chuckle]"),
        (1, "[laugh] I feel personally targeted by that! Alright, real work starts now. What is on the wire?"),
        (0, "Plenty. Here are the day's major headlines."),
    ],
    "revenge-bedtime": [
        (1, "Matthew, I was up until two in the morning last night in full 'revenge bedtime' mode."),
        (0, "[chuckle] Revenge against whom? Your own alarm clock?"),
        (1, "Against the entire workday! If my schedule controls my daylight, midnight belongs to me and my jigsaw puzzle."),
        (0, "[sigh] That is painfully relatable. Though your morning self definitely loses that war."),
        (1, "[laugh] Every single time. Let's wrap up our day with the actual headlines."),
        (0, "Sounds good. Here is what happened today."),
    ],
    "underconsumption-core": [
        (0, "Have you seen people raving about 'underconsumption core' this week?"),
        (1, "Wait, what happened to just buying things you need? Is that a trend now?"),
        (0, "Bragging rights for wearing the same winter coat for seven years and owning two coffee mugs. [chuckle]"),
        (1, "[laugh] So living like our grandparents is now a revolutionary lifestyle movement? Incredible."),
        (0, "It really is. Well, before we over-consume the banter... here are the evening headlines."),
        (1, "Let's get into it. First up tonight..."),
    ],
    "micro-cations": [
        (1, "Matthew, apparently everyone is trading two-week holidays for thirty-six-hour 'micro-cations'."),
        (0, "Thirty-six hours? That barely covers packing, finding parking, and airport security!"),
        (1, "[laugh] Exactly! Fly in Friday night, eat one pastry, run past a museum, and fly right back."),
        (0, "[sigh] Sounds more exhausting than the work week. Let's take a proper breather with tonight's news."),
        (1, "Much better idea. Here are the top stories."),
    ],
    "hurkle-durkling": [
        (0, "I found my new favorite phrase: 'hurkle-durkling'."),
        (1, "Hurkle-durkling? [chuckle] Did you just sneeze or make up a word?"),
        (0, "It is an old Scottish term from the 1800s. It means staying in bed long after you should have gotten up."),
        (1, "[laugh] That is fantastic! Two centuries of wisdom defending lazy mornings. I love it."),
        (0, "Hard to argue with history. But duty calls... here are the day's key stories."),
        (1, "Right into the news. Top headlines first."),
    ],
    "dumbphone-revolution": [
        (1, "Matthew, people are ditching their smartphones for twenty-dollar flip phones."),
        (0, "Back to T9 texting and playing Snake on a black-and-green screen?"),
        (1, "Exactly! No notifications, no endless feeds, just a battery that lasts five days. [chuckle]"),
        (0, "[sigh] Honestly? That sounds kind of peaceful. But while we still have digital signals... let's check the news."),
        (1, "Fair enough. Here is what is happening in the world."),
    ],
}


def sanitize_text(text: str) -> str:
    """Removes or neutralizes social media references from banter text."""
    cleaned = text
    for pattern, replacement in RE_SOCIAL_CLEAN:
        cleaned = pattern.sub(replacement, cleaned)
    # Catch any remaining bare mentions
    for word in BANNED_SOCIAL_PLATFORMS:
        cleaned = re.sub(rf"\b{word}\b", "the internet", cleaned, flags=re.I)
    return cleaned


def validate_banter_turns(turns: list[tuple[int, str]]) -> tuple[bool, str]:
    """Validates that banter turns follow all strict non-prod guardrails."""
    if not turns or len(turns) < 4:
        return False, "Banter must have at least 4 turns."
    if len(turns) > 7:
        return False, "Banter must have at most 7 turns to stay within time budget."

    speakers = [who for who, _ in turns]
    if any(s not in (0, 1) for s in speakers):
        return False, "Speaker IDs must be 0 (host A) or 1 (host B)."
    # Check that hosts alternate turns
    for i in range(1, len(speakers)):
        if speakers[i] == speakers[i - 1]:
            return False, f"Hosts must alternate: duplicate speaker at turn {i}."

    total_words = 0
    for who, text in turns:
        words = text.split()
        total_words += len(words)
        lower = text.lower()
        # Check banned socials
        for banned in BANNED_SOCIAL_PLATFORMS:
            if re.search(rf"\b{banned}\b", lower):
                return False, f"Banned social media platform found in turn: '{banned}'."
        # Check vulgarity
        for vulgar in BANNED_VULGARITY:
            if re.search(rf"\b{vulgar}\b", lower):
                return False, f"Vulgar or inappropriate word found in turn: '{vulgar}'."

    if total_words > 80:
        return False, f"Total word count ({total_words}) exceeds 80 words."
    if total_words < 25:
        return False, f"Total word count ({total_words}) is too short (< 25 words)."

    # Must contain a news bridge at the end
    last_text = " ".join(t[1] for t in turns[-2:]).lower()
    bridge_words = ("news", "headlines", "stories", "first up", "leading off", "what happened", "wire")
    if not any(bw in last_text for bw in bridge_words):
        return False, "Final turns must bridge smoothly into the news."

    return True, "Valid"


def get_curated_topic(topic_id: str) -> TrendingTopic | None:
    """Finds a topic by its ID in the curated catalog."""
    for t in CURATED_TRENDS:
        if t.topic_id == topic_id:
            return t
    return None


def get_schedule_pair() -> tuple[TrendingTopic, TrendingTopic]:
    """Returns the default morning and evening curated topic pair."""
    morning = next(t for t in CURATED_TRENDS if t.slot == "morning")
    evening = next(t for t in CURATED_TRENDS if t.slot == "evening")
    return morning, evening


def build_trending_script(
    topic: TrendingTopic,
    hosts: tuple[str, str] = ("Matthew", "Kelly"),
    news_lead: str = "world headlines",
) -> list[tuple[int, str]]:
    """Builds the 2-host script for a topic, customized with host names and bridge."""
    raw_turns = CURATED_DIALOGUES.get(topic.topic_id)
    if not raw_turns:
        # Generic fallback
        raw_turns = [
            (0, f"{hosts[1]}, people online are losing their minds over this new phrase: '{topic.term}'."),
            (1, f"Wait, {hosts[0]}... '{topic.term}'? Is that seriously a thing now?"),
            (0, f"Apparently! {topic.summary} [chuckle]"),
            (1, f"[laugh] We truly need a word for everything these days. Well, before we get completely derailed..."),
            (0, f"Good call. Let's turn to the actual {news_lead}."),
            (1, "Here is what is happening today."),
        ]

    # Swap in custom host names if needed
    h_a, h_b = hosts
    formatted: list[tuple[int, str]] = []
    for who, line in raw_turns:
        text = line.replace("Kelly", h_b).replace("Matthew", h_a)
        text = sanitize_text(text)
        formatted.append((who, text))

    is_valid, msg = validate_banter_turns(formatted)
    if not is_valid:
        log.warning("Validation issue in trending script for %s: %s", topic.topic_id, msg)
    return formatted


@dataclass
class DailyReviewDeck:
    """Deck containing candidate trending topics and banter for user review."""
    morning_topic: TrendingTopic
    morning_turns: list[tuple[int, str]]
    evening_topic: TrendingTopic
    evening_turns: list[tuple[int, str]]
    hosts: tuple[str, str] = ("Matthew", "Kelly")

    def format_terminal(self) -> str:
        h_a, h_b = self.hosts
        lines = [
            "=" * 70,
            "🎙️  HARK DAILY — NON-PROD TRENDING BANTER REVIEW DECK",
            "=" * 70,
            "",
            f"Hosts: {h_a} (Host A) & {h_b} (Host B)",
            "Guardrail Policy: Zero social media brand mentions • Non-vulgar • News pivot",
            "",
            "----------------------------------------------------------------------",
            f"🌅 MORNING SCHEDULE: {self.morning_topic.term} ({self.morning_topic.category})",
            f"Headline: {self.morning_topic.headline}",
            f"Context:  {self.morning_topic.summary}",
            "----------------------------------------------------------------------",
            "Dialogue Script:",
        ]
        for who, text in self.morning_turns:
            speaker = h_a if who == 0 else h_b
            lines.append(f"  [{speaker}]: {text}")

        lines.extend([
            "",
            "----------------------------------------------------------------------",
            f"🌆 EVENING SCHEDULE: {self.evening_topic.term} ({self.evening_topic.category})",
            f"Headline: {self.evening_topic.headline}",
            f"Context:  {self.evening_topic.summary}",
            "----------------------------------------------------------------------",
            "Dialogue Script:",
        ])
        for who, text in self.evening_turns:
            speaker = h_a if who == 0 else h_b
            lines.append(f"  [{speaker}]: {text}")

        lines.extend([
            "",
            "=" * 70,
            "💡 Commands to Test:",
            "  Review & test script: python scripts/demo_trending_banter.py --review",
            "  Synthesize audio:     python scripts/demo_trending_banter.py --synthesise",
            "  Export HTML player:   python scripts/demo_trending_banter.py --html",
            "=" * 70,
        ])
        return "\n".join(lines)

    def to_dict(self) -> dict:
        h_a, h_b = self.hosts
        return {
            "morning": {
                "topic": asdict(self.morning_topic),
                "script": [{"speaker": h_a if who == 0 else h_b, "text": text} for who, text in self.morning_turns],
            },
            "evening": {
                "topic": asdict(self.evening_topic),
                "script": [{"speaker": h_a if who == 0 else h_b, "text": text} for who, text in self.evening_turns],
            },
        }
