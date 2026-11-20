from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.services import qr_service

router = APIRouter(prefix="/qr", tags=["qr"])


class CreateQRRequest(BaseModel):
    campaign_id: UUID
    destination_type: str
    destination_value: str


@router.post("")
def create_qr(
    payload: CreateQRRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        qr_service.create_campaign_qr(
            db,
            user,
            payload.campaign_id,
            destination_type=payload.destination_type,
            destination_value=payload.destination_value,
        )
    )


@router.get("/{code}/redirect")
def redirect_qr(code: str, request: Request, db: Session = Depends(get_db)):
    result = qr_service.resolve_scan(
        db,
        code,
        user_agent=request.headers.get("user-agent"),
        referrer=request.headers.get("referer"),
        ip_address=request.client.host if request.client else None,
    )
    return RedirectResponse(url=result["redirect_url"], status_code=302)


@router.get("/{code}/image")
def qr_image(code: str, db: Session = Depends(get_db)):
    import qrcode

    from app.core.exceptions import NotFoundError
    from app.models.qr import QRCode

    qr = db.query(QRCode).filter(QRCode.code == code).first()
    if not qr:
        raise NotFoundError("QR code not found")

    img = qrcode.make(f"/t/{code}")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png")
