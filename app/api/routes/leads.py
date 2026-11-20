from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.services import lead_service

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
def list_leads(
    business_id: Optional[UUID] = None,
    campaign_id: Optional[UUID] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        lead_service.list_leads(
            db,
            user,
            business_id=business_id,
            campaign_id=campaign_id,
            status=status,
            source=source,
            search=search,
        )
    )


@router.patch("/{lead_id}")
def update_lead(
    lead_id: UUID,
    payload: LeadUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        lead_service.update_lead(db, user, lead_id, status=payload.status, notes=payload.notes)
    )
