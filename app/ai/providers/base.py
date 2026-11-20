from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class GenerationResult:
    content: Any
    provider: str
    is_mock: bool
    tokens_used: int = 0
    estimated_cost: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


class TextGenerationProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, *, system: Optional[str] = None, **kwargs: Any) -> GenerationResult:
        raise NotImplementedError


class ImageGenerationProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        raise NotImplementedError


class VideoGenerationProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        raise NotImplementedError


class VoiceGenerationProvider(ABC):
    @abstractmethod
    def generate(self, text: str, *, language: str = "en", **kwargs: Any) -> GenerationResult:
        raise NotImplementedError


class MusicGenerationProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        raise NotImplementedError


class TranslationProvider(ABC):
    @abstractmethod
    def translate(self, text: str, *, target_language: str, source_language: str = "en") -> GenerationResult:
        raise NotImplementedError
