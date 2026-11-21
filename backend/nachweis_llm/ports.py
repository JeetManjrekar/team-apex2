from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(slots=True)
class ProviderResponse:
    data: dict[str, Any]
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass(slots=True)
class TextProviderResponse:
    text: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)


class LLMProvider(Protocol):
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
        model: str | None = None,
    ) -> ProviderResponse: ...

    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> TextProviderResponse: ...


class ImageVisionProvider(Protocol):
    async def classify_image(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        allowed_categories: tuple[str, ...],
        context: str = "",
        model: str | None = None,
    ) -> ProviderResponse: ...
