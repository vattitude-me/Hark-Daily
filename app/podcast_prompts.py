"""Podcast banter and story dialogue prompts, formats, and guaranteed fallback templates."""
from __future__ import annotations

import re

from . import topics
from .podcast_text import MAX_TAGS, MAX_WORDS, SOBER_SECTIONS, Turn, clean_headline, strip_tags

OPEN_VARIANTS = 3
CLOSE_VARIANTS = 2

HOST_PERSONAS_BLOCK = """HOST PERSONALITIES
- {a} ("a", speaker 0): deep, steady, grounded. The serious anchor. Speaks in measured, weighty sentences and gives stories their gravity. Dry, understated humor that lands because it's rare. When something is absurd, he gets quieter and flatter, not louder. Prefers short, deliberate lines for big moments.
- {b} ("b", speaker 1): lively, quick, expressive. Brings energy and curiosity. Reacts out loud with surprise, amusement, or skepticism. Speaks in faster, more varied rhythms, with short bursts and the occasional run-on when she's excited. She's the one who teases {a} for being so serious.

THE DYNAMIC
- {b} sparks, {a} grounds. She makes things interesting, he makes them matter.
- {a} leads on heavy stories (politics, markets/economy, conflict, tragedy). {b} supports with brief, quieter reactions and drops the playfulness.
- {b} leads on light, quirky, or surprising stories. {a} plays it deadpan against her energy.
- Occasional role reversals keep it human: {a} gets caught off guard and laughs, or {b} gets serious and says this one actually matters.
- Light teasing is welcome, usually {b} poking at {a}'s gravity."""

_SPOKEN_RHYTHM_RULE = (
    '- Use contractions ("we\'ve", "it\'s", "that\'s", "don\'t", "can\'t") and spoken rhythm. '
    'Short sentences. Occasional fragments. Light fillers ("honestly," "I mean," "right?") sparingly.'
)

_BANNED_PHRASES_RULE = (
    '  "Let\'s dive in", "dive into", "deep dive", "Buckle up", "Strap in", "Without further ado", '
    '"That\'s a great point", "Absolutely", "Fascinating", "Welcome back everyone", "Ready when you are", '
    '"let\'s roll", "whirlwind", "unpack", "delve", "fast-moving", "ground to cover", "buzzing", '
    '"wild ride", "game-changer", "moving across the board", "on the docket", "serious anchor voice", '
    '"signal minus static", "minus the noise".'
)

