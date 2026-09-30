from __future__ import annotations

import dataclasses
import time

from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import BASE, use_sample_sources


def client_for(cfg, **overrides):
    app = create_app(dataclasses.replace(cfg, allow_private_urls=True, **overrides), start_scheduler=False)
    return app, TestClient(app)


def test_empty_state_and_static_ui(cfg):
    _, client = client_for(cfg)
    assert client.get("/api/briefing/latest").json() == {"briefing": None}
    assert "Morning Brief" in client.get("/").text
    assert client.get("/api/briefing/2020-01-01").status_code == 404


def test_sources_crud(cfg):
    _, client = client_for(cfg)
    sources = client.get("/api/sources").json()["sources"]
    assert any(s["builtin"] and s["section"] == "canada" for s in sources)

    preview = client.post("/api/sources/detect", json={"url": f"{BASE}/"}).json()
    assert preview["kind"] == "feed" and preview["sample"]

    created = client.post("/api/sources", json={"url": f"{BASE}/tech/feed.xml", "section": "custom"})
    assert created.status_code == 201
    sid = created.json()["source"]["id"]
    assert client.post("/api/sources", json={"url": f"{BASE}/tech/feed.xml"}).status_code == 409

    patched = client.patch(f"/api/sources/{sid}", json={"enabled": False, "section": "tech"}).json()["source"]
    assert patched["enabled"] is False and patched["section"] == "tech"
    assert client.delete(f"/api/sources/{sid}").status_code == 204

    builtin = next(s for s in sources if s["builtin"])
    assert client.delete(f"/api/sources/{builtin['id']}").status_code == 400
    assert client.post("/api/sources/detect", json={"url": f"{BASE}/nope"}).status_code == 422


def test_private_urls_blocked_by_default(cfg):
    _, client = client_for(cfg)
    app = create_app(cfg, start_scheduler=False)
    r = TestClient(app).post("/api/sources/detect", json={"url": "http://127.0.0.1:9/feed"})
    assert r.status_code == 422
    assert "private" in r.json()["detail"]


def test_settings_validation(cfg):
    _, client = client_for(cfg)
    ok = client.put("/api/settings", json={"briefing_time": "07:15", "speed": 1.1, "stories": {"tech": 20}})
    assert ok.status_code == 200
    s = ok.json()["settings"]
    assert s["briefing_time"] == "07:15" and s["stories"]["tech"] == 12 and s["stories"]["canada"] == 6
    assert client.put("/api/settings", json={"briefing_time": "7am"}).status_code == 422
    assert client.put("/api/settings", json={"voice": "nope:x"}).status_code == 422
    voices = client.get("/api/voices").json()["voices"]
    assert any(v["id"] == "kokoro:af_heart" and v["recommended"] for v in voices)
    assert any(v["accent"] == "Canadian" for v in voices)


def test_generate_and_fetch_briefing(cfg):
    app, client = client_for(cfg)
    use_sample_sources(app.state.db)
    assert client.post("/api/briefing/generate").json()["started"] is True
    for _ in range(200):
        status = client.get("/api/status").json()
        if not status["running"]:
            break
        time.sleep(0.05)
    assert status["error"] is None, status
    data = client.get("/api/briefing/latest").json()["briefing"]
    assert data["stories"]
    audio = client.get(data["audio_url"])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"
    assert client.get("/api/briefings").json()["briefings"][0]["date"] == data["date"]


def test_voice_preview_is_cached(cfg):
    _, client = client_for(cfg)
    r = client.get("/api/voices/preview", params={"voice": "fake:tone"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert list(cfg.cache_dir.glob("preview-*.mp3"))
    assert client.get("/api/voices/preview", params={"voice": "bad:x"}).status_code == 404


def test_password_protection(cfg):
    _, client = client_for(cfg, app_password="s3cret")
    assert client.get("/api/sources").status_code == 401
    assert client.get("/api/sources", auth=("me", "s3cret")).status_code == 200


def test_healthz_skips_password(cfg):
    _, client = client_for(cfg, app_password="s3cret")
    assert client.get("/healthz").json() == {"ok": True}


def test_edge_only_host_hides_kokoro(monkeypatch):
    from app import tts

    monkeypatch.setenv("TTS_ENGINES", "edge")
    monkeypatch.setattr(tts, "_ENGINES", {})
    monkeypatch.setattr(tts, "_builtins_loaded", False)
    assert set(tts.engines()) == {"edge"}
    assert tts.default_voice() == "edge:en-CA-ClaraNeural"
    monkeypatch.setenv("DEFAULT_VOICE", "edge:en-CA-LiamNeural")
    assert tts.default_voice() == "edge:en-CA-LiamNeural"
