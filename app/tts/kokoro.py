"""Kokoro-82M neural TTS (https://github.com/thewh1teagle/kokoro-onnx)."""
from __future__ import annotations

import logging
import os
import threading
import urllib.request
from pathlib import Path

import numpy as np

from . import SAMPLE_RATE, Voice

log = logging.getLogger(__name__)
logging.getLogger("phonemizer").setLevel(logging.ERROR)  # noisy per-sentence word-count warnings

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = {"kokoro-v1.0.onnx": 325_532_387, "voices-v1.0.bin": 28_214_398}

VOICES = [
    Voice("kokoro:af_heart", "kokoro", "Heart", "American", "female", "Warm and natural, the best all-rounder", True),
    Voice("kokoro:af_bella", "kokoro", "Bella", "American", "female", "Bright, upbeat, energetic"),
    Voice("kokoro:am_michael", "kokoro", "Michael", "American", "male", "Calm, steady newsreader"),
    Voice("kokoro:am_fenrir", "kokoro", "Fenrir", "American", "male", "Deep and confident"),
    Voice("kokoro:am_puck", "kokoro", "Puck", "American", "male", "Friendly, conversational"),
    Voice("kokoro:bf_emma", "kokoro", "Emma", "British", "female", "Polished, BBC-style delivery"),
    Voice("kokoro:bm_george", "kokoro", "George", "British", "male", "Classic, authoritative"),
]


def model_dir() -> Path:
    from ..config import load

    return load().model_dir


def download_models(target: Path | None = None, progress=None) -> None:
    target = target or model_dir()
    target.mkdir(parents=True, exist_ok=True)
    for name, size in FILES.items():
        dest = target / name
        if dest.exists() and dest.stat().st_size == size:
            continue
        log.info("Downloading %s (%.0f MB)…", name, size / 1e6)
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(f"{RELEASE}/{name}", timeout=60) as resp, open(tmp, "wb") as fh:
            done = 0
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(name, done, size)
        tmp.replace(dest)


class KokoroEngine:
    name = "kokoro"

    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()

    def _paths(self) -> tuple[Path, Path]:
        d = model_dir()
        return d / "kokoro-v1.0.onnx", d / "voices-v1.0.bin"

    def status(self) -> tuple[bool, str]:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False, "kokoro-onnx is not installed"
        model, voices = self._paths()
        if model.exists() and voices.exists():
            return True, ""
        return True, "Voice model (~350 MB) downloads on first use"

    def voices(self) -> list[Voice]:
        return VOICES

    def _load(self):
        if self._model is None:
            from kokoro_onnx import Kokoro

            model, voices = self._paths()
            if not (model.exists() and voices.exists()):
                download_models(model.parent)
            os.environ.setdefault("ONNX_PROVIDER", "CPUExecutionProvider")
            self._model = Kokoro(str(model), str(voices))
        return self._model

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> np.ndarray:
        lang = "en-gb" if voice.startswith("b") else "en-us"
        with self._lock:
            samples, sr = self._load().create(text, voice=voice, speed=float(speed), lang=lang)
        samples = np.asarray(samples, dtype=np.float32)
        if sr != SAMPLE_RATE:
            from ..audio import resample

            samples = resample(samples, sr, SAMPLE_RATE)
        return samples
