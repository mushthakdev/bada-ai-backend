from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.response import success_response
from app.models.base import utcnow
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return success_response(
        [
            {
                "id": str(n.id),
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "is_read": n.is_read,
                "entity_type": n.entity_type,
                "entity_id": n.entity_id,
                "created_at": n.created_at.isoformat(),
            }
            for n in items
        ]
    )


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user.id)
        .first()
    )
    if not n:
        raise NotFoundError("Notification not found")
    n.is_read = True
    n.read_at = utcnow()
    db.commit()
    return success_response(message="Marked as read")


@router.post("/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read.is_(False)
    ).update({"is_read": True, "read_at": utcnow()})
    db.commit()
    return success_response(message="All notifications marked as read")
