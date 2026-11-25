"""Structured customer requirement model with field provenance."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Optional


class FieldStatus(str, Enum):
    UNKNOWN = "unknown"
    INFERRED = "inferred"
    EXPLICIT = "explicit"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"


REQUIREMENT_FIELDS = (
    "customer_id",
    "business_name",
    "business_category",
    "business_description",
    "business_location",
    "business_postal_code",
    "advertising_objective",
    "target_audience",
    "target_age_group",
    "target_geographic_locations",
    "target_postal_codes",
    "preferred_mediums",
    "budget_amount",
    "budget_currency",
    "campaign_duration_days",
    "preferred_start_date",
    "campaign_end_date",
    "preferred_time_slots",
    "creative_availability",
    "creative_requirements",
    "special_restrictions",
    "customer_preferences",
    "required_approvals",
    "radius_km",
)

# Minimum fields to run inventory search for local / OOH style campaigns
CRITICAL_FOR_SEARCH = (
    "business_location",  # or target_geographic_locations / postal codes
    "budget_amount",
)

QUESTION_PRIORITY = (
    "business_location",
    "budget_amount",
    "advertising_objective",
    "target_audience",
    "preferred_mediums",
    "campaign_duration_days",
    "business_category",
)


def empty_requirements() -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for name in REQUIREMENT_FIELDS:
        fields[name] = {"value": None, "status": FieldStatus.UNKNOWN.value}
    fields["budget_currency"] = {"value": "INR", "status": FieldStatus.INFERRED.value}
    fields["campaign_duration_days"] = {"value": 30, "status": FieldStatus.INFERRED.value}
    return {
        "fields": fields,
        "completeness_status": "incomplete",
        "current_campaign_state": "DISCOVERY",
        "last_plan": None,
        "last_inventory": None,
        "last_external": None,
        "pending_question": None,
    }


def get_value(req: dict[str, Any], field: str) -> Any:
    entry = (req.get("fields") or {}).get(field) or {}
    return entry.get("value")


def get_status(req: dict[str, Any], field: str) -> str:
    entry = (req.get("fields") or {}).get(field) or {}
    return entry.get("status") or FieldStatus.UNKNOWN.value


def set_field(
    req: dict[str, Any],
    field: str,
    value: Any,
    status: FieldStatus,
    *,
    overwrite_weaker: bool = True,
) -> bool:
    """Set a field. Stronger statuses win unless overwrite_weaker is False for equal."""
    if field not in REQUIREMENT_FIELDS:
        return False
    fields = req.setdefault("fields", {})
    current = fields.get(field) or {"value": None, "status": FieldStatus.UNKNOWN.value}
    rank = {
        FieldStatus.UNKNOWN.value: 0,
        FieldStatus.INFERRED.value: 1,
        FieldStatus.EXPLICIT.value: 2,
        FieldStatus.CONFIRMED.value: 3,
        FieldStatus.MODIFIED.value: 4,
    }
    new_status = status.value if isinstance(status, FieldStatus) else str(status)
    if value is None:
        return False
    if current.get("value") == value and current.get("status") == new_status:
        return False
    cur_rank = rank.get(current.get("status") or FieldStatus.UNKNOWN.value, 0)
    new_rank = rank.get(new_status, 0)
    if not overwrite_weaker and new_rank < cur_rank:
        return False
    # Explicit/modified always apply; inferred does not overwrite explicit/confirmed
    if new_status == FieldStatus.INFERRED.value and cur_rank >= rank[FieldStatus.EXPLICIT.value]:
        return False
    if (
        new_status == FieldStatus.EXPLICIT.value
        and current.get("value") is not None
        and cur_rank >= rank[FieldStatus.EXPLICIT.value]
        and current.get("value") != value
    ):
        new_status = FieldStatus.MODIFIED.value
    fields[field] = {"value": value, "status": new_status}
    return True


def merge_extracted(req: dict[str, Any], extracted: dict[str, Any], *, as_modified: bool = False) -> list[str]:
    """Merge extracted values. Returns list of changed field names."""
    changed: list[str] = []
    status = FieldStatus.MODIFIED if as_modified else FieldStatus.EXPLICIT
    for field, value in (extracted or {}).items():
        if value is None or value == "" or value == []:
            continue
        # Inferred keys use weaker status
        field_status = status
        if field.startswith("_inferred_"):
            continue
        meta = (extracted.get("_meta") or {}).get(field)
        if meta == "inferred":
            field_status = FieldStatus.INFERRED
        if set_field(req, field, value, field_status):
            changed.append(field)
    return changed


def _is_strong(status: str) -> bool:
    return status in {
        FieldStatus.EXPLICIT.value,
        FieldStatus.CONFIRMED.value,
        FieldStatus.MODIFIED.value,
    }


def has_location(req: dict[str, Any], *, require_confirmed: bool = True) -> bool:
    """Location is ready when customer-provided (not merely profile-inferred)."""
    loc = get_value(req, "business_location")
    if loc and (not require_confirmed or _is_strong(get_status(req, "business_location"))):
        return True
    locs = get_value(req, "target_geographic_locations") or []
    if locs and (not require_confirmed or _is_strong(get_status(req, "target_geographic_locations"))):
        return True
    pins = get_value(req, "target_postal_codes") or []
    if pins and (not require_confirmed or _is_strong(get_status(req, "target_postal_codes"))):
        return True
    # Postal code alone on business profile (inferred) does not satisfy
    return False


def has_budget(req: dict[str, Any], *, require_confirmed: bool = True) -> bool:
    amount = get_value(req, "budget_amount")
    if amount is None or float(amount) <= 0:
        return False
    if not require_confirmed:
        return True
    return _is_strong(get_status(req, "budget_amount"))


def missing_critical(req: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not has_location(req):
        missing.append("business_location")
    if not has_budget(req):
        missing.append("budget_amount")
    return missing


def next_question_field(req: dict[str, Any]) -> Optional[str]:
    missing = set(missing_critical(req))
    for field in QUESTION_PRIORITY:
        if field in missing:
            return field
        if field == "advertising_objective" and not get_value(req, "advertising_objective"):
            # Optional — only ask if we already have location+budget and still validating
            continue
        if field == "business_category" and not get_value(req, "business_category"):
            continue
    return missing_critical(req)[0] if missing_critical(req) else None


def readiness(req: dict[str, Any]) -> dict[str, Any]:
    missing = missing_critical(req)
    can_search = len(missing) == 0
    req["completeness_status"] = "ready_for_search" if can_search else "incomplete"
    return {
        "can_search": can_search,
        "missing_critical": missing,
        "next_question": next_question_field(req),
        "has_category": bool(get_value(req, "business_category")),
        "has_objective": bool(get_value(req, "advertising_objective")),
        "has_mediums": bool(get_value(req, "preferred_mediums")),
    }


def requirements_summary(req: dict[str, Any]) -> str:
    lines = []
    mapping = [
        ("business_category", "Business"),
        ("business_location", "Location"),
        ("target_postal_codes", "Pincodes"),
        ("advertising_objective", "Objective"),
        ("target_audience", "Audience"),
        ("preferred_mediums", "Mediums"),
        ("budget_amount", "Budget"),
        ("campaign_duration_days", "Duration (days)"),
        ("radius_km", "Radius (km)"),
    ]
    for field, label in mapping:
        val = get_value(req, field)
        status = get_status(req, field)
        if val is None or val == "" or val == []:
            continue
        if field == "budget_amount":
            currency = get_value(req, "budget_currency") or "INR"
            display = f"₹{int(float(val)):,}" if currency == "INR" else f"{val} {currency}"
        elif isinstance(val, list):
            display = ", ".join(str(v) for v in val)
        else:
            display = str(val).replace("_", " ")
        tag = "" if status in (FieldStatus.EXPLICIT.value, FieldStatus.CONFIRMED.value, FieldStatus.MODIFIED.value) else f" ({status})"
        lines.append(f"- {label}: {display}{tag}")
    return "\n".join(lines) if lines else "(no requirements captured yet)"


def snapshot(req: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(req)
