from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.exceptions import AppException, UnauthorizedError, ValidationAppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    safe_decode_token,
    verify_password,
)
from app.models.base import utcnow
from app.models.notification import Notification
from app.models.user import RefreshToken, Role, User
from app.schemas.auth import AuthResponse, TokenResponse, UserOut

settings = get_settings()

# In-memory OTP store for development (replace with Redis in production)
_otp_store: dict[str, tuple[str, datetime]] = {}
_reset_tokens: dict[str, tuple[str, datetime]] = {}


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        role=user.role.name if user.role else "advertiser",
        is_verified=user.is_verified,
        onboarding_completed=user.onboarding_completed,
        preferred_language=user.preferred_language,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    role_name = user.role.name if user.role else "advertiser"
    access = create_access_token(
        str(user.id),
        claims={"role": role_name, "email": user.email},
    )
    refresh, jti, expires = create_refresh_token(str(user.id))
    token_hash = hashlib.sha256(refresh.encode()).hexdigest()
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            token_hash=token_hash,
            expires_at=expires.replace(tzinfo=None) if expires.tzinfo else expires,
        )
    )
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def get_role_by_name(db: Session, name: str) -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if not role:
        raise AppException(f"Role '{name}' is not configured", status_code=500, code="role_missing")
    return role


def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    phone: Optional[str],
    role_name: str,
) -> AuthResponse:
    existing = db.query(User).filter(User.email == email.lower()).first()
    if existing:
        raise ValidationAppError("An account with this email already exists")

    if phone:
        phone_exists = db.query(User).filter(User.phone == phone).first()
        if phone_exists:
            raise ValidationAppError("An account with this phone number already exists")

    role = get_role_by_name(db, role_name)
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        phone=phone,
        role_id=role.id,
        is_verified=False,
        onboarding_completed=False,
    )
    db.add(user)
    db.flush()
    db.add(
        Notification(
            user_id=user.id,
            title="Welcome to Bada",
            message="Complete your business onboarding to create your first TV ad campaign.",
            type="welcome",
        )
    )
    db.commit()
    db.refresh(user)
    user = db.query(User).options(joinedload(User.role)).filter(User.id == user.id).one()
    tokens = _issue_tokens(db, user)
    return AuthResponse(user=_user_out(user), tokens=tokens)


def login_user(db: Session, *, email: str, password: str) -> AuthResponse:
    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.email == email.lower(), User.is_deleted.is_(False))
        .first()
    )
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedError("Account is suspended")

    user.last_login_at = utcnow()
    db.commit()
    tokens = _issue_tokens(db, user)
    return AuthResponse(user=_user_out(user), tokens=tokens)


def refresh_tokens(db: Session, refresh_token: str) -> TokenResponse:
    payload = safe_decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token")

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not jti or not user_id:
        raise UnauthorizedError("Invalid refresh token")

    stored = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if not stored or not stored.is_active:
        raise UnauthorizedError("Refresh token revoked or expired")

    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    if stored.token_hash != token_hash:
        raise UnauthorizedError("Refresh token mismatch")

    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.id == UUID(user_id), User.is_deleted.is_(False))
        .first()
    )
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    # Rotate refresh token
    stored.revoked_at = utcnow()
    new_tokens = _issue_tokens(db, user)
    stored.replaced_by = safe_decode_token(new_tokens.refresh_token).get("jti") if safe_decode_token(new_tokens.refresh_token) else None
    db.commit()
    return new_tokens


def logout_user(db: Session, refresh_token: Optional[str]) -> None:
    if not refresh_token:
        return
    payload = safe_decode_token(refresh_token)
    if not payload:
        return
    jti = payload.get("jti")
    if not jti:
        return
    stored = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if stored and stored.revoked_at is None:
        stored.revoked_at = utcnow()
        db.commit()


def request_password_reset(db: Session, email: str) -> dict:
    user = db.query(User).filter(User.email == email.lower()).first()
    # Always return success to avoid email enumeration
    if user:
        token = secrets.token_urlsafe(32)
        _reset_tokens[token] = (str(user.id), utcnow() + timedelta(hours=1))
        return {
            "message": "If the email exists, a reset link has been sent.",
            "dev_reset_token": token if settings.debug else None,
        }
    return {"message": "If the email exists, a reset link has been sent.", "dev_reset_token": None}


def reset_password(db: Session, token: str, new_password: str) -> None:
    entry = _reset_tokens.get(token)
    if not entry:
        raise ValidationAppError("Invalid or expired reset token")
    user_id, expires = entry
    if expires < utcnow():
        _reset_tokens.pop(token, None)
        raise ValidationAppError("Invalid or expired reset token")
    user = db.query(User).filter(User.id == UUID(user_id)).first()
    if not user:
        raise ValidationAppError("Invalid or expired reset token")
    user.password_hash = hash_password(new_password)
    _reset_tokens.pop(token, None)
    db.commit()


def request_otp(phone: str) -> dict:
    otp = "123456" if settings.debug else f"{secrets.randbelow(1000000):06d}"
    _otp_store[phone] = (otp, utcnow() + timedelta(minutes=10))
    return {
        "message": "OTP sent",
        "dev_otp": otp if settings.debug else None,
        "expires_in": 600,
    }


def verify_otp(db: Session, phone: str, otp: str) -> AuthResponse:
    entry = _otp_store.get(phone)
    if not entry or entry[0] != otp or entry[1] < utcnow():
        raise ValidationAppError("Invalid or expired OTP")
    _otp_store.pop(phone, None)

    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.phone == phone, User.is_deleted.is_(False))
        .first()
    )
    if not user:
        role = get_role_by_name(db, "advertiser")
        user = User(
            email=f"{phone}@phone.bada.local",
            phone=phone,
            full_name=f"User {phone[-4:]}",
            role_id=role.id,
            is_verified=True,
            phone_verified_at=utcnow(),
        )
        db.add(user)
        db.commit()
        user = db.query(User).options(joinedload(User.role)).filter(User.id == user.id).one()
    else:
        user.phone_verified_at = utcnow()
        user.is_verified = True
        db.commit()

    tokens = _issue_tokens(db, user)
    return AuthResponse(user=_user_out(user), tokens=tokens)
