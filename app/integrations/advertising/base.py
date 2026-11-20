from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class IntegrationMode(str, Enum):
    API = "api"  # Fully API-connected when credentials + eligibility exist
    PARTNER = "partner"  # Partner-managed buying
    MANUAL = "manual"  # Manual / ops workflow
    SIMULATED = "simulated"  # Demo / development only


class ConnectionStatus(str, Enum):
    NOT_CONNECTED = "not_connected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    EXPIRED = "expired"
    ERROR = "error"
    NOT_AVAILABLE = "not_available"


@dataclass
class ProviderCapabilities:
    objectives: list[str] = field(default_factory=list)
    ad_formats: list[str] = field(default_factory=list)
    targeting: list[str] = field(default_factory=list)
    budget_types: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    supports_oauth: bool = False
    supports_auto_launch: bool = False
    min_daily_budget: float = 500.0
    pricing_model: str = "cpm"
    estimated_cpm: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class ProviderActionResult:
    success: bool
    status: str
    provider_campaign_id: Optional[str] = None
    message: str = ""
    is_simulated: bool = True
    integration_mode: str = IntegrationMode.SIMULATED.value
    details: dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None


class AdvertisingProvider(ABC):
    """Capability-based advertising provider adapter.

    Concrete providers must declare what they support and refuse unsupported
    targeting / objectives rather than silently inventing behaviour.
    """

    code: str
    name: str
    category: str
    integration_mode: IntegrationMode = IntegrationMode.SIMULATED

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    def connect_account(self, *, auth_code: Optional[str] = None, **kwargs: Any) -> ProviderActionResult:
        return ProviderActionResult(
            success=False,
            status=ConnectionStatus.NOT_AVAILABLE.value,
            message=f"{self.name} OAuth is not configured. Use partner/manual workflow.",
            is_simulated=True,
            integration_mode=self.integration_mode.value,
        )

    def disconnect_account(self, *, connection_id: str) -> ProviderActionResult:
        return ProviderActionResult(
            success=True,
            status=ConnectionStatus.NOT_CONNECTED.value,
            message="Disconnected locally",
            is_simulated=True,
            integration_mode=self.integration_mode.value,
        )

    def validate_connection(self, *, access_token: Optional[str] = None) -> ProviderActionResult:
        return ProviderActionResult(
            success=False,
            status=ConnectionStatus.NOT_CONNECTED.value,
            message="No live connection",
            is_simulated=True,
            integration_mode=self.integration_mode.value,
        )

    def filter_targeting(self, targeting: dict[str, Any]) -> dict[str, Any]:
        allowed = set(self.capabilities().targeting)
        return {k: v for k, v in targeting.items() if k in allowed and v is not None}

    def supports_objective(self, objective: str) -> bool:
        return objective in self.capabilities().objectives

    @abstractmethod
    def create_campaign(self, payload: dict[str, Any]) -> ProviderActionResult:
        raise NotImplementedError

    @abstractmethod
    def upload_creative(self, payload: dict[str, Any]) -> ProviderActionResult:
        raise NotImplementedError

    @abstractmethod
    def submit_campaign(self, *, provider_campaign_id: str) -> ProviderActionResult:
        raise NotImplementedError

    def pause_campaign(self, *, provider_campaign_id: str) -> ProviderActionResult:
        return ProviderActionResult(
            success=True,
            status="paused",
            provider_campaign_id=provider_campaign_id,
            message="Paused (simulated)",
            is_simulated=True,
            integration_mode=self.integration_mode.value,
        )

    def resume_campaign(self, *, provider_campaign_id: str) -> ProviderActionResult:
        return ProviderActionResult(
            success=True,
            status="active",
            provider_campaign_id=provider_campaign_id,
            message="Resumed (simulated)",
            is_simulated=True,
            integration_mode=self.integration_mode.value,
        )

    def stop_campaign(self, *, provider_campaign_id: str) -> ProviderActionResult:
        return ProviderActionResult(
            success=True,
            status="stopped",
            provider_campaign_id=provider_campaign_id,
            message="Stopped (simulated)",
            is_simulated=True,
            integration_mode=self.integration_mode.value,
        )

    def get_campaign_status(self, *, provider_campaign_id: str) -> ProviderActionResult:
        return ProviderActionResult(
            success=True,
            status="unknown",
            provider_campaign_id=provider_campaign_id,
            message="Status unavailable without live provider API",
            is_simulated=True,
            integration_mode=self.integration_mode.value,
        )

    def get_analytics(self, *, provider_campaign_id: str) -> ProviderActionResult:
        return ProviderActionResult(
            success=True,
            status="ok",
            provider_campaign_id=provider_campaign_id,
            message="No live analytics; use Bada aggregated metrics",
            is_simulated=True,
            integration_mode=self.integration_mode.value,
            details={"metrics": {}},
        )
