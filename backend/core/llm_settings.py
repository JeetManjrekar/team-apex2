"""Settings for the LLM pipeline (merged from APEX 2 `backend/config.py`, LLM/STT/reviewer part only).

Read once from the environment (app.py loads backend/.env first). APEX 2 names are primary; the repo's older names are
accepted as fallbacks so existing .env files keep working:
  LLM_API_KEY      <- OPENAI_API_KEY          LLM_MODEL_EXTRACT <- LLM_MODEL
  LLM_MODEL_REVIEW <- LLM_REVIEWER_MODEL      ENABLE_REVIEWER_LLM <- LLM_REVIEWER_ENABLED
  CONFIDENCE_THRESHOLD <- LLM_CONFIDENCE_THRESHOLD
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def _e(*names, default=""):
    for n in names:
        v = os.environ.get(n)
        if v is not None and v.strip() != "" and not v.strip().startswith("#"):   # "KEY=  # comment" = empty
            return v.strip()
    return default


def _bool(v: str) -> bool:
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _csv(v: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in v.split(",") if x.strip())


def _f(v: str, d: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


DEFAULT_CRITICAL = ("occurred_at,location,expected_ground,found_ground,depth_rock_m,drilling_time_h,drilling_time_ref_h,"
                    "ordered_by,quantity,start_time")


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "openai"                  # openai | anthropic | groq
    api_key: str = ""
    model_extract: str = ""
    model_review: str = ""
    temperature: float = 0.0
    reasoning_effort: str = ""
    timeout_s: int = 45
    cache_mode: str = "off"                   # off | record | replay (replay = demo without network)
    cache_dir: Path = BACKEND / "data" / "llm_cache"
    doc_text_max_chars: int = 20000
    confidence_threshold: float = 0.6
    input_cost_eur_per_1m: float = 0.0
    output_cost_eur_per_1m: float = 0.0
    # reviewer (LLM B)
    reviewer_enabled: bool = False
    reviewer_mode: str = "single"             # single | double_judge
    critical_fields: tuple[str, ...] = field(default_factory=lambda: _csv(DEFAULT_CRITICAL))
    judge_a_model: str = ""
    judge_b_model: str = ""
    judge_b_provider: str = ""
    judge_b_api_key: str = ""
    review_timeout_s: int = 30
    # vision (scanned PDFs; photos still go through nachweis_llm)
    vision_provider: str = "openai"
    vision_model: str = ""
    # claim potential (Qwen3-14B behind any OpenAI-compatible endpoint: vLLM, DashScope, Ollama, ...)
    claim_base_url: str = ""
    claim_api_key: str = ""
    claim_model: str = ""
    # demo
    demo_today: dt.date | None = None
    demo_dir: Path = BACKEND / "data" / "demo"

    @property
    def llm_ready(self) -> bool:
        """True when extraction can call a model (or replay recorded answers)."""
        return bool(self.model_extract and (self.api_key or self.cache_mode == "replay"))

    @property
    def claim_ready(self) -> bool:
        """True when the claim-potential model is configured (a local vLLM / Ollama may run without a key)."""
        return bool(self.claim_model and (self.claim_base_url or self.cache_mode == "replay"))

    @classmethod
    def from_env(cls) -> "LLMConfig":
        today = _e("DEMO_TODAY")
        try:
            demo_today = dt.date.fromisoformat(today) if today else None
        except ValueError:
            demo_today = None
        provider = _e("LLM_PROVIDER", default="openai").lower()
        model = _e("LLM_MODEL_EXTRACT", "LLM_MODEL")
        return cls(
            provider=provider,
            api_key=_e("LLM_API_KEY", {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY"}.get(provider, "OPENAI_API_KEY")),
            model_extract=model,
            model_review=_e("LLM_MODEL_REVIEW", "LLM_REVIEWER_MODEL", default=model),
            temperature=_f(_e("LLM_TEMPERATURE", default="0"), 0.0),
            reasoning_effort=_e("LLM_REASONING_EFFORT"),
            timeout_s=int(_f(_e("LLM_TIMEOUT_S", "LLM_REQUEST_TIMEOUT_SECONDS", default="45"), 45)),
            cache_mode=_e("LLM_CACHE_MODE", default="off").lower(),
            cache_dir=Path(_e("LLM_CACHE_DIR", default=str(BACKEND / "data" / "llm_cache"))),
            doc_text_max_chars=int(_f(_e("DOC_TEXT_MAX_CHARS", default="20000"), 20000)),
            confidence_threshold=_f(_e("CONFIDENCE_THRESHOLD", "LLM_CONFIDENCE_THRESHOLD", default="0.6"), 0.6),
            input_cost_eur_per_1m=_f(_e("LLM_INPUT_COST_EUR_PER_1M", default="0"), 0.0),
            output_cost_eur_per_1m=_f(_e("LLM_OUTPUT_COST_EUR_PER_1M", default="0"), 0.0),
            reviewer_enabled=_bool(_e("ENABLE_REVIEWER_LLM", "LLM_REVIEWER_ENABLED", default="false")),
            reviewer_mode=_e("REVIEWER_MODE", default="single").lower(),
            critical_fields=_csv(_e("REVIEW_CRITICAL_FIELDS", default=DEFAULT_CRITICAL)),
            judge_a_model=_e("REVIEW_JUDGE_A_MODEL"),
            judge_b_model=_e("REVIEW_JUDGE_B_MODEL"),
            judge_b_provider=_e("REVIEW_JUDGE_B_PROVIDER").lower(),
            judge_b_api_key=_e("REVIEW_JUDGE_B_API_KEY"),
            review_timeout_s=int(_f(_e("REVIEW_TIMEOUT_S", default="30"), 30)),
            vision_provider=_e("VISION_PROVIDER", default="openai").lower(),
            vision_model=_e("VISION_MODEL", default=model),
            claim_base_url=_e("CLAIM_LLM_BASE_URL"),
            claim_api_key=_e("CLAIM_LLM_API_KEY"),
            claim_model=_e("CLAIM_LLM_MODEL"),
            demo_today=demo_today,
            demo_dir=Path(_e("DEMO_DATA_DIR", default=str(BACKEND / "data" / "demo"))),
        )


CFG = LLMConfig.from_env()


def today() -> dt.date:
    """Reference date for relative times in prompts ("seit 10 Uhr" -> HEUTE 10:00). DEMO_TODAY pins it for the demo."""
    return CFG.demo_today or dt.date.today()
