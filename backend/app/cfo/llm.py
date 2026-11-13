"""Thin client for a local (or cloud) Ollama model. Works with Qwen, Nemotron or any tool-capable model.

Switch models with environment variables only:
    OLLAMA_MODEL=qwen3.5:4b                        (default, runs on the laptop)
    OLLAMA_MODEL=nemotron-3-super:cloud            (NVIDIA Nemotron on Ollama cloud; needs OLLAMA_API_KEY)
"""
from __future__ import annotations

import time

import httpx

from .. import config

_cache = {"t": 0.0, "ok": False, "models": []}


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.OLLAMA_API_KEY}"} if config.OLLAMA_API_KEY else {}


def status(force: bool = False) -> dict:
    if config.LLM_PROVIDER == "none":
        return {"available": False, "model": None, "reason": "LLM disabled (LLM_PROVIDER=none)"}
    if force or time.time() - _cache["t"] > 20:
        try:
            r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=2.5, headers=_headers())
            _cache.update(ok=r.status_code == 200, models=[m["name"] for m in r.json().get("models", [])], reason=None)
        except Exception as e:
            _cache.update(ok=False, models=[], reason=f"Ollama not reachable at {config.OLLAMA_URL} ({type(e).__name__})")
        _cache["t"] = time.time()
    base = config.OLLAMA_MODEL.split(":")[0]
    installed = any(m == config.OLLAMA_MODEL or m.split(":")[0] == base for m in _cache["models"]) or config.OLLAMA_MODEL.endswith(":cloud")
    reason = _cache.get("reason") or (None if installed else f"Model {config.OLLAMA_MODEL} is not installed. Run: ollama pull {config.OLLAMA_MODEL}")
    return {"available": bool(_cache["ok"] and installed), "model": config.OLLAMA_MODEL, "reason": reason,
            "installed_models": _cache["models"]}


def chat(messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2, max_tokens: int = 500) -> dict:
    """Returns the assistant message dict: {"content": str, "tool_calls": [...]}. Raises on failure."""
    body = {"model": config.OLLAMA_MODEL, "messages": messages, "stream": False, "think": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 4096}}
    if tools:
        body["tools"] = tools
    r = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=config.LLM_TIMEOUT, headers=_headers())
    if r.status_code == 400 and "think" in r.text:  # older models/servers without the think option
        body.pop("think")
        r = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=config.LLM_TIMEOUT, headers=_headers())
    r.raise_for_status()
    return r.json().get("message", {})
