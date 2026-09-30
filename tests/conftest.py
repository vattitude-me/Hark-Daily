from __future__ import annotations

import dataclasses
from pathlib import Path

import httpx
import numpy as np
import pytest

from app import fetcher, tts
from app.config import Config
from app.tts import SAMPLE_RATE, Voice

from . import fakenews

BASE = "https://sample.news"


class ToneEngine:
    """Deterministic stand-in for a neural voice: 0.05 s of tone per word."""

    name = "fake"

    def status(self):
        return True, ""

    def voices(self):
        return [Voice("fake:tone", "fake", "Tone", "Test", "none", "test voice")]

    def synthesize(self, text, voice, speed=1.0):
        n = int(len(text.split()) * 0.05 * SAMPLE_RATE / speed)
        t = np.arange(n) / SAMPLE_RATE
        return (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


@pytest.fixture(autouse=True)
def fake_network(monkeypatch):
    transport = httpx.MockTransport(fakenews.handler(BASE))

    def make_client(timeout: float = 20.0):
        return httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=timeout)

    monkeypatch.setattr(fetcher, "make_client", make_client)
    monkeypatch.setattr("app.weather.forecast", lambda *a, **k: {
        "city": "Toronto", "now": 12, "high": 17, "low": 8, "code": 1, "conditions": "mostly clear skies", "precip": 10,
    })
    tts.register(ToneEngine())
    yield


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    c = dataclasses.replace(
        Config(), data_dir=tmp_path, model_dir=tmp_path / "models", anthropic_api_key=None,
        app_password=None, scheduler_enabled=False,
    )
    c.ensure_dirs()
    return c


def use_sample_sources(db):
    for s in db.list_sources():
        db.update_source(s["id"], enabled=False)
    for key, section in (("canada", "canada"), ("canada2", "canada"), ("tech", "tech")):
        db.add_source(name=fakenews.SOURCE_NAMES[key], url=f"{BASE}/{key}/feed.xml",
                      feed_url=f"{BASE}/{key}/feed.xml", kind="feed", section=section)
    db.update_settings({"voice": "fake:tone"})
