"""Web Push (VAPID) notifications: key storage and sending."""
from __future__ import annotations

import base64
import json
import logging

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush

from .config import Config

log = logging.getLogger(__name__)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def load_keys(cfg: Config) -> dict:
    """VAPID key pair, generated once and kept in the data directory."""
    path = cfg.data_dir / "vapid.json"
    if path.exists():
        return json.loads(path.read_text())
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.X962,
                                           serialization.PublicFormat.UncompressedPoint)
    keys = {"private_pem": private, "public_key": _b64(public)}
    path.write_text(json.dumps(keys))
    path.chmod(0o600)
    return keys


def send(cfg: Config, subscriptions: list[dict], title: str, body: str, url: str = "/") -> tuple[int, list[str]]:
    """Push to each subscription. Returns (sent, endpoints the push service says are gone)."""
    if not subscriptions:
        return 0, []
    keys = load_keys(cfg)
    payload = json.dumps({"title": title, "body": body, "url": url})
    sent, gone = 0, []
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload, vapid_private_key=keys["private_pem"], vapid_claims={"sub": cfg.vapid_subject},
                ttl=6 * 3600,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                gone.append(sub["endpoint"])
            else:
                log.warning("Push failed (%s): %s", status, exc)
        except Exception as exc:  # noqa: BLE001 - never let a notification break a build
            log.warning("Push failed: %s", exc)
    return sent, gone
