"""Stitch voice segments into one MP3 with chapter timestamps."""
from __future__ import annotations

import numpy as np

from .tts import SAMPLE_RATE


def silence(seconds: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    return np.zeros(int(seconds * sr), dtype=np.float32)


def resample(samples: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or samples.size == 0:
        return samples
    n = int(round(samples.size * dst / src))
    x_old = np.linspace(0, 1, samples.size, endpoint=False)
    x_new = np.linspace(0, 1, n, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def trim_silence(samples: np.ndarray, threshold: float = 0.004, pad: float = 0.05, sr: int = SAMPLE_RATE) -> np.ndarray:
    loud = np.flatnonzero(np.abs(samples) > threshold)
    if loud.size == 0:
        return samples
    start = max(loud[0] - int(pad * sr), 0)
    end = min(loud[-1] + int(pad * sr), samples.size)
    return samples[start:end]


def level(samples: np.ndarray, target_rms: float = 0.085) -> np.ndarray:
    """Even out loudness between segments, with a soft limiter so peaks never clip."""
    rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
    if rms > 1e-5:
        samples = samples * (target_rms / rms)
    return np.tanh(samples * 1.2) / np.tanh(1.2)


def fade(samples: np.ndarray, ms: float = 12, sr: int = SAMPLE_RATE) -> np.ndarray:
    n = min(int(sr * ms / 1000), samples.size // 2)
    if n:
        ramp = np.linspace(0, 1, n, dtype=np.float32)
        samples = samples.copy()
        samples[:n] *= ramp
        samples[-n:] *= ramp[::-1]
    return samples


def assemble(segments: list[tuple[str, np.ndarray, float]], sr: int = SAMPLE_RATE) -> tuple[np.ndarray, dict[str, tuple[float, float]]]:
    """Join (key, samples, pause_after) segments; return audio and key -> (start, end) seconds."""
    parts: list[np.ndarray] = [silence(0.35, sr)]
    cursor = parts[0].size
    marks: dict[str, tuple[float, float]] = {}
    for key, samples, pause in segments:
        clip = fade(level(trim_silence(samples, sr=sr)), sr=sr).astype(np.float32)
        start = cursor / sr
        parts.append(clip)
        cursor += clip.size
        marks[key] = (round(start, 2), round(cursor / sr, 2))
        gap = silence(pause, sr)
        parts.append(gap)
        cursor += gap.size
    return np.concatenate(parts), marks


def encode_mp3(samples: np.ndarray, sr: int = SAMPLE_RATE, bitrate: int = 96) -> bytes:
    import lameenc

    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(bitrate)
    enc.set_in_sample_rate(sr)
    enc.set_channels(1)
    enc.set_quality(2)
    return bytes(enc.encode(pcm) + enc.flush())
