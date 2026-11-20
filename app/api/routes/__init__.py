from fastapi import APIRouter

from app.api.routes import (
    admin,
    agencies,
    ai,
    analytics,
    auth,
    businesses,
    campaigns,
    health,
    integrations,
    leads,
    locations,
    marketplace,
    media,
    notifications,
    omnichannel,
    onboarding,
    payments,
    qr,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(businesses.router)
api_router.include_router(onboarding.router)
api_router.include_router(campaigns.router)
api_router.include_router(omnichannel.router)
api_router.include_router(marketplace.router)
api_router.include_router(integrations.router)
api_router.include_router(ai.router)
api_router.include_router(analytics.router)
api_router.include_router(payments.router)
api_router.include_router(leads.router)
api_router.include_router(media.router)
api_router.include_router(locations.router)
api_router.include_router(notifications.router)
api_router.include_router(qr.router)
api_router.include_router(agencies.router)
api_router.include_router(admin.router)
