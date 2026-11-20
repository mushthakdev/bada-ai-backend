from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.schemas.business import BusinessCreate, BusinessUpdate, OnboardingPayload
from app.services import business_service

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("")
def list_businesses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = business_service.list_businesses_for_user(db, user)
    return success_response([business_service.to_business_out(b).model_dump() for b in items])


@router.post("")
def create_business(
    payload: BusinessCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    business = business_service.create_business(db, user, payload)
    return success_response(business_service.to_business_out(business).model_dump(), message="Business created")


@router.get("/{business_id}")
def get_business(
    business_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    business = business_service.user_can_access_business(db, user, business_id)
    return success_response(business_service.to_business_out(business).model_dump())


@router.patch("/{business_id}")
def update_business(
    business_id: UUID,
    payload: BusinessUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    business = business_service.update_business(db, user, business_id, payload)
    return success_response(business_service.to_business_out(business).model_dump())
