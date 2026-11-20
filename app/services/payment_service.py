from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.base import utcnow
from app.models.notification import Notification
from app.models.payment import Invoice, Payment, Transaction
from app.models.user import User
from app.services.campaign_service import get_campaign

settings = get_settings()


def create_payment_order(db: Session, user: User, campaign_id: UUID) -> dict[str, Any]:
    campaign = get_campaign(db, user, campaign_id)
    if not campaign.budget:
        raise ValidationAppError("Campaign budget is required before payment")
    if campaign.status not in ("approved", "payment_pending", "ready_for_review"):
        # Allow payment after creative is ready/approved
        if campaign.status not in ("ready_for_review", "approved", "payment_pending"):
            raise ValidationAppError("Campaign is not eligible for payment")

    amount = campaign.budget.total_payable
    is_mock = settings.payment_mock_mode
    order_id = f"{'mock' if is_mock else 'order'}_{secrets.token_hex(8)}"

    payment = Payment(
        user_id=user.id,
        business_id=campaign.business_id,
        campaign_id=campaign.id,
        amount=amount,
        currency="INR",
        status="created",
        provider="mock" if is_mock else "razorpay",
        provider_order_id=order_id,
        is_mock=is_mock,
        receipt_number=f"RCPT-{secrets.token_hex(4).upper()}",
        meta_json=json.dumps({"campaign_name": campaign.name}),
    )
    db.add(payment)
    campaign.status = "payment_pending"
    db.commit()
    db.refresh(payment)

    result: dict[str, Any] = {
        "payment_id": str(payment.id),
        "order_id": order_id,
        "amount": amount,
        "currency": "INR",
        "provider": payment.provider,
        "is_mock": is_mock,
        "key_id": settings.razorpay_key_id if not is_mock else None,
        "note": "Mock payment mode — no real charge will occur." if is_mock else None,
    }
    return result


def verify_payment(
    db: Session,
    user: User,
    *,
    payment_id: UUID,
    provider_payment_id: Optional[str] = None,
    provider_signature: Optional[str] = None,
    mock_success: bool = True,
) -> dict[str, Any]:
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise NotFoundError("Payment not found")
    if payment.user_id != user.id and (user.role.name if user.role else "") not in (
        "admin",
        "super_admin",
    ):
        raise NotFoundError("Payment not found")

    campaign = get_campaign(db, user, payment.campaign_id)

    if payment.is_mock:
        if not mock_success:
            payment.status = "failed"
            db.commit()
            return {"status": "failed", "is_mock": True}
        payment.status = "paid"
        payment.provider_payment_id = provider_payment_id or f"mock_pay_{secrets.token_hex(6)}"
        payment.provider_signature = provider_signature or "mock_signature"
    else:
        if not provider_payment_id or not provider_signature or not payment.provider_order_id:
            raise ValidationAppError("Missing Razorpay verification fields")
        payload = f"{payment.provider_order_id}|{provider_payment_id}"
        expected = hmac.new(
            (settings.razorpay_key_secret or "").encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, provider_signature):
            payment.status = "failed"
            db.commit()
            raise ValidationAppError("Payment signature verification failed")
        payment.status = "paid"
        payment.provider_payment_id = provider_payment_id
        payment.provider_signature = provider_signature

    db.add(
        Transaction(
            payment_id=payment.id,
            business_id=payment.business_id,
            amount=payment.amount,
            currency=payment.currency,
            type="campaign_payment",
            status="success",
            description=f"Payment for campaign {campaign.name}",
            external_id=payment.provider_payment_id,
        )
    )
    invoice_number = f"INV-{utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    db.add(
        Invoice(
            payment_id=payment.id,
            business_id=payment.business_id,
            invoice_number=invoice_number,
            amount=campaign.budget.total_budget if campaign.budget else payment.amount,
            tax_amount=campaign.budget.tax_amount if campaign.budget else 0,
            total_amount=payment.amount,
            status="issued",
        )
    )
    campaign.status = "scheduled" if campaign.schedule else "approved"
    db.add(
        Notification(
            user_id=user.id,
            title="Payment successful",
            message=f"Payment of ₹{payment.amount:.0f} for '{campaign.name}' was successful"
            + (" (mock)" if payment.is_mock else "")
            + ".",
            type="payment_successful",
            entity_type="campaign",
            entity_id=str(campaign.id),
        )
    )
    db.commit()

    return {
        "status": "paid",
        "payment_id": str(payment.id),
        "campaign_id": str(campaign.id),
        "campaign_status": campaign.status,
        "is_mock": payment.is_mock,
        "invoice_number": invoice_number,
    }


def list_payments(db: Session, user: User, business_id: Optional[UUID] = None) -> list[dict[str, Any]]:
    from app.services.business_service import list_businesses_for_user

    query = db.query(Payment)
    role = user.role.name if user.role else ""
    if role not in ("admin", "super_admin"):
        if business_id:
            from app.services.business_service import user_can_access_business

            user_can_access_business(db, user, business_id)
            query = query.filter(Payment.business_id == business_id)
        else:
            ids = [b.id for b in list_businesses_for_user(db, user)]
            query = query.filter(Payment.business_id.in_(ids)) if ids else query.filter(False)
    elif business_id:
        query = query.filter(Payment.business_id == business_id)

    payments = query.order_by(Payment.created_at.desc()).all()
    return [
        {
            "id": str(p.id),
            "campaign_id": str(p.campaign_id),
            "amount": p.amount,
            "currency": p.currency,
            "status": p.status,
            "provider": p.provider,
            "is_mock": p.is_mock,
            "provider_order_id": p.provider_order_id,
            "created_at": p.created_at.isoformat(),
        }
        for p in payments
    ]
