"""LLM-backed governance decision node for the medium loop."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from langgraph.errors import GraphInterrupt, Interrupt

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.serialization import serialize_plan
from hyperliquid_agent.langgraph.state import GlobalState, StatePatch


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _budget_available(
    context: LangGraphRuntimeContext,
    loop: Literal["fast", "medium", "slow"],
) -> float:
    return context.budgets.limit_for(loop).available()


def llm_decision_engine(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Call the governance-aware LLM when review is allowed."""

    plan = context.governor.active_plan
    if plan is None:
        return {}

    account_state = context.cache.get("medium_account_state") or context.cache.get(
        "fast_account_state"
    )
    if account_state is None:
        return {}

    plan_health = (state.get("medium") or {}).get("plan_health") or {}
    if not plan_health.get("can_review", False):
        return {}

    if _budget_available(context, "medium") <= 0:
        raise GraphInterrupt(
            [
                Interrupt(
                    value={
                        "type": "llm_budget_exhausted",
                        "loop": "medium",
                        "plan_id": plan.plan_id,
                    }
                )
            ]
        )

    metadata = {
        "loop": "medium",
        "plan_id": plan.plan_id,
        "regime": context.regime_detector.current_regime,
    }

    with node_trace("llm_decision_engine", metadata=metadata) as run:
        decision = context.decision_engine.get_decision_with_governance(
            account_state=account_state,
            active_plan=plan,
            current_regime=context.regime_detector.current_regime,
            can_review=True,
        )

        cost_delta = max(decision.cost_usd, 0.0)
        context.record_llm_cost("medium", cost_delta)

        telemetry_patch = {
            **(state.get("telemetry", {}) or {}),
            "llm_cost_usd": (state.get("telemetry", {}) or {}).get("llm_cost_usd", 0.0)
            + cost_delta,
            "last_llm_call": _now_iso(),
        }

        decision_patch: dict[str, Any] = {
            "maintain_plan": decision.maintain_plan,
            "reasoning": decision.reasoning,
            "cost_usd": decision.cost_usd,
            "micro_adjustments": [
                {
                    "action_type": action.action_type,
                    "coin": action.coin,
                    "size": action.size,
                    "market_type": action.market_type,
                    "reasoning": action.reasoning,
                }
                for action in decision.micro_adjustments or []
            ],
        }

        patch: StatePatch = {
            "telemetry": telemetry_patch,
            "governance": {
                "active_plan": serialize_plan(plan),
            },
            "medium": {
                "llm_decision": decision_patch,
            },
        }

        if not decision.success:
            decision_patch["error"] = decision.error
            if run is not None:
                run.add_outputs(summarize_patch({"medium": decision_patch}))
            return patch

        if decision.proposed_plan is not None:
            raise GraphInterrupt(
                [
                    Interrupt(
                        value={
                            "type": "plan_change_proposed",
                            "plan": decision.proposed_plan.to_dict(),
                            "reasoning": decision.reasoning,
                            "cost_usd": decision.cost_usd,
                        }
                    )
                ]
            )

        if run is not None:
            run.add_outputs(summarize_patch({"medium": decision_patch}))
        return patch


__all__ = ["llm_decision_engine"]
