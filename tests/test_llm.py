"""Tests for app.llm consistency, concurrency-safe rate limiting, and provider fallback chains."""
from __future__ import annotations

import dataclasses
import json
import subprocess
import threading

import httpx
import pytest

from app import llm, podcast, podcast_dialogue


# --------------------------------------------------------------------------- helpers

def _chat_completion(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def _fake_story(story_id: str = "s1", headline: str = "Canada launches AI research fund"):
    return {
        "id": story_id,
        "section": "tech",
        "rank": 1,
        "title": headline,
        "source": "CBC News",
        "summary": "Ottawa announced a 500 million dollar fund for domestic AI computing infrastructure.",
    }


def _valid_dialogue_json(headline: str = "Canada launches AI research fund") -> str:
    return json.dumps({
        "summary": "Ottawa announced a 500 million dollar fund to build domestic AI computing clusters across Canada.",
        "turns": [
            {
                "speaker": "a",
                "purpose": "hook",
                "fact_refs": [0],
                "text": "Canada just committed five hundred million dollars toward building domestic AI research compute across universities.",
            },
            {
                "speaker": "b",
                "purpose": "detail",
                "fact_refs": [0],
                "text": "Labs in Toronto and Montreal have waited years for shared graphics clusters to train public models locally.",
            },
            {
                "speaker": "a",
                "purpose": "takeaway",
                "fact_refs": [0],
                "text": "University teams expect the first hardware allocations to come online before next autumn.",
            },
        ],
    })


def _valid_banter_json(pieces: list[podcast.Piece]) -> str:
    payload: dict = {"open": [], "close": [], "tease": {}, "bridge": {}}
    for p in pieces:
        turns = [
            {"speaker": "a", "text": f"Here is the latest update on {p.section or 'today'}."},
            {"speaker": "b", "text": f"Let us walk through what stands out in {p.section or 'this hour'}."},
        ]
        if p.kind in ("open", "close"):
            payload[p.kind].append(turns)
        else:
            payload[p.kind][p.section] = turns
    return json.dumps(payload)


# --------------------------------------------------------------------------- 1. API consistency

def test_post_chat_raw_and_generate_chat_text_json_mode(monkeypatch):
    captured_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=_chat_completion('{"ok": true}'))

    monkeypatch.setattr(llm, "rate_limit_llm", lambda *a, **k: 0.0)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    msgs = [{"role": "user", "content": "Hello"}]

    # Default (json_mode=True) preserves JSON response_format
    resp = llm.post_chat_raw(
        client, url=llm.GROQ_URL, token="tok", model="llama3.1:8b",
        messages=msgs, temperature=0.2, max_tokens=150, throttle=False,
    )
    assert resp.status_code == 200
    assert captured_bodies[-1]["response_format"] == {"type": "json_object"}

    # Non-JSON mode via post_chat_raw omits response_format
    llm.post_chat_raw(
        client, url=llm.GROQ_URL, token="tok", model="llama3.1:8b",
        messages=msgs, temperature=0.2, max_tokens=150, throttle=False, json_mode=False,
    )
    assert "response_format" not in captured_bodies[-1]

    # generate_chat_text propagates json_mode=False and json_mode=True
    txt_plain = llm.generate_chat_text(
        client, model="llama3.1:8b", url=llm.GROQ_URL, token="tok", provider="Groq",
        messages=msgs, temperature=0.2, max_tokens=150, json_mode=False, throttle=False,
    )
    assert txt_plain == '{"ok": true}'
    assert "response_format" not in captured_bodies[-1]

    txt_json = llm.generate_chat_text(
        client, model="llama3.1:8b", url=llm.GROQ_URL, token="tok", provider="Groq",
        messages=msgs, temperature=0.2, max_tokens=150, throttle=False,
    )
    assert txt_json == '{"ok": true}'
    assert captured_bodies[-1]["response_format"] == {"type": "json_object"}


