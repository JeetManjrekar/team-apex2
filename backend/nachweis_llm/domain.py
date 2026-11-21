from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentType(str, Enum):
    NACHTRAGSMELDUNG = "nachtragsmeldung"
    BAUTAGESBERICHT = "bautagesbericht"
    BEHINDERUNGSANZEIGE = "behinderungsanzeige"
    MEHRKOSTENANZEIGE = "mehrkostenanzeige"
    MAENGELANZEIGE = "maengelanzeige"
    BEDENKENANMELDUNG = "bedenkenanmeldung"
    AKTENNOTIZ = "aktennotiz"


class EvidenceKind(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    PHOTO = "photo"
    EMAIL = "email"
    DOCUMENT_PAGE = "document_page"
    SCHEDULE_ROW = "schedule_row"
    CALENDAR = "calendar"
    MANUAL = "manual"


class EvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    kind: EvidenceKind
    locator: str = Field(min_length=1, description="e.g. audio 00:12-00:18, page 14, email quote")
    excerpt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LockedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
    author: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = Field(default=1, ge=1)


class FieldClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any | None = None
    evidence_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str = "proposed"
    locked_by_user: bool = False
    version: int = Field(default=1, ge=1)
    note: str | None = None


class FollowUpQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str
    question_de: str
    reason: str


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    event_id: str | None = None
    document_type: DocumentType
    input_text: str = Field(min_length=1)
    evidence: list[EvidenceSource] = Field(min_length=1, max_length=100)
    context_documents: list[str] = Field(default_factory=list, description="Page-tagged source excerpts")
    locked_fields: dict[str, LockedField] = Field(default_factory=dict)
    locale: str = "de-DE"

    @field_validator("evidence")
    @classmethod
    def evidence_ids_must_be_unique(cls, values: list[EvidenceSource]) -> list[EvidenceSource]:
        ids = [item.evidence_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence_id values must be unique within one request")
        return values


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    project_id: str
    event_id: str | None = None
    document_type: DocumentType
    fields: dict[str, FieldClaim]
    missing_fields: list[str]
    follow_up_questions: list[FollowUpQuestion]
    unsupported_field_names: list[str] = Field(default_factory=list)
    reviewer_status: str = "not_requested"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewerFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str
    issue: str
    explanation_de: str
    suggested_action_de: str


class ReviewerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    checked_fields: list[str] = Field(default_factory=list)
    findings: list[ReviewerFinding] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    document_type: DocumentType
    title_de: str
    body_de: str
    used_field_names: list[str]
    missing_field_names: list[str]
    evidence_ids: list[str]
    footer_de: str = "Entwurf mit KI-Unterstützung erstellt, geprüft von [Name], [Datum]"
    status: str = "draft"


class CompletenessItem(BaseModel):
    field_name: str
    label_de: str
    present: bool
    evidence_attached: bool


class CompletenessChecklist(BaseModel):
    document_type: DocumentType
    items: list[CompletenessItem]
    missing_fields: list[str]
    note_de: str = "Formale Vollständigkeitsübersicht anhand der konfigurierten Vorlage; keine rechtliche Bewertung."
