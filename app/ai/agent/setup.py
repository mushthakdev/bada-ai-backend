"""Multi-step campaign setup wizard driven by Agent chat."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.agent.prompts import OBJECTIVE_ALIASES
from app.core.exceptions import ValidationAppError
from app.integrations.advertising.registry import get_provider
from app.models.ai import AIConversation
from app.models.campaign import Campaign
from app.models.channels import CampaignChannel
from app.models.inventory import PincodeInventory
from app.models.user import User
from app.schemas.campaign import (
    CampaignAudienceIn,
    CampaignBudgetIn,
    CampaignCreate,
    CampaignLocationIn,
    CampaignScheduleIn,
)
from app.services import campaign_service
from app.services.channel_service import CHANNEL_CATALOG_SEED, ensure_channel_catalog
from app.services import payment_service
from app.services.omnichannel_service import launch_omnichannel

STEPS = (
    "area",
    "pincode",
    "objective",
    "name",
    "language",
    "budget",
    "confirm",
    "platforms",
    "payment",
    "start",
)

OBJECTIVES = [
    ("brand_awareness", "Brand awareness"),
    ("increase_store_visits", "Store visits / footfall"),
    ("lead_generation", "Lead generation"),
    ("website_traffic", "Website traffic"),
    ("sales", "Sales"),
]

LANGUAGES = [
    ("en", "English"),
    ("ml", "Malayalam"),
    ("ta", "Tamil"),
    ("hi", "Hindi"),
    ("te", "Telugu"),
    ("kn", "Kannada"),
]

PLATFORMS = [
    (item["code"], item["name"], item["description"]) for item in CHANNEL_CATALOG_SEED
]

PLATFORM_ALIASES = {
    "meta": "meta",
    "facebook": "meta",
    "instagram": "meta",
    "fb": "meta",
    "ig": "meta",
    "youtube": "youtube",
    "yt": "youtube",
    "google": "youtube",
    "ctv": "ctv",
    "connected tv": "ctv",
    "connectedtv": "ctv",
    "tv": "ctv",
    "ott": "ott",
    "streaming": "ott",
    "jiohotstar": "jiohotstar",
    "hotstar": "jiohotstar",
    "disney hotstar": "jiohotstar",
    "jiocinema": "jiohotstar",
    "jio cinema": "jiohotstar",
    "sonyliv": "sonyliv",
    "sony liv": "sonyliv",
    "sony": "sonyliv",
    "zee5": "zee5",
    "zee": "zee5",
    "amazon_prime": "amazon_prime",
    "amazon prime": "amazon_prime",
    "prime": "amazon_prime",
    "prime video": "amazon_prime",
    "mx_player": "mx_player",
    "mx player": "mx_player",
    "mxplayer": "mx_player",
    "netflix": "netflix",
    "aha": "aha",
    "sunnxt": "sunnxt",
    "sun nxt": "sunnxt",
    "publishers": "publishers",
    "publisher": "publishers",
    "digital": "publishers",
    "local_screens": "local_screens",
    "local screens": "local_screens",
    "local": "local_screens",
    "screens": "local_screens",
    "outdoor": "outdoor",
    "billboard": "outdoor",
    "transit": "outdoor",
}

CANCEL_RE = re.compile(r"^\s*(cancel|stop|exit|quit|never\s*mind|abort)\s*$", re.I)
CONFIRM_RE = re.compile(
    r"^\s*(yes|y|ok|okay|confirm|create|go\s*ahead|do\s*it|sure|"
    r"yes[,\s]+create(\s+it)?|yes[,\s]+create\s+draft|create\s+(it|draft))\s*$",
    re.I,
)
PIN_RE = re.compile(r"\b(\d{6})\b")
ALL_PINS_RE = re.compile(r"^\s*(all|all\s+pincodes?|select\s+all|every|all\s+platforms?)\s*$", re.I)
NEAR_AREA_RE = re.compile(
    r"\b(?:near|in|around|at|for)\s+([A-Za-z][A-Za-z\s]{1,40})(?:\s+(?:area|city|district|town))?\b",
    re.I,
)
ADVERT_INTENT_RE = re.compile(
    r"\b(advert|ads?|campa\w*|promot|market|publici[sz]e)\b|"
    r"\b(new|create|start|launch|set\s*up|setup)\b.*\b(near|in|around)\b|"
    r"\b(near|in|around)\b.*\b(advert|ads?|campa\w*|company|business)\b",
    re.I,
)
CREATE_RE = re.compile(
    r"\b(create|start|new|launch|make|set\s*up|setup)\b.*\b(campa\w*|ad|ads|advert)\b|"
    r"\b(campa\w*|ad)\b.*\b(create|new|start)\b",
    re.I,
)


def _load_setup(conversation: AIConversation) -> Optional[dict[str, Any]]:
    if not conversation.context_json:
        return None
    try:
        data = json.loads(conversation.context_json)
    except json.JSONDecodeError:
        return None
    setup = data.get("setup")
    if isinstance(setup, dict) and setup.get("active"):
        return setup
    return None


def _save_setup(conversation: AIConversation, setup: Optional[dict[str, Any]]) -> None:
    try:
        data = json.loads(conversation.context_json) if conversation.context_json else {}
    except json.JSONDecodeError:
        data = {}
    if setup is None:
        data.pop("setup", None)
    else:
        data["setup"] = setup
    conversation.context_json = json.dumps(data)


def _new_setup(ctx: dict[str, Any], area: Optional[str] = None) -> dict[str, Any]:
    businesses = ctx.get("businesses") or []
    business_id = businesses[0]["id"] if businesses else None
    default_obj = None
    if businesses:
        default_obj = businesses[0].get("objective")
    return {
        "active": True,
        "step": "area" if not area else "pincode",
        "draft": {
            "business_id": business_id,
            "area": area,
            "pincodes": [],
            "suggested": [],
            "objective": default_obj,
            "name": None,
            "language": "ml" if area and re.search(r"ernakulam|kochi|kerala", area, re.I) else "en",
            "daily_budget": 1500,
            "total_days": 14,
            "platforms": [],
            "campaign_id": None,
            "paid": False,
        },
    }


def lookup_area_pincodes(db: Session, area: str, limit: int = 12) -> list[dict[str, Any]]:
    like = f"%{area.strip()}%"
    rows = (
        db.query(PincodeInventory)
        .filter(
            PincodeInventory.is_available.is_(True),
            (
                PincodeInventory.city.ilike(like)
                | PincodeInventory.district.ilike(like)
                | PincodeInventory.state.ilike(like)
                | PincodeInventory.pincode.ilike(like)
            ),
        )
        .order_by(PincodeInventory.pincode.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "pincode": r.pincode,
            "city": r.city,
            "district": r.district,
            "state": r.state,
            "estimated_ctv_reach": r.estimated_ctv_reach,
            "avg_cpm": r.avg_cpm,
        }
        for r in rows
    ]


def _extract_area(message: str) -> Optional[str]:
    # Known hubs first (handles typos / extra words around the place name)
    for name in (
        "Ernakulam",
        "Kochi",
        "Cochin",
        "Thrissur",
        "Trivandrum",
        "Thiruvananthapuram",
        "Calicut",
        "Kozhikode",
        "Bangalore",
        "Bengaluru",
        "Chennai",
        "Hyderabad",
        "Mumbai",
        "Delhi",
    ):
        if re.search(rf"\b{re.escape(name)}\b", message, re.I):
            return "Ernakulam" if name.lower() in ("kochi", "cochin") else name

    # Prefer "near <place>" / "in <place>"
    m = NEAR_AREA_RE.search(message)
    if m:
        area = m.group(1).strip(" ,.")
        # Stop at another near/in or junk marketing words (incl. misspellings)
        area = re.split(
            r"\b(?:near|in|around|at|for|advert\w*|advanc\w*|ads?|campa\w*|compan\w*|business|and)\b",
            area,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" ,.")
        if len(area) >= 3:
            return area.title()
    return None


def _format_pin_list(pins: list[dict[str, Any]]) -> str:
    lines = []
    for p in pins[:10]:
        reach = p.get("estimated_ctv_reach")
        reach_s = f" · ~{reach:,} CTV reach" if reach else ""
        lines.append(f"- **{p['pincode']}** — {p.get('city') or ''} {p.get('district') or ''}{reach_s}".strip())
    return "\n".join(lines)


def _suggestions_for(step: str, draft: dict[str, Any]) -> list[str]:
    if step == "area":
        return ["Ernakulam", "Kochi", "Thrissur", "Trivandrum"]
    if step == "pincode":
        pins = [p["pincode"] for p in (draft.get("suggested") or [])[:4]]
        out = pins[:]
        if pins:
            out.append("all")
        out.append("skip")
        return out
    if step == "objective":
        return [label for _, label in OBJECTIVES]
    if step == "name":
        area = draft.get("area") or "Local"
        return [f"{area} awareness", f"{area} store visits", "Skip — use default"]
    if step == "language":
        return [label for _, label in LANGUAGES[:4]]
    if step == "budget":
        return ["₹1500 / day", "₹2500 / day", "₹5000 / day", "₹10000 / day"]
    if step == "confirm":
        return ["Yes, create it", "Cancel"]
    if step == "platforms":
        return ["meta, youtube", "all", "skip"]
    if step == "payment":
        return ["Pay now", "Pay later", "Open payments"]
    if step == "start":
        return ["Start advertising", "Keep scheduled", "Finish later"]
    return []


def _select_for(step: str, draft: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Structured select UI for the Agent frontend (multi/single + select-all)."""
    if step == "area":
        return {
            "id": "area",
            "mode": "single",
            "title": "Select target area",
            "submit_label": "Continue",
            "allow_custom": True,
            "custom_placeholder": "Or type a city / district",
            "options": [
                {"value": "Ernakulam", "label": "Ernakulam", "description": "Kochi metro · Kerala"},
                {"value": "Kochi", "label": "Kochi", "description": "Mapped to Ernakulam inventory"},
                {"value": "Thrissur", "label": "Thrissur", "description": "Kerala"},
                {"value": "Trivandrum", "label": "Trivandrum", "description": "Thiruvananthapuram"},
            ],
        }

    if step == "pincode":
        options = []
        for p in draft.get("suggested") or []:
            reach = p.get("estimated_ctv_reach")
            desc_parts = [x for x in [p.get("city"), p.get("district")] if x]
            if reach:
                desc_parts.append(f"~{int(reach):,} CTV reach")
            options.append(
                {
                    "value": p["pincode"],
                    "label": p["pincode"],
                    "description": " · ".join(desc_parts) if desc_parts else None,
                }
            )
        if not options:
            options = [
                {"value": "682001", "label": "682001", "description": "Kochi · Ernakulam"},
                {"value": "682016", "label": "682016", "description": "Kochi · Ernakulam"},
                {"value": "682020", "label": "682020", "description": "Kochi · Ernakulam"},
                {"value": "682030", "label": "682030", "description": "Kochi · Ernakulam"},
            ]
        return {
            "id": "pincode",
            "mode": "multi",
            "title": "Select pincodes",
            "select_all": True,
            "allow_skip": True,
            "allow_custom": True,
            "custom_placeholder": "Add pincode (6 digits)",
            "submit_label": "Continue with selected",
            "options": options,
        }

    if step == "objective":
        return {
            "id": "objective",
            "mode": "single",
            "title": "Select campaign objective",
            "submit_label": "Continue",
            "options": [
                {"value": label, "label": label, "description": key.replace("_", " ")}
                for key, label in OBJECTIVES
            ],
        }

    if step == "name":
        area = draft.get("area") or "Local"
        obj = (draft.get("objective") or "campaign").replace("_", " ")
        return {
            "id": "name",
            "mode": "single",
            "title": "Choose a campaign name",
            "submit_label": "Continue",
            "allow_custom": True,
            "custom_placeholder": "Type your own campaign name",
            "options": [
                {"value": f"{area} awareness", "label": f"{area} awareness"},
                {"value": f"{area} store visits", "label": f"{area} store visits"},
                {"value": f"{area} {obj}", "label": f"{area} {obj}"},
                {"value": "Skip — use default", "label": "Use default name"},
            ],
        }

    if step == "language":
        return {
            "id": "language",
            "mode": "single",
            "title": "Select ad language",
            "submit_label": "Continue",
            "options": [{"value": label, "label": label} for _, label in LANGUAGES],
        }

    if step == "budget":
        return {
            "id": "budget",
            "mode": "single",
            "title": "Select daily budget (₹)",
            "submit_label": "Continue",
            "allow_custom": True,
            "custom_placeholder": "Or type amount (min 1000)",
            "options": [
                {"value": "1500", "label": "₹1,500 / day", "description": "Starter"},
                {"value": "2500", "label": "₹2,500 / day", "description": "Popular"},
                {"value": "5000", "label": "₹5,000 / day", "description": "Growth"},
                {"value": "10000", "label": "₹10,000 / day", "description": "High reach"},
            ],
        }

    if step == "confirm":
        return {
            "id": "confirm",
            "mode": "single",
            "title": "Confirm draft campaign",
            "submit_label": "Confirm",
            "options": [
                {
                    "value": "Yes, create it",
                    "label": "Yes, create draft",
                    "description": "Creates the draft, then choose platforms",
                },
                {"value": "Cancel", "label": "Cancel setup", "description": "Discard this wizard"},
            ],
        }

    if step == "platforms":
        return {
            "id": "platforms",
            "mode": "multi",
            "title": "Choose advertising platforms",
            "select_all": True,
            "allow_skip": True,
            "submit_label": "Continue with platforms",
            "options": [
                {"value": code, "label": name, "description": desc}
                for code, name, desc in PLATFORMS
            ],
        }

    if step == "payment":
        amount = draft.get("total_payable")
        amount_s = f"₹{int(amount):,}" if amount else "campaign total"
        return {
            "id": "payment",
            "mode": "single",
            "title": "Payment",
            "submit_label": "Continue",
            "options": [
                {
                    "value": "pay_now",
                    "label": "Pay now (mock)",
                    "description": f"Complete mock payment of {amount_s} and schedule the campaign",
                },
                {
                    "value": "pay_later",
                    "label": "Pay later",
                    "description": "Skip payment for now — pay from Payments anytime",
                },
                {
                    "value": "open_payments",
                    "label": "Open payments page",
                    "description": "Go to the Payments screen for this campaign",
                },
            ],
        }

    if step == "start":
        return {
            "id": "start",
            "mode": "single",
            "title": "Start advertising",
            "submit_label": "Finish",
            "options": [
                {
                    "value": "start_now",
                    "label": "Start advertising now",
                    "description": "Launch selected platforms (simulated delivery)",
                },
                {
                    "value": "keep_scheduled",
                    "label": "Keep scheduled",
                    "description": "Leave campaign scheduled — start later from campaign page",
                },
                {
                    "value": "finish_later",
                    "label": "Finish later",
                    "description": "Exit wizard — open campaign when you are ready",
                },
            ],
        }
    return None


