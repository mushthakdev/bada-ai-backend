from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import BaseModel


class AdCreative(BaseModel):
    __tablename__ = "ad_creatives"

    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True
    )
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    language: Mapped[str] = mapped_column(String(50), default="en", nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    voiceover_script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storyboard_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    generation_mode: Mapped[str] = mapped_column(String(50), default="mock", nullable=False)
    preview_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    voice_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    music_track: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    cta_text: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    qr_destination_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    qr_destination_value: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    approval_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    scenes: Mapped[list[CreativeScene]] = relationship(
        back_populates="creative", cascade="all, delete-orphan", order_by="CreativeScene.order_index"
    )


class CreativeScene(BaseModel):
    __tablename__ = "creative_scenes"

    creative_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ad_creatives.id"), nullable=False, index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    text_overlay: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    media_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str] = mapped_column(String(50), default="image", nullable=False)
    voiceover_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    creative: Mapped[AdCreative] = relationship(back_populates="scenes")
