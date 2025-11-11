"""LangGraph node that hydrates live account + signal state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext, LoopName
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.serialization import serialize_account_state, serialize_plan
from hyperliquid_agent.langgraph.state import (
    FAST_LOOP,
    MEDIUM_LOOP,
    SLOW_LOOP,
    GlobalState,
    StatePatch,
)

LOOP_TO_BRANCH = {
    FAST_LOOP: "fast",
    MEDIUM_LOOP: "medium",
    SLOW_LOOP: "slow",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def collect_signals(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
    loop: LoopName = FAST_LOOP,
) -> StatePatch:
    """Collect the latest account snapshot + loop-specific signals."""

    branch = LOOP_TO_BRANCH[loop]
    plan = context.governor.active_plan
    metadata = {
        "loop": loop,
        "plan_id": plan.plan_id if plan else None,
        "langgraph_phase": context.langgraph_config.phase_tag,
    }

    with node_trace("collect_signals", metadata=metadata) as run:
        account_state = context.monitor.get_current_state_with_signals(loop, active_plan=plan)
        context.cache[f"{loop}_account_state"] = account_state
        serialized_state = serialize_account_state(account_state)

        loop_patch: dict[str, Any] = {
            "account_state": serialized_state,
            "tick_id": int(account_state.timestamp),
        }
        if loop == FAST_LOOP and account_state.fast_signals:
            loop_patch["signals"] = serialized_state.get("fast_signals")
        elif loop == MEDIUM_LOOP and account_state.medium_signals:
            loop_patch["signals"] = serialized_state.get("medium_signals")
        elif loop == SLOW_LOOP and account_state.slow_signals:
            loop_patch["signals"] = serialized_state.get("slow_signals")

        existing_telemetry = dict(state.get("telemetry", {}) or {})
        telemetry_patch: dict[str, Any] = {
            **existing_telemetry,
            "tick": int(account_state.timestamp),
            "last_loop": loop,
            "langgraph_phase": context.langgraph_config.phase_tag,
            "collected_at": _now_iso(),
        }

        existing_scheduler = dict(state.get("scheduler", {}) or {})
        scheduler_patch = {
            **existing_scheduler,
            f"{branch}_last_run": telemetry_patch["collected_at"],
        }

        patch: StatePatch = {
            branch: loop_patch,
            "governance": {
                "active_plan": serialize_plan(plan),
            },
            "telemetry": telemetry_patch,
            "scheduler": scheduler_patch,
        }

        if run is not None:
            run.add_outputs(
                {
                    **summarize_patch({branch: loop_patch}),
                    "collected_at": telemetry_patch["collected_at"],
                }
            )
        return patch


__all__ = ["collect_signals"]
