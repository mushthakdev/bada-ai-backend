from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import success_response
from app.models.agency import Agency, AgencyClient, AgencyMember
from app.models.business import Business
from app.models.user import User
from app.services.business_service import to_business_out

router = APIRouter(prefix="/agencies", tags=["agencies"])


class AgencyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    legal_name: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    description: Optional[str] = None


class ClientAssign(BaseModel):
    business_id: UUID


def _require_agency_access(db: Session, user: User, agency_id: UUID) -> Agency:
    agency = db.query(Agency).filter(Agency.id == agency_id, Agency.is_deleted.is_(False)).first()
    if not agency:
        raise NotFoundError("Agency not found")
    role = user.role.name if user.role else ""
    if role in ("admin", "super_admin") or agency.owner_id == user.id:
        return agency
    member = (
        db.query(AgencyMember)
        .filter(
            AgencyMember.agency_id == agency_id,
            AgencyMember.user_id == user.id,
            AgencyMember.is_active.is_(True),
        )
        .first()
    )
    if not member:
        raise ForbiddenError("No access to this agency")
    return agency


@router.post("")
def create_agency(
    payload: AgencyCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = user.role.name if user.role else ""
    if role not in ("agency", "admin", "super_admin"):
        raise ForbiddenError("Only agency accounts can create an agency")
    agency = Agency(
        owner_id=user.id,
        name=payload.name,
        legal_name=payload.legal_name,
        website=payload.website,
        email=payload.email,
        phone=payload.phone,
        description=payload.description,
    )
    db.add(agency)
    db.flush()
    db.add(AgencyMember(agency_id=agency.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(agency)
    return success_response(
        {
            "id": str(agency.id),
            "name": agency.name,
            "status": agency.status,
        },
        message="Agency created",
    )


@router.get("")
def list_agencies(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    role = user.role.name if user.role else ""
    if role in ("admin", "super_admin"):
        agencies = db.query(Agency).filter(Agency.is_deleted.is_(False)).all()
    else:
        member_ids = [
            m.agency_id
            for m in db.query(AgencyMember)
            .filter(AgencyMember.user_id == user.id, AgencyMember.is_active.is_(True))
            .all()
        ]
        agencies = (
            db.query(Agency)
            .filter(Agency.id.in_(member_ids), Agency.is_deleted.is_(False))
            .all()
            if member_ids
            else []
        )
    return success_response(
        [
            {
                "id": str(a.id),
                "name": a.name,
                "status": a.status,
                "white_label_enabled": a.white_label_enabled,
            }
            for a in agencies
        ]
    )


@router.get("/{agency_id}/clients")
def list_clients(
    agency_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_agency_access(db, user, agency_id)
    clients = db.query(AgencyClient).filter(AgencyClient.agency_id == agency_id).all()
    result = []
    for c in clients:
        business = db.query(Business).filter(Business.id == c.business_id).first()
        if business:
            result.append(
                {
                    "client_id": str(c.id),
                    "status": c.status,
                    "business": to_business_out(business).model_dump(),
                }
            )
    return success_response(result)


@router.post("/{agency_id}/clients")
def assign_client(
    agency_id: UUID,
    payload: ClientAssign,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agency = _require_agency_access(db, user, agency_id)
    business = db.query(Business).filter(Business.id == payload.business_id).first()
    if not business:
        raise NotFoundError("Business not found")
    existing = (
        db.query(AgencyClient)
        .filter(AgencyClient.agency_id == agency_id, AgencyClient.business_id == payload.business_id)
        .first()
    )
    if existing:
        raise ValidationAppError("Client already assigned")
    business.agency_id = agency.id
    db.add(AgencyClient(agency_id=agency.id, business_id=business.id))
    db.commit()
    return success_response(message="Client assigned")
