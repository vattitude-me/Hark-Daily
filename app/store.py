"""Supabase access for the worker: PostgREST for tables, the Storage API for MP3s.

Uses the secret key, which bypasses row-level security, so this module only
ever runs on the server.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx

log = logging.getLogger(__name__)


class StoreError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status

    @property
    def quota(self) -> bool:
        """Storage full, file too large or plan limit hit."""
        text = str(self).lower()
        return self.status in (402, 413) or "quota" in text or "exceed" in text or "too large" in text


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, url: str, key: str, bucket: str = "briefings", client: httpx.Client | None = None):
        if not url or not key:
            raise StoreError("SUPABASE_URL and SUPABASE_SECRET_KEY must be set")
        self.url = url.rstrip("/")
        self.bucket = bucket
        headers = {"apikey": key}
        if not key.startswith("sb_"):  # legacy service_role JWT
            headers["Authorization"] = f"Bearer {key}"
        self.http = client or httpx.Client(timeout=60, headers=headers)
        self.http.headers.update(headers)

    # ------------------------------------------------------------------ REST
    def _call(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            resp = self.http.request(method, f"{self.url}{path}", **kw)
        except httpx.HTTPError as exc:
            raise StoreError(f"Supabase unreachable: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = body.get("message") or body.get("error") or body.get("msg") or resp.text
            except ValueError:
                msg = resp.text
            raise StoreError(f"Supabase {method} {path.split('?')[0]} → {resp.status_code}: {msg}"[:400],
                             resp.status_code)
        return resp

    def select(self, table: str, params: dict | None = None) -> list[dict]:
        return self._call("GET", f"/rest/v1/{table}", params={"select": "*", **(params or {})}).json()

    def insert(self, table: str, rows: list[dict] | dict, *, on_conflict: str | None = None,
               ignore_duplicates: bool = False) -> list[dict]:
        prefer = ["return=representation"]
        params = {}
        if on_conflict:
            prefer.append("resolution=" + ("ignore-duplicates" if ignore_duplicates else "merge-duplicates"))
            params["on_conflict"] = on_conflict
        return self._call("POST", f"/rest/v1/{table}", params=params, json=rows,
                          headers={"Prefer": ",".join(prefer)}).json()

    def update(self, table: str, params: dict, values: dict) -> list[dict]:
        return self._call("PATCH", f"/rest/v1/{table}", params=params, json=values,
                          headers={"Prefer": "return=representation"}).json()

    def delete(self, table: str, params: dict) -> None:
        self._call("DELETE", f"/rest/v1/{table}", params=params)

    @staticmethod
    def _in(values) -> str:
        return "in.(" + ",".join(f'"{v}"' for v in values) + ")"

    # -------------------------------------------------------------- profiles
    def delete_user(self, user_id: str) -> None:
        """Delete the sign-in account. Profiles, links, briefings, push subscriptions and requests cascade."""
        self._call("DELETE", f"/auth/v1/admin/users/{user_id}")

    def profiles(self) -> list[dict]:
        return self.select("profiles", {"order": "created_at"})

    def set_admins(self, emails: tuple[str, ...]) -> None:
        if emails:
            self.update("profiles", {"email": self._in(emails)}, {"is_admin": True})

    def set_profile_status(self, user_id: str, status: dict) -> None:
        self.update("profiles", {"id": f"eq.{user_id}"}, {"status": status})

    # --------------------------------------------------------------- sources
    def sources(self) -> list[dict]:
        return self.select("sources", {"order": "id"})

    def seed_builtins(self, builtins: list[dict]) -> None:
        rows = [{"name": s["name"], "url": s["url"], "feed_url": s["url"], "kind": "feed",
                 "section": s["section"], "weight": s.get("weight", 1.0), "user_id": None} for s in builtins]
        self.insert("sources", rows, on_conflict="user_id,url", ignore_duplicates=True)

    def update_source(self, source_id: int, values: dict) -> None:
        self.update("sources", {"id": f"eq.{source_id}"}, values)

    def reset_consumed(self, user_ids: list[str], since: str) -> None:
        self.update("sources", {"user_id": self._in(user_ids), "consumed_at": f"gte.{since}"}, {"consumed_at": None})

    # ------------------------------------------------------------- briefings
    def upsert_briefing(self, user_id: str, day: str, data: dict, audio_path: str) -> None:
        self.insert("briefings", {"user_id": user_id, "date": day, "data": data, "audio_path": audio_path},
                    on_conflict="user_id,date")

    def briefings(self, params: dict) -> list[dict]:
        return self.select("briefings", {"select": "user_id,date,audio_path", **params})

    def delete_briefings(self, rows: list[dict]) -> None:
        """Delete briefing rows and their MP3s."""
        paths = [r["audio_path"] for r in rows if r.get("audio_path")]
        if paths:
            self.remove_objects(paths)
        for r in rows:
            self.delete("briefings", {"user_id": f"eq.{r['user_id']}", "date": f"eq.{r['date']}"})

    # ------------------------------------------------------------------ push
    def push_subscriptions(self, user_ids: list[str] | None = None) -> list[dict]:
        params = {"user_id": self._in(user_ids)} if user_ids else {}
        return self.select("push_subscriptions", params)

    def delete_push_subscription(self, endpoint: str) -> None:
        self.delete("push_subscriptions", {"endpoint": f"eq.{endpoint}"})

    # -------------------------------------------------------------- requests
    def pending_requests(self) -> list[dict]:
        return self.select("build_requests", {"status": "eq.queued", "order": "id"})

    def update_request(self, request_id: int, values: dict) -> None:
        self.update("build_requests", {"id": f"eq.{request_id}"}, values)

    # ---------------------------------------------------------------- status
    def set_app_status(self, data: dict) -> None:
        self.insert("app_status", {"id": 1, "data": data, "updated_at": now_iso()}, on_conflict="id")

    def app_status(self) -> dict:
        rows = self.select("app_status", {"id": "eq.1"})
        return rows[0]["data"] if rows else {}

    def set_showcase(self, data: dict) -> None:
        self.insert("showcase", {"id": 1, "data": data, "updated_at": now_iso()}, on_conflict="id")

    def showcase(self) -> dict:
        rows = self.select("showcase", {"id": "eq.1"})
        return rows[0]["data"] if rows else {}

    # --------------------------------------------------------------- storage
    def public_url(self, path: str) -> str:
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"

    def upload(self, path: str, data: bytes, content_type: str = "audio/mpeg") -> str:
        self._call("POST", f"/storage/v1/object/{self.bucket}/{path}", content=data,
                   headers={"Content-Type": content_type, "x-upsert": "true", "Cache-Control": "max-age=3600"})
        return self.public_url(path)

    def list_objects(self, prefix: str) -> list[str]:
        rows = self._call("POST", f"/storage/v1/object/list/{self.bucket}",
                          json={"prefix": prefix, "limit": 1000}).json()
        return [f"{prefix.rstrip('/')}/{r['name']}" for r in rows if r.get("id")]

    def remove_objects(self, paths: list[str]) -> None:
        for i in range(0, len(paths), 100):
            self._call("DELETE", f"/storage/v1/object/{self.bucket}", json={"prefixes": paths[i:i + 100]})


def cutoff(today: date, keep_days: int) -> str:
    """Oldest date to keep: keep_days=2 keeps today and yesterday."""
    from datetime import timedelta

    return (today - timedelta(days=max(1, keep_days) - 1)).isoformat()
