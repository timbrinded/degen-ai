"""Unit tests exercising key LangGraph nodes."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from hyperliquid_agent.config import Config
from hyperliquid_agent.governance.regime import PriceContext, RegimeClassification, RegimeSignals
from hyperliquid_agent.governance.tripwire import TripwireAction, TripwireEvent
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.nodes.regime_detector import regime_detector
from hyperliquid_agent.langgraph.nodes.tripwire_check import tripwire_check
from hyperliquid_agent.langgraph.state import GlobalState


class _DummyConfig(Config):  # pragma: no cover - helper for type checker
    pass


def _fake_config() -> Config:
    return cast(Config, SimpleNamespace())


def test_tripwire_node_marks_emergency() -> None:
    """Tripwire node should flag emergency unwind when violations exist."""

    account_state = SimpleNamespace(positions=[], portfolio_value=100_000, available_balance=50_000)
    context = SimpleNamespace(
        cache={"fast_account_state": account_state},
        governor=SimpleNamespace(active_plan=None),
        tripwire=SimpleNamespace(
            check_all_tripwires=lambda *_: [
                TripwireEvent(
                    severity="critical",
                    category="account_safety",
                    trigger="daily_loss_limit",
                    action=TripwireAction.CUT_SIZE_TO_FLOOR,
                    timestamp=datetime.now(UTC),
                    details={"loss_pct": 5.5},
                )
            ]
        ),
        langgraph_config=SimpleNamespace(phase_tag="test"),
    )

    patch = tripwire_check(
        cast(GlobalState, {}),
        _fake_config(),
        context=cast(LangGraphRuntimeContext, context),
    )
    fast_tripwire = patch["fast"]["tripwire"]

    assert fast_tripwire["emergency_unwind_required"] is True
    assert fast_tripwire["violations"][0]["action"] == TripwireAction.CUT_SIZE_TO_FLOOR.value


def test_regime_detector_updates_state() -> None:
    """Regime detector node should persist latest classification + history."""

    signals = RegimeSignals(
        price_context=PriceContext(
            current_price=100.0,
            return_1d=1.0,
            return_7d=3.0,
            return_30d=5.0,
            return_90d=10.0,
            sma20_distance=1.2,
            sma50_distance=0.8,
            higher_highs=True,
            higher_lows=True,
        ),
        price_sma_20=98.0,
        price_sma_50=96.0,
        adx=30.0,
        realized_vol_24h=0.05,
        avg_funding_rate=0.001,
        bid_ask_spread_bps=5.0,
        order_book_depth=1_000_000.0,
    )

    class DummyRegimeDetector:
        def __init__(self):
            self.llm_client = SimpleNamespace(total_cost_usd=0.0)
            self.current_regime = "unknown"
            self.regime_history: list[RegimeClassification] = []

        def classify_regime(self, _signals):
            return RegimeClassification(
                regime="trending-bull",
                confidence=0.8,
                timestamp=datetime.now(UTC),
                signals=signals,
                reasoning="positive returns",
            )

        def update_and_confirm(self, classification):
            self.regime_history.append(classification)
            self.current_regime = classification.regime
            return True, "Regime change confirmed"

    context = SimpleNamespace(
        cache={"regime_signals": signals},
        regime_detector=DummyRegimeDetector(),
        record_llm_cost=lambda *_, **__: None,
    )

    patch = regime_detector(
        cast(GlobalState, {}),
        _fake_config(),
        context=cast(LangGraphRuntimeContext, context),
    )
    regime_state = patch["governance"]["regime"]

    assert regime_state["label"] == "trending-bull"
    assert regime_state["changed"] is True
