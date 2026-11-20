from __future__ import annotations

from functools import lru_cache

from app.ai.providers.base import (
    ImageGenerationProvider,
    MusicGenerationProvider,
    TextGenerationProvider,
    TranslationProvider,
    VideoGenerationProvider,
    VoiceGenerationProvider,
)
from app.ai.providers.mock import (
    MockImageProvider,
    MockMusicProvider,
    MockTextProvider,
    MockTranslationProvider,
    MockVideoProvider,
    MockVoiceProvider,
)
from app.core.config import get_settings


@lru_cache
def get_text_provider() -> TextGenerationProvider:
    settings = get_settings()
    if settings.gemini_adc_ready or settings.gemini_api_key:
        from app.ai.providers.gemini import GeminiTextProvider

        return GeminiTextProvider(
            api_key=settings.gemini_api_key,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            use_adc=settings.gemini_adc_ready,
            model=settings.gemini_model,
        )
    return MockTextProvider()


@lru_cache
def get_image_provider() -> ImageGenerationProvider:
    return MockImageProvider()


@lru_cache
def get_video_provider() -> VideoGenerationProvider:
    return MockVideoProvider()


@lru_cache
def get_voice_provider() -> VoiceGenerationProvider:
    return MockVoiceProvider()


@lru_cache
def get_music_provider() -> MusicGenerationProvider:
    return MockMusicProvider()


@lru_cache
def get_translation_provider() -> TranslationProvider:
    return MockTranslationProvider()
