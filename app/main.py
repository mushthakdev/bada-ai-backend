from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.exceptions import AppException, app_exception_handler, http_exception_handler
from app.services.media_service import _ensure_media_dir

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
    description="Bada AI — omnichannel advertising marketplace API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

app.include_router(api_router)

media_path = _ensure_media_dir()
app.mount("/media", StaticFiles(directory=str(media_path)), name="media")


@app.on_event("startup")
def on_startup() -> None:
    # Import models so metadata is registered
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    from app.core.schema_patch import ensure_sqlite_schema

    ensure_sqlite_schema(engine)
    db = SessionLocal()
    try:
        from app.services.channel_service import ensure_channel_catalog
        from app.scripts.seed import seed_if_empty, seed_omnichannel_demo

        ensure_channel_catalog(db)
        if settings.seed_demo_data:
            seed_if_empty(db)
            seed_omnichannel_demo(db)
    finally:
        db.close()


@app.get("/")
def root() -> dict:
    return {
        "message": f"Welcome to {settings.app_name}",
        "docs": "/docs",
        "health": "/api/v1/health",
        "ai_mode": "mock" if settings.ai_mock_mode else "live",
        "payment_mode": "mock" if settings.payment_mock_mode else "razorpay",
    }
