from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CampaignLocationIn(BaseModel):
    pincode: str = Field(min_length=6, max_length=6)
    city: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None


class CampaignAudienceIn(BaseModel):
    demographics: Optional[str] = None
    interests: Optional[str] = None
    languages: list[str] = Field(default_factory=lambda: ["en"])
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    gender: Optional[str] = None


class CampaignBudgetIn(BaseModel):
    daily_budget: float = Field(ge=1000)
    total_budget: float = Field(ge=1000)
    duration_days: Optional[int] = None


class CampaignScheduleIn(BaseModel):
    start_date: date
    end_date: date
    preferred_slots: Optional[str] = None
    prime_time: bool = False
    daily_impression_cap: Optional[int] = None
    frequency_cap: Optional[int] = None


class CampaignCreate(BaseModel):
    business_id: UUID
    name: str = Field(min_length=2, max_length=200)
    objective: str
    description: Optional[str] = None
    language: str = "en"
    video_duration: int = Field(default=30, ge=15, le=60)
    brief_text: Optional[str] = None
    locations: list[CampaignLocationIn] = Field(default_factory=list)
    audience: Optional[CampaignAudienceIn] = None
    budget: Optional[CampaignBudgetIn] = None
    schedule: Optional[CampaignScheduleIn] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    objective: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None
    video_duration: Optional[int] = None
    brief_text: Optional[str] = None
    locations: Optional[list[CampaignLocationIn]] = None
    audience: Optional[CampaignAudienceIn] = None
    budget: Optional[CampaignBudgetIn] = None
    schedule: Optional[CampaignScheduleIn] = None


class BudgetBreakdownOut(BaseModel):
    daily_budget: float
    total_budget: float
    estimated_cpm: float
    estimated_impressions: int
    estimated_reach: int
    media_spend: float
    platform_fee: float
    tax_amount: float
    total_payable: float
    is_estimate: bool
    currency: str = "INR"


class CampaignOut(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    objective: str
    description: Optional[str] = None
    language: str
    status: str
    video_duration: int
    brief_text: Optional[str] = None
    is_simulated_delivery: bool
    created_at: datetime
    budget: Optional[BudgetBreakdownOut] = None
    location_count: int = 0
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    model_config = {"from_attributes": True}


class CampaignStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None
