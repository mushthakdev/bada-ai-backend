from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.services import channel_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


class ConnectRequest(BaseModel):
    business_id: UUID
    channel_code: str
    account_name: Optional[str] = None


class DisconnectRequest(BaseModel):
    business_id: UUID
    channel_code: str


@router.get("")
def list_integrations(
    business_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Channel Integrations page data — never includes access tokens."""
    return success_response(channel_service.list_integrations(db, user, business_id))


@router.post("/connect")
def connect(
    payload: ConnectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = channel_service.connect_channel(
        db,
        user,
        business_id=payload.business_id,
        channel_code=payload.channel_code,
        account_name=payload.account_name,
    )
    return success_response(
        result,
        message=(
            "Channel connected in demo/partner mode. "
            "Live OAuth requires configured provider credentials."
        ),
    )


@router.post("/disconnect")
def disconnect(
    payload: DisconnectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        channel_service.disconnect_channel(
            db, user, business_id=payload.business_id, channel_code=payload.channel_code
        ),
        message="Channel disconnected",
    )
