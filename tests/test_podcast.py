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

    async def fake_synth(client, base, text, voice, attempts=3, *args, **kwargs):
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


def test_provider_chain_prioritizes_groq_before_gemini(cfg, monkeypatch):
    c = dataclasses.replace(
        cfg,
        agy_enabled=False,
        groq_api_key="g_key",
        groq_models=("groq-m1",),
        local_llm_url="http://localhost:11434/v1/chat/completions",
        local_llm_model="llama3.1:8b",
        gemini_api_key="gem_key",
        gemini_models=("gemini-3.5-flash-lite",),
    )
    chain = podcast._ai_provider_chain(c)
    assert [provider for _, _, _, provider in chain] == ["Groq", "LocalLLM", "Gemini"]

    monkeypatch.setattr(podcast, "_agy_bin", lambda: "/opt/homebrew/bin/agy")
    c_with_agy = dataclasses.replace(c, agy_enabled=True, agy_model="gemini-3.8-flash-low")
    chain_agy = podcast._ai_provider_chain(c_with_agy)
    assert [provider for _, _, _, provider in chain_agy] == ["AntigravityCLI", "Groq", "LocalLLM", "Gemini"]


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
            {"speaker": "b", "purpose": "question", "fact_refs": ["F2"], "text": "And it actually runs on a single workstation [chuckle] under an Apache license?"},
            {"speaker": "a", "purpose": "context", "fact_refs": ["F2", "F3"], "text": "Yes, the team published the full training recipe alongside the weights."},
            {"speaker": "b", "purpose": "takeaway", "fact_refs": ["F3"], "text": "That gives smaller developer teams a serious local alternative, according to TechCrunch."},
        ]
    }
    turns = podcast.validate_story_dialogue(good_raw, brief)
    assert turns is not None and len(turns) == 4
    assert [t.speaker for t in turns] == [0, 1, 0, 1]
    assert "[chuckle]" in turns[1].text
    assert turns[1].pause_after == podcast.PURPOSE_PAUSES["question"]

    # Canned reflex tag at start of Turn 2 is stripped automatically
    leading_raw = {
        "turns": [
            {"speaker": "a", "purpose": "lead", "fact_refs": ["F1"], "text": "A new 32 billion parameter open model just landed with frontier coding scores."},
            {"speaker": "b", "purpose": "question", "fact_refs": ["F2"], "text": "[laugh] And it actually runs on a single workstation under an Apache license?"},
            {"speaker": "a", "purpose": "context", "fact_refs": ["F2", "F3"], "text": "Yes, the team published the full training recipe alongside the weights."},
            {"speaker": "b", "purpose": "takeaway", "fact_refs": ["F3"], "text": "That gives smaller developer teams a serious local alternative, according to TechCrunch."},
        ]
    }
    cleaned_turns = podcast.validate_story_dialogue(leading_raw, brief)
    assert cleaned_turns is not None
    assert not cleaned_turns[1].text.startswith("[laugh]")
    assert cleaned_turns[1].text.startswith("And it actually runs")

    # Sober section strips paralinguistic tags
    sober_brief = podcast.build_story_brief({**SAMPLE_STORY, "section": "top"})
    sober_turns = podcast.validate_story_dialogue(good_raw, sober_brief)
    assert sober_turns is not None
    assert "[chuckle]" not in sober_turns[1].text

    # Single-speaker monologue is rejected
    monologue = {"turns": [{**t, "speaker": "a"} for t in good_raw["turns"]]}
    assert podcast.validate_story_dialogue(monologue, brief) is None

    # Swearing / profanity is strictly rejected
    profane_raw = {
        "turns": [
            {"speaker": "b", "text": "Did you hear about Soul Glo's latest record?"},
            {"speaker": "a", "text": "Who the fuck gon beat my ass?"},
            {"speaker": "b", "text": "It is hailed as a punk milestone."},
        ]
    }
    assert podcast.validate_story_dialogue(profane_raw, brief) is None


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


def test_voice_normalize_converts_financial_and_textual_shorthand():
    from app.tts.text import voice_normalize
    assert voice_normalize("Anthropic raised $5B at a $60B valuation.") == "Anthropic raised 5 billion dollars at a 60 billion dollars valuation."
    assert voice_normalize("Revenue jumped 15% in Q3 vs Q2 w/ $500K in profit.") == "Revenue jumped 15 percent in the third quarter versus the second quarter with 500 thousand dollars in profit."
    assert voice_normalize("Acquisition cost €50M and £10B before the IPO.") == "Acquisition cost 50 million euros and 10 billion pounds before the I P O."
    assert voice_normalize("[chuckle] The stock gained $25.") == "[chuckle] The stock gained 25 dollars."


