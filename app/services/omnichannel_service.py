from __future__ import annotations

import json
import random
from datetime import date, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.integrations.advertising.registry import get_provider
from app.models.base import utcnow
from app.models.campaign import Campaign, CampaignAudience, CampaignBudget, CampaignLocation, CampaignSchedule
from app.models.channels import CampaignChannel, ChannelMetric
from app.models.user import User
from app.services.business_service import user_can_access_business
from app.services.campaign_service import get_campaign, _serialize_campaign
from app.services.channel_service import ensure_channel_catalog
from app.services.pricing import calculate_budget


def _channel_rows(db: Session, campaign_id: UUID) -> list[CampaignChannel]:
    return (
        db.query(CampaignChannel)
        .filter(CampaignChannel.campaign_id == campaign_id)
        .order_by(CampaignChannel.created_at.asc())
        .all()
    )


def serialize_campaign_channel(row: CampaignChannel) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "channel_code": row.channel_code,
        "channel_name": row.channel_name,
        "status": row.status,
        "allocated_budget": row.allocated_budget,
        "spent": row.spent,
        "provider_campaign_id": row.provider_campaign_id,
        "integration_mode": row.integration_mode,
        "is_simulated": row.is_simulated,
        "last_error": row.last_error,
        "launched_at": row.launched_at.isoformat() if row.launched_at else None,
        "paused_at": row.paused_at.isoformat() if row.paused_at else None,
    }


