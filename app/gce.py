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


def get_instance_info(project: str, zone: str, instance: str, token: str) -> tuple[int, dict | None]:
    """Query instance metadata directly from the Google Compute Engine API.
    Returns (http_status_code, response_dict_or_None).
    """
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}"
    try:
        resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
        return resp.status_code, (resp.json() if resp.status_code == 200 else None)
    except Exception as exc:
        log.warning("GCE API query failed for instance %s: %s", instance, exc)
        return 0, None


def get_instance_ip(project: str, zone: str, instance: str, token: str) -> str | None:
    """Read the active external IP of the GCE VM directly from the Compute Engine API.
    
    This eliminates brittle hardcoded IP addresses — if the VM IP ever changes,
    the system dynamically discovers the new address at runtime.
    """
    code, data = get_instance_info(project, zone, instance, token)
    if code == 200 and data:
        net_interfaces = data.get("networkInterfaces", [])
        if net_interfaces:
            access_configs = net_interfaces[0].get("accessConfigs", [])
            if access_configs:
                return access_configs[0].get("natIP")
    return None


def is_service_healthy(url: str, timeout: float = 3.0) -> bool:
    """Check if the Chatterbox-Turbo voice service is responding."""
    try:
        resp = httpx.get(f"{url.rstrip('/')}/health", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def send_start_vm(project: str, zone: str, instance: str, token: str) -> tuple[bool, str | None, str | None]:
    """Send an asynchronous start request to Google Compute Engine API.
    Returns (accepted: bool, op_name: str | None, error_msg: str | None).
    Fails fast if the VM was deleted/removed (404) or access is denied (403).
    """
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}/start"
    try:
        resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
        if resp.status_code in (200, 204):
            op_name = None
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    op_name = data.get("name")
                except Exception:
                    pass
            return True, op_name, None
        if resp.status_code == 404:
            raise VoiceServiceDown(
                f"GCE instance '{instance}' was not found (HTTP 404) in project '{project}', zone '{zone}'. "
                "If this VM was removed or decommissioned to save costs, set GCE_MANAGE_VM=false and configure an "
                "alternative VOICE_SERVICE_URL, or recreate the instance using scripts/deploy-gce.sh."
            )
        if resp.status_code == 403:
            raise VoiceServiceDown(
                f"Access denied (HTTP 403) when starting GCE instance '{instance}' in project '{project}'. "
                "Ensure the Compute Engine API is enabled and caller has roles/compute.instanceAdmin."
            )
        msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
        log.warning("GCE start API returned status %d: %s", resp.status_code, resp.text[:200])
        return False, None, msg
    except VoiceServiceDown:
        raise
    except Exception as exc:
        log.warning("Failed to call GCE start API: %s", exc)
        return False, None, str(exc)


def start_vm(project: str, zone: str, instance: str, token: str) -> bool:
    """Send an asynchronous start request to Google Compute Engine API.
    Preserves backward compatibility for callers expecting bool.
    """
    accepted, _, _ = send_start_vm(project, zone, instance, token)
    return accepted


