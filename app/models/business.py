from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import BaseModel, SoftDeleteMixin


class Business(BaseModel, SoftDeleteMixin):
    __tablename__ = "businesses"

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    agency_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agencies.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    pincode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, index=True)
    country: Mapped[str] = mapped_column(String(50), default="India", nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    brand_tagline: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    brand_primary_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    brand_secondary_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    advertising_objective: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    target_languages: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    onboarding_step: Mapped[int] = mapped_column(default=1, nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)

    memberships: Mapped[list[BusinessMembership]] = relationship(back_populates="business")


class BusinessMembership(BaseModel):
    __tablename__ = "business_memberships"
    __table_args__ = (UniqueConstraint("business_id", "user_id", name="uq_business_user"),)

    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="owner", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped[Business] = relationship(back_populates="memberships")
