from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LLMSettings
from .ports import TokenUsage


class MetricsRecorder:
    """Append-only JSONL metrics writer shared by all LLM pipeline stages."""

    def __init__(self, settings: LLMSettings):
        self._path = settings.metrics_file
        self._settings = settings
        self._lock = threading.Lock()

    def record(
        self,
        *,
        run_id: str,
        stage: str,
        started_at: datetime,
        duration_ms: float,
        model: str | None = None,
        usage: TokenUsage | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        usage = usage or TokenUsage()
        cost = (
            usage.input_tokens * self._settings.input_cost_eur_per_1m
            + usage.output_tokens * self._settings.output_cost_eur_per_1m
        ) / 1_000_000
        row: dict[str, Any] = {
            "run_id": run_id,
            "stage": stage,
            "started_at": started_at.astimezone(timezone.utc).isoformat(),
            "duration_ms": round(max(duration_ms, 0.0), 2),
            "model": model,
            "tokens_in": usage.input_tokens,
            "tokens_out": usage.output_tokens,
            "cost_eur": round(cost, 8),
        }
        if extra:
            row["extra"] = extra
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    @staticmethod
    def new_run_id() -> str:
        return str(uuid.uuid4())