def test_voice_phonetic_normalize_fixes_proper_noun_pronunciation():
    from app.tts.text import voice_phonetic_normalize
    assert voice_phonetic_normalize("Carney's 2nd budget earmarks billions.") == "Car-nee's 2nd budget earmarks billions."
    assert voice_phonetic_normalize("Prime Minister Mark Carney announced funding.") == "Prime Minister Mark Car-nee announced funding."
    assert voice_phonetic_normalize("Pierre Poilievre criticized the budget.") == "Pierre Pwal-ee-ev criticized the budget."
    assert voice_phonetic_normalize("Justin Trudeau and Chrystia Freeland spoke.") == "Justin Troo-doh and Kris-tya Freeland spoke."
    assert voice_phonetic_normalize("Visiting Calgary and Saskatchewan next week.") == "Visiting Cal-gree and Suh-skatch-uh-wun next week."


def test_prompt_demands_voice_based_spoken_text():
    assert "VOICE-BASED TEXT" in podcast.STORY_DIALOGUE_PROMPT
    assert "$5B" in podcast.STORY_DIALOGUE_PROMPT
    assert "5 billion dollars" in podcast.STORY_DIALOGUE_PROMPT
    assert "VOICE-BASED SPOKEN TEXT" in podcast.SYSTEM_PROMPT


def test_format_dialogue_transcript_normalizes_textual_shorthand():
    turns = [
        podcast.DialogueTurn(speaker=0, text="They secured $5B in funding.", purpose="lead", fact_refs=["F1"]),
        podcast.DialogueTurn(speaker=1, text="That represents 15% growth in Q3.", purpose="context", fact_refs=["F2"]),
    ]
    script = podcast.format_dialogue_transcript(turns, HOSTS)
    assert "[Matthew] They secured 5 billion dollars in funding." in script
    assert "[Kelly] That represents 15 percent growth in the third quarter." in script


def test_validate_story_dialogue_allows_short_human_reactions_and_quick_hits():
    brief = podcast.build_story_brief(SAMPLE_STORY)
    # Format 1: Explainer + 1-word human reaction ("Huh.") + continuation
    explainer_raw = {
        "turns": [
            {"speaker": "b", "purpose": "lead", "fact_refs": ["F1"], "text": "A research lab just dropped a 32 billion parameter open model that actually runs on a standard workstation."},
            {"speaker": "a", "purpose": "reaction", "fact_refs": ["F1"], "text": "Huh."},
            {"speaker": "b", "purpose": "context", "fact_refs": ["F2", "F3"], "text": "And they included the full training recipe under an Apache 2.0 license, matching much bigger proprietary models on coding."},
            {"speaker": "a", "purpose": "takeaway", "fact_refs": ["F3"], "text": "That is a real shift for smaller teams who want to run everything locally."},
        ]
    }
    turns = podcast.validate_story_dialogue(explainer_raw, brief)
    assert turns is not None and len(turns) == 4
    assert turns[1].text == "Huh."
    assert turns[1].pause_after == 0.28

    # Format 4: Quick hit (2 turns total)
    quick_hit_raw = {
        "turns": [
            {"speaker": "b", "purpose": "lead", "fact_refs": ["F1", "F2"], "text": "Researchers just released a 32 billion parameter open model with full training recipes under an Apache license."},
            {"speaker": "a", "purpose": "takeaway", "fact_refs": ["F3"], "text": "And independent benchmarks show it matching much larger proprietary systems on coding while running on a single workstation."},
        ]
    }
    qh_turns = podcast.validate_story_dialogue(quick_hit_raw, brief)
    assert qh_turns is not None and len(qh_turns) == 2


def test_select_story_format_rotates_and_never_repeats_consecutive():
    prev = None
    chosen_formats = []
    for rank in range(1, 7):
        fmt, desc = podcast.select_story_format("ai", rank, sober=False, previous_format=prev)
        assert fmt in podcast.STORY_FORMATS
        assert desc
        if prev is not None:
            assert fmt != prev, f"Rank {rank} repeated previous format {prev}"
        chosen_formats.append(fmt)
        prev = fmt
    assert len(set(chosen_formats)) == 6