def test_call_agy_cli_respects_json_mode(monkeypatch):
    seen_prompts: list[str] = []

    def fake_run(cmd, **kwargs):
        seen_prompts.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, stdout='Intro text\n{"k": 1}\nOutro text', stderr="")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)

    out_json = llm.call_agy_cli(
        "gemini-3.8-flash-low", [{"role": "user", "content": "Hi"}],
        bin_lookup=lambda: "/usr/local/bin/agy", json_mode=True,
    )
    assert out_json == '{"k": 1}'
    assert "Return ONLY raw valid JSON" in seen_prompts[-1]

    out_plain = llm.call_agy_cli(
        "gemini-3.8-flash-low", [{"role": "user", "content": "Hi"}],
        bin_lookup=lambda: "/usr/local/bin/agy", json_mode=False,
    )
    assert out_plain == 'Intro text\n{"k": 1}\nOutro text'
    assert "Return ONLY raw valid JSON" not in seen_prompts[-1]

    with pytest.raises(RuntimeError, match="not found"):
        llm.call_agy_cli("gemini-3.8-flash-low", [{"role": "user", "content": "Hi"}], bin_lookup=lambda: None)

    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 1, stdout="", stderr="boom"))
    with pytest.raises(RuntimeError, match="agy CLI failed: boom"):
        llm.call_agy_cli("gemini-3.8-flash-low", [{"role": "user", "content": "Hi"}], bin_lookup=lambda: "/usr/local/bin/agy")

    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="  \n ", stderr=""))
    with pytest.raises(ValueError, match="empty output"):
        llm.call_agy_cli("gemini-3.8-flash-low", [{"role": "user", "content": "Hi"}], bin_lookup=lambda: "/usr/local/bin/agy")


# --------------------------------------------------------------------------- 2. Rate limiter concurrency

def test_rate_limit_llm_sequential_and_concurrent_deterministic(monkeypatch):
    # Reset module state cleanly for deterministic testing
    monkeypatch.setattr(llm, "_LAST_LLM_CALL_TIME", None)

    now = [100.0]
    clock_lock = threading.Lock()
    waits: list[float] = []
    dispatches: list[float] = []

    def fake_monotonic() -> float:
        with clock_lock:
            return now[0]

    def fake_sleep(seconds: float) -> None:
        assert not llm._RATE_LOCK.locked(), "sleep() must NOT hold _RATE_LOCK"
        with clock_lock:
            waits.append(seconds)
            now[0] += seconds

    # Sequential behavior: first call is immediate, close second call sleeps interval, later call does not
    assert llm.rate_limit_llm(2.2, monotonic=fake_monotonic, sleep=fake_sleep) == 0.0
    assert llm.rate_limit_llm(2.2, monotonic=fake_monotonic, sleep=fake_sleep) == pytest.approx(2.2)
    with clock_lock:
        now[0] += 5.0
    assert llm.rate_limit_llm(2.2, monotonic=fake_monotonic, sleep=fake_sleep) == 0.0

    # Concurrent burst at a fixed timestamp: slots must be spaced by >= min_interval
    monkeypatch.setattr(llm, "_LAST_LLM_CALL_TIME", None)
    waits.clear()
    with clock_lock:
        now[0] = 200.0
    burst_now = 200.0
    n_threads = 6
    barrier = threading.Barrier(n_threads)
    slot_waits: list[float] = []

    def burst_sleep(seconds: float) -> None:
        assert not llm._RATE_LOCK.locked(), "Concurrent sleep() must run outside _RATE_LOCK"

    def worker() -> None:
        barrier.wait(timeout=2.0)
        w = llm.rate_limit_llm(2.2, monotonic=lambda: burst_now, sleep=burst_sleep)
        with clock_lock:
            slot_waits.append(w)
            dispatches.append(burst_now + w)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)

    dispatches.sort()
    assert len(dispatches) == n_threads
    assert slot_waits.count(0.0) == 1
    for prev, curr in zip(dispatches, dispatches[1:]):
        assert (curr - prev) == pytest.approx(2.2, abs=1e-9)


# --------------------------------------------------------------------------- 3. Provider fallback chains & 429

