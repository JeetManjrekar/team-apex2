from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from .domain import EvidenceSource, ExtractionRequest, ExtractionResult
from .factory import LLMServices


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extraction: ExtractionResult
    evidence: list[EvidenceSource]


def build_router(services: LLMServices):
    """Create an optional FastAPI router. The host app owns auth, persistence and approvals."""
    try:
        from fastapi import APIRouter, File, Form, HTTPException, UploadFile
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install FastAPI support: pip install -e '.[api]'") from exc

    router = APIRouter(prefix="/api/llm", tags=["LLM"])

    @router.post("/extract", response_model=ExtractionResult)
    async def extract(request: ExtractionRequest) -> ExtractionResult:
        try:
            return await services.extractor.extract(request)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM extraction failed: {exc}") from exc

    @router.post("/review")
    async def review_critical_fields(request: ReviewRequest):
        try:
            evidence = [item.model_dump(mode="json") for item in request.evidence]
            return await services.reviewer.review(request.extraction, evidence)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Critical-field review failed: {exc}") from exc

    @router.post("/draft")
    def create_draft(extraction: ExtractionResult):
        return services.drafts.build(extraction)

    @router.post("/completeness")
    def completeness(extraction: ExtractionResult):
        return services.completeness.check(extraction)

    @router.post("/photos/classify")
    async def classify_photo(
        evidence_id: str = Form(...),
        context: str = Form(default=""),
        image: UploadFile = File(...),
    ):
        try:
            content = await image.read()
            return await services.photos.classify(
                run_id="photo-" + evidence_id,
                evidence_id=evidence_id,
                image_bytes=content,
                mime_type=image.content_type or "image/jpeg",
                context=context,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Photo classification failed: {exc}") from exc

    return router
