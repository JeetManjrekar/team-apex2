"""Extraction (LLM A) and intent routing — merged from APEX 2 `backend/modules/extraction.py`.

Public:
  detect_intent(text, run_id) -> Intent
  extract(doc_type, chunks, only_fields=None, *, run_id, today, focus) -> ExtractionResult

Guarantees enforced in code (never trusted to the model):
  * PII (e-mail, phone, IBAN) is masked in every chunk before the prompt is built, and restored in the values after
  * a value survives only if it cites at least one ref that was in `chunks` (else dropped -> follow-up question)
  * a value below CONFIDENCE_THRESHOLD is dropped the same way
  * fields marked `derived: true` in the registry are computed in Python, never by the LLM (numbers never from the LLM)
  * every required field that ends up empty gets a follow-up question
User-locked fields are protected one level up: core.docs.set_field never lets AI input overwrite them.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel

from . import sanitizer
from .llm_adapter import Usage, complete_json
from .llm_settings import CFG, today as cfg_today
from . import registry
from .i18n import T
from .registry import all_specs, doc_spec, prompt
from .sources import SourceChunk

IntentName = Literal["nachtrag_candidate", "behinderung", "mehrkosten", "mangel", "bedenken", "aktennotiz",
                     "daily_report_request", "followup_answer", "diary_note", "smalltalk"]


class FieldOut(BaseModel):
    value: Any | None = None
    source_refs: list[str] = []
    confidence: float | None = None
    derived: bool = False


class FollowUpOut(BaseModel):
    field_key: str | None
    question_de: str


class ExtractionResult(BaseModel):
    doc_type: str
    fields: dict[str, FieldOut]
    followups: list[FollowUpOut]
    assistant_message_de: str
    sources: dict[str, SourceChunk]       # every ref cited by a surviving field
    only_fields: list[str] | None = None
    usage: Usage = Usage()
    dropped: dict[str, str] = {}          # field_key -> reason (honesty metric)


class Intent(BaseModel):
    intent: IntentName
    doc_type: str | None = None
    by: Literal["rule", "llm", "default"] = "rule"


class _LLMField(BaseModel):
    value: Any | None = None
    source_refs: list[str] = []
    confidence: float | None = None


class _LLMOut(BaseModel):
    fields: dict[str, _LLMField] = {}
    followups: list[FollowUpOut] = []
    assistant_message_de: str = ""


class _IntentOut(BaseModel):
    intent: IntentName = "smalltalk"


def _timed(stage, run_id, model, **extra):
    from . import llm_bridge     # late import: llm_bridge imports this module
    return llm_bridge.timed(stage, run_id, model=model, **extra)


# ---------------------------------------------------------------- intent
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())


def rule_intent(text: str) -> Intent | None:
    """Registry `intent_keywords`: each entry is a list of terms that must all occur (case-insensitive)."""
    t = _norm(text or "")
    for spec in all_specs():
        for group in (spec.get("intent_keywords") or []) + (spec.get("intent_keywords_en") or []):
            terms = [group] if isinstance(group, str) else group
            if all(term.lower() in t for term in terms):
                return Intent(intent=spec["intent"], doc_type=spec["key"], by="rule")
    return None


def detect_intent(text: str, run_id: str = "adhoc") -> Intent:
    hit = rule_intent(text)
    if hit:
        return hit
    if not (text or "").strip() or not CFG.llm_ready:
        return Intent(intent="smalltalk", by="default")
    masked, _ = sanitizer.mask(text)
    with _timed("llm_intent", run_id, CFG.model_extract) as tm:
        out, usage = complete_json(prompt("intent.md").replace("{text}", masked), _IntentOut, CFG.model_extract)
        tm.add_usage(usage)
    doc = next((s["key"] for s in all_specs() if s["intent"] == out.intent), None)
    return Intent(intent=out.intent, doc_type=doc, by="llm")


class _ChatOut(BaseModel):
    reply: str = ""


def converse(text: str, context: str, run_id: str = "chat", lang: str | None = None) -> str:
    """Short conversational answer for messages that report no site incident (questions, tests, greetings).
    Same language as the user, max 3 sentences, steers back to the assistant's job; no project facts beyond `context`."""
    mapping: dict = {}
    masked = sanitizer.mask(text, mapping)[0]
    p = (prompt("chat.md").replace("{project}", context.split("\n", 1)[0].removeprefix("Projekt: ").removeprefix("Project: "))
         .replace("{context}", context).replace("{text}", masked)
         .replace("{lang}", {"de": "Deutsch", "en": "Englisch"}.get(lang, "der Sprache der Nachricht (Deutsch oder Englisch)")))
    with _timed("llm_chat", run_id, CFG.model_extract) as tm:
        out, usage = complete_json(p, _ChatOut, CFG.model_extract)
        tm.add_usage(usage)
    return sanitizer.unmask(out.reply.strip(), mapping)


