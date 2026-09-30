"""Lightweight extractive summarizer used when no LLM is configured."""
from __future__ import annotations

import re
from collections import Counter

from .ranking import STOPWORDS

SENTENCE_SPLIT = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"”’']))\s+(?=[A-Z0-9\"“‘'])")
BOILERPLATE = re.compile(
    r"(sign up|subscribe|newsletter|click here|read more|follow us|advertisement|©|all rights reserved|"
    r"this article|photo:|image:|getty images|the canadian press$)",
    re.I,
)


def split_sentences(text: str, title: str = "") -> list[str]:
    """Split article text into sentences, skipping headings, captions and a repeated title."""
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
        out.extend(s.strip() for s in SENTENCE_SPLIT.split(para) if s.strip())
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
