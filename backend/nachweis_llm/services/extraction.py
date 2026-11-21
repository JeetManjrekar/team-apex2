from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..config import LLMSettings
from ..domain import (
    ExtractionRequest,
    ExtractionResult,
    FieldClaim,
    FollowUpQuestion,
)
from ..metrics import MetricsRecorder
from ..ports import LLMProvider
from ..prompts import EXTRACTION_SYSTEM_PROMPT, extraction_user_prompt
from ..registry import DOCUMENT_REGISTRY


def _extraction_schema(field_names: set[str]) -> dict[str, Any]:
    proposed_field = {
        "type": "object",
        "properties": {
            "value": {"type": ["string", "null"]},
            "evidence_id": {"type": ["string", "null"]},
            "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "note": {"type": ["string", "null"]},
        },
        "required": ["value", "evidence_id", "confidence", "note"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "properties": {name: proposed_field for name in sorted(field_names)},
                "required": sorted(field_names),
                "additionalProperties": False,
            }
        },
        "required": ["fields"],
        "additionalProperties": False,
    }


class ExtractionService:
    def __init__(self, provider: LLMProvider, settings: LLMSettings, metrics: MetricsRecorder):
        self.provider = provider
        self.settings = settings
        self.metrics = metrics

    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        spec = DOCUMENT_REGISTRY[request.document_type]
        started_wall = datetime.now(timezone.utc)
        started = time.perf_counter()
        response = await self.provider.generate_json(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=extraction_user_prompt(request, spec, self.settings.max_context_chars),
            schema_name=f"{request.document_type.value}_extraction",
            schema=_extraction_schema(spec.field_names),
            model=self.settings.model,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        self.metrics.record(
            run_id=request.run_id,
            stage="llm_extraction",
            started_at=started_wall,
            duration_ms=duration_ms,
            model=response.model,
            usage=response.usage,
            extra={"document_type": request.document_type.value},
        )

        raw_fields = response.data.get("fields", {})
        allowed_evidence = {item.evidence_id for item in request.evidence}
        known_fields = spec.field_names
        unsupported_names = sorted(set(raw_fields) - known_fields)
        fields: dict[str, FieldClaim] = {}

        for field_spec in spec.fields:
            name = field_spec.name
            # A human edit is immutable to this LLM pass. A later AI result can be proposed
            # by the host's versioning layer, but this service never replaces the lock.
            if name in request.locked_fields:
                locked = request.locked_fields[name]
                fields[name] = FieldClaim(
                    value=locked.value,
                    evidence_id=None,
                    confidence=1.0,
                    status="user_locked",
                    locked_by_user=True,
                    version=locked.version,
                    note=f"Manuell geaendert von {locked.author}",
                )
                continue

            raw = raw_fields.get(name) or {}
            value = raw.get("value")
            evidence_id = raw.get("evidence_id")
            confidence = raw.get("confidence")
            note = raw.get("note")
            valid_source = isinstance(evidence_id, str) and evidence_id in allowed_evidence
            normalized_value = str(value).strip() if value is not None else ""
            try:
                normalized_confidence = float(confidence) if confidence is not None else None
            except (TypeError, ValueError):
                normalized_confidence = None
            valid_confidence = (
                normalized_confidence is not None
                and normalized_confidence >= self.settings.confidence_threshold
            )

            # Non-empty AI values without a source, or below the configured confidence
            # threshold, are discarded and become follow-up gaps.
            if not normalized_value or not valid_source or not valid_confidence:
                fields[name] = FieldClaim(
                    value=None,
                    evidence_id=None,
                    confidence=normalized_confidence,
                    status="needs_evidence" if value is not None else "missing",
                    note=(note or "Keine ausreichend belastbare Quellenzuordnung.") if value is not None else note,
                )
            else:
                fields[name] = FieldClaim(
                    value=normalized_value,
                    evidence_id=evidence_id,
                    confidence=normalized_confidence,
                    status="proposed",
                    note=note,
                )

        # Ask only for required blanks or fields the model attempted but could not support.
        # Optional fields that were simply not mentioned do not create noisy questions.
        follow_up_names = {
            name for name in spec.required_fields if fields[name].value is None
        } | {
            name for name, claim in fields.items() if claim.status == "needs_evidence"
        }
        missing_fields = [field.name for field in spec.fields if field.name in follow_up_names]
        follow_ups = [
            FollowUpQuestion(
                field_name=field.name,
                question_de=field.question_de,
                reason="Die Angabe fehlt oder ist nicht ausreichend durch eine Quelle belegt.",
            )
            for field in spec.fields
            if field.name in missing_fields
        ]
        return ExtractionResult(
            run_id=request.run_id,
            project_id=request.project_id,
            event_id=request.event_id,
            document_type=request.document_type,
            fields=fields,
            missing_fields=missing_fields,
            follow_up_questions=follow_ups,
            unsupported_field_names=unsupported_names,
        )
