from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import BaseModel


class AIGeneration(BaseModel):
    __tablename__ = "ai_generations"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=True
    )
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=True
    )
    creative_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ad_creatives.id"), nullable=True
    )
    generation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="mock", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_mock: Mapped[bool] = mapped_column(default=True, nullable=False)
    task_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class AIConversation(BaseModel):
    __tablename__ = "ai_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), default="Campaign Assistant", nullable=False)
    context_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    messages: Mapped[list[AIMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class AIMessage(BaseModel):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    conversation: Mapped[AIConversation] = relationship(back_populates="messages")


class AIUsage(BaseModel):
    __tablename__ = "ai_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=True
    )
    generation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="lifetime", nullable=False)
