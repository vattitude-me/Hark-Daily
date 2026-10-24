from __future__ import annotations

import dataclasses
import time
import httpx
import pytest

from app import cbc, gce, push, storypack
from app.errors import DeadlineReached, PackBusy, PackIncomplete, VoiceServiceDown


def test_load_keys_from_config(cfg):
    custom_cfg = dataclasses.replace(cfg, vapid_private_key="PRIV_KEY_VAL", vapid_public_key="PUB_KEY_VAL")
    keys = push.load_keys(custom_cfg)
    assert keys["private_pem"] == "PRIV_KEY_VAL"
    assert keys["public_key"] == "PUB_KEY_VAL"


def test_synthesise_raises_voice_service_down_on_connection_error():
    async def run():
        transport = httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("refused", request=req)))
        async with httpx.AsyncClient(transport=transport) as client:
            await storypack.synthesise(client, "http://offline.local:8090", "hello", "her_reference", attempts=1)

    with pytest.raises(VoiceServiceDown):
        import asyncio
        asyncio.run(run())


def test_synthesise_raises_runtime_error_on_400():
    async def run():
        transport = httpx.MockTransport(lambda req: httpx.Response(400, text="Bad voice"))
        async with httpx.AsyncClient(transport=transport) as client:
            await storypack.synthesise(client, "http://voice.local:8090", "hello", "unknown_voice", attempts=1)

    with pytest.raises(RuntimeError, match="voice service 400"):
        import asyncio
        asyncio.run(run())


def test_pack_lease_blocks_concurrent_runs(store):
    with storypack.pack_lease(store, holder="run_one"):
        with pytest.raises(PackBusy, match="another pack run is using the GPU"):
            with storypack.pack_lease(store, holder="run_two"):
                pass


def test_build_narrator_isolation(cfg, store, monkeypatch):
    """If one voice fails, other voices still finish, and PackIncomplete is raised with published rows."""
    script = {"id": "1", "section": "top", "rank": 1, "title": "Headline",
              "source": "News", "url": "https://example.com/1", "script": "Story text."}

    async def fake_pack(per_section=5, sections=None, max_words=60):
        return [script]

    async def fake_synthesise(client, base, text, voice, *args, **kwargs):
        if voice == "her_reference":
            raise RuntimeError("Corrupt audio file")
        return b"mp3_data", 5.0

    monkeypatch.setattr(cbc, "build_pack", fake_pack)
    monkeypatch.setattr(storypack, "synthesise", fake_synthesise)

    cfg2 = dataclasses.replace(cfg, story_voices=("her_reference", "him_reference"), voice_url="http://test.voice")
    import asyncio
    with pytest.raises(PackIncomplete) as exc:
        asyncio.run(storypack.build(cfg2, store, day="2026-10-18", notes=False))

    assert "Alice" in exc.value.failed
    assert "Corrupt audio file" in exc.value.failed["Alice"]
    # Him (Mike) should have succeeded and published
    assert len(exc.value.rows) == 1
    assert exc.value.rows[0]["voice"] == "him_reference"


def test_build_reraises_voice_service_down_immediately(cfg, store, monkeypatch):
    """If the voice service is down, it halts immediately without trying other voices."""
    script = {"id": "1", "section": "top", "rank": 1, "title": "Headline",
              "source": "News", "url": "https://example.com/1", "script": "Story text."}

    async def fake_pack(per_section=5, sections=None, max_words=60):
        return [script]

    calls = []

    async def fake_synthesise(client, base, text, voice, *args, **kwargs):
        calls.append(voice)
        raise VoiceServiceDown("TTS service died")

    monkeypatch.setattr(cbc, "build_pack", fake_pack)
    monkeypatch.setattr(storypack, "synthesise", fake_synthesise)

    cfg2 = dataclasses.replace(cfg, story_voices=("her_reference", "him_reference"), voice_url="http://test.voice")
    import asyncio
    with pytest.raises(VoiceServiceDown):
        asyncio.run(storypack.build(cfg2, store, day="2026-10-18", notes=False))

    # Halts after first voice down: does not proceed to second voice
    assert len(calls) == 1


