"""Make news copy speakable and natural for neural text-to-speech voices."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

CURRENCY_PREFIXES = {
    "C": ("Canadian dollar", "Canadian dollars"),
    "CA": ("Canadian dollar", "Canadian dollars"),
    "CAD": ("Canadian dollar", "Canadian dollars"),
    "US": ("U.S. dollar", "U.S. dollars"),
    "USD": ("U.S. dollar", "U.S. dollars"),
    "U.S.": ("U.S. dollar", "U.S. dollars"),
}
SCALE = {
    "k": "thousand",
    "m": "million",
    "mn": "million",
    "b": "billion",
    "bn": "billion",
    "t": "trillion",
    "tn": "trillion",
    "cr": "crore",
    "crore": "crore",
    "lakh": "lakh",
}
QUARTERS = {
    "1": "the first quarter",
    "2": "the second quarter",
    "3": "the third quarter",
    "4": "the fourth quarter",
}

ABBREVIATIONS = {
    r"\be\.g\.?,?": "for example",
    r"\bi\.e\.?,?": "that is",
    r"\bvs\.?\b": "versus",
    r"\bw/": "with",
    r"\bw/o\b": "without",
    r"\bapprox\.": "approximately",
    r"\bGov\.": "Governor",
    r"\bSen\.": "Senator",
    r"\bSt\.": "Saint",
    r"\bOnt\.": "Ontario",
    r"\bQue\.": "Quebec",
    r"\bMt\.": "Mount",
    r"\bNo\.\s*(?=\d)": "number ",
    r"\b#\s*(?=\d)": "number ",
    r"\bdept\.\b": "department",
    r"\bgovt\.\b": "government",
    r"\bcorp\.\b": "corporation",
    r"\binc\.\b": "incorporated",
    r"\bco\.\b": "company",
    r"\bCo\.\b": "Company",
    r"\bCEO's\b": "C E O's",
    r"\bCEOs\b": "C E Os",
    r"\bCEO\b": "C E O",
    r"\bIPO's\b": "I P O's",
    r"\bIPOs\b": "I P Os",
    r"\bIPO\b": "I P O",
    r"\bCTO\b": "C T O",
    r"\bCFO\b": "C F O",
    r"\bCOO\b": "C O O",
}

def _load_lexicon() -> dict[str, str]:
    candidates = [
        Path(os.getenv("LEXICON_PATH", "")),
        Path(__file__).resolve().parent.parent.parent / "data" / "lexicon.json",
        Path(__file__).resolve().parent.parent / "data" / "lexicon.json",
    ]
    for c in candidates:
        if c.is_file():
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
                return {entry["pattern"]: entry["replacement"] for entry in data.get("entries", [])}
            except Exception:
                pass
    return {
        r"\bCarney's\b": "Car-nee's",
        r"\bCarney\b": "Car-nee",
        r"\bPoilievre's\b": "Pwal-ee-ev's",
        r"\bPoilievre\b": "Pwal-ee-ev",
        r"\bTrudeau's\b": "Troo-doh's",
        r"\bTrudeau\b": "Troo-doh",
        r"\bChrystia\b": "Kris-tya",
        r"\bJagmeet\b": "Jug-meet",
        r"\bLegault's\b": "Leh-goh's",
        r"\bLegault\b": "Leh-goh",
        r"\bBlanchet\b": "Blahn-shay",
        r"\bSaskatchewan\b": "Suh-skatch-uh-wun",
        r"\bCalgary\b": "Cal-gree",
        r"\bEdmonton\b": "Ed-mun-tun",
        r"\bByteDance\b": "Bite-dance",
        r"\bHuawei\b": "Hwah-way",
        r"\bNasdaq\b": "Naz-dak",
        r"\bSensex\b": "Sen-seks",
        r"\bNifty\b": "Nif-tee",
        r"\bTSMC\b": "T-S-M-C",
        r"\bNYSE\b": "N-Y-S-E",
        r"\bS&P\b": "S and P",
        r"\bDOGE\b": "Doj",
    }


# Phonetic respelling dictionary for proper nouns, Canadian/world political figures,
# and tricky names so neural TTS models (Chatterbox, Edge) pronounce them with 100% precision.
PRONUNCIATION_OVERRIDES = _load_lexicon()


def voice_phonetic_normalize(text: str) -> str:
    """Normalize tricky proper nouns into phonetic spellings specifically for audio speech synthesis."""
    if not text:
        return ""
    for pattern, repl in PRONUNCIATION_OVERRIDES.items():
        text = re.sub(pattern, repl, text)
    return text

EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF‍️]")

CURRENCY_RE = re.compile(
    r"(?:\b(C|CA|CAD|US|USD|U\.S\.))?(\$|€|£|₹)\s?(\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*(thousand|million|billion|trillion|crore|lakh)\b|\s*(bn|mn|tn|[kmbt])\b)?",
    re.I,
)


def _currency_replace(m: re.Match) -> str:
    prefix = m.group(1) or ""
    sym = m.group(2)
    amount = m.group(3)
    scale_word = m.group(4)
    scale_abbr = m.group(5)

    scale = scale_word.lower() if scale_word else SCALE.get((scale_abbr or "").lower(), "")
    is_singular = amount == "1" and not scale

    if sym == "€":
        curr = "euro" if is_singular else "euros"
    elif sym == "£":
        curr = "pound" if is_singular else "pounds"
    elif sym == "₹":
        curr = "rupee" if is_singular else "rupees"
    else:
        p = CURRENCY_PREFIXES.get(prefix.upper())
        if p:
            curr = p[0] if is_singular else p[1]
        else:
            curr = "dollar" if is_singular else "dollars"

    parts = [amount, scale, curr]
    return " ".join(p for p in parts if p)


def voice_normalize(text: str, preserve_tags: bool = True) -> str:
    """Normalize textual shorthand ($5B, 15%, Q3, etc.) into speakable natural words.

    If preserve_tags is True, paralinguistic Chatterbox tags like [laugh], [chuckle],
    [sigh], [gasp] are retained for voice performance.
    """
    if not text:
        return ""

    tags: list[str] = []
    if preserve_tags:
        def _mask_tag(m: re.Match) -> str:
            tags.append(m.group(0))
            return f"__CHTAG_{len(tags)-1}__"

        text = re.sub(r"\[(laugh|chuckle|sigh|gasp|cough|groan|sniffle|yawn)\]", _mask_tag, text, flags=re.I)

    text = EMOJI.sub("", text)
    text = text.replace("&", " and ")

    # Normalize hyphens and dashes so TTS pauses naturally
    text = re.sub(r"[\u2010\u2011\u00ad]", "-", text)
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    text = re.sub(r"\s+-\s+", ", ", text)

    # Currencies: $5B -> 5 billion dollars, €10M -> 10 million euros, $25 -> 25 dollars, Rs./INR -> rupees
    text = re.sub(r"\b(?:Rs\.?|INR)\s*", "₹", text, flags=re.I)
    text = CURRENCY_RE.sub(_currency_replace, text)

    # Standalone metric/financial scale suffixes: 32B -> 32 billion, 500k -> 500 thousand
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*[bB]\b(?!\w)", r"\1 billion", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*[mM]\b(?!\w)", r"\1 million", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*[kK]\b(?!m|g|w|hz|\w)", r"\1 thousand", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*[tT]\b(?!\w)", r"\1 trillion", text)

    # Percentages: 15% -> 15 percent
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"\1 percent", text)

    # Quarters: Q3 -> the third quarter
    text = re.sub(r"\bQ([1-4])\b", lambda m: QUARTERS[m.group(1)], text)

    # Multipliers: 5x -> 5 times
    text = re.sub(r"\b(\d+(?:\.\d+)?)x\b", r"\1 times", text)

    # Word slashes: and/or -> and or
    text = re.sub(r"\b([a-zA-Z]+)/([a-zA-Z]+)\b", r"\1 or \2", text)

    # Standard abbreviations
    for pattern, repl in ABBREVIATIONS.items():
        text = re.sub(pattern, repl, text)

    if preserve_tags:
        for idx, tag in enumerate(tags):
            text = text.replace(f"__CHTAG_{idx}__", tag)

    # Collapse horizontal whitespace per line while preserving newlines for speech beats
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def speakable(text: str) -> str:
    """Full TTS pipeline text cleaning for solo narrators (strips all brackets and guarantees end punctuation)."""
    text = re.sub(r"https?://\S+", "", text)
    text = voice_normalize(text, preserve_tags=False)
    text = voice_phonetic_normalize(text)
    text = re.sub(r"\s*[\[\]()]\s*", ", ", text)
    text = re.sub(r"[*_#|<>]", " ", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,+", ",", text)
    lines = [re.sub(r"[^\S\n]+", " ", line).strip(" ,") for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    if text and text[-1] not in ".!?":
        text += "."
    return text
