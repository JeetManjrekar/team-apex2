"""Bridge to the team's nachweis_llm package (vendored, unmodified).
The package owns extraction, evidence/confidence gates, the critical-field reviewer, photo classification and
LLM metrics. This host owns persistence, locks, status, schedule maths, export and the rule-based fallback."""
import asyncio, os, threading, time, datetime as dt
from dataclasses import replace

from nachweis_llm.config import LLMSettings
from nachweis_llm.domain import DocumentType, EvidenceKind, EvidenceSource, ExtractionRequest, LockedField
from nachweis_llm.metrics import MetricsRecorder
from nachweis_llm.registry import DOCUMENT_REGISTRY, PHOTO_CATEGORIES

from .store import DATA

_s = LLMSettings.from_env()
SETTINGS = _s if os.environ.get("LLM_METRICS_FILE") else replace(_s, metrics_file=DATA / "llm_metrics.jsonl")
METRICS = MetricsRecorder(SETTINGS)
_state = {"services": None, "error": None, "tried": False}

KIND_TO_SRC = {"text": "message", "audio": "voice", "email": "email", "photo": "photo", "document_page": "document",
               "schedule_row": "schedule", "calendar": "calendar", "manual": "project"}


def services():
    if _state["services"] or _state["tried"]:
        return _state["services"]
    _state["tried"] = True
    if not SETTINGS.api_key:
        _state["error"] = "no OPENAI_API_KEY"
        return None
    try:
        from nachweis_llm.factory import create_services
        _state["services"] = create_services(SETTINGS)
    except Exception as e:   # missing openai SDK, bad provider etc. -> rules fallback
        _state["error"] = str(e)
    return _state["services"]


def status():
    svc = services()
    return {"mode": "llm" if svc else "rules", "model": SETTINGS.model if svc else None, "error": _state["error"],
            "reviewer": bool(svc and SETTINGS.reviewer_enabled), "threshold": SETTINGS.confidence_threshold,
            "critical_fields": list(SETTINGS.critical_fields)}


def record(stage, started_wall, started_perf, run_id="host", extra=None):
    METRICS.record(run_id=run_id, stage=stage, started_at=started_wall.astimezone(dt.timezone.utc),
                   duration_ms=(time.perf_counter() - started_perf) * 1000, model=None, extra=extra)


class Timer:
    def __init__(self, stage, run_id="host", **extra):
        self.stage, self.run_id, self.extra = stage, run_id, extra or None

    def __enter__(self):
        self.w, self.p = dt.datetime.now(dt.timezone.utc), time.perf_counter()
        return self

    def __exit__(self, *a):
        record(self.stage, self.w, self.p, self.run_id, self.extra)


def evidence_source(e):
    return EvidenceSource(evidence_id=e["id"], kind=EvidenceKind(e["kind"]), locator=e["locator"], excerpt=(e.get("excerpt") or "")[:3000])


def extract(dtype, text, evidence, locked, run_id):
    """Runs the package extractor. Returns (fields, gaps, extraction_result) or None if the LLM is unavailable/failed."""
    svc = services()
    if not svc:
        return None
    req = ExtractionRequest(run_id=run_id, project_id="nachweis-demo", document_type=DocumentType(dtype),
                            input_text=text, evidence=[evidence_source(e) for e in evidence],
                            locked_fields={k: LockedField(value=v, author="Bauleitung") for k, v in locked.items()})
    try:
        res = asyncio.run(svc.extractor.extract(req))
    except Exception as e:
        _state["error"] = f"extraction failed: {e}"
        return None
    fields = {k: {"value": c.value, "evidence_id": c.evidence_id, "confidence": c.confidence}
              for k, c in res.fields.items() if c.status == "proposed" and c.value is not None}
    gaps = [k for k, c in res.fields.items() if c.status == "needs_evidence"]
    return fields, gaps, res


def review_in_background(extraction, evidence, on_done):
    """Optional second pass on configured critical fields only. Never blocks the chat path."""
    svc = services()
    if not (svc and SETTINGS.reviewer_enabled):
        return False

    def work():
        try:
            r = asyncio.run(svc.reviewer.review(extraction, [dict(e) for e in evidence]))
            on_done({"status": r.status, "checked": r.checked_fields, "findings": [f.model_dump() for f in r.findings]})
        except Exception as e:
            on_done({"status": "failed", "error": str(e), "findings": []})
    threading.Thread(target=work, daemon=True).start()
    return True


def classify_photo(raw, mime, evidence_id, context=""):
    svc = services()
    if not svc or os.environ.get("PHOTO_LLM", "on").lower() == "off":
        return None
    try:
        return asyncio.run(svc.photos.classify(run_id=f"photo-{evidence_id}", evidence_id=evidence_id,
                                               image_bytes=raw, mime_type=mime, context=context))
    except Exception as e:
        _state["error"] = f"photo classification failed: {e}"
        return None
