from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.integrations.advertising.registry import get_provider, list_providers
from app.models.base import utcnow
from app.models.channels import AdvertisingChannel, ChannelConnection
from app.models.user import User
from app.services.business_service import user_can_access_business


CHANNEL_CATALOG_SEED = [
    {
        "code": "meta",
        "name": "Meta (Facebook & Instagram)",
        "category": "social",
        "description": "Feed, Stories, and Reels advertising on Facebook and Instagram.",
        "logo_key": "meta",
        "sort_order": 10,
    },
    {
        "code": "youtube",
        "name": "YouTube",
        "category": "video",
        "description": "In-stream, bumper, and in-feed video ads.",
        "logo_key": "youtube",
        "sort_order": 20,
    },
    {
        "code": "ctv",
        "name": "Connected TV",
        "category": "ctv_ott",
        "description": "Smart TV and CTV network inventory via partners.",
        "logo_key": "ctv",
        "sort_order": 30,
    },
    {
        "code": "ott",
        "name": "OTT Streaming",
        "category": "ctv_ott",
        "description": "OTT / streaming inventory via approved partners (not unrestricted APIs).",
        "logo_key": "ott",
        "sort_order": 40,
    },
    {
        "code": "jiohotstar",
        "name": "JioHotstar",
        "category": "ctv_ott",
        "description": "Hotstar + JioCinema streaming ads — sports, movies, and shows via partners.",
        "logo_key": "jiohotstar",
        "sort_order": 41,
    },
    {
        "code": "sonyliv",
        "name": "Sony LIV",
        "category": "ctv_ott",
        "description": "Sony LIV premium and live sports streaming inventory.",
        "logo_key": "sonyliv",
        "sort_order": 42,
    },
    {
        "code": "zee5",
        "name": "ZEE5",
        "category": "ctv_ott",
        "description": "ZEE5 movies, originals, and regional language streaming ads.",
        "logo_key": "zee5",
        "sort_order": 43,
    },
    {
        "code": "amazon_prime",
        "name": "Amazon Prime Video",
        "category": "ctv_ott",
        "description": "Prime Video and Amazon miniTV reach via partner or Amazon Ads.",
        "logo_key": "amazon_prime",
        "sort_order": 44,
    },
    {
        "code": "mx_player",
        "name": "MX Player",
        "category": "ctv_ott",
        "description": "MX Player AVOD — mobile-first and vernacular streaming reach.",
        "logo_key": "mx_player",
        "sort_order": 45,
    },
    {
        "code": "netflix",
        "name": "Netflix",
        "category": "ctv_ott",
        "description": "Netflix brand / partner inventory only (no public self-serve ads API).",
        "logo_key": "netflix",
        "sort_order": 46,
    },
    {
        "code": "aha",
        "name": "aha",
        "category": "ctv_ott",
        "description": "aha Telugu and Tamil OTT streaming via regional partners.",
        "logo_key": "aha",
        "sort_order": 47,
    },
    {
        "code": "sunnxt",
        "name": "Sun NXT",
        "category": "ctv_ott",
        "description": "Sun NXT South Indian language movies and TV streaming ads.",
        "logo_key": "sunnxt",
        "sort_order": 48,
    },
    {
        "code": "publishers",
        "name": "Digital Publishers",
        "category": "publishers",
        "description": "News sites, regional publishers, and content networks.",
        "logo_key": "publishers",
        "sort_order": 50,
    },
    {
        "code": "local_screens",
        "name": "Local Digital Screens",
        "category": "local",
        "description": "Mall, retail, LED, and local screen inventory.",
        "logo_key": "local_screens",
        "sort_order": 60,
    },
    {
        "code": "outdoor",
        "name": "Outdoor & Transit",
        "category": "outdoor",
        "description": "Billboards, transit, and outdoor digital boards.",
        "logo_key": "outdoor",
        "sort_order": 70,
    },
]


def ensure_channel_catalog(db: Session) -> None:
    existing = {c.code for c in db.query(AdvertisingChannel).all()}
    for item in CHANNEL_CATALOG_SEED:
        if item["code"] in existing:
            continue
        provider = get_provider(item["code"])
        caps = provider.capabilities() if provider else None
        db.add(
            AdvertisingChannel(
                code=item["code"],
                name=item["name"],
                category=item["category"],
                description=item["description"],
                logo_key=item["logo_key"],
                ad_formats=",".join(caps.ad_formats) if caps else None,
                campaign_types=",".join(caps.objectives) if caps else None,
                targeting_options=",".join(caps.targeting) if caps else None,
                pricing_model=caps.pricing_model if caps else "cpm",
                estimated_cpm=caps.estimated_cpm if caps else None,
                minimum_budget=caps.min_daily_budget if caps else 500,
                integration_mode=provider.integration_mode.value if provider else "simulated",
                integration_status="available",
                is_active=True,
                is_estimate_pricing=True,
                sort_order=item["sort_order"],
                notes=caps.notes if caps else None,
            )
        )
    db.commit()


