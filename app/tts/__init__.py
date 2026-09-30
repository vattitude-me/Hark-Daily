"""Text-to-speech engines.

Two neural engines are supported:

* ``kokoro`` – Kokoro-82M (Apache-2.0) via kokoro-onnx. Runs locally on CPU,
  sounds natural and needs no API key. This is the default.
* ``edge``   – Microsoft Edge neural voices via the open-source edge-tts
  client. Needs internet but includes Canadian English voices.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np

SAMPLE_RATE = 24_000


@dataclass(frozen=True)
class Voice:
    id: str           # "<engine>:<voice>"
    engine: str
    name: str
    accent: str
    gender: str
    description: str
    recommended: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class Engine(Protocol):
    name: str

    def status(self) -> tuple[bool, str]: ...
    def voices(self) -> list[Voice]: ...
    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> np.ndarray: ...


_ENGINES: dict[str, Engine] = {}


def register(engine: Engine) -> None:
    _ENGINES[engine.name] = engine


def enabled_engines() -> list[str]:
    """TTS_ENGINES=edge skips Kokoro entirely, for hosts with under ~1.5 GB of RAM."""
    return [e.strip() for e in os.getenv("TTS_ENGINES", "kokoro,edge").split(",") if e.strip()]


_builtins_loaded = False


def engines() -> dict[str, Engine]:
    global _builtins_loaded
    if not _builtins_loaded:
        from .edge import EdgeEngine
        from .kokoro import KokoroEngine

        wanted = enabled_engines()
        for engine in (KokoroEngine(), EdgeEngine()):
            if engine.name in wanted:
                _ENGINES.setdefault(engine.name, engine)
        _builtins_loaded = True
    return _ENGINES


def default_voice() -> str:
    configured = os.getenv("DEFAULT_VOICE")
    if configured:
        try:
            resolve(configured)
            return configured
        except ValueError:
            pass
    for engine in engines().values():
        voices = engine.voices()
        if voices:
            return next((v.id for v in voices if v.recommended), voices[0].id)
    raise RuntimeError("No text-to-speech engine is enabled (check TTS_ENGINES)")


def all_voices() -> list[dict]:
    out = []
    for engine in engines().values():
        ok, note = engine.status()
        for v in engine.voices():
            out.append({**v.to_dict(), "available": ok, "note": note})
    return out


def resolve(voice_id: str) -> tuple[Engine, str]:
    engine_name, _, voice = voice_id.partition(":")
    engine = engines().get(engine_name)
    if engine is None or not voice:
        raise ValueError(f"Unknown voice '{voice_id}'")
    if voice not in {v.id.partition(':')[2] for v in engine.voices()}:
        raise ValueError(f"Unknown voice '{voice_id}'")
    return engine, voice


def synthesize(voice_id: str, text: str, speed: float = 1.0) -> np.ndarray:
    from .text import speakable

    engine, voice = resolve(voice_id)
    return engine.synthesize(speakable(text), voice, speed)
