from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import success_response
from app.models.user import User
from app.schemas.business import OnboardingPayload
from app.services import business_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("")
def submit_onboarding(
    payload: OnboardingPayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    business = business_service.process_onboarding(db, user, payload)
    return success_response(
        {
            "business": business_service.to_business_out(business).model_dump(),
            "onboarding_completed": business.onboarding_completed,
            "step": business.onboarding_step,
        },
        message="Onboarding saved",
    )


@router.get("/status")
def onboarding_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    businesses = business_service.list_businesses_for_user(db, user)
    business = businesses[0] if businesses else None
    return success_response(
        {
            "user_onboarding_completed": user.onboarding_completed,
            "business": business_service.to_business_out(business).model_dump() if business else None,
        }
    )
