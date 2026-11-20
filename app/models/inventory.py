from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PublisherPartner(BaseModel):
    __tablename__ = "publisher_partners"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    inventory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="demo", nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supported_languages: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    default_cpm: Mapped[float] = mapped_column(Float, default=250.0, nullable=False)


class AdInventory(BaseModel):
    __tablename__ = "ad_inventory"

    publisher_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    inventory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pincode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, index=True)
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    available_impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cpm: Mapped[float] = mapped_column(Float, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PincodeInventory(BaseModel):
    __tablename__ = "pincode_inventory"

    pincode: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    estimated_households: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_ctv_reach: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_cpm: Mapped[float] = mapped_column(Float, default=250.0, nullable=False)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
