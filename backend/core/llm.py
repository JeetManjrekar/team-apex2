"""Optional LLM. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env. Without a key the rule-based extractor is used."""
import json, re
import requests
from .store import env


def provider():
    if env("ANTHROPIC_API_KEY"):
        return "anthropic"
    if env("OPENAI_API_KEY"):
        return "openai"
    return None


def _parse(text):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else None


def chat_json(system: str, user: str, max_tokens=1500):
    p = provider()
    if p == "anthropic":
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
            "x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": env("LLM_MODEL", "claude-sonnet-5-5"), "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        return _parse("".join(b.get("text", "") for b in r.json()["content"]))
    if p == "openai":
        r = requests.post("https://api.openai.com/v1/chat/completions", timeout=60, headers={
            "Authorization": f"Bearer {env('OPENAI_API_KEY')}"},
            json={"model": env("LLM_MODEL", "gpt-4o-mini"), "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        return _parse(r.json()["choices"][0]["message"]["content"])
    return None