def _pack(
    reply: str,
    *,
    step: Optional[str] = None,
    draft: Optional[dict[str, Any]] = None,
    actions: Optional[list[dict[str, str]]] = None,
    tool_results: Optional[list[dict[str, Any]]] = None,
    suggestions: Optional[list[str]] = None,
) -> dict[str, Any]:
    d = draft or {}
    return {
        "reply": reply,
        "actions": actions or [],
        "suggestions": suggestions if suggestions is not None else (_suggestions_for(step, d) if step else []),
        "select": _select_for(step, d) if step else None,
        "tool_results": tool_results or [],
        "handled": True,
    }


def _parse_objective(text: str) -> Optional[str]:
    lower = text.lower().strip()
    for key, label in OBJECTIVES:
        if lower == key or lower == label.lower() or key.replace("_", " ") in lower:
            return key
    for alias, mapped in OBJECTIVE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            return mapped
    # numbered choice 1-5
    if lower.isdigit() and 1 <= int(lower) <= len(OBJECTIVES):
        return OBJECTIVES[int(lower) - 1][0]
    return None


def _parse_language(text: str) -> Optional[str]:
    lower = text.lower().strip()
    for code, label in LANGUAGES:
        if lower == code or lower == label.lower():
            return code
    if "malayalam" in lower:
        return "ml"
    if "tamil" in lower:
        return "ta"
    if "hindi" in lower:
        return "hi"
    if "english" in lower:
        return "en"
    return None


