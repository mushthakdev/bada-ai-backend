"""Deterministic requirement extraction from natural-language messages."""

from __future__ import annotations

import re
from typing import Any, Optional

PIN_RE = re.compile(r"\b(\d{6})\b")
BUDGET_RE = re.compile(
    r"(?:₹|rs\.?|inr|rupees?)?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k|thousand|lakhs?|lakh|cr|crore)?",
    re.I,
)
DURATION_RE = re.compile(
    r"\b(\d+)\s*[- ]?(?:day|days|din)\b|\bfor\s+(?:a\s+)?(\d+)\s*[- ]?day\b",
    re.I,
)
RADIUS_RE = re.compile(r"\b(?:within|around|radius(?:\s+of)?)\s*(?:approximately\s*)?(\d+)\s*k(?:m|ilomet(?:er|re)s?)\b", re.I)
REDUCE_BUDGET_RE = re.compile(
    r"\b(reduce|lower|cut|decrease|change)\b.*\b(budget|spend)\b|\bbudget\b.*\b(to|of)\b",
    re.I,
)
FOCUS_ONLY_RE = re.compile(r"\b(focus|only|just)\b.*\b(on|in)\b|\bonly\s+on\b", re.I)

AREA_ALIASES = {
    "kakkanad": "Kakkanad",
    "ernakulam": "Ernakulam",
    "kochi": "Kochi",
    "cochin": "Kochi",
    "edappally": "Edappally",
    "edapally": "Edappally",
    "thrissur": "Thrissur",
    "trivandrum": "Trivandrum",
    "thiruvananthapuram": "Trivandrum",
    "calicut": "Kozhikode",
    "kozhikode": "Kozhikode",
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "chennai": "Chennai",
    "hyderabad": "Hyderabad",
    "mumbai": "Mumbai",
    "delhi": "Delhi",
}

CATEGORY_PATTERNS = [
    (r"\bsalon\b|\bbeauty\s+parlo?u?r\b|\bhair\s*(?:salon|studio)\b", "salon"),
    (r"\bjeweller", "jewellery"),
    (r"\brestaurant\b|\bcafe\b|\bhotel\b", "restaurant"),
    (r"\bclinic\b|\bhospital\b|\bdoctor\b", "healthcare"),
    (r"\bgym\b|\bfitness\b", "fitness"),
    (r"\breal\s*estate\b|\bbuilder\b", "real_estate"),
    (r"\beducation\b|\bschool\b|\bcoaching\b", "education"),
    (r"\bretail\b|\bstore\b|\bshop\b", "retail"),
]

OBJECTIVE_PATTERNS = [
    (r"\bbrand\s*awareness\b|\bawareness\b", "brand_awareness"),
    (r"\bstore\s*visits?\b|\bfootfall\b|\bnearby\b", "increase_store_visits"),
    (r"\blead\b|\benquir", "lead_generation"),
    (r"\bsales?\b|\bpromote\s+sale\b", "sales"),
    (r"\bwebsite\b|\btraffic\b", "website_traffic"),
    (r"\bROI\b|\bbest\s+return|\beffective", "increase_store_visits"),
]

MEDIUM_PATTERNS = [
    (r"\bdigital\s+billboard|\bled\b|\bdooh\b|\boutdoor\b|\bbillboard\b", "outdoor"),
    (r"\blocal\s+screens?|\bmall\s+screen|\bretail\s+screen", "local_screens"),
    (r"\bctv\b|\bconnected\s*tv\b", "ctv"),
    (r"\bott\b|\bhotstar\b|\bstreaming\b", "ott"),
    (r"\byoutube\b", "youtube"),
    (r"\bmeta\b|\bfacebook\b|\binstagram\b", "meta"),
]

AUDIENCE_PATTERNS = [
    (r"working\s+professionals?", "working professionals"),
    (r"families|family", "families"),
    (r"students?", "students"),
    (r"youth|young\s+adults?", "youth"),
    (r"customers?\s+nearby|local\s+customers?", "nearby customers"),
]


