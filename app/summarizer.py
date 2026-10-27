"""Lightweight extractive summarizer used when no LLM is configured."""
from __future__ import annotations

import re
from collections import Counter

from .ranking import STOPWORDS

SENTENCE_SPLIT = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"”’']))\s+(?=[A-Z0-9\"“‘'])")
# A site's own furniture, not the story: sign-up prompts, follow buttons, credits, author bios.
BOILERPLATE = re.compile(
    r"(sign up|sign in|log in|subscribe|newsletter|click here|read more|continue reading|follow us|advertisement|"
    r"©|all rights reserved|this article|photo:|image:|getty images|the canadian press$|"
    r"posts from this|email digest|homepage feed|your feed|follow (this |the )?(author|topic|story|series)|"
    r"see all (stories|posts)|listen to this (article|story)|share (this|the) (article|story)|"
    r"we may earn|affiliate link|commission when you buy|cookie|reporting by|editing by|"
    r"this story (has been|was) (updated|originally)|^related:|^recommended:|^more:|^watch:|^read:)",
    re.I,
)

CONNECTORS: list[str] = [
    "Here are the details:",
    "Here's what you need to know:",
    "Taking a closer look:",
    "Here's what's happening:",
    "According to the reporting:",
    "In the details:",
    "Behind the headline:",
]


def get_connector(rank_or_idx: int = 1) -> str:
    """Return a rotating podcast conversational connector."""
    idx = max(0, rank_or_idx - 1) if rank_or_idx > 0 else 0
    return CONNECTORS[idx % len(CONNECTORS)]


def headline_overlap(headline: str, sentence: str) -> float:
    """Fraction of headline content words present in the sentence (0.0 to 1.0)."""
    h_words = {w for w in re.findall(r"[a-z']+", (headline or "").lower()) if w not in STOPWORDS and len(w) > 2}
    if not h_words:
        return 0.0
    s_words = {w for w in re.findall(r"[a-z']+", (sentence or "").lower()) if w not in STOPWORDS and len(w) > 2}
    return len(h_words & s_words) / len(h_words)


def format_script(title: str, summary: str, rank: int = 1, connector: str | None = None) -> str:
    """Format full broadcast script: [Headline]. [Podcast Banter Connector] [Body Summary]."""
    clean_title = (title or "").strip()
    if clean_title and not re.search(r"[.!?]$", clean_title):
        clean_title = f"{clean_title}."

    if not summary:
        return clean_title

    # If the summary is identical or almost identical to the title, return the title only
    if summary.strip().lower() == clean_title.rstrip(".").lower():
        return clean_title

    chosen_conn = connector if connector is not None else get_connector(rank)
    if not clean_title:
        return summary.strip()

    if chosen_conn:
        return f"{clean_title} {chosen_conn} {summary.strip()}"
    return f"{clean_title} {summary.strip()}"



LABEL_PREFIX = re.compile(
    r"^(?:[-*•]\s*)?(?:the news|why it matters|what to know|what happened|the big picture|from the source|"
    r"between the lines|catch up quick|by the numbers|what they(?:'re| are) saying|what's next|"
    r"the backstory|yes, but|details|context|zoom in|zoom out|what to watch|state of play|summary):\s*",
    re.I,
)


def clean_sentence(sent: str) -> str:
    """Clean a sentence by stripping editorial section tags (e.g. 'The news:', 'Why it matters:') and bullets."""
    s = re.sub(r"^[-*•]\s*", "", (sent or "").strip()).strip()
    s = LABEL_PREFIX.sub("", s).strip()
    s = re.sub(r"^[-*•]\s*", "", s).strip()
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def strip_headline_and_filler(title: str, script: str) -> str:
    """Extract clean body summary from broadcast script by stripping repeated headline and podcast fillers."""
    text = (script or "").strip()
    if not text:
        return ""
    clean_title = (title or "").strip().rstrip(".!?:")
    if clean_title:
        pattern = r"^" + re.escape(clean_title) + r"[.!?]?\s*"
        text = re.sub(pattern, "", text, flags=re.I).strip()

    conn_pattern = r"^(?:" + "|".join(re.escape(c) for c in CONNECTORS) + r")\s*"
    text = re.sub(conn_pattern, "", text, flags=re.I).strip()
    text = clean_sentence(text)
    return text.strip() or script.strip()


def drop_boilerplate(text: str) -> str:
    """Drops lines of site furniture from article text, so neither the summary nor the voice reads them."""
    return "\n".join(
        line for line in (text or "").splitlines()
        if not (len(line.split()) <= 40 and BOILERPLATE.search(line.strip()))
    )


def split_sentences(text: str, title: str = "") -> list[str]:
    """Split article text into sentences, skipping headings, captions, repeated titles, and editorial tags."""
    out = []
    title_key = re.sub(r"\W+", "", title.lower())
    for para in (text or "").splitlines():
        para = re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        if title_key and re.sub(r"\W+", "", para.lower()) == title_key:
            continue
        if not re.search(r"[.!?][\"”’']?$", para) and len(para.split()) < 20:
            continue  # heading, byline or caption fragment
        for s in SENTENCE_SPLIT.split(para):
            s = clean_sentence(s)
            if s:
                out.append(s)
    return out


def _clip_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    clipped = " ".join(words[:max_words]).rstrip(",;:—-")
    return clipped + "…"


def summarize(text: str, fallback: str = "", max_words: int = 60, max_sentences: int = 3, title: str = "") -> str:
    """Pick the most informative sentences (TF scoring with a news-lead bias)."""
    sentences = [
        s for s in split_sentences(text, title)
        if 6 <= len(s.split()) <= 50 and not BOILERPLATE.search(s)
    ][:40]

    # Deduplication: If the lead sentence essentially repeats the headline (>= 60% overlap),
    # drop it so the narrator moves straight to deeper context.
    if title and len(sentences) > 1 and headline_overlap(title, sentences[0]) >= 0.60:
        sentences = sentences[1:]

    if not sentences:
        return _clip_words(fallback.strip(), max_words) if fallback else ""

    freq = Counter(
        w for s in sentences for w in re.findall(r"[a-z']+", s.lower()) if w not in STOPWORDS and len(w) > 2
    )
    top = max(freq.values(), default=1)

    def score(idx: int, sent: str) -> float:
        words = [w for w in re.findall(r"[a-z']+", sent.lower()) if w not in STOPWORDS and len(w) > 2]
        if not words:
            return 0.0
        tf = sum(freq[w] / top for w in words) / len(words) ** 0.8
        lead_bonus = 1.0 if idx == 0 else 0.5 if idx < 3 else 0.0
        return tf + lead_bonus

    ranked = sorted(range(len(sentences)), key=lambda i: score(i, sentences[i]), reverse=True)
    chosen: list[int] = []
    words = 0
    for idx in ranked:
        n = len(sentences[idx].split())
        if chosen and words + n > max_words:
            continue
        chosen.append(idx)
        words += n
        if len(chosen) >= max_sentences:
            break
    summary = " ".join(sentences[i] for i in sorted(chosen))
    return _clip_words(summary, max_words)