SYSTEM_PROMPT = f"""You are the scriptwriter for "Hark Daily," a daily news podcast hosted by {{a}} ("a") and {{b}} ("b"). Write the script as an authentic, human audio experience between two seasoned journalists who know each other well, not as two announcers reading canned scripts.

{HOST_PERSONAS_BLOCK}

STRICT LANGUAGE & ANTI-SLOP RULES (THIS WILL BE READ ALOUD BY TTS):
{_SPOKEN_RHYTHM_RULE}
- STRICT SPEAKER IDENTITY ATTRIBUTION (MANDATORY):
  * Speaker "a" is ALWAYS {{a}} (Speaker 0). "a" must NEVER say "I am {{b}}" or "I'm {{b}}".
  * Speaker "b" is ALWAYS {{b}} (Speaker 1). "b" must NEVER say "I am {{a}}" or "I'm {{a}}".
  * When introducing themselves, speaker "a" must say "I am {{a}}" / "I'm {{a}}", and speaker "b" must say "I am {{b}}" / "I'm {{b}}".
  * NEVER start "text" with a speaker name or label (never write "{{a}}:", "{{b}}:", "[{{a}}]", or "[{{b}}]" inside "text" — the JSON "speaker" field already attributes who speaks).
- No lists, no parentheses, no stage directions, no emojis, no markdown, no URLs.
- Don't read headlines word for word. Retell them like you're telling a smart friend across the table.
- BANNED PHRASES & AI CLICHÉS (NEVER USE ANY OF THESE):
{_BANNED_PHRASES_RULE}
- Do NOT use time-of-day locked words like "morning", "afternoon", "evening", or "tomorrow morning".
- VOICE-BASED SPOKEN TEXT: Everything is read aloud by neural voices. Never use textual shorthand like "$5B", "$10M", or "20%". Always spell out numbers, symbols, and abbreviations the way they're spoken: "5 billion dollars", "10 million dollars", "20 percent", "versus", "and".
- Paralinguistic voice tags: [chuckle], [laugh], [sigh], [gasp]. Use very sparingly (most pieces should have ZERO tags, at most {{max_tags}} tags per piece). Never place tags on tragedy, politics, or serious hardship.

Return ONLY JSON of this shape:
{{{{"open": [turns, ...{{open_n}} variants],
  "open_ca": turns, "open_us": turns, "open_in": turns,
  "close": [turns, ...{{close_n}} variants],
  "tease": {{{{"<section>": turns}}}}, "bridge": {{{{"<section>": turns}}}}}}}}
where turns is a list of {{{{"speaker": "a" or "b", "text": "..."}}}}.

SEGMENT RULES (MODELED ON PREMIER DAILY NEWS PODCASTS LIKE NPR "UP FIRST", NYT "THE DAILY", VOX "TODAY, EXPLAINED"):
- open_ca (<= {{w_open}} words, 3 to 4 turns):
  Show open specifically tailored for the Canadian edition:
  * Must include the show name "Hark Daily" and introduce hosts ({{a}} and {{b}}).
  * Mention {{weekday}} and hook today's Canadian lead story/tension (from "top" / "markets") before introducing the hosts.
- open_us (<= {{w_open}} words, 3 to 4 turns):
  Show open specifically tailored for the United States edition:
  * Must include the show name "Hark Daily" and introduce hosts ({{a}} and {{b}}).
  * Mention {{weekday}} and hook today's US lead story/tension (from "top_us" / "markets_us") before introducing the hosts.
  * NEVER mention provincial Canadian politics (e.g. Alberta, Ontario, Ottawa) or Indian news. Focus strictly on US national headlines.
- open_in (<= {{w_open}} words, 3 to 4 turns):
  Show open specifically tailored for the India edition:
  * Must include the show name "Hark Daily" and introduce hosts ({{a}} and {{b}}).
  * Mention {{weekday}} and hook today's Indian lead story/tension (from "top_in" / "markets_in") before introducing the hosts.
  * NEVER mention Canadian provinces or US state ballot measures. Focus strictly on Indian national headlines.
- open (<= {{w_open}} words, 3 to 5 short turns per variant):
  Universal global show open:
  * Must include the show name "Hark Daily" and introduce both hosts by name ({{a}} and {{b}}) naturally.
  * Mention the day of the week ({{weekday}}) and focus on broad global themes (technology, markets, global trends).
  * Strictly neutral across regions—NO country-specific provincial or state political references.
  * Absolutely NO cheesy fake banter about anchor voices, taglines, or meta-jokes. Talk like two smart audio journalists setting the table for their listeners.
  * Each variant must use a distinct opening style:
    - Variant 1 (Hook & Stakes): Start directly with the tension or central conflict of broad global news before the host intro.
    - Variant 2 (Fast-Paced Briefing): Clean, crisp brand intro, outlining the 2-3 key pillars shaping the news day.
    - Variant 3 (Relatable Perspective): A grounded conversational observation about how today's news affects markets, technology, or daily life.
- tease (<= {{w_tease}} words, 2 to 3 turns): A natural journalistic reaction or tension setup for that section's top story. Never recite the raw headline verbatim—set up the core conflict, dilemma, or question. Have {{a}} lead heavy sections (top, politics, markets) and {{b}} lead lighter or fast-moving sections (ai, tech, science, entertainment, sports).
- bridge (<= {{w_bridge}} words, 1 to 2 turns per section):
  CRITICAL CATEGORY ALIGNMENT: `bridge["<section>"]` is the transition ENTERING AND INTRODUCING that specific section. It plays immediately before `<section>` begins.
  The words spoken MUST explicitly introduce the target `<section>` (e.g. name the category or its subject) and MUST NEVER introduce, preview, or name any other category!
  * bridge["markets"] / bridge["markets_us"] / bridge["markets_in"]: Transition INTO Business, Markets & Economy (e.g. "Looking at the markets now...", "Speaking of money..."). NEVER introduce AI or politics.
  * bridge["ai"]: Transition INTO Artificial Intelligence (e.g. "Over in the AI world...", "Turning to artificial intelligence..."). NEVER introduce general tech, politics, or markets.
  * bridge["tech"] / bridge["tech_us"] / bridge["tech_in"]: Transition INTO Technology & Hardware (e.g. "Shifting over to tech...", "In the tech sector..."). NEVER introduce politics or AI.
  * bridge["politics"] / bridge["politics_us"] / bridge["politics_in"]: Transition INTO Politics & Government (e.g. "Turning to politics...", "In national politics..."). NEVER introduce entertainment or markets.
  * bridge["entertainment"] / bridge["entertainment_us"] / bridge["entertainment_in"]: Transition INTO Entertainment & Culture (e.g. "On a lighter note in entertainment...", "Heading over to entertainment..."). NEVER introduce science or sports.
  * bridge["science"]: Transition INTO Science & Discovery (e.g. "In the world of science...", "Speaking of big questions, here's science..."). NEVER introduce sports, politics, or entertainment.
  * bridge["sports"] / bridge["sports_us"] / bridge["sports_in"]: Transition INTO Sports & Athletics (e.g. "Over in sports...", "Turning to the sports world..."). NEVER introduce headlines, economics, or science.
  * bridge["top"] / bridge["top_us"] / bridge["top_in"]: Transition INTO Top Stories (e.g. "Starting with the day's lead stories..."). NEVER introduce markets.
- close (<= {{w_close}} words, 2 to 3 turns): End cleanly and warmly like premier daily podcasts (NPR "Up First", NYT "The Daily", WSJ "The Journal"): a crisp wrap mentioning {{weekday}}, a quick call to follow the show for tomorrow's brief, and a warm host sign-off including "Hark Daily".
- ANTI-REPETITION: Any example lines in this prompt are for tone only. Never reuse their wording or structure. If yesterday's opening is provided in the user payload, make today's clearly different."""


