"""The only place where the host meets the LLM layer.

After the APEX 2 merge:
  * extraction + intent  -> core.llm_extract (registry YAML, source-ref gate, confidence gate, Python derivations)
  * critical-field review -> core.review (single / double judge, guarded writes)
  * photo classification + replanner wording -> the vendored nachweis_llm package (unmodified)
  * metrics: every stage appends one JSONL row via nachweis_llm.metrics.MetricsRecorder (shared format)
The host owns persistence, locks, status, schedule maths, export and the rule-based fallback."""
import asyncio, json, os, threading, time, datetime as dt
from dataclasses import replace

from nachweis_llm.config import LLMSettings
from nachweis_llm.metrics import MetricsRecorder
from nachweis_llm.ports import TokenUsage

from .llm_settings import CFG
from .sources import KIND_TO_SRC  # noqa: F401  (re-exported for core.assistant)
from .store import DATA

_s = LLMSettings.from_env()
_s = _s if os.environ.get("LLM_METRICS_FILE") else replace(_s, metrics_file=DATA / "llm_metrics.jsonl")
# nachweis_llm only ships an OpenAI adapter and is used here only for photo classification + replanner wording
# (with OPENAI_API_KEY). LLM_PROVIDER belongs to the main pipeline (may be groq / anthropic), so pin it here.
SETTINGS = replace(_s, provider="openai")
METRICS = MetricsRecorder(SETTINGS)
_state = {"services": None, "error": None, "tried": False}



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
    from . import review
    ready = CFG.llm_ready
    return {"mode": "llm" if ready else "rules", "provider": CFG.provider if ready else None,
            "model": CFG.model_extract if ready else None, "cache_mode": CFG.cache_mode, "error": _state["error"],
            "reviewer": review.enabled(), "reviewer_mode": CFG.reviewer_mode if review.enabled() else None,
            "threshold": CFG.confidence_threshold, "critical_fields": list(CFG.critical_fields),
            "photo_llm": bool(services()), "demo_today": CFG.demo_today.isoformat() if CFG.demo_today else None}


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


class timed:
    """Like Timer, plus model, token usage and cost: `with timed("llm_extraction", run_id, model=m) as t: ...; t.add_usage(u)`.
    Failed stages are recorded too (extra.ok = false)."""

    def __init__(self, stage, run_id="host", model=None, **extra):
        self.stage, self.run_id, self.model, self.meta = stage, run_id, model, dict(extra)
        self.usage = TokenUsage()
        self.extra_cost_eur = 0.0          # non-token cost, e.g. cloud STT priced per minute

    def add_cost(self, eur):
        self.extra_cost_eur += float(eur or 0)

    def add_usage(self, u):
        self.usage = TokenUsage(self.usage.input_tokens + int(getattr(u, "input", 0) or 0),
                                self.usage.output_tokens + int(getattr(u, "output", 0) or 0))
        if getattr(u, "model", ""):
            self.model = u.model
        if getattr(u, "cached", False):
            self.meta["cached"] = True

    def __enter__(self):
        self.w, self.p = dt.datetime.now(dt.timezone.utc), time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.meta.update(ok=False, error=str(exc)[:200])
        ms = (time.perf_counter() - self.p) * 1000
        if not self.extra_cost_eur:
            METRICS.record(run_id=self.run_id, stage=self.stage, started_at=self.w, duration_ms=ms, model=self.model,
                           usage=self.usage, extra=self.meta or None)
            return
        # same row format as MetricsRecorder, with the non-token cost added to cost_eur
        tok = (self.usage.input_tokens * SETTINGS.input_cost_eur_per_1m + self.usage.output_tokens * SETTINGS.output_cost_eur_per_1m) / 1_000_000
        row = {"run_id": self.run_id, "stage": self.stage, "started_at": self.w.isoformat(), "duration_ms": round(max(ms, 0.0), 2),
               "model": self.model, "tokens_in": self.usage.input_tokens, "tokens_out": self.usage.output_tokens,
               "cost_eur": round(tok + self.extra_cost_eur, 8)}
        if self.meta:
            row["extra"] = self.meta
        path = METRICS._path
        path.parent.mkdir(parents=True, exist_ok=True)
        with METRICS._lock, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract(dtype, chunks, run_id, only_fields=None, focus=None):
    """Merged APEX 2 extractor. Returns the ExtractionResult, or None if no model is configured / the call failed
    (the caller then runs the rule-based fallback under the same gates)."""
    if not CFG.llm_ready:
        return None
    from . import llm_extract
    try:
        return llm_extract.extract(dtype, chunks, only_fields, run_id=run_id, focus=focus or {})
    except Exception as e:
        _state["error"] = f"extraction failed: {str(e)[:300]}"
        return None


def detect_intent(text, run_id="host"):
    from . import llm_extract
    try:
        return llm_extract.detect_intent(text, run_id)
    except Exception as e:
        _state["error"] = f"intent failed: {str(e)[:300]}"
        return llm_extract.Intent(intent="smalltalk", by="default")


def converse(text, context, run_id="chat"):
    """Conversational answer for non-incident messages. None without a model or on failure (caller uses a help text)."""
    if not CFG.llm_ready:
        return None
    from . import llm_extract
    try:
        return llm_extract.converse(text, context, run_id) or None
    except Exception as e:
        _state["error"] = f"chat failed: {str(e)[:300]}"
        return None


def start_review(doc_id):
    """Background critical-field review (never blocks the chat path). Returns True if a review was started."""
    from . import review
    try:
        return review.start(doc_id)
    except Exception as e:
        _state["error"] = f"review failed to start: {str(e)[:300]}"
        return False


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


def phrase_replan(candidate):
    """German one-sentence wording for a rules-approved reassignment candidate (EligibleReassignmentCandidate).
    Returns the ReplannerPhrase, or None without key / on failure (caller falls back to a template sentence)."""
    svc = services()
    if not svc or getattr(svc, "replanner", None) is None:
        return None
    try:
        return asyncio.run(svc.replanner.phrase(run_id=f"replan-{int(time.time() * 1000)}", candidate=candidate))
    except Exception as e:
        _state["error"] = f"replanner wording failed: {e}"
        return None
