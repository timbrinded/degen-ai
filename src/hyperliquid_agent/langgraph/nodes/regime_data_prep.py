"""Slow-loop data prep feeding RegimeDetector."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from statistics import mean

from hyperliquid_agent.config import Config
from hyperliquid_agent.governance.regime import PriceContext, RegimeSignals
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.serialization import serialize_account_state
from hyperliquid_agent.langgraph.state import SLOW_LOOP, GlobalState, StatePatch


def _reference_price(account_state) -> float:
    positions = getattr(account_state, "positions", []) or []
    if positions:
        return abs(positions[0].current_price)
    price_map = getattr(account_state, "price_map", {}) or {}
    if price_map:
        return next(iter(price_map.values()))
    return 0.0


def _price_context(account_state, medium_signals) -> PriceContext:
    current_price = _reference_price(account_state)
    trend_score = getattr(medium_signals, "trend_score", 0.0) if medium_signals else 0.0
    return PriceContext(
        current_price=current_price,
        return_1d=trend_score * 5,
        return_7d=trend_score * 10,
        return_30d=trend_score * 20,
        return_90d=trend_score * 30,
        sma20_distance=trend_score * 2,
        sma50_distance=trend_score,
        higher_highs=trend_score > 0.2,
        higher_lows=trend_score > 0.1,
        data_quality="partial" if medium_signals else "insufficient",
        oldest_data_point=None,
    )


def _avg_funding(medium_signals) -> float:
    if medium_signals and medium_signals.funding_basis:
        return mean(medium_signals.funding_basis.values())
    return 0.0


def _spread_bps(fast_signals) -> float:
    if fast_signals and fast_signals.spreads:
        return float(mean(fast_signals.spreads.values()))
    return 0.0


def _order_book_depth(fast_signals) -> float:
    if fast_signals and fast_signals.order_book_depth:
        return float(mean(fast_signals.order_book_depth.values()))
    return 0.0


def regime_data_prep(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Prepare regime signals for downstream classification."""

    plan = context.governor.active_plan
    account_state = context.monitor.get_current_state_with_signals("slow", active_plan=plan)
    context.cache["slow_account_state"] = account_state
    medium_signals = account_state.medium_signals
    fast_signals = account_state.fast_signals

    signals = RegimeSignals(
        price_context=_price_context(account_state, medium_signals),
        price_sma_20=getattr(medium_signals, "trend_score", 0.0) * 10 if medium_signals else 0.0,
        price_sma_50=getattr(medium_signals, "trend_score", 0.0) * 8 if medium_signals else 0.0,
        adx=getattr(medium_signals, "trend_score", 0.0) * 50 if medium_signals else 0.0,
        realized_vol_24h=getattr(medium_signals, "realized_vol_24h", 0.0)
        if medium_signals
        else 0.0,
        avg_funding_rate=_avg_funding(medium_signals),
        bid_ask_spread_bps=_spread_bps(fast_signals),
        order_book_depth=_order_book_depth(fast_signals),
    )

    metadata = {
        "loop": SLOW_LOOP,
        "plan_id": plan.plan_id if plan else None,
    }

    with node_trace("regime_data_prep", metadata=metadata) as run:
        context.cache["regime_signals"] = signals
        patch: StatePatch = {
            "slow": {
                "regime_snapshot": serialize_account_state(account_state),
                "last_detection_at": datetime.now(UTC).isoformat(),
            },
            "governance": {
                "regime_signals": asdict(signals),
            },
        }

        if run is not None:
            run.add_outputs(summarize_patch({"slow": patch["slow"]}))
        return patch


__all__ = ["regime_data_prep"]
