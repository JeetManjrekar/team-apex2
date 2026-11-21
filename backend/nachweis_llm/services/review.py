from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..config import LLMSettings
from ..domain import ExtractionResult, ReviewerResult
from ..metrics import MetricsRecorder
from ..ports import LLMProvider
from ..prompts import REVIEW_SYSTEM_PROMPT, reviewer_user_prompt


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string"},
                    "issue": {
                        "type": "string",
                        "enum": ["missing_source", "contradiction", "unclear", "unsupported_value"],
                    },
                    "explanation_de": {"type": "string"},
                    "suggested_action_de": {"type": "string"},
                },
                "required": ["field_name", "issue", "explanation_de", "suggested_action_de"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


class CriticalFieldReviewer:
    def __init__(self, provider: LLMProvider, settings: LLMSettings, metrics: MetricsRecorder):
        self.provider = provider
        self.settings = settings
        self.metrics = metrics

    async def review(self, extraction: ExtractionResult, evidence: list[dict[str, Any]]) -> ReviewerResult:
        if not self.settings.reviewer_enabled:
            return ReviewerResult(run_id=extraction.run_id, status="disabled")

        critical = {
            name: extraction.fields[name].model_dump(mode="json")
            for name in self.settings.critical_fields
            if name in extraction.fields
        }
        if not critical:
            return ReviewerResult(run_id=extraction.run_id, status="no_configured_critical_fields")

        started_wall = datetime.now(timezone.utc)
        started = time.perf_counter()
        response = await self.provider.generate_json(
            system_prompt=REVIEW_SYSTEM_PROMPT,
            user_prompt=reviewer_user_prompt(
                document_type=extraction.document_type.value,
                critical_fields=critical,
                evidence=evidence,
            ),
            schema_name="critical_field_review",
            schema=REVIEW_SCHEMA,
            model=self.settings.reviewer_model,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        self.metrics.record(
            run_id=extraction.run_id,
            stage="llm_critical_review",
            started_at=started_wall,
            duration_ms=duration_ms,
            model=response.model,
            usage=response.usage,
            extra={"checked_fields": sorted(critical)},
        )

        findings = response.data.get("findings", [])
        # Ignore any model finding outside the configured critical-field set.
        safe_findings = [item for item in findings if item.get("field_name") in critical]
        from ..domain import ReviewerFinding

        return ReviewerResult(
            run_id=extraction.run_id,
            status="completed",
            checked_fields=sorted(critical),
            findings=[ReviewerFinding.model_validate(item) for item in safe_findings],
        )