def _parse_budget(text: str) -> Optional[float]:
    cleaned = text.replace(",", "").replace("₹", "").replace("rs", "").replace("inr", "")
    m = re.search(r"(\d+(?:\.\d+)?)", cleaned, re.I)
    if not m:
        return None
    value = float(m.group(1))
    if value < 100:  # treat as thousands shorthand? no — too ambiguous
        return None
    return max(value, 1000.0)


def _draft_summary(draft: dict[str, Any]) -> str:
    pins = draft.get("pincodes") or []
    pin_s = ", ".join(pins) if pins else "(none yet — you can add later)"
    obj = draft.get("objective") or "brand_awareness"
    lang = draft.get("language") or "en"
    lang_label = next((l for c, l in LANGUAGES if c == lang), lang)
    platforms = draft.get("platforms") or []
    plat_s = ", ".join(platforms) if platforms else "(choose next)"
    return (
        f"**Campaign draft**\n"
        f"- Name: {draft.get('name') or '(default)'}\n"
        f"- Area: {draft.get('area') or '—'}\n"
        f"- Pincodes: {pin_s}\n"
        f"- Objective: {obj.replace('_', ' ')}\n"
        f"- Language: {lang_label}\n"
        f"- Daily budget: ₹{int(draft.get('daily_budget') or 1500)}\n"
        f"- Duration: {draft.get('total_days') or 14} days\n"
        f"- Platforms: {plat_s}"
    )


