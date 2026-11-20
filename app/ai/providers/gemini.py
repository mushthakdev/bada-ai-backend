from __future__ import annotations

import json
from typing import Any, Optional

from app.ai.providers.base import GenerationResult, TextGenerationProvider
from app.core.config import get_settings


class GeminiTextProvider(TextGenerationProvider):
    """Google Gemini text generation via API key or Application Default Credentials (ADC)."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        project: Optional[str] = None,
        location: str = "us-central1",
        use_adc: bool = False,
        model: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key
        self.project = project
        self.location = location
        self.use_adc = use_adc
        self.model = model or settings.gemini_model

    def _client(self):
        from google import genai

        if self.use_adc:
            return genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
            )
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required when ADC is not enabled")
        return genai.Client(api_key=self.api_key)

    def _generate_json(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
    ) -> GenerationResult:
        settings = get_settings()
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        client = self._client()
        response = client.models.generate_content(
            model=self.model,
            contents=full_prompt,
            config={
                "temperature": temperature,
                "response_mime_type": "application/json",
            },
        )

        text = getattr(response, "text", None) or "{}"
        try:
            content = json.loads(text)
        except json.JSONDecodeError:
            content = {"raw_text": text}

        usage = getattr(response, "usage_metadata", None)
        tokens = 0
        if usage is not None:
            tokens = int(getattr(usage, "total_token_count", 0) or 0)

        return GenerationResult(
            content=content,
            provider="gemini",
            is_mock=False,
            tokens_used=tokens,
            estimated_cost=round(tokens * 0.00000035, 6),
            meta={
                "model": self.model,
                "env": settings.app_env,
                "auth": "adc" if self.use_adc else "api_key",
            },
        )

    def generate(self, prompt: str, *, system: Optional[str] = None, **kwargs: Any) -> GenerationResult:
        return self._generate_json(prompt, system=system, temperature=0.7)

    def generate_agent(self, prompt: str, *, system: Optional[str] = None, **kwargs: Any) -> GenerationResult:
        """Lower-temperature JSON plan for tool-calling agent turns."""
        return self._generate_json(prompt, system=system, temperature=0.2)
