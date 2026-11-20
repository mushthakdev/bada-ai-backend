from __future__ import annotations

import hashlib
import secrets
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.models.base import utcnow
from app.models.qr import QRCode, QRScan
from app.models.user import User
from app.services.campaign_service import get_campaign
from app.services.lead_service import create_lead

settings = get_settings()


def create_campaign_qr(
    db: Session,
    user: User,
    campaign_id: UUID,
    *,
    destination_type: str,
    destination_value: str,
) -> dict[str, Any]:
    campaign = get_campaign(db, user, campaign_id)
    code = secrets.token_urlsafe(10)
    qr = QRCode(
        campaign_id=campaign.id,
        business_id=campaign.business_id,
        code=code,
        destination_type=destination_type,
        destination_value=destination_value,
        image_url=f"/api/v1/qr/{code}/image",
        is_active=True,
    )
    db.add(qr)
    db.commit()
    db.refresh(qr)
    return {
        "id": str(qr.id),
        "code": qr.code,
        "tracking_url": f"{settings.frontend_url}/t/{qr.code}",
        "api_redirect_url": f"/api/v1/qr/{qr.code}/redirect",
        "destination_type": qr.destination_type,
        "destination_value": qr.destination_value,
        "image_url": qr.image_url,
    }


def resolve_scan(
    db: Session,
    code: str,
    *,
    user_agent: Optional[str] = None,
    referrer: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> dict[str, Any]:
    qr = db.query(QRCode).filter(QRCode.code == code, QRCode.is_active.is_(True)).first()
    if not qr:
        raise NotFoundError("QR code not found")

    device = "mobile" if user_agent and any(x in user_agent.lower() for x in ("iphone", "android", "mobile")) else "desktop"
    browser = None
    if user_agent:
        lower = user_agent.lower()
        if "chrome" in lower:
            browser = "chrome"
        elif "safari" in lower:
            browser = "safari"
        elif "firefox" in lower:
            browser = "firefox"

    ip_hash = hashlib.sha256((ip_address or "unknown").encode()).hexdigest()[:32]
    db.add(
        QRScan(
            qr_code_id=qr.id,
            campaign_id=qr.campaign_id,
            scanned_at=utcnow(),
            device_type=device,
            browser=browser,
            referrer=referrer,
            ip_hash=ip_hash,
            user_agent=user_agent,
        )
    )

    # Attribute a lightweight lead on QR scan if destination is lead-oriented
    if qr.destination_type in ("whatsapp", "phone", "landing_page"):
        from app.models.business import Business

        business = db.query(Business).filter(Business.id == qr.business_id).first()
        create_lead(
            db,
            business_id=qr.business_id,
            campaign_id=qr.campaign_id,
            name=None,
            phone=None,
            email=None,
            inquiry=f"QR scan → {qr.destination_type}",
            source="qr",
            notify_user_id=business.owner_id if business else None,
        )
    else:
        db.commit()

    destination = qr.destination_value
    if qr.destination_type == "whatsapp":
        phone = qr.destination_value.lstrip("+").replace(" ", "")
        destination = f"https://wa.me/{phone}"
    elif qr.destination_type == "phone":
        destination = f"tel:{qr.destination_value}"

    return {
        "redirect_url": destination,
        "campaign_id": str(qr.campaign_id),
        "destination_type": qr.destination_type,
    }