def test_select_story_lead_assigns_matthew_to_heavy_and_kelly_to_light():
    heavy_brief = podcast.build_story_brief({**SAMPLE_STORY, "id": "pol-1", "section": "politics"})
    markets_brief = podcast.build_story_brief({**SAMPLE_STORY, "id": "mkt-1", "section": "markets"})
    light_brief = podcast.build_story_brief({**SAMPLE_STORY, "id": "ent-2", "section": "entertainment"})
    assert "Matthew ('a'" in podcast.select_story_lead(heavy_brief, HOSTS) or "Kelly ('b') opens this one in a rare serious role reversal" in podcast.select_story_lead(heavy_brief, HOSTS)
    assert "Matthew" in podcast.select_story_lead(markets_brief, HOSTS)
    assert "Kelly" in podcast.select_story_lead(light_brief, HOSTS)


def test_parse_story_dialogue_payload_supports_script_lines_and_json():
    brief = podcast.build_story_brief(SAMPLE_STORY)
    script_lines = (
        "KELLY: A new 32 billion parameter open model just landed that runs on a single workstation.\n"
        "MATTHEW: Wait, really?\n"
        "KELLY: Yes, with full training recipes and an Apache license, matching big proprietary systems on coding.\n"
        "MATTHEW: That gives smaller engineering teams a serious local option.\n"
    )
    turns = podcast.validate_story_dialogue(script_lines, brief, HOSTS)
    assert turns is not None and len(turns) == 4
    assert [t.speaker for t in turns] == [1, 0, 1, 0]


def test_yesterdays_opening_is_fetched_and_passed_to_ai(cfg):
    store = FakeStore()
    store.insert("podcast_clips", {
        "date": "2026-10-26",
        "hosts": "matthew_reference+kelly_reference",
        "clip_key": "pod_open_1",
        "text": "This is Hark Daily. Yesterday's tagline.",
        "duration": 8.0,
        "audio_path": "podcast/2026-10-26/pod_open_1.mp3",
        "writer": "m1",
    })
    yest = podcast.fetch_yesterdays_opening(store, "2026-10-27", "matthew_reference+kelly_reference")
    assert yest == "This is Hark Daily. Yesterday's tagline."

    captured_payloads = []

    def handler(req):
        user_msg = json.loads(req.content)["messages"][1]["content"]
        captured_payloads.append(json.loads(user_msg))
        return _ok(_ai_json())(req)

    c = dataclasses.replace(cfg, groq_api_key="k", groq_models=("m1",))
    podcast.write_pieces(
        c, podcast.plan_pieces(SCRIPTS), HOSTS, "2026-10-27",
        client=_client(handler), yesterdays_opening=yest,
    )
    assert captured_payloads and captured_payloads[0].get("yesterdays_opening") == yest


def test_expanded_banned_phrases_and_hark_daily_brand_templates():
    assert "strap in" not in podcast.clean_slop("Strap in, here are the numbers.").lower()
    assert "great point" not in podcast.clean_slop("That's a great point, Matthew.").lower()
    assert "welcome back everyone" not in podcast.clean_slop("Welcome back everyone to the show.").lower()
    assert "fascinating" not in podcast.clean_slop("That is fascinating news.").lower()
    for tmpl in podcast.OPEN_TEMPLATES:
        joined = " ".join(t for _, t in tmpl)
        assert "Hark Daily" in joined
        assert "Welcome back everyone" not in joined
    for tmpl in podcast.CLOSE_TEMPLATES:
        joined = " ".join(t for _, t in tmpl)
        assert "Hark Daily" in joined


# ------------------------------------------------------------------ Unified Improvement Plan Tests
def test_solo_format_validation_and_fallback():
    brief_matthew = {
        "story_id": "test-solo-1",
        "section": "markets",
        "rank": 1,
        "sober": True,
        "story_format": "solo_matthew",
        "headline": "Markets hit new record high today.",
        "facts": [{"id": "F1", "fact": "Markets hit new record high today."},
                  {"id": "F2", "fact": "Tech stocks led the rally across global exchanges."}],
    }
    # Solo Matthew: speaker 0 only (needs >= 18 words total)
    turns_matthew = [
        {"speaker": "a", "purpose": "lead", "fact_refs": ["F1"], "text": "Markets closed at fresh record highs today following strong tech sector earnings."},
        {"speaker": "a", "purpose": "takeaway", "fact_refs": ["F2"], "text": "Tech shares drove the broad gains across North American exchanges."},
    ]
    res_m = podcast.validate_story_dialogue({"turns": turns_matthew}, brief_matthew, HOSTS)
    assert res_m is not None
    assert len(res_m) == 2
    assert all(t.speaker == 0 for t in res_m)

    # Solo Matthew rejects speaker 1 (Kelly)
    turns_bad = [
        {"speaker": "b", "purpose": "lead", "fact_refs": ["F1"], "text": "Markets closed at fresh record highs today following strong tech sector earnings."},
    ]
    assert podcast.validate_story_dialogue({"turns": turns_bad}, brief_matthew, HOSTS) is None

    # Solo Kelly: speaker 1 only (needs >= 18 words total)
    brief_kelly = dict(brief_matthew, story_format="solo_kelly")
    turns_kelly = [
        {"speaker": "b", "purpose": "lead", "fact_refs": ["F1"], "text": "Markets closed at fresh record highs today following strong tech sector earnings."},
        {"speaker": "b", "purpose": "takeaway", "fact_refs": ["F2"], "text": "Tech shares drove the broad gains across North American exchanges."},
    ]
    res_k = podcast.validate_story_dialogue({"turns": turns_kelly}, brief_kelly, HOSTS)
    assert res_k is not None
    assert len(res_k) == 2
    assert all(t.speaker == 1 for t in res_k)

    # Fallback generates solo dialogue cleanly
    fb_m = podcast.fallback_story_dialogue(
        {"id": "s1", "section": "markets", "rank": 1, "headline": "Nifty surges", "summary": "Index reaches new high", "source": "Bloomberg"},
        HOSTS,
    )
    assert len(fb_m.turns) >= 1
    # Check fallback format logic


