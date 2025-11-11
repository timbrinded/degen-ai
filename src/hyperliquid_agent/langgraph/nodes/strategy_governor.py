"""Strategy governor node synchronizing LangGraph + StrategyGovernor state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hyperliquid_agent.config import Config
from hyperliquid_agent.governance.plan_card import StrategyPlanCard
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.serialization import serialize_plan
from hyperliquid_agent.langgraph.state import GlobalState, StatePatch


def _activate_plan(
    payload: dict[str, Any],
    context: LangGraphRuntimeContext,
) -> StrategyPlanCard:
    plan = StrategyPlanCard.from_dict(payload)
    context.governor.activate_plan(plan, datetime.now(UTC))
    account_state = context.cache.get("fast_account_state")
    if account_state is not None:
        context.scorekeeper.start_tracking_plan(plan, account_state.portfolio_value)
    return plan


def strategy_governor(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Apply approved plan changes + mirror governor state into LangGraph."""

    governance_state = state.get("governance") or {}
    approved_plan = governance_state.get("approved_plan")
    plan_payload: dict[str, Any] | None = approved_plan if isinstance(approved_plan, dict) else None
    plan = context.governor.active_plan

    metadata = {
        "loop": "slow",
        "incoming_plan": bool(approved_plan),
        "current_plan_id": plan.plan_id if plan else None,
    }

    with node_trace("strategy_governor", metadata=metadata) as run:
        if plan_payload:
            plan = _activate_plan(plan_payload, context)

        patch: StatePatch = {
            "governance": {
                "active_plan": serialize_plan(plan),
                "approved_plan": None,
            }
        }

        if run is not None:
            run.add_outputs(summarize_patch({"governance": patch["governance"]}))
        return patch


__all__ = ["strategy_governor"]
