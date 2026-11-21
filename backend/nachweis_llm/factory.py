from __future__ import annotations

from dataclasses import dataclass

from .adapters.openai_adapter import OpenAIAdapter
from .config import LLMSettings
from .metrics import MetricsRecorder
from .ports import LLMProvider
from .services.documents import CompletenessService, DocumentDraftService
from .services.extraction import ExtractionService
from .services.photos import PhotoClassificationService
from .services.replanner import ReplannerNarrator
from .services.review import CriticalFieldReviewer


@dataclass(slots=True)
class LLMServices:
    provider: LLMProvider
    metrics: MetricsRecorder
    extractor: ExtractionService
    reviewer: CriticalFieldReviewer
    drafts: DocumentDraftService
    completeness: CompletenessService
    photos: PhotoClassificationService
    replanner: ReplannerNarrator


def create_services(settings: LLMSettings | None = None, provider: LLMProvider | None = None) -> LLMServices:
    settings = settings or LLMSettings.from_env()
    if provider is None:
        if settings.provider != "openai":
            raise ValueError(f"Unsupported LLM_PROVIDER={settings.provider!r}; provide a custom provider adapter")
        provider = OpenAIAdapter(settings.api_key or "", settings.request_timeout_seconds)
    metrics = MetricsRecorder(settings)
    return LLMServices(
        provider=provider,
        metrics=metrics,
        extractor=ExtractionService(provider, settings, metrics),
        reviewer=CriticalFieldReviewer(provider, settings, metrics),
        drafts=DocumentDraftService(metrics),
        completeness=CompletenessService(),
        photos=PhotoClassificationService(provider, settings, metrics),
        replanner=ReplannerNarrator(provider, metrics, settings.model),
    )
