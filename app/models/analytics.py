from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import BaseModel


class CampaignImpression(BaseModel):
    __tablename__ = "campaign_impressions"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    pincode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    completed_view: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    device_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CampaignMetric(BaseModel):
    __tablename__ = "campaign_metrics"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_reach: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qr_scans: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    website_visits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    whatsapp_inquiries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    phone_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    spend: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