def _is_confirm(text: str) -> bool:
    t = text.strip()
    if CONFIRM_RE.match(t):
        return True
    lower = t.lower()
    return lower in {
        "yes, create it",
        "yes create it",
        "yes, create draft",
        "yes create draft",
        "create draft",
        "confirm",
    } or lower.startswith("yes")


def _platform_label(code: str) -> str:
    for c, name, _ in PLATFORMS:
        if c == code:
            return name
    return code


def _parse_platforms(text: str) -> Optional[list[str]]:
    """Parse platform codes from multi-select or free text. Returns [] for skip."""
    raw = text.strip()
    if not raw:
        return None
    if re.match(r"^\s*skip\s*$", raw, re.I):
        return []
    if ALL_PINS_RE.match(raw):
        return [code for code, _, _ in PLATFORMS]

    # Split on commas / "and" / whitespace for known codes
    parts = re.split(r"[,+/]|and|\s+", raw.lower())
    parts = [p.strip() for p in parts if p.strip()]
    found: list[str] = []
    for part in parts:
        code = PLATFORM_ALIASES.get(part) or PLATFORM_ALIASES.get(part.replace("_", " "))
        if not code:
            for alias, mapped in PLATFORM_ALIASES.items():
                if alias in part or part in alias:
                    code = mapped
                    break
        if code and code not in found:
            found.append(code)

    # Also match full catalog names in the raw string
    lower = raw.lower()
    for code, name, _ in PLATFORMS:
        if code in found:
            continue
        if code in lower or name.lower() in lower:
            found.append(code)

    return found if found else None


def _campaign_actions(campaign_id: str, *, paid: bool = False, live: bool = False) -> list[dict[str, str]]:
    actions = [
        {"type": "link", "label": "Open campaign", "href": f"/campaigns/{campaign_id}"},
        {"type": "link", "label": "Edit details", "href": f"/campaigns/{campaign_id}/edit"},
        {"type": "link", "label": "Generate creative", "href": f"/studio/{campaign_id}"},
        {"type": "link", "label": "Payments", "href": f"/payments?campaign={campaign_id}"},
    ]
    if paid or live:
        actions.append(
            {"type": "link", "label": "Omnichannel control", "href": f"/campaigns/omnichannel/{campaign_id}"}
        )
    return actions


def _attach_platforms(
    db: Session,
    user: User,
    campaign_id: UUID,
    codes: list[str],
) -> dict[str, Any]:
    """Mark campaign omnichannel and attach selected channels with equal budget split."""
    if not codes:
        return {"ok": True, "platforms": [], "skipped": True}

    ensure_channel_catalog(db)
    campaign = campaign_service.get_campaign(db, user, campaign_id)
    if campaign.budget:
        total = float(campaign.budget.total_budget)
    else:
        total = 1500.0 * 14

    per = round(total / len(codes), 2) if codes else 0.0
    # Fix rounding on last channel
    allocations = []
    remaining = total
    for i, code in enumerate(codes):
        provider = get_provider(code)
        if not provider:
            raise ValidationAppError(f"Unknown platform: {code}")
        amt = remaining if i == len(codes) - 1 else per
        remaining = round(remaining - amt, 2)
        allocations.append((code, provider.name, provider.integration_mode.value, amt))

    # Replace existing channel rows for this campaign
    db.query(CampaignChannel).filter(CampaignChannel.campaign_id == campaign.id).delete()
    for code, name, mode, amt in allocations:
        db.add(
            CampaignChannel(
                campaign_id=campaign.id,
                channel_code=code,
                channel_name=name,
                status="draft",
                allocated_budget=amt,
                integration_mode=mode,
                is_simulated=True,
                targeting_json=json.dumps({}),
            )
        )

    # Persist omnichannel flag on ORM campaign
    row = db.query(Campaign).filter(Campaign.id == campaign.id).first()
    if row:
        row.is_omnichannel = True
        row.is_simulated_delivery = True
    db.commit()
    return {
        "ok": True,
        "platforms": codes,
        "labels": [_platform_label(c) for c in codes],
        "allocations": [{"channel_code": c, "budget": a} for c, _, _, a in allocations],
    }


def _prepare_for_payment(db: Session, user: User, campaign_id: UUID) -> None:
    """Advance draft → ready_for_review → approved so payment is eligible."""
    campaign = campaign_service.get_campaign(db, user, campaign_id)
    path = {
        "draft": ["ready_for_review", "approved"],
        "creative_generating": ["ready_for_review", "approved"],
        "ready_for_review": ["approved"],
        "approved": [],
        "payment_pending": [],
        "scheduled": [],
        "active": [],
    }
    for status in path.get(campaign.status, []):
        campaign_service.transition_status(db, user, campaign_id, status)


def _run_mock_payment(db: Session, user: User, campaign_id: UUID) -> dict[str, Any]:
    _prepare_for_payment(db, user, campaign_id)
    order = payment_service.create_payment_order(db, user, campaign_id)
    verified = payment_service.verify_payment(
        db,
        user,
        payment_id=UUID(str(order["payment_id"])),
        mock_success=True,
    )
    return {"ok": True, "order": order, "verified": verified}


