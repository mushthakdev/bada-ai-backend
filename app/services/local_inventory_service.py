from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.models.channels import LocalAdProvider, LocalInventoryListing
from app.models.user import User


def register_provider(
    db: Session,
    user: User,
    *,
    business_name: str,
    contact_name: Optional[str],
    contact_email: Optional[str],
    contact_phone: Optional[str],
    description: Optional[str],
) -> dict[str, Any]:
    provider = LocalAdProvider(
        owner_user_id=user.id,
        business_name=business_name,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        description=description,
        status="pending_review",
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return _serialize_provider(provider)


def submit_listing(
    db: Session,
    user: User,
    *,
    provider_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    provider = db.query(LocalAdProvider).filter(LocalAdProvider.id == provider_id).first()
    if not provider or provider.is_deleted:
        raise NotFoundError("Local provider not found")
    role = user.role.name if user.role else ""
    if provider.owner_user_id != user.id and role not in ("admin", "super_admin"):
        raise ForbiddenError("Not allowed to add inventory for this provider")

    listing = LocalInventoryListing(
        provider_id=provider.id,
        title=payload["title"],
        inventory_type=payload["inventory_type"],
        address=payload.get("address"),
        city=payload["city"],
        district=payload.get("district"),
        state=payload["state"],
        pincode=payload["pincode"],
        screen_size=payload.get("screen_size"),
        resolution=payload.get("resolution"),
        formats=payload.get("formats"),
        operating_hours=payload.get("operating_hours"),
        available_slots=payload.get("available_slots"),
        pricing_model=payload.get("pricing_model", "cpm"),
        price=float(payload["price"]),
        estimated_impressions=payload.get("estimated_impressions"),
        language=payload.get("language"),
        photo_urls=payload.get("photo_urls"),
        status="pending_review",
        is_estimate=True,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return _serialize_listing(listing)


def marketplace_listings(
    db: Session,
    *,
    city: Optional[str] = None,
    state: Optional[str] = None,
    pincode: Optional[str] = None,
    inventory_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = db.query(LocalInventoryListing).filter(
        LocalInventoryListing.is_deleted.is_(False),
        LocalInventoryListing.status == "approved",
    )
    if city:
        query = query.filter(LocalInventoryListing.city.ilike(f"%{city}%"))
    if state:
        query = query.filter(LocalInventoryListing.state.ilike(f"%{state}%"))
    if pincode:
        query = query.filter(LocalInventoryListing.pincode == pincode)
    if inventory_type:
        query = query.filter(LocalInventoryListing.inventory_type == inventory_type)
    rows = query.order_by(LocalInventoryListing.created_at.desc()).limit(100).all()
    return [_serialize_listing(r) for r in rows]


def admin_review_listing(
    db: Session,
    user: User,
    listing_id: UUID,
    *,
    status: str,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    role = user.role.name if user.role else ""
    if role not in ("admin", "super_admin"):
        raise ForbiddenError("Admin only")
    if status not in ("approved", "rejected"):
        raise ValidationAppError("Status must be approved or rejected")
    listing = db.query(LocalInventoryListing).filter(LocalInventoryListing.id == listing_id).first()
    if not listing:
        raise NotFoundError("Listing not found")
    listing.status = status
    listing.admin_notes = notes
    if status == "approved" and listing.provider:
        listing.provider.status = "active"
    db.commit()
    return _serialize_listing(listing)


def admin_pending_listings(db: Session, user: User) -> list[dict[str, Any]]:
    role = user.role.name if user.role else ""
    if role not in ("admin", "super_admin"):
        raise ForbiddenError("Admin only")
    rows = (
        db.query(LocalInventoryListing)
        .filter(LocalInventoryListing.status == "pending_review", LocalInventoryListing.is_deleted.is_(False))
        .order_by(LocalInventoryListing.created_at.desc())
        .all()
    )
    return [_serialize_listing(r) for r in rows]


def _serialize_provider(p: LocalAdProvider) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "business_name": p.business_name,
        "contact_name": p.contact_name,
        "contact_email": p.contact_email,
        "status": p.status,
        "description": p.description,
    }


def _serialize_listing(r: LocalInventoryListing) -> dict[str, Any]:
    provider_name = None
    if getattr(r, "provider", None) is not None:
        provider_name = r.provider.business_name
    return {
        "id": str(r.id),
        "provider_id": str(r.provider_id),
        "provider_name": provider_name,
        "title": r.title,
        "inventory_type": r.inventory_type,
        "address": r.address,
        "city": r.city,
        "district": r.district,
        "state": r.state,
        "pincode": r.pincode,
        "screen_size": r.screen_size,
        "resolution": r.resolution,
        "formats": r.formats,
        "operating_hours": r.operating_hours,
        "pricing_model": r.pricing_model,
        "price": r.price,
        "estimated_impressions": r.estimated_impressions,
        "language": r.language,
        "status": r.status,
        "is_estimate": r.is_estimate,
        "admin_notes": r.admin_notes,
        "disclaimer": "Local inventory impressions and pricing are estimates until verified by ops.",
    }
