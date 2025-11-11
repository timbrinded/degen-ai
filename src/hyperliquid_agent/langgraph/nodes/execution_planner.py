"""Execution planner node bridging StrategyGovernor and TradeExecutor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import FAST_LOOP, FastLoopState, GlobalState, StatePatch


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def execution_planner(state: GlobalState, config: Config) -> StatePatch:
    """Produce a lightweight execution patch to keep LangGraph wiring functional."""

    fast_state = cast(FastLoopState, state.get("fast", {}) or {})
    plan = fast_state.get("plan") or {}
    allocations = plan.get("target_allocations") or []

    planned_actions = [
        {
            "coin": alloc.get("coin"),
            "market_type": alloc.get("market_type", "perp"),
            "target_pct": alloc.get("target_pct"),
            "strategy_name": plan.get("strategy_name"),
        }
        for alloc in allocations
    ]

    telemetry = cast(dict[str, Any], state.get("telemetry", {}) or {})

    patch: StatePatch = {
        "fast": {
            "execution": {
                "pending_actions": planned_actions,
                "last_plan_id": plan.get("plan_id"),
                "last_execution_at": _now_iso(),
                "summary": f"{len(planned_actions)} actions planned",
            }
        }
    }

    metadata = {
        "loop": FAST_LOOP,
        "tick": fast_state.get("tick_id", 0),
        "actions": len(planned_actions),
        "langgraph_phase": telemetry.get("langgraph_phase"),
        "snapshot_id": telemetry.get("last_snapshot_id"),
    }
    with node_trace("execution_planner", metadata=metadata, inputs={"has_plan": bool(plan)}) as run:
        if run is not None:
            run.add_outputs(summarize_patch(patch))
    return patch


__all__ = ["execution_planner"]
