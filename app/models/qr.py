from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import BaseModel


class QRCode(BaseModel):
    __tablename__ = "qr_codes"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    destination_type: Mapped[str] = mapped_column(String(50), nullable=False)
    destination_value: Mapped[str] = mapped_column(String(500), nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    scans: Mapped[list[QRScan]] = relationship(back_populates="qr_code", cascade="all, delete-orphan")


class QRScan(BaseModel):
    __tablename__ = "qr_scans"

    qr_code_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("qr_codes.id"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    scanned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    device_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    browser: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    referrer: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    location_hint: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    qr_code: Mapped[QRCode] = relationship(back_populates="scans")
