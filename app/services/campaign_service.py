from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.campaign import (
    Campaign,
    CampaignAudience,
    CampaignBudget,
    CampaignLocation,
    CampaignSchedule,
)
from app.models.user import User
from app.schemas.campaign import (
    BudgetBreakdownOut,
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
)
from app.services.business_service import user_can_access_business
from app.services.pricing import calculate_budget

VALID_TRANSITIONS = {
    "draft": {"creative_generating", "ready_for_review", "cancelled"},
    "creative_generating": {"ready_for_review", "failed", "draft"},
    "ready_for_review": {"approved", "rejected", "draft"},
    "approved": {"payment_pending", "cancelled"},
    "payment_pending": {"scheduled", "cancelled", "payment_pending"},
    "scheduled": {"active", "cancelled", "paused"},
    "active": {"paused", "completed", "cancelled"},
    "paused": {"active", "cancelled", "completed"},
    "rejected": {"draft", "cancelled"},
    "failed": {"draft", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _serialize_campaign(campaign: Campaign) -> CampaignOut:
    budget = None
    if campaign.budget:
        budget = BudgetBreakdownOut(
            daily_budget=campaign.budget.daily_budget,
            total_budget=campaign.budget.total_budget,
            estimated_cpm=campaign.budget.estimated_cpm,
            estimated_impressions=campaign.budget.estimated_impressions,
            estimated_reach=campaign.budget.estimated_reach,
            media_spend=campaign.budget.media_spend,
            platform_fee=campaign.budget.platform_fee,
            tax_amount=campaign.budget.tax_amount,
            total_payable=campaign.budget.total_payable,
            is_estimate=campaign.budget.is_estimate,
            currency=campaign.budget.currency,
        )
    return CampaignOut(
        id=campaign.id,
        business_id=campaign.business_id,
        name=campaign.name,
        objective=campaign.objective,
        description=campaign.description,
        language=campaign.language,
        status=campaign.status,
        video_duration=campaign.video_duration,
        brief_text=campaign.brief_text,
        is_simulated_delivery=campaign.is_simulated_delivery,
        created_at=campaign.created_at,
        budget=budget,
        location_count=len(campaign.locations or []),
        start_date=campaign.schedule.start_date if campaign.schedule else None,
        end_date=campaign.schedule.end_date if campaign.schedule else None,
    )


def list_campaigns(
    db: Session,
    user: User,
    business_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> list[CampaignOut]:
    query = db.query(Campaign).filter(Campaign.is_deleted.is_(False))
    if business_id:
        user_can_access_business(db, user, business_id)
        query = query.filter(Campaign.business_id == business_id)
    else:
        from app.services.business_service import list_businesses_for_user

        businesses = list_businesses_for_user(db, user)
        ids = [b.id for b in businesses]
        if not ids:
            return []
        query = query.filter(Campaign.business_id.in_(ids))

    if status:
        query = query.filter(Campaign.status == status)

    campaigns = query.order_by(Campaign.created_at.desc()).all()
    return [_serialize_campaign(c) for c in campaigns]


def get_campaign(db: Session, user: User, campaign_id: UUID) -> Campaign:
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.is_deleted.is_(False))
        .first()
    )
    if not campaign:
        raise NotFoundError("Campaign not found")
    user_can_access_business(db, user, campaign.business_id)
    return campaign


def create_campaign(db: Session, user: User, payload: CampaignCreate) -> CampaignOut:
    user_can_access_business(db, user, payload.business_id)

    if payload.schedule and payload.schedule.end_date < payload.schedule.start_date:
        raise ValidationAppError("End date must be after start date")

    campaign = Campaign(
        business_id=payload.business_id,
        created_by=user.id,
        name=payload.name,
        objective=payload.objective,
        description=payload.description,
        language=payload.language,
        video_duration=payload.video_duration,
        brief_text=payload.brief_text,
        status="draft",
        is_simulated_delivery=True,
    )
    db.add(campaign)
    db.flush()

    if payload.audience:
        db.add(
            CampaignAudience(
                campaign_id=campaign.id,
                demographics=payload.audience.demographics,
                interests=payload.audience.interests,
                languages=",".join(payload.audience.languages),
                age_min=payload.audience.age_min,
                age_max=payload.audience.age_max,
                gender=payload.audience.gender,
            )
        )

    pincodes: list[str] = []
    for loc in payload.locations:
        pincodes.append(loc.pincode)
        from app.models.inventory import PincodeInventory

        pin = db.query(PincodeInventory).filter(PincodeInventory.pincode == loc.pincode).first()
        db.add(
            CampaignLocation(
                campaign_id=campaign.id,
                pincode=loc.pincode,
                city=loc.city or (pin.city if pin else None),
                state=loc.state or (pin.state if pin else None),
                district=loc.district or (pin.district if pin else None),
                estimated_audience=pin.estimated_ctv_reach if pin else None,
                is_estimate=True,
            )
        )

    if payload.budget:
        breakdown = calculate_budget(
            db,
            daily_budget=payload.budget.daily_budget,
            total_budget=payload.budget.total_budget,
            pincodes=pincodes,
        )
        db.add(
            CampaignBudget(
                campaign_id=campaign.id,
                daily_budget=breakdown.daily_budget,
                total_budget=breakdown.total_budget,
                estimated_cpm=breakdown.estimated_cpm,
                estimated_impressions=breakdown.estimated_impressions,
                estimated_reach=breakdown.estimated_reach,
                media_spend=breakdown.media_spend,
                platform_fee=breakdown.platform_fee,
                tax_amount=breakdown.tax_amount,
                total_payable=breakdown.total_payable,
                is_estimate=breakdown.is_estimate,
            )
        )

    if payload.schedule:
        db.add(
            CampaignSchedule(
                campaign_id=campaign.id,
                start_date=payload.schedule.start_date,
                end_date=payload.schedule.end_date,
                preferred_slots=payload.schedule.preferred_slots,
                prime_time=payload.schedule.prime_time,
                daily_impression_cap=payload.schedule.daily_impression_cap,
                frequency_cap=payload.schedule.frequency_cap,
            )
        )

    db.commit()
    db.refresh(campaign)
    return _serialize_campaign(campaign)


def update_campaign(db: Session, user: User, campaign_id: UUID, payload: CampaignUpdate) -> CampaignOut:
    campaign = get_campaign(db, user, campaign_id)
    if campaign.status not in ("draft", "ready_for_review", "rejected", "payment_pending"):
        raise ValidationAppError("Campaign cannot be edited in its current status")

    data = payload.model_dump(exclude_unset=True, exclude={"locations", "audience", "budget", "schedule"})
    for key, value in data.items():
        setattr(campaign, key, value)

    if payload.locations is not None:
        db.query(CampaignLocation).filter(CampaignLocation.campaign_id == campaign.id).delete()
        for loc in payload.locations:
            db.add(
                CampaignLocation(
                    campaign_id=campaign.id,
                    pincode=loc.pincode,
                    city=loc.city,
                    state=loc.state,
                    district=loc.district,
                    is_estimate=True,
                )
            )

    if payload.audience is not None:
        if campaign.audience:
            campaign.audience.demographics = payload.audience.demographics
            campaign.audience.interests = payload.audience.interests
            campaign.audience.languages = ",".join(payload.audience.languages)
            campaign.audience.age_min = payload.audience.age_min
            campaign.audience.age_max = payload.audience.age_max
            campaign.audience.gender = payload.audience.gender
        else:
            db.add(
                CampaignAudience(
                    campaign_id=campaign.id,
                    demographics=payload.audience.demographics,
                    interests=payload.audience.interests,
                    languages=",".join(payload.audience.languages),
                    age_min=payload.audience.age_min,
                    age_max=payload.audience.age_max,
                    gender=payload.audience.gender,
                )
            )

    if payload.budget is not None:
        pincodes = [l.pincode for l in (campaign.locations or [])]
        breakdown = calculate_budget(
            db,
            daily_budget=payload.budget.daily_budget,
            total_budget=payload.budget.total_budget,
            pincodes=pincodes,
        )
        if campaign.budget:
            for field in (
                "daily_budget",
                "total_budget",
                "estimated_cpm",
                "estimated_impressions",
                "estimated_reach",
                "media_spend",
                "platform_fee",
                "tax_amount",
                "total_payable",
                "is_estimate",
            ):
                setattr(campaign.budget, field, getattr(breakdown, field))
        else:
            db.add(
                CampaignBudget(
                    campaign_id=campaign.id,
                    daily_budget=breakdown.daily_budget,
                    total_budget=breakdown.total_budget,
                    estimated_cpm=breakdown.estimated_cpm,
                    estimated_impressions=breakdown.estimated_impressions,
                    estimated_reach=breakdown.estimated_reach,
                    media_spend=breakdown.media_spend,
                    platform_fee=breakdown.platform_fee,
                    tax_amount=breakdown.tax_amount,
                    total_payable=breakdown.total_payable,
                    is_estimate=breakdown.is_estimate,
                )
            )

    if payload.schedule is not None:
        if payload.schedule.end_date < payload.schedule.start_date:
            raise ValidationAppError("End date must be after start date")
        if campaign.schedule:
            campaign.schedule.start_date = payload.schedule.start_date
            campaign.schedule.end_date = payload.schedule.end_date
            campaign.schedule.preferred_slots = payload.schedule.preferred_slots
            campaign.schedule.prime_time = payload.schedule.prime_time
            campaign.schedule.daily_impression_cap = payload.schedule.daily_impression_cap
            campaign.schedule.frequency_cap = payload.schedule.frequency_cap
        else:
            db.add(
                CampaignSchedule(
                    campaign_id=campaign.id,
                    start_date=payload.schedule.start_date,
                    end_date=payload.schedule.end_date,
                    preferred_slots=payload.schedule.preferred_slots,
                    prime_time=payload.schedule.prime_time,
                    daily_impression_cap=payload.schedule.daily_impression_cap,
                    frequency_cap=payload.schedule.frequency_cap,
                )
            )

    db.commit()
    db.refresh(campaign)
    return _serialize_campaign(campaign)


def transition_status(db: Session, user: User, campaign_id: UUID, new_status: str) -> CampaignOut:
    campaign = get_campaign(db, user, campaign_id)
    allowed = VALID_TRANSITIONS.get(campaign.status, set())
    # Normalize status names to snake_case matching DB
    normalized = new_status.replace("-", "_").replace(" ", "_").lower()
    status_map = {
        "creativegenerating": "creative_generating",
        "readyforreview": "ready_for_review",
        "paymentpending": "payment_pending",
    }
    normalized = status_map.get(normalized.replace("_", ""), normalized)
    if normalized not in allowed and user.role.name not in ("admin", "super_admin"):
        raise ValidationAppError(f"Cannot transition from {campaign.status} to {normalized}")
    campaign.status = normalized
    db.commit()
    db.refresh(campaign)
    return _serialize_campaign(campaign)


def duplicate_campaign(db: Session, user: User, campaign_id: UUID) -> CampaignOut:
    original = get_campaign(db, user, campaign_id)
    payload = CampaignCreate(
        business_id=original.business_id,
        name=f"{original.name} (Copy)",
        objective=original.objective,
        description=original.description,
        language=original.language,
        video_duration=original.video_duration,
        brief_text=original.brief_text,
        locations=[
            {"pincode": loc.pincode, "city": loc.city, "state": loc.state, "district": loc.district}
            for loc in original.locations
        ],
    )
    return create_campaign(db, user, payload)


def estimate_pricing(db: Session, daily_budget: float, total_budget: float, pincodes: list[str]) -> BudgetBreakdownOut:
    breakdown = calculate_budget(
        db, daily_budget=daily_budget, total_budget=total_budget, pincodes=pincodes
    )
    return BudgetBreakdownOut(**breakdown.__dict__)
