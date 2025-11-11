"""Typed state models and snapshot helpers for LangGraph scaffolding.

The structures mirror the imperative governed agent components defined in:
- `hyperliquid_agent.monitor_enhanced.EnhancedPositionMonitor`
- `hyperliquid_agent.governance` modules (governor, tripwire, regime detector)
- `hyperliquid_agent.governed_agent.GovernedTradingAgent`

Phase 1 only needs lightweight schema definitions plus helpers to hydrate state from the
Phase 0 snapshots stored under `state/snapshots/`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, TypedDict, cast

SNAPSHOT_SCHEMA = "degen-ai.snapshot.v1"
FAST_LOOP = "fast"
MEDIUM_LOOP = "medium"
SLOW_LOOP = "slow"


class TelemetryState(TypedDict, total=False):
    """Global telemetry used by the scheduler and observability sinks."""

    tick: int
    last_loop: str | None
    last_snapshot_id: str | None
    langgraph_phase: str | None
    trace_id: str | None
    llm_cost_usd: float
    total_actions: int
    state_version: int


class TripwireState(TypedDict, total=False):
    """Tripwire status surface derived from `TripwireService`."""

    violations: list[dict[str, Any]]
    last_run: str | None
    emergency_unwind_required: bool
    suppressed: list[str]


class ExecutionState(TypedDict, total=False):
    """Execution bookkeeping for `TradeExecutor` patches."""

    pending_actions: list[dict[str, Any]]
    last_execution_at: str | None
    last_plan_id: str | None
    summary: str | None


class FastLoopState(TypedDict, total=False):
    """Serialized inputs/outputs for the fast loop pipeline."""

    tick_id: int
    account_state: dict[str, Any]
    plan: dict[str, Any] | None
    signals: dict[str, Any]
    tripwire: TripwireState
    execution: ExecutionState


class MediumLoopState(TypedDict, total=False):
    """Serialized plan maintenance inputs for the medium loop."""

    plan_health: dict[str, Any]
    llm_context: dict[str, Any]
    pending_proposals: list[dict[str, Any]]
    last_review_at: str | None


class SlowLoopState(TypedDict, total=False):
    """Serialized macro / regime context for the slow loop."""

    regime_snapshot: dict[str, Any]
    macro_events: list[dict[str, Any]]
    data_window_hours: int | None
    last_detection_at: str | None


class GovernanceState(TypedDict, total=False):
    """State shared between loops for governance + plan enforcement."""

    active_plan: dict[str, Any] | None
    approved_plan: dict[str, Any] | None
    plan_history: list[dict[str, Any]]
    regime: dict[str, Any]
    tripwire: TripwireState
    interrupts: list[dict[str, Any]]


class SchedulerState(TypedDict, total=False):
    """Timestamps used to decide which loop should run next."""

    fast_last_run: str | None
    medium_last_run: str | None
    slow_last_run: str | None
    pending_loops: list[str]
    next_loop: str | None


class GlobalState(TypedDict, total=False):
    """Canonical LangGraph state tree."""

    fast: FastLoopState
    medium: MediumLoopState
    slow: SlowLoopState
    governance: GovernanceState
    telemetry: TelemetryState
    scheduler: SchedulerState


StatePatch = dict[str, Any]


@dataclass(slots=True)
class SnapshotMetadata:
    """Metadata describing a stored snapshot."""

    path: Path
    loop_type: str
    captured_at: str
    schema: str
    snapshot_id: str
    tick: int | None = None

    @property
    def tag(self) -> str:
        """Friendly identifier for logs and traces."""

        return f"{self.loop_type}:{self.snapshot_id}"


class SnapshotPayload(TypedDict, total=False):
    """Wire schema for serialized Phase 0 snapshots."""

    schema: str
    loop_type: str
    captured_at: str
    account_state: dict[str, Any]
    plan: dict[str, Any] | None
    governance: dict[str, Any]
    regime: dict[str, Any]
    extra: NotRequired[dict[str, Any]]


def empty_state() -> GlobalState:
    """Return a zeroed-out state tree suitable for initializing the graph."""

    return {
        "fast": cast(FastLoopState, {}),
        "medium": cast(MediumLoopState, {}),
        "slow": cast(SlowLoopState, {}),
        "governance": cast(GovernanceState, {}),
        "telemetry": cast(TelemetryState, {}),
        "scheduler": cast(SchedulerState, {"pending_loops": []}),
    }


def load_snapshot(path: str | Path) -> tuple[SnapshotMetadata, SnapshotPayload]:
    """Load a stored snapshot JSON document."""

    snapshot_path = Path(path)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    metadata = SnapshotMetadata(
        path=snapshot_path,
        loop_type=str(payload.get("loop_type", FAST_LOOP)),
        captured_at=str(payload.get("captured_at", "")),
        schema=str(payload.get("schema", SNAPSHOT_SCHEMA)),
        snapshot_id=snapshot_path.stem,
        tick=payload.get("extra", {}).get("tick")
        if isinstance(payload.get("extra"), dict)
        else None,
    )
    return metadata, payload  # type: ignore[return-value]


def bootstrap_state_from_snapshot(path: str | Path) -> tuple[SnapshotMetadata, GlobalState]:
    """Hydrate a `GlobalState` structure from a stored snapshot file."""

    metadata, payload = load_snapshot(path)
    state = empty_state()

    fast_state: FastLoopState = state.setdefault("fast", {})
    fast_state["account_state"] = payload.get("account_state", {})
    fast_state["plan"] = payload.get("plan")
    fast_state.setdefault("tripwire", cast(TripwireState, {}))
    fast_state.setdefault("execution", cast(ExecutionState, {}))
    if metadata.tick is not None:
        fast_state["tick_id"] = metadata.tick

    telemetry: TelemetryState = state.setdefault("telemetry", {})
    telemetry["tick"] = metadata.tick or 0
    telemetry["last_loop"] = metadata.loop_type
    telemetry["last_snapshot_id"] = metadata.snapshot_id

    governance: GovernanceState = state.setdefault("governance", {})
    governance["active_plan"] = payload.get("plan")
    governance["tripwire"] = payload.get("governance", {}).get("tripwire", cast(TripwireState, {}))
    governance["regime"] = payload.get("regime", {})
    governance["plan_history"] = []
    governance["interrupts"] = []

    slow_state: SlowLoopState = state.setdefault("slow", {})
    slow_state["regime_snapshot"] = payload.get("regime", {})
    slow_state["macro_events"] = payload.get("regime", {}).get("macro_events", [])
    slow_state["last_detection_at"] = payload.get("captured_at")

    scheduler: SchedulerState = state.setdefault("scheduler", {"pending_loops": []})
    scheduler["fast_last_run"] = payload.get("captured_at")
    scheduler["pending_loops"] = []

    return metadata, state


def list_snapshot_files(snapshot_dir: str | Path, *, loop_type: str | None = None) -> list[Path]:
    """Enumerate snapshot files for dry-run tooling."""

    directory = Path(snapshot_dir)
    if not directory.exists():
        return []

    files = sorted(directory.glob("*.json"))
    if loop_type:
        return [path for path in files if f"{loop_type}-" in path.name or loop_type in path.stem]
    return files


__all__ = [
    "FAST_LOOP",
    "MEDIUM_LOOP",
    "SLOW_LOOP",
    "ExecutionState",
    "FastLoopState",
    "GovernanceState",
    "GlobalState",
    "SchedulerState",
    "SnapshotMetadata",
    "SnapshotPayload",
    "StatePatch",
    "TelemetryState",
    "TripwireState",
    "bootstrap_state_from_snapshot",
    "empty_state",
    "list_snapshot_files",
    "load_snapshot",
]
