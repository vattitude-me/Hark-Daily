"""FastAPI app: JSON API, audio files and the web UI."""
from __future__ import annotations

import base64
import hashlib
import logging
import re
import secrets
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import audio, tts
from .briefing import list_briefings, load_briefing
from .config import Config, load
from .db import Database
from .fetcher import FetchError, detect, normalize_url
from .jobs import BriefingJobs
from .sources import SECTIONS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("news")

PREVIEW_TEXT = (
    "Good morning! This is how your daily briefing will sound. "
    "Here's a quick look at the top stories from across Canada, and the latest in AI and tech."
)


class SourceIn(BaseModel):
    url: str = Field(min_length=4, max_length=2000)
    section: Literal["canada", "tech", "custom"] = "custom"
    name: str | None = Field(default=None, max_length=120)


class DetectIn(BaseModel):
    url: str = Field(min_length=4, max_length=2000)


class SourcePatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    section: Literal["canada", "tech", "custom"] | None = None
    enabled: bool | None = None


class SettingsIn(BaseModel):
    voice: str | None = None
    speed: float | None = Field(default=None, ge=0.7, le=1.4)
    briefing_time: str | None = None
    auto_generate: bool | None = None
    stories: dict[str, int] | None = None
    city: str | None = Field(default=None, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    weather: bool | None = None

    @field_validator("briefing_time")
    @classmethod
    def _time(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("Use HH:MM (24-hour)")
        return v

    @field_validator("stories")
    @classmethod
    def _stories(cls, v: dict[str, int] | None) -> dict[str, int] | None:
        if v is None:
            return v
        return {k: max(0, min(int(n), 12)) for k, n in v.items() if k in SECTIONS}

    @field_validator("voice")
    @classmethod
    def _voice(cls, v: str | None) -> str | None:
        if v is not None:
            tts.resolve(v)  # raises ValueError for unknown voices
        return v


def create_app(cfg: Config | None = None, *, start_scheduler: bool | None = None) -> FastAPI:
    cfg = cfg or load()
    db = Database(cfg.db_path)
    jobs = BriefingJobs(cfg, db)
    run_scheduler = cfg.scheduler_enabled if start_scheduler is None else start_scheduler

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if run_scheduler:
            jobs.start_scheduler()
        yield
        jobs.stop_scheduler()

    app = FastAPI(title="News Extractor · Morning Brief", lifespan=lifespan)
    app.state.cfg, app.state.db, app.state.jobs = cfg, db, jobs

    if cfg.app_password:
        expected = cfg.app_password.encode()

        @app.middleware("http")
        async def basic_auth(request: Request, call_next):
            header = request.headers.get("authorization", "")
            if header.lower().startswith("basic "):
                try:
                    _, _, pw = base64.b64decode(header[6:]).decode().partition(":")
                    if secrets.compare_digest(pw.encode(), expected):
                        return await call_next(request)
                except Exception:  # noqa: BLE001 - malformed header
                    pass
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Morning Brief"'})

    # ---------------------------------------------------------------- briefing
    @app.get("/api/briefing/latest")
    def latest():
        data = load_briefing(cfg)
        if not data:
            return JSONResponse({"briefing": None}, status_code=200)
        return {"briefing": data}

    @app.get("/api/briefing/{day}")
    def by_day(day: str):
        data = load_briefing(cfg, day)
        if not data:
            raise HTTPException(404, "No briefing for that day")
        return {"briefing": data}

    @app.get("/api/briefings")
    def archive():
        return {"briefings": list_briefings(cfg)}

    @app.post("/api/briefing/generate", status_code=202)
    def generate():
        started = jobs.start("manual")
        return {"started": started, "status": jobs.state()}

    @app.get("/api/status")
    def status():
        return {
            **jobs.state(),
            "writer": "claude" if cfg.anthropic_api_key else "built-in",
            "timezone": cfg.timezone,
        }

    # ----------------------------------------------------------------- sources
    @app.get("/api/sources")
    def sources():
        return {"sources": db.list_sources(), "sections": SECTIONS}

    @app.post("/api/sources/detect")
    async def detect_source(body: DetectIn):
        try:
            d = await detect(body.url, allow_private=cfg.allow_private_urls)
        except FetchError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"kind": d.kind, "url": d.url, "feed_url": d.feed_url, "name": d.name, "sample": d.sample,
                "exists": db.source_exists(d.url) or bool(d.feed_url and db.source_exists(d.feed_url))}

    @app.post("/api/sources", status_code=201)
    async def add_source(body: SourceIn):
        url = normalize_url(body.url)
        if db.source_exists(url):
            raise HTTPException(409, "You're already following that link.")
        try:
            d = await detect(url, allow_private=cfg.allow_private_urls)
        except FetchError as exc:
            raise HTTPException(422, str(exc)) from exc
        if d.feed_url and db.source_exists(d.feed_url):
            raise HTTPException(409, "You're already following that feed.")
        src = db.add_source(name=(body.name or d.name or url)[:120], url=d.url, feed_url=d.feed_url,
                            kind=d.kind, section=body.section)
        return {"source": src}

    @app.patch("/api/sources/{source_id}")
    def patch_source(source_id: int, body: SourcePatch):
        src = db.update_source(source_id, **body.model_dump(exclude_none=True))
        if not src:
            raise HTTPException(404, "Source not found")
        return {"source": src}

    @app.delete("/api/sources/{source_id}", status_code=204)
    def delete_source(source_id: int):
        src = db.get_source(source_id)
        if not src:
            raise HTTPException(404, "Source not found")
        if src["builtin"]:
            raise HTTPException(400, "Built-in sources can be switched off but not deleted.")
        db.delete_source(source_id)
        return Response(status_code=204)

    # ---------------------------------------------------------- voices/settings
    @app.get("/api/voices")
    def voices():
        return {"voices": tts.all_voices()}

    @app.get("/api/voices/preview")
    def voice_preview(voice: str = Query(...), speed: float = Query(1.0, ge=0.7, le=1.4)):
        try:
            tts.resolve(voice)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        key = hashlib.sha1(f"{voice}|{speed:.2f}|{PREVIEW_TEXT}".encode()).hexdigest()[:16]
        path = cfg.cache_dir / f"preview-{key}.mp3"
        if not path.exists():
            try:
                pcm, _ = audio.assemble([("p", tts.synthesize(voice, PREVIEW_TEXT, speed), 0.2)])
            except Exception as exc:  # noqa: BLE001
                log.warning("Voice preview failed for %s: %s", voice, exc)
                raise HTTPException(503, "That voice isn't available right now.") from exc
            path.write_bytes(audio.encode_mp3(pcm))
        return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/api/settings")
    def get_settings():
        return {"settings": db.get_settings()}

    @app.put("/api/settings")
    def put_settings(body: SettingsIn):
        values = body.model_dump(exclude_none=True)
        if "stories" in values:
            values["stories"] = {**db.get_settings()["stories"], **values["stories"]}
        settings = db.update_settings(values)
        jobs.reschedule()
        return {"settings": settings, "next_run": jobs.next_run()}

    # ------------------------------------------------------------------ static
    app.mount("/media", StaticFiles(directory=cfg.briefings_dir), name="media")
    app.mount("/", StaticFiles(directory=cfg.web_dir, html=True), name="web")
    return app


def factory() -> FastAPI:
    return create_app()
