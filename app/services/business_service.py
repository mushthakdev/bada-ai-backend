from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.models.business import Business, BusinessMembership
from app.models.user import User
from app.schemas.business import (
    BusinessCreate,
    BusinessOut,
    BusinessUpdate,
    OnboardingPayload,
)


def user_can_access_business(db: Session, user: User, business_id: UUID) -> Business:
    business = (
        db.query(Business)
        .filter(Business.id == business_id, Business.is_deleted.is_(False))
        .first()
    )
    if not business:
        raise NotFoundError("Business not found")

    role = user.role.name if user.role else ""
    if role in ("admin", "super_admin"):
        return business
    if business.owner_id == user.id:
        return business

    membership = (
        db.query(BusinessMembership)
        .filter(
            BusinessMembership.business_id == business_id,
            BusinessMembership.user_id == user.id,
            BusinessMembership.is_active.is_(True),
        )
        .first()
    )
    if membership:
        return business

    if role == "agency" and business.agency_id:
        from app.models.agency import AgencyMember

        agency_member = (
            db.query(AgencyMember)
            .filter(
                AgencyMember.agency_id == business.agency_id,
                AgencyMember.user_id == user.id,
                AgencyMember.is_active.is_(True),
            )
            .first()
        )
        if agency_member:
            return business

    raise ForbiddenError("You do not have access to this business")


def list_businesses_for_user(db: Session, user: User) -> list[Business]:
    role = user.role.name if user.role else ""
    if role in ("admin", "super_admin"):
        return db.query(Business).filter(Business.is_deleted.is_(False)).order_by(Business.created_at.desc()).all()

    owned = db.query(Business).filter(Business.owner_id == user.id, Business.is_deleted.is_(False))
    member_ids = [
        m.business_id
        for m in db.query(BusinessMembership)
        .filter(BusinessMembership.user_id == user.id, BusinessMembership.is_active.is_(True))
        .all()
    ]
    member_businesses = (
        db.query(Business)
        .filter(Business.id.in_(member_ids), Business.is_deleted.is_(False))
        .all()
        if member_ids
        else []
    )
    result = {b.id: b for b in owned.all()}
    for b in member_businesses:
        result[b.id] = b
    return sorted(result.values(), key=lambda x: x.created_at, reverse=True)


def create_business(db: Session, user: User, payload: BusinessCreate) -> Business:
    business = Business(
        owner_id=user.id,
        name=payload.name,
        category=payload.category,
        description=payload.description,
        website=payload.website,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        pincode=payload.pincode,
        country=payload.country,
        onboarding_step=1,
    )
    db.add(business)
    db.flush()
    db.add(
        BusinessMembership(
            business_id=business.id,
            user_id=user.id,
            role="owner",
        )
    )
    db.commit()
    db.refresh(business)
    return business


def update_business(db: Session, user: User, business_id: UUID, payload: BusinessUpdate) -> Business:
    business = user_can_access_business(db, user, business_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(business, key, value)
    db.commit()
    db.refresh(business)
    return business


def process_onboarding(db: Session, user: User, payload: OnboardingPayload) -> Business:
    businesses = list_businesses_for_user(db, user)
    business: Optional[Business] = businesses[0] if businesses else None

    if not business:
        business = create_business(db, user, payload.business)
    else:
        for key, value in payload.business.model_dump().items():
            setattr(business, key, value)

    if payload.brand:
        for key, value in payload.brand.model_dump(exclude_unset=True).items():
            setattr(business, key, value)

    if payload.advertising_objective:
        business.advertising_objective = payload.advertising_objective

    if payload.audience:
        business.target_languages = ",".join(payload.audience.languages)
        if payload.audience.target_city:
            business.city = payload.audience.target_city
        if payload.audience.target_state:
            business.state = payload.audience.target_state

    business.onboarding_step = max(business.onboarding_step, payload.step)
    if payload.step >= 5:
        business.onboarding_completed = True
        user.onboarding_completed = True

    db.commit()
    db.refresh(business)
    return business


def to_business_out(business: Business) -> BusinessOut:
    return BusinessOut.model_validate(business)