def serialize_channel(channel: AdvertisingChannel, connection: Optional[ChannelConnection] = None) -> dict[str, Any]:
    provider = get_provider(channel.code)
    caps = provider.capabilities() if provider else None
    return {
        "code": channel.code,
        "name": channel.name,
        "category": channel.category,
        "description": channel.description,
        "logo_key": channel.logo_key,
        "ad_formats": (channel.ad_formats or "").split(",") if channel.ad_formats else [],
        "campaign_types": (channel.campaign_types or "").split(",") if channel.campaign_types else [],
        "targeting_options": (channel.targeting_options or "").split(",") if channel.targeting_options else [],
        "pricing_model": channel.pricing_model,
        "estimated_cpm": channel.estimated_cpm,
        "minimum_budget": channel.minimum_budget,
        "integration_mode": channel.integration_mode,
        "integration_status": channel.integration_status,
        "is_estimate_pricing": channel.is_estimate_pricing,
        "notes": channel.notes,
        "capabilities": {
            "objectives": caps.objectives if caps else [],
            "ad_formats": caps.ad_formats if caps else [],
            "targeting": caps.targeting if caps else [],
            "metrics": caps.metrics if caps else [],
            "supports_oauth": caps.supports_oauth if caps else False,
            "supports_auto_launch": caps.supports_auto_launch if caps else False,
            "min_daily_budget": caps.min_daily_budget if caps else channel.minimum_budget,
        } if caps else None,
        "connection": {
            "status": connection.status if connection else "not_connected",
            "account_name": connection.account_name if connection else None,
            "account_id": connection.account_id if connection else None,
            "last_synced_at": connection.last_synced_at.isoformat() if connection and connection.last_synced_at else None,
            "last_error": connection.last_error if connection else None,
        },
        "disclaimer": (
            "Estimated pricing and simulated integrations until official APIs / partners are configured. "
            "Campaigns are not claimed live on third-party platforms without provider confirmation."
        ),
    }


def list_marketplace_channels(
    db: Session,
    *,
    category: Optional[str] = None,
    business_id: Optional[UUID] = None,
) -> list[dict[str, Any]]:
    ensure_channel_catalog(db)
    query = db.query(AdvertisingChannel).filter(AdvertisingChannel.is_active.is_(True))
    if category:
        query = query.filter(AdvertisingChannel.category == category)
    channels = query.order_by(AdvertisingChannel.sort_order.asc()).all()

    connections: dict[str, ChannelConnection] = {}
    if business_id:
        for conn in db.query(ChannelConnection).filter(ChannelConnection.business_id == business_id).all():
            connections[conn.channel_code] = conn

    return [serialize_channel(c, connections.get(c.code)) for c in channels]


def list_integrations(db: Session, user: User, business_id: UUID) -> list[dict[str, Any]]:
    user_can_access_business(db, user, business_id)
    return list_marketplace_channels(db, business_id=business_id)


def connect_channel(
    db: Session,
    user: User,
    *,
    business_id: UUID,
    channel_code: str,
    account_name: Optional[str] = None,
) -> dict[str, Any]:
    user_can_access_business(db, user, business_id)
    channel = db.query(AdvertisingChannel).filter(AdvertisingChannel.code == channel_code).first()
    if not channel:
        raise NotFoundError("Channel not found")

    provider = get_provider(channel_code)
    result = provider.connect_account() if provider else None

    conn = (
        db.query(ChannelConnection)
        .filter(ChannelConnection.business_id == business_id, ChannelConnection.channel_code == channel_code)
        .first()
    )
    if not conn:
        conn = ChannelConnection(
            business_id=business_id,
            user_id=user.id,
            channel_code=channel_code,
        )
        db.add(conn)

    # Simulated / manual connect — never store real secrets without OAuth
    if channel.integration_mode in ("simulated", "partner", "manual") or (
        result and not result.success
    ):
        conn.status = "connected"
        conn.account_name = account_name or f"Demo {channel.name} account"
        conn.account_id = f"demo_{channel_code}"
        conn.last_synced_at = utcnow()
        conn.last_error = None
        conn.meta_json = json.dumps(
            {
                "mode": channel.integration_mode,
                "note": "Demo connection. Not a live OAuth token. Tokens are never exposed to the frontend.",
            }
        )
    db.commit()
    db.refresh(conn)
    return serialize_channel(channel, conn)


def disconnect_channel(db: Session, user: User, *, business_id: UUID, channel_code: str) -> dict[str, Any]:
    user_can_access_business(db, user, business_id)
    conn = (
        db.query(ChannelConnection)
        .filter(ChannelConnection.business_id == business_id, ChannelConnection.channel_code == channel_code)
        .first()
    )
    if not conn:
        raise NotFoundError("Connection not found")
    conn.status = "not_connected"
    conn.access_token_encrypted = None
    conn.refresh_token_encrypted = None
    conn.account_name = None
    conn.account_id = None
    conn.last_error = None
    db.commit()
    channel = db.query(AdvertisingChannel).filter(AdvertisingChannel.code == channel_code).first()
    return serialize_channel(channel, conn) if channel else {"status": "not_connected"}
