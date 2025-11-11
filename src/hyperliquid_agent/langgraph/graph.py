"""LangGraph StateGraph scaffolding for the governed trading agent."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver  # type: ignore[import-not-found]

try:  # Optional extra installed via langgraph[sqlite]
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    SqliteSaver = None  # type: ignore[assignment]
from langgraph.graph import END, START, StateGraph

from hyperliquid_agent.config import Config, LangGraphConfig
from hyperliquid_agent.langgraph.nodes import (
    collect_signals,
    execution_planner,
    plan_scorekeeper,
    regime_detector,
    tripwire_check,
)
from hyperliquid_agent.langgraph.state import (
    FAST_LOOP,
    GlobalState,
    SnapshotMetadata,
    StatePatch,
    bootstrap_state_from_snapshot,
    list_snapshot_files,
)


def _deep_merge(target: StatePatch, incoming: StatePatch) -> StatePatch:
    """Recursively merge state patches."""

    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)  # type: ignore[arg-type]
        else:
            target[key] = value
    return target


def _merge_patches(*patches: StatePatch) -> StatePatch:
    merged: StatePatch = {}
    for patch in patches:
        _deep_merge(merged, patch)
    return merged


def _scheduler_node(state: GlobalState, *, app_config: Config) -> StatePatch:
    """Seed telemetry values + pending loop order."""

    langgraph_cfg = app_config.langgraph or LangGraphConfig()
    telemetry = state.get("telemetry", {}) or {}
    pending = ["fast_loop", "medium_loop", "slow_loop"]
    patch: StatePatch = {
        "telemetry": {
            **telemetry,
            "langgraph_phase": langgraph_cfg.phase_tag,
            "last_loop": telemetry.get("last_loop", "scheduler"),
        },
        "scheduler": {
            "pending_loops": pending,
        },
    }
    return patch


def _fast_loop_node(state: GlobalState, *, app_config: Config) -> StatePatch:
    patch = _merge_patches(
        collect_signals(state, app_config),
        tripwire_check(state, app_config),
        execution_planner(state, app_config),
    )
    patch.setdefault("telemetry", {})["last_loop"] = FAST_LOOP
    return patch


def _medium_loop_node(state: GlobalState, *, app_config: Config) -> StatePatch:
    return plan_scorekeeper(state, app_config)


def _slow_loop_node(state: GlobalState, *, app_config: Config) -> StatePatch:
    return regime_detector(state, app_config)


def _build_checkpointer(config: Config):
    """Instantiate a LangGraph checkpointer per config."""

    langgraph_cfg = config.langgraph or LangGraphConfig()
    if langgraph_cfg.checkpoint_backend == "sqlite":
        if SqliteSaver is None:
            # Fallback gracefully when sqlite extra is unavailable; MemorySaver keeps scaffolding usable.
            return MemorySaver()
        storage_path = Path(langgraph_cfg.storage_path)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteSaver(str(storage_path))
    return MemorySaver()


def build_langgraph(config: Config):
    """Compile the scaffolding StateGraph."""

    graph = StateGraph(GlobalState)
    graph.add_node("scheduler", partial(_scheduler_node, app_config=config))
    graph.add_node("fast_loop", partial(_fast_loop_node, app_config=config))
    graph.add_node("medium_loop", partial(_medium_loop_node, app_config=config))
    graph.add_node("slow_loop", partial(_slow_loop_node, app_config=config))

    graph.add_edge(START, "scheduler")
    graph.add_edge("scheduler", "fast_loop")
    graph.add_edge("fast_loop", "medium_loop")
    graph.add_edge("medium_loop", "slow_loop")
    graph.add_edge("slow_loop", END)

    return graph.compile(checkpointer=_build_checkpointer(config))


def load_dry_run_state(
    config: Config,
    *,
    snapshot_path: str | Path | None = None,
    loop_type: str | None = FAST_LOOP,
) -> tuple[SnapshotMetadata, GlobalState]:
    """Locate and load a snapshot for LangGraph dry-runs."""

    langgraph_cfg = config.langgraph or LangGraphConfig()
    if snapshot_path is not None:
        return bootstrap_state_from_snapshot(snapshot_path)

    snapshot_dir = Path(langgraph_cfg.snapshot_dir)
    candidates = list_snapshot_files(snapshot_dir, loop_type=loop_type)
    if not candidates:
        raise FileNotFoundError(f"No snapshots found in {snapshot_dir} (loop={loop_type or 'any'})")
    return bootstrap_state_from_snapshot(candidates[-1])


__all__ = ["build_langgraph", "load_dry_run_state"]
