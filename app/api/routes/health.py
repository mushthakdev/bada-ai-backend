from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    settings = get_settings()
    return {
        "success": True,
        "message": "OK",
        "data": {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "ai_mode": "mock" if settings.ai_mock_mode else "live",
            "payment_mode": "mock" if settings.payment_mock_mode else "razorpay",
            "storage_mode": "local" if settings.storage_local_mode else "s3",
        },
    }
