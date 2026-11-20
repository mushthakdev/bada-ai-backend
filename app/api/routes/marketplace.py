from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.response import success_response
from app.models.user import User
from app.services import channel_service, local_inventory_service

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


class LocalProviderCreate(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    description: Optional[str] = None


class LocalListingCreate(BaseModel):
    provider_id: UUID
    title: str
    inventory_type: str
    city: str
    state: str
    pincode: str = Field(min_length=6, max_length=6)
    price: float = Field(gt=0)
    address: Optional[str] = None
    district: Optional[str] = None
    screen_size: Optional[str] = None
    resolution: Optional[str] = None
    formats: Optional[str] = None
    operating_hours: Optional[str] = None
    available_slots: Optional[str] = None
    pricing_model: str = "cpm"
    estimated_impressions: Optional[int] = None
    language: Optional[str] = None
    photo_urls: Optional[str] = None


class ListingReview(BaseModel):
    status: str
    notes: Optional[str] = None


@router.get("/channels")
def marketplace_channels(
    category: Optional[str] = None,
    business_id: Optional[UUID] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = channel_service.list_marketplace_channels(db, category=category, business_id=business_id)
    return success_response(
        data,
        meta={
            "categories": [
                "ctv_ott",
                "video",
                "social",
                "publishers",
                "local",
                "outdoor",
                "regional",
            ],
            "note": "Pricing and availability are estimates unless a live partner confirms inventory.",
        },
    )


@router.get("/local")
def local_marketplace(
    city: Optional[str] = None,
    state: Optional[str] = None,
    pincode: Optional[str] = None,
    inventory_type: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        local_inventory_service.marketplace_listings(
            db, city=city, state=state, pincode=pincode, inventory_type=inventory_type
        )
    )


@router.post("/local/providers")
def register_local_provider(
    payload: LocalProviderCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        local_inventory_service.register_provider(db, user, **payload.model_dump()),
        message="Provider submitted for review",
    )


@router.post("/local/listings")
def submit_local_listing(
    payload: LocalListingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = payload.model_dump()
    provider_id = data.pop("provider_id")
    return success_response(
        local_inventory_service.submit_listing(db, user, provider_id=provider_id, payload=data),
        message="Listing submitted for admin approval",
    )


@router.get("/local/pending")
def pending_local(
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    return success_response(local_inventory_service.admin_pending_listings(db, user))


@router.post("/local/listings/{listing_id}/review")
def review_listing(
    listing_id: UUID,
    payload: ListingReview,
    user: User = Depends(require_roles("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    return success_response(
        local_inventory_service.admin_review_listing(
            db, user, listing_id, status=payload.status, notes=payload.notes
        )
    )
