"""LangGraph StateGraph scaffolding for the governed trading agent."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver  # type: ignore[import-not-found]

try:  # Optional extra installed via langgraph[sqlite]
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    SqliteSaver = None  # type: ignore[assignment]
from langgraph.graph import END, START, StateGraph

from hyperliquid_agent.config import Config, LangGraphConfig
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.nodes import (
    collect_signals,
    emergency_unwind,
    execution_planner,
    llm_decision_engine,
    plan_health_check,
    plan_scorekeeper,
    regime_data_prep,
    regime_detector,
    strategy_governor,
    trade_executor,
    tripwire_check,
)
from hyperliquid_agent.langgraph.state import (
    FAST_LOOP,
    MEDIUM_LOOP,
    GlobalState,
    SnapshotMetadata,
    StatePatch,
    bootstrap_state_from_snapshot,
    list_snapshot_files,
)


def _scheduler_node(state: GlobalState, *, context: LangGraphRuntimeContext) -> StatePatch:
    """Decide which loop should run next."""

    scheduler: dict[str, Any] = dict(state.get("scheduler", {}) or {})
    raw_pending = scheduler.get("pending_loops", [])
    pending: list[str] = list(raw_pending) if isinstance(raw_pending, list) else []
    now = datetime.now(UTC)

    def _interval_seconds(loop: str) -> int:
        if loop == "fast":
            return context.governance.fast_loop_interval_seconds
        if loop == "medium":
            return context.governance.medium_loop_interval_minutes * 60
        return context.governance.slow_loop_interval_hours * 3600

    def _due(loop: str) -> bool:
        last_run = scheduler.get(f"{loop}_last_run")
        if not isinstance(last_run, str):
            return True
        try:
            last_dt = datetime.fromisoformat(last_run)
        except ValueError:
            return True
        return (now - last_dt).total_seconds() >= _interval_seconds(loop)

    if not pending:
        if _due("fast"):
            pending.append("fast_loop")
        if _due("medium"):
            pending.append("medium_loop")
        if _due("slow"):
            pending.append("slow_loop")

    next_loop = pending.pop(0) if pending else "idle"
    scheduler["pending_loops"] = pending
    scheduler["next_loop"] = next_loop

    telemetry = state.get("telemetry", {}) or {}
    telemetry_patch = {
        **telemetry,
        "langgraph_phase": context.langgraph_config.phase_tag,
        "last_loop": telemetry.get("last_loop", "scheduler"),
        "scheduler_run_at": now.isoformat(),
    }

    return {
        "telemetry": telemetry_patch,
        "scheduler": scheduler,
    }


def _scheduler_router(state: GlobalState) -> str:
    scheduler = state.get("scheduler", {}) or {}
    next_loop = scheduler.get("next_loop")
    return next_loop if isinstance(next_loop, str) else "idle"


def _build_fast_subgraph(config: Config, context: LangGraphRuntimeContext):
    graph = StateGraph(GlobalState)
    graph.add_node(
        "collect_signals",
        partial(collect_signals, config=config, context=context, loop=FAST_LOOP),
    )
    graph.add_node("tripwire_check", partial(tripwire_check, config=config, context=context))
    graph.add_node("execution_planner", partial(execution_planner, config=config, context=context))
    graph.add_node("trade_executor", partial(trade_executor, config=config, context=context))
    graph.add_node("emergency_unwind", partial(emergency_unwind, config=config, context=context))

    graph.add_edge(START, "collect_signals")
    graph.add_edge("collect_signals", "tripwire_check")
    graph.add_conditional_edges(
        "tripwire_check",
        lambda state: (
            "emergency"
            if (state.get("fast", {}).get("tripwire") or {}).get("emergency_unwind_required")
            else "normal"
        ),
        {
            "emergency": "emergency_unwind",
            "normal": "execution_planner",
        },
    )
    graph.add_edge("execution_planner", "trade_executor")
    graph.add_edge("trade_executor", END)
    graph.add_edge("emergency_unwind", END)
    return graph.compile()


def _build_medium_subgraph(config: Config, context: LangGraphRuntimeContext):
    graph = StateGraph(GlobalState)
    graph.add_node(
        "collect_signals",
        partial(collect_signals, config=config, context=context, loop=MEDIUM_LOOP),
    )
    graph.add_node("plan_health_check", partial(plan_health_check, config=config, context=context))
    graph.add_node(
        "llm_decision_engine", partial(llm_decision_engine, config=config, context=context)
    )
    graph.add_node("plan_scorekeeper", partial(plan_scorekeeper, config=config, context=context))

    graph.add_edge(START, "collect_signals")
    graph.add_edge("collect_signals", "plan_health_check")
    graph.add_edge("plan_health_check", "llm_decision_engine")
    graph.add_edge("llm_decision_engine", "plan_scorekeeper")
    graph.add_edge("plan_scorekeeper", END)
    return graph.compile()


def _build_slow_subgraph(config: Config, context: LangGraphRuntimeContext):
    graph = StateGraph(GlobalState)
    graph.add_node("regime_data_prep", partial(regime_data_prep, config=config, context=context))
    graph.add_node("regime_detector", partial(regime_detector, config=config, context=context))
    graph.add_node("strategy_governor", partial(strategy_governor, config=config, context=context))

    graph.add_edge(START, "regime_data_prep")
    graph.add_edge("regime_data_prep", "regime_detector")
    graph.add_edge("regime_detector", "strategy_governor")
    graph.add_edge("strategy_governor", END)
    return graph.compile()


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


def build_langgraph(
    config: Config,
    *,
    context: LangGraphRuntimeContext | None = None,
):
    """Compile the LangGraph runtime accompanied by its shared context."""

    runtime = context or LangGraphRuntimeContext.from_config(config)
    graph = StateGraph(GlobalState)
    graph.add_node("scheduler", partial(_scheduler_node, context=runtime))
    graph.add_node("fast_loop", _build_fast_subgraph(config, runtime))
    graph.add_node("medium_loop", _build_medium_subgraph(config, runtime))
    graph.add_node("slow_loop", _build_slow_subgraph(config, runtime))

    graph.add_edge(START, "scheduler")
    graph.add_conditional_edges(
        "scheduler",
        _scheduler_router,
        {
            "fast_loop": "fast_loop",
            "medium_loop": "medium_loop",
            "slow_loop": "slow_loop",
            "idle": END,
        },
    )
    graph.add_edge("fast_loop", "scheduler")
    graph.add_edge("medium_loop", "scheduler")
    graph.add_edge("slow_loop", "scheduler")

    compiled = graph.compile(checkpointer=_build_checkpointer(config))
    return compiled, runtime


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