def create_omnichannel_campaign(
    db: Session,
    user: User,
    *,
    business_id: UUID,
    name: str,
    objective: str,
    brief_text: Optional[str],
    language: str,
    channel_codes: list[str],
    allocations: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    audience: Optional[dict[str, Any]],
    total_budget: float,
    daily_budget: float,
    start_date: date,
    end_date: date,
    media_plan: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    user_can_access_business(db, user, business_id)
    ensure_channel_catalog(db)

    if not channel_codes:
        raise ValidationAppError("Select at least one advertising channel")
    if end_date < start_date:
        raise ValidationAppError("End date must be after start date")

    alloc_map = {a["channel_code"]: float(a["budget"]) for a in allocations}
    for code in channel_codes:
        if code not in alloc_map:
            raise ValidationAppError(f"Missing budget allocation for {code}")
        provider = get_provider(code)
        if not provider:
            raise ValidationAppError(f"Unknown channel: {code}")

    alloc_sum = round(sum(alloc_map[c] for c in channel_codes), 2)
    if abs(alloc_sum - total_budget) > 1.0:
        raise ValidationAppError(
            f"Channel allocations (₹{alloc_sum:.0f}) must match total budget (₹{total_budget:.0f})"
        )

    pincodes = [loc["pincode"] for loc in locations]
    breakdown = calculate_budget(
        db, daily_budget=daily_budget, total_budget=total_budget, pincodes=pincodes
    )

    campaign = Campaign(
        business_id=business_id,
        created_by=user.id,
        name=name,
        objective=objective,
        description=brief_text,
        language=language,
        brief_text=brief_text,
        status="draft",
        is_omnichannel=True,
        is_simulated_delivery=True,
        media_plan_json=json.dumps(media_plan) if media_plan else None,
    )
    db.add(campaign)
    db.flush()

    if audience:
        db.add(
            CampaignAudience(
                campaign_id=campaign.id,
                demographics=audience.get("demographics"),
                interests=audience.get("interests"),
                languages=",".join(audience.get("languages") or [language]),
                age_min=audience.get("age_min"),
                age_max=audience.get("age_max"),
                gender=audience.get("gender"),
            )
        )

    for loc in locations:
        db.add(
            CampaignLocation(
                campaign_id=campaign.id,
                pincode=loc["pincode"],
                city=loc.get("city"),
                state=loc.get("state"),
                district=loc.get("district"),
                is_estimate=True,
            )
        )

    db.add(
        CampaignBudget(
            campaign_id=campaign.id,
            daily_budget=breakdown.daily_budget,
            total_budget=breakdown.total_budget,
            estimated_cpm=breakdown.estimated_cpm,
            estimated_impressions=breakdown.estimated_impressions,
            estimated_reach=breakdown.estimated_reach,
            media_spend=breakdown.media_spend,
            platform_fee=breakdown.platform_fee,
            tax_amount=breakdown.tax_amount,
            total_payable=breakdown.total_payable,
            is_estimate=True,
        )
    )
    db.add(
        CampaignSchedule(
            campaign_id=campaign.id,
            start_date=start_date,
            end_date=end_date,
        )
    )

    targeting = {
        "location": True,
        "city": True,
        "pincode": True,
        "language": language,
        "age": audience.get("age_min") if audience else None,
        "gender": audience.get("gender") if audience else None,
        "interests": audience.get("interests") if audience else None,
    }

    for code in channel_codes:
        provider = get_provider(code)
        assert provider is not None
        filtered = provider.filter_targeting(targeting)
        db.add(
            CampaignChannel(
                campaign_id=campaign.id,
                channel_code=code,
                channel_name=provider.name,
                status="draft",
                allocated_budget=alloc_map[code],
                integration_mode=provider.integration_mode.value,
                is_simulated=True,
                targeting_json=json.dumps(filtered),
            )
        )

    db.commit()
    db.refresh(campaign)
    return get_omnichannel_detail(db, user, campaign.id)


def get_omnichannel_detail(db: Session, user: User, campaign_id: UUID) -> dict[str, Any]:
    campaign = get_campaign(db, user, campaign_id)
    channels = _channel_rows(db, campaign.id)
    base = _serialize_campaign(campaign).model_dump()
    base["is_omnichannel"] = campaign.is_omnichannel
    base["media_plan"] = json.loads(campaign.media_plan_json) if campaign.media_plan_json else None
    base["launch_summary"] = (
        json.loads(campaign.launch_summary_json) if campaign.launch_summary_json else None
    )
    base["channels"] = [serialize_campaign_channel(c) for c in channels]
    base["channel_count"] = len(channels)
    live = sum(1 for c in channels if c.status == "active")
    failed = sum(1 for c in channels if c.status == "failed")
    base["channel_status_summary"] = {
        "total": len(channels),
        "active": live,
        "failed": failed,
        "draft": sum(1 for c in channels if c.status == "draft"),
        "paused": sum(1 for c in channels if c.status == "paused"),
    }
    return base


def update_allocations(
    db: Session,
    user: User,
    campaign_id: UUID,
    allocations: list[dict[str, Any]],
) -> dict[str, Any]:
    campaign = get_campaign(db, user, campaign_id)
    if campaign.status not in ("draft", "ready_for_review", "payment_pending", "approved"):
        raise ValidationAppError("Allocations can only be edited before launch")
    rows = {r.channel_code: r for r in _channel_rows(db, campaign.id)}
    total = 0.0
    for item in allocations:
        code = item["channel_code"]
        if code not in rows:
            raise ValidationAppError(f"Channel {code} is not on this campaign")
        rows[code].allocated_budget = float(item["budget"])
        total += float(item["budget"])
    if campaign.budget:
        campaign.budget.total_budget = round(total, 2)
        campaign.budget.total_payable = round(total + campaign.budget.tax_amount, 2)
    db.commit()
    return get_omnichannel_detail(db, user, campaign_id)


def launch_omnichannel(db: Session, user: User, campaign_id: UUID) -> dict[str, Any]:
    campaign = get_campaign(db, user, campaign_id)
    channels = _channel_rows(db, campaign.id)
    if not channels:
        raise ValidationAppError("Add at least one channel before launch")

    results = []
    for row in channels:
        provider = get_provider(row.channel_code)
        if not provider:
            row.status = "failed"
            row.last_error = "Provider not registered"
            results.append({"channel_code": row.channel_code, "status": "failed", "message": row.last_error})
            continue

        create = provider.create_campaign(
            {
                "objective": campaign.objective,
                "name": campaign.name,
                "budget": row.allocated_budget,
                "targeting": json.loads(row.targeting_json) if row.targeting_json else {},
            }
        )
        if not create.success:
            row.status = "failed"
            row.last_error = create.message
            results.append(
                {
                    "channel_code": row.channel_code,
                    "status": "failed",
                    "message": create.message,
                    "is_simulated": True,
                }
            )
            continue

        row.provider_campaign_id = create.provider_campaign_id
        provider.upload_creative({"format": "auto", "campaign_id": str(campaign.id)})
        submit = provider.submit_campaign(provider_campaign_id=create.provider_campaign_id or "")
        if submit.success:
            row.status = "active"
            row.is_simulated = True
            row.launched_at = utcnow()
            row.last_error = None
            _seed_channel_metrics(db, campaign.id, row)
            results.append(
                {
                    "channel_code": row.channel_code,
                    "status": "active",
                    "message": submit.message,
                    "is_simulated": True,
                    "provider_campaign_id": row.provider_campaign_id,
                }
            )
        else:
            row.status = "failed"
            row.last_error = submit.message
            results.append(
                {
                    "channel_code": row.channel_code,
                    "status": "failed",
                    "message": submit.message,
                    "is_simulated": True,
                }
            )

    active = [r for r in results if r["status"] == "active"]
    failed = [r for r in results if r["status"] == "failed"]
    if active and not failed:
        campaign.status = "active"
        partial = False
    elif active and failed:
        campaign.status = "active"
        partial = True
    else:
        campaign.status = "failed"
        partial = False

    campaign.is_simulated_delivery = True
    campaign.launch_summary_json = json.dumps(
        {
            "partial_launch": partial,
            "results": results,
            "note": (
                "Channel launches are simulated / partner-managed until live provider APIs confirm delivery. "
                "Failed channels are listed individually — the campaign is not marked fully successful if any fail."
            ),
        }
    )
    if campaign.schedule:
        campaign.schedule.activated_at = utcnow()
    db.commit()

    detail = get_omnichannel_detail(db, user, campaign.id)
    detail["launch"] = {
        "partial_launch": partial,
        "results": results,
        "active_count": len(active),
        "failed_count": len(failed),
    }
    return detail


def _seed_channel_metrics(db: Session, campaign_id: UUID, row: CampaignChannel) -> None:
    existing = (
        db.query(ChannelMetric)
        .filter(ChannelMetric.campaign_id == campaign_id, ChannelMetric.channel_code == row.channel_code)
        .count()
    )
    if existing:
        return
    for i in range(7):
        d = date.today() - timedelta(days=6 - i)
        impressions = random.randint(200, 900)
        db.add(
            ChannelMetric(
                campaign_id=campaign_id,
                channel_code=row.channel_code,
                metric_date=str(d),
                impressions=impressions,
                reach=int(impressions * 0.7),
                clicks=random.randint(5, 40),
                video_views=random.randint(50, 400),
                qr_scans=random.randint(0, 8),
                leads=random.randint(0, 6),
                conversions=random.randint(0, 3),
                spend=round(row.allocated_budget / 14 + random.uniform(-50, 50), 2),
                is_simulated=True,
            )
        )


def channel_control(
    db: Session,
    user: User,
    campaign_id: UUID,
    *,
    channel_code: Optional[str],
    action: str,
) -> dict[str, Any]:
    campaign = get_campaign(db, user, campaign_id)
    rows = _channel_rows(db, campaign.id)
    targets = rows if not channel_code else [r for r in rows if r.channel_code == channel_code]
    if not targets:
        raise NotFoundError("Channel not found on campaign")

    for row in targets:
        provider = get_provider(row.channel_code)
        pid = row.provider_campaign_id or f"local_{row.channel_code}"
        if action == "pause":
            if provider:
                provider.pause_campaign(provider_campaign_id=pid)
            row.status = "paused"
            row.paused_at = utcnow()
        elif action == "resume":
            if provider:
                provider.resume_campaign(provider_campaign_id=pid)
            row.status = "active"
            row.paused_at = None
        elif action == "stop":
            if provider:
                provider.stop_campaign(provider_campaign_id=pid)
            row.status = "cancelled"
        else:
            raise ValidationAppError("Unsupported action")

    # Update parent campaign status
    statuses = {r.status for r in _channel_rows(db, campaign.id)}
    if statuses == {"paused"} or (statuses <= {"paused", "cancelled", "failed"} and "active" not in statuses):
        if "paused" in statuses:
            campaign.status = "paused"
    elif "active" in statuses:
        campaign.status = "active"
    db.commit()
    return get_omnichannel_detail(db, user, campaign_id)


def omnichannel_analytics(db: Session, user: User, campaign_id: UUID) -> dict[str, Any]:
    campaign = get_campaign(db, user, campaign_id)
    channels = _channel_rows(db, campaign.id)
    metrics = db.query(ChannelMetric).filter(ChannelMetric.campaign_id == campaign.id).all()

    by_channel: dict[str, dict[str, Any]] = {}
    for row in channels:
        by_channel[row.channel_code] = {
            "channel_code": row.channel_code,
            "channel_name": row.channel_name,
            "budget": row.allocated_budget,
            "status": row.status,
            "is_simulated": row.is_simulated,
            "impressions": 0,
            "reach": 0,
            "clicks": 0,
            "video_views": 0,
            "qr_scans": 0,
            "leads": 0,
            "conversions": 0,
            "spend": 0.0,
        }

    for m in metrics:
        bucket = by_channel.setdefault(
            m.channel_code,
            {
                "channel_code": m.channel_code,
                "channel_name": m.channel_code,
                "budget": 0,
                "status": "unknown",
                "is_simulated": m.is_simulated,
                "impressions": 0,
                "reach": 0,
                "clicks": 0,
                "video_views": 0,
                "qr_scans": 0,
                "leads": 0,
                "conversions": 0,
                "spend": 0.0,
            },
        )
        bucket["impressions"] += m.impressions
        bucket["reach"] += m.reach
        bucket["clicks"] += m.clicks
        bucket["video_views"] += m.video_views
        bucket["qr_scans"] += m.qr_scans
        bucket["leads"] += m.leads
        bucket["conversions"] += m.conversions
        bucket["spend"] += m.spend

    channel_list = list(by_channel.values())
    for c in channel_list:
        c["spend"] = round(c["spend"], 2)
        c["cost_per_lead"] = round(c["spend"] / c["leads"], 2) if c["leads"] else None
        c["cost_per_result"] = c["cost_per_lead"]

    totals = {
        "spend": round(sum(c["spend"] for c in channel_list), 2),
        "impressions": sum(c["impressions"] for c in channel_list),
        "reach": sum(c["reach"] for c in channel_list),
        "clicks": sum(c["clicks"] for c in channel_list),
        "video_views": sum(c["video_views"] for c in channel_list),
        "qr_scans": sum(c["qr_scans"] for c in channel_list),
        "leads": sum(c["leads"] for c in channel_list),
        "conversions": sum(c["conversions"] for c in channel_list),
    }
    totals["cost_per_lead"] = round(totals["spend"] / totals["leads"], 2) if totals["leads"] else None

    # Compatible comparison metrics only
    comparison = [
        {
            "channel_code": c["channel_code"],
            "channel_name": c["channel_name"],
            "impressions": c["impressions"],
            "spend": c["spend"],
            "leads": c["leads"],
            "video_views": c["video_views"],
        }
        for c in channel_list
    ]

    insight = _ai_insight(channel_list, totals)

    return {
        "campaign_id": str(campaign.id),
        "campaign_name": campaign.name,
        "is_omnichannel": campaign.is_omnichannel,
        "totals": totals,
        "channels": channel_list,
        "comparison": comparison,
        "insight": insight,
        "data_quality": {
            "is_simulated": all(c.get("is_simulated", True) for c in channel_list) if channel_list else True,
            "label": "Simulated channel metrics — not live provider reporting",
        },
    }


def _ai_insight(channels: list[dict[str, Any]], totals: dict[str, Any]) -> str:
    if not channels:
        return "No channel metrics yet. Launch the campaign to start collecting results."
    by_engage = sorted(channels, key=lambda c: c["clicks"] + c["leads"] * 5, reverse=True)
    by_video = sorted(channels, key=lambda c: c["video_views"], reverse=True)
    top_engage = by_engage[0]
    top_video = by_video[0]
    local = next((c for c in channels if c["channel_code"] == "local_screens"), None)
    parts = [
        f"{top_engage['channel_name']} generated the strongest engagement signals "
        f"({top_engage['clicks']} clicks, {top_engage['leads']} leads) among channels with data.",
        f"{top_video['channel_name']} delivered the most video views ({top_video['video_views']}).",
    ]
    if local:
        parts.append(f"Local screen advertising generated {local['qr_scans']} QR scans.")
    if totals["leads"] and len(channels) > 1:
        parts.append(
            "Consider shifting a portion of remaining budget toward the best-performing channel, "
            "subject to available data and each channel's minimum budgets."
        )
    parts.append("These insights use recorded Bada metrics only and do not invent live platform stats.")
    return " ".join(parts)
