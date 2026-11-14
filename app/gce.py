"""Control the GCE GPU instance for Chatterbox-Turbo TTS on demand.

Ensures the GPU VM runs ONLY while synthesizing audio and shuts it down reliably
on exit. Uses Compute Engine APIs with dynamic external IP resolution.
"""
from __future__ import annotations

import contextlib
import logging
import subprocess
import time

import httpx

from .errors import VoiceServiceDown

log = logging.getLogger(__name__)


def _instance_url(project: str, zone: str, instance: str, suffix: str = "") -> str:
    return f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}{suffix}"


def _raise_for_gce_status(status_or_code: str | int, project: str, zone: str, instance: str, context: str) -> None:
    if status_or_code in ("NOT_FOUND", 404):
        raise VoiceServiceDown(
            f"GCE instance '{instance}' was not found (HTTP 404) in project '{project}', zone '{zone}'. "
            "If this VM was removed or decommissioned to save costs, set GCE_MANAGE_VM=false and configure an "
            "alternative VOICE_SERVICE_URL, or recreate the instance using scripts/deploy-gce.sh."
        )
    if status_or_code in ("FORBIDDEN", 403):
        raise VoiceServiceDown(
            f"Access denied (HTTP 403) {context} GCE instance '{instance}' in project '{project}'. "
            "Ensure Compute Engine API is enabled and caller has roles/compute.instanceAdmin."
        )


def get_access_token() -> str | None:
    """Obtain an access token for GCP APIs (metadata server first, local gcloud CLI fallback)."""
    try:
        resp = httpx.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
            timeout=2.0,
        )
        if resp.status_code == 200 and (token := resp.json().get("access_token")):
            return token
    except Exception:
        pass
    try:
        out = subprocess.check_output(["gcloud", "auth", "print-access-token"],
                                      stderr=subprocess.DEVNULL, text=True).strip()
        if out:
            return out
    except Exception:
        pass
    return None