def _parse_budget_amount(text: str) -> Optional[float]:
    # Prefer amounts near budget / ₹ keywords
    candidates: list[float] = []
    for m in BUDGET_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        suffix = (m.group(2) or "").lower()
        if suffix in ("k", "thousand"):
            value *= 1000
        elif suffix in ("lakh", "lakhs"):
            value *= 100000
        elif suffix in ("cr", "crore"):
            value *= 10000000
        # Ignore tiny numbers that are likely days/radius unless currency marker nearby
        span = text[max(0, m.start() - 12) : m.end() + 8].lower()
        has_currency = any(x in span for x in ("₹", "rs", "inr", "rupee", "budget"))
        if value < 500 and not has_currency:
            continue
        if value >= 500:
            candidates.append(value)
    if not candidates:
        # Spoken: "twenty thousand"
        spoken = {
            "ten thousand": 10000,
            "fifteen thousand": 15000,
            "twenty thousand": 20000,
            "twenty five thousand": 25000,
            "twenty-five thousand": 25000,
            "thirty thousand": 30000,
            "fifty thousand": 50000,
        }
        lower = text.lower()
        for phrase, amount in spoken.items():
            if phrase in lower:
                return float(amount)
        return None
    # Prefer the largest plausible campaign budget if multiple
    return max(candidates)


def _extract_areas(text: str) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for alias, canonical in AREA_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            if canonical not in found:
                found.append(canonical)
    # "near X" / "in X"
    m = re.search(
        r"\b(?:near|in|around|at|for|located\s+in|based\s+in)\s+([A-Za-z][A-Za-z\s]{1,30}?)"
        r"(?=\s+(?:area|city|district|,|\.|$|i\s|with|for|and|especially|under|budget|₹|rs)|\s*$)",
        text,
        re.I,
    )
    if m:
        area = m.group(1).strip(" ,.")
        area = re.split(
            r"\b(?:advert|ads?|campa|budget|for|with|and|especially)\b",
            area,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" ,.")
        if len(area) >= 3:
            titled = AREA_ALIASES.get(area.lower(), area.title())
            if titled not in found:
                found.append(titled)
    return found


def extract_requirements(message: str) -> dict[str, Any]:
    text = message.strip()
    out: dict[str, Any] = {"_meta": {}}

    pins = PIN_RE.findall(text)
    if pins:
        out["target_postal_codes"] = pins
        out["business_postal_code"] = pins[0]

    areas = _extract_areas(text)
    if areas:
        out["business_location"] = areas[0]
        out["target_geographic_locations"] = areas

    budget = _parse_budget_amount(text)
    if budget is not None:
        out["budget_amount"] = budget
        out["budget_currency"] = "INR"

    dur = DURATION_RE.search(text)
    if dur:
        days = int(dur.group(1) or dur.group(2))
        if 1 <= days <= 365:
            out["campaign_duration_days"] = days

    rad = RADIUS_RE.search(text)
    if rad:
        out["radius_km"] = int(rad.group(1))

    for pattern, category in CATEGORY_PATTERNS:
        if re.search(pattern, text, re.I):
            out["business_category"] = category
            break

    for pattern, objective in OBJECTIVE_PATTERNS:
        if re.search(pattern, text, re.I):
            out["advertising_objective"] = objective
            break

    mediums: list[str] = []
    for pattern, medium in MEDIUM_PATTERNS:
        if re.search(pattern, text, re.I) and medium not in mediums:
            mediums.append(medium)
    if mediums:
        out["preferred_mediums"] = mediums

    audiences: list[str] = []
    for pattern, audience in AUDIENCE_PATTERNS:
        if re.search(pattern, text, re.I) and audience not in audiences:
            audiences.append(audience)
    if audiences:
        out["target_audience"] = ", ".join(audiences)

    # Ownership phrasing → business description hint
    own = re.search(r"\b(?:i\s+own|we\s+own|my|our)\s+([a-z][a-z\s]{2,40})", text, re.I)
    if own and "business_category" in out:
        out["business_description"] = own.group(0).strip()

    return out


