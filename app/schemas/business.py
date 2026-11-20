from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class BusinessCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = Field(default=None, max_length=10)
    country: str = "India"


class BrandUpdate(BaseModel):
    logo_url: Optional[str] = None
    brand_tagline: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None


class ObjectiveUpdate(BaseModel):
    advertising_objective: str


class AudienceOnboarding(BaseModel):
    target_city: Optional[str] = None
    target_state: Optional[str] = None
    target_pincodes: list[str] = Field(default_factory=list)
    demographics: Optional[str] = None
    interests: Optional[str] = None
    languages: list[str] = Field(default_factory=lambda: ["en"])


class BudgetOnboarding(BaseModel):
    daily_budget: float = Field(ge=1000)
    total_budget: float = Field(ge=1000)
    duration_days: int = Field(ge=1, le=365)


class OnboardingPayload(BaseModel):
    business: BusinessCreate
    brand: Optional[BrandUpdate] = None
    advertising_objective: Optional[str] = None
    audience: Optional[AudienceOnboarding] = None
    budget: Optional[BudgetOnboarding] = None
    step: int = Field(default=1, ge=1, le=5)


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    logo_url: Optional[str] = None
    brand_tagline: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None
    advertising_objective: Optional[str] = None
    target_languages: Optional[str] = None


class BusinessOut(BaseModel):
    id: UUID
    name: str
    category: str
    description: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: str
    logo_url: Optional[str] = None
    brand_tagline: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None
    advertising_objective: Optional[str] = None
    target_languages: Optional[str] = None
    onboarding_step: int
    onboarding_completed: bool
    is_verified: bool
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
