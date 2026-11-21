from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class LLMSettings:
    provider: str = "openai"
    api_key: str | None = None
    model: str = "gpt-4.1-mini"
    reviewer_model: str = "gpt-4.1-mini"
    reviewer_enabled: bool = False
    critical_fields: tuple[str, ...] = (
        "event_datetime",
        "location",
        "quantity",
        "instruction_by",
        "expected_ground",
        "found_ground",
    )
    request_timeout_seconds: int = 45
    confidence_threshold: float = 0.55
    max_context_chars: int = 24_000
    metrics_file: Path = Path("./var/llm_metrics.jsonl")
    input_cost_eur_per_1m: float = 0.0
    output_cost_eur_per_1m: float = 0.0

    @classmethod
    def from_env(cls) -> "LLMSettings":
        # Load a local .env for development; deployment environments can inject secrets directly.
        try:
            from dotenv import load_dotenv

            load_dotenv(override=False)
        except ImportError:  # pragma: no cover - optional if vendored outside this package
            pass
        critical_fields = tuple(
            item.strip()
            for item in os.getenv(
                "LLM_CRITICAL_FIELDS",
                "event_datetime,location,quantity,instruction_by,expected_ground,found_ground",
            ).split(",")
            if item.strip()
        )
        return cls(
            provider=os.getenv("LLM_PROVIDER", "openai").strip().lower(),
            api_key=os.getenv("OPENAI_API_KEY") or None,
            model=os.getenv("LLM_MODEL", "gpt-4.1-mini"),
            reviewer_model=os.getenv("LLM_REVIEWER_MODEL", os.getenv("LLM_MODEL", "gpt-4.1-mini")),
            reviewer_enabled=_as_bool(os.getenv("LLM_REVIEWER_ENABLED"), False),
            critical_fields=critical_fields,
            request_timeout_seconds=_as_int(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS"), 45),
            confidence_threshold=_as_float(os.getenv("LLM_CONFIDENCE_THRESHOLD"), 0.55),
            max_context_chars=_as_int(os.getenv("LLM_MAX_CONTEXT_CHARS"), 24_000),
            metrics_file=Path(os.getenv("LLM_METRICS_FILE", "./var/llm_metrics.jsonl")),
            input_cost_eur_per_1m=_as_float(os.getenv("LLM_INPUT_COST_EUR_PER_1M"), 0.0),
            output_cost_eur_per_1m=_as_float(os.getenv("LLM_OUTPUT_COST_EUR_PER_1M"), 0.0),
        )