def wait_for_operation(project: str, zone: str, operation_name: str, token: str, timeout: float = 60.0) -> tuple[bool, str | None]:
    """Poll a GCE zone operation until it reaches DONE.
    Returns (success: bool, error_message: str | None).
    """
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
    """Wait for the instance status to reach RUNNING."""
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
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}/stop"
    try:
        resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
        # If already deleted (404), stop request is effectively satisfied
        if resp.status_code in (200, 204, 404):
            return True
        log.warning("GCE stop API returned status %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        log.warning("Failed to call GCE stop API: %s", exc)
        return False


def instance_status(project: str, zone: str, instance: str, token: str) -> str | None:
    """RUNNING, STOPPING, TERMINATED, NOT_FOUND... or None when the API can't say."""
    code, data = get_instance_info(project, zone, instance, token)
    if code == 200 and data:
        return data.get("status")
    if code == 404:
        return "NOT_FOUND"
    if code == 403:
        return "FORBIDDEN"
    return None


def stop_vm_verified(project: str, zone: str, instance: str, token: str, attempts: int = 3) -> bool:
    """Stop the VM and confirm it is stopping, because a GPU left on is the expensive failure.
    If the VM does not exist (404), confirms shutdown immediately without retrying or false alarms.
    """
    for attempt in range(1, attempts + 1):
        status = instance_status(project, zone, instance, token)
        if status == "NOT_FOUND":
            log.info("GCE VM '%s' does not exist (404); no shutdown needed.", instance)
            return True
        if status in ("STOPPING", "TERMINATED", "STOPPED", "SUSPENDED"):
            return True
        stop_vm(project, zone, instance, token)
        status_after = instance_status(project, zone, instance, token)
        if status_after in ("STOPPING", "TERMINATED", "STOPPED", "SUSPENDED", "NOT_FOUND"):
            return True
        log.warning("GCE VM %s is %s after stop attempt %d/%d", instance, status_after or "unknown", attempt, attempts)
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

    # Fail fast if the VM was deleted or access was revoked
    status = instance_status(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
    if status == "NOT_FOUND":
        raise VoiceServiceDown(
            f"GCE instance '{cfg.gce_instance}' was not found (HTTP 404) in project '{cfg.gcp_project}', zone '{cfg.gce_zone}'. "
            "If the VM was removed or decommissioned to save costs, set GCE_MANAGE_VM=false and configure an "
            "alternative VOICE_SERVICE_URL, or recreate the instance with scripts/deploy-gce.sh."
        )
    if status == "FORBIDDEN":
        raise VoiceServiceDown(
            f"Access denied (HTTP 403) accessing GCE instance '{cfg.gce_instance}' in project '{cfg.gcp_project}'. "
            "Ensure Compute Engine API is enabled and caller has roles/compute.instanceAdmin."
        )

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

    max_attempts = getattr(cfg, "gce_start_retries", 3)
    backoff = getattr(cfg, "gce_start_backoff", 60.0)
    vm_started = False
    last_error = "Unknown error"

    for attempt in range(1, max_attempts + 1):
        st = instance_status(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
        if st == "RUNNING":
            log.info("GCE GPU VM '%s' is in RUNNING state.", cfg.gce_instance)
            vm_started = True
            break

        log.info(
            "Starting GCE GPU VM '%s' (%s/%s) for Chatterbox-Turbo (attempt %d/%d)...",
            cfg.gce_instance,
            cfg.gcp_project,
            cfg.gce_zone,
            attempt,
            max_attempts,
        )
        accepted, op_name, err = send_start_vm(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
        if not accepted:
            last_error = err or "Start request rejected"
            log.warning("GCE start request %d/%d not accepted: %s", attempt, max_attempts, last_error)
        elif op_name:
            op_ok, op_err = wait_for_operation(cfg.gcp_project, cfg.gce_zone, op_name, token, timeout=60.0)
            if op_ok:
                if wait_for_vm_running(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token, timeout=30.0):
                    log.info("✓ GCE GPU VM '%s' successfully started (RUNNING).", cfg.gce_instance)
                    vm_started = True
                    break
                else:
                    last_error = f"VM did not reach RUNNING state after operation {op_name}"
                    log.warning("GCE start attempt %d/%d: %s", attempt, max_attempts, last_error)
            else:
                last_error = op_err or "Operation failed"
                log.warning("GCE start operation %d/%d failed: %s", attempt, max_attempts, last_error)
        else:
            if wait_for_vm_running(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token, timeout=45.0):
                log.info("✓ GCE GPU VM '%s' reached RUNNING state.", cfg.gce_instance)
                vm_started = True
                break
            last_error = "VM did not reach RUNNING state"
            log.warning("GCE start attempt %d/%d: %s", attempt, max_attempts, last_error)

        if attempt < max_attempts:
            log.info("Waiting %.0fs backoff before retrying VM start (attempt %d/%d)...", backoff, attempt + 1, max_attempts)
            time.sleep(backoff)

    if not vm_started:
        log.error("Failed to start GCE GPU VM '%s' after %d attempts: %s", cfg.gce_instance, max_attempts, last_error)
        stop_vm_verified(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
        raise VoiceServiceDown(
            f"Failed to start GCE GPU VM '{cfg.gce_instance}' after {max_attempts} attempts: {last_error}"
        )

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
        # Check if VM unexpectedly terminated while waiting for the voice service
        vm_st = instance_status(cfg.gcp_project, cfg.gce_zone, cfg.gce_instance, token)
        if vm_st in ("TERMINATED", "STOPPED", "STOPPING"):
            log.error("GCE GPU VM '%s' unexpectedly transitioned to %s during service startup.", cfg.gce_instance, vm_st)
            break

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
