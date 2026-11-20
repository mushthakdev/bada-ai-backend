from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import BaseModel


class Payment(BaseModel):
    __tablename__ = "payments"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="created", nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="mock", nullable=False)
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    provider_signature: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    receipt_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Transaction(BaseModel):
    __tablename__ = "transactions"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payments.id"), nullable=False, index=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class Invoice(BaseModel):
    __tablename__ = "invoices"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payments.id"), nullable=False, index=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="issued", nullable=False)
