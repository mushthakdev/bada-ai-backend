"""Orchestrate Bada Agent: plan → tools → reply."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.agent.prompts import AGENT_SYSTEM_PROMPT, AGENT_USER_TEMPLATE
from app.ai.agent.setup import handle_setup_turn
from app.ai.agent.tools import (
    build_account_context,
    collect_actions,
    context_as_text,
    execute_tools,
    rule_based_plan,
)
from app.ai.factory import get_text_provider
from app.core.config import get_settings
from app.models.ai import AIConversation, AIMessage
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()


def _history_text(db: Session, conversation_id: UUID, limit: int = 8) -> str:
    rows = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation_id)
        .order_by(AIMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    if not rows:
        return "(no prior messages)"
    return "\n".join(f"{m.role}: {m.content[:500]}" for m in rows)


def _parse_agent_json(raw: Any) -> Optional[dict[str, Any]]:
    if isinstance(raw, dict) and "reply" in raw:
        tools = raw.get("tools") or []
        if not isinstance(tools, list):
            tools = []
        return {"reply": str(raw.get("reply") or ""), "tools": tools}

    text = None
    if isinstance(raw, dict) and "raw_text" in raw:
        text = str(raw["raw_text"])
    elif isinstance(raw, str):
        text = raw
    if not text:
        return None

    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract first JSON object
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        else:
            return None

    if not isinstance(data, dict) or "reply" not in data:
        return None
    tools = data.get("tools") or []
    if not isinstance(tools, list):
        tools = []
    return {"reply": str(data.get("reply") or ""), "tools": tools}


def _llm_plan(message: str, context_text: str, history: str) -> Optional[dict[str, Any]]:
    if settings.ai_mock_mode:
        return None

    provider = get_text_provider()
    prompt = AGENT_USER_TEMPLATE.format(
        context=context_text,
        history=history,
        message=message,
    )
    try:
        # Prefer chat helper if present; fall back to generate()
        if hasattr(provider, "generate_agent"):
            result = provider.generate_agent(prompt, system=AGENT_SYSTEM_PROMPT)
        else:
            result = provider.generate(prompt, system=AGENT_SYSTEM_PROMPT)
        return _parse_agent_json(result.content)
    except Exception:
        logger.exception("Agent LLM plan failed; falling back to rules")
        return None


def _enrich_reply(reply: str, tool_results: list[dict[str, Any]]) -> str:
    parts = [reply.strip()] if reply.strip() else []

    for result in tool_results:
        if not result.get("ok"):
            err = result.get("error") or "Tool failed"
            parts.append(f"Couldn’t complete `{result.get('tool')}`: {err}")
            continue

        tool = result.get("tool")
        if tool == "create_campaign":
            c = result.get("campaign") or {}
            parts.append(
                f"Draft campaign **{c.get('name')}** is ready (status: {c.get('status')}). "
                "Next: edit targeting/budget, generate a creative in Studio, then submit for review."
            )
        elif tool == "list_campaigns":
            campaigns = result.get("campaigns") or []
            if not campaigns:
                parts.append("You have no campaigns yet. Say “create a new campaign” to start one.")
            else:
                lines = [f"- {c['name']} — {c['status']}" for c in campaigns[:10]]
                parts.append("Campaigns:\n" + "\n".join(lines))
        elif tool == "get_account_summary":
            lines = result.get("summary_lines") or []
            if lines:
                parts.append("Account snapshot:\n- " + "\n- ".join(lines))
            top = result.get("top_pincodes") or []
            if top:
                parts.append(
                    "Top pincodes by leads: "
                    + ", ".join(f"{p.get('pincode')} ({p.get('leads', 0)})" for p in top)
                )
        elif tool == "help":
            caps = result.get("capabilities") or []
            if caps:
                parts.append("I can:\n- " + "\n- ".join(caps))

    # Deduplicate consecutive identical paragraphs
    cleaned: list[str] = []
    for p in parts:
        if not cleaned or cleaned[-1] != p:
            cleaned.append(p)
    return "\n\n".join(cleaned).strip()


def run_agent(
    db: Session,
    user: User,
    *,
    message: str,
    conversation_id: UUID,
    business_id: Optional[UUID] = None,
) -> dict[str, Any]:
    ctx = build_account_context(db, user, business_id=business_id)
    conversation = db.query(AIConversation).filter(AIConversation.id == conversation_id).first()

    # Guided campaign setup (area → pincode → objective → …) takes priority
    if conversation is not None:
        setup_result = handle_setup_turn(db, user, conversation, message, ctx)
        if setup_result and setup_result.get("handled"):
            dq = (ctx.get("metrics") or {}).get("data_quality") or {
                "is_simulated": False,
                "label": "Live",
            }
            return {
                "reply": setup_result.get("reply") or "",
                "actions": setup_result.get("actions") or [],
                "suggestions": setup_result.get("suggestions") or [],
                "select": setup_result.get("select"),
                "tool_results": setup_result.get("tool_results") or [],
                "data_quality": dq,
                "is_mock_llm": True,
                "provider": "setup_wizard",
            }

    context_text = context_as_text(ctx)
    history = _history_text(db, conversation_id)

    plan = _llm_plan(message, context_text, history)
    used_llm = plan is not None
    if not plan:
        plan = rule_based_plan(message, ctx)
        used_llm = False

    tool_results = execute_tools(
        db,
        user,
        plan.get("tools") or [],
        ctx=ctx,
        business_id=business_id,
    )
    reply = _enrich_reply(str(plan.get("reply") or ""), tool_results)
    actions = collect_actions(tool_results)

    provider_name = "gemini" if used_llm and not settings.ai_mock_mode else "rules"
    return {
        "reply": reply,
        "actions": actions,
        "suggestions": [],
        "select": None,
        "tool_results": [
            {k: v for k, v in r.items() if k != "summary_lines"} for r in tool_results
        ],
        "data_quality": (ctx.get("metrics") or {}).get("data_quality")
        or {"is_simulated": False, "label": "Live"},
        "is_mock_llm": settings.ai_mock_mode or not used_llm,
        "provider": provider_name,
    }
