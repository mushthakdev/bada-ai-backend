from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.services import creative_formats_service, media_planner_service, omnichannel_service

router = APIRouter(prefix="/omnichannel", tags=["omnichannel"])


class MediaPlanRequest(BaseModel):
    business_id: Optional[UUID] = None
    business_type: str
    product: str
    objective: str
    budget: float = Field(ge=1000)
    location: str
    audience: Optional[str] = None
    duration_days: int = Field(default=14, ge=1, le=365)
    selected_channels: Optional[list[str]] = None


class EqualAllocRequest(BaseModel):
    channel_codes: list[str]
    budget: float = Field(ge=1000)


class OmnichannelCreate(BaseModel):
    business_id: UUID
    name: str = Field(min_length=2, max_length=200)
    objective: str
    brief_text: Optional[str] = None
    language: str = "en"
    channel_codes: list[str] = Field(min_length=1)
    allocations: list[dict[str, Any]]
    locations: list[dict[str, Any]] = Field(default_factory=list)
    audience: Optional[dict[str, Any]] = None
    total_budget: float = Field(ge=1000)
    daily_budget: float = Field(ge=1000)
    start_date: date
    end_date: date
    media_plan: Optional[dict[str, Any]] = None


class AllocationUpdate(BaseModel):
    allocations: list[dict[str, Any]]


class ChannelAction(BaseModel):
    action: str  # pause | resume | stop
    channel_code: Optional[str] = None


class FormatsRequest(BaseModel):
    creative_id: UUID
    channel_codes: Optional[list[str]] = None


@router.post("/media-plan")
def media_plan(
    payload: MediaPlanRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = media_planner_service.recommend_media_plan(db, user, **payload.model_dump())
    return success_response(plan, message="Estimated media plan generated")


@router.post("/allocations/equal")
def equal_alloc(payload: EqualAllocRequest, user: User = Depends(get_current_user)):
    return success_response(
        media_planner_service.equal_allocation(payload.channel_codes, payload.budget)
    )


@router.post("/campaigns")
def create_campaign(
    payload: OmnichannelCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = omnichannel_service.create_omnichannel_campaign(
        db, user, **payload.model_dump()
    )
    return success_response(result, message="Omnichannel campaign created")


@router.get("/campaigns/{campaign_id}")
def get_campaign(
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(omnichannel_service.get_omnichannel_detail(db, user, campaign_id))


@router.patch("/campaigns/{campaign_id}/allocations")
def patch_allocations(
    campaign_id: UUID,
    payload: AllocationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        omnichannel_service.update_allocations(db, user, campaign_id, payload.allocations)
    )


@router.post("/campaigns/{campaign_id}/launch")
def launch(
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        omnichannel_service.launch_omnichannel(db, user, campaign_id),
        message="Launch attempted per channel (simulated / partner modes labeled)",
    )


@router.post("/campaigns/{campaign_id}/control")
def control(
    campaign_id: UUID,
    payload: ChannelAction,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        omnichannel_service.channel_control(
            db,
            user,
            campaign_id,
            channel_code=payload.channel_code,
            action=payload.action,
        )
    )


@router.get("/campaigns/{campaign_id}/analytics")
def analytics(
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(omnichannel_service.omnichannel_analytics(db, user, campaign_id))


@router.post("/creatives/formats")
def creative_formats(
    payload: FormatsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        creative_formats_service.generate_format_variants(
            db, user, creative_id=payload.creative_id, channel_codes=payload.channel_codes
        )
    )
