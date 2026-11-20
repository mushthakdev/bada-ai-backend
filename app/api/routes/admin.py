from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.exceptions import NotFoundError
from app.core.response import success_response
from app.models.ai import AIGeneration, AIUsage
from app.models.agency import Agency
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.creative import AdCreative
from app.models.inventory import AdInventory, PublisherPartner
from app.models.lead import Lead
from app.models.payment import Payment
from app.models.settings import SystemSetting
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


class SettingUpdate(BaseModel):
    value: str
    description: Optional[str] = None


class CreativeApproval(BaseModel):
    approval_status: str
    notes: Optional[str] = None


@router.get("/dashboard")
def admin_dashboard(
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    return success_response(
        {
            "users": db.query(func.count(User.id)).scalar() or 0,
            "businesses": db.query(func.count(Business.id)).filter(Business.is_deleted.is_(False)).scalar() or 0,
            "agencies": db.query(func.count(Agency.id)).filter(Agency.is_deleted.is_(False)).scalar() or 0,
            "campaigns": db.query(func.count(Campaign.id)).filter(Campaign.is_deleted.is_(False)).scalar() or 0,
            "active_campaigns": db.query(func.count(Campaign.id))
            .filter(Campaign.status == "active", Campaign.is_deleted.is_(False))
            .scalar()
            or 0,
            "payments": db.query(func.count(Payment.id)).scalar() or 0,
            "revenue": db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.status == "paid")
            .scalar()
            or 0,
            "leads": db.query(func.count(Lead.id)).scalar() or 0,
            "ai_generations": db.query(func.count(AIGeneration.id)).scalar() or 0,
        }
    )


@router.get("/users")
def list_users(
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    users = db.query(User).options(joinedload(User.role)).filter(User.is_deleted.is_(False)).all()
    return success_response(
        [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role.name if u.role else None,
                "is_active": u.is_active,
                "is_verified": u.is_verified,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ]
    )


@router.get("/campaigns")
def list_campaigns(
    status: Optional[str] = None,
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    query = db.query(Campaign).filter(Campaign.is_deleted.is_(False))
    if status:
        query = query.filter(Campaign.status == status)
    campaigns = query.order_by(Campaign.created_at.desc()).limit(100).all()
    return success_response(
        [
            {
                "id": str(c.id),
                "name": c.name,
                "status": c.status,
                "business_id": str(c.business_id),
                "is_simulated_delivery": c.is_simulated_delivery,
                "created_at": c.created_at.isoformat(),
            }
            for c in campaigns
        ]
    )


@router.get("/creatives/pending")
def pending_creatives(
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    creatives = (
        db.query(AdCreative)
        .filter(AdCreative.approval_status == "pending")
        .order_by(AdCreative.created_at.desc())
        .all()
    )
    return success_response(
        [
            {
                "id": str(c.id),
                "title": c.title,
                "status": c.status,
                "is_mock": c.is_mock,
                "campaign_id": str(c.campaign_id) if c.campaign_id else None,
                "approval_status": c.approval_status,
            }
            for c in creatives
        ]
    )


@router.post("/creatives/{creative_id}/approval")
def approve_creative(
    creative_id: UUID,
    payload: CreativeApproval,
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    creative = db.query(AdCreative).filter(AdCreative.id == creative_id).first()
    if not creative:
        raise NotFoundError("Creative not found")
    creative.approval_status = payload.approval_status
    creative.approval_notes = payload.notes
    if payload.approval_status == "approved":
        creative.status = "approved"
        if creative.campaign_id:
            campaign = db.query(Campaign).filter(Campaign.id == creative.campaign_id).first()
            if campaign and campaign.status == "ready_for_review":
                campaign.status = "approved"
    elif payload.approval_status == "rejected":
        creative.status = "rejected"
    db.commit()
    return success_response({"id": str(creative.id), "approval_status": creative.approval_status})


@router.get("/ai/logs")
def ai_logs(
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    rows = db.query(AIGeneration).order_by(AIGeneration.created_at.desc()).limit(100).all()
    return success_response(
        [
            {
                "id": str(r.id),
                "type": r.generation_type,
                "provider": r.provider,
                "status": r.status,
                "is_mock": r.is_mock,
                "tokens_used": r.tokens_used,
                "estimated_cost": r.estimated_cost,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    )


@router.get("/publishers")
def publishers(
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    rows = db.query(PublisherPartner).order_by(PublisherPartner.created_at.desc()).all()
    return success_response(
        [
            {
                "id": str(p.id),
                "name": p.name,
                "inventory_type": p.inventory_type,
                "status": p.status,
                "is_simulated": p.is_simulated,
                "default_cpm": p.default_cpm,
            }
            for p in rows
        ]
    )


@router.get("/inventory")
def inventory(
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    rows = db.query(AdInventory).limit(100).all()
    return success_response(
        [
            {
                "id": str(i.id),
                "name": i.name,
                "inventory_type": i.inventory_type,
                "city": i.city,
                "pincode": i.pincode,
                "cpm": i.cpm,
                "available_impressions": i.available_impressions,
                "is_simulated": i.is_simulated,
            }
            for i in rows
        ]
    )


@router.get("/settings")
def get_settings(
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    rows = db.query(SystemSetting).order_by(SystemSetting.key.asc()).all()
    return success_response(
        [
            {
                "key": s.key,
                "value": s.value,
                "description": s.description,
                "category": s.category,
            }
            for s in rows
        ]
    )


@router.put("/settings/{key}")
def update_setting(
    key: str,
    payload: SettingUpdate,
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        setting = SystemSetting(key=key, value=payload.value, description=payload.description)
        db.add(setting)
    else:
        setting.value = payload.value
        if payload.description is not None:
            setting.description = payload.description
    db.commit()
    return success_response({"key": key, "value": setting.value})


@router.get("/payments")
def admin_payments(
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    rows = db.query(Payment).order_by(Payment.created_at.desc()).limit(100).all()
    return success_response(
        [
            {
                "id": str(p.id),
                "amount": p.amount,
                "status": p.status,
                "provider": p.provider,
                "is_mock": p.is_mock,
                "created_at": p.created_at.isoformat(),
            }
            for p in rows
        ]
    )