def _start_advertising(db: Session, user: User, campaign_id: UUID, platforms: list[str]) -> dict[str, Any]:
    campaign = campaign_service.get_campaign(db, user, campaign_id)

    # Ensure channels exist if user skipped platforms earlier but now wants to start
    if platforms and campaign.is_omnichannel is False:
        _attach_platforms(db, user, campaign_id, platforms)
        campaign = campaign_service.get_campaign(db, user, campaign_id)

    # If paid/scheduled → active; if still draft-like, advance then activate
    if campaign.status in ("draft", "creative_generating", "ready_for_review", "approved", "payment_pending"):
        # Soft-path for demo: mark scheduled without forcing payment when user chose pay later
        if campaign.status in ("draft", "creative_generating"):
            campaign_service.transition_status(db, user, campaign_id, "ready_for_review")
            campaign = campaign_service.get_campaign(db, user, campaign_id)
        if campaign.status == "ready_for_review":
            campaign_service.transition_status(db, user, campaign_id, "approved")
            campaign = campaign_service.get_campaign(db, user, campaign_id)
        if campaign.status == "approved":
            campaign_service.transition_status(db, user, campaign_id, "payment_pending")
            campaign = campaign_service.get_campaign(db, user, campaign_id)
        if campaign.status == "payment_pending":
            campaign_service.transition_status(db, user, campaign_id, "scheduled")
            campaign = campaign_service.get_campaign(db, user, campaign_id)

    # Prefer omnichannel launch when channels are attached
    row = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    has_channels = (
        db.query(CampaignChannel).filter(CampaignChannel.campaign_id == campaign_id).count() > 0
    )
    if has_channels and row:
        try:
            detail = launch_omnichannel(db, user, campaign_id)
            launch = detail.get("launch") or {}
            return {
                "ok": True,
                "mode": "omnichannel",
                "status": detail.get("status") or "active",
                "campaign_id": str(campaign_id),
                "active_count": launch.get("active_count"),
                "failed_count": launch.get("failed_count"),
                "partial_launch": launch.get("partial_launch"),
            }
        except ValidationAppError as exc:
            # Fall back to status transition
            if campaign.status == "scheduled":
                out = campaign_service.transition_status(db, user, campaign_id, "active")
                return {
                    "ok": True,
                    "mode": "status",
                    "status": out.status,
                    "campaign_id": str(campaign_id),
                    "warning": str(exc),
                }
            raise

    if campaign.status == "scheduled":
        out = campaign_service.transition_status(db, user, campaign_id, "active")
        return {"ok": True, "mode": "status", "status": out.status, "campaign_id": str(campaign_id)}
    if campaign.status == "active":
        return {"ok": True, "mode": "already_active", "status": "active", "campaign_id": str(campaign_id)}

    out = campaign_service.transition_status(db, user, campaign_id, "active")
    return {"ok": True, "mode": "status", "status": out.status, "campaign_id": str(campaign_id)}


