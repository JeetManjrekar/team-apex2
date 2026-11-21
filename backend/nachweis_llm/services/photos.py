from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..config import LLMSettings
from ..metrics import MetricsRecorder
from ..ports import ImageVisionProvider
from ..registry import PHOTO_CATEGORIES


class PhotoClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    category: str | None
    caption_de: str
    confidence: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    needs_human_confirmation: bool


PHOTO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(PHOTO_CATEGORIES)},
        "caption_de": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["category", "caption_de", "confidence", "tags"],
    "additionalProperties": False,
}


class PhotoClassificationService:
    def __init__(self, provider: ImageVisionProvider, settings: LLMSettings, metrics: MetricsRecorder):
        self.provider = provider
        self.settings = settings
        self.metrics = metrics

    async def classify(
        self,
        *,
        run_id: str,
        evidence_id: str,
        image_bytes: bytes,
        mime_type: str,
        context: str = "",
    ) -> PhotoClassification:
        if not image_bytes:
            raise ValueError("image_bytes must not be empty")
        started_wall = datetime.now(timezone.utc)
        started = time.perf_counter()
        response = await self.provider.classify_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            allowed_categories=PHOTO_CATEGORIES,
            context=context,
            model=self.settings.model,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        self.metrics.record(
            run_id=run_id,
            stage="photo_classification",
            started_at=started_wall,
            duration_ms=duration_ms,
            model=response.model,
            usage=response.usage,
            extra={"evidence_id": evidence_id},
        )
        data = response.data
        category = data.get("category")
        confidence = float(data.get("confidence", 0.0))
        valid = category in PHOTO_CATEGORIES
        return PhotoClassification(
            evidence_id=evidence_id,
            category=category if valid else None,
            caption_de=str(data.get("caption_de", "")),
            confidence=confidence,
            tags=[str(tag) for tag in data.get("tags", [])],
            needs_human_confirmation=(not valid or confidence < self.settings.confidence_threshold),
        )
