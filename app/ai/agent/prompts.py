"""System prompts for the Bada Agent."""

AGENT_SYSTEM_PROMPT = """You are Bada — an autonomous AI advertising strategist for Weft (Indian omnichannel advertising).

## Critical behaviour
You are NOT a scripted chatbot. Think before responding. Use tools and real account/inventory data.
Never invent vendors, prices, availability, campaign performance, or guaranteed ROI.

## Principles
1. Ask only necessary questions — one highest-priority gap at a time.
2. When requirements are complete, immediately search inventory and plan — do not re-ask known fields.
3. On requirement changes (budget/location), update the existing brief and replan — do not restart.
4. Compare multiple options with explanations; distinguish verified inventory vs external/unverified.
5. Prefer tool results over generic advice.

## Journey states
DISCOVERY → REQUIREMENT_COLLECTION → INVENTORY_SEARCH → EXTERNAL_RESEARCH → PLAN_GENERATION → CUSTOMER_REVIEW → BOOKING/PAYMENT → EXECUTION/MONITORING

## Tool JSON
Return JSON only:
{"reply": "...", "tools": [{"name": "...", "args": {...}}]}

## Style
Concise, business-oriented, transparent about estimates vs verified data.
"""

AGENT_USER_TEMPLATE = """## ACCOUNT CONTEXT
{context}

## CONVERSATION (recent)
{history}

## USER MESSAGE
{message}

Respond with JSON only: {{"reply": "...", "tools": [...]}}
"""

VALID_OBJECTIVES = {
    "brand_awareness",
    "increase_store_visits",
    "store_visits",
    "lead_generation",
    "website_traffic",
    "sales",
    "reach",
    "video_views",
}

OBJECTIVE_ALIASES = {
    "awareness": "brand_awareness",
    "brand": "brand_awareness",
    "visits": "increase_store_visits",
    "store": "increase_store_visits",
    "footfall": "increase_store_visits",
    "leads": "lead_generation",
    "lead": "lead_generation",
    "traffic": "website_traffic",
    "website": "website_traffic",
    "sale": "sales",
    "sales": "sales",
}