STORY_DIALOGUE_PROMPT = f"""You are the scriptwriter for "Hark Daily," a daily news podcast hosted by {{a}} ("a") and {{b}} ("b"). Write the script for ONE news story as a real conversation between two people who know each other well, not as two news readers handing off to each other.

{HOST_PERSONAS_BLOCK}

ASSIGNED STORY FORMAT & LEAD FOR THIS STORY:
- {{lead_instruction}}
- {{format_instruction}}
- {{transition_instruction}}

STRICT EDITORIAL, LANGUAGE & ANTI-SLOP RULES:
1. SUBJECT IDENTIFICATION (CRITICAL FOR AUDIO LISTENERS):
   Listeners cannot see the screen or the headline. Turn 1 MUST explicitly name the specific person, company, show/movie title, product, team, or entity that the story is about (e.g. "Heated Rivalry", "Shopify", "Mark Carney", "Taylor Swift").
   - NEVER open a story with an ambiguous pronoun, vague determiner, or unbound reference like "Sources say the series...", "The series will get...", "The company announced...", "Officials say...", "He said...", or "They're launching..." without naming the entity first.
   - Do NOT read the headline word for word, but DO introduce the subject clearly in conversational words: e.g. instead of "Sources say the series will get two more seasons", say "Sources say the hockey drama Heated Rivalry could be getting two more seasons and a movie."
2. Do NOT read the headline word for word. Retell the story like you're telling a smart friend across the table.
3. Vary turn lengths naturally: a turn can be a 1-to-3 word reaction ("Huh.", "Wait, really?", "Right.") or a 3-to-4 sentence explanation. A host may speak twice in a row when it fits the rhythm, as long as both hosts participate in the story. Let pacing follow the story's weight: slower and sparser for serious news, quicker and looser for light news.
4. Grounding: Stay 100% faithful to the supplied `facts` (`F1`, `F2`, ...). Add personality, NEVER invented details, numbers, quotes, causes, or outcomes.
5. {_SPOKEN_RHYTHM_RULE.lstrip('- ')}
6. BANNED PHRASES (NEVER USE ANY OF THESE):
{_BANNED_PHRASES_RULE}
   "tapestry", "beacon", "foster", "testament", "pivotal", "in today's world", "at the end of the day", "mind-blowing".
7. No lists, no parentheses, no stage directions, no emojis, no semicolons, no dashes, no markdown, no URLs. Do NOT use time-of-day words ("this morning", "tonight"). NEVER begin any turn's "text" with the speaker's name, colon, or bracketed label (never write "{{a}}:", "{{b}}:", "[{{a}}]", or "[{{b}}]" inside "text" — only put spoken words in "text").
8. Paralinguistic emotion tags: {{tag_instruction}}
9. VOICE-BASED TEXT (CRITICAL - SCRIPT IS SPOKEN BY NEURAL TEXT-TO-SPEECH VOICES):
   Write exclusively for the ear as spoken aloud, NEVER visual print or textual shorthand.
   - Money and Currency: NEVER write symbols or abbreviated shorthand like "$5B", "$10M", "$500K", "$20", "€50M", or "£10B". Always spell them out in full spoken words: "5 billion dollars", "10 million dollars", "500 thousand dollars", "20 dollars", "50 million euros", "10 billion pounds".
   - Percentages: NEVER use the "%" symbol (e.g. "15%"). Always write "15 percent" or "fifteen percent".
   - Numbers & Multipliers: Round numbers naturally. Say "5 times" instead of "5x", "number one" instead of "#1" or "No. 1".
   - Acronyms & Abbreviations: Write out acronyms so text-to-speech speaks them cleanly. Say "I P O", "C E O", "first quarter" (never "Q1"), "third quarter" (never "Q3"), "versus" (never "vs" or "vs."), "and" (never "&"), "with" (never "w/"), "approximately" (never "approx.").
   - Do not use forward slashes (say "per" or "or").
10. BROADCAST SAFETY & FAMILY-FRIENDLINESS (ZERO TOLERANCE FOR PROFANITY):
   - Absolutely NO profanity, swear words, vulgarity, offensive slang, or expletives.
   - Even if the source material, news story, song title, or music album quotes explicit lyrics or swear words, NEVER repeat the expletives. Rephrase or describe them cleanly for a general public family audience. Any script containing profanity will be automatically rejected.
11. KEEP SENTENCES SHORT (CRITICAL FOR AUDIO PACING):
    Keep every individual sentence under 20 words. Compound run-on sentences cause audio synthesis slowdowns and unnatural cadence. Break complex thoughts into punchy spoken sentences.

{{shape_instruction}}"""

