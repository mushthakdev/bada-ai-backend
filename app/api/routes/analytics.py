from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard")
def dashboard(
    business_id: Optional[UUID] = None,
    range: str = Query(default="30d", pattern="^(today|7d|30d|90d|custom)$"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = analytics_service.get_dashboard_metrics(
        db, user, business_id=business_id, range_key=range, start=start, end=end
    )
    return success_response(data)


@router.get("/campaigns/{campaign_id}")
def campaign_analytics(
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(analytics_service.get_campaign_analytics(db, user, campaign_id))
