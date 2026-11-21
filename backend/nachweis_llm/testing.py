"""Small fake provider for local UI integration and tests; never use for production."""

from __future__ import annotations

from collections import deque
from typing import Any

from .ports import ProviderResponse, TextProviderResponse, TokenUsage


class FakeLLMProvider:
    def __init__(
        self,
        *,
        json_responses: list[dict[str, Any]] | None = None,
        text_responses: list[str] | None = None,
        image_responses: list[dict[str, Any]] | None = None,
    ):
        self.json_responses = deque(json_responses or [])
        self.text_responses = deque(text_responses or [])
        self.image_responses = deque(image_responses or [])
        self.calls: list[dict[str, Any]] = []

    async def generate_json(self, *, system_prompt, user_prompt, schema_name, schema, model=None):
        self.calls.append({"kind": "json", "schema_name": schema_name, "model": model})
        data = self.json_responses.popleft() if self.json_responses else {}
        return ProviderResponse(data=data, model=model or "fake-model", usage=TokenUsage(10, 5))

    async def generate_text(self, *, system_prompt, user_prompt, model=None):
        self.calls.append({"kind": "text", "model": model})
        result = self.text_responses.popleft() if self.text_responses else "Vorschlag zur Pruefung durch die Bauleitung."
        return TextProviderResponse(text=result, model=model or "fake-model", usage=TokenUsage(8, 6))

    async def classify_image(self, *, image_bytes, mime_type, allowed_categories, context="", model=None):
        self.calls.append({"kind": "image", "model": model})
        data = self.image_responses.popleft() if self.image_responses else {
            "category": allowed_categories[0],
            "caption_de": "Baustellenfoto zur Pruefung.",
            "confidence": 0.9,
            "tags": [],
        }
        return ProviderResponse(data=data, model=model or "fake-model", usage=TokenUsage(12, 5))
