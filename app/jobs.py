"""Background briefing builds and the daily morning schedule."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .briefing import BriefingError, build_briefing, load_briefing
from .config import Config
from .db import Database

log = logging.getLogger(__name__)


class BriefingJobs:
    def __init__(self, cfg: Config, db: Database):
        self.cfg = cfg
        self.db = db
        self._lock = threading.Lock()
        self._state = {"running": False, "step": None, "progress": 0.0, "error": None,
                       "started_at": None, "finished_at": None, "trigger": None}
        self.scheduler: BackgroundScheduler | None = None

    # ------------------------------------------------------------------ builds
    def state(self) -> dict:
        with self._lock:
            out = dict(self._state)
        out["next_run"] = self.next_run()
        return out

    def _progress(self, step: str, fraction: float) -> None:
        with self._lock:
            self._state.update(step=step, progress=round(fraction, 3))

    def start(self, trigger: str = "manual") -> bool:
        with self._lock:
            if self._state["running"]:
                return False
            self._state.update(running=True, step="Starting", progress=0.0, error=None, trigger=trigger,
                               started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        threading.Thread(target=self._run, name="briefing-build", daemon=True).start()
        return True

    def _run(self) -> None:
        error = None
        try:
            build_briefing(self.cfg, self.db, self._progress)
        except BriefingError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - surface anything unexpected to the UI
            log.exception("Briefing build failed")
            error = f"Something went wrong while building the briefing ({exc.__class__.__name__})."
        with self._lock:
            self._state.update(running=False, error=error,
                               finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    # --------------------------------------------------------------- schedule
    def start_scheduler(self) -> None:
        self.scheduler = BackgroundScheduler(timezone=ZoneInfo(self.cfg.timezone))
        self.scheduler.start()
        self.reschedule()
        self._catch_up()

    def stop_scheduler(self) -> None:
        if self.scheduler:
            self.scheduler.shutdown(wait=False)

    def reschedule(self) -> None:
        if not self.scheduler:
            return
        settings = self.db.get_settings()
        if self.scheduler.get_job("daily"):
            self.scheduler.remove_job("daily")
        if not settings.get("auto_generate", True):
            return
        hour, minute = (int(x) for x in settings["briefing_time"].split(":"))
        self.scheduler.add_job(
            lambda: self.start("schedule"),
            CronTrigger(hour=hour, minute=minute, timezone=ZoneInfo(self.cfg.timezone)),
            id="daily", misfire_grace_time=3600, coalesce=True,
        )

    def _catch_up(self) -> None:
        """If the server was asleep at briefing time, build today's briefing now."""
        settings = self.db.get_settings()
        if not settings.get("auto_generate", True):
            return
        now = datetime.now(ZoneInfo(self.cfg.timezone))
        hour, minute = (int(x) for x in settings["briefing_time"].split(":"))
        latest = load_briefing(self.cfg)
        if (now.hour, now.minute) >= (hour, minute) and (not latest or latest["date"] != now.date().isoformat()):
            self.start("catch-up")

    def next_run(self) -> str | None:
        job = self.scheduler.get_job("daily") if self.scheduler else None
        return job.next_run_time.isoformat() if job and job.next_run_time else None
