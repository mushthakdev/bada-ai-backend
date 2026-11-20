from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import BaseModel, SoftDeleteMixin


class Campaign(BaseModel, SoftDeleteMixin):
    __tablename__ = "campaigns"

    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(50), default="en", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    video_duration: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    brief_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_plan_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_plan_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_omnichannel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_simulated_delivery: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    launch_summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    audience: Mapped[Optional[CampaignAudience]] = relationship(
        back_populates="campaign", uselist=False, cascade="all, delete-orphan"
    )
    locations: Mapped[list[CampaignLocation]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    budget: Mapped[Optional[CampaignBudget]] = relationship(
        back_populates="campaign", uselist=False, cascade="all, delete-orphan"
    )
    schedule: Mapped[Optional[CampaignSchedule]] = relationship(
        back_populates="campaign", uselist=False, cascade="all, delete-orphan"
    )


class CampaignAudience(BaseModel):
    __tablename__ = "campaign_audiences"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), unique=True, nullable=False
    )
    demographics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interests: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    languages: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    age_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    campaign: Mapped[Campaign] = relationship(back_populates="audience")


class CampaignLocation(BaseModel):
    __tablename__ = "campaign_locations"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    country: Mapped[str] = mapped_column(String(50), default="India", nullable=False)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    estimated_audience: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    campaign: Mapped[Campaign] = relationship(back_populates="locations")


class CampaignBudget(BaseModel):
    __tablename__ = "campaign_budgets"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), unique=True, nullable=False
    )
    daily_budget: Mapped[float] = mapped_column(Float, nullable=False)
    total_budget: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    estimated_cpm: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_impressions: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_reach: Mapped[int] = mapped_column(Integer, nullable=False)
    media_spend: Mapped[float] = mapped_column(Float, nullable=False)
    platform_fee: Mapped[float] = mapped_column(Float, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_payable: Mapped[float] = mapped_column(Float, nullable=False)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    campaign: Mapped[Campaign] = relationship(back_populates="budget")


class CampaignSchedule(BaseModel):
    __tablename__ = "campaign_schedules"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), unique=True, nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    preferred_slots: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    prime_time: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_impression_cap: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    frequency_cap: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    campaign: Mapped[Campaign] = relationship(back_populates="schedule")
