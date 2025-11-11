"""State migration helpers for persisted LangGraph checkpoints."""

from __future__ import annotations

from hyperliquid_agent.langgraph.state import (
    GlobalState,
    GovernanceState,
    MediumLoopState,
    SchedulerState,
    TelemetryState,
)

LANGGRAPH_STATE_VERSION = 3


def ensure_state_version(state: GlobalState) -> GlobalState:
    """Upgrade a persisted state tree to the current schema version."""

    telemetry: TelemetryState = state.setdefault("telemetry", {})
    prior_version = int(telemetry.get("state_version", 0) or 0)

    if prior_version < 2:
        governance: GovernanceState = state.setdefault("governance", {})
        governance.setdefault("plan_history", [])
        governance.setdefault("interrupts", [])
        telemetry.setdefault("llm_cost_usd", 0.0)

    if prior_version < 3:
        scheduler: SchedulerState = state.setdefault("scheduler", {"pending_loops": []})
        scheduler.setdefault("pending_loops", [])
        scheduler.setdefault("next_loop", "idle")
        medium: MediumLoopState = state.setdefault("medium", {})
        medium.setdefault("pending_proposals", [])

    telemetry["state_version"] = LANGGRAPH_STATE_VERSION
    return state


__all__ = ["LANGGRAPH_STATE_VERSION", "ensure_state_version"]