def test_ai_provider_chain_exact_order(cfg):
    c = dataclasses.replace(
        cfg,
        agy_enabled=True, agy_model="agy-m",
        groq_api_key="g-key", groq_models=("g1", "g2"),
        local_llm_url="http://localhost:11434/v1/chat/completions", local_llm_model="loc1",
        gemini_api_key="gem-key", gemini_models=("gem1", "gem2"),
    )
    chain = llm.ai_provider_chain(c, bin_lookup=lambda: "/usr/local/bin/agy")
    assert [(m, p) for m, _, _, p in chain] == [
        ("agy-m", "AntigravityCLI"),
        ("g1", "Groq"),
        ("g2", "Groq"),
        ("loc1", "LocalLLM"),
        ("gem1", "Gemini"),
        ("gem2", "Gemini"),
    ]


def test_retry_after_and_generate_chat_text_errors(monkeypatch):
    r_hdr = httpx.Response(429, headers={"retry-after": "7.5"}, text="rate limited")
    assert llm.retry_after(r_hdr) == pytest.approx(7.5)
    r_body = httpx.Response(429, text="Please try again in 1m2.5s.")
    assert llm.retry_after(r_body) == pytest.approx(62.5)
    r_def = httpx.Response(429, text="limit")
    assert llm.retry_after(r_def) == pytest.approx(10.0)

    monkeypatch.setattr(llm, "rate_limit_llm", lambda *a, **k: 0.0)
    client_429 = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(429, headers={"retry-after": "5"})))
    with pytest.raises(llm._RetryAfterSignal) as exc_info:
        llm.generate_chat_text(
            client_429, model="g1", url=llm.GROQ_URL, token="t", provider="Groq",
            messages=[{"role": "user", "content": "hi"}], temperature=0.2, max_tokens=10,
            on_rate_limit=llm.retry_after,
        )
    assert exc_info.value.delay == pytest.approx(5.0)

    # Without on_rate_limit handler, 429 raises HTTPStatusError
    with pytest.raises(httpx.HTTPStatusError):
        llm.generate_chat_text(
            client_429, model="g1", url=llm.GROQ_URL, token="t", provider="Groq",
            messages=[{"role": "user", "content": "hi"}], temperature=0.2, max_tokens=10,
        )


def test_podcast_ask_ai_four_provider_fallback_matrix(cfg, monkeypatch):
    c = dataclasses.replace(
        cfg,
        agy_enabled=True, agy_model="agy-m",
        groq_api_key="g-key", groq_models=("g1",),
        local_llm_url="http://local/v1/chat/completions", local_llm_model="loc1",
        gemini_api_key="gem-key", gemini_models=("gem1",),
    )
    monkeypatch.setattr(podcast, "_agy_bin", lambda: "/usr/local/bin/agy")
    monkeypatch.setattr(llm, "rate_limit_llm", lambda *a, **k: 0.0)
    pieces = podcast.plan_pieces([{"section": "tech", "rank": 1, "title": "Chip boom", "summary": "New chips arrive."}])
    good_json = _valid_banter_json(pieces)

    # 1. Primary (AntigravityCLI) succeeds; HTTP providers not called
    http_calls: list[str] = []
    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=good_json, stderr=""))
    client = httpx.Client(transport=httpx.MockTransport(lambda req: (http_calls.append(str(req.url)), httpx.Response(500))[1]))
    written, problems = podcast.ask_ai(c, pieces, ("Matthew", "Kelly"), "2026-11-14", client=client)
    assert len(written) == len(pieces)
    assert all(w.writer == "agy-m" for w in written.values())
    assert http_calls == []
    assert problems == []

    # 2. Primary empty -> Groq timeout -> LocalLLM malformed JSON -> Gemini succeeds
    def cli_empty(*a, **k):
        return subprocess.CompletedProcess(a[0], 0, stdout="   ", stderr="")

    monkeypatch.setattr(llm.subprocess, "run", cli_empty)
    order: list[str] = []

    def multi_fail_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        order.append(url)
        if url == llm.GROQ_URL:
            raise httpx.TimeoutException("groq timed out", request=request)
        if url == "http://local/v1/chat/completions":
            return httpx.Response(200, json=_chat_completion("{bad json"))
        return httpx.Response(200, json=_chat_completion(good_json))

    client = httpx.Client(transport=httpx.MockTransport(multi_fail_handler))
    written, problems = podcast.ask_ai(c, pieces, ("Matthew", "Kelly"), "2026-11-14", client=client)
    assert order == [llm.GROQ_URL, "http://local/v1/chat/completions", llm.GEMINI_URL]
    assert len(problems) == 3
    assert all(w.writer == "gem1" for w in written.values())

    # 3. All providers fail (ConnectError / 429 / empty) -> write_pieces ships template banter
    def all_fail_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == llm.GROQ_URL:
            raise httpx.ConnectError("refused", request=request)
        if url == "http://local/v1/chat/completions":
            return httpx.Response(429, headers={"retry-after": "1"}, text="rate limit")
        return httpx.Response(200, json=_chat_completion(""))

    client = httpx.Client(transport=httpx.MockTransport(all_fail_handler))
    written_tpl, probs_tpl = podcast.write_pieces(c, pieces, ("Matthew", "Kelly"), "2026-11-14", client=client)
    assert len(written_tpl) == len(pieces)
    assert all(w.writer == "built-in" for w in written_tpl.values())
    assert len(probs_tpl) == 4


