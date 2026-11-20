from __future__ import annotations

from functools import lru_cache
from typing import Optional

from app.integrations.advertising.base import AdvertisingProvider
from app.integrations.advertising.providers import (
    CTVProvider,
    LocalScreenProvider,
    MetaAdsProvider,
    OTTProvider,
    OutdoorProvider,
    PublisherProvider,
    YouTubeAdsProvider,
)


@lru_cache
def get_provider_registry() -> dict[str, AdvertisingProvider]:
    providers: list[AdvertisingProvider] = [
        MetaAdsProvider(),
        YouTubeAdsProvider(),
        CTVProvider(),
        OTTProvider(),
        PublisherProvider(),
        LocalScreenProvider(),
        OutdoorProvider(),
    ]
    return {p.code: p for p in providers}


def get_provider(code: str) -> Optional[AdvertisingProvider]:
    return get_provider_registry().get(code)


def list_providers() -> list[AdvertisingProvider]:
    return list(get_provider_registry().values())
