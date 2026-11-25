from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.creative import AdCreative
from app.models.user import User
from app.services.business_service import user_can_access_business

# Format specs — adaptation hints, not naive crops
FORMAT_SPECS: list[dict[str, Any]] = [
    {
        "format_key": "ctv_16x9",
        "label": "TV / CTV — 16:9",
        "aspect_ratio": "16:9",
        "orientation": "landscape",
        "channels": [
            "ctv",
            "ott",
            "jiohotstar",
            "sonyliv",
            "zee5",
            "amazon_prime",
            "mx_player",
            "netflix",
            "aha",
            "sunnxt",
        ],
        "duration_seconds": 30,
        "safe_zone": "Keep logo and CTA within central 80% — TV overscan",
        "adaptation": "Larger type, slower pacing, end-card with QR",
    },
    {
        "format_key": "youtube_landscape",
        "label": "YouTube — landscape",
        "aspect_ratio": "16:9",
        "orientation": "landscape",
        "channels": ["youtube"],
        "duration_seconds": 20,
        "safe_zone": "Leave lower-right clear for YouTube UI chrome",
        "adaptation": "Hook in first 5s; captions burned in",
    },
    {
        "format_key": "instagram_reel",
        "label": "Instagram Reel — 9:16",
        "aspect_ratio": "9:16",
        "orientation": "portrait",
        "channels": ["meta"],
        "duration_seconds": 15,
        "safe_zone": "Keep CTA above bottom 20% (UI overlays)",
        "adaptation": "Vertical reframing with subject-aware composition, not a simple crop",
    },
    {
        "format_key": "instagram_story",
        "label": "Instagram Story — 9:16",
        "aspect_ratio": "9:16",
        "orientation": "portrait",
        "channels": ["meta"],
        "duration_seconds": 10,
        "safe_zone": "Top 14% and bottom 20% reserved for system UI",
        "adaptation": "Shorter copy, swipe-up style CTA language",
    },
    {
        "format_key": "facebook_feed",
        "label": "Facebook feed",
        "aspect_ratio": "1:1",
        "orientation": "square",
        "channels": ["meta"],
        "duration_seconds": 15,
        "safe_zone": "Primary message in centre third",
        "adaptation": "Square master with readable captions",
    },
    {
        "format_key": "social_image",
        "label": "Social feed image",
        "aspect_ratio": "1:1",
        "orientation": "square",
        "channels": ["meta"],
        "duration_seconds": 0,
        "safe_zone": "Logo bottom-left, offer centre",
        "adaptation": "Static key visual derived from brief — not a video frame grab alone",
    },
    {
        "format_key": "display_banner",
        "label": "Display banner",
        "aspect_ratio": "16:9",
        "orientation": "landscape",
        "channels": ["publishers"],
        "duration_seconds": 0,
        "safe_zone": "300x250 / 728x90 friendly hierarchy",
        "adaptation": "Compressed messaging for banner density",
    },
    {
        "format_key": "local_screen",
        "label": "Local digital screen",
        "aspect_ratio": "16:9",
        "orientation": "landscape",
        "channels": ["local_screens"],
        "duration_seconds": 10,
        "safe_zone": "High contrast; large CTA for viewing distance",
        "adaptation": "Loop-friendly; QR prominent",
    },
    {
        "format_key": "publisher_video",
        "label": "Publisher video ad",
        "aspect_ratio": "16:9",
        "orientation": "landscape",
        "channels": ["publishers"],
        "duration_seconds": 15,
        "safe_zone": "Centre-weighted for in-article players",
        "adaptation": "Muted-autoplay ready with captions",
    },
]


def generate_format_variants(
    db: Session,
    user: User,
    *,
    creative_id: UUID,
    channel_codes: Optional[list[str]] = None,
) -> dict[str, Any]:
    creative = db.query(AdCreative).filter(AdCreative.id == creative_id).first()
    if not creative:
        raise NotFoundError("Creative not found")
    user_can_access_business(db, user, creative.business_id)

    specs = FORMAT_SPECS
    if channel_codes:
        specs = [s for s in FORMAT_SPECS if any(ch in s["channels"] for ch in channel_codes)]

    variants = []
    for spec in specs:
        variants.append(
            {
                **spec,
                "status": "mock_adapted",
                "is_mock": True,
                "preview_note": (
                    f"AI-assisted adaptation plan for {spec['label']}: {spec['adaptation']}. "
                    "Not a naive crop of a single master. Render requires a video/image provider."
                ),
                "script_hint": creative.script,
                "cta": creative.cta_text,
                "source_creative_id": str(creative.id),
            }
        )

    return {
        "creative_id": str(creative.id),
        "variants": variants,
        "is_mock": True,
        "note": (
            "Universal Creative Studio returns adaptation blueprints per format. "
            "Final rendered assets require configured generation providers."
        ),
    }
