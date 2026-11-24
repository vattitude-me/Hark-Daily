"""Spell numbers out as words before they reach the voice model.

Chatterbox reads digits unreliably: "287" can come out as a garbled run of
sounds instead of "two hundred eighty-seven". Writing every number as words
removes the guesswork. This runs only on the text that gets voiced, so cards
and transcripts keep their digits.

Covered: cardinals ("287", "1,200,000"), decimals ("3.5"), years ("2026",
"1990s"), ordinals ("21st"), clock times ("7:30"), and numeric ranges
("2020-2025"). Digits glued to letters ("G7", "5G") are left alone;
"COVID-19" becomes "COVID-nineteen".
"""
from __future__ import annotations

import re

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_SCALES = ((10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand"))

_ORDINAL_SUFFIX = {
    "one": "first", "two": "second", "three": "third", "five": "fifth",
    "eight": "eighth", "nine": "ninth", "twelve": "twelfth",
}


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    if not hundreds:
        return _below_hundred(rest)
    head = f"{_ONES[hundreds]} hundred"
    return f"{head} {_below_hundred(rest)}" if rest else head


def cardinal(n: int) -> str:
    """287 -> "two hundred eighty-seven"."""
    if n < 0:
        return "minus " + cardinal(-n)
    if n < 1000:
        return _below_thousand(n)
    parts: list[str] = []
    for value, name in _SCALES:
        if n >= value:
            chunk, n = divmod(n, value)
            parts.append(f"{cardinal(chunk)} {name}")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def ordinal(n: int) -> str:
    """21 -> "twenty-first"."""
    words = cardinal(n)
    head, sep, last = words.rpartition("-" if "-" in words.split()[-1] else " ")
    if last in _ORDINAL_SUFFIX:
        last = _ORDINAL_SUFFIX[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return f"{head}{sep}{last}"


def year(n: int) -> str:
    """2026 -> "twenty twenty-six", 1900 -> "nineteen hundred", 2005 -> "two thousand five"."""
    if 2000 <= n <= 2009:
        return cardinal(n)
    high, low = divmod(n, 100)
    if low == 0:
        return f"{cardinal(high)} hundred"
    if low < 10:
        return f"{cardinal(high)} oh {_ONES[low]}"
    return f"{cardinal(high)} {_below_hundred(low)}"


def _plural(words: str) -> str:
    """"nineteen ninety" -> "nineteen nineties", "two thousand" -> "two thousands"."""
    if words.endswith("y"):
        return words[:-1] + "ies"
    if words.endswith("x"):
        return words + "es"
    return words + "s"


def _digits(s: str) -> str:
    return " ".join(_ONES[int(d)] for d in s)


def _is_year(s: str) -> bool:
    return s.isascii() and s.isdigit() and len(s) == 4 and 1100 <= int(s) <= 2099


def _number(raw: str) -> str:
    """Speak one bare number token: integer with optional commas and decimals."""
    whole, _, frac = raw.partition(".")
    whole = whole.replace(",", "")
    if len(whole) > 15 or (len(whole) > 1 and whole.startswith("0") and not frac):
        return _digits(whole)
    words = cardinal(int(whole))
    if frac:
        words += " point " + _digits(frac)
    return words


# A number not glued to a letter on its left. Commas only count as thousands
# separators when they sit in groups of three.
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_LEFT = r"(?<![A-Za-z\d.,])"

_TIME = re.compile(rf"{_LEFT}([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_RANGE = re.compile(rf"{_LEFT}(\d+)\s*[-–]\s*(\d+)(?![\d.A-Za-z])")
_DECADE = re.compile(rf"{_LEFT}(\d{{4}}|\d0)'?s\b")
_ORDINAL = re.compile(rf"{_LEFT}(\d+)(st|nd|rd|th)\b", re.I)
_PLAIN = re.compile(rf"{_LEFT}({_NUM})(?![\dA-Za-z])")


def _time(m: re.Match) -> str:
    hour, minute = int(m.group(1)), int(m.group(2))
    if minute == 0:
        return cardinal(hour)
    if minute < 10:
        return f"{cardinal(hour)} oh {_ONES[minute]}"
    return f"{cardinal(hour)} {_below_hundred(minute)}"


def _range(m: re.Match) -> str:
    a, b = m.group(1), m.group(2)
    if int(a) >= int(b):
        # Not a range: a score such as 3-2. Keep the dash out of the audio.
        return f"{_say(a)} {_say(b)}"
    return f"{_say(a)} to {_say(b)}"


def _say(s: str) -> str:
    return year(int(s)) if _is_year(s) else _number(s)


def _decade(m: re.Match) -> str:
    s = m.group(1)
    return _plural(year(int(s)) if len(s) == 4 else cardinal(int(s)))


def spell_numbers(text: str) -> str:
    """Rewrite every number in ``text`` as spoken English words."""
    if not text or not any(c.isdigit() for c in text):
        return text
    text = _TIME.sub(_time, text)
    text = _RANGE.sub(_range, text)
    text = _DECADE.sub(_decade, text)
    text = _ORDINAL.sub(lambda m: ordinal(int(m.group(1))), text)
    text = _PLAIN.sub(lambda m: _say(m.group(1)), text)
    return text
