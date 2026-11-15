"""Client for the LOCAL Ollama model that powers the AI CFO (Phase 7: Qwen 2.5, qwen2.5:3b).

Privacy rule: financial context never leaves the machine. Only a local Ollama server is used; cloud models (":cloud" tags,
hosted URLs) are refused, and there is no fallback to any remote or GPT model. Select the local model with OLLAMA_MODEL.
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

from .. import config

_cache = {"t": 0.0, "ok": False, "models": []}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
NUM_CTX = 8192


def _remote_reason() -> str | None:
    host = urlparse(config.OLLAMA_URL).hostname or ""
    if host not in LOCAL_HOSTS:
        return f"Remote LLM endpoints are disabled: financial data stays on this machine (OLLAMA_URL host '{host}')."
    if config.OLLAMA_MODEL.endswith(":cloud"):
        return f"Cloud models are disabled: financial data stays on this machine ({config.OLLAMA_MODEL})."
    return None


def status(force: bool = False) -> dict:
    if config.LLM_PROVIDER == "none":
        return {"available": False, "model": None, "reason": "LLM disabled (LLM_PROVIDER=none)"}
    remote = _remote_reason()
    if remote:
        return {"available": False, "model": config.OLLAMA_MODEL, "reason": remote, "installed_models": []}
    if force or time.time() - _cache["t"] > 20:
        try:
            r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=2.5)
            _cache.update(ok=r.status_code == 200, models=[m["name"] for m in r.json().get("models", [])], reason=None)
        except Exception as e:
            _cache.update(ok=False, models=[], reason=f"Ollama is not running at {config.OLLAMA_URL} ({type(e).__name__}). Start it with: ollama serve")
        _cache["t"] = time.time()
    installed = config.OLLAMA_MODEL in _cache["models"]
    reason = _cache.get("reason") or (None if installed else f"Model {config.OLLAMA_MODEL} is not installed. Run: ollama pull {config.OLLAMA_MODEL}")
    return {"available": bool(_cache["ok"] and installed), "model": config.OLLAMA_MODEL, "reason": reason,
            "installed_models": _cache["models"], "local_only": True}


def chat(messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2, max_tokens: int = 600,
         stats: list | None = None) -> dict:
    """Returns the assistant message dict: {"content": str, "tool_calls": [...]}. Raises on failure.
    When `stats` is a list, appends {latency_ms, prompt_tokens, output_tokens, tokens_per_s, load_ms}."""
    remote = _remote_reason()
    if remote:
        raise RuntimeError(remote)
    body = {"model": config.OLLAMA_MODEL, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": NUM_CTX}}
    if tools:
        body["tools"] = tools
    t0 = time.time()
    r = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    j = r.json()
    if stats is not None:
        ev, evd = j.get("eval_count") or 0, j.get("eval_duration") or 0
        stats.append({"latency_ms": round((time.time() - t0) * 1000), "prompt_tokens": j.get("prompt_eval_count"),
                      "output_tokens": ev, "tokens_per_s": round(ev / (evd / 1e9), 1) if evd else None,
                      "load_ms": round((j.get("load_duration") or 0) / 1e6)})
    return j.get("message", {})


def chat_json(messages: list[dict], schema: dict, max_tokens: int = 300, stats: list | None = None) -> dict:
    """Schema-constrained JSON output (Ollama structured outputs). Raises on failure or invalid JSON."""
    import json
    remote = _remote_reason()
    if remote:
        raise RuntimeError(remote)
    body = {"model": config.OLLAMA_MODEL, "messages": messages, "stream": False, "format": schema, "keep_alive": "30m",
            "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": NUM_CTX}}
    t0 = time.time()
    r = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    j = r.json()
    if stats is not None:
        stats.append(_stat("plan", j, t0))
    return json.loads(j.get("message", {}).get("content") or "{}")


def chat_stream(messages: list[dict], temperature: float = 0.2, max_tokens: int = 400, stats: list | None = None):
    """Yields text deltas as the local model generates them; appends timing stats when finished."""
    import json
    remote = _remote_reason()
    if remote:
        raise RuntimeError(remote)
    body = {"model": config.OLLAMA_MODEL, "messages": messages, "stream": True, "keep_alive": "30m",
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": NUM_CTX}}
    t0 = time.time()
    with httpx.stream("POST", f"{config.OLLAMA_URL}/api/chat", json=body, timeout=config.LLM_TIMEOUT) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            j = json.loads(line)
            delta = (j.get("message") or {}).get("content") or ""
            if delta:
                yield delta
            if j.get("done"):
                if stats is not None:
                    stats.append(_stat("write", j, t0))
                break


def _stat(kind: str, j: dict, t0: float) -> dict:
    ev, evd = j.get("eval_count") or 0, j.get("eval_duration") or 0
    return {"kind": kind, "latency_ms": round((time.time() - t0) * 1000), "prompt_tokens": j.get("prompt_eval_count"),
            "prompt_ms": round((j.get("prompt_eval_duration") or 0) / 1e6), "output_tokens": ev,
            "tokens_per_s": round(ev / (evd / 1e9), 1) if evd else None, "load_ms": round((j.get("load_duration") or 0) / 1e6)}
