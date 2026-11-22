"""Claim potential: the euro amount a Nachtragsmeldung / Mehrkostenanzeige can realistically recover.

Estimated by a separate model (Qwen3-14B via CLAIM_LLM_*) in the background, debounced per document and only when the
document's field values changed (fingerprint). The result is stored as doc["claim_potential"]:
    {amount_eur, low_eur, high_eur, confidence, rationale_de, basis, fp, at, model}
amount_eur is null when the data is insufficient. Without a configured model, or when the call fails, nothing is stored.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time

from pydantic import BaseModel, Field

from . import llm_adapter, registry, sanitizer
from .llm_settings import CFG
from .store import load, now, save

log = logging.getLogger(__name__)

CLAIM_TYPES = ("nachtragsmeldung", "mehrkostenanzeige")
DEBOUNCE_S = 2.0
RETRY_AFTER_FAIL_S = 300
SYSTEM = ("Du bist eine Komponente eines Baustellen-Assistenten. Antworte ausschließlich mit einem gültigen "
          "JSON-Objekt ohne Markdown. /no_think")   # /no_think: Qwen3 soft switch, no reasoning block

_lock = threading.Lock()
_timers: dict[str, threading.Timer] = {}
_running: set[str] = set()
_failed: dict[str, tuple[str, float]] = {}


class ClaimEstimate(BaseModel):
    amount_eur: float | None = None
    low_eur: float | None = None
    high_eur: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale_de: str = ""
    basis: list[str] = []


def fingerprint(doc) -> str:
    vals = {k: f.get("value") for k, f in sorted(doc.get("fields", {}).items()) if f.get("value")}
    raw = json.dumps([doc.get("type"), vals, len(doc.get("photos") or [])], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def stale(doc) -> bool:
    return doc.get("type") in CLAIM_TYPES and (doc.get("claim_potential") or {}).get("fp") != fingerprint(doc)


def estimate(doc) -> dict:
    from . import docs
    lines = [f"- {label} ({key}): {doc['fields'][key]['value']}" for key, label, *_ in docs.fields_of(doc)
             if doc["fields"].get(key, {}).get("value")]
    if doc.get("photos"):
        lines.append(f"- Fotobelege: {len(doc['photos'])}")
    fields, mapping = sanitizer.mask("\n".join(lines) or "(keine)")
    prompt = (registry._prompt_raw("claim_potential.md")      # German prompt; the rationale stays German
              .replace("{doc_type}", docs.DOC_TYPES[doc["type"]]["title"]).replace("{fields}", fields))
    res, _ = llm_adapter.complete_json(prompt, ClaimEstimate, CFG.claim_model, system=SYSTEM, provider="qwen")
    out = sanitizer.unmask(res.model_dump(), mapping)
    amt = out["amount_eur"]
    if amt is None or amt <= 0:
        out.update(amount_eur=None, low_eur=None, high_eur=None)
    else:
        lo, hi = out["low_eur"], out["high_eur"]
        out["low_eur"] = round(min(lo, amt) if lo is not None and lo > 0 else amt)
        out["high_eur"] = round(max(hi, amt) if hi is not None else amt)
        out["amount_eur"] = round(amt)
    return out


def _store(doc_id, cp):
    """Writes only claim_potential; updated_at stays, so the estimate does not reorder the document history."""
    from . import docs
    with docs.LOCK:
        rows = load("docs", [])
        for d in rows:
            if d.get("id") == doc_id:
                d["claim_potential"] = cp
                save("docs", rows)
                return


def _run(doc_id):
    from . import docs
    with _lock:
        _timers.pop(doc_id, None)
        if doc_id in _running:
            return                       # the doc is re-checked on the next save / list after this run
        _running.add(doc_id)
    try:
        doc = docs.get(doc_id)
        if not doc or not stale(doc):
            return
        fp = fingerprint(doc)
        try:
            res = estimate(doc)
        except Exception as e:           # unreachable model, timeout, invalid JSON: store nothing, UI shows "–"
            log.warning("claim potential for %s failed: %s", doc_id, str(e)[:300])
            with _lock:
                _failed[doc_id] = (fp, time.time())
            return
        _store(doc_id, dict(res, fp=fp, at=now(), model=CFG.claim_model))
    finally:
        with _lock:
            _running.discard(doc_id)


def schedule(doc):
    """Debounced background estimate if the claim's fields changed since the last one. Never blocks, never raises."""
    if not CFG.claim_ready or not stale(doc) or not any(f.get("value") for f in doc.get("fields", {}).values()):
        return                           # nothing configured, nothing changed, or an empty new draft
    fp = fingerprint(doc)
    with _lock:
        f = _failed.get(doc["id"])
        if f and f[0] == fp and time.time() - f[1] < RETRY_AFTER_FAIL_S:
            return
        old = _timers.pop(doc["id"], None)
        if old:
            old.cancel()
        t = threading.Timer(DEBOUNCE_S, _run, args=(doc["id"],))
        t.daemon = True
        _timers[doc["id"]] = t
        t.start()
