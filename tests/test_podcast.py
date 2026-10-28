from __future__ import annotations

import asyncio
import dataclasses
import json

import httpx
import pytest

from app import podcast, storypack
from tests.conftest import FakeStore

run = asyncio.run
HOSTS = ("Matthew", "Kelly")
SCRIPTS = [
    {"section": "top", "rank": 1, "title": "Floods hit the east coast", "summary": "Heavy rain caused floods."},
    {"section": "top", "rank": 2, "title": "Second top story", "summary": "x"},
    {"section": "ai", "rank": 1, "title": "New AI model launches", "summary": "A lab released a model."},
]


def _cfg(cfg, **kw):
    return dataclasses.replace(cfg, podcast_enabled=True,
                               podcast_hosts=("matthew_reference", "kelly_reference"), **kw)


def _ai_json(**over):
    good = lambda *t: [{"speaker": s, "text": x} for s, x in t]  # noqa: E731
    data = {
        "open": [good(("a", "Good morning Kelly, how are you?"), ("b", "Great, Matthew!"))] * 3,
        "close": [good(("a", "That's all. Bye."))] * 2,
        "tease": {"top": good(("a", "Scary floods today."), ("b", "Yes.")),
                  "ai": good(("a", "Exciting AI news."))},
        "bridge": {"top": good(("a", "Starting with the main story.")), "ai": good(("b", "Now AI."))},
    }
    data.update(over)
    return data


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok(data):
    return lambda req: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(data)}}]})


# ------------------------------------------------------------------ catalogue
def test_plan_has_variants_and_a_tease_per_present_section():
    keys = [p.key for p in podcast.plan_pieces(SCRIPTS)]
    assert keys.count("pod_open_1") == 1 and "pod_open_3" in keys and "pod_close_2" in keys
    assert "pod_tease_top" in keys and "pod_tease_ai" in keys and "pod_tease_sports" not in keys
    tease = next(p for p in podcast.plan_pieces(SCRIPTS) if p.key == "pod_tease_top")
    assert tease.headline == "Floods hit the east coast"  # rank 1, not rank 2


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize("raw", [
    None, [], "text", [{"speaker": "c", "text": "hi"}], [{"speaker": "a", "text": ""}],
    [{"speaker": "a", "text": "see https://x.com"}], [{"speaker": "a", "text": "*bold*"}],
    [{"speaker": "a", "text": "word " * 60}], [{"speaker": "a", "text": "hi"}] * 9, ["not a dict"],
])
def test_validate_rejects_bad_pieces(raw):
    assert podcast.validate_turns(raw, "open") is None


def test_validate_accepts_good_piece():
    assert podcast.validate_turns([{"speaker": "A", "text": "Hi there"}, {"speaker": "b", "text": "Hey"}], "open") \
        == [(0, "Hi there"), (1, "Hey")]


# ------------------------------------------------------------------ templates
def test_templates_cover_every_piece_without_ai(cfg):
    pieces = podcast.plan_pieces(SCRIPTS)
    written, problems = podcast.write_pieces(cfg, pieces, HOSTS, "2026-10-27")
    assert problems == ["no AI key configured"]
    assert set(written) == {p.key for p in pieces}
    for p in pieces:
        w = written[p.key]
        assert w.writer == "built-in"
        assert podcast.validate_turns([{"speaker": "ab"[s], "text": t} for s, t in w.turns], p.kind) is not None, p.key
        assert "{" not in podcast.transcript(w.turns)
    assert "Kelly" in podcast.transcript(written["pod_open_1"].turns)
    assert "Floods hit the east coast" in podcast.transcript(written["pod_tease_top"].turns) \
        or "Floods" in podcast.transcript(written["pod_tease_top"].turns)


# ------------------------------------------------------------------ AI chain
def test_ai_pieces_used_and_bad_ones_replaced(cfg):
    c = dataclasses.replace(cfg, groq_api_key="k", groq_models=("m1",))
    data = _ai_json(bridge={"top": [{"speaker": "a", "text": "http://spam"}], "ai": [{"speaker": "b", "text": "Now AI."}]})
    written, problems = podcast.write_pieces(c, podcast.plan_pieces(SCRIPTS), HOSTS, "2026-10-27", client=_client(_ok(data)))
    assert written["pod_open_1"].writer == "m1"
    assert written["pod_tease_ai"].writer == "m1"
    assert written["pod_bridge_ai"].writer == "m1"
    assert written["pod_bridge_top"].writer == "built-in"  # invalid -> template
    assert problems == []


def test_falls_through_models_then_template(cfg):
    c = dataclasses.replace(cfg, groq_api_key="k", groq_models=("bad", "good"))

    def handler(req):
        if json.loads(req.content)["model"] == "bad":
            return httpx.Response(429, text="rate limited")
        return _ok(_ai_json())(req)

    written, problems = podcast.write_pieces(c, podcast.plan_pieces(SCRIPTS), HOSTS, "2026-10-27", client=_client(handler))
    assert written["pod_open_1"].writer == "good"
    assert len(problems) == 1 and "bad" in problems[0]


def test_ai_down_everywhere_uses_templates(cfg):
    c = dataclasses.replace(cfg, groq_api_key="k", groq_models=("m",))
    written, problems = podcast.write_pieces(
        c, podcast.plan_pieces(SCRIPTS), HOSTS, "2026-10-27",
        client=_client(lambda r: httpx.Response(500, text="boom")))
    assert {w.writer for w in written.values()} == {"built-in"} and problems