def detect_intent(message: str, has_active_plan: bool = False) -> str:
    text = message.lower().strip()
    if re.search(r"\b(cancel|stop|abort|never\s*mind)\b", text):
        return "cancel"
    if re.search(r"\b(yes|accept|approve|go\s+ahead|book\s+it|proceed|looks?\s+good)\b", text) and has_active_plan:
        return "accept_plan"
    if re.search(r"\b(modify|change|update|reduce|lower|focus|instead)\b", text):
        return "modify_requirements"
    if REDUCE_BUDGET_RE.search(text) or FOCUS_ONLY_RE.search(text):
        return "modify_requirements"
    if re.search(r"\b(list|show)\b.*\b(campaign)|how\s+is\s+(my\s+)?(spend|performance)|dashboard|metrics\b", text):
        return "account_query"
    if re.search(r"\b(help|what\s+can\s+you)\b", text):
        return "help"
    if re.search(r"\b(create|start|launch|new)\b.*\b(campaign|ad|advert)", text):
        return "campaign_request"
    if re.search(r"\b(advert|ads?|campaign|promot|market|billboard|where\s+should\s+i\s+advert)", text):
        return "campaign_request"
    if re.search(r"\b(salon|jeweller|restaurant|clinic|store|shop)\b", text):
        return "campaign_request"
    return "general"


def question_for_field(field: str, req_summary_hint: Optional[str] = None) -> tuple[str, Optional[dict[str, Any]], list[str]]:
    """Return (reply, select_ui, suggestions) for the highest-priority missing field."""
    if field == "business_location":
        reply = (
            "Which area is your business located in, and are you mainly targeting customers nearby?"
        )
        if req_summary_hint:
            reply = f"Got it — {req_summary_hint}. {reply}"
        select = {
            "id": "area",
            "mode": "single",
            "title": "Select target area",
            "submit_label": "Continue",
            "allow_custom": True,
            "custom_placeholder": "City / locality (e.g. Kakkanad)",
            "options": [
                {"value": "Kakkanad", "label": "Kakkanad", "description": "Ernakulam · Kochi"},
                {"value": "Ernakulam", "label": "Ernakulam", "description": "Kochi metro"},
                {"value": "Kochi", "label": "Kochi", "description": "Includes nearby localities"},
                {"value": "Thrissur", "label": "Thrissur", "description": "Kerala"},
            ],
        }
        return reply, select, ["Kakkanad", "Ernakulam", "Kochi"]

    if field == "budget_amount":
        reply = "What total campaign budget are you working with (in ₹)?"
        select = {
            "id": "budget",
            "mode": "single",
            "title": "Select campaign budget",
            "submit_label": "Continue",
            "allow_custom": True,
            "custom_placeholder": "Or type amount (e.g. 25000)",
            "options": [
                {"value": "10000", "label": "₹10,000", "description": "Starter"},
                {"value": "15000", "label": "₹15,000", "description": "Focused local"},
                {"value": "25000", "label": "₹25,000", "description": "Balanced"},
                {"value": "50000", "label": "₹50,000", "description": "Broader reach"},
            ],
        }
        return reply, select, ["₹15,000", "₹25,000", "₹50,000"]

    if field == "advertising_objective":
        reply = "What is the main goal — more nearby visits, leads, or brand awareness?"
        select = {
            "id": "objective",
            "mode": "single",
            "title": "Campaign objective",
            "submit_label": "Continue",
            "options": [
                {"value": "increase_store_visits", "label": "Store visits / footfall"},
                {"value": "lead_generation", "label": "Lead generation"},
                {"value": "brand_awareness", "label": "Brand awareness"},
                {"value": "sales", "label": "Sales"},
            ],
        }
        return reply, select, ["Store visits", "Leads", "Awareness"]

    return "Could you share a bit more detail so I can search the right inventory?", None, []
