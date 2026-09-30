"""Microsoft Edge neural voices through the open-source edge-tts client."""
from __future__ import annotations

import asyncio

import numpy as np

from . import SAMPLE_RATE, Voice

VOICES = [
    Voice("edge:en-CA-ClaraNeural", "edge", "Clara", "Canadian", "female", "Canadian English, clear and friendly", True),
    Voice("edge:en-CA-LiamNeural", "edge", "Liam", "Canadian", "male", "Canadian English, relaxed and warm"),
    Voice("edge:en-US-AvaMultilingualNeural", "edge", "Ava", "American", "female", "Expressive, very lifelike"),
    Voice("edge:en-US-AndrewMultilingualNeural", "edge", "Andrew", "American", "male", "Natural, podcast-style"),
    Voice("edge:en-GB-SoniaNeural", "edge", "Sonia", "British", "female", "Crisp British newsreader"),
]


class EdgeEngine:
    name = "edge"

    def status(self) -> tuple[bool, str]:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False, "edge-tts is not installed"
        return True, "Streams from Microsoft's speech service (needs internet)"

    def voices(self) -> list[Voice]:
        return VOICES

    async def _mp3(self, text: str, voice: str, speed: float) -> bytes:
        import edge_tts

        rate = f"{round((speed - 1) * 100):+d}%"
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
        if not audio:
            raise RuntimeError("edge-tts returned no audio")
        return bytes(audio)

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> np.ndarray:
        import miniaudio

        mp3 = asyncio.run(self._mp3(text, voice, speed))
        decoded = miniaudio.decode(
            mp3, output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1, sample_rate=SAMPLE_RATE
        )
        return np.asarray(decoded.samples, dtype=np.float32)