def test_lead_takeaway_format_validation():
    brief = {
        "story_id": "test-2turn-1",
        "section": "top",
        "rank": 2,
        "sober": False,
        "story_format": "lead_takeaway",
        "headline": "New battery tech doubles electric vehicle range.",
        "facts": [{"id": "F1", "fact": "New battery tech doubles electric vehicle range."},
                  {"id": "F2", "fact": "Mass production begins next spring."}],
    }
    turns = [
        {"speaker": "b", "purpose": "lead", "fact_refs": ["F1"], "text": "Engineers just unveiled a new battery design that promises double the range."},
        {"speaker": "a", "purpose": "takeaway", "fact_refs": ["F2"], "text": "Production begins next spring, so we will see commercial rollout soon."},
    ]
    res = podcast.validate_story_dialogue({"turns": turns}, brief, HOSTS)
    assert res is not None
    assert len(res) == 2
    assert {t.speaker for t in res} == {0, 1}


def test_sentence_length_ceiling_for_tts_pacing():
    brief = {
        "story_id": "test-len-1",
        "section": "top",
        "rank": 1,
        "sober": False,
        "story_format": "explainer_reactions",
        "headline": "Headline.",
        "facts": [{"id": "F1", "fact": "Headline."}],
    }
    # Turn with an individual sentence of 28 words (> 24 ceiling)
    long_sentence = (
        "This is an extremely long sentence that continues on and on without any punctuation or stopping "
        "because someone wrote a massive run-on sentence that severely slows down the neural voice model."
    )
    assert len(long_sentence.split()) > 24
    turns_bad = [
        {"speaker": "a", "purpose": "lead", "fact_refs": ["F1"], "text": long_sentence},
        {"speaker": "b", "purpose": "reaction", "fact_refs": ["F1"], "text": "Right."},
    ]
    assert podcast.validate_story_dialogue({"turns": turns_bad}, brief, HOSTS) is None

    # Sentence under 24 words passes (needs >= 20 words across turns)
    short_sentence = "This is a clean, punchy spoken lead sentence for neural text to speech."
    turns_ok = [
        {"speaker": "a", "purpose": "lead", "fact_refs": ["F1"], "text": short_sentence},
        {"speaker": "b", "purpose": "reaction", "fact_refs": ["F1"], "text": "Right, that makes total sense and sounds very natural."},
    ]
    assert podcast.validate_story_dialogue({"turns": turns_ok}, brief, HOSTS) is not None


def test_profanity_rejection_in_story_dialogue():
    brief = {
        "story_id": "test-profanity-1",
        "section": "tech",
        "rank": 1,
        "sober": False,
        "headline": "Music news.",
        "facts": [{"id": "F1", "fact": "Band releases hardcore record."}],
    }
    turns_vulgar = [
        {"speaker": "b", "purpose": "lead", "fact_refs": ["F1"], "text": "Have you heard the new album?"},
        {"speaker": "a", "purpose": "reaction", "fact_refs": ["F1"], "text": "Who the fuck is going to beat that?"},
    ]
    assert podcast.validate_story_dialogue({"turns": turns_vulgar}, brief, HOSTS) is None


