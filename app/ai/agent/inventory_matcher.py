"""Multi-stage inventory matching: hard filters → geo → suitability scoring."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.ai.agent.requirements import get_value
from app.models.channels import LocalInventoryListing
from app.models.inventory import AdInventory, PincodeInventory
from app.services.local_inventory_service import marketplace_listings

# Configurable weights (example defaults from master spec)
WEIGHTS = {
    "geographic": 0.25,
    "audience": 0.20,
    "budget_efficiency": 0.20,
    "reach": 0.15,
    "vendor_reliability": 0.10,
    "objective_alignment": 0.10,
}

AREA_PINCODE_HINTS = {
    "kakkanad": ["682030", "682024"],
    "ernakulam": ["682001", "682016", "682020", "682030"],
    "kochi": ["682001", "682016", "682020", "682030", "682024"],
    "edappally": ["682024"],
}


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _location_terms(req: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    loc = get_value(req, "business_location")
    if loc:
        terms.append(str(loc))
    for item in get_value(req, "target_geographic_locations") or []:
        if item and str(item) not in terms:
            terms.append(str(item))
    return terms


def _target_pincodes(db: Session, req: dict[str, Any]) -> list[str]:
    pins = list(get_value(req, "target_postal_codes") or [])
    for term in _location_terms(req):
        key = _norm(term)
        for hint_pin in AREA_PINCODE_HINTS.get(key, []):
            if hint_pin not in pins:
                pins.append(hint_pin)
        like = f"%{term}%"
        rows = (
            db.query(PincodeInventory)
            .filter(
                PincodeInventory.is_available.is_(True),
                (
                    PincodeInventory.city.ilike(like)
                    | PincodeInventory.district.ilike(like)
                    | PincodeInventory.pincode.ilike(like)
                ),
            )
            .limit(12)
            .all()
        )
        for row in rows:
            if row.pincode not in pins:
                pins.append(row.pincode)
    return pins


def _medium_match(preferred: list[str], inventory_type: str) -> float:
    t = _norm(inventory_type)
    if not preferred:
        return 0.6  # neutral when unspecified
    mapping = {
        "outdoor": ["led_outdoor", "outdoor", "billboard", "transit"],
        "local_screens": ["mall_screen", "retail_screen", "local_screens", "led"],
        "ctv": ["connected_tv", "ctv"],
        "ott": ["ott"],
        "youtube": ["youtube"],
        "meta": ["meta", "social"],
    }
    for pref in preferred:
        keys = mapping.get(pref, [pref])
        if any(k in t for k in keys):
            return 1.0
    return 0.15


def _objective_alignment(objective: Optional[str], inventory_type: str) -> float:
    t = _norm(inventory_type)
    obj = _norm(objective) or "increase_store_visits"
    if obj in ("increase_store_visits", "store_visits", "sales"):
        if any(x in t for x in ("local", "mall", "retail", "outdoor", "led")):
            return 1.0
        if "connected_tv" in t or "ctv" in t:
            return 0.55
        return 0.4
    if obj in ("brand_awareness", "reach"):
        if any(x in t for x in ("ctv", "connected", "outdoor", "ott")):
            return 1.0
        return 0.6
    if obj in ("lead_generation", "website_traffic"):
        if "retail" in t or "mall" in t:
            return 0.75
        return 0.5
    return 0.55


def _score_item(
    *,
    req: dict[str, Any],
    geo_score: float,
    inventory_type: str,
    price: float,
    impressions: Optional[int],
    vendor_score: float,
    budget: float,
    duration_days: int,
) -> tuple[float, dict[str, float], list[str]]:
    preferred = get_value(req, "preferred_mediums") or []
    objective = get_value(req, "advertising_objective")
    audience = get_value(req, "target_audience")

    audience_score = 0.7
    if audience and any(x in _norm(audience) for x in ("professional", "nearby", "local", "work")):
        if any(x in _norm(inventory_type) for x in ("local", "mall", "retail", "outdoor", "led")):
            audience_score = 0.95
        else:
            audience_score = 0.55

    # Budget efficiency: can this fit in budget for the campaign duration?
    # Local listings often priced as slot/day-ish demo values — treat price as campaign-period cost estimate.
    period_cost = float(price)
    if duration_days and duration_days > 14 and price < budget / 4:
        # Likely daily-ish; scale lightly without inventing exact calendars
        period_cost = min(budget, price * max(1, duration_days / 7))
    if budget <= 0:
        budget_eff = 0.0
    elif period_cost <= budget:
        budget_eff = max(0.35, 1.0 - (period_cost / budget) * 0.5)
    else:
        budget_eff = max(0.0, 0.25 - min(1.0, (period_cost - budget) / budget) * 0.25)

    reach_score = 0.4
    reach_note_missing = impressions is None
    if impressions is not None and impressions > 0:
        # Normalize roughly against 100k impressions
        reach_score = min(1.0, impressions / 100000)

    medium_score = _medium_match(list(preferred), inventory_type)
    # Fold medium preference into geographic/objective buckets via objective alignment boost
    obj_score = _objective_alignment(objective, inventory_type)
    if preferred:
        obj_score = (obj_score * 0.6) + (medium_score * 0.4)

    components = {
        "geographic": geo_score,
        "audience": audience_score,
        "budget_efficiency": budget_eff,
        "reach": reach_score if not reach_note_missing else 0.0,
        "vendor_reliability": vendor_score,
        "objective_alignment": obj_score,
    }

    # Renormalize weights when reach is missing
    weights = dict(WEIGHTS)
    if reach_note_missing:
        leftover = weights.pop("reach")
        for k in list(weights):
            weights[k] += leftover / len(weights)

    score = sum(components[k] * weights[k] for k in weights)
    reasons: list[str] = []
    if geo_score >= 0.8:
        reasons.append("Strong geographic match to your target area")
    elif geo_score >= 0.5:
        reasons.append("Partial geographic overlap with your target area")
    if medium_score >= 0.9:
        reasons.append("Matches your preferred advertising medium")
    if budget_eff >= 0.6:
        reasons.append("Fits within the stated campaign budget")
    elif period_cost > budget:
        reasons.append("May exceed budget — verify pricing before booking")
    if reach_note_missing:
        reasons.append("Estimated reach not available for this listing")
    elif impressions:
        reasons.append(f"Listed estimated impressions: {int(impressions):,} (estimate)")
    return round(score * 100, 1), components, reasons


def search_and_rank(db: Session, req: dict[str, Any], *, limit: int = 12) -> dict[str, Any]:
    """Stage 1–4 matching against registered Bada inventory (demo + approved local)."""
    budget = float(get_value(req, "budget_amount") or 0)
    duration = int(get_value(req, "campaign_duration_days") or 30)
    preferred = list(get_value(req, "preferred_mediums") or [])
    pins = _target_pincodes(db, req)
    terms = _location_terms(req)

    hard_rejected: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    # Local marketplace listings (vendor inventory)
    local_rows = marketplace_listings(db)
    for row in local_rows:
        inv_type = row.get("inventory_type") or ""
        pin = str(row.get("pincode") or "")
        city = _norm(row.get("city"))
        district = _norm(row.get("district"))
        price = float(row.get("price") or 0)

        # Hard: preferred medium when explicitly required
        if preferred and _medium_match(preferred, inv_type) < 0.5:
            # Soft-skip only if user insisted on mediums — still allow near-miss outdoor↔led
            if not any(p in ("outdoor", "local_screens") for p in preferred):
                hard_rejected.append(
                    {
                        "id": row.get("id"),
                        "title": row.get("title"),
                        "reason": "Medium does not match preferred advertising formats",
                    }
                )
                continue

        geo = 0.0
        if pin and pin in pins:
            geo = 1.0
        elif any(t in city or t in district for t in (_norm(x) for x in terms)):
            geo = 0.85
        elif terms and (city or district):
            # Same district-ish Kerala Kochi cluster
            if any(x in city or x in district for x in ("kochi", "ernakulam")) and any(
                _norm(t) in ("kakkanad", "kochi", "ernakulam", "edappally") for t in terms
            ):
                geo = 0.7
            else:
                geo = 0.2
        else:
            geo = 0.1

        if geo < 0.45:
            hard_rejected.append(
                {
                    "id": row.get("id"),
                    "title": row.get("title"),
                    "reason": "Outside target geography",
                }
            )
            continue

        # Hard budget: reject clearly unaffordable single placements when min price >> budget
        if budget > 0 and price > budget * 1.5:
            hard_rejected.append(
                {
                    "id": row.get("id"),
                    "title": row.get("title"),
                    "reason": "Base price exceeds budget constraints",
                }
            )
            continue

        score, components, reasons = _score_item(
            req=req,
            geo_score=geo,
            inventory_type=inv_type,
            price=price,
            impressions=row.get("estimated_impressions"),
            vendor_score=0.75,  # approved local demo vendor
            budget=budget,
            duration_days=duration,
        )
        candidates.append(
            {
                "source": "verified_bada_inventory",
                "classification": "Verified Bada Inventory",
                "inventory_id": row.get("id"),
                "vendor_name": row.get("provider_name") or "Local provider",
                "title": row.get("title"),
                "medium": inv_type,
                "city": row.get("city"),
                "pincode": pin,
                "price": price,
                "pricing_model": row.get("pricing_model"),
                "estimated_impressions": row.get("estimated_impressions"),
                "is_estimate": bool(row.get("is_estimate", True)),
                "availability": row.get("status") or "approved",
                "suitability_score": score,
                "score_components": components,
                "reasons": reasons,
                "limitations": [
                    "Demo/approved marketplace listing — confirm live availability before booking",
                    "Performance metrics are estimates unless verified delivery is connected",
                ],
            }
        )

    # CTV / AdInventory by pincode
    if pins:
        ad_rows = (
            db.query(AdInventory)
            .filter(AdInventory.is_available.is_(True), AdInventory.pincode.in_(pins))
            .limit(20)
            .all()
        )
    else:
        ad_rows = []
    for ad in ad_rows:
        if preferred and _medium_match(preferred, ad.inventory_type) < 0.5:
            # Still include CTV as alternative unless user forbade it — mark lower later
            pass
        geo = 1.0 if ad.pincode in pins else 0.5
        # Approximate period cost from CPM * rough buy — do not invent ROI; use inventory CPM as estimate only
        cpm = float(ad.cpm or 0)
        impressions = int(ad.available_impressions or 0)
        # Suggest a budget slice cost estimate: buy min(available, budget/cpm*1000)
        est_cost = min(budget, (impressions / 1000.0) * cpm) if budget and cpm else cpm * 50
        score, components, reasons = _score_item(
            req=req,
            geo_score=geo,
            inventory_type=ad.inventory_type,
            price=est_cost or cpm,
            impressions=impressions or None,
            vendor_score=0.65 if ad.is_simulated else 0.85,
            budget=budget,
            duration_days=duration,
        )
        candidates.append(
            {
                "source": "verified_bada_inventory",
                "classification": "Verified Bada Inventory",
                "inventory_id": str(ad.id),
                "vendor_name": "Demo CTV Network India" if ad.is_simulated else "Publisher partner",
                "title": ad.name,
                "medium": ad.inventory_type,
                "city": ad.city,
                "pincode": ad.pincode,
                "price": round(est_cost, 2),
                "pricing_model": "cpm",
                "cpm": cpm,
                "estimated_impressions": impressions,
                "is_estimate": True,
                "is_simulated": bool(ad.is_simulated),
                "availability": "available" if ad.is_available else "unavailable",
                "suitability_score": score,
                "score_components": components,
                "reasons": reasons,
                "limitations": [
                    "CPM and impressions are inventory estimates",
                    "Simulated demo inventory" if ad.is_simulated else "Confirm publisher availability",
                ],
            }
        )

    candidates.sort(key=lambda x: x["suitability_score"], reverse=True)
    ranked = candidates[:limit]

    return {
        "ok": True,
        "tool": "search_inventory",
        "matched_count": len(ranked),
        "rejected_count": len(hard_rejected),
        "target_pincodes": pins,
        "items": ranked,
        "hard_rejected_sample": hard_rejected[:5],
        "data_quality": {
            "label": "Demo / registered inventory — not live vendor confirmation",
            "is_simulated": True,
        },
    }


def discover_external_opportunities(req: dict[str, Any]) -> dict[str, Any]:
    """
    External discovery stub: does NOT invent prices or availability.
    Creates structured leads for admin vendor acquisition.
    """
    location = get_value(req, "business_location") or (
        (get_value(req, "target_geographic_locations") or ["unknown"])[0]
    )
    mediums = get_value(req, "preferred_mediums") or ["outdoor", "local_screens"]
    category = get_value(req, "business_category") or "local_business"
    opportunities = []
    for medium in mediums[:3]:
        opportunities.append(
            {
                "classification": "Externally Discovered Opportunity",
                "status": "Pending Vendor Verification",
                "vendor_name": None,
                "medium": medium,
                "location": location,
                "price": None,
                "availability": None,
                "notes": (
                    f"No confirmed Bada inventory matched well for {category} in {location} "
                    f"({medium}). Recommend vendor enquiry — pricing/availability unverified."
                ),
                "source": "external_discovery_stub",
                "action": "quotation_enquiry",
            }
        )
    return {
        "ok": True,
        "tool": "discover_external",
        "opportunities": opportunities,
        "vendor_leads": [
            {
                "category": medium,
                "location": location,
                "demand_trigger": category,
                "status": "pending_review",
            }
            for medium in mediums[:3]
        ],
        "disclaimer": "External opportunities are unverified. Prices and availability are not invented.",
    }


def optimize_budget_plans(inventory_result: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    """Generate Plan A/B/C from real ranked inventory — not fixed packages."""
    items = list(inventory_result.get("items") or [])
    budget = float(get_value(req, "budget_amount") or 0)
    duration = int(get_value(req, "campaign_duration_days") or 30)

    def pack(selected: list[dict[str, Any]], name: str, focus: str) -> dict[str, Any]:
        total = 0.0
        lines = []
        for item in selected:
            price = float(item.get("price") or 0)
            if budget and total + price > budget * 1.05:
                continue
            total += price
            lines.append(
                {
                    "title": item.get("title"),
                    "vendor_name": item.get("vendor_name"),
                    "medium": item.get("medium"),
                    "pincode": item.get("pincode"),
                    "allocated_budget": price,
                    "suitability_score": item.get("suitability_score"),
                    "classification": item.get("classification"),
                    "is_estimate": item.get("is_estimate", True),
                }
            )
        return {
            "name": name,
            "focus": focus,
            "duration_days": duration,
            "total_allocated": round(total, 2),
            "remaining_budget": round(max(0.0, budget - total), 2),
            "items": lines,
            "assumptions": [
                "Allocations use listed/estimated prices from inventory records",
                "Audience overlap not double-counted as additive reach",
                "Not a guaranteed ROI forecast",
            ],
        }

    by_price = sorted(items, key=lambda x: float(x.get("price") or 0))
    by_score = sorted(items, key=lambda x: x.get("suitability_score") or 0, reverse=True)
    by_reach = sorted(
        items,
        key=lambda x: (x.get("estimated_impressions") or 0, x.get("suitability_score") or 0),
        reverse=True,
    )

    plans = [
        pack(by_price[:3], "Plan A — Budget Efficient", "Prioritise cost fit while meeting core location needs"),
        pack(by_score[:3], "Plan B — Balanced Strategy", "Balance suitability score, relevance and cost"),
        pack(by_reach[:3], "Plan C — Maximum Relevant Reach", "Prioritise estimated impressions within budget"),
    ]
    return {
        "ok": True,
        "tool": "optimize_budget",
        "budget": budget,
        "plans": plans,
        "data_quality": {"label": "Plans generated from registered inventory only", "is_estimate": True},
    }


def build_proposal(req: dict[str, Any], inventory: dict[str, Any], plans: dict[str, Any]) -> dict[str, Any]:
    primary = (plans.get("plans") or [None])[1 if len(plans.get("plans") or []) > 1 else 0]
    return {
        "ok": True,
        "tool": "generate_proposal",
        "proposal": {
            "business_overview": {
                "category": get_value(req, "business_category"),
                "location": get_value(req, "business_location"),
                "description": get_value(req, "business_description"),
            },
            "objective": get_value(req, "advertising_objective") or "increase_store_visits",
            "target_audience": get_value(req, "target_audience"),
            "target_locations": get_value(req, "target_geographic_locations"),
            "target_postal_codes": inventory.get("target_pincodes") or get_value(req, "target_postal_codes"),
            "recommended_strategy": (
                "Focus geographically near the business for local footfall, "
                "compare outdoor/local screens against CTV only where budget allows."
            ),
            "mediums": get_value(req, "preferred_mediums"),
            "inventory_matches": (inventory.get("items") or [])[:5],
            "duration_days": get_value(req, "campaign_duration_days"),
            "budget": get_value(req, "budget_amount"),
            "plans": plans.get("plans") or [],
            "recommended_plan": primary,
            "risks_and_assumptions": [
                "No guaranteed ROI without conversion attribution data",
                "Inventory availability must be re-confirmed at booking",
                "External opportunities (if any) are unverified until vendor responds",
            ],
            "next_steps": [
                "Review the recommended plan",
                "Adjust budget or locations if needed",
                "Approve to proceed toward booking",
            ],
        },
    }
