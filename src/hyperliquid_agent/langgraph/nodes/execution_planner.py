"""Execution planner node bridging StrategyGovernor and TradeExecutor."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.serialization import serialize_plan
from hyperliquid_agent.langgraph.state import FAST_LOOP, GlobalState, StatePatch

ALLOCATION_THRESHOLD_PCT = 1.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _build_alias_map(account_state) -> dict[str, str]:
    alias_map: dict[str, str] = {"USDC": "USDC"}
    assets = getattr(account_state, "assets", {}) or {}
    for canonical, identity in assets.items():
        alias_map[canonical.upper()] = canonical
        alias_map[identity.wallet_symbol.upper()] = canonical
        for alias in identity.all_aliases:
            alias_map[alias.upper()] = canonical
    return alias_map


def _resolve_canonical(symbol: str, alias_map: dict[str, str]) -> str:
    if not symbol:
        return symbol
    upper = symbol.upper()
    return alias_map.get(upper, upper)


def _resolve_price(
    account_state, canonical: str, raw_symbol: str, alias_map: dict[str, str]
) -> float:
    positions = getattr(account_state, "positions", []) or []
    price_map = getattr(account_state, "price_map", {}) or {}
    for position in positions:
        identity = getattr(position, "asset_identity", None)
        candidate = (
            identity.canonical_symbol
            if identity and getattr(identity, "canonical_symbol", None)
            else _resolve_canonical(position.coin, alias_map)
        )
        if candidate == canonical:
            return position.current_price
    # Fallback to watchlist price
    if raw_symbol in price_map:
        return price_map[raw_symbol]
    if canonical in price_map:
        return price_map[canonical]
    if raw_symbol.upper().startswith("U") and raw_symbol[1:] in price_map:
        return price_map[raw_symbol[1:]]
    return 0.0


def _compute_current_allocations(account_state) -> dict[tuple[str, str], float]:
    allocations: dict[tuple[str, str], float] = defaultdict(float)
    total_value = max(account_state.portfolio_value, 1e-9)
    alias_map = _build_alias_map(account_state)
    for position in getattr(account_state, "positions", []) or []:
        canonical = _resolve_canonical(position.coin, alias_map)
        key = (canonical, position.market_type)
        value = abs(position.size * position.current_price)
        allocations[key] += (value / total_value) * 100
    return allocations


def _plan_rebalance_actions(plan, account_state) -> list[dict[str, Any]]:
    if plan is None or not getattr(plan, "target_allocations", None):
        return []

    alias_map = _build_alias_map(account_state)
    current_allocs = _compute_current_allocations(account_state)
    total_value = max(account_state.portfolio_value, 0.0)
    actions: list[dict[str, Any]] = []

    for allocation in plan.target_allocations:
        canonical = _resolve_canonical(allocation.coin, alias_map)
        market_type = allocation.market_type or "perp"
        key = (canonical, market_type)
        current_pct = current_allocs.get(key, 0.0)
        target_pct = float(allocation.target_pct)
        gap_pct = target_pct - current_pct

        if abs(gap_pct) < ALLOCATION_THRESHOLD_PCT or total_value <= 0:
            continue

        price = _resolve_price(account_state, canonical, allocation.coin, alias_map)
        if price <= 0:
            continue

        value_gap = (gap_pct / 100) * total_value
        size = abs(value_gap / price)
        if size <= 0:
            continue

        action_type = "buy" if gap_pct > 0 else "sell"
        actions.append(
            {
                "action_type": action_type,
                "coin": canonical,
                "market_type": market_type,
                "size": round(size, 6),
                "target_pct": target_pct,
                "current_pct": round(current_pct, 4),
                "reasoning": f"Rebalance toward target ({current_pct:.2f}% -> {target_pct:.2f}%)",
                "native_symbol": allocation.coin,
                "price": price,
            }
        )

    return actions


def execution_planner(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Translate plan drift into executable actions for the fast loop."""

    account_state = context.cache.get("fast_account_state")
    plan = context.governor.active_plan
    if account_state is None or plan is None:
        return {
            "fast": {
                "execution": {
                    "pending_actions": [],
                    "last_plan_id": plan.plan_id if plan else None,
                    "last_execution_at": _now_iso(),
                    "summary": "No active plan" if plan is None else "Waiting for account state",
                }
            }
        }

    metadata = {
        "loop": FAST_LOOP,
        "plan_id": plan.plan_id,
        "langgraph_phase": context.langgraph_config.phase_tag,
    }

    with node_trace("execution_planner", metadata=metadata) as run:
        pending_actions = _plan_rebalance_actions(plan, account_state)
        execution_patch = {
            "pending_actions": pending_actions,
            "last_plan_id": plan.plan_id,
            "last_execution_at": _now_iso(),
            "summary": f"{len(pending_actions)} actions planned",
        }

        telemetry_patch = {
            **(state.get("telemetry", {}) or {}),
            "total_actions": len(pending_actions),
        }

        patch: StatePatch = {
            "fast": {
                "execution": execution_patch,
            },
            "telemetry": telemetry_patch,
            "governance": {
                "active_plan": serialize_plan(plan),
            },
        }

        if run is not None:
            run.add_outputs(summarize_patch({"fast": execution_patch}))
        return patch


__all__ = ["execution_planner"]
