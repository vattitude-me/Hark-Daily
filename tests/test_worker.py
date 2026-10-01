from app.worker import Worker


def test_delete_account_removes_audio_and_every_row(cfg, store):
    keep = store.add_user("keep@example.com")
    gone = store.add_user("gone@example.com")
    store.add_source(gone, "My blog", "https://blog.example/feed", "custom")
    store.upload(f"toku-{gone[-1]}/2026-10-01.mp3", b"mp3")
    store.upload(f"toku-{keep[-1]}/2026-10-01.mp3", b"mp3")
    store.upsert_briefing(gone, "2026-10-01", {}, f"toku-{gone[-1]}/2026-10-01.mp3")
    store.requests.append({"id": 1, "user_id": gone, "kind": "delete_account", "status": "queued"})

    Worker(cfg, store).poll_requests()

    assert [p["id"] for p in store.profiles()] == [keep]
    assert not any(s["user_id"] == gone for s in store.sources_)
    assert not any(k[0] == gone for k in store.briefings_)
    assert list(store.objects) == [f"toku-{keep[-1]}/2026-10-01.mp3"]
    assert store.requests == []


def test_failed_delete_is_reported_and_keeps_the_account(cfg, store, monkeypatch):
    uid = store.add_user("me@example.com")
    store.requests.append({"id": 1, "user_id": uid, "kind": "delete_account", "status": "queued"})

    def boom(_uid):
        raise RuntimeError("auth admin unavailable")

    monkeypatch.setattr(store, "delete_user", boom)
    Worker(cfg, store).poll_requests()

    assert [p["id"] for p in store.profiles()] == [uid]
    assert store.requests[0]["status"] == "error"
    assert "auth admin unavailable" in store.requests[0]["message"]
