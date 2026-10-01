from __future__ import annotations

import json

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import push
from app.batch import Batch, notify_admin
from app.report import RunReport

from . import fakenews
from .conftest import BASE

ARTICLE = f"{BASE}/tech/articles/" + fakenews.slug(fakenews.STORIES["tech"][1][0])


def run(cfg, store, **kw):
    report = RunReport("test")
    results = Batch(cfg, store, report, progress=lambda *a: None).run(**kw)
    return report, {r.profile["email"]: r for r in results}


def test_builds_a_personal_briefing_for_each_user(cfg, store):
    a = store.add_user("a@example.com", name="Ana")
    b = store.add_user("b@example.com", disabled_sources=[3])  # b switched off the tech feed
    art = store.add_source(a, "Saved article", ARTICLE, "custom", kind="article")

    report, results = run(cfg, store)

    assert report.ok and sorted(report.built) == ["a@example.com", "b@example.com"]
    ba, bb = results["a@example.com"].briefing, results["b@example.com"].briefing
    assert {s["key"] for s in ba["sections"]} == {"canada", "tech", "custom"}
    assert {s["key"] for s in bb["sections"]} == {"canada"}
    assert ba["intro"].startswith("Good morning, Ana!") and "Toronto" in ba["intro"]
    assert ba["writer"] == "built-in"
    day = ba["date"]
    assert store.objects[f"toku-1/{day}.mp3"][:3] in (b"ID3",) or store.objects[f"toku-1/{day}.mp3"][0] == 0xFF
    assert ba["audio_url"].startswith(f"{store.url}/storage/v1/object/public/briefings/toku-1/{day}.mp3?v=")
    assert store.briefings_[(b, day)]["data"]["stories"]
    assert store.source(art["id"])["consumed_at"], "single articles are used once"
    assert store.profiles_[0]["status"]["ok"] is True
    bank = next(s for s in ba["stories"] if "Bank of Canada" in s["headline"])
    assert bank["also"], "duplicate coverage is merged into one card"
    starts = [c["start"] for c in ba["chapters"]]
    assert starts == sorted(starts)


def test_users_with_daily_off_are_skipped_unless_named(cfg, store):
    store.add_user("a@example.com", daily=False)
    _, results = run(cfg, store)
    assert results == {}
    _, results = run(cfg, store, emails=["A@example.com"], scheduled=False)
    assert results["a@example.com"].briefing


def test_fresh_run_clears_today_and_requeues_articles(cfg, store):
    a = store.add_user("a@example.com")
    art = store.add_source(a, "Saved article", ARTICLE, "custom", kind="article")
    run(cfg, store)
    day = datetime.now(ZoneInfo(cfg.timezone)).date().isoformat()
    first = store.briefings_[(a, day)]["data"]["audio_url"]
    assert store.source(art["id"])["consumed_at"]
    assert any((cfg.cache_dir / "tts").iterdir())

    # Without --fresh the used article isn't read again.
    _, results = run(cfg, store)
    assert "custom" not in {s["key"] for s in results["a@example.com"].briefing["sections"]}

    _, results = run(cfg, store, fresh=True, emails=["a@example.com"], scheduled=False)
    again = results["a@example.com"].briefing
    assert "custom" in {s["key"] for s in again["sections"]}
    assert store.briefings_[(a, day)]["data"]["audio_url"] != first or again["generated_at"]


def test_old_briefings_are_deleted(cfg, store):
    a = store.add_user("a@example.com")
    today = datetime.now(ZoneInfo(cfg.timezone)).date()
    for n in (1, 2, 5):
        d = (today - timedelta(days=n)).isoformat()
        store.upsert_briefing(a, d, {}, f"toku-1/{d}.mp3")
        store.objects[f"toku-1/{d}.mp3"] = b"x"
    run(cfg, store)
    kept = sorted(d for (_, d) in store.briefings_)
    assert kept == [(today - timedelta(days=1)).isoformat(), today.isoformat()]
    assert sorted(p for p in store.objects if p.startswith("toku-1/")) == [f"toku-1/{d}.mp3" for d in kept]


def test_stories_from_yesterday_are_not_told_again(cfg, store):
    a = store.add_user("a@example.com")
    _, results = run(cfg, store)
    first = results["a@example.com"].briefing
    told = first["stories"][0]
    yesterday = (datetime.fromisoformat(first["date"]) - timedelta(days=1)).date().isoformat()
    store.upsert_briefing(a, yesterday, {"stories": [told]}, "")

    _, results = run(cfg, store, fresh=True)

    again = results["a@example.com"].briefing["stories"]
    assert told["url"] not in {c["url"] for c in again}
    assert len(again) == len(first["stories"]) - 1, "today's own briefing doesn't count as heard"


def test_new_links_are_detected_and_private_ones_refused(cfg, store):
    import dataclasses

    cfg = dataclasses.replace(cfg, allow_private_urls=False)
    a = store.add_user("a@example.com")
    new = store.add_source(a, f"{BASE}/tech/feed.xml", f"{BASE}/tech/feed.xml", "custom", kind="auto", feed_url="")
    lan = store.add_source(a, "Router", "http://192.168.1.1/feed", "custom", kind="feed")
    import app.fetcher as fetcher

    # sample.news isn't a real host: treat it as public, but keep the real check for IPs.
    real = fetcher.check_public_url
    patched = lambda url, allow: None if "sample.news" in url else real(url, allow)  # noqa: E731
    import app.batch as batch

    batch.check_public_url, fetcher.check_public_url = patched, patched
    try:
        report, results = run(cfg, store)
    finally:
        batch.check_public_url, fetcher.check_public_url = real, real
    assert store.source(new["id"])["kind"] == "feed"
    assert store.source(new["id"])["name"] == "Circuit Report"
    assert "private network" in store.source(lan["id"])["last_status"]
    assert results["a@example.com"].briefing


