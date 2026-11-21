"""Live model prices (EUR per 1M tokens) for the cost metric.
Source: OpenRouter public models API (USD per token, no key) + frankfurter.app (ECB) for USD->EUR.
Cached in memory and in data/pricing_cache.json (TTL PRICING_TTL_H, default 24 h). The refresh runs in a background
thread, so a request never waits for the network; rates() returns None while nothing is known. Never raises.
Env: LIVE_PRICING=on|off. OpenRouter quotes its default provider, which can differ slightly from e.g. Groq's own price."""
import json, os, threading, time

import requests

from .store import DATA

MODELS_URL = "https://openrouter.ai/api/v1/models"
FX_URL = "https://api.frankfurter.app/latest?from=USD&to=EUR"
_state = {"rates": None, "fetched_at": 0.0, "busy": False}
_lock = threading.Lock()


def _cache_file():
    return DATA / "pricing_cache.json"


def _ttl_s():
    try:
        return float(os.environ.get("PRICING_TTL_H", "24")) * 3600
    except ValueError:
        return 86400.0


def _fetch() -> dict:
    fx = requests.get(FX_URL, timeout=5).json()["rates"]["EUR"]
    out = {}
    for m in requests.get(MODELS_URL, timeout=10).json().get("data", []):
        p = m.get("pricing") or {}
        try:
            out[m["id"]] = [float(p["prompt"]) * fx * 1e6, float(p["completion"]) * fx * 1e6]
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _refresh():
    try:
        rates = _fetch()
        if rates:
            _state.update(rates=rates, fetched_at=time.time())
            _cache_file().write_text(json.dumps({"fetched_at": _state["fetched_at"], "rates": rates}))
    except Exception:
        pass
    finally:
        _state["busy"] = False


def _load_disk():
    try:
        d = json.loads(_cache_file().read_text())
        _state.update(rates=d["rates"], fetched_at=float(d["fetched_at"]))
    except Exception:
        pass


def rates(model: str | None):
    """(input_eur_per_1m, output_eur_per_1m) for `model`, or None if unknown / live pricing off."""
    if not model or os.environ.get("LIVE_PRICING", "on").lower() in ("off", "0", "false"):
        return None
    with _lock:
        if _state["rates"] is None:
            _load_disk()
        if time.time() - _state["fetched_at"] > _ttl_s() and not _state["busy"]:
            _state["busy"] = True
            threading.Thread(target=_refresh, daemon=True).start()
        table = _state["rates"] or {}
    for key in (model, model.split(":")[-1], f"openai/{model}", f"anthropic/{model}"):
        if key in table:
            return tuple(table[key])
    return None


def info() -> dict:
    return {"source": "openrouter", "fetched_at": _state["fetched_at"] or None, "models": len(_state["rates"] or {})}
