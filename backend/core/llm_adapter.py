"""LLM adapter (merged from APEX 2 `backend/adapters/llm.py`). The only module that talks to an LLM provider for
extraction, intent and review.

Public: complete_json(), vision_json(). Both return (validated Pydantic object, Usage).
Providers: openai | anthropic | groq (OpenAI-compatible). One repair retry on invalid JSON.
Replay cache: LLM_CACHE_MODE=off|record|replay (record once with keys, replay the demo offline).
Callers mask PII before building prompts (core.sanitizer); nothing here sees unmasked chat text.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .llm_settings import CFG

_SYSTEM_DEFAULT = ("Du bist eine Komponente eines Baustellen-Assistenten. Antworte ausschließlich mit "
                   "einem gültigen JSON-Objekt ohne Markdown.")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class Usage(BaseModel):
    input: int = 0
    output: int = 0
    model: str = ""
    cached: bool = False


class LLMError(RuntimeError):
    pass


def _key(provider: str) -> str | None:
    # CFG.api_key belongs to LLM_PROVIDER; a second provider (judge B) uses REVIEW_JUDGE_B_API_KEY, else the SDK's env var.
    if provider == CFG.provider:
        return CFG.api_key or None
    return CFG.judge_b_api_key or None


def _openai_compatible(system: str, content: Any, model: str, provider: str) -> tuple[str, Usage]:
    from openai import OpenAI   # heavy import inside: the backend starts without the SDK
    kw = {"base_url": GROQ_BASE_URL} if provider == "groq" else {}
    client = OpenAI(api_key=_key(provider), timeout=CFG.timeout_s, **kw)
    extra = {"reasoning_effort": CFG.reasoning_effort} if provider == "groq" and CFG.reasoning_effort else {}
    r = client.chat.completions.create(
        model=model, temperature=CFG.temperature, response_format={"type": "json_object"}, **extra,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}])
    u = r.usage
    return r.choices[0].message.content or "", Usage(input=u.prompt_tokens if u else 0, output=u.completion_tokens if u else 0, model=r.model)


def _anthropic(system: str, content: Any, model: str, provider: str = "anthropic") -> tuple[str, Usage]:
    import anthropic
    client = anthropic.Anthropic(api_key=_key("anthropic"), timeout=CFG.timeout_s)
    if isinstance(content, list):   # OpenAI-style parts -> Anthropic blocks
        blocks = []
        for p in content:
            if p["type"] == "text":
                blocks.append({"type": "text", "text": p["text"]})
            else:
                head, b64 = p["image_url"]["url"].split(",", 1)
                blocks.append({"type": "image", "source": {"type": "base64", "data": b64,
                                                           "media_type": head.removeprefix("data:").split(";")[0]}})
        content = blocks
    r = client.messages.create(model=model, max_tokens=4096, temperature=CFG.temperature,
                               system=system, messages=[{"role": "user", "content": content}])
    text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    return text, Usage(input=r.usage.input_tokens, output=r.usage.output_tokens, model=r.model)


_PROVIDERS = {"openai": _openai_compatible, "groq": _openai_compatible, "anthropic": _anthropic}


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _cache_path(key: dict) -> Path:
    digest = hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return CFG.cache_dir / f"{digest}.json"


def _retry_after(err: Exception) -> float | None:
    """Seconds to wait if `err` is a rate limit (HTTP 429), else None. Groq says 'try again in 585ms' / 'in 7.2s'."""
    if getattr(err, "status_code", None) != 429 and "429" not in str(err)[:40]:
        return None
    if "insufficient_quota" in str(err) or "credit" in str(err).lower():
        return None                                   # out of credits: waiting does not help
    m = re.search(r"try again in ([\d.]+)\s*(ms|s)", str(err))
    return (float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)) if m else 2.0


def _with_rate_limit_retry(fn, attempts: int = 3):
    """Free-tier token-per-minute limits are hit by two quick voice notes; wait as told (max LLM_RATE_LIMIT_MAX_WAIT_S)."""
    import os
    import time
    max_wait = float(os.environ.get("LLM_RATE_LIMIT_MAX_WAIT_S", "20") or 20)
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            wait = _retry_after(e)
            if wait is None or i == attempts - 1 or wait > max_wait:
                raise
            time.sleep(wait + 0.3)


def _call(system: str, content: Any, model: str, provider: str) -> tuple[str, Usage]:
    if provider not in _PROVIDERS:
        raise LLMError(f"Unknown LLM provider '{provider}'")
    if not model:
        raise LLMError("No LLM model configured (LLM_MODEL_EXTRACT / LLM_MODEL_REVIEW)")
    mode = CFG.cache_mode
    path = _cache_path({"p": provider, "m": model, "s": system, "c": content}) if mode != "off" else None
    if mode == "replay":
        if not path.exists():
            raise LLMError(f"LLM replay cache miss: {path.name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["text"], Usage(**data["usage"], cached=True)
    text, usage = _with_rate_limit_retry(lambda: _PROVIDERS[provider](system, content, model, provider))
    if mode == "record":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"text": text, "usage": usage.model_dump(exclude={"cached"})}, ensure_ascii=False), encoding="utf-8")
    return text, usage


def _validated(system: str, content: Any, schema: type[BaseModel], model: str, provider: str) -> tuple[BaseModel, Usage]:
    """One call, plus one repair retry if the JSON does not validate."""
    text, usage = _call(system, content, model, provider)
    try:
        return schema.model_validate(_parse_json(text)), usage
    except (ValidationError, json.JSONDecodeError) as err:
        repair = f"{system}\n\nDeine letzte Antwort war ungültig ({str(err)[:300]}). Antworte jetzt nur mit dem korrekten JSON-Objekt."
        text2, usage2 = _call(repair, content, model, provider)
        total = Usage(input=usage.input + usage2.input, output=usage.output + usage2.output, model=usage2.model, cached=usage2.cached)
        try:
            return schema.model_validate(_parse_json(text2)), total
        except (ValidationError, json.JSONDecodeError) as err2:
            raise LLMError(f"LLM output failed validation twice: {err2}") from err2


def complete_json(prompt: str, schema: type[BaseModel], model: str, *, system: str | None = None,
                  provider: str | None = None) -> tuple[BaseModel, Usage]:
    return _validated(system or _SYSTEM_DEFAULT, prompt, schema, model, provider or CFG.provider)


def vision_json(image_path: str, prompt: str, schema: type[BaseModel], *, model: str | None = None,
                provider: str | None = None) -> tuple[BaseModel, Usage]:
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]
    return _validated(_SYSTEM_DEFAULT, content, schema, model or CFG.vision_model, provider or CFG.vision_provider)
