from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.inventory import PincodeInventory
from app.models.settings import SystemSetting


@dataclass
class PricingBreakdown:
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


def _get_setting(db: Session, key: str, default: str) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return row.value if row else default


def get_pricing_config(db: Session) -> dict[str, float]:
    settings = get_settings()
    return {
        "minimum_daily_budget": float(
            _get_setting(db, "minimum_daily_budget", str(settings.minimum_daily_budget))
        ),
        "media_margin_percent": float(
            _get_setting(db, "media_margin_percent", str(settings.media_margin_percent))
        ),
        "default_cpm": float(_get_setting(db, "default_cpm", str(settings.default_cpm))),
        "tax_percent": float(_get_setting(db, "tax_percent", "0")),
    }


def estimate_cpm_for_pincodes(db: Session, pincodes: list[str]) -> tuple[float, bool]:
    if not pincodes:
        config = get_pricing_config(db)
        return config["default_cpm"], True

    rows = db.query(PincodeInventory).filter(PincodeInventory.pincode.in_(pincodes)).all()
    if not rows:
        config = get_pricing_config(db)
        return config["default_cpm"], True

    avg = sum(r.avg_cpm for r in rows) / len(rows)
    is_estimate = any(r.is_estimate for r in rows)
    return round(avg, 2), is_estimate


def calculate_budget(
    db: Session,
    *,
    daily_budget: float,
    total_budget: float,
    pincodes: Optional[list[str]] = None,
) -> PricingBreakdown:
    config = get_pricing_config(db)
    if daily_budget < config["minimum_daily_budget"]:
        raise ValueError(
            f"Daily budget must be at least ₹{config['minimum_daily_budget']:.0f}"
        )
    if total_budget < daily_budget:
        raise ValueError("Total budget must be greater than or equal to daily budget")

    cpm, is_estimate = estimate_cpm_for_pincodes(db, pincodes or [])
    margin = config["media_margin_percent"] / 100.0
    tax_rate = config["tax_percent"] / 100.0

    # Media spend is the advertiser media allocation; platform fee is Bada margin on media.
    media_spend = round(total_budget / (1 + margin), 2)
    platform_fee = round(total_budget - media_spend, 2)
    tax_amount = round(total_budget * tax_rate, 2)
    total_payable = round(total_budget + tax_amount, 2)

    estimated_impressions = int((media_spend / cpm) * 1000) if cpm > 0 else 0
    estimated_reach = int(estimated_impressions * 0.65)

    return PricingBreakdown(
        daily_budget=daily_budget,
        total_budget=total_budget,
        estimated_cpm=cpm,
        estimated_impressions=estimated_impressions,
        estimated_reach=estimated_reach,
        media_spend=media_spend,
        platform_fee=platform_fee,
        tax_amount=tax_amount,
        total_payable=total_payable,
        is_estimate=is_estimate,
    )
