from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Bada AI API"
    app_env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:3000"

    database_url: str = "sqlite:///./bada.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    use_celery: bool = False

    secret_key: str = "bada-dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    algorithm: str = "HS256"

    s3_endpoint_url: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: str = "bada-media"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    local_media_dir: str = "./media"

    gemini_api_key: Optional[str] = None
    gemini_use_adc: bool = False
    gemini_model: str = "gemini-2.0-flash"
    google_cloud_project: Optional[str] = None
    google_cloud_location: str = "us-central1"
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    razorpay_webhook_secret: Optional[str] = None

    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    email_from: str = "noreply@bada.ai"

    frontend_url: str = "http://localhost:3000"
    media_margin_percent: float = 20.0
    minimum_daily_budget: float = 1000.0
    default_cpm: float = 250.0
    seed_demo_data: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def gemini_adc_ready(self) -> bool:
        return bool(self.gemini_use_adc and self.google_cloud_project)

    @property
    def ai_mock_mode(self) -> bool:
        return not (self.gemini_api_key or self.gemini_adc_ready)

    @property
    def payment_mock_mode(self) -> bool:
        return not (self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def storage_local_mode(self) -> bool:
        return not (self.s3_endpoint_url and self.s3_access_key and self.s3_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
