from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.services import media_service

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    business_id: Optional[UUID] = Form(default=None),
    category: Optional[str] = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = media_service.save_upload(
        db, user, file, business_id=business_id, category=category
    )
    return success_response(
        {
            "id": str(record.id),
            "filename": record.filename,
            "original_filename": record.original_filename,
            "content_type": record.content_type,
            "file_size": record.file_size,
            "public_url": record.public_url,
            "media_type": record.media_type,
            "category": record.category,
            "storage_provider": record.storage_provider,
        },
        message="Upload successful",
    )


@router.get("")
def list_media(
    business_id: Optional[UUID] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = media_service.list_media(db, user, business_id)
    return success_response(
        [
            {
                "id": str(m.id),
                "filename": m.filename,
                "original_filename": m.original_filename,
                "content_type": m.content_type,
                "file_size": m.file_size,
                "public_url": m.public_url,
                "media_type": m.media_type,
                "category": m.category,
            }
            for m in items
        ]
    )
