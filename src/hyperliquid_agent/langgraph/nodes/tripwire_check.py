"""LangGraph node that mirrors `TripwireService.detect` outputs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import (
    FAST_LOOP,
    FastLoopState,
    GlobalState,
    StatePatch,
    TripwireState,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def tripwire_check(state: GlobalState, config: Config) -> StatePatch:
    """Project tripwire detections into LangGraph-compatible patches."""

    fast_state = cast(FastLoopState, state.get("fast", {}) or {})
    existing_tripwire = cast(TripwireState, fast_state.get("tripwire", {}) or {})
    violations = existing_tripwire.get("violations", [])
    emergency = bool(violations)

    patch: StatePatch = {
        "fast": {
            "tripwire": {
                "violations": violations,
                "last_run": _now_iso(),
                "emergency_unwind_required": emergency,
                "suppressed": existing_tripwire.get("suppressed", []),
            },
        },
        "governance": {
            "tripwire": {
                "violations": violations,
                "last_run": _now_iso(),
                "emergency_unwind_required": emergency,
            },
        },
    }

    metadata = {
        "loop": FAST_LOOP,
        "tick": fast_state.get("tick_id", 0),
        "violation_count": len(violations),
    }
    with node_trace(
        "tripwire_check", metadata=metadata, inputs={"has_violations": emergency}
    ) as run:
        if run is not None:
            run.add_outputs(summarize_patch(patch))
    return patch


__all__ = ["tripwire_check"]
