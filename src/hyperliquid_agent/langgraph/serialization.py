"""Serialization helpers for LangGraph state patches."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from hyperliquid_agent.governance.plan_card import StrategyPlanCard
from hyperliquid_agent.monitor import AccountState
from hyperliquid_agent.signals.models import EnhancedAccountState


def _to_serializable(value: Any) -> Any:
    """Convert dataclasses / datetimes into JSON-friendly types."""

    if is_dataclass(value):
        return {key: _to_serializable(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_serializable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def serialize_account_state(state: AccountState | EnhancedAccountState | None) -> dict[str, Any]:
    """Serialize account state dataclasses for graph state storage."""

    if state is None:
        return {}
    return _to_serializable(state)


def serialize_plan(plan: StrategyPlanCard | None) -> dict[str, Any] | None:
    """Serialize plan cards into dicts when present."""

    if plan is None:
        return None
    return _to_serializable(plan)


__all__ = ["serialize_account_state", "serialize_plan"]
