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


def test_clean_slop_purges_ai_cliches():
    assert podcast.clean_slop("Alright Kelly, let's roll!") == "Alright Kelly, let's get started!"
    assert podcast.clean_slop("It has been a whirlwind today.") == "It has been a lot happening today."
    assert podcast.clean_slop("Let's dive into the details.") == "Let's look at the details."
    assert podcast.clean_slop("There is quite a lot to unpack here.") == "There is a lot of details here here." or \
           "unpack" not in podcast.clean_slop("There is quite a lot to unpack here.")
    assert "buckle up" not in podcast.clean_slop("Buckle up everyone, big news.")


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


# ------------------------------------------------------------------ story dialogue & PCM stitching
SAMPLE_STORY = {
    "id": "s-ai-1",
    "section": "ai",
    "rank": 1,
    "title": "Open weights model matches frontier reasoning benchmarks",
    "source": "TechCrunch",
    "url": "https://techcrunch.com/2026/10/30/open-weights-model",
    "summary": "Researchers released a 32-billion-parameter model that runs on consumer workstations.",
    "article_text": (
        "Researchers released a 32-billion-parameter model that runs on consumer workstations. "
        "The release includes full training recipes and an Apache 2.0 license for commercial teams. "
        "Independent benchmarks show it matching much larger proprietary systems on coding tasks."
    ),
    "script": "Open weights model matches frontier reasoning benchmarks.",
}


def test_provider_chain_prioritizes_groq_before_gemini(cfg):
    c = dataclasses.replace(
        cfg,
        groq_api_key="g_key",
        groq_models=("groq-m1",),
        local_llm_url="http://localhost:11434/v1/chat/completions",
        local_llm_model="llama3.1:8b",
        gemini_api_key="gem_key",
        gemini_models=("gemini-2.5-flash",),
    )
    chain = podcast._ai_provider_chain(c)
    assert [provider for _, _, _, provider in chain] == ["Groq", "LocalLLM", "Gemini"]


def test_build_story_brief_extracts_facts_and_sober_flag():
    brief = podcast.build_story_brief(SAMPLE_STORY)
    assert brief["section"] == "ai"
    assert brief["sober"] is False
    assert len(brief["facts"]) >= 3
    assert brief["facts"][0]["id"] == "F1"

    sober_brief = podcast.build_story_brief({**SAMPLE_STORY, "section": "politics_us"})
    assert sober_brief["sober"] is True


def test_validate_story_dialogue_enforces_alternation_and_sober_tags():
    brief = podcast.build_story_brief(SAMPLE_STORY)
    good_raw = {
        "turns": [
            {"speaker": "a", "purpose": "lead", "fact_refs": ["F1"], "text": "A new 32 billion parameter open model just landed with frontier coding scores."},
            {"speaker": "b", "purpose": "question", "fact_refs": ["F2"], "text": "[chuckle] And it actually runs on a single workstation under an Apache license?"},
            {"speaker": "a", "purpose": "context", "fact_refs": ["F2", "F3"], "text": "Yes, the team published the full training recipe alongside the weights."},
            {"speaker": "b", "purpose": "takeaway", "fact_refs": ["F3"], "text": "That gives smaller developer teams a serious local alternative, according to TechCrunch."},
        ]
    }
    turns = podcast.validate_story_dialogue(good_raw, brief)
    assert turns is not None and len(turns) == 4
    assert [t.speaker for t in turns] == [0, 1, 0, 1]
    assert "[chuckle]" in turns[1].text
    assert turns[1].pause_after == podcast.PURPOSE_PAUSES["question"]

    # Sober section strips paralinguistic tags
    sober_brief = podcast.build_story_brief({**SAMPLE_STORY, "section": "top"})
    sober_turns = podcast.validate_story_dialogue(good_raw, sober_brief)
    assert sober_turns is not None
    assert "[chuckle]" not in sober_turns[1].text

    # Single-speaker monologue is rejected
    monologue = {"turns": [{**t, "speaker": "a"} for t in good_raw["turns"]]}
    assert podcast.validate_story_dialogue(monologue, brief) is None


def test_generate_story_dialogue_uses_groq_and_repairs_invalid_first_attempt(cfg):
    c = dataclasses.replace(cfg, groq_api_key="g_key", groq_models=("groq-fast",))
    attempts = 0

    def handler(req):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            # First attempt returns only 1 turn (invalid)
            bad = {"summary": "Short.", "turns": [{"speaker": "a", "text": "Too short."}]}
            return _ok(bad)(req)
        good = {
            "summary": "A 32B open model runs on workstations with Apache 2.0 licensing.",
            "turns": [
                {"speaker": "a", "purpose": "lead", "fact_refs": ["F1"], "text": "Researchers just released a 32 billion parameter model built for workstations."},
                {"speaker": "b", "purpose": "context", "fact_refs": ["F2"], "text": "It ships with full training recipes and an Apache 2.0 commercial license."},
                {"speaker": "a", "purpose": "implication", "fact_refs": ["F3"], "text": "Independent benchmarks put it right alongside much larger proprietary systems on coding."},
                {"speaker": "b", "purpose": "takeaway", "fact_refs": ["F2", "F3"], "text": "That is a major step forward for local developer workflows, TechCrunch reports."},
            ],
        }
        return _ok(good)(req)

    dialogue = podcast.generate_story_dialogue(c, SAMPLE_STORY, HOSTS, client=_client(handler), force=True)
    assert attempts == 2
    assert dialogue.writer == "groq-fast"
    assert len(dialogue.turns) == 4
    formatted = podcast.format_dialogue_transcript(dialogue.turns, HOSTS)
    assert "[Matthew]" in formatted and "[Kelly]" in formatted


def test_generate_story_dialogue_falls_back_to_grounded_facts_when_ai_offline(cfg):
    dialogue = podcast.generate_story_dialogue(cfg, SAMPLE_STORY, HOSTS, force=True)
    assert dialogue.writer == "built-in"
    assert len(dialogue.turns) >= 3
    assert {t.speaker for t in dialogue.turns} == {0, 1}


def test_stitch_turns_inserts_audible_silence_between_hosts():
    from app import audio
    sr = 24000
    t = audio. np.arange(int(0.5 * sr), dtype=audio.np.float32) / sr
    tone = 0.2 * audio.np.sin(2 * audio.np.pi * 220 * t)
    pause_sec = 0.40
    combined, marks = audio.stitch_turns([(tone, pause_sec), (tone, 0.35)], sr=sr)
    assert len(marks) == 2
    gap_start = int(marks[0][1] * sr) + int(0.05 * sr)
    gap_end = int(marks[1][0] * sr) - int(0.05 * sr)
    assert gap_end > gap_start
    gap_rms = float(audio.np.sqrt(audio.np.mean(combined[gap_start:gap_end] ** 2)))
    assert gap_rms < 1e-4, f"Expected near-zero silence between turns, got RMS={gap_rms}"


def test_voice_scripts_duo_synthesizes_two_host_conversation(cfg, voice):
    store = FakeStore()
    c = _cfg(cfg)
    rows = run(storypack.voice_scripts(
        store, [SAMPLE_STORY], day="2026-10-30", voice="matthew_reference+kelly_reference",
        base="http://v", force=True, cfg=c,
    ))
    assert len(rows) == 1
    row = rows[0]
    assert row["voice"] == "matthew_reference+kelly_reference"
    assert "[Matthew]" in row["script"] and "[Kelly]" in row["script"]
    assert {v for v, _ in voice} == {"matthew_reference", "kelly_reference"}
    assert row["audio_path"] in store.objects
    assert row["duration"] > 1.0
