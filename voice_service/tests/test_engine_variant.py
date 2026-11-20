"""Unit tests for Turbo vs standard non-Turbo Chatterbox engine selection."""
from __future__ import annotations

import contextlib
import sys
from types import SimpleNamespace

import numpy as np

from turbo_voice.engine import TurboVoice, normalize_variant


def test_normalize_variant_defaults_to_standard_and_accepts_turbo_aliases(monkeypatch):
    monkeypatch.delenv("CHATTERBOX_VARIANT", raising=False)
    assert normalize_variant() == "standard"
    for alias in ("turbo", "chatterbox-turbo", "chatterbox_turbo"):
        assert normalize_variant(alias) == "turbo"
    for alias in ("standard", "non-turbo", "non_turbo", "nonturbo", "base", "chatterbox"):
        assert normalize_variant(alias) == "standard"


def test_sidecar_paths_isolated_between_turbo_and_standard(tmp_path):
    clip = tmp_path / "matthew_reference.wav"
    clip.write_bytes(b"WAV")

    turbo = TurboVoice(clip, device="cpu", variant="turbo")
    standard = TurboVoice(clip, device="cpu", variant="standard")

    assert turbo._sidecar(clip).name == "matthew_reference.turbo-v1.conds.pt"
    assert standard._sidecar(clip).name == "matthew_reference.standard-v1.conds.pt"
    assert turbo._sidecar(clip) != standard._sidecar(clip)


def test_standard_variant_strips_turbo_tags_and_routes_generate_kwargs(tmp_path, monkeypatch):
    clip = tmp_path / "kelly_reference.wav"
    clip.write_bytes(b"WAV")
    seen_calls: list[tuple[str, dict]] = []

    class FakeWav:
        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return np.zeros((1, 2400), dtype=np.float32)

    class FakeModel:
        def __init__(self):
            self.t3 = SimpleNamespace(hp=SimpleNamespace(emotion_adv=False))
            self.conds = None

        def generate(self, text, **kwargs):
            seen_calls.append((text, kwargs))
            return FakeWav()

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=contextlib.nullcontext))
    monkeypatch.setattr("turbo_voice.engine._adjust_pace", lambda arr, pace, sr: arr)

    voice = TurboVoice(clip, device="cpu", variant="standard", cache_conds=False)
    voice._model = FakeModel()
    voice._prepared = (str(clip), clip.stat().st_mtime_ns)

    out = voice.say("Well, [chuckle] that escalated fast [sigh].", reference=clip, cfg_weight=0.45, exaggeration=0.6)
    assert isinstance(out, np.ndarray)
    assert len(seen_calls) == 1
    spoken, kwargs = seen_calls[0]
    assert "[chuckle]" not in spoken
    assert "[sigh]" not in spoken
    assert "Well, that escalated fast ." in spoken or "Well, that escalated fast." in spoken
    assert "top_k" not in kwargs
    assert kwargs["cfg_weight"] == 0.45
    assert kwargs["exaggeration"] == 0.6

    audio, marks = voice.render("Hello world.", reference=clip, cfg_weight=0.33, exaggeration=0.50)
    assert isinstance(audio, np.ndarray)
    assert len(marks) == 1
    assert seen_calls[-1][1]["cfg_weight"] == 0.33
    assert seen_calls[-1][1]["exaggeration"] == 0.50