def _create_from_draft(
    db: Session,
    user: User,
    draft: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    businesses = ctx.get("businesses") or []
    if not businesses and not draft.get("business_id"):
        return {"ok": False, "error": "No business on your account. Complete onboarding first."}

    bid = UUID(str(draft.get("business_id") or businesses[0]["id"]))
    area = draft.get("area") or "Local"
    name = (draft.get("name") or f"{area} campaign {date.today().isoformat()}").strip()[:200]
    objective = draft.get("objective") or "brand_awareness"
    language = draft.get("language") or "en"
    daily = float(draft.get("daily_budget") or 1500)
    days = int(draft.get("total_days") or 14)
    total = max(daily * days, 1000)

    locations: list[CampaignLocationIn] = []
    for pin in draft.get("pincodes") or []:
        row = db.query(PincodeInventory).filter(PincodeInventory.pincode == pin).first()
        locations.append(
            CampaignLocationIn(
                pincode=pin,
                city=row.city if row else None,
                state=row.state if row else None,
                district=row.district if row else None,
            )
        )

    start = date.today() + timedelta(days=3)
    end = start + timedelta(days=days)

    payload = CampaignCreate(
        business_id=bid,
        name=name,
        objective=objective,
        description=f"Agent setup for {area}",
        language=language,
        video_duration=30,
        brief_text=f"Advertise near {area}" if area else None,
        locations=locations,
        audience=CampaignAudienceIn(languages=[language]),
        budget=CampaignBudgetIn(daily_budget=max(daily, 1000), total_budget=total, duration_days=days),
        schedule=CampaignScheduleIn(start_date=start, end_date=end),
    )
    created = campaign_service.create_campaign(db, user, payload)
    return {
        "ok": True,
        "campaign": {
            "id": str(created.id),
            "name": created.name,
            "status": created.status,
            "href": f"/campaigns/{created.id}",
            "edit_href": f"/campaigns/{created.id}/edit",
            "studio_href": f"/studio/{created.id}",
        },
        "actions": [
            {"type": "link", "label": "Open campaign", "href": f"/campaigns/{created.id}"},
            {"type": "link", "label": "Edit details", "href": f"/campaigns/{created.id}/edit"},
            {"type": "link", "label": "Generate creative", "href": f"/studio/{created.id}"},
        ],
    }


def should_start_setup(message: str) -> bool:
    text = message.strip()
    if CREATE_RE.search(text):
        return True
    if ADVERT_INTENT_RE.search(text) and (_extract_area(text) or PIN_RE.search(text)):
        return True
    if ADVERT_INTENT_RE.search(text) and re.search(r"\b(new|create|start|near|company)\b", text, re.I):
        return True
    return False


def handle_setup_turn(
    db: Session,
    user: User,
    conversation: AIConversation,
    message: str,
    ctx: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """
    Process one wizard turn. Returns agent response dict, or None if wizard not active
    and message should fall through to normal agent.
    """
    text = message.strip()
    setup = _load_setup(conversation)

    # Cancel
    if setup and CANCEL_RE.match(text):
        _save_setup(conversation, None)
        return _pack(
            "Okay — campaign setup cancelled. Say “create a new campaign” anytime to start again.",
            suggestions=["Create a new campaign", "List my campaigns", "How is my spend?"],
            tool_results=[{"ok": True, "tool": "setup_cancel"}],
        )

    # Start new setup
    if not setup:
        if not should_start_setup(text):
            return None
        businesses = ctx.get("businesses") or []
        if not businesses:
            return _pack(
                "You need a business on your account before we can set up a campaign. Finish onboarding first.",
                actions=[{"type": "link", "label": "Go to onboarding", "href": "/onboarding"}],
                suggestions=[],
            )

        area = _extract_area(text)
        pins_in_msg = PIN_RE.findall(text)
        setup = _new_setup(ctx, area=area)
        if pins_in_msg:
            setup["draft"]["pincodes"] = pins_in_msg
            setup["step"] = "objective"
        elif area:
            suggested = lookup_area_pincodes(db, area)
            setup["draft"]["suggested"] = suggested
            setup["step"] = "pincode" if suggested else "area"
        else:
            setup["step"] = "area"
        _save_setup(conversation, setup)

        if setup["step"] == "pincode":
            suggested = setup["draft"]["suggested"]
            reply = (
                f"Great — let’s set up advertising near **{area}**.\n\n"
                f"Select one or more pincodes below (use **Select all**), or add a custom pincode.\n\n"
                f"{_format_pin_list(suggested)}"
            )
            return _pack(
                reply,
                step="pincode",
                draft=setup["draft"],
                tool_results=[{"ok": True, "tool": "setup_start", "step": "pincode", "area": area}],
            )

        if setup["step"] == "objective":
            reply = (
                "Got it — starting campaign setup with your pincode(s).\n\n"
                "Select the **objective** below."
            )
            return _pack(
                reply,
                step="objective",
                draft=setup["draft"],
                tool_results=[{"ok": True, "tool": "setup_start", "step": "objective"}],
            )

        return _pack(
            "Let’s set up your campaign step by step.\n\n"
            "**Step 1 — Area:** Select a city/district, or type your own.",
            step="area",
            draft=setup["draft"],
            tool_results=[{"ok": True, "tool": "setup_start", "step": "area"}],
        )

    # Continue existing setup
    draft = setup.setdefault("draft", {})
    step = setup.get("step") or "area"

    if step == "area":
        area = _extract_area(text) or (text.title() if len(text) >= 3 and not PIN_RE.search(text) else None)
        if PIN_RE.search(text):
            draft["pincodes"] = PIN_RE.findall(text)
            draft["area"] = draft.get("area") or "Selected pincodes"
            setup["step"] = "objective"
            _save_setup(conversation, setup)
            return _pack(
                f"Saved pincode(s): {', '.join(draft['pincodes'])}.\n\n"
                "Select the **objective** for this campaign.",
                step="objective",
                draft=draft,
                tool_results=[{"ok": True, "tool": "setup_step", "step": "objective"}],
            )
        if not area:
            return _pack(
                "Please select a city/district below, or type one (e.g. **Ernakulam**).",
                step="area",
                draft=draft,
            )
        suggested = lookup_area_pincodes(db, area)
        draft["area"] = area
        draft["suggested"] = suggested
        if not suggested:
            setup["step"] = "pincode"
            _save_setup(conversation, setup)
            return _pack(
                f"I couldn’t find inventory for “{area}” in demo data. "
                "Select pincodes below or type a **6-digit** code.",
                step="pincode",
                draft=draft,
            )
        setup["step"] = "pincode"
        _save_setup(conversation, setup)
        return _pack(
            f"Targeting **{area}**. Select pincodes (or **Select all**):\n\n{_format_pin_list(suggested)}",
            step="pincode",
            draft=draft,
            tool_results=[{"ok": True, "tool": "setup_step", "step": "pincode"}],
        )

    if step == "pincode":
        if re.match(r"^\s*skip\s*$", text, re.I):
            draft["pincodes"] = []
        elif ALL_PINS_RE.match(text):
            draft["pincodes"] = [p["pincode"] for p in (draft.get("suggested") or [])]
            if not draft["pincodes"]:
                return _pack(
                    "No suggested pincodes to select. Type a 6-digit pincode instead.",
                    step="pincode",
                    draft=draft,
                )
        else:
            pins = PIN_RE.findall(text)
            if not pins:
                area = _extract_area(text) or text.title()
                suggested = lookup_area_pincodes(db, area)
                if suggested:
                    draft["area"] = area
                    draft["suggested"] = suggested
                    _save_setup(conversation, setup)
                    return _pack(
                        f"Updated area to **{area}**. Select pincodes (or Select all):\n\n"
                        f"{_format_pin_list(suggested)}",
                        step="pincode",
                        draft=draft,
                    )
                return _pack(
                    "Select at least one pincode below, use **Select all**, or type a 6-digit code.",
                    step="pincode",
                    draft=draft,
                )
            draft["pincodes"] = pins

        setup["step"] = "objective"
        _save_setup(conversation, setup)
        pin_s = ", ".join(draft["pincodes"]) if draft["pincodes"] else "none (add later in editor)"
        return _pack(
            f"Pincodes saved: {pin_s}.\n\nSelect the **objective** for this ad.",
            step="objective",
            draft=draft,
            tool_results=[{"ok": True, "tool": "setup_step", "step": "objective"}],
        )

    if step == "objective":
        objective = _parse_objective(text)
        if not objective:
            return _pack(
                "Select an objective from the list below.",
                step="objective",
                draft=draft,
            )
        draft["objective"] = objective
        setup["step"] = "name"
        _save_setup(conversation, setup)
        return _pack(
            f"Objective set to **{objective.replace('_', ' ')}**.\n\n"
            "Select a campaign name, or type your own.",
            step="name",
            draft=draft,
            tool_results=[{"ok": True, "tool": "setup_step", "step": "name"}],
        )

    if step == "name":
        if re.search(r"skip|default", text, re.I):
            area = draft.get("area") or "Local"
            obj = (draft.get("objective") or "campaign").replace("_", " ")
            draft["name"] = f"{area} {obj}"[:200]
        else:
            draft["name"] = text.strip()[:200]
        setup["step"] = "language"
        _save_setup(conversation, setup)
        return _pack(
            f"Campaign name: **{draft['name']}**.\n\nSelect the **ad language**.",
            step="language",
            draft=draft,
            tool_results=[{"ok": True, "tool": "setup_step", "step": "language"}],
        )

    if step == "language":
        lang = _parse_language(text) or draft.get("language") or "en"
        if not _parse_language(text) and not re.match(r"^\s*(skip|default)\s*$", text, re.I):
            if len(text) < 20 and not any(x[1].lower() in text.lower() for x in LANGUAGES):
                return _pack(
                    "Select a language from the options below.",
                    step="language",
                    draft=draft,
                )
        draft["language"] = lang
        setup["step"] = "budget"
        _save_setup(conversation, setup)
        return _pack(
            f"Language set to **{next((l for c, l in LANGUAGES if c == lang), lang)}**.\n\n"
            "Select a **daily budget**, or type your own amount (min ₹1000).",
            step="budget",
            draft=draft,
            tool_results=[{"ok": True, "tool": "setup_step", "step": "budget"}],
        )

    if step == "budget":
        budget = _parse_budget(text)
        if budget is None:
            return _pack(
                "Select a budget option, or type a daily amount (min 1000).",
                step="budget",
                draft=draft,
            )
        draft["daily_budget"] = budget
        setup["step"] = "confirm"
        _save_setup(conversation, setup)
        return _pack(
            f"{_draft_summary(draft)}\n\nConfirm to create this **draft** campaign.",
            step="confirm",
            draft=draft,
            tool_results=[{"ok": True, "tool": "setup_step", "step": "confirm"}],
        )

    if step == "confirm":
        if CANCEL_RE.match(text):
            _save_setup(conversation, None)
            return _pack(
                "Okay — campaign setup cancelled. Say “create a new campaign” anytime to start again.",
                suggestions=["Create a new campaign", "List my campaigns"],
                tool_results=[{"ok": True, "tool": "setup_cancel"}],
            )
        if not _is_confirm(text):
            return _pack(
                "Select **Yes, create draft** to continue, or **Cancel setup**.",
                step="confirm",
                draft=draft,
            )
        result = _create_from_draft(db, user, draft, ctx)
        if not result.get("ok"):
            _save_setup(conversation, None)
            return _pack(
                f"Couldn’t create the campaign: {result.get('error')}",
                suggestions=["Create a new campaign"],
                tool_results=[{"ok": False, "tool": "create_campaign", "error": result.get("error")}],
            )
        c = result["campaign"]
        draft["campaign_id"] = c["id"]
        draft["campaign_name"] = c["name"]
        draft["campaign_href"] = c["href"]
        if c.get("status"):
            draft["campaign_status"] = c["status"]
        # Capture payable for payment step copy
        try:
            camp = campaign_service.get_campaign(db, user, UUID(c["id"]))
            if camp.budget:
                draft["total_payable"] = float(camp.budget.total_payable)
        except Exception:
            pass
        setup["step"] = "platforms"
        _save_setup(conversation, setup)
        return _pack(
            f"Created draft **{c['name']}**.\n\n"
            "Next — choose which **platforms** to advertise on "
            "(Meta, YouTube, CTV, OTT, publishers, local screens, outdoor).\n\n"
            "Select one or more below, **Select all**, or skip for now.",
            step="platforms",
            draft=draft,
            actions=_campaign_actions(c["id"]),
            tool_results=[{"ok": True, "tool": "create_campaign", "campaign": c}],
        )

    if step == "platforms":
        campaign_id = draft.get("campaign_id")
        if not campaign_id:
            _save_setup(conversation, None)
            return _pack(
                "Campaign id missing from setup. Start again with “create a new campaign”.",
                suggestions=["Create a new campaign"],
            )

        platforms = _parse_platforms(text)
        if platforms is None:
            return _pack(
                "Select at least one platform, use **Select all**, or **Skip for now**.\n\n"
                "Available: Meta, YouTube, Connected TV, OTT, Digital Publishers, "
                "Local Digital Screens, Outdoor & Transit.",
                step="platforms",
                draft=draft,
            )

        try:
            attached = _attach_platforms(db, user, UUID(str(campaign_id)), platforms)
        except ValidationAppError as exc:
            return _pack(
                f"Couldn’t save platforms: {exc}. Try again.",
                step="platforms",
                draft=draft,
                tool_results=[{"ok": False, "tool": "attach_platforms", "error": str(exc)}],
            )

        draft["platforms"] = platforms
        setup["step"] = "payment"
        _save_setup(conversation, setup)

        if attached.get("skipped") or not platforms:
            plat_msg = "No platforms selected yet — you can add them later in Omnichannel."
        else:
            labels = ", ".join(attached.get("labels") or [_platform_label(p) for p in platforms])
            plat_msg = f"Platforms saved: **{labels}**."

        amount = draft.get("total_payable")
        amount_line = f" Payable estimate: **₹{int(amount):,}**." if amount else ""
        return _pack(
            f"{plat_msg}{amount_line}\n\n"
            "How would you like to handle **payment**?",
            step="payment",
            draft=draft,
            actions=_campaign_actions(str(campaign_id)),
            tool_results=[{"ok": True, "tool": "attach_platforms", "platforms": platforms}],
        )

    if step == "payment":
        campaign_id = draft.get("campaign_id")
        if not campaign_id:
            _save_setup(conversation, None)
            return _pack(
                "Campaign id missing. Start again with “create a new campaign”.",
                suggestions=["Create a new campaign"],
            )

        lower = text.strip().lower()
        choice = None
        if lower in ("pay_now", "pay now", "pay now (mock)", "pay", "mock pay", "pay immediately"):
            choice = "pay_now"
        elif lower in ("pay_later", "pay later", "later", "skip payment", "skip"):
            choice = "pay_later"
        elif lower in (
            "open_payments",
            "open payments",
            "open payments page",
            "payments",
            "billing",
        ):
            choice = "open_payments"
        elif "pay now" in lower or lower.startswith("pay_now"):
            choice = "pay_now"
        elif "later" in lower:
            choice = "pay_later"
        elif "payment" in lower or "billing" in lower:
            choice = "open_payments"

        if not choice:
            return _pack(
                "Select **Pay now**, **Pay later**, or **Open payments page**.",
                step="payment",
                draft=draft,
            )

        actions = _campaign_actions(str(campaign_id), paid=(choice == "pay_now"))
        tool_results: list[dict[str, Any]] = []

        if choice == "pay_now":
            try:
                pay = _run_mock_payment(db, user, UUID(str(campaign_id)))
                draft["paid"] = True
                draft["campaign_status"] = (pay.get("verified") or {}).get("campaign_status") or "scheduled"
                tool_results.append({"ok": True, "tool": "mock_payment", **pay})
                pay_msg = (
                    "Mock payment **successful**. Campaign is **scheduled**.\n\n"
                    "Ready to start advertising?"
                )
            except ValidationAppError as exc:
                return _pack(
                    f"Payment failed: {exc}. Choose another option.",
                    step="payment",
                    draft=draft,
                    actions=actions,
                    tool_results=[{"ok": False, "tool": "mock_payment", "error": str(exc)}],
                )
        elif choice == "open_payments":
            draft["paid"] = False
            setup["step"] = "start"
            _save_setup(conversation, setup)
            return _pack(
                "Open the Payments page to complete checkout when you are ready.\n\n"
                "Meanwhile — do you want to **start advertising** after payment, "
                "keep the campaign scheduled, or finish later?",
                step="start",
                draft=draft,
                actions=actions,
                tool_results=[{"ok": True, "tool": "open_payments", "href": f"/payments?campaign={campaign_id}"}],
            )
        else:
            draft["paid"] = False
            tool_results.append({"ok": True, "tool": "pay_later"})
            pay_msg = (
                "Okay — payment skipped for now. You can pay anytime from **Payments**.\n\n"
                "Do you want to **start advertising** (demo path), keep it scheduled, or finish later?"
            )

        setup["step"] = "start"
        _save_setup(conversation, setup)
        return _pack(
            pay_msg,
            step="start",
            draft=draft,
            actions=actions,
            tool_results=tool_results,
        )

    if step == "start":
        campaign_id = draft.get("campaign_id")
        if not campaign_id:
            _save_setup(conversation, None)
            return _pack(
                "Campaign id missing. Start again with “create a new campaign”.",
                suggestions=["Create a new campaign"],
            )

        lower = text.strip().lower()
        choice = None
        if lower in (
            "start_now",
            "start advertising",
            "start advertising now",
            "start",
            "go live",
            "launch",
            "launch now",
        ):
            choice = "start_now"
        elif lower in (
            "keep_scheduled",
            "keep scheduled",
            "scheduled",
            "keep as scheduled",
        ):
            choice = "keep_scheduled"
        elif lower in (
            "finish_later",
            "finish later",
            "later",
            "done",
            "finish",
            "exit",
        ):
            choice = "finish_later"
        elif "start" in lower or "launch" in lower or "live" in lower:
            choice = "start_now"
        elif "schedul" in lower:
            choice = "keep_scheduled"
        elif "finish" in lower or "later" in lower:
            choice = "finish_later"

        if not choice:
            return _pack(
                "Select **Start advertising now**, **Keep scheduled**, or **Finish later**.",
                step="start",
                draft=draft,
            )

        name = draft.get("campaign_name") or "your campaign"
        platforms = draft.get("platforms") or []
        actions = _campaign_actions(str(campaign_id), paid=bool(draft.get("paid")), live=(choice == "start_now"))

        if choice == "start_now":
            try:
                started = _start_advertising(db, user, UUID(str(campaign_id)), platforms)
            except ValidationAppError as exc:
                return _pack(
                    f"Couldn’t start advertising: {exc}. Try again or open the campaign page.",
                    step="start",
                    draft=draft,
                    actions=actions,
                    tool_results=[{"ok": False, "tool": "start_advertising", "error": str(exc)}],
                )
            _save_setup(conversation, None)
            plat_s = ", ".join(_platform_label(p) for p in platforms) if platforms else "selected channels"
            return _pack(
                f"**{name}** is now live (simulated) on **{plat_s}**.\n\n"
                "You can pause, edit creatives, or review performance anytime.",
                actions=actions,
                suggestions=["List my campaigns", "How is my spend?", "Create another campaign"],
                tool_results=[{"ok": True, "tool": "start_advertising", **started}],
            )

        _save_setup(conversation, None)
        if choice == "keep_scheduled":
            return _pack(
                f"**{name}** will stay scheduled. Start delivery later from the campaign page "
                "or Omnichannel control.",
                actions=actions,
                suggestions=["List my campaigns", "Open payments", "Create another campaign"],
                tool_results=[{"ok": True, "tool": "keep_scheduled", "campaign_id": campaign_id}],
            )

        return _pack(
            f"Setup complete for **{name}**. Open the campaign when you are ready to pay or go live.",
            actions=actions,
            suggestions=["List my campaigns", "Generate creative", "Create another campaign"],
            tool_results=[{"ok": True, "tool": "finish_later", "campaign_id": campaign_id}],
        )

    # Unknown step — reset
    _save_setup(conversation, None)
    return None
