"""Shared LLM provider configuration, rate-limiting, CLI invocation, and OpenAI-compatible HTTP client."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
AGY_CLI_URL = "agy://cli"

DEFAULT_GROQ_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")
DEFAULT_GEMINI_MODELS = ("gemini-3.5-flash-lite", "gemini-flash-lite-latest")

_LAST_LLM_CALL_TIME: float = 0.0
_MIN_LLM_INTERVAL: float = 2.2  # Minimum seconds between external requests to stay within free-tier RPM


def retry_after(resp: httpx.Response) -> float:
    """Return suggested retry delay in seconds from Retry-After header or Groq error body."""
    try:
        return float(resp.headers.get("retry-after", ""))
    except ValueError:
        pass
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", resp.text)
    if m:
        h, mins, s = (float(x) if x else 0.0 for x in m.groups())
        return h * 3600 + mins * 60 + s
    return 10.0


def rate_limit_llm(min_interval: float = _MIN_LLM_INTERVAL) -> None:
    """Sleep if needed so at least `min_interval` seconds elapse between external LLM calls."""
    global _LAST_LLM_CALL_TIME
    now = time.monotonic()
    elapsed = now - _LAST_LLM_CALL_TIME
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _LAST_LLM_CALL_TIME = time.monotonic()


def agy_bin() -> str | None:
    """Return the path to the Antigravity CLI ('agy') executable if installed."""
    found = shutil.which("agy")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/agy", "/usr/local/bin/agy"):
        if Path(candidate).is_file():
            return candidate
    return None


def extract_json_text(raw: str) -> str:
    """Strip markdown code fences and isolate the outermost JSON object from CLI stdout."""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def call_agy_cli(
    model: str,
    messages: list[dict[str, str]],
    timeout: float = 45.0,
    *,
    bin_lookup: Callable[[], str | None] = agy_bin,
) -> str:
    """Invoke the local Antigravity CLI ('agy') in headless mode to generate raw JSON text."""
    bin_path = bin_lookup()
    if not bin_path:
        raise RuntimeError("Antigravity CLI ('agy') executable not found")
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user").upper()
        parts.append(f"[{role}]\n{msg.get('content', '')}")
    parts.append("\nIMPORTANT: Return ONLY raw valid JSON with no markdown code fences and no commentary.")
    proc = subprocess.run(
        [bin_path, "--model", model, "--disable-slash-commands", "-p", "\n\n".join(parts)],
        cwd="/tmp",
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:160]
        raise RuntimeError(f"agy CLI failed: {err}")
    out = extract_json_text(proc.stdout)
    if not out:
        raise ValueError("agy CLI returned empty output")
    return out


def ai_provider_chain(
    cfg,
    *,
    bin_lookup: Callable[[], str | None] = agy_bin,
) -> list[tuple[str, str, str, str]]:
    """Ordered (model, url, token, provider_label) chain: Antigravity CLI -> Groq -> Local LLM -> Gemini."""
    models: list[tuple[str, str, str, str]] = []
    if getattr(cfg, "agy_enabled", False) and bin_lookup():
        agy_model = getattr(cfg, "agy_model", "gemini-3.8-flash-low") or "gemini-3.8-flash-low"
        models.append((agy_model, AGY_CLI_URL, "agy", "AntigravityCLI"))
    if getattr(cfg, "groq_api_key", None):
        models += [(m, GROQ_URL, cfg.groq_api_key, "Groq") for m in cfg.groq_models]
    if getattr(cfg, "local_llm_url", None):
        models.append((getattr(cfg, "local_llm_model", "llama3.1:8b"), cfg.local_llm_url, "local", "LocalLLM"))
    if getattr(cfg, "gemini_api_key", None):
        models += [(m, GEMINI_URL, cfg.gemini_api_key, "Gemini") for m in cfg.gemini_models]
    return models


def build_chat_body(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    json_mode: bool = True,
) -> dict:
    """Construct a uniform OpenAI-compatible chat completion payload."""
    body: dict = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **({"response_format": {"type": "json_object"}} if json_mode else {}),
        **({"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}),
        "messages": messages,
    }
    return body


def post_chat_raw(
    client: httpx.Client,
    *,
    url: str,
    token: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    throttle: bool = True,
) -> httpx.Response:
    """Execute one OpenAI-compatible POST request with optional free-tier rate limiting."""
    if throttle:
        rate_limit_llm()
    body = build_chat_body(model, messages, temperature=temperature, max_tokens=max_tokens)
    return client.post(url, json=body, headers={"Authorization": f"Bearer {token}"})


def generate_chat_text(
    client: httpx.Client,
    *,
    model: str,
    url: str,
    token: str,
    provider: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    cli_timeout: float = 45.0,
    bin_lookup: Callable[[], str | None] = agy_bin,
    on_rate_limit: Callable[[httpx.Response], float | None] | None = None,
) -> str:
    """Invoke either Antigravity CLI or OpenAI-compatible HTTP endpoint and return raw response text."""
    if url == AGY_CLI_URL or provider == "AntigravityCLI":
        return call_agy_cli(model, messages, timeout=cli_timeout, bin_lookup=bin_lookup)
    resp = post_chat_raw(
        client,
        url=url,
        token=token,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        throttle=True,
    )
    if resp.status_code == 429 and on_rate_limit is not None:
        delay = on_rate_limit(resp)
        if delay is not None:
            raise _RetryAfterSignal(delay, resp)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


class _RetryAfterSignal(Exception):
    """Internal signal thrown when a rate-limited request wants caller backoff + retry."""

    def __init__(self, delay: float, response: httpx.Response):
        super().__init__(f"rate limited for {delay:.1f}s")
        self.delay = delay
        self.response = response
