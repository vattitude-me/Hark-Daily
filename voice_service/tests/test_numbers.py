"""Numbers are spelled out so the voice model never has to read digits."""
from __future__ import annotations

import pytest

from turbo_voice import spans
from turbo_voice.numbers import cardinal, ordinal, spell_numbers, year


@pytest.mark.parametrize(
    "n, words",
    [
        (0, "zero"),
        (7, "seven"),
        (19, "nineteen"),
        (40, "forty"),
        (287, "two hundred eighty-seven"),
        (1_000, "one thousand"),
        (1_200_000, "one million two hundred thousand"),
        (3_004_050, "three million four thousand fifty"),
    ],
)
def test_cardinal(n, words):
    assert cardinal(n) == words


@pytest.mark.parametrize(
    "n, words",
    [(1, "first"), (2, "second"), (12, "twelfth"), (20, "twentieth"), (21, "twenty-first"), (100, "one hundredth")],
)
def test_ordinal(n, words):
    assert ordinal(n) == words


@pytest.mark.parametrize(
    "n, words",
    [(2026, "twenty twenty-six"), (2005, "two thousand five"), (1900, "nineteen hundred"), (1905, "nineteen oh five")],
)
def test_year(n, words):
    assert year(n) == words


@pytest.mark.parametrize(
    "text, spoken",
    [
        (
            "They identified 287 unique genetic variants.",
            "They identified two hundred eighty-seven unique genetic variants.",
        ),
        ("a 194-year-old giant tortoise", "a one hundred ninety-four-year-old giant tortoise"),
        ("1,200 jobs", "one thousand two hundred jobs"),
        ("up 3.5 percent", "up three point five percent"),
        ("64.6 million euro", "sixty-four point six million euro"),
        ("down 0.05 percent to 1.25", "down zero point zero five percent to one point two five"),
        ("in the 1990s", "in the nineteen nineties"),
        ("the 21st century", "the twenty-first century"),
        ("at 7:30 tonight", "at seven thirty tonight"),
        ("from 2020-2025", "from twenty twenty to twenty twenty-five"),
        ("won 3-2", "won three two"),
        ("the G7 and 5G", "the G7 and 5G"),
        ("COVID-19", "COVID-nineteen"),
        ("no digits here", "no digits here"),
    ],
)
def test_spell_numbers(text, spoken):
    assert spell_numbers(text) == spoken


def test_pause_markers_survive():
    assert spans("Up 287. [[pause:0.8]] Down 3.") == ["Up two hundred eighty-seven.", "Down three."]