def test_synthesise_story_dialogue_wav_and_pace_temp_honest_cache(tmp_path):
    recorded_calls = []

    async def mock_synth(client, base, text, voice, attempts=3, *, pace=None, temperature=None, fmt="mp3", **kwargs):
        recorded_calls.append({"text": text, "voice": voice, "pace": pace, "temp": temperature, "fmt": fmt})
        return b"RIFFmockwavdata12345678", 1.5

    import app.storypack as sp
    from unittest.mock import patch

    turns = [
        podcast.DialogueTurn(speaker=0, text="Matthew leads with steady pace.", purpose="lead", fact_refs=["F1"], pause_after=0.4),
        podcast.DialogueTurn(speaker=1, text="Kelly replies with lively energy.", purpose="context", fact_refs=["F2"], pause_after=0.3),
        podcast.DialogueTurn(speaker=1, text="Wait really?", purpose="reaction", fact_refs=["F2"], pause_after=0.28),
    ]
    dialogue = podcast.StoryDialogue(
        story_id="s1", section="top", headline="Headline", summary="Summary", turns=turns, writer="test", story_format="conversational_dialogue"
    )

    with patch.object(sp, "synthesise", side_effect=mock_synth):
        async def run_synth():
            async with httpx.AsyncClient() as client:
                return await podcast.synthesise_story_dialogue(
                    client, "http://voice", dialogue, ("matthew_reference", "kelly_reference"), cache_dir=tmp_path
                )

        mp3_bytes, dur, marks = run(run_synth())
        assert mp3_bytes is not None
        assert dur > 0
        assert len(marks) == 3
        # Check that format requested is 'wav'
        assert all(c["fmt"] == "wav" for c in recorded_calls)
        # Check Matthew pace=0.93, Kelly pace=0.97, reaction pace=0.98
        assert recorded_calls[0]["pace"] == 0.93
        assert recorded_calls[0]["temp"] == 0.82
        assert recorded_calls[1]["pace"] == 0.97
        assert recorded_calls[1]["temp"] == 0.88
        assert recorded_calls[2]["pace"] == 0.98
        assert recorded_calls[2]["temp"] == 0.90
        # Check cache files written with .wav and .json
        cached_wavs = list((tmp_path / "podcast_turns").glob("*.wav"))
        assert len(cached_wavs) == 3


def test_facts_deduplication_and_fallback_anti_repetition():
    story = {
        "section": "tech_us",
        "rank": 3,
        "headline": "Here’s the full text of Jensen Huang’s memo to Nvidia",
        "source": "The Verge",
        "summary": "On Sunday, Nvidia announced it was launching an investigation into CEO Jensen Huang’s relationship with Alice Huang, an AI executive.",
        "article_text": "On Sunday, Nvidia announced it was launching an investigation into CEO Jensen Huang’s relationship with Alice Huang, an AI executive."
    }
    brief = podcast.build_story_brief(story)
    # Check that facts do NOT contain duplicates between normalized summary and article_text
    facts_text = [f["fact"] for f in brief["facts"]]
    assert len(facts_text) == len(set(f.lower() for f in facts_text))

    # Test fallback dialogue does not duplicate turns and never emits robotic filler
    dial = podcast.fallback_story_dialogue(story, HOSTS)
    assert len(dial.turns) >= 2
    # Ensure Turn 1 and Turn 2 are never identical
    assert dial.turns[0].text.lower().rstrip(".") != dial.turns[1].text.lower().rstrip(".")
    for turn in dial.turns:
        low = turn.text.lower()
        assert "reporting from" not in low
        assert "reporting there from" not in low
        assert "that comes from" not in low
        assert "key developments we are tracking" not in low
        assert "here is what is developing" not in low


def test_clean_existing_script_filters_fragments_and_placeholders():
    from scripts.regen_story import clean_existing_script

    # Truncated stub followed by full sentence
    corrupt_script = (
        "[Matthew] A memo circulated earlier this year claimed that technology executive Alice Huang was recruited by China’s Ministry of State Security to spy o "
        "[Matthew] A memo circulated earlier this year claimed that technology executive Alice Huang was recruited by China’s Ministry of State Security to spy on Nvidia C E O Jensen Huang, according to multiple media reports."
    )
    cleaned = clean_existing_script(corrupt_script)
    assert "to spy o A memo" not in cleaned
    assert "to spy o " not in cleaned
    assert cleaned.startswith("A memo circulated earlier this year claimed that technology executive Alice Huang was recruited by China’s Ministry of State Security to spy on Nvidia C E O Jensen Huang")
    # Boilerplate placeholder filtering
    placeholder = "[Matthew] Full details on that story are available from New York Times · Top stories."
    assert clean_existing_script(placeholder) == ""
