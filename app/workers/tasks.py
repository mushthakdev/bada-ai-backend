from __future__ import annotations

from uuid import UUID

from app.core.database import SessionLocal
from app.workers.celery_app import celery_app


@celery_app.task(name="ai.generate_creative", bind=True, max_retries=3)
def generate_creative_task(self, user_id: str, campaign_id: str, duration: int = 30) -> dict:
    from app.models.user import User
    from app.services import ai_service

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        if not user:
            return {"status": "failed", "error": "user_not_found"}
        result = ai_service.generate_creative(
            db, user, campaign_id=UUID(campaign_id), duration=duration
        )
        return {"status": "completed", "result": result}
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=10) from exc
    finally:
        db.close()


@celery_app.task(name="campaign.activate")
def activate_campaign_task(campaign_id: str) -> dict:
    from app.models.base import utcnow
    from app.models.campaign import Campaign

    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == UUID(campaign_id)).first()
        if not campaign:
            return {"status": "failed", "error": "not_found"}
        campaign.status = "active"
        if campaign.schedule:
            campaign.schedule.activated_at = utcnow()
        # Delivery remains simulated until a real publisher integration is connected.
        campaign.is_simulated_delivery = True
        db.commit()
        return {
            "status": "active",
            "is_simulated_delivery": True,
            "note": "Campaign marked active with simulated delivery.",
        }
    finally:
        db.close()
