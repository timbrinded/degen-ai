"""Plan scorekeeper node backed by `PlanScorekeeper` heuristics."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import GlobalState, StatePatch


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def plan_scorekeeper(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Mirror PlanScorekeeper metrics into LangGraph state."""

    plan = context.governor.active_plan
    account_state = context.cache.get("medium_account_state") or context.cache.get(
        "fast_account_state"
    )
    if plan is None or account_state is None:
        return {}

    metadata = {
        "plan_id": plan.plan_id,
    }

    with node_trace("plan_scorekeeper", metadata=metadata) as run:
        tracked_plan_id = context.cache.get("scorekeeper_plan_id")
        if tracked_plan_id != plan.plan_id:
            context.scorekeeper.start_tracking_plan(plan, account_state.portfolio_value)
            context.cache["scorekeeper_plan_id"] = plan.plan_id

        context.scorekeeper.update_metrics(account_state, plan)
        metrics = context.scorekeeper.active_metrics
        metrics_dict = asdict(metrics) if metrics else {}
        metrics_dict["timestamp"] = _now_iso()

        patch: StatePatch = {
            "governance": {
                "plan_history": [metrics_dict],
            },
            "medium": {
                "plan_health": {
                    "last_score": metrics_dict,
                },
                "last_review_at": metrics_dict["timestamp"],
            },
        }

        if run is not None:
            run.add_outputs(summarize_patch({"governance": patch["governance"]}))
        return patch


__all__ = ["plan_scorekeeper"]