def test_story_dialogue_four_provider_fallback_and_429_retry(cfg, monkeypatch):
    c = dataclasses.replace(
        cfg,
        agy_enabled=True, agy_model="agy-m",
        groq_api_key="g-key", groq_models=("g1",),
        local_llm_url="http://local/v1/chat/completions", local_llm_model="loc1",
        gemini_api_key="gem-key", gemini_models=("gem1",),
    )
    monkeypatch.setattr(podcast, "_agy_bin", lambda: "/usr/local/bin/agy")
    monkeypatch.setattr(llm, "rate_limit_llm", lambda *a, **k: 0.0)
    story = _fake_story()
    good_dialogue = _valid_dialogue_json()

    # 1. Antigravity fails -> Groq gets short 429 (retry-after=4 <= 35), sleeps & succeeds on attempt 2
    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 1, stdout="", stderr="cli down"))
    sleeps: list[float] = []
    groq_hits = 0

    def groq_retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal groq_hits
        assert str(request.url) == llm.GROQ_URL
        groq_hits += 1
        if groq_hits == 1:
            return httpx.Response(429, headers={"retry-after": "4"})
        return httpx.Response(200, json=_chat_completion(good_dialogue))

    client = httpx.Client(transport=httpx.MockTransport(groq_retry_handler))
    res = podcast_dialogue.generate_story_dialogue(
        c, story, ("Matthew", "Kelly"), client=client, force=True, sleep=sleeps.append,
    )
    assert res.writer == "g1"
    assert sleeps == [4.0]
    assert groq_hits == 2

    # 2. Long 429 (>35s) skips sleep on Groq, LocalLLM raises TimeoutException (twice), Gemini returns malformed JSON -> grounded fallback
    sleeps.clear()
    seen_urls: list[str] = []

    def all_escalate_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen_urls.append(url)
        if url == llm.GROQ_URL:
            return httpx.Response(429, headers={"retry-after": "45"})
        if url == "http://local/v1/chat/completions":
            raise httpx.TimeoutException("local timeout", request=request)
        return httpx.Response(200, json=_chat_completion("not-valid-json"))

    client = httpx.Client(transport=httpx.MockTransport(all_escalate_handler))
    res_fb = podcast_dialogue.generate_story_dialogue(
        c, _fake_story(story_id="s2"), ("Matthew", "Kelly"), client=client, force=True, sleep=sleeps.append,
    )
    assert sleeps == []
    assert seen_urls == [
        llm.GROQ_URL,
        "http://local/v1/chat/completions", "http://local/v1/chat/completions",
        llm.GEMINI_URL, llm.GEMINI_URL,
    ]
    assert res_fb.writer == "built-in"
