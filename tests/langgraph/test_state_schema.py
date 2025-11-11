"""Tests for LangGraph state serialization helpers."""

from __future__ import annotations

from pathlib import Path

from hyperliquid_agent.langgraph.state import (
    FAST_LOOP,
    bootstrap_state_from_snapshot,
    list_snapshot_files,
)

SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "state" / "snapshots"


def test_bootstrap_state_from_snapshot_loads_fast_snapshot():
    """Ensure baseline snapshot hydrates a typed state tree."""

    metadata, state = bootstrap_state_from_snapshot(SNAPSHOT_DIR / "sample_fast_loop.json")

    assert metadata.loop_type == FAST_LOOP
    assert metadata.schema == "degen-ai.snapshot.v1"
    assert state["fast"]["account_state"]["portfolio_value"] == 125000.0
    assert state["telemetry"]["last_loop"] == FAST_LOOP
    active_plan = state["governance"]["active_plan"]
    assert active_plan is not None
    assert active_plan["plan_id"] == "carry-001"


def test_list_snapshot_files_filters_by_loop():
    """Loop filter should limit enumerated files."""

    fast_files = list_snapshot_files(SNAPSHOT_DIR, loop_type="fast")
    assert fast_files, "expected fixture directory to include at least one fast snapshot"
    for path in fast_files:
        assert "fast" in path.stem