# ---------------------------------------------------------------- python derivations
def _hours(start: str, end: str) -> float | None:
    try:
        a, b = dt.datetime.strptime(start, "%H:%M"), dt.datetime.strptime(end, "%H:%M")
    except (TypeError, ValueError):
        return None
    return (b - a).total_seconds() / 3600


def _derive_drilling(chunks: list[SourceChunk], pile_id: str | None) -> dict[str, FieldOut]:
    rows = [c for c in chunks if c.ref.startswith("drill:") and c.data.get("pile_id")]
    target = next((c for c in rows if c.data["pile_id"] == pile_id), None)
    if not target:
        return {}
    th = _hours(target.data.get("start"), target.data.get("end"))
    tdepth = float(target.data.get("depth_reached_m") or 0)
    refs = []
    for c in rows:
        if c is target:
            continue
        h, d = _hours(c.data.get("start"), c.data.get("end")), float(c.data.get("depth_reached_m") or 0)
        if h and d and d >= float(c.data.get("target_depth_m") or d):   # completed piles only
            refs.append((c, h, d))
    if not th or not tdepth or not refs:
        return {}
    ref_refs = [c.ref for c, _, _ in refs]
    out = {
        "drilling_time_h": FieldOut(value=round(th, 1), source_refs=[target.ref], confidence=1.0, derived=True),
        "drilling_time_ref_h": FieldOut(value=round(mean(h for _, h, _ in refs), 1), source_refs=ref_refs, confidence=1.0, derived=True),
        "drilling_time_ratio": FieldOut(value=round((th / tdepth) / mean(h / d for _, h, d in refs), 1),
                                        source_refs=[target.ref] + ref_refs, confidence=1.0, derived=True),
        "rig_hours": FieldOut(value=round(th, 1), source_refs=[target.ref], confidence=1.0, derived=True),
    }
    crew = target.data.get("crew_count")
    if crew:
        out["crew_hours"] = FieldOut(value=round(th * float(crew), 1), source_refs=[target.ref], confidence=1.0, derived=True)
    return out


def derive(doc_type: str, chunks: list[SourceChunk], focus: dict) -> dict[str, FieldOut]:
    if doc_type == "nachtragsmeldung":
        return _derive_drilling(chunks, focus.get("pile_id"))
    return {}


# ---------------------------------------------------------------- prompt rendering
def _render_fields(fields: list[dict]) -> str:
    lines = []
    for f in fields:
        tag = " (berechnet)" if f.get("derived") else ""
        req = "Pflicht" if f.get("required") else "optional"
        lines.append(f"- {f['key']}: {f['label_de']} [{f.get('type', 'text')}, {req}]{tag}")
    return "\n".join(lines)


def _render_sources(chunks: list[SourceChunk], derived: dict[str, FieldOut]) -> str:
    per_chunk = max(500, CFG.doc_text_max_chars // max(1, len(chunks)))
    parts = [f"<<{c.ref}>> {c.label_de}{' (' + c.locator + ')' if c.locator else ''}\n{c.text[:per_chunk]}" for c in chunks]
    if derived:
        parts.append("BERECHNETE WERTE (nur zur Information für assistant_message_de, nicht als Feld ausfüllen):\n"
                     + "\n".join(f"- {k} = {v.value}" for k, v in derived.items()))
    return "\n\n".join(parts)


def _coerce(value: Any, ftype: str, today: dt.date) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()) or value == []:
        return None
    if ftype == "number":
        if isinstance(value, (int, float)):
            return float(value)
        m = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
        return float(m.group(0).replace(",", ".")) if m else None
    if ftype == "datetime":
        s = str(value).strip()
        if re.fullmatch(r"\d{1,2}:\d{2}", s):                     # "10:00" -> today 10:00
            return f"{today.isoformat()}T{int(s.split(':')[0]):02d}:{s.split(':')[1]}"
        return s
    if ftype == "list":
        return value if isinstance(value, list) else [value]
    return value if isinstance(value, (str, int, float)) else json.dumps(value, ensure_ascii=False)


def _resolve(ref: str, known: dict) -> list[str]:
    """Exact ref if it was in the request. A bare recording ref ("audio:<id>", models sometimes drop the "@start-end"
    segment part) resolves to that recording's segment refs. Anything else is unknown and gets dropped by the caller."""
    ref = (ref or "").strip().strip("<>")
    if ref in known:
        return [ref]
    if ref.startswith("audio:") and "@" not in ref:
        return [k for k in known if k.startswith(ref + "@")]
    return []


