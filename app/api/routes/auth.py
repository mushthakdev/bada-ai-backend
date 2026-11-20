from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    OTPRequest,
    OTPVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    result = auth_service.register_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone=payload.phone,
        role_name=payload.role,
    )
    return success_response(result.model_dump(), message="Registration successful")


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    result = auth_service.login_user(db, email=payload.email, password=payload.password)
    return success_response(result.model_dump(), message="Login successful")


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    tokens = auth_service.refresh_tokens(db, payload.refresh_token)
    return success_response(tokens.model_dump())


@router.post("/logout")
def logout(payload: RefreshRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    auth_service.logout_user(db, payload.refresh_token)
    return success_response(message="Logged out")


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).options(joinedload(User.role)).filter(User.id == user.id).one()
    return success_response(
        UserOut(
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
        ).model_dump()
    )


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    result = auth_service.request_password_reset(db, payload.email)
    return success_response(result)


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    auth_service.reset_password(db, payload.token, payload.new_password)
    return success_response(message="Password updated")


@router.post("/otp/request")
def otp_request(payload: OTPRequest):
    return success_response(auth_service.request_otp(payload.phone))


@router.post("/otp/verify")
def otp_verify(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    result = auth_service.verify_otp(db, payload.phone, payload.otp)
    return success_response(result.model_dump())
