"""Make news copy easier for a neural voice to read aloud."""
from __future__ import annotations

import re

ABBREVIATIONS = {
    r"\be\.g\.": "for example",
    r"\bi\.e\.": "that is",
    r"\bvs\.?": "versus",
    r"\bapprox\.": "approximately",
    r"\bGov\.": "Governor",
    r"\bSen\.": "Senator",
    r"\bSt\.": "Saint",
    r"\bOnt\.": "Ontario",
    r"\bQue\.": "Quebec",
    r"\bMt\.": "Mount",
    r"\bNo\. (?=\d)": "number ",
    r"\bCEO's\b": "C E O's",
}
SCALE = {"k": "thousand", "m": "million", "mn": "million", "b": "billion", "bn": "billion", "t": "trillion", "tn": "trillion"}
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF‍️]")


def _money(m: re.Match) -> str:
    prefix, amount, scale_word, scale_abbr = m.group(1) or "", m.group(2), m.group(3), m.group(4)
    currency = {"C": "Canadian dollars", "CA": "Canadian dollars", "US": "U.S. dollars", "U.S.": "U.S. dollars"}.get(
        prefix, "dollars"
    )
    scale = scale_word or SCALE.get((scale_abbr or "").lower(), "")
    return " ".join(p for p in (amount, scale, currency) if p)


def speakable(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = EMOJI.sub("", text)
    text = text.replace("&", " and ").replace("%", " percent").replace("…", ".")
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    text = re.sub(
        r"(?:\b(C|CA|US|U\.S\.))?\$\s?(\d[\d,]*(?:\.\d+)?)(?:\s?(thousand|million|billion|trillion)\b|(bn|mn|tn|[kmbt])\b)?",
        _money,
        text,
        flags=re.I,
    )
    for pattern, repl in ABBREVIATIONS.items():
        text = re.sub(pattern, repl, text)
    text = re.sub(r"\s*[\[\]()]\s*", ", ", text)
    text = re.sub(r"[*_#|<>]", " ", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    if text and text[-1] not in ".!?":
        text += "."
    return text
