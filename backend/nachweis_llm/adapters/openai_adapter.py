from __future__ import annotations

import base64
import json
from typing import Any

from ..ports import ProviderResponse, TextProviderResponse, TokenUsage


class OpenAIAdapter:
    """OpenAI Chat Completions adapter. The OpenAI SDK is an optional dependency."""

    def __init__(self, api_key: str, timeout_seconds: int = 45):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Install the optional dependency: pip install -e '.[openai]'") from exc
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
        model: str | None = None,
    ) -> ProviderResponse:
        result = await self.client.chat.completions.create(
            model=model or "gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
            temperature=0.1,
        )
        message = result.choices[0].message
        if not message.content:
            raise RuntimeError("LLM returned an empty structured response")
        parsed = json.loads(message.content)
        usage = result.usage
        return ProviderResponse(
            data=parsed,
            model=result.model,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )

    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> TextProviderResponse:
        result = await self.client.chat.completions.create(
            model=model or "gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        content = result.choices[0].message.content or ""
        usage = result.usage
        return TextProviderResponse(
            text=content,
            model=result.model,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )

    async def classify_image(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        allowed_categories: tuple[str, ...],
        context: str = "",
        model: str | None = None,
    ) -> ProviderResponse:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        schema = {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(allowed_categories)},
                "caption_de": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["category", "caption_de", "confidence", "tags"],
            "additionalProperties": False,
        }
        result = await self.client.chat.completions.create(
            model=model or "gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ordne das Baustellenfoto genau einer vorgegebenen Kategorie zu. "
                        "Beschreibe nur sichtbar Erkennbares. Keine Annahmen zu Personen, Ursache, "
                        "Verantwortung oder rechtlicher Bedeutung. Antworte auf Deutsch."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Kontext: {context}\nErlaubte Kategorien: {allowed_categories}"},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "site_photo_classification", "strict": True, "schema": schema},
            },
            temperature=0.1,
        )
        message = result.choices[0].message
        if not message.content:
            raise RuntimeError("LLM returned an empty photo classification")
        usage = result.usage
        return ProviderResponse(
            data=json.loads(message.content),
            model=result.model,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )
