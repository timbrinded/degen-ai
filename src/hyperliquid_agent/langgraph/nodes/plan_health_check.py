"""Plan health node that feeds the medium loop."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import MEDIUM_LOOP, GlobalState, StatePatch


def plan_health_check(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Assess plan health + review windows before invoking LLM."""

    plan = context.governor.active_plan
    account_state = context.cache.get("medium_account_state") or context.cache.get(
        "fast_account_state"
    )
    if plan is None or account_state is None:
        return {}

    now = datetime.now(UTC)
    can_review, review_reason = context.governor.can_review_plan(now)
    in_event_lock, event_reason = context.regime_detector.is_in_event_lock_window(now)
    effective_can_review = can_review and not in_event_lock

    if context.scorekeeper.active_metrics is None:
        context.scorekeeper.start_tracking_plan(plan, account_state.portfolio_value)
    context.scorekeeper.update_metrics(account_state, plan)
    metrics = context.scorekeeper.active_metrics

    metadata = {
        "loop": MEDIUM_LOOP,
        "plan_id": plan.plan_id,
        "can_review": effective_can_review,
    }

    with node_trace("plan_health_check", metadata=metadata) as run:
        plan_health: dict[str, Any] = {
            "can_review": effective_can_review,
            "review_reason": event_reason if in_event_lock else review_reason,
            "regime": context.regime_detector.current_regime,
            "last_review_at": now.isoformat(),
        }
        if metrics:
            plan_health["plan_metrics"] = asdict(metrics)

        patch: StatePatch = {
            "medium": {
                "plan_health": plan_health,
                "last_review_at": now.isoformat(),
            }
        }

        if run is not None:
            run.add_outputs(summarize_patch({"medium": plan_health}))
        return patch


__all__ = ["plan_health_check"]
