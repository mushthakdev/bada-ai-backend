from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from app.ai.providers.base import (
    GenerationResult,
    ImageGenerationProvider,
    MusicGenerationProvider,
    TextGenerationProvider,
    TranslationProvider,
    VideoGenerationProvider,
    VoiceGenerationProvider,
)

LANGUAGE_NAMES = {
    "en": "English",
    "ml": "Malayalam",
    "ta": "Tamil",
    "hi": "Hindi",
    "te": "Telugu",
    "kn": "Kannada",
}


class MockTextProvider(TextGenerationProvider):
    def generate(self, prompt: str, *, system: Optional[str] = None, **kwargs: Any) -> GenerationResult:
        business_hint = kwargs.get("business_name", "your business")
        objective = kwargs.get("objective", "brand awareness")
        language = kwargs.get("language", "en")
        duration = kwargs.get("duration", 30)

        plan = {
            "campaign_concept": f"A warm, premium {duration}s CTV spot showcasing {business_hint} with a clear local call-to-action.",
            "target_audience": "Local households interested in quality products and nearby store visits.",
            "advertising_strategy": f"Lead with the offer, reinforce trust, and drive {objective.replace('_', ' ')}.",
            "recommended_duration": duration,
            "recommended_daily_budget": 1500,
            "ad_script": (
                f"Discover {business_hint}. "
                f"Crafted for your neighbourhood. "
                f"Visit us today — scan the QR code for directions and offers."
            ),
            "voiceover_script": (
                f"Looking for something special? {business_hint} brings you trusted quality, "
                f"right here in your city. Visit us this week."
            ),
            "scene_breakdown": [
                {"order": 1, "title": "Business introduction", "duration": 5, "visual": "Storefront / logo"},
                {"order": 2, "title": "Product showcase", "duration": 10, "visual": "Hero products"},
                {"order": 3, "title": "Offer highlight", "duration": 8, "visual": "Offer text overlay"},
                {"order": 4, "title": "Call to action", "duration": 7, "visual": "QR + location CTA"},
            ],
            "visual_recommendations": [
                "Bright, well-lit product shots",
                "Local landmark or neighbourhood cue",
                "Clear end card with logo and QR",
            ],
            "call_to_action": "Scan the QR code to visit us today",
            "language": LANGUAGE_NAMES.get(language, language),
            "source_prompt": prompt[:500],
        }
        return GenerationResult(
            content=plan,
            provider="mock",
            is_mock=True,
            tokens_used=len(prompt.split()) + 120,
            estimated_cost=0.0,
            meta={"note": "Mock AI plan — configure GEMINI_API_KEY for live generation"},
        )


class MockImageProvider(ImageGenerationProvider):
    def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        digest = hashlib.md5(prompt.encode()).hexdigest()[:8]
        return GenerationResult(
            content={
                "image_url": f"/media/mock/images/{digest}.svg",
                "prompt": prompt,
                "status": "mock_generated",
            },
            provider="mock",
            is_mock=True,
            meta={"note": "Placeholder visual — not a real AI-generated image"},
        )


class MockVideoProvider(VideoGenerationProvider):
    def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        duration = kwargs.get("duration", 30)
        return GenerationResult(
            content={
                "video_url": None,
                "preview_html": (
                    "<div style='padding:24px;background:#0A1628;color:white;font-family:sans-serif'>"
                    f"<h3>Mock TV Ad Preview ({duration}s)</h3>"
                    f"<p>{prompt[:180]}</p>"
                    "<p style='opacity:.7'>This is a mock-generated preview. "
                    "Connect a video generation provider to produce real creatives.</p>"
                    "</div>"
                ),
                "status": "mock_generated",
                "duration": duration,
            },
            provider="mock",
            is_mock=True,
            meta={"note": "Mock video — not a real rendered advertisement"},
        )


class MockVoiceProvider(VoiceGenerationProvider):
    def generate(self, text: str, *, language: str = "en", **kwargs: Any) -> GenerationResult:
        return GenerationResult(
            content={
                "audio_url": None,
                "transcript": text,
                "language": language,
                "voice_id": kwargs.get("voice_id", "mock_warm_female"),
                "status": "mock_generated",
            },
            provider="mock",
            is_mock=True,
        )


class MockMusicProvider(MusicGenerationProvider):
    def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        return GenerationResult(
            content={
                "track_name": "Mock Soft Retail Bed",
                "audio_url": None,
                "status": "mock_generated",
                "prompt": prompt,
            },
            provider="mock",
            is_mock=True,
        )


class MockTranslationProvider(TranslationProvider):
    def translate(self, text: str, *, target_language: str, source_language: str = "en") -> GenerationResult:
        lang = LANGUAGE_NAMES.get(target_language, target_language)
        return GenerationResult(
            content={
                "translated_text": f"[{lang} translation] {text}",
                "source_language": source_language,
                "target_language": target_language,
                "status": "mock_generated",
            },
            provider="mock",
            is_mock=True,
        )
