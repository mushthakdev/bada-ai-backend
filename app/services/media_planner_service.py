from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationAppError
from app.integrations.advertising.registry import get_provider, list_providers
from app.models.user import User
from app.services.business_service import user_can_access_business
from app.services.channel_service import ensure_channel_catalog


# Heuristic weights by objective → channel affinity (not live inventory)
OBJECTIVE_WEIGHTS: dict[str, dict[str, float]] = {
    "brand_awareness": {"youtube": 0.25, "ctv": 0.25, "meta": 0.2, "ott": 0.15, "local_screens": 0.1, "outdoor": 0.05},
    "reach": {"ctv": 0.25, "youtube": 0.2, "meta": 0.2, "publishers": 0.15, "local_screens": 0.1, "outdoor": 0.1},
    "video_views": {"youtube": 0.4, "ctv": 0.25, "ott": 0.2, "meta": 0.15},
    "website_traffic": {"meta": 0.35, "youtube": 0.25, "publishers": 0.25, "local_screens": 0.15},
    "whatsapp_leads": {"meta": 0.45, "youtube": 0.2, "publishers": 0.2, "local_screens": 0.15},
    "phone_calls": {"meta": 0.35, "local_screens": 0.3, "publishers": 0.2, "youtube": 0.15},
    "store_visits": {"local_screens": 0.3, "ctv": 0.25, "meta": 0.2, "outdoor": 0.15, "youtube": 0.1},
    "sales": {"meta": 0.3, "youtube": 0.25, "local_screens": 0.2, "ctv": 0.15, "publishers": 0.1},
    "lead_generation": {"meta": 0.4, "youtube": 0.25, "publishers": 0.2, "local_screens": 0.15},
    "increase_store_visits": {"local_screens": 0.3, "ctv": 0.25, "meta": 0.2, "outdoor": 0.15, "youtube": 0.1},
    "promote_sale": {"meta": 0.3, "youtube": 0.25, "local_screens": 0.2, "ctv": 0.15, "publishers": 0.1},
}


REASON_TEMPLATES = {
    "youtube": "Strong for video storytelling and measurable views in your target language markets.",
    "meta": "Efficient for local intent, WhatsApp/lead actions, and social creative formats.",
    "ctv": "Premium lean-back attention for brand and neighbourhood awareness.",
    "ott": "Streaming reach via partner inventory — subject to partner availability (not self-serve APIs).",
    "publishers": "Regional news/content context for credibility and local discovery.",
    "local_screens": "High relevance near store footfall; good for QR and visit prompts.",
    "outdoor": "Broad local awareness; estimates only until inventory partners confirm.",
}


def recommend_media_plan(
    db: Session,
    user: User,
    *,
    business_id: Optional[UUID],
    business_type: str,
    product: str,
    objective: str,
    budget: float,
    location: str,
    audience: Optional[str] = None,
    duration_days: int = 14,
    selected_channels: Optional[list[str]] = None,
) -> dict[str, Any]:
    if business_id:
        user_can_access_business(db, user, business_id)
    if budget < 1000:
        raise ValidationAppError("Media plan budget must be at least ₹1,000")

    ensure_channel_catalog(db)
    weights = dict(OBJECTIVE_WEIGHTS.get(objective, OBJECTIVE_WEIGHTS["brand_awareness"]))

    if selected_channels:
        weights = {k: v for k, v in weights.items() if k in selected_channels}
        if not weights:
            weights = {code: 1.0 for code in selected_channels}

    # Drop channels that don't support the objective
    filtered: dict[str, float] = {}
    for code, weight in weights.items():
        provider = get_provider(code)
        if not provider:
            continue
        if not provider.supports_objective(objective) and objective not in (
            "increase_store_visits",
            "promote_sale",
            "phone_calls",
        ):
            # soft-allow mapped objectives for jewellery-style goals
            if code not in provider.capabilities().objectives and objective not in OBJECTIVE_WEIGHTS:
                continue
        filtered[code] = weight

    if not filtered:
        filtered = {"meta": 0.4, "youtube": 0.3, "local_screens": 0.3}

    total_w = sum(filtered.values())
    allocations = []
    remaining = budget
    codes = list(filtered.keys())
    for i, code in enumerate(codes):
        provider = get_provider(code)
        share = filtered[code] / total_w
        amount = round(budget * share, 2) if i < len(codes) - 1 else round(remaining, 2)
        remaining -= amount if i < len(codes) - 1 else 0
        caps = provider.capabilities() if provider else None
        min_budget = caps.min_daily_budget * max(1, duration_days // 7) if caps else 500
        if amount < (caps.min_daily_budget if caps else 500):
            # still include but flag
            pass
        allocations.append(
            {
                "channel_code": code,
                "channel_name": provider.name if provider else code,
                "category": provider.category if provider else "unknown",
                "allocation_percent": round(share * 100, 1),
                "budget": amount,
                "estimated_cpm": caps.estimated_cpm if caps else None,
                "estimated_impressions": int((amount / (caps.estimated_cpm or 200)) * 1000)
                if caps and caps.estimated_cpm
                else None,
                "integration_mode": provider.integration_mode.value if provider else "simulated",
                "is_estimate": True,
                "reason": REASON_TEMPLATES.get(code, "Recommended based on objective affinity."),
                "minimum_budget_hint": caps.min_daily_budget if caps else None,
            }
        )

    return {
        "business_type": business_type,
        "product": product,
        "objective": objective,
        "location": location,
        "audience": audience,
        "budget": budget,
        "duration_days": duration_days,
        "allocations": allocations,
        "strategy_summary": (
            f"For a {business_type} promoting {product} in {location} with objective "
            f"'{objective.replace('_', ' ')}', prioritize a mix of video, social, and local "
            f"presence over {duration_days} days. Budgets and impressions are estimates — "
            f"not live inventory guarantees."
        ),
        "data_quality": {
            "is_estimate": True,
            "label": "Estimated media plan — not live inventory or guaranteed pricing",
        },
        "available_providers": [
            {
                "code": p.code,
                "name": p.name,
                "mode": p.integration_mode.value,
                "supports_objective": p.supports_objective(objective)
                or objective in OBJECTIVE_WEIGHTS,
            }
            for p in list_providers()
        ],
    }


def equal_allocation(channel_codes: list[str], budget: float) -> list[dict[str, Any]]:
    if not channel_codes:
        raise ValidationAppError("Select at least one channel")
    each = round(budget / len(channel_codes), 2)
    result = []
    remaining = budget
    for i, code in enumerate(channel_codes):
        provider = get_provider(code)
        amount = each if i < len(channel_codes) - 1 else round(remaining, 2)
        remaining -= amount if i < len(channel_codes) - 1 else 0
        result.append(
            {
                "channel_code": code,
                "channel_name": provider.name if provider else code,
                "allocation_percent": round((amount / budget) * 100, 1),
                "budget": amount,
                "is_estimate": True,
            }
        )
    return result
