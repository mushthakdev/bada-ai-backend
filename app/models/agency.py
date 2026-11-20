from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import BaseModel, SoftDeleteMixin


class Agency(BaseModel, SoftDeleteMixin):
    __tablename__ = "agencies"

    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    legal_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    white_label_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    white_label_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    members: Mapped[list[AgencyMember]] = relationship(back_populates="agency")
    clients: Mapped[list[AgencyClient]] = relationship(back_populates="agency")


class AgencyMember(BaseModel):
    __tablename__ = "agency_members"
    __table_args__ = (UniqueConstraint("agency_id", "user_id", name="uq_agency_user"),)

    agency_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agencies.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    agency: Mapped[Agency] = relationship(back_populates="members")


class AgencyClient(BaseModel):
    __tablename__ = "agency_clients"
    __table_args__ = (UniqueConstraint("agency_id", "business_id", name="uq_agency_business"),)

    agency_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agencies.id"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=False
    )
    assigned_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)

    agency: Mapped[Agency] = relationship(back_populates="clients")
