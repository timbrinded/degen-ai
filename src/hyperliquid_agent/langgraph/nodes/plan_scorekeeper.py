"""Plan scorekeeper node backed by `PlanScorekeeper` heuristics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import GlobalState, GovernanceState, StatePatch


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def plan_scorekeeper(state: GlobalState, config: Config) -> StatePatch:
    """Stub for plan scorekeeping logic.

    The governed agent already records plan KPIs via `PlanScorekeeper`. This node simply
    mirrors that metadata into the LangGraph state so the graph can route on it in later
    phases.
    """

    governance = cast(GovernanceState, state.get("governance", {}) or {})
    active_plan = governance.get("active_plan") or {}
    regime = governance.get("regime") or {}

    score_entry = {
        "plan_id": active_plan.get("plan_id"),
        "regime": regime.get("label"),
        "timestamp": _now_iso(),
        "kpis": {
            "expected_edge_bps": active_plan.get("expected_edge_bps"),
            "rebalance_progress_pct": active_plan.get("rebalance_progress_pct"),
        },
    }

    telemetry = cast(dict[str, Any], state.get("telemetry", {}) or {})

    patch: StatePatch = {
        "governance": {
            "plan_history": [score_entry],
        },
        "medium": {
            "plan_health": {
                "last_score": score_entry,
            },
            "last_review_at": score_entry["timestamp"],
        },
    }

    metadata = {
        "plan_id": score_entry["plan_id"],
        "regime": score_entry["regime"],
        "langgraph_phase": telemetry.get("langgraph_phase"),
        "snapshot_id": telemetry.get("last_snapshot_id"),
    }
    with node_trace(
        "plan_scorekeeper", metadata=metadata, inputs={"has_plan": bool(score_entry["plan_id"])}
    ) as run:
        if run is not None:
            run.add_outputs(summarize_patch(patch))
    return patch


__all__ = ["plan_scorekeeper"]
