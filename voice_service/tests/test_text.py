"""The pause and tag layer: pure logic, no model needed."""
from __future__ import annotations

from turbo_voice import DEFAULT_BEAT, MAX_PAUSE, Pause, Say, parse, plain, spans, tags


def pauses(text: str) -> list[float]:
    return [item.seconds for item in parse(text) if isinstance(item, Pause)]


def kinds(text: str) -> list[str]:
    return [type(item).__name__ for item in parse(text)]


def test_plain_sentence_is_a_single_span():
    assert kinds("Hello there.") == ["Say"]


def test_blank_line_is_a_beat():
    assert kinds("One.\n\nTwo.") == ["Say", "Pause", "Say"]
    assert pauses("One.\n\nTwo.") == [DEFAULT_BEAT]


def test_explicit_pause_uses_its_seconds():
    assert pauses("One. [[pause:1.5]] Two.") == [1.5]


def test_ellipsis_is_a_beat():
    assert pauses("One... Two.") == [DEFAULT_BEAT]
    assert pauses("One… Two.") == [DEFAULT_BEAT]


def test_adjacent_pauses_are_summed():
    assert pauses("One...\n\nTwo.") == [round(DEFAULT_BEAT * 2, 3)]


def test_long_pause_is_clamped():
    assert pauses("One. [[pause:99]] Two.") == [MAX_PAUSE]


def test_leading_and_trailing_pauses_are_dropped():
    assert kinds("...One.") == ["Say"]
    assert kinds("One...") == ["Say"]


def test_tags_reach_the_model_untouched():
    (only,) = parse("Well, [sigh] fine.")
    assert isinstance(only, Say)
    assert "[sigh]" in only.text


def test_unknown_tags_are_reported_but_known_ones_are_not():
    assert tags("Hi [chortle] there") == ["chortle"]
    assert tags("Hi [sigh] there") == []
    assert tags("Wait [[pause:0.5]] here") == []


def test_numbers_are_not_mistaken_for_pauses():
    assert spans("In 2026 we won.") == ["In 2026 we won."]


def test_plain_strips_markers_and_tags():
    assert plain("Hi [[pause:0.5]] [sigh] there") == "Hi there"


def test_empty_input_has_no_spans():
    assert parse("   ") == []
    assert spans("") == []


def test_whitespace_is_tidied_within_a_span():
    assert spans("Hello    \n  world.") == ["Hello world."]


def test_phonetic_overrides_normalize_proper_nouns():
    items = parse("Carney's second budget will be presented by Mark Carney.")
    assert len(items) == 1
    assert items[0].text == "Car-nee's second budget will be presented by Mark Car-nee."


def test_phonetic_overrides_normalize_markets_and_tech():
    items = parse("Nvidia reported Nasdaq and Sensex rally.")
    assert len(items) == 1
    assert "En-vid-ee-uh" in items[0].text
    assert "Naz-dak" in items[0].text
    assert "Sen-seks" in items[0].text


def test_long_turn_is_split_into_sentences_with_micro_pauses():
    text = (
        "The Canadian Shield Institute just put out a paper called Canadian Dupes. "
        "It asks how we actually define a Canadian firm. "
        "Right now we have a patchwork of rules, and the two new procurement policies each use their own shaky definition. "
        "The prime minister said we will be our own best customer, but those policies are among the weakest in setting clear criteria."
    )
    items = parse(text)
    # Must produce multiple Say items separated by 0.08s Pause items
    say_items = [i for i in items if isinstance(i, Say)]
    pause_items = [i for i in items if isinstance(i, Pause)]
    assert len(say_items) > 1
    assert len(pause_items) == len(say_items) - 1
    assert all(p.seconds == 0.08 for p in pause_items)
    # No abbreviations like U.S. should be broken
    us_text = (
        "The CLOUD Act allows U.S. authorities to compel companies to produce data even when it is stored abroad. "
        "That means information processed by Palantir for Canadian troops could be accessed without a court order."
    )
    us_items = parse(us_text)
    assert any("U.S." in s.text for s in us_items if isinstance(s, Say))


def test_profanity_is_sanitized_to_bleep():
    items = parse("Who the fuck gon beat my ass?")
    assert len(items) == 1
    assert "fuck" not in items[0].text.lower()
    assert "[bleep]" in items[0].text



