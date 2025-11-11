"""Regime detector node mirroring `RegimeDetector.classify` outputs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import GlobalState, SlowLoopState, StatePatch


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def regime_detector(state: GlobalState, config: Config) -> StatePatch:
    """Populate slow-loop + governance regime snapshots."""

    slow_state = cast(SlowLoopState, state.get("slow", {}) or {})
    regime_snapshot = cast(dict[str, Any], slow_state.get("regime_snapshot") or {})
    macro_events = slow_state.get("macro_events") or regime_snapshot.get("macro_events") or []
    current_regime = regime_snapshot.get("current_regime")

    telemetry = cast(dict[str, Any], state.get("telemetry", {}) or {})

    patch: StatePatch = {
        "slow": {
            "regime_snapshot": regime_snapshot,
            "macro_events": macro_events,
            "last_detection_at": _now_iso(),
        },
        "governance": {
            "regime": {
                "label": current_regime,
                "updated_at": _now_iso(),
                "macro_events": macro_events,
            }
        },
    }

    metadata = {
        "regime": current_regime,
        "macro_events": len(macro_events),
        "langgraph_phase": telemetry.get("langgraph_phase"),
        "snapshot_id": telemetry.get("last_snapshot_id"),
    }
    with node_trace(
        "regime_detector", metadata=metadata, inputs={"has_regime": bool(current_regime)}
    ) as run:
        if run is not None:
            run.add_outputs(summarize_patch(patch))
    return patch


__all__ = ["regime_detector"]
