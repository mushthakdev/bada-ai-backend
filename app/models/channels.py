from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import BaseModel, SoftDeleteMixin


class AdvertisingChannel(BaseModel):
    """Catalog of supported advertising channels in the Bada marketplace."""

    __tablename__ = "advertising_channels"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ad_formats: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # comma-separated
    campaign_types: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    targeting_options: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pricing_model: Mapped[str] = mapped_column(String(50), default="cpm", nullable=False)
    estimated_cpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    minimum_budget: Mapped[float] = mapped_column(Float, default=500.0, nullable=False)
    integration_mode: Mapped[str] = mapped_column(String(30), default="simulated", nullable=False)
    integration_status: Mapped[str] = mapped_column(String(30), default="available", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_estimate_pricing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ChannelConnection(BaseModel):
    """Per-business connection to an advertising channel (OAuth / partner)."""

    __tablename__ = "channel_connections"
    __table_args__ = (
        UniqueConstraint("business_id", "channel_code", name="uq_business_channel_connection"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    channel_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="not_connected", nullable=False)
    account_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    account_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Tokens stored server-side only — never returned to frontend
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scopes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CampaignChannel(BaseModel):
    """A channel selected on an omnichannel campaign."""

    __tablename__ = "campaign_channels"
    __table_args__ = (
        UniqueConstraint("campaign_id", "channel_code", name="uq_campaign_channel"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    channel_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    channel_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    allocated_budget: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    spent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    provider_campaign_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    integration_mode: Mapped[str] = mapped_column(String(30), default="simulated", nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    schedule_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    targeting_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    launched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ChannelMetric(BaseModel):
    """Daily metrics per campaign channel."""

    __tablename__ = "channel_metrics"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    channel_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metric_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reach: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    video_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qr_scans: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    spend: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LocalAdProvider(BaseModel, SoftDeleteMixin):
    """Local advertising inventory owner (screens, outdoor, regional)."""

    __tablename__ = "local_ad_providers"

    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending_review", nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    listings: Mapped[list[LocalInventoryListing]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )


class LocalInventoryListing(BaseModel, SoftDeleteMixin):
    """Individual local advertising inventory unit."""

    __tablename__ = "local_inventory_listings"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("local_ad_providers.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    inventory_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    pincode: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    screen_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    formats: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    operating_hours: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    available_slots: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pricing_model: Mapped[str] = mapped_column(String(50), default="cpm", nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_impressions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    photo_urls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending_review", nullable=False, index=True)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    provider: Mapped[LocalAdProvider] = relationship(back_populates="listings")
