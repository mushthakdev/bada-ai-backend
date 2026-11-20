from __future__ import annotations

import uuid
from typing import Callable, Optional

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import safe_decode_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Missing or invalid authorization header")

    payload = safe_decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired access token")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token subject")

    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise UnauthorizedError("Invalid token subject") from exc

    user = db.query(User).filter(User.id == uid, User.is_deleted.is_(False)).first()
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not credentials:
        return None
    try:
        return get_current_user(credentials, db)
    except UnauthorizedError:
        return None


def require_roles(*roles: str) -> Callable:
    def checker(user: User = Depends(get_current_user)) -> User:
        role_name = user.role.name if user.role else None
        if role_name not in roles:
            raise ForbiddenError("Insufficient permissions")
        return user

    return checker


def get_client_ip(x_forwarded_for: Optional[str] = Header(default=None)) -> Optional[str]:
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return None