def get_instance_info(project: str, zone: str, instance: str, token: str) -> tuple[int, dict | None]:
    """Query instance metadata from Compute Engine API; returns (http_status, json_or_None)."""
    try:
        resp = httpx.get(_instance_url(project, zone, instance),
                         headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
        return resp.status_code, (resp.json() if resp.status_code == 200 else None)
    except Exception as exc:
        log.warning("GCE API query failed for instance %s: %s", instance, exc)
        return 0, None


def get_instance_ip(project: str, zone: str, instance: str, token: str) -> str | None:
    """Read the active external natIP of the GCE VM from the Compute Engine API."""
    code, data = get_instance_info(project, zone, instance, token)
    if code == 200 and data:
        for iface in data.get("networkInterfaces", []):
            for ac in iface.get("accessConfigs", []):
                if ac.get("natIP"):
                    return ac["natIP"]
    return None


def is_service_healthy(url: str, timeout: float = 3.0) -> bool:
    """Return True if the voice service /health endpoint responds HTTP 200."""
    try:
        return httpx.get(f"{url.rstrip('/')}/health", timeout=timeout).status_code == 200
    except Exception:
        return False


def send_start_vm(project: str, zone: str, instance: str, token: str) -> tuple[bool, str | None, str | None]:
    """Send an asynchronous start request; raises VoiceServiceDown immediately on 403/404."""
    try:
        resp = httpx.post(_instance_url(project, zone, instance, "/start"),
                          headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
        if resp.status_code in (200, 204):
            op_name = None
            if resp.status_code == 200:
                try:
                    op_name = resp.json().get("name")
                except Exception:
                    pass
            return True, op_name, None
        _raise_for_gce_status(resp.status_code, project, zone, instance, "when starting")
        msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
        log.warning("GCE start API returned status %d: %s", resp.status_code, resp.text[:200])
        return False, None, msg
    except VoiceServiceDown:
        raise
    except Exception as exc:
        log.warning("Failed to call GCE start API: %s", exc)
        return False, None, str(exc)


def start_vm(project: str, zone: str, instance: str, token: str) -> bool:
    """Send an asynchronous start request; returns bool."""
    accepted, _, _ = send_start_vm(project, zone, instance, token)
    return accepted


def wait_for_operation(project: str, zone: str, operation_name: str, token: str,
                       timeout: float = 60.0) -> tuple[bool, str | None]:
    """Poll a GCE zone operation until DONE; returns (success, error_message)."""
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/operations/{operation_name}"
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "DONE":
                    error = data.get("error")
                    if error:
                        errors = error.get("errors", [])
                        code = errors[0].get("code", "") if errors else ""
                        msg = errors[0].get("message") if errors else "Operation failed"
                        return False, f"{code}: {msg}" if code else msg
                    return True, None
        except Exception as exc:
            log.warning("Error checking operation %s: %s", operation_name, exc)
        time.sleep(2.0)
    return False, f"Operation {operation_name} did not complete within {timeout}s"


def wait_for_vm_running(project: str, zone: str, instance: str, token: str, timeout: float = 60.0) -> bool:
    """Wait until instance status reaches RUNNING or fails into TERMINATED/STOPPED."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        st = instance_status(project, zone, instance, token)
        if st == "RUNNING":
            return True
        if st in ("TERMINATED", "STOPPED"):
            return False
        time.sleep(2.0)
    return False


def stop_vm(project: str, zone: str, instance: str, token: str) -> bool:
    """Send an asynchronous stop request to Google Compute Engine API."""
    try:
        resp = httpx.post(_instance_url(project, zone, instance, "/stop"),
                          headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
        if resp.status_code in (200, 204, 404):
            return True
        log.warning("GCE stop API returned status %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        log.warning("Failed to call GCE stop API: %s", exc)
        return False


def instance_status(project: str, zone: str, instance: str, token: str) -> str | None:
    """RUNNING, STOPPING, TERMINATED, NOT_FOUND, FORBIDDEN, or None."""
    code, data = get_instance_info(project, zone, instance, token)
    if code == 200 and data:
        return data.get("status")
    return {404: "NOT_FOUND", 403: "FORBIDDEN"}.get(code)


def stop_vm_verified(project: str, zone: str, instance: str, token: str, attempts: int = 3) -> bool:
    """Stop the VM and verify it is stopping or gone so GPU billing never lingers."""
    stopped_states = ("STOPPING", "TERMINATED", "STOPPED", "SUSPENDED", "NOT_FOUND")
    for attempt in range(1, attempts + 1):
        status = instance_status(project, zone, instance, token)
        if status == "NOT_FOUND":
            log.info("GCE VM '%s' does not exist (404); no shutdown needed.", instance)
            return True
        if status in stopped_states:
            return True
        stop_vm(project, zone, instance, token)
        status_after = instance_status(project, zone, instance, token)
        if status_after in stopped_states:
            return True
        log.warning("GCE VM %s is %s after stop attempt %d/%d", instance, status_after or "unknown", attempt, attempts)
        time.sleep(3 * attempt)
    log.error("COULD NOT STOP GCE VM %s. Stop it manually: gcloud compute instances stop %s --zone=%s",
              instance, instance, zone)
    return False


def _stop_on_exit(cfg, token: str) -> None:
    if getattr(cfg, "gce_keep_vm", False):
        log.warning("GCE_KEEP_VM is set: leaving GCE GPU VM '%s' running. Stop it when done.", cfg.gce_instance)
        return
    log.info("Shutting down GCE GPU VM '%s' immediately to save costs...", cfg.gce_instance)
    if stop_vm_verified(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, get_access_token() or token):
        log.info("✓ VM stop confirmed.")


def _start_vm_with_retries(cfg, token: str) -> None:
    max_attempts = getattr(cfg, "gce_start_retries", 3)
    backoff = getattr(cfg, "gce_start_backoff", 60.0)
    last_error = "Unknown error"

    for attempt in range(1, max_attempts + 1):
        if instance_status(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token) == "RUNNING":
            log.info("GCE GPU VM '%s' is in RUNNING state.", cfg.gce_instance)
            return

        log.info("Starting GCE GPU VM '%s' (%s/%s) (attempt %d/%d)...",
                 cfg.gce_instance, cfg.gcp_project, cfg.gce_zone, attempt, max_attempts)
        accepted, op_name, err = send_start_vm(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
        if not accepted:
            last_error = err or "Start request rejected"
            log.warning("GCE start request %d/%d not accepted: %s", attempt, max_attempts, last_error)
        elif op_name:
            op_ok, op_err = wait_for_operation(cfg.gcp_project, cfg.gce_zone, op_name, token, timeout=60.0)
            if op_ok and wait_for_vm_running(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token, timeout=30.0):
                log.info("✓ GCE GPU VM '%s' successfully started (RUNNING).", cfg.gce_instance)
                return
            last_error = (f"VM did not reach RUNNING state after operation {op_name}" if op_ok
                          else op_err or "Operation failed")
            log.warning("GCE start attempt %d/%d: %s", attempt, max_attempts, last_error)
        else:
            if wait_for_vm_running(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token, timeout=45.0):
                log.info("✓ GCE GPU VM '%s' reached RUNNING state.", cfg.gce_instance)
                return
            last_error = "VM did not reach RUNNING state"
            log.warning("GCE start attempt %d/%d: %s", attempt, max_attempts, last_error)

        if attempt < max_attempts:
            log.info("Waiting %.0fs backoff before retrying VM start (attempt %d/%d)...", backoff, attempt + 1, max_attempts)
            time.sleep(backoff)

    log.error("Failed to start GCE GPU VM '%s' after %d attempts: %s", cfg.gce_instance, max_attempts, last_error)
    stop_vm_verified(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
    raise VoiceServiceDown(f"Failed to start GCE GPU VM '{cfg.gce_instance}' after {max_attempts} attempts: {last_error}")


def _wait_for_voice_healthy(cfg, token: str, voice_url: str) -> str:
    start_time = time.monotonic()
    timeout = getattr(cfg, "gce_health_timeout", 180.0)
    log.info("Waiting for Chatterbox-Turbo voice service on %s (timeout: %.0fs)...", cfg.gce_instance, timeout)

    while time.monotonic() - start_time < timeout:
        vm_st = instance_status(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
        if vm_st in ("TERMINATED", "STOPPED", "STOPPING"):
            log.error("GCE GPU VM '%s' unexpectedly transitioned to %s during startup.", cfg.gce_instance, vm_st)
            break
        if not voice_url or "auto" in voice_url:
            if fresh_ip := get_instance_ip(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token):
                voice_url = f"http://{fresh_ip}:8090"
                log.info("Discovered active GCE VM IP dynamically: %s", voice_url)
            else:
                time.sleep(3)
                continue
        if is_service_healthy(voice_url):
            log.info("✓ Chatterbox-Turbo voice service is online at %s (took %.1fs)!",
                     voice_url, time.monotonic() - start_time)
            return voice_url
        time.sleep(3)

    log.error("Voice service did not become healthy within %.0fs. Shutting down VM...", timeout)
    stop_vm_verified(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
    raise VoiceServiceDown(f"Chatterbox-Turbo service at {voice_url or cfg.gce_instance} did not respond within {timeout}s")


@contextlib.contextmanager
def voice_vm_session(cfg):
    """Start the GCE GPU VM if needed, wait for healthy voice service, and stop the VM on exit."""
    voice_url = (getattr(cfg, "voice_url", "") or "").rstrip("/")
    if voice_url.lower() in ("auto", "dynamic", "none"):
        voice_url = ""

    if not getattr(cfg, "gce_manage_vm", True) or not getattr(cfg, "gce_instance", None):
        yield voice_url
        return

    token = get_access_token()
    if not token:
        log.warning("No GCP access token available for %s; proceeding with %s", cfg.gce_instance, voice_url or "empty URL")
        yield voice_url
        return

    status = instance_status(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
    _raise_for_gce_status(status or 0, cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, "accessing")

    if discovered_ip := get_instance_ip(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token):
        candidate_url = f"http://{discovered_ip}:8090"
        if is_service_healthy(candidate_url):
            log.info("Chatterbox-Turbo voice service is already running at %s", candidate_url)
            try:
                yield candidate_url
            finally:
                _stop_on_exit(cfg, token)
            return

    _start_vm_with_retries(cfg, token)
    voice_url = _wait_for_voice_healthy(cfg, token, voice_url)
    try:
        yield voice_url
    finally:
        _stop_on_exit(cfg, token)
