from __future__ import annotations

import mimetypes
import secrets
import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError
from app.models.media import MediaFile
from app.models.user import User
from app.services.business_service import user_can_access_business

settings = get_settings()

ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/svg+xml",
    "video/mp4",
    "video/webm",
    "audio/mpeg",
    "audio/wav",
}
MAX_SIZE = 50 * 1024 * 1024  # 50MB


def _ensure_media_dir() -> Path:
    path = Path(settings.local_media_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "uploads").mkdir(exist_ok=True)
    (path / "mock" / "images").mkdir(parents=True, exist_ok=True)
    return path


def save_upload(
    db: Session,
    user: User,
    file: UploadFile,
    *,
    business_id: Optional[UUID] = None,
    category: Optional[str] = None,
) -> MediaFile:
    if business_id:
        user_can_access_business(db, user, business_id)

    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        raise ValidationAppError(f"Unsupported file type: {content_type}")

    data = file.file.read()
    if len(data) > MAX_SIZE:
        raise ValidationAppError("File exceeds 50MB limit")

    media_dir = _ensure_media_dir()
    ext = Path(file.filename or "file").suffix or ".bin"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = media_dir / "uploads" / stored_name
    dest.write_bytes(data)

    media_type = "image" if content_type.startswith("image/") else "video" if content_type.startswith("video/") else "audio"
    public_url = f"/media/uploads/{stored_name}"

    record = MediaFile(
        business_id=business_id,
        uploaded_by=user.id,
        filename=stored_name,
        original_filename=file.filename or stored_name,
        content_type=content_type,
        file_size=len(data),
        storage_provider="local",
        storage_path=str(dest),
        public_url=public_url,
        media_type=media_type,
        category=category,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_media(
    db: Session,
    user: User,
    business_id: Optional[UUID] = None,
) -> list[MediaFile]:
    query = db.query(MediaFile).filter(MediaFile.is_deleted.is_(False))
    if business_id:
        user_can_access_business(db, user, business_id)
        query = query.filter(MediaFile.business_id == business_id)
    else:
        query = query.filter(MediaFile.uploaded_by == user.id)
    return query.order_by(MediaFile.created_at.desc()).all()
