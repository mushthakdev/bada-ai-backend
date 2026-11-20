from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignStatusUpdate, CampaignUpdate
from app.services import campaign_service

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class EstimateRequest(BaseModel):
    daily_budget: float = Field(ge=1000)
    total_budget: float = Field(ge=1000)
    pincodes: list[str] = Field(default_factory=list)


@router.get("")
def list_campaigns(
    business_id: Optional[UUID] = None,
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = campaign_service.list_campaigns(db, user, business_id=business_id, status=status)
    return success_response([i.model_dump() for i in items])


@router.post("")
def create_campaign(
    payload: CampaignCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = campaign_service.create_campaign(db, user, payload)
    return success_response(item.model_dump(), message="Campaign created")


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campaign = campaign_service.get_campaign(db, user, campaign_id)
    return success_response(campaign_service._serialize_campaign(campaign).model_dump())


@router.patch("/{campaign_id}")
def update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = campaign_service.update_campaign(db, user, campaign_id, payload)
    return success_response(item.model_dump())


@router.post("/{campaign_id}/status")
def update_status(
    campaign_id: UUID,
    payload: CampaignStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = campaign_service.transition_status(db, user, campaign_id, payload.status)
    return success_response(item.model_dump())


@router.post("/{campaign_id}/duplicate")
def duplicate(
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = campaign_service.duplicate_campaign(db, user, campaign_id)
    return success_response(item.model_dump(), message="Campaign duplicated")


@router.post("/estimate")
def estimate(payload: EstimateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    breakdown = campaign_service.estimate_pricing(
        db, payload.daily_budget, payload.total_budget, payload.pincodes
    )
    return success_response(breakdown.model_dump())
