"""Control the GCE GPU instance for Chatterbox-Turbo TTS on demand.

Ensures the GPU VM runs ONLY while synthesizing audio (typically ~25-35 minutes per day for
4 voices across 35 stories and section notes), costing ~$0.30-$0.45/day (~$10-14/month)
instead of $500/month 24/7. Verified automated shutdown on exit and GCP hypervisor max-run-duration
backstops ensure the VM cannot remain running unnoticed.

Features dynamic IP resolution directly via Google Compute Engine API so hardcoded IPs
never break even if the VM is assigned a new IP or recreated.
"""
from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import time
import httpx

from .errors import VoiceServiceDown

log = logging.getLogger(__name__)


def get_access_token() -> str | None:
    """Obtain an access token for Google Cloud APIs (works in Cloud Run and locally via gcloud)."""
    # 1. Metadata server (inside Cloud Run / GCP)
    try:
        resp = httpx.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
            timeout=2.0,
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            if token:
                return token
    except Exception:
        pass

    # 2. Local gcloud CLI fallback
    try:
        out = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return out
    except Exception:
        pass

    return None


def get_instance_ip(project: str, zone: str, instance: str, token: str) -> str | None:
    """Read the active external IP of the GCE VM directly from the Compute Engine API.
    
    This eliminates brittle hardcoded IP addresses — if the VM IP ever changes,
    the system dynamically discovers the new address at runtime.
    """
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}"
    try:
        resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            net_interfaces = data.get("networkInterfaces", [])
            if net_interfaces:
                access_configs = net_interfaces[0].get("accessConfigs", [])
                if access_configs:
                    return access_configs[0].get("natIP")
    except Exception as exc:
        log.warning("Could not dynamically resolve IP for instance %s: %s", instance, exc)
    return None


def is_service_healthy(url: str, timeout: float = 3.0) -> bool:
    """Check if the Chatterbox-Turbo voice service is responding."""
    try:
        resp = httpx.get(f"{url.rstrip('/')}/health", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def start_vm(project: str, zone: str, instance: str, token: str) -> bool:
    """Send an asynchronous start request to Google Compute Engine API."""
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}/start"
    try:
        resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
        return resp.status_code in (200, 204)
    except Exception as exc:
        log.warning("Failed to call GCE start API: %s", exc)
        return False


def stop_vm(project: str, zone: str, instance: str, token: str) -> bool:
    """Send an asynchronous stop request to Google Compute Engine API."""
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}/stop"
    try:
        resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
        return resp.status_code in (200, 204)
    except Exception as exc:
        log.warning("Failed to call GCE stop API: %s", exc)
        return False


def instance_status(project: str, zone: str, instance: str, token: str) -> str | None:
    """RUNNING, STOPPING, TERMINATED... or None when the API can't say."""
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}"
    try:
        resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
        return resp.json().get("status") if resp.status_code == 200 else None
    except Exception:
        return None


def stop_vm_verified(project: str, zone: str, instance: str, token: str, attempts: int = 3) -> bool:
    """Stop the VM and confirm it is stopping, because a GPU left on is the expensive failure."""
    for attempt in range(1, attempts + 1):
        stop_vm(project, zone, instance, token)
        status = instance_status(project, zone, instance, token)
        if status in ("STOPPING", "TERMINATED", "STOPPED", "SUSPENDED"):
            return True
        log.warning("GCE VM %s is %s after stop attempt %d/%d", instance, status or "unknown", attempt, attempts)
        time.sleep(3 * attempt)
    log.error("COULD NOT STOP GCE VM %s. It is still billing; stop it by hand: "
              "gcloud compute instances stop %s --zone=%s", instance, instance, zone)
    return False


def _stop_on_exit(cfg, token: str) -> None:
    if getattr(cfg, "gce_keep_vm", False):
        log.warning("GCE_KEEP_VM is set: leaving GCE GPU VM '%s' running. Stop it when you are done.",
                    cfg.gce_instance)
        return
    log.info("Shutting down GCE GPU VM '%s' immediately to save costs...", cfg.gce_instance)
    if stop_vm_verified(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, get_access_token() or token):
        log.info("✓ VM stop confirmed.")


@contextlib.contextmanager
def voice_vm_session(cfg):
    """Context manager that starts the GCE GPU VM if needed, resolves its IP dynamically,
    waits for Chatterbox-Turbo, and stops the VM on the way out, whoever started it.

    A VM that was already running is stopped too: leaving it for "whoever started it" is how one
    ended up billing for hours after a killed job. Set GCE_KEEP_VM=1 to keep it warm on purpose.

    Yields the active voice service URL (e.g. 'http://34.67.158.112:8090').
    """
    voice_url = (getattr(cfg, "voice_url", "") or "").rstrip("/")
    if voice_url.lower() in ("auto", "dynamic", "none"):
        voice_url = ""

    if not getattr(cfg, "gce_manage_vm", True) or not getattr(cfg, "gce_instance", None):
        yield voice_url
        return

    token = get_access_token()
    if not token:
        log.warning(
            "No GCP access token available to manage GCE instance %s; proceeding directly with %s",
            cfg.gce_instance,
            voice_url or "empty URL",
        )
        yield voice_url
        return

    # Check if VM is already running and voice service is already healthy
    discovered_ip = get_instance_ip(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
    if discovered_ip:
        voice_url = f"http://{discovered_ip}:8090"
        if is_service_healthy(voice_url):
            log.info("Chatterbox-Turbo voice service is already running at %s", voice_url)
            try:
                yield voice_url
            finally:
                _stop_on_exit(cfg, token)
            return

    log.info(
        "Starting GCE GPU VM '%s' (%s/%s) for Chatterbox-Turbo...",
        cfg.gce_instance,
        cfg.gcp_project,
        cfg.gce_zone,
    )
    if not start_vm(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token):
        log.warning("Failed to send start command to %s", cfg.gce_instance)

    # Wait for GCE to assign external IP (ephemeral or static) and for service to report healthy
    ready = False
    start_time = time.monotonic()
    timeout = getattr(cfg, "gce_health_timeout", 180.0)
    log.info(
        "Waiting for Chatterbox-Turbo voice service on %s to report healthy (timeout: %.0fs)...",
        cfg.gce_instance,
        timeout,
    )

    while time.monotonic() - start_time < timeout:
        if not voice_url or "auto" in voice_url:
            fresh_ip = get_instance_ip(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
            if fresh_ip:
                voice_url = f"http://{fresh_ip}:8090"
                log.info("Discovered active GCE VM IP dynamically: %s", voice_url)
            else:
                time.sleep(3)
                continue

        if is_service_healthy(voice_url):
            ready = True
            log.info(
                "✓ Chatterbox-Turbo voice service is online and ready at %s (took %.1fs)!",
                voice_url,
                time.monotonic() - start_time,
            )
            break
        time.sleep(3)

    if not ready:
        log.error(
            "Chatterbox-Turbo voice service did not become healthy within %.0fs. Shutting down VM immediately...",
            timeout,
        )
        stop_vm_verified(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
        raise VoiceServiceDown(
            f"Chatterbox-Turbo service at {voice_url or cfg.gce_instance} did not respond within {timeout}s")

    try:
        yield voice_url
    finally:
        _stop_on_exit(cfg, token)
