from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..metrics import MetricsRecorder
from ..ports import LLMProvider


class EligibleReassignmentCandidate(BaseModel):
    """A candidate already selected by deterministic schedule/crew rules."""

    model_config = ConfigDict(extra="forbid")

    person_label: str
    current_activity: str
    proposed_activity: str
    target_crew: str
    duration: str | None = None
    reason: str
    qualification_check_passed: bool
    activity_unblocked: bool
    evidence_ids: list[str] = Field(default_factory=list)


class ReplannerPhrase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    suggestion_de: str
    proposal_only: bool = True
    evidence_ids: list[str] = Field(default_factory=list)


class ReplannerNarrator:
    """Only phrases an already-approved-by-rules candidate; it never chooses a worker/task."""

    def __init__(self, provider: LLMProvider, metrics: MetricsRecorder, model: str):
        self.provider = provider
        self.metrics = metrics
        self.model = model

    async def phrase(self, run_id: str, candidate: EligibleReassignmentCandidate) -> ReplannerPhrase:
        if not candidate.qualification_check_passed or not candidate.activity_unblocked:
            raise ValueError("Replanner may phrase only candidates that pass deterministic eligibility rules")
        started_wall = datetime.now(timezone.utc)
        started = time.perf_counter()
        response = await self.provider.generate_text(
            system_prompt=(
                "Formuliere auf Deutsch genau einen knappen, sachlichen Vorschlag zur Umplanung. "
                "Nutze nur die gelieferten Daten. Fuege keine Qualifikationen, Zeiten oder Tatsachen hinzu. "
                "Schreibe ausdruecklich als Vorschlag, nicht als bereits erfolgte Zuweisung. Keine Aktion ausfuehren."
            ),
            user_prompt=(
                "Bereits regelbasiert gepruefter Kandidat:\n"
                f"Person: {candidate.person_label}\nAktuelle Taetigkeit: {candidate.current_activity}\n"
                f"Vorgeschlagene Taetigkeit: {candidate.proposed_activity}\nZielkolonne: {candidate.target_crew}\n"
                f"Dauer: {candidate.duration or 'nicht angegeben'}\nGrund: {candidate.reason}\n"
                "Ausgabe nur als Vorschlag formulieren."
            ),
            model=self.model,
        )
        self.metrics.record(
            run_id=run_id,
            stage="replanner_wording",
            started_at=started_wall,
            duration_ms=(time.perf_counter() - started) * 1000,
            model=response.model,
            usage=response.usage,
            extra={"proposal_only": True},
        )
        return ReplannerPhrase(
            run_id=run_id,
            suggestion_de=response.text.strip(),
            proposal_only=True,
            evidence_ids=candidate.evidence_ids,
        )