def test_garbage_json_uses_templates(cfg):
    c = dataclasses.replace(cfg, groq_api_key="k", groq_models=("m",))
    h = lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})  # noqa: E731
    written, problems = podcast.write_pieces(c, podcast.plan_pieces(SCRIPTS), HOSTS, "2026-10-27", client=_client(h))
    assert {w.writer for w in written.values()} == {"built-in"} and problems


# ------------------------------------------------------------------ audio
@pytest.fixture
def voice(monkeypatch):
    calls = []

    async def fake_synth(client, base, text, voice, attempts=3):
        calls.append((voice, text))
        if "FAIL" in text:
            raise RuntimeError("tts refused")
        return f"<{voice}>".encode(), 2.0

    monkeypatch.setattr(storypack, "synthesise", fake_synth)
    return calls


def test_flag_off_does_nothing(cfg, voice):
    store = FakeStore()
    assert run(podcast.build_podcast(dataclasses.replace(cfg, podcast_enabled=False), store, SCRIPTS,
                                     day="2026-10-27", base="http://v")) == []
    assert not voice and not store.tables


def test_publishes_pieces_and_ready_marker(cfg, voice):
    store = FakeStore()
    rows = run(podcast.build_podcast(_cfg(cfg), store, SCRIPTS, day="2026-10-27", base="http://v"))
    keys = {r["clip_key"] for r in store.tables["podcast_clips"]}
    assert podcast.READY_KEY in keys and "pod_open_1" in keys and "pod_tease_ai" in keys
    assert len(rows) == len(podcast.plan_pieces(SCRIPTS))
    # Both hosts speak, each with their own voice, and the audio is stored.
    assert {v for v, _ in voice} == {"matthew_reference", "kelly_reference"}
    assert all(r["audio_path"] in store.objects for r in rows)
    assert all(r["duration"] > 0 for r in rows)


def test_rerun_reuses_existing_pieces(cfg, voice):
    store = FakeStore()
    run(podcast.build_podcast(_cfg(cfg), store, SCRIPTS, day="2026-10-27", base="http://v"))
    first = len(voice)
    run(podcast.build_podcast(_cfg(cfg), store, SCRIPTS, day="2026-10-27", base="http://v"))
    assert len(voice) == first


def test_one_failed_piece_is_skipped_but_podcast_still_ready(cfg, voice, monkeypatch):
    store = FakeStore()
    monkeypatch.setitem(podcast.BRIDGE_TEMPLATES, "excited", [(1, "FAIL now")])
    with pytest.raises(podcast.PodcastIncomplete) as err:
        run(podcast.build_podcast(_cfg(cfg), store, SCRIPTS, day="2026-10-27", base="http://v"))
    assert "pod_bridge_ai" in str(err.value)
    keys = {r["clip_key"] for r in store.tables["podcast_clips"]}
    assert podcast.READY_KEY in keys and "pod_bridge_ai" not in keys and "pod_tease_ai" in keys


def test_no_opening_means_not_ready(cfg, voice, monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(podcast, "OPEN_TEMPLATES", [[(0, "FAIL")]])
    with pytest.raises(podcast.PodcastIncomplete):
        run(podcast.build_podcast(_cfg(cfg), store, SCRIPTS, day="2026-10-27", base="http://v"))
    assert podcast.READY_KEY not in {r["clip_key"] for r in store.tables.get("podcast_clips", [])}


def test_bad_host_config_is_reported_not_crashing(cfg, voice):
    c = dataclasses.replace(cfg, podcast_enabled=True, podcast_hosts=("only_one",))
    with pytest.raises(podcast.PodcastIncomplete):
        run(podcast.build_podcast(c, FakeStore(), SCRIPTS, day="2026-10-27", base="http://v"))


# ------------------------------------------------------------------ voice tags
def _t(text, who="a"):
    return [{"speaker": who, "text": text}]


def test_known_voice_tags_are_kept_and_unknown_brackets_rejected():
    assert podcast.validate_turns(_t("[Chuckle] Fair point."), "tease", "ai") == [(0, "[chuckle] Fair point.")]
    assert podcast.validate_turns(_t("[shout] Fair point."), "tease", "ai") is None
    assert podcast.validate_turns(_t("[[pause:2]] hi"), "open") is None


def test_too_many_tags_rejected_and_tags_dont_count_as_words():
    assert podcast.validate_turns(_t("[laugh] a [sigh] b [gasp] c"), "open") is None
    just_fits = " ".join(["word"] * podcast.MAX_WORDS["bridge"])
    assert podcast.validate_turns(_t(f"[chuckle] {just_fits}"), "bridge", "ai") is not None


def test_tags_removed_in_sober_sections():
    assert podcast.validate_turns(_t("[laugh] Big floods today."), "tease", "top") == [(0, "Big floods today.")]
    assert podcast.validate_turns(_t("[sigh] Tough vote."), "bridge", "politics") == [(0, "Tough vote.")]
    assert podcast.validate_turns(_t("[laugh] Good morning!"), "open") == [(0, "[laugh] Good morning!")]


def test_captions_have_no_tags_but_voice_gets_them(cfg, voice):
    store = FakeStore()
    run(podcast.build_podcast(_cfg(cfg), store, SCRIPTS, day="2026-10-27", base="http://v"))
    assert any("[" in line for _, line in voice)
    assert all("[" not in r["text"] for r in store.tables["podcast_clips"])


def test_clean_replaces_emdashes_and_endashes():
    assert podcast._clean("News today — AI is booming – and fast") == "News today, AI is booming, and fast"
    assert podcast._clean("Ready —. Yes.") == "Ready. Yes."
    turns = podcast.validate_turns([{"speaker": "a", "text": "Hello — how are you?"}], "open")
    assert turns == [(0, "Hello, how are you?")]