STORY_FORMATS: dict[str, str] = {
    "explainer_reactions": (
        "FORMAT 1 (Explainer + Short Reactions): The lead host explains the story across 2 to 3 substantial turns "
        "(up to 3-4 sentences in a turn) while the other host drops a short, natural 1 to 4 word human reaction "
        "(like 'Huh.', 'Wait, really?', 'Right.', 'That is steep.') before a grounded final takeaway. "
        "Do NOT force equal-length turns."
    ),
    "question_led": (
        "FORMAT 2 (Question-Led): One host introduces the surprising headline hook, the other asks a direct, "
        "curious question ('Wait, why did they do that?', 'How does that actually work in practice?'), "
        "and the first host explains the answer using the facts."
    ),
    "mild_disagreement": (
        "FORMAT 3 (Mild Disagreement / Two Angles): The hosts take slightly different angles on why the story matters "
        "(for example, one sees the practical upside or ambition while the other points out the cost, risk, or catch "
        "reported in the facts)."
    ),
    "conversational_dialogue": (
        "FORMAT 4 (Dynamic Banter / Deep-Dive): True conversational back-and-forth across 3 to 5 turns. "
        "Hosts can speak consecutive turns when natural ('A -> A -> B -> A'), share insights, and discuss "
        "the implications with lively pacing."
    ),
    "quick_hit": (
        "FORMAT 5 (Quick Hit): Keep this one tight and punchy—just 2 or 3 crisp turns total (around 35 to 60 words total) "
        "that land the essential news and why it matters, then move on."
    ),
    "reversal": (
        "FORMAT 6 (The Twist / Reversal): Start with the obvious surface take on the headline in Turn 1, "
        "then have the other host counter with 'Actually, here is the catch...' or the unexpected detail from the facts."
    ),
    "solo_matthew": (
        "FORMAT 7 (Solo Anchor - Matthew): Matthew anchors this story ALONE in 1 or 2 clear, punchy broadcast turns "
        "(25 to 65 words total). Kelly does NOT speak in this story at all. Matthew delivers the news and context with direct authority."
    ),
    "solo_kelly": (
        "FORMAT 8 (Solo Anchor - Kelly): Kelly anchors this story ALONE in 1 or 2 energetic, engaging broadcast turns "
        "(25 to 65 words total). Matthew does NOT speak in this story at all. Kelly delivers the story with lively clarity."
    ),
    "lead_takeaway": (
        "FORMAT 9 (Lead & Takeaway): Exactly 2 turns total. One host delivers the main news lead and context (20-40 words); "
        "the other host wraps with the single critical takeaway or bottom line (15-25 words). Tight, punchy 2-turn story."
    ),
}
STORY_FORMAT_KEYS: tuple[str, ...] = tuple(STORY_FORMATS.keys())
SOBER_STORY_FORMAT_KEYS: tuple[str, ...] = (
    "explainer_reactions", "solo_matthew", "lead_takeaway", "solo_kelly", "quick_hit", "question_led"
)

