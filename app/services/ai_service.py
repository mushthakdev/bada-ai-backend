from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.ai.factory import (
    get_music_provider,
    get_text_provider,
    get_translation_provider,
    get_video_provider,
    get_voice_provider,
)
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.ai import AIConversation, AIGeneration, AIMessage, AIUsage
from app.models.base import utcnow
from app.models.campaign import Campaign
from app.models.creative import AdCreative, CreativeScene
from app.models.user import User
from app.services.business_service import user_can_access_business
from app.services.campaign_service import get_campaign

settings = get_settings()


def _track_usage(
    db: Session,
    *,
    user_id: UUID,
    business_id: Optional[UUID],
    generation_type: str,
    provider: str,
    tokens: int,
    cost: float,
) -> None:
    db.add(
        AIUsage(
            user_id=user_id,
            business_id=business_id,
            generation_type=generation_type,
            provider=provider,
            tokens_used=tokens,
            cost=cost,
        )
    )


def create_generation_record(
    db: Session,
    *,
    user: User,
    generation_type: str,
    prompt: str,
    business_id: Optional[UUID] = None,
    campaign_id: Optional[UUID] = None,
    creative_id: Optional[UUID] = None,
    provider: str = "mock",
    is_mock: bool = True,
) -> AIGeneration:
    record = AIGeneration(
        user_id=user.id,
        business_id=business_id,
        campaign_id=campaign_id,
        creative_id=creative_id,
        generation_type=generation_type,
        provider=provider,
        status="pending",
        prompt=prompt,
        is_mock=is_mock,
        task_id=str(uuid4()),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def plan_campaign(
    db: Session,
    user: User,
    *,
    campaign_id: UUID,
    brief: Optional[str] = None,
) -> dict[str, Any]:
    campaign = get_campaign(db, user, campaign_id)
    prompt = brief or campaign.brief_text or campaign.description or campaign.name
    if not prompt:
        raise ValidationAppError("Provide a campaign brief to generate a plan")

    record = create_generation_record(
        db,
        user=user,
        generation_type="campaign_plan",
        prompt=prompt,
        business_id=campaign.business_id,
        campaign_id=campaign.id,
        provider="gemini" if not settings.ai_mock_mode else "mock",
        is_mock=settings.ai_mock_mode,
    )
    record.status = "processing"
    campaign.status = "creative_generating"
    db.commit()

    provider = get_text_provider()
    result = provider.generate(
        prompt,
        system=(
            "You are Bada's TV advertising planner for Indian businesses. "
            "Return structured JSON for a CTV campaign plan."
        ),
        business_name=campaign.name,
        objective=campaign.objective,
        language=campaign.language,
        duration=campaign.video_duration,
    )

    record.status = "completed"
    record.result_json = json.dumps(result.content)
    record.tokens_used = result.tokens_used
    record.estimated_cost = result.estimated_cost
    record.is_mock = result.is_mock
    record.provider = result.provider
    campaign.ai_plan_json = json.dumps(result.content)
    campaign.status = "ready_for_review"
    _track_usage(
        db,
        user_id=user.id,
        business_id=campaign.business_id,
        generation_type="campaign_plan",
        provider=result.provider,
        tokens=result.tokens_used,
        cost=result.estimated_cost,
    )
    db.commit()

    return {
        "generation_id": str(record.id),
        "status": "completed",
        "is_mock": result.is_mock,
        "provider": result.provider,
        "plan": result.content,
        "meta": result.meta,
    }


def generate_creative(
    db: Session,
    user: User,
    *,
    campaign_id: UUID,
    duration: Optional[int] = None,
) -> dict[str, Any]:
    campaign = get_campaign(db, user, campaign_id)
    plan = json.loads(campaign.ai_plan_json) if campaign.ai_plan_json else None
    if not plan:
        planned = plan_campaign(db, user, campaign_id=campaign_id)
        plan = planned["plan"]

    duration = duration or campaign.video_duration
    prompt = plan.get("ad_script") or campaign.brief_text or campaign.name

    record = create_generation_record(
        db,
        user=user,
        generation_type="video_creative",
        prompt=prompt,
        business_id=campaign.business_id,
        campaign_id=campaign.id,
        is_mock=True,
        provider="mock",
    )
    record.status = "processing"
    campaign.status = "creative_generating"
    db.commit()

    text_provider = get_text_provider()
    video_provider = get_video_provider()
    voice_provider = get_voice_provider()
    music_provider = get_music_provider()

    video = video_provider.generate(prompt, duration=duration)
    voice = voice_provider.generate(plan.get("voiceover_script", prompt), language=campaign.language)
    music = music_provider.generate(f"Upbeat retail bed for {campaign.name}")

    creative = AdCreative(
        business_id=campaign.business_id,
        campaign_id=campaign.id,
        title=f"{campaign.name} — {duration}s",
        language=campaign.language,
        duration_seconds=duration,
        script=plan.get("ad_script"),
        voiceover_script=plan.get("voiceover_script"),
        storyboard_json=json.dumps(plan.get("scene_breakdown", [])),
        status="ready_for_review",
        generation_mode="mock" if video.is_mock else "live",
        preview_url=None,
        video_url=video.content.get("video_url"),
        thumbnail_url=None,
        voice_id=voice.content.get("voice_id"),
        music_track=music.content.get("track_name"),
        cta_text=plan.get("call_to_action"),
        qr_destination_type="website",
        is_mock=video.is_mock,
        approval_status="pending",
    )
    db.add(creative)
    db.flush()

    scenes = plan.get("scene_breakdown") or [
        {"order": 1, "title": "Intro", "duration": 5, "visual": "Logo"},
        {"order": 2, "title": "Product", "duration": 10, "visual": "Products"},
        {"order": 3, "title": "Offer", "duration": 8, "visual": "Offer"},
        {"order": 4, "title": "CTA", "duration": 7, "visual": "QR"},
    ]
    for scene in scenes:
        db.add(
            CreativeScene(
                creative_id=creative.id,
                order_index=int(scene.get("order", 1)),
                title=scene.get("title", "Scene"),
                description=scene.get("visual"),
                duration_seconds=float(scene.get("duration", 3)),
                text_overlay=scene.get("title"),
                voiceover_text=None,
                media_type="image",
            )
        )

    record.status = "completed"
    record.creative_id = creative.id
    record.result_json = json.dumps(
        {
            "creative_id": str(creative.id),
            "video": video.content,
            "voice": voice.content,
            "music": music.content,
        }
    )
    record.is_mock = True
    campaign.status = "ready_for_review"
    _track_usage(
        db,
        user_id=user.id,
        business_id=campaign.business_id,
        generation_type="video_creative",
        provider="mock",
        tokens=0,
        cost=0.0,
    )
    db.commit()
    db.refresh(creative)

    return {
        "generation_id": str(record.id),
        "creative_id": str(creative.id),
        "status": "completed",
        "is_mock": True,
        "generation_mode": "mock",
        "note": "Mock-generated creative. Not a real AI-rendered TV advertisement.",
        "creative": serialize_creative(creative),
        "preview": video.content,
    }


def serialize_creative(creative: AdCreative) -> dict[str, Any]:
    return {
        "id": str(creative.id),
        "business_id": str(creative.business_id),
        "campaign_id": str(creative.campaign_id) if creative.campaign_id else None,
        "title": creative.title,
        "language": creative.language,
        "duration_seconds": creative.duration_seconds,
        "script": creative.script,
        "voiceover_script": creative.voiceover_script,
        "status": creative.status,
        "generation_mode": creative.generation_mode,
        "is_mock": creative.is_mock,
        "preview_url": creative.preview_url,
        "video_url": creative.video_url,
        "cta_text": creative.cta_text,
        "approval_status": creative.approval_status,
        "music_track": creative.music_track,
        "scenes": [
            {
                "id": str(s.id),
                "order_index": s.order_index,
                "title": s.title,
                "description": s.description,
                "duration_seconds": s.duration_seconds,
                "text_overlay": s.text_overlay,
                "media_url": s.media_url,
                "media_type": s.media_type,
                "voiceover_text": s.voiceover_text,
            }
            for s in sorted(creative.scenes or [], key=lambda x: x.order_index)
        ],
    }


def get_generation(db: Session, user: User, generation_id: UUID) -> AIGeneration:
    record = db.query(AIGeneration).filter(AIGeneration.id == generation_id).first()
    if not record:
        raise NotFoundError("Generation not found")
    if record.user_id != user.id and (user.role.name if user.role else "") not in (
        "admin",
        "super_admin",
    ):
        raise NotFoundError("Generation not found")
    return record


def translate_script(db: Session, user: User, text: str, target_language: str) -> dict[str, Any]:
    provider = get_translation_provider()
    result = provider.translate(text, target_language=target_language)
    _track_usage(
        db,
        user_id=user.id,
        business_id=None,
        generation_type="translation",
        provider=result.provider,
        tokens=result.tokens_used,
        cost=result.estimated_cost,
    )
    db.commit()
    return {
        "is_mock": result.is_mock,
        "provider": result.provider,
        **result.content,
    }


def assistant_chat(
    db: Session,
    user: User,
    *,
    message: str,
    business_id: Optional[UUID] = None,
    conversation_id: Optional[UUID] = None,
) -> dict[str, Any]:
    if business_id:
        user_can_access_business(db, user, business_id)

    if conversation_id:
        conversation = (
            db.query(AIConversation)
            .filter(AIConversation.id == conversation_id, AIConversation.user_id == user.id)
            .first()
        )
        if not conversation:
            raise NotFoundError("Conversation not found")
    else:
        conversation = AIConversation(
            user_id=user.id,
            business_id=business_id,
            title=message[:80],
        )
        db.add(conversation)
        db.flush()

    db.add(AIMessage(conversation_id=conversation.id, role="user", content=message))
    db.flush()

    from app.ai.agent import run_agent

    result = run_agent(
        db,
        user,
        message=message,
        conversation_id=conversation.id,
        business_id=business_id or conversation.business_id,
    )

    reply = result["reply"]
    meta = {
        "actions": result.get("actions") or [],
        "tool_results": result.get("tool_results") or [],
        "provider": result.get("provider"),
    }
    db.add(
        AIMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=reply,
            meta_json=json.dumps(meta),
        )
    )
    db.commit()

    return {
        "conversation_id": str(conversation.id),
        "reply": reply,
        "actions": result.get("actions") or [],
        "suggestions": result.get("suggestions") or [],
        "select": result.get("select"),
        "tool_results": result.get("tool_results") or [],
        "data_quality": result.get("data_quality")
        or {"is_simulated": False, "label": "Live"},
        "is_mock_llm": result.get("is_mock_llm", settings.ai_mock_mode),
        "provider": result.get("provider", "rules"),
    }


def update_scene(
    db: Session,
    user: User,
    creative_id: UUID,
    scene_id: UUID,
    updates: dict[str, Any],
) -> dict[str, Any]:
    creative = db.query(AdCreative).filter(AdCreative.id == creative_id).first()
    if not creative:
        raise NotFoundError("Creative not found")
    user_can_access_business(db, user, creative.business_id)
    scene = (
        db.query(CreativeScene)
        .filter(CreativeScene.id == scene_id, CreativeScene.creative_id == creative_id)
        .first()
    )
    if not scene:
        raise NotFoundError("Scene not found")
    for key in ("title", "description", "duration_seconds", "text_overlay", "media_url", "voiceover_text", "order_index"):
        if key in updates and updates[key] is not None:
            setattr(scene, key, updates[key])
    db.commit()
    db.refresh(creative)
    return serialize_creative(creative)
