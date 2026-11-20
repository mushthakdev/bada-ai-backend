from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.lead import Lead
from app.models.notification import Notification
from app.models.user import User
from app.services.business_service import list_businesses_for_user, user_can_access_business


def list_leads(
    db: Session,
    user: User,
    *,
    business_id: Optional[UUID] = None,
    campaign_id: Optional[UUID] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = db.query(Lead)
    if business_id:
        user_can_access_business(db, user, business_id)
        query = query.filter(Lead.business_id == business_id)
    else:
        ids = [b.id for b in list_businesses_for_user(db, user)]
        if not ids:
            return []
        query = query.filter(Lead.business_id.in_(ids))

    if campaign_id:
        query = query.filter(Lead.campaign_id == campaign_id)
    if status:
        query = query.filter(Lead.status == status)
    if source:
        query = query.filter(Lead.source == source)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (Lead.name.ilike(like)) | (Lead.phone.ilike(like)) | (Lead.email.ilike(like))
        )

    leads = query.order_by(Lead.created_at.desc()).all()
    return [_serialize(l) for l in leads]


def create_lead(
    db: Session,
    *,
    business_id: UUID,
    campaign_id: Optional[UUID],
    name: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    inquiry: Optional[str],
    source: str,
    pincode: Optional[str] = None,
    notify_user_id: Optional[UUID] = None,
) -> Lead:
    lead = Lead(
        business_id=business_id,
        campaign_id=campaign_id,
        name=name,
        phone=phone,
        email=email,
        inquiry=inquiry,
        source=source,
        pincode=pincode,
        status="new",
    )
    db.add(lead)
    if notify_user_id:
        db.add(
            Notification(
                user_id=notify_user_id,
                title="New lead received",
                message=f"New {source} lead" + (f" from {name}" if name else "") + ".",
                type="new_lead",
                entity_type="lead",
            )
        )
    db.commit()
    db.refresh(lead)
    return lead


def update_lead(
    db: Session,
    user: User,
    lead_id: UUID,
    *,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise NotFoundError("Lead not found")
    user_can_access_business(db, user, lead.business_id)
    if status:
        lead.status = status
    if notes is not None:
        lead.notes = notes
    db.commit()
    db.refresh(lead)
    return _serialize(lead)


def _serialize(lead: Lead) -> dict[str, Any]:
    return {
        "id": str(lead.id),
        "business_id": str(lead.business_id),
        "campaign_id": str(lead.campaign_id) if lead.campaign_id else None,
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "inquiry": lead.inquiry,
        "source": lead.source,
        "pincode": lead.pincode,
        "status": lead.status,
        "notes": lead.notes,
        "created_at": lead.created_at.isoformat(),
    }