def test_failing_link_is_reported_to_its_owner_only(cfg, store):
    a = store.add_user("a@example.com")
    b = store.add_user("b@example.com")
    store.add_source(a, "Broken", f"{BASE}/missing/feed.xml", "custom")
    report, results = run(cfg, store)
    codes_a = [n["code"] for n in results["a@example.com"].briefing["notes"]]
    codes_b = [n["code"] for n in results["b@example.com"].briefing["notes"]]
    assert codes_a == ["sources_failed"] and codes_b == []
    assert b


def test_user_without_stories_fails_cleanly_and_others_still_build(cfg, store):
    store.add_user("a@example.com")
    store.add_user("b@example.com", disabled_sources=[1, 2, 3])
    report, results = run(cfg, store)
    assert results["a@example.com"].briefing
    assert results["b@example.com"].briefing is None
    assert "switch on at least one source" in results["b@example.com"].error
    assert report.failed == ["b@example.com"] and not report.ok
    assert store.profiles_[1]["status"]["ok"] is False


def test_storage_failure_is_reported(cfg, store, monkeypatch):
    from app.store import StoreError

    store.add_user("a@example.com")

    def full(*a, **k):
        raise StoreError("Payload too large", 413)

    monkeypatch.setattr(store, "upload", full)
    report, results = run(cfg, store)
    assert "storage space may be full" in results["a@example.com"].error
    assert [i.code for i in report.issues] == ["ai_off", "storage_failed"]
    assert [n["code"] for n in report.for_user(store.profiles_[0]["id"])] == ["storage_failed"]


def test_admin_is_notified_when_a_run_has_problems(cfg, store, monkeypatch):
    admin = store.add_user("admin@example.com")
    store.subs.append({"endpoint": "https://push/admin", "user_id": admin, "p256dh": "k", "auth": "a"})
    sent = []
    monkeypatch.setattr(push, "send", lambda cfg, subs, title, body, url="/": sent.append((subs, title, body)) or (1, []))

    clean = RunReport("schedule")
    clean.built.append("x")
    notify_admin(cfg, store, clean)
    assert sent == []

    bad = RunReport("schedule")
    bad.add("ai_daily_limit", "llama: tokens per day")
    notify_admin(cfg, store, bad)
    subs, title, body = sent[-1]
    assert subs[0]["endpoint"] == "https://push/admin" and title.startswith("⚠️") and "ai_daily_limit" in body

    # Supabase down: the cached admin subscription is still used.
    down = RunReport("schedule")
    down.add("supabase_down", "unreachable", level="error")
    notify_admin(cfg, None, down)
    assert sent[-1][0][0]["endpoint"] == "https://push/admin" and sent[-1][1].startswith("❌")


def test_admin_briefing_becomes_the_landing_page_demo(cfg, store):
    admin = store.add_user("admin@example.com")
    store.add_source(admin, "Saved article", ARTICLE, "custom", kind="article")
    store.add_user("b@example.com")
    report, results = run(cfg, store)
    assert report.ok, report.issues

    demo = json.loads(store.objects["showcase/sample.json"])
    briefing = demo["briefing"]
    mp3 = briefing["audio_url"].split("/briefings/")[1]
    assert mp3.startswith("showcase/")
    assert store.objects[mp3] == store.objects[f"toku-1/{briefing['date']}.mp3"], "a copy of the admin's audio"
    assert briefing["stories"] and all(c["section"] != "custom" and "links" not in c for c in briefing["stories"])
    assert briefing["notes"] == [] and demo["voices"]

    # A rebuild the same day replaces the demo and leaves only one MP3 behind.
    Batch(cfg, store, RunReport("adhoc"), notify=False).run(emails=["admin@example.com"], scheduled=False)
    assert len([p for p in store.list_objects("showcase") if p.endswith(".mp3")]) == 1
    assert json.loads(store.objects["showcase/sample.json"])["briefing"]["audio_url"] != briefing["audio_url"]


def test_runs_without_the_admin_leave_the_demo_alone(cfg, store):
    store.add_user("admin@example.com")
    store.add_user("b@example.com")
    Batch(cfg, store, RunReport("adhoc"), notify=False).run(emails=["b@example.com"], scheduled=False)
    assert store.list_objects("showcase") == []


def test_store_retries_a_dropped_connection_but_not_a_plain_insert(monkeypatch):
    import httpx
    from app.store import Store, StoreError

    calls = []

    def flaky(request):
        calls.append(request.method)
        if len(calls) == 1:
            raise httpx.ReadError("ssl/tls alert bad record mac")
        return httpx.Response(200, json=[])

    s = Store("https://proj.supabase.co", "sb_secret_x", client=httpx.Client(transport=httpx.MockTransport(flaky)))
    monkeypatch.setattr("app.store.time.sleep", lambda _s: None)
    assert s.select("profiles") == [] and calls == ["GET", "GET"]

    calls.clear()
    with pytest.raises(StoreError):
        s.insert("sources", {"url": "x"})
    assert calls == ["POST"], "a plain insert might have landed, so it isn't repeated"
