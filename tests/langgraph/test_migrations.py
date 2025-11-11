"""Tests for LangGraph state migrations."""

from hyperliquid_agent.langgraph.migrations import (
    LANGGRAPH_STATE_VERSION,
    ensure_state_version,
)
from hyperliquid_agent.langgraph.state import GlobalState


def test_ensure_state_version_sets_defaults() -> None:
    state: GlobalState = {"telemetry": {}, "governance": {}}
    migrated = ensure_state_version(state)

    assert migrated["telemetry"]["state_version"] == LANGGRAPH_STATE_VERSION
    assert migrated["governance"]["plan_history"] == []
    assert migrated["governance"]["interrupts"] == []
    assert migrated["scheduler"]["pending_loops"] == []
