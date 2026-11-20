"""Executable tools the Bada Agent can call on behalf of the user."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.agent.prompts import OBJECTIVE_ALIASES, VALID_OBJECTIVES
from app.core.exceptions import ValidationAppError
from app.models.user import User
from app.models.inventory import PincodeInventory
from app.schemas.campaign import (
    CampaignAudienceIn,
    CampaignBudgetIn,
    CampaignCreate,
    CampaignLocationIn,
    CampaignScheduleIn,
)
from app.services import campaign_service
from app.services.analytics_service import get_dashboard_metrics
from app.services.business_service import list_businesses_for_user, user_can_access_business

PAGE_PATHS = {
    "dashboard": "/dashboard",
    "campaigns": "/campaigns",
    "campaigns_new": "/campaigns/new",
    "omnichannel": "/campaigns/omnichannel/new",
    "studio": "/studio",
    "creatives": "/creatives",
    "marketplace": "/marketplace",
    "leads": "/leads",
    "reports": "/reports",
    "billing": "/billing",
    "payments": "/payments",
    "integrations": "/integrations",
    "settings": "/settings",
    "assistant": "/assistant",
}


def build_account_context(db: Session, user: User, business_id: Optional[UUID] = None) -> dict[str, Any]:
    businesses = list_businesses_for_user(db, user)
    metrics = get_dashboard_metrics(db, user, business_id=business_id)
    campaigns = campaign_service.list_campaigns(db, user, business_id=business_id)[:12]

    return {
        "user": {
            "name": user.full_name,
            "email": user.email,
        },
        "businesses": [
            {
                "id": str(b.id),
                "name": b.name,
                "category": b.category,
                "city": b.city,
                "objective": b.advertising_objective,
                "pincode": b.pincode,
            }
            for b in businesses
        ],
        "metrics": {
            "totals": metrics.get("totals", {}),
            "data_quality": metrics.get("data_quality", {}),
            "top_pincodes": (metrics.get("top_pincodes") or [])[:5],
            "recent_campaigns": (metrics.get("recent_campaigns") or [])[:5],
        },
        "campaigns": [
            {
                "id": str(c.id),
                "name": c.name,
                "status": c.status,
                "objective": c.objective,
                "business_id": str(c.business_id),
            }
            for c in campaigns
        ],
        "pages": PAGE_PATHS,
    }


def context_as_text(ctx: dict[str, Any]) -> str:
    lines: list[str] = []
    user = ctx.get("user") or {}
    lines.append(f"User: {user.get('name')} <{user.get('email')}>")

    businesses = ctx.get("businesses") or []
    if not businesses:
        lines.append("Businesses: (none — user must complete onboarding)")
    else:
        lines.append("Businesses:")
        for b in businesses:
            lines.append(
                f"  - {b['name']} id={b['id']} category={b.get('category')} "
                f"city={b.get('city')} default_objective={b.get('objective')}"
            )

    totals = (ctx.get("metrics") or {}).get("totals") or {}
    dq = (ctx.get("metrics") or {}).get("data_quality") or {}
    lines.append(
        "Metrics: "
        f"campaigns={totals.get('campaigns', 0)}, "
        f"active={totals.get('active_campaigns', 0)}, "
        f"spend=₹{totals.get('spend', 0)}, "
        f"impressions={totals.get('impressions', 0)}, "
        f"qr_scans={totals.get('qr_scans', 0)}, "
        f"whatsapp={totals.get('whatsapp_inquiries', 0)}, "
        f"leads={totals.get('leads', 0)}, "
        f"simulated={dq.get('is_simulated', False)}"
    )

    top = (ctx.get("metrics") or {}).get("top_pincodes") or []
    if top:
        lines.append(
            "Top pincodes: "
            + ", ".join(f"{p.get('pincode')}({p.get('leads', 0)} leads)" for p in top)
        )

    campaigns = ctx.get("campaigns") or []
    if campaigns:
        lines.append("Recent campaigns:")
        for c in campaigns:
            lines.append(f"  - {c['name']} [{c['status']}] id={c['id']} objective={c['objective']}")
    else:
        lines.append("Recent campaigns: (none)")

    lines.append("App paths: " + ", ".join(f"{k}={v}" for k, v in PAGE_PATHS.items()))
    return "\n".join(lines)


def _normalize_objective(raw: Optional[str], fallback: str = "brand_awareness") -> str:
    if not raw:
        return fallback
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if key in VALID_OBJECTIVES:
        return "increase_store_visits" if key == "store_visits" else key
    for alias, mapped in OBJECTIVE_ALIASES.items():
        if alias in key:
            return mapped
    return fallback


def _resolve_business_id(
    db: Session,
    user: User,
    ctx: dict[str, Any],
    requested: Optional[str],
    preferred: Optional[UUID],
) -> UUID:
    businesses = ctx.get("businesses") or []
    if not businesses:
        raise ValidationAppError("No business found. Complete onboarding before creating a campaign.")

    if requested:
        try:
            bid = UUID(str(requested))
            user_can_access_business(db, user, bid)
            return bid
        except Exception as exc:
            raise ValidationAppError("Invalid business_id") from exc

    if preferred:
        return preferred

    return UUID(businesses[0]["id"])


def tool_get_account_summary(db: Session, user: User, args: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    business_id = kwargs.get("business_id")
    metrics = get_dashboard_metrics(db, user, business_id=business_id)
    totals = metrics.get("totals") or {}
    dq = metrics.get("data_quality") or {}
    return {
        "ok": True,
        "tool": "get_account_summary",
        "totals": totals,
        "data_quality": dq,
        "top_pincodes": (metrics.get("top_pincodes") or [])[:5],
        "summary_lines": [
            f"Total campaigns: {totals.get('campaigns', 0)}",
            f"Active campaigns: {totals.get('active_campaigns', 0)}",
            f"Total spend: ₹{totals.get('spend', 0)}",
            f"Impressions ({'simulated' if dq.get('is_simulated') else 'real'}): {totals.get('impressions', 0)}",
            f"QR scans: {totals.get('qr_scans', 0)}",
            f"WhatsApp inquiries: {totals.get('whatsapp_inquiries', 0)}",
            f"Leads: {totals.get('leads', 0)}",
        ],
    }


def tool_list_campaigns(db: Session, user: User, args: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    business_id = kwargs.get("business_id")
    status = args.get("status")
    campaigns = campaign_service.list_campaigns(db, user, business_id=business_id, status=status)
    items = [
        {
            "id": str(c.id),
            "name": c.name,
            "status": c.status,
            "objective": c.objective,
            "href": f"/campaigns/{c.id}",
        }
        for c in campaigns[:20]
    ]
    return {"ok": True, "tool": "list_campaigns", "count": len(items), "campaigns": items}


def tool_create_campaign(
    db: Session,
    user: User,
    args: dict[str, Any],
    *,
    ctx: dict[str, Any],
    business_id: Optional[UUID] = None,
    **_: Any,
) -> dict[str, Any]:
    businesses = ctx.get("businesses") or []
    default_objective = (businesses[0].get("objective") if businesses else None) or "brand_awareness"

    bid = _resolve_business_id(db, user, ctx, args.get("business_id"), business_id)
    name = (args.get("name") or "").strip() or f"New campaign {date.today().isoformat()}"
    objective = _normalize_objective(args.get("objective"), fallback=_normalize_objective(default_objective))
    language = (args.get("language") or "en").strip()[:10] or "en"
    duration = int(args.get("video_duration") or 30)
    if duration not in (15, 30, 60):
        duration = 30

    description = args.get("description")
    brief = args.get("brief_text") or description

    # Optional light schedule/budget so the draft is usable in the wizard
    start = date.today() + timedelta(days=3)
    end = start + timedelta(days=14)
    daily = float(args.get("daily_budget") or 1500)
    total = float(args.get("total_budget") or daily * 14)

    locations: list[CampaignLocationIn] = []
    for pin in args.get("pincodes") or []:
        pin_s = str(pin).strip()
        if len(pin_s) != 6 or not pin_s.isdigit():
            continue
        row = db.query(PincodeInventory).filter(PincodeInventory.pincode == pin_s).first()
        locations.append(
            CampaignLocationIn(
                pincode=pin_s,
                city=row.city if row else None,
                state=row.state if row else None,
                district=row.district if row else None,
            )
        )

    payload = CampaignCreate(
        business_id=bid,
        name=name[:200],
        objective=objective,
        description=description,
        language=language,
        video_duration=duration,
        brief_text=brief,
        locations=locations,
        audience=CampaignAudienceIn(languages=[language]),
        budget=CampaignBudgetIn(daily_budget=max(daily, 1000), total_budget=max(total, 1000), duration_days=14),
        schedule=CampaignScheduleIn(start_date=start, end_date=end),
    )
    created = campaign_service.create_campaign(db, user, payload)
    return {
        "ok": True,
        "tool": "create_campaign",
        "campaign": {
            "id": str(created.id),
            "name": created.name,
            "status": created.status,
            "objective": created.objective,
            "business_id": str(created.business_id),
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


def tool_open_page(_db: Session, _user: User, args: dict[str, Any], **_: Any) -> dict[str, Any]:
    key = (args.get("page") or args.get("path") or "").strip().lower()
    href = PAGE_PATHS.get(key) or args.get("href")
    if not href or not str(href).startswith("/"):
        return {"ok": False, "tool": "open_page", "error": "Unknown page"}
    label = args.get("label") or key.replace("_", " ").title() or "Open"
    return {
        "ok": True,
        "tool": "open_page",
        "href": href,
        "actions": [{"type": "link", "label": label, "href": href}],
    }


def tool_help(_db: Session, _user: User, _args: dict[str, Any], **_: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": "help",
        "capabilities": [
            "Guided campaign setup (area → pincode → objective → budget)",
            "Create a draft campaign with target pincodes",
            "List your campaigns",
            "Summarise spend, impressions, QR scans, leads",
            "Open Studio, Marketplace, Reports, Omnichannel planner",
            "Explain next steps to go live",
        ],
    }


TOOL_HANDLERS = {
    "get_account_summary": tool_get_account_summary,
    "list_campaigns": tool_list_campaigns,
    "create_campaign": tool_create_campaign,
    "open_page": tool_open_page,
    "help": tool_help,
}


def execute_tools(
    db: Session,
    user: User,
    tools: list[dict[str, Any]],
    *,
    ctx: dict[str, Any],
    business_id: Optional[UUID] = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for call in tools or []:
        name = (call.get("name") or "").strip()
        args = call.get("args") or {}
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            results.append({"ok": False, "tool": name or "unknown", "error": f"Unknown tool: {name}"})
            continue
        try:
            results.append(
                handler(db, user, args, ctx=ctx, business_id=business_id)
            )
        except Exception as exc:  # noqa: BLE001 — surface tool errors in agent reply
            results.append({"ok": False, "tool": name, "error": str(exc)})
    return results


def collect_actions(tool_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in tool_results:
        for action in result.get("actions") or []:
            href = action.get("href")
            if not href or href in seen:
                continue
            seen.add(href)
            actions.append(
                {
                    "type": action.get("type") or "link",
                    "label": action.get("label") or "Open",
                    "href": href,
                }
            )
        campaign = result.get("campaign")
        if campaign and campaign.get("href") and campaign["href"] not in seen:
            seen.add(campaign["href"])
            actions.append(
                {"type": "link", "label": f"Open {campaign.get('name', 'campaign')}", "href": campaign["href"]}
            )
    return actions


_CREATE_RE = re.compile(
    r"\b(create|start|new|launch|make|set\s*up|setup)\b.*\b(campa\w*|ad|ads|advert)\b|"
    r"\b(campa\w*|ad)\b.*\b(create|new|start)\b",
    re.I,
)
_LIST_RE = re.compile(
    r"\b(list|show|my)\b.*\b(campa\w*)\b|\b(campa\w*)\b.*\b(list|show)\b",
    re.I,
)
_METRICS_RE = re.compile(
    r"\b(spend|budget|impression|reach|lead|qr|whatsapp|performance|metric|summary|how\s+am\s+i|"
    r"how\s+is|dashboard|analytics)\b",
    re.I,
)
_STUDIO_RE = re.compile(r"\b(studio|creative|video|generate\s+ad|ad\s+creative)\b", re.I)
_OMNI_RE = re.compile(r"\b(omni|omnichannel|multi.?channel|youtube|meta|ctv)\b", re.I)
_HELP_RE = re.compile(r"\b(help|what\s+can\s+you|capabilities|how\s+do\s+you)\b", re.I)


def rule_based_plan(message: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """Deterministic planner used when Gemini is unavailable or returns unusable JSON."""
    text = message.strip()
    tools: list[dict[str, Any]] = []

    if _HELP_RE.search(text) and not _CREATE_RE.search(text):
        tools.append({"name": "help", "args": {}})
        return {
            "reply": (
                "I can create draft campaigns, list your campaigns, summarise real account metrics, "
                "and open Studio, Marketplace, Reports, or the Omnichannel planner. "
                "Try: “create a new campaign for store visits”."
            ),
            "tools": tools,
        }

    if _CREATE_RE.search(text):
        businesses = ctx.get("businesses") or []
        if not businesses:
            return {
                "reply": (
                    "You don’t have a business yet. Finish onboarding first, then I can create a campaign draft for you."
                ),
                "tools": [{"name": "open_page", "args": {"page": "settings", "label": "Go to settings"}}],
            }

        # Infer name / objective from free text
        name = None
        m = re.search(r"(?:named|called|for)\s+[\"']?([^\"'\n,.]+)", text, re.I)
        if m:
            name = m.group(1).strip()[:200]
        if not name:
            name = f"New campaign {date.today().isoformat()}"

        objective = None
        for alias, mapped in OBJECTIVE_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", text, re.I):
                objective = mapped
                break
        if not objective:
            objective = businesses[0].get("objective") or "brand_awareness"

        lang = "en"
        if re.search(r"\bmalayalam\b", text, re.I):
            lang = "ml"
        elif re.search(r"\btamil\b", text, re.I):
            lang = "ta"
        elif re.search(r"\bhindi\b", text, re.I):
            lang = "hi"

        tools.append(
            {
                "name": "create_campaign",
                "args": {
                    "business_id": businesses[0]["id"],
                    "name": name,
                    "objective": objective,
                    "language": lang,
                    "brief_text": text,
                },
            }
        )
        return {
            "reply": f"Creating a draft campaign “{name}” for {businesses[0]['name']}…",
            "tools": tools,
        }

    if _LIST_RE.search(text):
        tools.append({"name": "list_campaigns", "args": {}})
        return {"reply": "Here are your campaigns.", "tools": tools}

    if _STUDIO_RE.search(text):
        tools.append({"name": "open_page", "args": {"page": "studio", "label": "Open AI Studio"}})
        return {
            "reply": "AI Studio is where you generate and edit creatives for a campaign. Open it here:",
            "tools": tools,
        }

    if _OMNI_RE.search(text):
        tools.append({"name": "open_page", "args": {"page": "omnichannel", "label": "Omnichannel planner"}})
        return {
            "reply": "Use the Omnichannel planner to allocate budget across CTV, YouTube, Meta, and local screens.",
            "tools": tools,
        }

    if _METRICS_RE.search(text) or re.search(r"\bpincode\b", text, re.I):
        tools.append({"name": "get_account_summary", "args": {}})
        return {
            "reply": "Here’s what I can see from your Bada account (I only use real stored metrics).",
            "tools": tools,
        }

    tools.append({"name": "help", "args": {}})
    tools.append({"name": "get_account_summary", "args": {}})
    return {
        "reply": (
            "I can create campaigns, list them, and report live account metrics. "
            "Say “create a new campaign” or ask about spend, leads, or QR scans."
        ),
        "tools": tools,
    }
