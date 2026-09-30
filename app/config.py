"""Runtime configuration, read once from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", ROOT / "data")))
    model_dir: Path = field(
        default_factory=lambda: Path(os.getenv("MODEL_DIR", Path(os.getenv("DATA_DIR", ROOT / "data")) / "models"))
    )
    web_dir: Path = ROOT / "web"
    timezone: str = os.getenv("BRIEFING_TIMEZONE", "America/Toronto")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
    app_password: str | None = os.getenv("APP_PASSWORD") or None
    allow_private_urls: bool = _bool("ALLOW_PRIVATE_URLS")
    scheduler_enabled: bool = _bool("SCHEDULER_ENABLED", True)
    keep_days: int = int(os.getenv("KEEP_DAYS", "14"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "news.db"

    @property
    def briefings_dir(self) -> Path:
        return self.data_dir / "briefings"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.model_dir, self.briefings_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)


def load() -> Config:
    cfg = Config()
    cfg.ensure_dirs()
    return cfg