# ---------------------------------------------------------------- public
def extract(doc_type: str, chunks: list[SourceChunk], only_fields: list[str] | None = None, *, run_id: str = "adhoc",
            today: dt.date | None = None, focus: dict | None = None) -> ExtractionResult:
    spec, today, focus = doc_spec(doc_type), today or cfg_today(), focus or {}
    fields = [f for f in spec["fields"] if not only_fields or f["key"] in only_fields]
    known = {c.ref: c for c in chunks}
    for c in chunks:                                   # alias refs resolve to their chunk
        for a in c.aliases:
            known.setdefault(a, c)
    derived = {k: v for k, v in derive(doc_type, chunks, focus).items() if any(f["key"] == k for f in fields)}

    mapping: dict = {}                                 # one shared PII mapping for the whole prompt
    masked = [c.model_copy(update={"text": sanitizer.mask(c.text, mapping)[0]}) for c in chunks]
    note = ("GEZIELTE NACHEXTRAKTION: Die Antwort des Bauleiters auf die Rückfrage steht unter den Quellen. Sie kann "
            "beliebig viele Felder der Feldliste in beliebiger Reihenfolge enthalten, auch andere als das zuletzt "
            "erfragte (z. B. Ort und Uhrzeit in einem Satz). Fülle jedes Feld der Feldliste, das die Antwort belegt; "
            "alle übrigen bleiben null.\n") if only_fields else ""
    text = (prompt(spec["prompt"]).replace("{rules}", prompt("extraction_rules.md"))
            .replace("{today}", today.isoformat()).replace("{only_fields_note}", note)
            .replace("{fields}", _render_fields(fields)).replace("{sources}", _render_sources(masked, derived)))

    with _timed("llm_extraction", run_id, CFG.model_extract, document_type=doc_type, chunks=len(chunks), targeted=bool(only_fields)) as tm:
        raw, usage = complete_json(text, _LLMOut, CFG.model_extract)
        tm.add_usage(usage)

    out_fields: dict[str, FieldOut] = {}
    dropped: dict[str, str] = {}
    for f in fields:
        key = f["key"]
        if f.get("derived"):
            out_fields[key] = derived.get(key, FieldOut(derived=True))
            continue
        r = raw.fields.get(key) or _LLMField()
        value = _coerce(sanitizer.unmask(r.value, mapping), f.get("type", "text"), today)
        refs = list(dict.fromkeys(x for ref in r.source_refs for x in _resolve(ref, known)))
        if value is not None and not refs:
            dropped[key] = "no_valid_source" if r.source_refs else "no_source"
            value = None
        if value is not None and r.confidence is not None and r.confidence < CFG.confidence_threshold:
            dropped[key] = "low_confidence"
            value = None
        if value is None:
            refs = []
        if isinstance(value, str) and value.strip() in refs:      # "doc:bgg@p14" -> "Baugrundgutachten, Seite 14"
            value = known[value.strip()].label_de
        for x in list(refs):                                       # add alias refs of cited chunks (drill:P07)
            refs += [a for a in known[x].aliases if a not in refs]
        out_fields[key] = FieldOut(value=value, source_refs=refs, confidence=r.confidence if value is not None else None)

    scope = {f["key"] for f in fields}
    qs: dict[str | None, str] = {}
    for fu in raw.followups:
        if fu.field_key in scope and out_fields[fu.field_key].value is None and fu.question_de.strip():
            qs.setdefault(fu.field_key, sanitizer.unmask(fu.question_de.strip(), mapping))
    for f in fields:                                   # registry order = priority
        if out_fields[f["key"]].value is None and not f.get("derived") and (f.get("required") or f["key"] in dropped):
            qs.setdefault(f["key"], registry.tr(f, "question") or (T("generic_q") + registry.tr(f, "label")))
    order = [f["key"] for f in fields]
    followups = [FollowUpOut(field_key=k, question_de=q) for k, q in sorted(qs.items(), key=lambda kv: order.index(kv[0]))]

    cited = {r for v in out_fields.values() for r in v.source_refs}
    return ExtractionResult(doc_type=doc_type, fields=out_fields, followups=followups,
                            assistant_message_de=sanitizer.unmask(raw.assistant_message_de.strip(), mapping),
                            sources={r: known[r] for r in cited if r in known}, only_fields=only_fields, usage=usage, dropped=dropped)