def test_deadline_stops_synthesis(cfg, store, monkeypatch):
    script = {"id": "1", "section": "top", "rank": 1, "title": "Headline",
              "source": "News", "url": "https://example.com/1", "script": "Story text."}

    async def fake_pack(per_section=5, sections=None, max_words=60):
        return [script]

    monkeypatch.setattr(cbc, "build_pack", fake_pack)
    # Deadline already in the past
    deadline = time.monotonic() - 10.0

    cfg2 = dataclasses.replace(cfg, story_voices=("her_reference",), voice_url="http://test.voice")
    import asyncio
    with pytest.raises(PackIncomplete) as exc:
        asyncio.run(storypack.build(cfg2, store, day="2026-10-18", deadline=deadline, notes=False))

    assert "ran out of time" in exc.value.failed["Alice"]


def test_voice_vm_session_stops_vm_on_exit_even_if_already_running(cfg, monkeypatch):
    stopped = []
    monkeypatch.setattr(gce, "get_instance_ip", lambda proj, zone, inst, tok: "10.0.0.1")
    monkeypatch.setattr(gce, "is_service_healthy", lambda url: True)
    monkeypatch.setattr(gce, "get_access_token", lambda: "mock_tok")
    monkeypatch.setattr(gce, "stop_vm_verified", lambda proj, zone, inst, tok: stopped.append(inst) or True)

    cfg_gce = dataclasses.replace(cfg, gce_manage_vm=True, voice_url="auto")
    with gce.voice_vm_session(cfg_gce) as url:
        assert url == "http://10.0.0.1:8090"

    assert stopped == [cfg_gce.gce_instance]


def test_voice_vm_session_fails_fast_when_instance_not_found(cfg, monkeypatch):
    monkeypatch.setattr(gce, "get_access_token", lambda: "mock_tok")
    monkeypatch.setattr(gce, "instance_status", lambda proj, zone, inst, tok: "NOT_FOUND")

    cfg_gce = dataclasses.replace(cfg, gce_manage_vm=True, voice_url="auto")
    with pytest.raises(VoiceServiceDown) as exc:
        with gce.voice_vm_session(cfg_gce):
            pass

    assert "HTTP 404" in str(exc.value)
    assert cfg_gce.gce_instance in str(exc.value)


def test_voice_vm_session_fails_fast_when_permission_denied(cfg, monkeypatch):
    monkeypatch.setattr(gce, "get_access_token", lambda: "mock_tok")
    monkeypatch.setattr(gce, "instance_status", lambda proj, zone, inst, tok: "FORBIDDEN")

    cfg_gce = dataclasses.replace(cfg, gce_manage_vm=True, voice_url="auto")
    with pytest.raises(VoiceServiceDown) as exc:
        with gce.voice_vm_session(cfg_gce):
            pass

    assert "HTTP 403" in str(exc.value)


def test_start_vm_raises_voice_service_down_on_404(monkeypatch):
    class FakeResponse:
        status_code = 404
        text = "Not Found"

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(VoiceServiceDown) as exc:
        gce.start_vm("proj", "zone", "vm-voice", "tok")

    assert "HTTP 404" in str(exc.value)


def test_start_vm_raises_voice_service_down_on_403(monkeypatch):
    class FakeResponse:
        status_code = 403
        text = "Forbidden"

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(VoiceServiceDown) as exc:
        gce.start_vm("proj", "zone", "vm-voice", "tok")

    assert "HTTP 403" in str(exc.value)


def test_stop_vm_verified_handles_deleted_vm_immediately(monkeypatch):
    calls = []
    monkeypatch.setattr(gce, "instance_status", lambda proj, zone, inst, tok: calls.append("check") or "NOT_FOUND")
    monkeypatch.setattr(gce, "stop_vm", lambda proj, zone, inst, tok: calls.append("stop") or True)

    ok = gce.stop_vm_verified("proj", "zone", "vm-voice", "tok")
    assert ok is True
    assert calls == ["check"]  # Stop was not even called because instance is already gone


def test_storypack_build_raises_voice_service_down_when_url_missing(cfg, store):
    cfg2 = dataclasses.replace(cfg, voice_url="")
    with pytest.raises(VoiceServiceDown) as exc:
        import asyncio
        asyncio.run(storypack.build(cfg2, store, day="2026-10-24"))
    assert "VOICE_SERVICE_URL is not set" in str(exc.value)

