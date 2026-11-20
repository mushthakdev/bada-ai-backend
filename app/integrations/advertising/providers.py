from __future__ import annotations

import secrets
from typing import Any

from app.integrations.advertising.base import (
    AdvertisingProvider,
    IntegrationMode,
    ProviderActionResult,
    ProviderCapabilities,
)


class SimulatedProvider(AdvertisingProvider):
    """Base for demo providers. Never claims live delivery."""

    integration_mode = IntegrationMode.SIMULATED

    def __init__(self, code: str, name: str, category: str, caps: ProviderCapabilities) -> None:
        self.code = code
        self.name = name
        self.category = category
        self._caps = caps

    def capabilities(self) -> ProviderCapabilities:
        return self._caps

    def create_campaign(self, payload: dict[str, Any]) -> ProviderActionResult:
        objective = payload.get("objective", "")
        if objective and not self.supports_objective(objective):
            return ProviderActionResult(
                success=False,
                status="failed",
                message=f"{self.name} does not support objective '{objective}'",
                is_simulated=True,
                integration_mode=self.integration_mode.value,
                error_code="unsupported_objective",
            )
        pid = f"sim_{self.code}_{secrets.token_hex(6)}"
        return ProviderActionResult(
            success=True,
            status="created",
            provider_campaign_id=pid,
            message=(
                f"Simulated {self.name} campaign draft created. "
                "Not live on the real platform."
            ),
            is_simulated=True,
            integration_mode=self.integration_mode.value,
            details={"filtered_targeting": self.filter_targeting(payload.get("targeting") or {})},
        )

    def upload_creative(self, payload: dict[str, Any]) -> ProviderActionResult:
        return ProviderActionResult(
            success=True,
            status="uploaded",
            message=f"Simulated creative upload to {self.name}",
            is_simulated=True,
            integration_mode=self.integration_mode.value,
            details={"format": payload.get("format")},
        )

    def submit_campaign(self, *, provider_campaign_id: str) -> ProviderActionResult:
        return ProviderActionResult(
            success=True,
            status="active",
            provider_campaign_id=provider_campaign_id,
            message=(
                f"Simulated launch on {self.name}. "
                "Delivery is not confirmed on a real advertising platform."
            ),
            is_simulated=True,
            integration_mode=self.integration_mode.value,
        )


class MetaAdsProvider(SimulatedProvider):
    def __init__(self) -> None:
        super().__init__(
            "meta",
            "Meta (Facebook & Instagram)",
            "social",
            ProviderCapabilities(
                objectives=[
                    "brand_awareness",
                    "reach",
                    "website_traffic",
                    "whatsapp_leads",
                    "lead_generation",
                    "sales",
                    "store_visits",
                ],
                ad_formats=["feed_image", "feed_video", "story", "reel", "carousel"],
                targeting=["location", "city", "pincode", "age", "gender", "interests", "language", "device"],
                budget_types=["daily", "lifetime"],
                metrics=["impressions", "reach", "clicks", "spend", "leads", "video_views"],
                supports_oauth=True,
                supports_auto_launch=False,
                min_daily_budget=300,
                pricing_model="mixed",
                estimated_cpm=180,
                notes="OAuth-ready architecture. Live Meta API requires approved app credentials.",
            ),
        )
        self.integration_mode = IntegrationMode.MANUAL


class YouTubeAdsProvider(SimulatedProvider):
    def __init__(self) -> None:
        super().__init__(
            "youtube",
            "YouTube",
            "video",
            ProviderCapabilities(
                objectives=["brand_awareness", "reach", "video_views", "website_traffic", "lead_generation"],
                ad_formats=["skippable_in_stream", "non_skippable", "bumper", "in_feed"],
                targeting=["location", "city", "age", "gender", "interests", "language", "device"],
                budget_types=["daily", "campaign"],
                metrics=["impressions", "views", "view_rate", "spend", "clicks"],
                supports_oauth=True,
                supports_auto_launch=False,
                min_daily_budget=500,
                pricing_model="cpv_cpm",
                estimated_cpm=220,
                notes="Google Ads / YouTube API eligibility required for live buying.",
            ),
        )
        self.integration_mode = IntegrationMode.MANUAL


