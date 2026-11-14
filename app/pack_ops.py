"""Pack lifecycle operations: voice catalog helpers, readiness markers, pruning, push notifications, and leases."""
from __future__ import annotations

import contextlib
import logging
import os
import platform
from datetime import datetime

from . import push, store as store_mod
from .errors import PackBusy
from .store import StoreError

log = logging.getLogger(__name__)

STATIC_DATE = "2000-01-01"
PACK_READY = "pack_ready"

VOICES: dict[str, dict[str, str]] = {
    "matthew_reference+kelly_reference": {"name": "Matthew & Kelly", "gender": "duo"},
    "c3po_reference": {"name": "C-3PO", "gender": "male"},
    "matthew_reference": {"name": "Matthew", "gender": "male"},
    "kelly_reference": {"name": "Kelly", "gender": "female"},
    "matthew_american": {"name": "Matthew", "gender": "male"},
    "kelly": {"name": "Kelly", "gender": "female"},
    "kelley_reference": {"name": "Kelly", "gender": "female"},
    # Legacy narrator IDs preserved for historical packs and test suites
    "her_reference": {"name": "Alice", "gender": "female"},
    "him_reference": {"name": "Mike", "gender": "male"},
    "jerry_reference": {"name": "Jerry", "gender": "male"},
}
DEFAULT_VOICE = "c3po_reference"


def voice_slug(voice: str) -> str:
    """Storage-safe voice identifier (replaces '+' duo separator with '__')."""
    return voice.replace("+", "__")


def voice_name(voice: str | None) -> str:
    """Human-readable narrator label, e.g. 'Matthew & Kelly' or 'C-3PO'."""
    if not voice:
        return "the narrator"
    if voice in VOICES:
        return VOICES[voice]["name"]
    if "+" in voice:
        return " & ".join(voice_name(part) for part in voice.split("+") if part.strip())
    clean = (
        voice.replace("_reference", "")
        .replace("_american", "")
        .replace("_male", "")
        .replace("_female", "")
        .replace("_", " ")
        .strip()
        .title()
    )
    return clean or voice


def ready(store, *, day: str, voice: str) -> bool:
    """Whether every clip and note for this narrator's day is published."""
    return bool(store.select("voice_notes", {"date": f"eq.{day}", "voice": f"eq.{voice}",
                                              "note_key": f"eq.{PACK_READY}"}))


def mark_ready(store, *, day: str, voice: str, clips: int, notes: int) -> None:
    """Publish the completeness marker for one narrator's day."""
    store.insert("voice_notes", {
        "date": day,
        "voice": voice,
        "note_key": PACK_READY,
        "text": f"{clips} clip{'s' if clips != 1 else ''}, {notes} note{'s' if notes != 1 else ''}",
        "duration": 0,
        "audio_path": f"notes/{day}/{PACK_READY}-{voice}.mp3",
    }, on_conflict="date,voice,note_key")


def clear_ready(store, *, day: str, voice: str) -> None:
    """Take a day off the air for a narrator whose clips are about to be replaced."""
    store.delete("voice_notes", {"date": f"eq.{day}", "voice": f"eq.{voice}", "note_key": f"eq.{PACK_READY}"})


def _delete_prunable_rows(
    store, table: str, rows: list[dict], cutoff_date: str, preserve_set: set[str],
) -> tuple[list[dict], set[str]]:
    """Delete prunable DB rows for one table and return (deleted_rows, paths_still_referenced)."""
    if table == "voice_notes":
        key_fn = lambda r: {"date": f"eq.{r['date']}", "voice": f"eq.{r['voice']}", "note_key": f"eq.{r['note_key']}"}
    elif table == "story_audio" and preserve_set:
        key_fn = lambda r: {"id": f"eq.{r['id']}"}
    else:
        key_fn = None

    if key_fn is None:
        try:
            store.delete(table, {"date": f"lt.{cutoff_date}"})
            return rows, set()
        except Exception as exc:  # noqa: BLE001
            log.warning("[prune] %s: DB batch delete failed (cutoff=%s, rows=%d): %s",
                        table, cutoff_date, len(rows), exc)
            return [], {r["audio_path"] for r in rows if r.get("audio_path")}

    deleted: list[dict] = []
    still_referenced: set[str] = set()
    for r in rows:
        try:
            store.delete(table, key_fn(r))
            deleted.append(r)
        except Exception as exc:  # noqa: BLE001
            log.warning("[prune] %s: DB row delete failed (date=%s, path=%s): %s",
                        table, r.get("date"), r.get("audio_path"), exc)
            if r.get("audio_path"):
                still_referenced.add(r["audio_path"])
    return deleted, still_referenced


