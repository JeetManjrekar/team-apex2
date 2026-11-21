from __future__ import annotations

import time
from datetime import datetime, timezone

from ..domain import CompletenessChecklist, CompletenessItem, DocumentDraft, ExtractionResult
from ..metrics import MetricsRecorder
from ..registry import DOCUMENT_REGISTRY


class CompletenessService:
    """Formal field-presence checklist from the configured company/document registry."""

    def check(self, extraction: ExtractionResult) -> CompletenessChecklist:
        spec = DOCUMENT_REGISTRY[extraction.document_type]
        items = []
        for field in spec.fields:
            claim = extraction.fields.get(field.name)
            present = bool(claim and claim.value is not None)
            evidence_attached = bool(claim and (claim.evidence_id or claim.locked_by_user))
            items.append(
                CompletenessItem(
                    field_name=field.name,
                    label_de=field.label_de,
                    present=present,
                    evidence_attached=evidence_attached,
                )
            )
        missing = [item.field_name for item in items if item.field_name in spec.required_fields and not item.present]
        return CompletenessChecklist(document_type=extraction.document_type, items=items, missing_fields=missing)


class DocumentDraftService:
    """Builds a source-preserving draft body; Word/PDF rendering stays outside this package."""

    def __init__(self, metrics: MetricsRecorder | None = None):
        self.metrics = metrics

    def build(self, extraction: ExtractionResult) -> DocumentDraft:
        started_wall = datetime.now(timezone.utc)
        started = time.perf_counter()
        spec = DOCUMENT_REGISTRY[extraction.document_type]
        used_fields: list[str] = []
        evidence_ids: list[str] = []
        lines = [spec.title_de, ""]

        for field_spec in spec.fields:
            claim = extraction.fields.get(field_spec.name)
            if not claim or claim.value is None:
                continue
            if not claim.locked_by_user and not claim.evidence_id:
                continue
            lines.append(f"{field_spec.label_de}: {claim.value}")
            if claim.evidence_id:
                lines.append(f"  Quellenreferenz: {claim.evidence_id}")
                evidence_ids.append(claim.evidence_id)
            elif claim.locked_by_user:
                lines.append("  Quellenreferenz: manuelle Eingabe durch Benutzer")
            lines.append("")
            used_fields.append(field_spec.name)

        missing = sorted(
            set(extraction.missing_fields)
            | {name for name in spec.required_fields if name not in used_fields}
        )
        if missing:
            field_labels = {field.name: field.label_de for field in spec.fields}
            lines.extend(
                [
                    "Offene Angaben (vor Freigabe ergaenzen):",
                    *[f"- {field_labels[name]}" for name in missing],
                ]
            )

        if self.metrics:
            self.metrics.record(
                run_id=extraction.run_id,
                stage="document_generation",
                started_at=started_wall,
                duration_ms=(time.perf_counter() - started) * 1000,
                model=None,
                extra={"document_type": extraction.document_type.value},
            )

        return DocumentDraft(
            run_id=extraction.run_id,
            document_type=extraction.document_type,
            title_de=spec.title_de,
            body_de="\n".join(lines).strip(),
            used_field_names=used_fields,
            missing_field_names=missing,
            evidence_ids=sorted(set(evidence_ids)),
        )