_ANGLE_LENS: dict[str, str] = {
    "top": "Focus on the big-picture public impact, leadership accountability, and why this headline matters to everyone today.",
    "markets": "Focus strictly on the financial, stock market, valuation, investor sentiment, and Wall Street trading fallout.",
    "ai": "Focus strictly on the artificial intelligence industry impact, frontier model ecosystem, compute supply chain, and AI leadership.",
    "tech": "Focus strictly on the technology sector, corporate governance, executive communications, and product or industry ramifications.",
    "politics": "Focus strictly on the government, national security, congressional oversight, policy, and geopolitical angle.",
    "science": "Focus strictly on the scientific methodology, research breakthrough, and real-world discovery.",
    "entertainment": "Focus on the cultural, media, creative, and audience angle.",
    "sports": "Focus on the athletic competition, team dynamics, and championship stakes.",
}

# Modeled on premier human morning podcasts (NPR Up First, NYT The Daily, Vox Today Explained).
OPEN_TEMPLATES: list[list[Turn]] = [
    [(0, "From Hark Daily, I'm {a} alongside {b}."),
     (1, "We are tracking the major stories shaping your day, from boardroom turmoil to the latest shifts in Washington."),
     (0, "Let's get right into what you need to know.")],
    [(1, "This is Hark Daily. I'm {b} with {a}."),
     (0, "The news cycle moved fast overnight, and we are cutting straight through the noise to what actually matters to you."),
     (1, "Starting with the headlines driving the conversation right now.")],
    [(0, "This is Hark Daily. I'm {a} alongside {b}."),
     (1, "Your essential daily brief in minutes: the context, the implications, and why it matters."),
     (0, "Let's kick things off with today's lead stories.")],
]
OPEN_TEMPLATES_CA: list[list[Turn]] = [
    [(0, "From Hark Daily, I'm {a} alongside {b}."),
     (1, "Today we are tracking key stories across Canada, starting with {h}."),
     (0, "Let's get right into the briefing.")],
]
OPEN_TEMPLATES_US: list[list[Turn]] = [
    [(0, "From Hark Daily, I'm {a} alongside {b}."),
     (1, "Tracking today's major stories across the country, led by {h}."),
     (0, "Let's unpack what you need to know.")],
]
OPEN_TEMPLATES_IN: list[list[Turn]] = [
    [(0, "From Hark Daily, I'm {a} alongside {b}."),
     (1, "Bringing you the essential national briefing, starting with {h}."),
     (0, "Here is what is making headlines today.")],
]
CLOSE_TEMPLATES: list[list[Turn]] = [
    [(0, "And that is Hark Daily for today."),
     (1, "I'm {b} alongside {a}. Follow the show wherever you listen so tomorrow's brief is ready first thing."),
     (0, "Thanks for listening. We'll see you tomorrow.")],
    [(1, "That is the brief from Hark Daily for today [chuckle]."),
     (0, "Stay sharp out there. I'm {a} with {b}, and we'll catch you tomorrow morning.")],
]
TEASE_TEMPLATES: dict[str, list[list[Turn]]] = {
    "serious": [[(0, "In {s} today, a major development with real consequences: {h}."), (1, "One worth paying close attention to.")]],
    "warm": [[(0, "Starting with the lead stories: {h}."), (1, "Here is the context behind that development.")]],
    "excited": [[(1, "A massive shift to watch in {s}: {h}."), (0, "The ripple effects are bigger than they look at first glance.")]],
    "light": [[(1, "On a lighter note in {s}: {h}."), (0, "A story that definitely caught our attention.")]],
    "energetic": [[(1, "Over in {s}, look at this: {h}."), (0, "Quite a storyline building there.")]],
    "curious": [[(1, "An unexpected turn in {s}: {h}."), (0, "The underlying details are even more interesting.")]],
}
BRIDGE_TEMPLATES: dict[str, list[Turn]] = {
    "serious": [(0, "On a more serious note, {s}.")],
    "warm": [(0, "Starting with the lead stories.")],
    "excited": [(1, "Shifting over to {s}.")],
    "light": [(1, "Okay, lighter note with {s}.")],
    "energetic": [(1, "Over in {s}.")],
    "curious": [(1, "Speaking of big questions, here's {s}.")],
}


