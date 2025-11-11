"""LangGraph node that wraps `EnhancedPositionMonitor` + signal ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import FAST_LOOP, FastLoopState, GlobalState, StatePatch


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def collect_signals(state: GlobalState, config: Config) -> StatePatch:
    """Project monitor + signal payloads into the LangGraph state tree.

    Phase 1 keeps the implementation lightweight by reading the latest serialized snapshot
    fields produced by `EnhancedPositionMonitor` and the signal caches. Later phases will
    call the live services directly.
    """

    fast_state = cast(FastLoopState, state.get("fast", {}) or {})
    account_state = cast(dict[str, Any], fast_state.get("account_state", {}) or {})
    tick = fast_state.get("tick_id", 0)
    fast_signals = account_state.get("fast_signals", {})

    telemetry = cast(dict[str, Any], state.get("telemetry", {}) or {})

    patch: StatePatch = {
        "fast": {
            "signals": fast_signals,
            "account_state": account_state,
        },
        "telemetry": {
            "tick": tick,
            "last_loop": FAST_LOOP,
            "last_snapshot_id": telemetry.get("last_snapshot_id"),
            "langgraph_phase": telemetry.get("langgraph_phase", "phase_1"),
            "trace_id": telemetry.get("trace_id"),
        },
    }

    metadata = {
        "loop": FAST_LOOP,
        "tick": tick,
        "langgraph_phase": telemetry.get("langgraph_phase"),
        "snapshot_id": telemetry.get("last_snapshot_id"),
    }
    with node_trace(
        "collect_signals", metadata=metadata, inputs={"has_signals": bool(fast_signals)}
    ) as run:
        if run is not None:
            run.add_outputs(
                {
                    **summarize_patch({"fast": patch["fast"]}),
                    "collected_at": _now_iso(),
                }
            )
    return patch


__all__ = ["collect_signals"]
