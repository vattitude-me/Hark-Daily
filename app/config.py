"""Runtime configuration, read once from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        with env_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_env_file()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str) -> tuple[str, ...]:
    return tuple(x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip())


@dataclass(frozen=True)
class Config:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", ROOT / "data")))
    model_dir: Path = field(
        default_factory=lambda: Path(os.getenv("MODEL_DIR", Path(os.getenv("DATA_DIR", ROOT / "data")) / "models"))
    )
    timezone: str = os.getenv("BRIEFING_TIMEZONE", "America/Toronto")
    batch_time: str = os.getenv("BATCH_TIME", "07:05")
    keep_days: int = int(os.getenv("KEEP_DAYS", "2"))
    # Off when the phones build their own briefings: the worker then only answers on-demand requests.
    daily_batch: bool = _bool("DAILY_BATCH", True)
    # Supabase: the worker uses the secret key, which bypasses row-level security. Never ship it to the browser.
    supabase_url: str = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_secret_key: str = os.getenv("SUPABASE_SECRET_KEY", "")
    bucket: str = os.getenv("SUPABASE_BUCKET", "briefings")
    # Groq writes the summaries; each model has its own free-tier limits, so we fall through the list.
    groq_api_key: str | None = os.getenv("GROQ_API_KEY") or None
    groq_models: tuple[str, ...] = tuple(
        m.strip() for m in os.getenv("GROQ_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",") if m.strip()
    )
    # Gemini AI Studio support
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None
    gemini_models: tuple[str, ...] = tuple(
        m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-2.5-flash,gemini-1.5-flash").split(",") if m.strip()
    )
    # Optional local / secondary OpenAI-compatible LLM endpoint (e.g. Ollama / vLLM / LM Studio)
    local_llm_url: str | None = os.getenv("LOCAL_LLM_URL") or None
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "llama3.1:8b")
    admin_emails: tuple[str, ...] = _list("ADMIN_EMAILS")
    # "issues" pushes the admin only when a run had problems; "always" after every run.
    admin_notify: str = os.getenv("ADMIN_NOTIFY", "issues").strip().lower()
    vapid_subject: str = os.getenv("VAPID_SUBJECT", "https://hark.vattitude.ca")
    vapid_private_key: str | None = os.getenv("VAPID_PRIVATE_KEY")
    vapid_public_key: str | None = os.getenv("VAPID_PUBLIC_KEY")
    allow_private_urls: bool = _bool("ALLOW_PRIVATE_URLS")
    max_custom_sources: int = int(os.getenv("MAX_CUSTOM_SOURCES", "15"))
    # The Cloned narrator: the LAN/GPU voice service that voices the shared daily stories.
    voice_url: str = os.getenv("VOICE_SERVICE_URL", "").rstrip("/")
    voice_pace: float = float(os.getenv("VOICE_PACE", "0.94"))
    voice_temperature: float = float(os.getenv("VOICE_TEMPERATURE", "0.90"))
    voice_top_p: float = float(os.getenv("VOICE_TOP_P", "0.98"))
    voice_exaggeration: float = float(os.getenv("VOICE_EXAGGERATION", "0.75"))
    story_voice: str = os.getenv("STORY_VOICE", "c3po_reference")
    # Every voice the pack renders each day. A listener hears the one they picked, and the
    # clips are shared, so the cost is stories × voices rather than × listeners.
    story_voices: tuple[str, ...] = tuple(
        v.strip()
        for v in os.getenv("STORY_VOICES", "c3po_reference,matthew_reference,kelly_reference").split(",")
        if v.strip()
    )
    stories_per_section: int = int(os.getenv("STORIES_PER_SECTION", "5"))
    # Podcast mode: two hosts chat around the news. The flag is the kill switch (server side:
    # nothing is generated and the app hides the mode); the hosts are any two voice ids.
    podcast_enabled: bool = _bool("PODCAST_ENABLED", True)
    podcast_hosts: tuple[str, ...] = tuple(
        v.strip()
        for v in os.getenv("PODCAST_HOSTS", "matthew_reference,kelly_reference").split(",")
        if v.strip()
    )[:2]
    # GCE VM automated lifecycle (Chatterbox-Turbo on-demand GPU VM)
    gcp_project: str = os.getenv("GCP_PROJECT", "project-67937e0a-4d2d-43ea-9ba")
    gce_zone: str = os.getenv("GCE_ZONE", "us-central1-c")
    gce_instance: str = os.getenv("GCE_INSTANCE", "morning-brief-voice")
    gce_manage_vm: bool = _bool("GCE_MANAGE_VM", True)
    # Off by default: a session stops the VM on the way out. Set it to keep the GPU warm on purpose.
    gce_keep_vm: bool = _bool("GCE_KEEP_VM")
    gce_health_timeout: float = float(os.getenv("GCE_HEALTH_TIMEOUT", "300.0"))
    gce_start_retries: int = int(os.getenv("GCE_START_RETRIES", "3"))
    gce_start_backoff: float = float(os.getenv("GCE_START_BACKOFF", "60.0"))

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.model_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)


def load() -> Config:
    cfg = Config()
    cfg.ensure_dirs()
    return cfg