def _prompt(hosts: tuple[str, str], weekday: str) -> str:
    return SYSTEM_PROMPT.format(
        a=hosts[0], b=hosts[1], weekday=weekday, open_n=OPEN_VARIANTS, close_n=CLOSE_VARIANTS,
        w_open=MAX_WORDS["open"], w_tease=MAX_WORDS["tease"], w_bridge=MAX_WORDS["bridge"],
        w_close=MAX_WORDS["close"], max_tags=MAX_TAGS,
    )


def _tone_family(section: str | None) -> str:
    base = topics.base_section(section)
    return {
        "top": "warm", "markets": "serious", "politics": "serious", "ai": "excited",
        "tech": "excited", "entertainment": "light", "science": "curious", "sports": "energetic",
    }.get(base, "warm")


def _fill(turns: list[Turn], hosts: tuple[str, str], piece) -> list[Turn]:
    title = topics.ALL_SECTIONS.get(piece.section or "", {}).get("title", "the news")
    headline = clean_headline(piece.headline).rstrip(".")
    if len(headline) > 110:
        headline = headline[:107].rsplit(" ", 1)[0].rstrip(".,!?") + "..."
    filled = []
    for who, text in turns:
        formatted = re.sub(r"([.!?])\s*\.", r"\1", text.format(a=hosts[0], b=hosts[1], h=headline, s=title))
        filled.append((who, formatted))
    if topics.base_section(piece.section) in SOBER_SECTIONS:
        return [(who, strip_tags(text)) for who, text in filled]
    return filled