def prune_older(store, *, keep: str, keep_days: int = 2, preserve_sections: list[str] | None = None) -> list[str]:
    """Delete DB rows and associated audio older than ``keep_days``, protecting static/preserved assets.

    Deletes database rows before storage objects per table so a database failure never permanently
    destroys audio referenced by live rows, and deduplicates object paths across tables.
    """
    days: list[str] = []
    removed_paths: set[str] = set()
    protected_paths: set[str] = set()
    preserve_set = set(preserve_sections or ())
    try:
        base_date = datetime.fromisoformat(keep).date()
        cutoff_date = store_mod.cutoff(base_date, keep_days)
        run_log_cutoff = store_mod.cutoff(base_date, 15)
    except Exception:
        cutoff_date = keep
        run_log_cutoff = keep

    for table in ("story_audio", "voice_notes", "podcast_clips"):
        try:
            all_rows = store.select(table, {"date": f"lt.{cutoff_date}"})
        except Exception as exc:  # noqa: BLE001
            log.warning("[prune] %s: could not query rows (cutoff=%s): %s", table, cutoff_date, exc)
            continue

        if table == "voice_notes":
            protected_paths.update(r["audio_path"] for r in all_rows
                                   if r.get("audio_path") and str(r.get("date")) <= STATIC_DATE)
            rows = [r for r in all_rows if str(r.get("date")) > STATIC_DATE]
        elif table == "story_audio" and preserve_set:
            protected_paths.update(r["audio_path"] for r in all_rows
                                   if r.get("audio_path") and r.get("section") in preserve_set)
            rows = [r for r in all_rows if r.get("section") not in preserve_set]
        else:
            rows = all_rows

        if not rows:
            continue

        deleted_rows, still_referenced = _delete_prunable_rows(store, table, rows, cutoff_date, preserve_set)
        protected_paths.update(still_referenced)
        if not deleted_rows:
            continue

        days.extend(str(r["date"]) for r in deleted_rows)
        paths = list(dict.fromkeys(
            r["audio_path"]
            for r in deleted_rows
            if r.get("audio_path")
            and not str(r["audio_path"]).startswith("notes/static/")
            and r["audio_path"] not in protected_paths
            and r["audio_path"] not in removed_paths
        ))
        removed_count = 0
        if paths:
            try:
                store.remove_objects(paths)
                removed_paths.update(paths)
                removed_count = len(paths)
            except Exception as exc:  # noqa: BLE001
                log.warning("[prune] %s: storage remove failed (%d file(s), first=%s): %s",
                            table, len(paths), paths[0], exc)
        log.info("[prune] %s: %d rows deleted, %d files removed (older than %s)",
                 table, len(deleted_rows), removed_count, cutoff_date)

    unique_days = sorted(set(days))
    for d in unique_days:
        try:
            extra = [
                p for p in store.list_objects(f"stories/{d}")
                if p not in removed_paths
                and p not in protected_paths
                and not str(p).startswith("notes/static/")
            ]
            if extra:
                store.remove_objects(extra)
                removed_paths.update(extra)
                log.info("[prune] orphan cleanup stories/%s: %d extra file(s) removed", d, len(extra))
        except Exception as exc:  # noqa: BLE001
            log.warning("[prune] could not prune extra objects for %s: %s", d, exc)
    try:
        store.delete("run_log", {"run_date": f"lt.{run_log_cutoff}"})
    except Exception as exc:  # noqa: BLE001 — an unpruned log is harmless
        log.debug("Could not trim the run log: %s", exc)
    return unique_days


def notify_listeners(cfg, store, *, title: str, body: str) -> int:
    """Push to every subscribed listener device, pruning expired endpoints."""
    try:
        subs = store.push_subscriptions()
        return push.push_and_prune(cfg, store, subs, title, body, context="listener")
    except Exception as exc:  # noqa: BLE001 - a failed notification is not a failed brief
        log.warning("Listener notification failed: %s", exc)
        return 0


def record(store, *, day: str, status: str, title: str, body: str = "", detail: str = "",
           voices: list[dict] | None = None) -> bool:
    """Write one line to the run_log table so the admin page records every outcome."""
    try:
        store.insert("run_log", {"run_date": day, "status": status, "title": title,
                                 "body": body, "detail": detail, "voices": voices or []})
        return True
    except Exception as exc:  # noqa: BLE001 — a missing log line must not break the morning
        log.warning("Could not write to the run log: %s", exc)
        return False


def notify_admins(cfg, store, *, title: str, body: str, day: str = "", status: str = "ok",
                  detail: str = "", voices: list[dict] | None = None) -> int:
    """Record the outcome in run_log, then push it to admin devices."""
    from .batch import admin_subscriptions

    if day:
        record(store, day=day, status=status, title=title, body=body, detail=detail, voices=voices)
    try:
        subs = admin_subscriptions(cfg, store)
        if not subs:
            log.info("[push] no admin devices are subscribed")
            return 0
        return push.push_and_prune(cfg, store, subs, title, body, context="admin")
    except Exception as exc:  # noqa: BLE001
        log.warning("Admin notification failed: %s", exc)
        return 0


def holder_name() -> str:
    """Human-readable identifier of the process requesting the GPU lease."""
    return os.getenv("CLOUD_RUN_EXECUTION") or f"{platform.node()}:{os.getpid()}"


@contextlib.contextmanager
def pack_lease(store, holder: str | None = None, ttl_minutes: float = 75.0):
    """Acquire an exclusive GPU pack lease, raising PackBusy if another run holds it."""
    holder = holder or holder_name()
    try:
        busy = store.acquire_lease(holder, ttl_minutes * 60)
    except StoreError as exc:
        if exc.status != 404:
            raise
        log.warning("No pack_lease table yet (run supabase/schema.sql): overlapping pack runs are not blocked")
        yield
        return
    if busy:
        raise PackBusy(f"another pack run is using the GPU ({busy})")
    try:
        yield
    finally:
        try:
            store.release_lease(holder)
        except Exception as exc:  # noqa: BLE001 — expires automatically via ttl_minutes
            log.warning("Could not release the pack lease: %s", exc)