class CTVProvider(SimulatedProvider):
    def __init__(self) -> None:
        super().__init__(
            "ctv",
            "Connected TV",
            "ctv_ott",
            ProviderCapabilities(
                objectives=["brand_awareness", "reach", "video_views", "store_visits"],
                ad_formats=["ctv_15s", "ctv_30s", "ctv_horizontal"],
                targeting=["location", "state", "city", "pincode", "language", "device"],
                budget_types=["daily", "total"],
                metrics=["impressions", "estimated_reach", "completed_views", "spend", "qr_scans"],
                supports_oauth=False,
                supports_auto_launch=False,
                min_daily_budget=1000,
                pricing_model="cpm",
                estimated_cpm=250,
                notes="Partner / publisher inventory. Simulated until a CTV partner API is connected.",
            ),
        )
        self.integration_mode = IntegrationMode.PARTNER


class OTTProvider(SimulatedProvider):
    def __init__(self) -> None:
        super().__init__(
            "ott",
            "OTT Streaming",
            "ctv_ott",
            ProviderCapabilities(
                objectives=["brand_awareness", "reach", "video_views"],
                ad_formats=["ott_15s", "ott_30s"],
                targeting=["location", "state", "city", "language"],
                budget_types=["total"],
                metrics=["impressions", "completed_views", "spend"],
                supports_oauth=False,
                supports_auto_launch=False,
                min_daily_budget=2000,
                pricing_model="cpm",
                estimated_cpm=320,
                notes=(
                    "Netflix and many OTT platforms do not offer unrestricted self-serve APIs. "
                    "Bada uses partner-managed or manual workflows unless an approved integration exists."
                ),
            ),
        )
        self.integration_mode = IntegrationMode.PARTNER


class PublisherProvider(SimulatedProvider):
    def __init__(self) -> None:
        super().__init__(
            "publishers",
            "Digital Publishers",
            "publishers",
            ProviderCapabilities(
                objectives=["brand_awareness", "website_traffic", "lead_generation", "reach"],
                ad_formats=["display_banner", "native", "publisher_video"],
                targeting=["location", "state", "city", "pincode", "language", "device"],
                budget_types=["daily", "total"],
                metrics=["impressions", "clicks", "spend", "ctr"],
                supports_oauth=False,
                supports_auto_launch=False,
                min_daily_budget=400,
                pricing_model="cpm_cpc",
                estimated_cpm=120,
                notes="Regional news and content networks via partner inventory.",
            ),
        )
        self.integration_mode = IntegrationMode.PARTNER


class LocalScreenProvider(SimulatedProvider):
    def __init__(self) -> None:
        super().__init__(
            "local_screens",
            "Local Digital Screens",
            "local",
            ProviderCapabilities(
                objectives=["brand_awareness", "store_visits", "reach", "sales"],
                ad_formats=["led_loop", "mall_screen", "retail_screen", "billboard_digital"],
                targeting=["location", "state", "city", "district", "pincode"],
                budget_types=["daily", "slot", "total"],
                metrics=["impressions", "estimated_reach", "qr_scans", "spend"],
                supports_oauth=False,
                supports_auto_launch=False,
                min_daily_budget=500,
                pricing_model="cpm_slot",
                estimated_cpm=90,
                notes="Local inventory marketplace. Listings require admin approval.",
            ),
        )
        self.integration_mode = IntegrationMode.PARTNER


class OutdoorProvider(SimulatedProvider):
    def __init__(self) -> None:
        super().__init__(
            "outdoor",
            "Outdoor & Transit",
            "outdoor",
            ProviderCapabilities(
                objectives=["brand_awareness", "reach", "store_visits"],
                ad_formats=["billboard", "transit", "led_outdoor"],
                targeting=["location", "city", "district", "pincode"],
                budget_types=["total", "slot"],
                metrics=["estimated_impressions", "spend"],
                supports_oauth=False,
                supports_auto_launch=False,
                min_daily_budget=1500,
                pricing_model="flat_cpm",
                estimated_cpm=150,
                notes="Partner/manual booking. Estimates only until inventory partners confirm.",
            ),
        )
        self.integration_mode = IntegrationMode.MANUAL
