"""Central Bada orchestrator: understand → gaps → act → validate → respond → persist."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.agent.extraction import (
    detect_intent,
    extract_requirements,
    question_for_field,
)
from app.ai.agent.inventory_matcher import (
    build_proposal,
    discover_external_opportunities,
    optimize_budget_plans,
    search_and_rank,
)
from app.ai.agent.requirements import (
    empty_requirements,
    get_value,
    merge_extracted,
    readiness,
    requirements_summary,
    set_field,
    FieldStatus,
)
from app.ai.agent.states import AgentState, transition
from app.ai.agent.tools import (
    build_account_context,
    collect_actions,
    execute_tools,
    rule_based_plan,
)
from app.models.ai import AIConversation
from app.models.user import User

logger = logging.getLogger(__name__)


def _load_context(conversation: AIConversation) -> dict[str, Any]:
    try:
        data = json.loads(conversation.context_json) if conversation.context_json else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if "agent" not in data or not isinstance(data.get("agent"), dict):
        data["agent"] = {
            "state": AgentState.DISCOVERY.value,
            "requirements": empty_requirements(),
        }
    agent = data["agent"]
    if "requirements" not in agent or not isinstance(agent.get("requirements"), dict):
        agent["requirements"] = empty_requirements()
    if "state" not in agent:
        agent["state"] = AgentState.DISCOVERY.value
    # Disable legacy linear wizard when using orchestrator
    if data.get("setup", {}).get("active"):
        data["setup"]["active"] = False
        data["setup"]["migrated_to_orchestrator"] = True
    return data


def _save_context(conversation: AIConversation, data: dict[str, Any]) -> None:
    conversation.context_json = json.dumps(data, default=str)


def _state(agent: dict[str, Any]) -> AgentState:
    try:
        return AgentState(agent.get("state") or AgentState.DISCOVERY.value)
    except ValueError:
        return AgentState.DISCOVERY


def _set_state(agent: dict[str, Any], target: AgentState) -> AgentState:
    current = _state(agent)
    nxt = transition(current, target)
    agent["state"] = nxt.value
    req = agent.get("requirements") or {}
    req["current_campaign_state"] = nxt.value
    agent["requirements"] = req
    return nxt


def _seed_from_business(req: dict[str, Any], ctx: dict[str, Any]) -> None:
    businesses = ctx.get("businesses") or []
    if not businesses:
        return
    b = businesses[0]
    if b.get("category"):
        set_field(req, "business_category", str(b["category"]).lower(), FieldStatus.INFERRED)
    if b.get("name"):
        set_field(req, "business_name", b["name"], FieldStatus.INFERRED)
    if b.get("city"):
        set_field(req, "business_location", b["city"], FieldStatus.INFERRED)
    if b.get("pincode"):
        set_field(req, "business_postal_code", b["pincode"], FieldStatus.INFERRED)
        set_field(req, "target_postal_codes", [b["pincode"]], FieldStatus.INFERRED)
    if b.get("objective"):
        set_field(req, "advertising_objective", b["objective"], FieldStatus.INFERRED)


def _format_inventory_reply(inventory: dict[str, Any], plans: dict[str, Any], proposal: dict[str, Any], req: dict[str, Any]) -> str:
    items = inventory.get("items") or []
    lines = [
        "I have enough detail to search registered inventory. Here’s what fits your brief:",
        "",
        "**Requirements captured**",
        requirements_summary(req),
        "",
    ]
    if not items:
        lines.append("No suitable **verified Bada inventory** matched your constraints.")
        return "\n".join(lines)

    lines.append("**Top inventory matches** (ranked by suitability — not just price):")
    for i, item in enumerate(items[:5], 1):
        price = item.get("price")
        price_s = f"₹{int(price):,}" if isinstance(price, (int, float)) else "price on request"
        est = "estimate" if item.get("is_estimate") else "listed"
        lines.append(
            f"{i}. **{item.get('title')}** — {item.get('medium')} · {item.get('city') or ''} {item.get('pincode') or ''} · "
            f"{price_s} ({est}) · score {item.get('suitability_score')}"
        )
        for reason in (item.get("reasons") or [])[:2]:
            lines.append(f"   - {reason}")
        lim = (item.get("limitations") or [])[:1]
        if lim:
            lines.append(f"   - Limitation: {lim[0]}")

    plan_list = plans.get("plans") or []
    if plan_list:
        lines.append("")
        lines.append("**Alternative plans** (from available inventory only):")
        for plan in plan_list:
            lines.append(
                f"- **{plan.get('name')}**: ₹{int(plan.get('total_allocated') or 0):,} allocated · "
                f"{len(plan.get('items') or [])} placements · {plan.get('focus')}"
            )

    prop = (proposal or {}).get("proposal") or {}
    if prop.get("risks_and_assumptions"):
        lines.append("")
        lines.append("**Transparency**")
        for risk in prop["risks_and_assumptions"][:3]:
            lines.append(f"- {risk}")

    lines.append("")
    lines.append(
        "This placement mix looks suitable for local reach, but there isn’t enough conversion data "
        "to predict actual ROI reliably."
    )
    lines.append("")
    lines.append(
        "Next: say **accept plan** to proceed toward booking, or change budget/location "
        "(e.g. “reduce budget to ₹15,000 and focus only on Kakkanad”)."
    )
    return "\n".join(lines)


def _run_planning_pipeline(db: Session, req: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    tool_results: list[dict[str, Any]] = []
    inventory = search_and_rank(db, req)
    tool_results.append(inventory)

    if not inventory.get("items"):
        external = discover_external_opportunities(req)
        tool_results.append(external)
        req["last_inventory"] = inventory
        req["last_external"] = external
        lines = [
            "I searched registered Bada inventory for your requirements and found **no suitable matches**.",
            "",
            requirements_summary(req),
            "",
            "**External opportunity discovery** (unverified — no invented prices):",
        ]
        for opp in external.get("opportunities") or []:
            lines.append(
                f"- {opp.get('medium')} near {opp.get('location')}: "
                f"{opp.get('classification')} · {opp.get('status')}"
            )
            lines.append(f"  {opp.get('notes')}")
        lines.append("")
        lines.append(external.get("disclaimer") or "")
        lines.append("I can log vendor acquisition leads for the ops team, or you can widen location/budget/mediums.")
        return "\n".join(lines), tool_results, {"state": AgentState.EXTERNAL_RESEARCH}

    # Unsuitable if all scores low or all exceed budget badly
    top = inventory["items"][0]
    if float(top.get("suitability_score") or 0) < 35:
        external = discover_external_opportunities(req)
        tool_results.append(external)
        req["last_inventory"] = inventory
        req["last_external"] = external
        reply = (
            "Available inventory poorly matches your brief (low suitability). "
            "I’m treating this as an inventory gap and opening external discovery "
            "without inventing vendor prices.\n\n"
            + (external.get("disclaimer") or "")
        )
        return reply, tool_results, {"state": AgentState.EXTERNAL_RESEARCH}

    plans = optimize_budget_plans(inventory, req)
    tool_results.append(plans)
    proposal = build_proposal(req, inventory, plans)
    tool_results.append(proposal)
    req["last_inventory"] = inventory
    req["last_plan"] = proposal.get("proposal")
    reply = _format_inventory_reply(inventory, plans, proposal, req)
    return reply, tool_results, {"state": AgentState.CUSTOMER_REVIEW}


def handle_orchestrator_turn(
    db: Session,
    user: User,
    conversation: AIConversation,
    message: str,
    *,
    business_id: Optional[UUID] = None,
) -> dict[str, Any]:
    ctx = build_account_context(db, user, business_id=business_id)
    data = _load_context(conversation)
    agent = data["agent"]
    req = agent["requirements"]
    _seed_from_business(req, ctx)

    text = message.strip()
    has_plan = bool(req.get("last_plan"))
    intent = detect_intent(text, has_active_plan=has_plan)

    # Account / help intents can short-circuit without destroying requirements
    if intent in ("account_query", "help", "general") and intent != "campaign_request":
        # Still merge any embedded requirements if present
        extracted = extract_requirements(text)
        changed = merge_extracted(req, extracted, as_modified=(intent == "modify_requirements"))
        ready = readiness(req)
        if intent in ("account_query", "help") or (
            intent == "general" and not changed and not ready["can_search"] and _state(agent) == AgentState.DISCOVERY
        ):
            plan = rule_based_plan(text, ctx)
            tool_results = execute_tools(db, user, plan.get("tools") or [], ctx=ctx, business_id=business_id)
            actions = collect_actions(tool_results)
            reply = str(plan.get("reply") or "").strip()
            for result in tool_results:
                if result.get("tool") == "get_account_summary" and result.get("summary_lines"):
                    reply += "\n\nAccount snapshot:\n- " + "\n- ".join(result["summary_lines"])
                elif result.get("tool") == "list_campaigns":
                    camps = result.get("campaigns") or []
                    reply += "\n\nCampaigns:\n" + ("\n".join(f"- {c['name']} — {c['status']}" for c in camps[:10]) if camps else "None yet.")
                elif result.get("tool") == "help" and result.get("capabilities"):
                    reply += "\n\nI can:\n- " + "\n- ".join(result["capabilities"])
            if intent == "help":
                _set_state(agent, AgentState.DISCOVERY)
            elif intent == "account_query":
                _set_state(agent, AgentState.PERFORMANCE_MONITORING)
            agent["requirements"] = req
            _save_context(conversation, data)
            dq = (ctx.get("metrics") or {}).get("data_quality") or {"is_simulated": False, "label": "Live"}
            return {
                "reply": reply,
                "actions": actions,
                "suggestions": ["Create a campaign plan", "List my campaigns", "How is my spend?"],
                "select": None,
                "tool_results": tool_results,
                "data_quality": dq,
                "is_mock_llm": True,
                "provider": "orchestrator",
                "agent_state": agent["state"],
            }

    # Extract & merge requirements
    extracted = extract_requirements(text)
    as_modified = intent == "modify_requirements" or _state(agent) in {
        AgentState.CUSTOMER_REVIEW,
        AgentState.PLAN_GENERATION,
    }
    changed = merge_extracted(req, extracted, as_modified=as_modified)

    # If user answered a pending single-field question with a bare value
    pending = req.get("pending_question")
    if pending and not changed:
        if pending == "business_location" and len(text) >= 3 and not text.isdigit():
            set_field(req, "business_location", text.title() if len(text) < 40 else text[:40], FieldStatus.EXPLICIT)
            set_field(req, "target_geographic_locations", [get_value(req, "business_location")], FieldStatus.EXPLICIT)
            changed = ["business_location"]
        elif pending == "budget_amount":
            from app.ai.agent.extraction import _parse_budget_amount

            amount = _parse_budget_amount(text)
            if amount:
                set_field(req, "budget_amount", amount, FieldStatus.EXPLICIT)
                changed = ["budget_amount"]

    req["pending_question"] = None
    ready = readiness(req)

    # Accept plan → booking pending (does not auto-charge)
    if intent == "accept_plan" and has_plan:
        _set_state(agent, AgentState.BOOKING_PENDING)
        agent["requirements"] = req
        _save_context(conversation, data)
        return {
            "reply": (
                "Great — marked as **customer approved** for the recommended plan.\n\n"
                "Next I’ll prepare a booking summary (availability + pricing confirmation). "
                "Say **create draft campaign** to create the campaign record, or **pay later** / open Payments when ready.\n\n"
                "I will not mark payment successful until the payment provider confirms it."
            ),
            "actions": [
                {"type": "link", "label": "Open payments", "href": "/payments"},
                {"type": "link", "label": "Campaigns", "href": "/campaigns"},
            ],
            "suggestions": ["Create draft campaign", "Pay later", "Modify budget"],
            "select": None,
            "tool_results": [{"ok": True, "tool": "accept_plan", "state": "BOOKING_PENDING"}],
            "data_quality": {"is_simulated": True, "label": "Proposal accepted — booking not yet confirmed"},
            "is_mock_llm": True,
            "provider": "orchestrator",
            "agent_state": agent["state"],
        }

    if intent == "cancel":
        data["agent"] = {
            "state": AgentState.DISCOVERY.value,
            "requirements": empty_requirements(),
        }
        _save_context(conversation, data)
        return {
            "reply": "Okay — I cleared the active advertising brief. Tell me what you’d like to plan next.",
            "actions": [],
            "suggestions": ["I own a salon in Kakkanad", "New advertising near Ernakulam", "List my campaigns"],
            "select": None,
            "tool_results": [{"ok": True, "tool": "reset_requirements"}],
            "data_quality": {"is_simulated": False, "label": "Live"},
            "is_mock_llm": True,
            "provider": "orchestrator",
            "agent_state": AgentState.DISCOVERY.value,
        }

    # Incomplete → ask only the next necessary question
    if not ready["can_search"]:
        _set_state(agent, AgentState.REQUIREMENT_COLLECTION)
        field = ready["next_question"] or "business_location"
        req["pending_question"] = field
        hint = None
        cat = get_value(req, "business_category")
        if cat and field == "business_location":
            hint = f"for your {cat}"
        reply, select, suggestions = question_for_field(field, hint)
        # Prefix acknowledgement of what we already know
        known = requirements_summary(req)
        if known and "no requirements" not in known:
            reply = f"Here’s what I have so far:\n{known}\n\n{reply}"
        agent["requirements"] = req
        _save_context(conversation, data)
        return {
            "reply": reply,
            "actions": [],
            "suggestions": suggestions,
            "select": select,
            "tool_results": [
                {
                    "ok": True,
                    "tool": "collect_requirements",
                    "missing": ready["missing_critical"],
                    "asked": field,
                    "state": agent["state"],
                }
            ],
            "data_quality": {"is_simulated": False, "label": "Requirement collection"},
            "is_mock_llm": True,
            "provider": "orchestrator",
            "agent_state": agent["state"],
        }

    # Sufficient info → search / replan immediately (including after modifications)
    _set_state(agent, AgentState.INVENTORY_SEARCH)
    reply, tool_results, meta = _run_planning_pipeline(db, req)
    target_state = meta.get("state") or AgentState.CUSTOMER_REVIEW
    _set_state(agent, target_state)
    agent["requirements"] = req
    _save_context(conversation, data)

    actions = [
        {"type": "link", "label": "Marketplace", "href": "/marketplace"},
        {"type": "link", "label": "Omnichannel planner", "href": "/campaigns/omnichannel/new"},
    ]
    if target_state == AgentState.CUSTOMER_REVIEW:
        suggestions = ["Accept plan", "Reduce budget to ₹15,000", "Focus only on Kakkanad", "Show alternatives"]
    else:
        suggestions = ["Widen location", "Increase budget", "Change mediums", "List my campaigns"]

    return {
        "reply": reply,
        "actions": actions,
        "suggestions": suggestions,
        "select": None,
        "tool_results": tool_results,
        "data_quality": (inventory_dq(tool_results)),
        "is_mock_llm": True,
        "provider": "orchestrator",
        "agent_state": agent["state"],
    }


def inventory_dq(tool_results: list[dict[str, Any]]) -> dict[str, Any]:
    for r in tool_results:
        if r.get("data_quality"):
            return r["data_quality"]
    return {"is_simulated": True, "label": "Demo inventory analysis"}
