"""Reviewer (LLM B) — merged from APEX 2 `adapters/review_judges.py` + `modules/review.py`, on the JSON store.

Guardrails (all in this module):
  * off unless ENABLE_REVIEWER_LLM=true (or the older LLM_REVIEWER_ENABLED=true)
  * only REVIEW_CRITICAL_FIELDS that are filled, AI-authored and not locked
  * start() marks them "being_verified" synchronously (the UI shows it at once), then judges in a daemon thread
  * judges see ONLY the chunks each field cites; they say supported / not supported, never propose values
  * REVIEWER_MODE=single: judge A. double_judge: judges A and B in parallel, unanimous agreement required
  * the reviewer never writes a value or a status; a verdict is written only if the field is still unlocked and its
    `version` is unchanged since the review started (a user edit meanwhile wins)
  * failure or REVIEW_TIMEOUT_S: fields revert to their previous review state, nothing else is written
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel

from . import docs, sanitizer
from .llm_adapter import complete_json
from .llm_settings import CFG
from .registry import prompt

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="review")


class JudgeInput(BaseModel):
    field_key: str
    label_de: str
    value: Any
    cited_chunks: list[dict]             # [{"source_ref", "text"}] only the chunks this field cites


class Verdict(BaseModel):
    field_key: str
    supported: bool
    note_de: str | None = None
    followup_question_de: str | None = None
    judges: dict[str, bool] = {}


class _JudgeOut(BaseModel):
    verdicts: list[Verdict]


def _timed(stage, run_id, model, **extra):
    from . import llm_bridge
    return llm_bridge.timed(stage, run_id, model=model, **extra)


# ---------------------------------------------------------------- judges
def _judge(model: str, provider: str, items: list[JudgeInput], run_id: str, tag: str) -> list[Verdict]:
    if not items:
        return []
    mapping: dict = {}
    payload = [{"field_key": i.field_key, "label_de": i.label_de, "value": sanitizer.mask(str(i.value), mapping)[0],
                "quellen": [{"source_ref": c["source_ref"], "text": sanitizer.mask(c["text"], mapping)[0]} for c in i.cited_chunks]}
               for i in items]
    text = prompt("reviewer.md").replace("{items}", json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    with _timed("llm_review", run_id, model, judge=tag, provider=provider, items=len(items)) as t:
        out, usage = complete_json(text, _JudgeOut, model, provider=provider)
        t.add_usage(usage)
    wanted, seen = {i.field_key for i in items}, {}
    for v in out.verdicts:               # drop unknown keys and duplicates; never invent a verdict
        if v.field_key in wanted and v.field_key not in seen:
            seen[v.field_key] = v.model_copy(update={"judges": {tag: v.supported}, "note_de": sanitizer.unmask(v.note_de, mapping),
                                                     "followup_question_de": sanitizer.unmask(v.followup_question_de, mapping)})
    return list(seen.values())


def _judge_a(items, run_id):
    return _judge(CFG.judge_a_model or CFG.model_review, CFG.provider, items, run_id, "a")


def _judge_b(items, run_id):
    return _judge(CFG.judge_b_model or CFG.model_review, CFG.judge_b_provider or CFG.provider, items, run_id, "b")


def _note(v: Verdict, extra: str) -> str:
    return "; ".join(x for x in [v.note_de, extra] if x)


def combine(a: list[Verdict] | None, b: list[Verdict] | None) -> list[Verdict]:
    """Unanimous: verified only if every answering judge supports the value."""
    if a is None and b is None:
        raise RuntimeError("Both review judges failed")
    if a is None or b is None:
        return [v.model_copy(update={"note_de": _note(v, "nur ein Prüfer")}) for v in (a if a is not None else b)]
    by_b, out = {v.field_key: v for v in b}, []
    for va in a:
        vb = by_b.get(va.field_key)
        if vb is None:
            out.append(va.model_copy(update={"note_de": _note(va, "nur ein Prüfer")}))
            continue
        judges = {"a": va.supported, "b": vb.supported}
        if va.supported and vb.supported:
            out.append(Verdict(field_key=va.field_key, supported=True, judges=judges))
            continue
        notes = [n for n in (va.note_de, vb.note_de) if n]
        note = ("Prüfer uneinig" + (f": {notes[0]}" if notes else "")) if va.supported != vb.supported \
            else ("; ".join(dict.fromkeys(notes)) or "Wert durch Quelle nicht gestützt")
        q = next((x.followup_question_de for x in (va, vb) if not x.supported and x.followup_question_de), None)
        out.append(Verdict(field_key=va.field_key, supported=False, note_de=note, followup_question_de=q, judges=judges))
    seen = {v.field_key for v in out}
    out += [vb.model_copy(update={"note_de": _note(vb, "nur ein Prüfer")}) for vb in b if vb.field_key not in seen]
    return out


def judge_fields(items: list[JudgeInput], run_id: str = "review") -> list[Verdict]:
    if not items:
        return []
    if CFG.reviewer_mode != "double_judge":
        return _judge_a(items, run_id)
    fa, fb = _POOL.submit(_judge_a, items, run_id), _POOL.submit(_judge_b, items, run_id)
    res = []
    for f in (fa, fb):
        try:
            res.append(f.result())
        except Exception:
            res.append(None)
    return combine(res[0], res[1])


# ---------------------------------------------------------------- orchestration on the JSON store
def enabled() -> bool:
    return CFG.reviewer_enabled and CFG.llm_ready


def _candidates(doc) -> dict[str, dict]:
    crit, snap = set(CFG.critical_fields), {}
    for k, f in doc["fields"].items():
        if (k in crit and f.get("value") and not f.get("locked") and f.get("by") == "ai"
                and (f.get("source") or {}).get("chunks") and (f.get("review") or {}).get("status") != "being_verified"):
            snap[k] = {"version": f.get("version", 0), "prev": f.get("review")}
    return snap


def start(doc_id: str) -> bool:
    """Mark critical fields 'being_verified' now, judge them in the background. Returns False if nothing to review."""
    if not enabled():
        return False
    doc = docs.get(doc_id)
    snap = _candidates(doc) if doc else {}
    if not snap:
        return False
    for k in snap:
        doc["fields"][k]["review"] = {"status": "being_verified"}
    doc["review"] = {"status": "running", "mode": CFG.reviewer_mode, "fields": sorted(snap), "findings": []}
    docs.put(doc)
    threading.Thread(target=_run, args=(doc_id, snap), daemon=True).start()
    return True


def _write(doc_id: str, apply):
    with docs.LOCK:
        doc = docs.get(doc_id)
        if doc:
            apply(doc)
            docs.put(doc)


def _run(doc_id: str, snap: dict[str, dict]):
    run_id, t0 = f"review-{doc_id}-{int(time.time())}", time.perf_counter()
    doc = docs.get(doc_id)
    labels = {f[0]: f[1] for f in docs.DOC_TYPES[doc["type"]]["fields"]}
    # fields edited or locked since start() are no longer the AI value we were asked to check: skip them
    current = {k: doc["fields"].get(k) or {} for k in snap}
    items = [JudgeInput(field_key=k, label_de=labels.get(k, k), value=f["value"],
                        cited_chunks=[{"source_ref": c["ref"], "text": c["text"]} for c in (f.get("source") or {}).get("chunks", [])])
             for k, f in current.items()
             if not f.get("locked") and f.get("version", 0) == snap[k]["version"] and (f.get("source") or {}).get("chunks")]
    try:
        verdicts = _POOL.submit(judge_fields, items, run_id).result(timeout=CFG.review_timeout_s) if items else []
        error = None
    except Exception as e:
        verdicts, error = [], str(e)[:300]

    def apply(d):
        by_key = {v.field_key: v for v in verdicts}
        findings = []
        for k, s in snap.items():
            f = d["fields"].get(k)
            if f is None:
                continue
            unchanged = not f.get("locked") and f.get("version", 0) == s["version"]
            v = by_key.get(k)
            if not unchanged or v is None:              # edited/locked meanwhile, or no verdict: restore previous state
                if (f.get("review") or {}).get("status") == "being_verified":
                    f["review"] = s["prev"]
                continue
            f["review"] = {"status": "verified" if v.supported else "flagged", "note_de": v.note_de, "judges": v.judges}
            if not v.supported:
                # same shape the review panel already renders (frontend/js/app.js)
                findings.append({"field_name": k, "issue": "nicht belegt" if len(v.judges) < 2 or not any(v.judges.values()) else "Prüfer uneinig",
                                 "explanation_de": v.note_de or "Wert durch Quelle nicht gestützt",
                                 "suggested_action_de": v.followup_question_de or "Bitte Wert und Quelle prüfen."})
        d["review"] = {"status": "failed" if error else "done", "mode": CFG.reviewer_mode, "fields": sorted(snap),
                       "findings": findings, "error": error, "duration_ms": round((time.perf_counter() - t0) * 1000)}
    _write(doc_id, apply)
