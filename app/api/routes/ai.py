from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.creative import AdCreative
from app.models.user import User
from app.services import ai_service
from app.services.business_service import user_can_access_business

router = APIRouter(prefix="/ai", tags=["ai"])


class PlanRequest(BaseModel):
    campaign_id: UUID
    brief: Optional[str] = None


class GenerateRequest(BaseModel):
    campaign_id: UUID
    duration: Optional[int] = Field(default=None, ge=15, le=60)


class TranslateRequest(BaseModel):
    text: str
    target_language: str


class AssistantRequest(BaseModel):
    message: str
    business_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None


class SceneUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration_seconds: Optional[float] = None
    text_overlay: Optional[str] = None
    media_url: Optional[str] = None
    voiceover_text: Optional[str] = None
    order_index: Optional[int] = None


@router.post("/plan")
def plan(payload: PlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = ai_service.plan_campaign(db, user, campaign_id=payload.campaign_id, brief=payload.brief)
    return success_response(result, message="Campaign plan generated")


@router.post("/generate")
def generate(payload: GenerateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = ai_service.generate_creative(db, user, campaign_id=payload.campaign_id, duration=payload.duration)
    return success_response(result, message="Creative generated")


@router.get("/generations/{generation_id}")
def get_generation(
    generation_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = ai_service.get_generation(db, user, generation_id)
    return success_response(
        {
            "id": str(record.id),
            "status": record.status,
            "generation_type": record.generation_type,
            "provider": record.provider,
            "is_mock": record.is_mock,
            "result_json": record.result_json,
            "error_message": record.error_message,
        }
    )


@router.post("/translate")
def translate(payload: TranslateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(ai_service.translate_script(db, user, payload.text, payload.target_language))


@router.post("/assistant")
def assistant(payload: AssistantRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = ai_service.assistant_chat(
        db,
        user,
        message=payload.message,
        business_id=payload.business_id,
        conversation_id=payload.conversation_id,
    )
    return success_response(result)


@router.get("/creatives")
def list_creatives(
    business_id: Optional[UUID] = None,
    campaign_id: Optional[UUID] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(AdCreative)
    if business_id:
        user_can_access_business(db, user, business_id)
        query = query.filter(AdCreative.business_id == business_id)
    if campaign_id:
        query = query.filter(AdCreative.campaign_id == campaign_id)
    creatives = query.order_by(AdCreative.created_at.desc()).limit(50).all()
    # ownership filter for non-admins without business_id
    if not business_id and not campaign_id:
        from app.services.business_service import list_businesses_for_user

        ids = [b.id for b in list_businesses_for_user(db, user)]
        creatives = [c for c in creatives if c.business_id in ids]
    return success_response([ai_service.serialize_creative(c) for c in creatives])


@router.get("/creatives/{creative_id}")
def get_creative(
    creative_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    creative = db.query(AdCreative).filter(AdCreative.id == creative_id).first()
    if not creative:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Creative not found")
    user_can_access_business(db, user, creative.business_id)
    return success_response(ai_service.serialize_creative(creative))


@router.patch("/creatives/{creative_id}/scenes/{scene_id}")
def update_scene(
    creative_id: UUID,
    scene_id: UUID,
    payload: SceneUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = ai_service.update_scene(
        db, user, creative_id, scene_id, payload.model_dump(exclude_unset=True)
    )
    return success_response(result)
