from __future__ import annotations

import json

import httpx

from app.fetcher import parse_feed
from app.ranking import select_top
from app.report import RunReport
from datetime import datetime

from app.writer import StoryWriter, compose, section_leads, template_copy

from . import fakenews
from .conftest import BASE

MODELS = ("big", "small")


def _stories(n=3):
    _, items = parse_feed(fakenews.rss("tech", BASE).encode(), {"id": 1, "name": "Circuit", "section": "tech"})
    return select_top(items, {"tech": n})["tech"]


def _ok(model):
    content = json.dumps({"headline": f"H by {model}", "summary": "Card summary.", "spoken": "Spoken copy."})
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _writer(tmp_path, responder, key="gsk_test"):
    calls = []

    def handle(request):
        model = json.loads(request.content)["model"]
        calls.append(model)
        return responder(model, len(calls))

    report = RunReport("test")
    w = StoryWriter(tmp_path, report, api_key=key, models=MODELS,
                    client=httpx.Client(transport=httpx.MockTransport(handle)), sleep=lambda s: None)
    return w, report, calls


def test_groq_writes_copy_and_caches_it(tmp_path):
    w, report, calls = _writer(tmp_path, lambda m, n: _ok(m))
    story = _stories(1)[0]
    first = w.copy("tech", story)
    again = w.copy("tech", story)
    assert first.writer == "big" and first.spoken == "Spoken copy." and again == first
    assert calls == ["big"]
    assert report.writers["big"] == 2 and not report.issues


def test_per_minute_limit_waits_and_retries(tmp_path):
    def respond(model, n):
        if n == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, json={"error": {"message": "Rate limit reached for model on tokens per minute (TPM). Please try again in 3s."}})
        return _ok(model)

    w, report, calls = _writer(tmp_path, respond)
    assert w.copy("tech", _stories(1)[0]).writer == "big"
    assert calls == ["big", "big"]
    assert [i.code for i in report.issues] == ["ai_rate_limited"]
    assert report.for_user("anyone") == []  # info only: users aren't bothered


def test_daily_limit_moves_to_the_next_model_then_built_in(tmp_path):
    def respond(model, n):
        if model == "big" or n > 3:
            return httpx.Response(429, json={"error": {"message": f"Rate limit reached for model `{model}` on tokens per day (TPD). Please try again in 7m12s."}})
        return _ok(model)

    w, report, calls = _writer(tmp_path, respond)
    s1, s2, s3 = _stories(3)
    assert w.copy("tech", s1).writer == "small"
    assert w.copy("tech", s2).writer == "small"
    assert w.copy("tech", s3).writer == "built-in"   # small's daily limit hit too
    assert w.copy("tech", _stories(3)[2]).writer == "built-in"
    assert calls.count("big") == 1, "an exhausted model isn't retried"
    assert [i.code for i in report.issues] == ["ai_daily_limit"]
    assert "free daily limit" in report.for_user("u")[0]["message"]
    assert "small 2" in report.summary() and "built-in 2" in report.summary()


def test_bad_key_switches_to_built_in_and_tells_the_admin(tmp_path):
    w, report, calls = _writer(tmp_path, lambda m, n: httpx.Response(401, json={"error": {"message": "Invalid API Key"}}))
    for s in _stories(3):
        assert w.copy("tech", s).writer == "built-in"
    assert calls == ["big"]
    assert report.issues[0].code == "ai_auth" and report.issues[0].level == "error"
    assert not report.ok


def test_repeated_server_errors_give_up_on_ai(tmp_path):
    w, report, calls = _writer(tmp_path, lambda m, n: httpx.Response(503, text="overloaded"))
    for s in _stories(4):
        assert w.copy("tech", s).writer == "built-in"
    assert [i.code for i in report.issues] == ["ai_unavailable"]
    assert len(calls) == 9  # 3 attempts on each of 3 stories, then Groq is skipped


def test_no_key_uses_built_in_quietly(tmp_path):
    report = RunReport("test")
    w = StoryWriter(tmp_path, report, api_key=None, models=MODELS)
    assert w.copy("tech", _stories(1)[0]).writer == "built-in"
    assert report.for_user("u") == []


def test_template_connector_is_the_same_for_a_story_everywhere():
    story = _stories(3)[2]
    assert template_copy(story).spoken == template_copy(story).spoken


def test_spoken_copy_is_clean_unless_the_listener_wants_sources():
    stories = _stories(2)
    copies = {s.id: template_copy(s) for s in stories}
    assert all("Circuit" not in c.spoken for c in copies.values())
    when = datetime(2026, 9, 30, 7)
    clean = compose({"tech": stories}, copies, when, None)
    credited = compose({"tech": stories}, copies, when, None, say_sources=True)
    assert all("Circuit" not in c.spoken for c in clean.stories.values())
    assert all(c.spoken.endswith(".") and "Circuit" in c.spoken for c in credited.stories.values())
    assert "Circuit" not in copies[stories[0].id].spoken  # the shared copy is untouched


def test_intro_does_not_count_stories_and_sections_are_announced_in_order():
    stories = _stories(3)
    copies = {s.id: template_copy(s) for s in stories}
    when = datetime(2026, 9, 30, 7)
    script = compose({"canada": stories[:1], "tech": stories[1:2], "custom": stories[2:]}, copies, when, None, name="Ana")
    assert script.intro == "Good morning, Ana! It's Wednesday, September 30. Here's your briefing."
    assert script.section_leads == {
        "canada": "First, the top stories from across Canada.",
        "tech": "Next, the latest in AI and technology.",
        "custom": "And finally, stories from the sources you follow.",
    }
    # Two sections: no "Next"; one section: just the topic.
    assert section_leads(["tech", "custom"]) == {"tech": "First, the latest in AI and technology.",
                                                 "custom": "And finally, stories from the sources you follow."}
    assert section_leads(["tech"]) == {"tech": "The latest in AI and technology."}
