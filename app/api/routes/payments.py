from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.services import payment_service

router = APIRouter(prefix="/payments", tags=["payments"])


class CreateOrderRequest(BaseModel):
    campaign_id: UUID


class VerifyRequest(BaseModel):
    payment_id: UUID
    provider_payment_id: Optional[str] = None
    provider_signature: Optional[str] = None
    mock_success: bool = True


@router.post("/orders")
def create_order(
    payload: CreateOrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(payment_service.create_payment_order(db, user, payload.campaign_id))


@router.post("/verify")
def verify(
    payload: VerifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = payment_service.verify_payment(
        db,
        user,
        payment_id=payload.payment_id,
        provider_payment_id=payload.provider_payment_id,
        provider_signature=payload.provider_signature,
        mock_success=payload.mock_success,
    )
    return success_response(result, message="Payment verified")


@router.get("")
def list_payments(
    business_id: Optional[UUID] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(payment_service.list_payments(db, user, business_id))
