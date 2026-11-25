"""Controlled agent journey states for Bada orchestrator."""

from __future__ import annotations

from enum import Enum


class AgentState(str, Enum):
    DISCOVERY = "DISCOVERY"
    REQUIREMENT_COLLECTION = "REQUIREMENT_COLLECTION"
    REQUIREMENT_VALIDATION = "REQUIREMENT_VALIDATION"
    INVENTORY_SEARCH = "INVENTORY_SEARCH"
    EXTERNAL_RESEARCH = "EXTERNAL_RESEARCH"
    STRATEGY_ANALYSIS = "STRATEGY_ANALYSIS"
    PLAN_GENERATION = "PLAN_GENERATION"
    CUSTOMER_REVIEW = "CUSTOMER_REVIEW"
    CREATIVE_GENERATION = "CREATIVE_GENERATION"
    BOOKING_PENDING = "BOOKING_PENDING"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CAMPAIGN_EXECUTION = "CAMPAIGN_EXECUTION"
    PERFORMANCE_MONITORING = "PERFORMANCE_MONITORING"
    COMPLETED = "COMPLETED"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"


ALLOWED_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.DISCOVERY: {
        AgentState.REQUIREMENT_COLLECTION,
        AgentState.REQUIREMENT_VALIDATION,
        AgentState.INVENTORY_SEARCH,
        AgentState.PERFORMANCE_MONITORING,
        AgentState.HUMAN_ESCALATION,
    },
    AgentState.REQUIREMENT_COLLECTION: {
        AgentState.REQUIREMENT_VALIDATION,
        AgentState.INVENTORY_SEARCH,
        AgentState.DISCOVERY,
        AgentState.HUMAN_ESCALATION,
    },
    AgentState.REQUIREMENT_VALIDATION: {
        AgentState.REQUIREMENT_COLLECTION,
        AgentState.INVENTORY_SEARCH,
        AgentState.STRATEGY_ANALYSIS,
    },
    AgentState.INVENTORY_SEARCH: {
        AgentState.EXTERNAL_RESEARCH,
        AgentState.STRATEGY_ANALYSIS,
        AgentState.PLAN_GENERATION,
        AgentState.REQUIREMENT_COLLECTION,
        AgentState.CUSTOMER_REVIEW,
    },
    AgentState.EXTERNAL_RESEARCH: {
        AgentState.STRATEGY_ANALYSIS,
        AgentState.PLAN_GENERATION,
        AgentState.CUSTOMER_REVIEW,
        AgentState.REQUIREMENT_COLLECTION,
    },
    AgentState.STRATEGY_ANALYSIS: {
        AgentState.PLAN_GENERATION,
        AgentState.INVENTORY_SEARCH,
        AgentState.REQUIREMENT_COLLECTION,
    },
    AgentState.PLAN_GENERATION: {
        AgentState.CUSTOMER_REVIEW,
        AgentState.INVENTORY_SEARCH,
        AgentState.REQUIREMENT_COLLECTION,
    },
    AgentState.CUSTOMER_REVIEW: {
        AgentState.REQUIREMENT_COLLECTION,
        AgentState.INVENTORY_SEARCH,
        AgentState.PLAN_GENERATION,
        AgentState.CREATIVE_GENERATION,
        AgentState.BOOKING_PENDING,
        AgentState.HUMAN_ESCALATION,
    },
    AgentState.CREATIVE_GENERATION: {
        AgentState.CUSTOMER_REVIEW,
        AgentState.BOOKING_PENDING,
    },
    AgentState.BOOKING_PENDING: {
        AgentState.PAYMENT_PENDING,
        AgentState.CUSTOMER_REVIEW,
        AgentState.CAMPAIGN_EXECUTION,
    },
    AgentState.PAYMENT_PENDING: {
        AgentState.CAMPAIGN_EXECUTION,
        AgentState.BOOKING_PENDING,
        AgentState.CUSTOMER_REVIEW,
    },
    AgentState.CAMPAIGN_EXECUTION: {
        AgentState.PERFORMANCE_MONITORING,
        AgentState.COMPLETED,
        AgentState.HUMAN_ESCALATION,
    },
    AgentState.PERFORMANCE_MONITORING: {
        AgentState.COMPLETED,
        AgentState.DISCOVERY,
        AgentState.REQUIREMENT_COLLECTION,
    },
    AgentState.COMPLETED: {
        AgentState.DISCOVERY,
        AgentState.REQUIREMENT_COLLECTION,
        AgentState.PERFORMANCE_MONITORING,
    },
    AgentState.HUMAN_ESCALATION: {
        AgentState.DISCOVERY,
        AgentState.REQUIREMENT_COLLECTION,
        AgentState.CUSTOMER_REVIEW,
    },
}


def transition(current: AgentState, target: AgentState) -> AgentState:
    if current == target:
        return current
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target in allowed:
        return target
    if target in {
        AgentState.REQUIREMENT_COLLECTION,
        AgentState.INVENTORY_SEARCH,
        AgentState.DISCOVERY,
    }:
        return target
    return current
