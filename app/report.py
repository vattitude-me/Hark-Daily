"""What happened during a batch run, in words users and the admin can act on.

Every known failure mode has a code and a plain-language message. Users see the
messages that affect them (in the app, above their briefing); the admin gets a
push notification with the run summary and the technical detail.
"""
from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Codes only the admin needs to act on; users aren't shown these.
ADMIN_ONLY = {"ai_model_gone", "showcase_failed"}

MESSAGES = {
    # Groq / AI summaries
    "ai_rate_limited": "The AI summary service was busy, so today's briefing took a little longer to build.",
    "ai_daily_limit": ("The AI summary service hit its free daily limit, so some summaries were written by the "
                       "built-in summarizer instead. They're shorter and plainer. The limit resets within 24 hours."),
    "ai_auth": ("The AI summary service rejected our access key, so the built-in summarizer wrote today's summaries. "
                "The admin has been notified."),
    "ai_unavailable": ("The AI summary service couldn't be reached, so some summaries were written by the "
                       "built-in summarizer."),
    "ai_off": "AI summaries are switched off, so the built-in summarizer wrote today's summaries.",
    "showcase_failed": "Admin: the demo on the landing page couldn't be updated.",
    "ai_model_gone": "Admin: a configured Groq model is no longer available. Update GROQ_MODELS on the server.",
    # News and links
    "sources_failed": "Some of your links couldn't be read this morning. Check Sources for details.",
    "no_sources": "Nothing to build from: switch on at least one source.",
    "no_stories": "No fresh stories were found in the last two days, so no briefing was built.",
    # Voice, storage, overall
    "tts_fallback": "The main voice had a problem, so part of today's audio uses a backup voice.",
    "storage_failed": "Today's audio couldn't be saved (the storage space may be full). The admin has been notified.",
    "build_failed": "Today's briefing couldn't be built. The admin has been notified.",
    "supabase_down": "The app's database couldn't be reached, so no briefings were built.",
}


@dataclass
class Issue:
    code: str
    level: str               # info | warn | error
    message: str             # for users
    detail: str = ""         # for the admin
    user_id: str | None = None   # None = affects everyone in this run


@dataclass
class RunReport:
    trigger: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    finished_at: str | None = None
    issues: list[Issue] = field(default_factory=list)
    built: list[str] = field(default_factory=list)        # emails
    failed: list[str] = field(default_factory=list)       # emails
    writers: Counter = field(default_factory=Counter)     # model name or "built-in" -> stories written
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, code: str, detail: str = "", *, level: str = "warn", user_id: str | None = None) -> None:
        with self._lock:
            if any(i.code == code and i.user_id == user_id for i in self.issues):
                return
            self.issues.append(Issue(code, level, MESSAGES.get(code, code), detail, user_id))

    def for_user(self, user_id: str) -> list[dict]:
        """Notes shown to one user: run-wide issues plus their own."""
        return [{"code": i.code, "level": i.level, "message": i.message}
                for i in self.issues
                if i.user_id in (None, user_id) and i.level != "info" and i.code not in ADMIN_ONLY]

    @property
    def ok(self) -> bool:
        return not self.failed and not any(i.level == "error" for i in self.issues)

    def summary(self) -> str:
        parts = [f"{len(self.built)} built"]
        if self.failed:
            parts.append(f"{len(self.failed)} failed ({', '.join(self.failed)})")
        if self.writers:
            parts.append("summaries: " + ", ".join(f"{k} {v}" for k, v in self.writers.most_common()))
        return " · ".join(parts)

    def admin_detail(self) -> str:
        seen, lines = set(), []
        for i in self.issues:
            if i.code in seen:
                continue
            seen.add(i.code)
            lines.append(f"{i.code}: {i.detail or i.message}")
        return "; ".join(lines)

    def to_dict(self) -> dict:
        return {
            "trigger": self.trigger, "started_at": self.started_at, "finished_at": self.finished_at,
            "ok": self.ok, "built": len(self.built), "failed": len(self.failed), "summary": self.summary(),
            "issues": [{"code": i.code, "level": i.level, "message": i.message}
                       for i in self.issues if i.user_id is None],
        }
