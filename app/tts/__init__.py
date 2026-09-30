"""Text-to-speech engines.

Two neural engines are supported:

* ``kokoro`` – Kokoro-82M (Apache-2.0) via kokoro-onnx. Runs locally on CPU,
  sounds natural and needs no API key. This is the default.
* ``edge``   – Microsoft Edge neural voices via the open-source edge-tts
  client. Needs internet but includes Canadian English voices.
"""
from __future__ import annotations

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


def engines() -> dict[str, Engine]:
    if "kokoro" not in _ENGINES:
        from .edge import EdgeEngine
        from .kokoro import KokoroEngine

        _ENGINES.setdefault("kokoro", KokoroEngine())
        _ENGINES.setdefault("edge", EdgeEngine())
    return _ENGINES


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
