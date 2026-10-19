"""Failures the pack pipeline tells apart, because each one calls for a different response."""
from __future__ import annotations


class VoiceServiceDown(RuntimeError):
    """The GPU voice service can't be reached. Every other clip would fail the same way, so stop."""


class DeadlineReached(RuntimeError):
    """The run's time budget is spent. Stop cleanly before the platform kills the job."""


class PackBusy(RuntimeError):
    """Another pack run holds the GPU. Two at once only slow each other down and double the bill."""


class PackIncomplete(RuntimeError):
    """Some narrators did not finish. The others are published; `failed` says why, voice by voice."""

    def __init__(self, failed: dict[str, str], rows: list[dict] | None = None):
        self.failed = failed
        self.rows = rows or []
        super().__init__("; ".join(f"{voice}: {why}" for voice, why in failed.items()))
