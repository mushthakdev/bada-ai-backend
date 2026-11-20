from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analytics import CampaignMetric
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.models.qr import QRScan
from app.models.user import User
from app.services.business_service import list_businesses_for_user, user_can_access_business


def _date_range(range_key: str, start: Optional[date] = None, end: Optional[date] = None) -> tuple[date, date]:
    today = date.today()
    if range_key == "today":
        return today, today
    if range_key == "7d":
        return today - timedelta(days=6), today
    if range_key == "90d":
        return today - timedelta(days=89), today
    if range_key == "custom" and start and end:
        return start, end
    return today - timedelta(days=29), today


def get_dashboard_metrics(
    db: Session,
    user: User,
    *,
    business_id: Optional[UUID] = None,
    range_key: str = "30d",
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict[str, Any]:
    if business_id:
        user_can_access_business(db, user, business_id)
        business_ids = [business_id]
    else:
        business_ids = [b.id for b in list_businesses_for_user(db, user)]

    start_date, end_date = _date_range(range_key, start, end)

    if not business_ids:
        return {
            "totals": {
                "campaigns": 0,
                "active_campaigns": 0,
                "completed_campaigns": 0,
                "spend": 0,
                "impressions": 0,
                "estimated_reach": 0,
                "qr_scans": 0,
                "whatsapp_inquiries": 0,
                "phone_calls": 0,
                "website_visits": 0,
                "leads": 0,
            },
            "timeseries": [],
            "top_pincodes": [],
            "funnel": {},
            "recent_campaigns": [],
            "recent_leads": [],
            "data_quality": {"is_simulated": True, "label": "No data yet"},
            "range": {"start": str(start_date), "end": str(end_date)},
        }

    campaigns = (
        db.query(Campaign)
        .filter(Campaign.business_id.in_(business_ids), Campaign.is_deleted.is_(False))
        .all()
    )
    campaign_ids = [c.id for c in campaigns]

    metrics_q = db.query(CampaignMetric).filter(
        CampaignMetric.metric_date >= start_date,
        CampaignMetric.metric_date <= end_date,
    )
    if campaign_ids:
        metrics_q = metrics_q.filter(CampaignMetric.campaign_id.in_(campaign_ids))
    else:
        metrics_q = metrics_q.filter(False)

    metrics = metrics_q.all()
    is_simulated = all(m.is_simulated for m in metrics) if metrics else True

    totals = {
        "campaigns": len(campaigns),
        "active_campaigns": sum(1 for c in campaigns if c.status == "active"),
        "completed_campaigns": sum(1 for c in campaigns if c.status == "completed"),
        "spend": round(sum(m.spend for m in metrics), 2),
        "impressions": sum(m.impressions for m in metrics),
        "estimated_reach": sum(m.estimated_reach for m in metrics),
        "qr_scans": sum(m.qr_scans for m in metrics),
        "whatsapp_inquiries": sum(m.whatsapp_inquiries for m in metrics),
        "phone_calls": sum(m.phone_calls for m in metrics),
        "website_visits": sum(m.website_visits for m in metrics),
        "leads": sum(m.leads for m in metrics),
    }

    by_date: dict[str, dict[str, float]] = {}
    for m in metrics:
        key = str(m.metric_date)
        bucket = by_date.setdefault(
            key,
            {
                "date": key,
                "impressions": 0,
                "spend": 0,
                "leads": 0,
                "qr_scans": 0,
            },
        )
        bucket["impressions"] += m.impressions
        bucket["spend"] += m.spend
        bucket["leads"] += m.leads
        bucket["qr_scans"] += m.qr_scans

    timeseries = [by_date[k] for k in sorted(by_date.keys())]

    lead_rows = (
        db.query(Lead.pincode, func.count(Lead.id))
        .filter(Lead.business_id.in_(business_ids), Lead.pincode.isnot(None))
        .group_by(Lead.pincode)
        .order_by(func.count(Lead.id).desc())
        .limit(5)
        .all()
    )
    top_pincodes = [{"pincode": p, "leads": c} for p, c in lead_rows if p]

    funnel = {
        "impressions": totals["impressions"],
        "engagement": int(totals["impressions"] * 0.12),
        "qr_scans": totals["qr_scans"],
        "website_visits": totals["website_visits"],
        "whatsapp_inquiries": totals["whatsapp_inquiries"],
        "leads": totals["leads"],
    }

    recent_campaigns = [
        {
            "id": str(c.id),
            "name": c.name,
            "status": c.status,
            "objective": c.objective,
            "is_simulated_delivery": c.is_simulated_delivery,
        }
        for c in sorted(campaigns, key=lambda x: x.created_at, reverse=True)[:5]
    ]

    recent_leads = (
        db.query(Lead)
        .filter(Lead.business_id.in_(business_ids))
        .order_by(Lead.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "totals": totals,
        "timeseries": timeseries,
        "top_pincodes": top_pincodes,
        "funnel": funnel,
        "recent_campaigns": recent_campaigns,
        "recent_leads": [
            {
                "id": str(l.id),
                "name": l.name,
                "source": l.source,
                "status": l.status,
                "created_at": l.created_at.isoformat(),
            }
            for l in recent_leads
        ],
        "data_quality": {
            "is_simulated": is_simulated,
            "label": "Simulated demo metrics" if is_simulated else "Live metrics",
        },
        "range": {"start": str(start_date), "end": str(end_date)},
        "insights": _build_insights(totals, top_pincodes, is_simulated),
    }


def _build_insights(totals: dict[str, Any], top_pincodes: list[dict], is_simulated: bool) -> list[str]:
    prefix = "[Demo] " if is_simulated else ""
    insights = [
        f"{prefix}Your campaigns generated {totals['impressions']:,} impressions in this period.",
        f"{prefix}You received {totals['qr_scans']} QR scans and {totals['whatsapp_inquiries']} WhatsApp inquiries.",
        f"{prefix}Total leads generated: {totals['leads']}.",
    ]
    if top_pincodes:
        insights.append(
            f"{prefix}Highest-performing pincode was {top_pincodes[0]['pincode']} "
            f"with {top_pincodes[0]['leads']} leads."
        )
    return insights


def get_campaign_analytics(db: Session, user: User, campaign_id: UUID) -> dict[str, Any]:
    from app.services.campaign_service import get_campaign

    campaign = get_campaign(db, user, campaign_id)
    metrics = (
        db.query(CampaignMetric)
        .filter(CampaignMetric.campaign_id == campaign.id)
        .order_by(CampaignMetric.metric_date.asc())
        .all()
    )
    is_simulated = all(m.is_simulated for m in metrics) if metrics else True
    totals = {
        "impressions": sum(m.impressions for m in metrics),
        "estimated_reach": sum(m.estimated_reach for m in metrics),
        "completed_views": sum(m.completed_views for m in metrics),
        "qr_scans": sum(m.qr_scans for m in metrics),
        "website_visits": sum(m.website_visits for m in metrics),
        "whatsapp_inquiries": sum(m.whatsapp_inquiries for m in metrics),
        "phone_calls": sum(m.phone_calls for m in metrics),
        "leads": sum(m.leads for m in metrics),
        "spend": round(sum(m.spend for m in metrics), 2),
    }
    completion_rate = (
        round(totals["completed_views"] / totals["impressions"] * 100, 2)
        if totals["impressions"]
        else 0
    )
    cpl = round(totals["spend"] / totals["leads"], 2) if totals["leads"] else None

    return {
        "campaign_id": str(campaign.id),
        "campaign_name": campaign.name,
        "status": campaign.status,
        "is_simulated_delivery": campaign.is_simulated_delivery,
        "totals": totals,
        "video_completion_rate": completion_rate,
        "cost_per_lead": cpl,
        "timeseries": [
            {
                "date": str(m.metric_date),
                "impressions": m.impressions,
                "spend": m.spend,
                "leads": m.leads,
                "qr_scans": m.qr_scans,
            }
            for m in metrics
        ],
        "funnel": {
            "impressions": totals["impressions"],
            "engagement": int(totals["impressions"] * 0.12),
            "qr_scans": totals["qr_scans"],
            "website_visits": totals["website_visits"],
            "whatsapp_inquiries": totals["whatsapp_inquiries"],
            "leads": totals["leads"],
        },
        "data_quality": {
            "is_simulated": is_simulated,
            "label": "Simulated demo metrics" if is_simulated else "Live metrics",
        },
    }
