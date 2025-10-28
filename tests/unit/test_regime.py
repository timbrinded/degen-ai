"""Unit tests for Regime Detector module."""

from datetime import datetime, timedelta
from typing import cast

import pytest

from hyperliquid_agent.config import LLMConfig
from hyperliquid_agent.governance.regime import (
    PriceContext,
    RegimeDetector,
    RegimeDetectorConfig,
    RegimeSignals,
)


@pytest.fixture
def llm_config() -> LLMConfig:
    """Create a test LLM configuration."""
    return LLMConfig(
        provider="anthropic",
        model="claude-3-5-haiku-20241022",
        api_key="test-key",
        temperature=0.0,
        max_tokens=500,
    )


@pytest.fixture
def regime_config() -> RegimeDetectorConfig:
    """Create a test regime detector configuration."""
    return RegimeDetectorConfig(
        confirmation_cycles_required=3,
        hysteresis_enter_threshold=0.7,
        hysteresis_exit_threshold=0.4,
        event_lock_window_hours_before=2,
        event_lock_window_hours_after=1,
        use_enhanced_signals=False,
    )


@pytest.fixture
def bull_price_context() -> PriceContext:
    """Create price context for bull trend."""
    return PriceContext(
        current_price=51000.0,
        return_1d=2.0,
        return_7d=10.0,
        return_30d=20.0,
        return_90d=50.0,
        sma20_distance=2.0,
        sma50_distance=6.25,
        higher_highs=True,
        higher_lows=True,
    )


@pytest.fixture
def range_price_context() -> PriceContext:
    """Create price context for range-bound market."""
    return PriceContext(
        current_price=50000.0,
        return_1d=0.2,
        return_7d=1.0,
        return_30d=2.0,
        return_90d=3.0,
        sma20_distance=0.0,
        sma50_distance=-0.2,
        higher_highs=False,
        higher_lows=False,
    )


@pytest.fixture
def trending_signals(bull_price_context: PriceContext) -> RegimeSignals:
    """Create signals indicating a trending regime."""
    return RegimeSignals(
        price_context=bull_price_context,
        price_sma_20=50000.0,
        price_sma_50=48000.0,  # SMA20 > SMA50 by >2%
        adx=30.0,  # Strong trend (>25)
        realized_vol_24h=0.5,
        avg_funding_rate=0.01,
        bid_ask_spread_bps=5.0,
        order_book_depth=1000000.0,
    )


@pytest.fixture
def range_bound_signals(range_price_context: PriceContext) -> RegimeSignals:
    """Create signals indicating a range-bound regime."""
    return RegimeSignals(
        price_context=range_price_context,
        price_sma_20=50000.0,
        price_sma_50=50100.0,  # SMAs very close
        adx=15.0,  # Weak trend (<20)
        realized_vol_24h=0.25,  # Low volatility (<0.3)
        avg_funding_rate=0.005,
        bid_ask_spread_bps=3.0,
        order_book_depth=1500000.0,
    )


@pytest.fixture
def carry_friendly_signals(range_price_context: PriceContext) -> RegimeSignals:
    """Create signals indicating a carry-friendly regime."""
    return RegimeSignals(
        price_context=range_price_context,
        price_sma_20=50000.0,
        price_sma_50=50000.0,
        adx=18.0,
        realized_vol_24h=0.35,  # Low-moderate volatility (<0.4)
        avg_funding_rate=0.015,  # Positive funding (>0.01)
        bid_ask_spread_bps=4.0,
        order_book_depth=1200000.0,
    )


@pytest.fixture
def unknown_signals(range_price_context: PriceContext) -> RegimeSignals:
    """Create signals that don't match any clear regime."""
    return RegimeSignals(
        price_context=range_price_context,
        price_sma_20=50000.0,
        price_sma_50=49500.0,
        adx=22.0,  # Borderline
        realized_vol_24h=0.45,  # Moderate
        avg_funding_rate=0.008,  # Moderate
        bid_ask_spread_bps=6.0,
        order_book_depth=800000.0,
    )


def test_regime_detector_initialization(regime_config, llm_config):
    """Test RegimeDetector initializes correctly."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    assert detector.config == regime_config
    assert detector.current_regime == "unknown"
    assert len(detector.regime_history) == 0
    assert detector.macro_calendar == []
    assert detector.external_data is None


def test_classify_regime_trending(regime_config, llm_config, trending_signals):
    """Test classification of trending regime."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    classification = detector.classify_regime(trending_signals)

    assert classification.regime == "trending"
    assert classification.confidence > 0.5
    assert classification.signals == trending_signals
    assert isinstance(classification.timestamp, datetime)


def test_classify_regime_range_bound(regime_config, llm_config, range_bound_signals):
    """Test classification of range-bound regime."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    classification = detector.classify_regime(range_bound_signals)

    assert classification.regime == "range-bound"
    assert classification.confidence == pytest.approx(0.8)
    assert classification.signals == range_bound_signals


def test_classify_regime_carry_friendly(regime_config, llm_config, carry_friendly_signals):
    """Test classification of carry-friendly regime."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    classification = detector.classify_regime(carry_friendly_signals)

    assert classification.regime == "carry-friendly"
    assert classification.confidence == pytest.approx(0.75)
    assert classification.signals == carry_friendly_signals


def test_classify_regime_unknown(regime_config, llm_config, unknown_signals):
    """Test classification defaults to unknown for ambiguous signals."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    classification = detector.classify_regime(unknown_signals)

    assert classification.regime == "unknown"
    assert classification.confidence == 0.5
    assert classification.signals == unknown_signals


def test_classify_regime_event_risk_near_macro_event(regime_config, llm_config, unknown_signals):
    """Test classification prioritizes event-risk when near macro event."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    # Add upcoming macro event within the lock window (< 2 hours before)
    detector.macro_calendar = [
        {
            "name": "FOMC Meeting",
            "datetime": datetime.now() + timedelta(hours=1),  # 1 hour away, within 2-hour window
        }
    ]

    # Use signals that don't match other regimes so event-risk takes priority
    classification = detector.classify_regime(unknown_signals)

    assert classification.regime == "event-risk"
    assert classification.confidence == 1.0


def test_update_and_confirm_insufficient_history(regime_config, llm_config, trending_signals):
    """Test regime change requires sufficient history."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    # Add only 2 classifications (need 3)
    for _ in range(2):
        classification = detector.classify_regime(trending_signals)
        changed, reason = detector.update_and_confirm(classification)

        assert changed is False
        assert "Insufficient history" in reason


def test_update_and_confirm_no_change(regime_config, llm_config, trending_signals):
    """Test no regime change when regime stays the same."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    detector.current_regime = "trending"

    # Add 3 trending classifications
    changed, reason = False, ""
    for _ in range(3):
        classification = detector.classify_regime(trending_signals)
        changed, reason = detector.update_and_confirm(classification)

    assert changed is False
    assert "No regime change" in reason
    assert detector.current_regime == "trending"


def test_update_and_confirm_regime_change_confirmed(
    regime_config, llm_config, trending_signals, range_bound_signals
):
    """Test regime change is confirmed with sufficient sustained signals."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    detector.current_regime = "range-bound"

    # Add 3 trending classifications (100% trending = 1.0 > 0.7 threshold)
    changed, reason = False, ""
    for _ in range(3):
        classification = detector.classify_regime(trending_signals)
        changed, reason = detector.update_and_confirm(classification)

    assert changed is True
    assert "Regime change confirmed" in reason
    assert "range-bound → trending" in reason
    assert detector.current_regime == "trending"


def test_update_and_confirm_regime_change_not_confirmed(
    regime_config, llm_config, trending_signals, range_bound_signals
):
    """Test regime change is not confirmed without sufficient confidence."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    detector.current_regime = "range-bound"

    # Add mixed classifications (2 trending, 1 range-bound = 66.7% < 70% threshold)
    for _ in range(2):
        classification = detector.classify_regime(trending_signals)
        detector.update_and_confirm(classification)

    classification = detector.classify_regime(range_bound_signals)
    changed, reason = detector.update_and_confirm(classification)

    assert changed is False
    assert "not confirmed" in reason
    assert detector.current_regime == "range-bound"


def test_hysteresis_threshold_prevents_ping_pong(
    regime_config, llm_config, trending_signals, range_bound_signals
):
    """Test hysteresis prevents rapid regime switching."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    detector.current_regime = "range-bound"

    # Add 2 trending, 1 range-bound (66.7% confidence)
    for _ in range(2):
        classification = detector.classify_regime(trending_signals)
        detector.update_and_confirm(classification)

    classification = detector.classify_regime(range_bound_signals)
    changed, _ = detector.update_and_confirm(classification)

    # Should not change (66.7% < 70% threshold)
    assert changed is False
    assert detector.current_regime == "range-bound"

    # Add one more trending to reach 3 trending total
    classification = detector.classify_regime(trending_signals)
    changed, _ = detector.update_and_confirm(classification)

    # Now should change (66.7% still, but history shifted)
    # Actually with deque of 3, we now have [trending, range, trending]
    # So 66.7% trending, still not enough
    assert changed is False


def test_regime_history_max_length(regime_config, llm_config, trending_signals):
    """Test regime history respects max length."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    # Add more classifications than max length
    for _ in range(5):
        classification = detector.classify_regime(trending_signals)
        detector.update_and_confirm(classification)

    # History should be capped at confirmation_cycles_required
    assert len(detector.regime_history) == regime_config.confirmation_cycles_required


def test_is_in_event_lock_window_no_events(regime_config, llm_config):
    """Test no event lock when no events scheduled."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    current_time = datetime.now()

    in_lock, message = detector.is_in_event_lock_window(current_time)

    assert in_lock is False
    assert "No event lock" in message


def test_is_in_event_lock_window_before_event(regime_config, llm_config):
    """Test event lock window before scheduled event."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    event_time = datetime.now() + timedelta(hours=1)
    current_time = datetime.now()

    detector.macro_calendar = [
        {
            "name": "FOMC Meeting",
            "datetime": event_time,
        }
    ]

    in_lock, message = detector.is_in_event_lock_window(current_time)

    assert in_lock is True
    assert "Event lock" in message
    assert "FOMC Meeting" in message


def test_is_in_event_lock_window_after_event(regime_config, llm_config):
    """Test event lock window after scheduled event."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    event_time = datetime.now() - timedelta(minutes=30)  # 30 min ago
    current_time = datetime.now()

    detector.macro_calendar = [
        {
            "name": "CPI Release",
            "datetime": event_time,
        }
    ]

    in_lock, message = detector.is_in_event_lock_window(current_time)

    assert in_lock is True
    assert "Event lock" in message
    assert "CPI Release" in message


def test_is_in_event_lock_window_outside_window(regime_config, llm_config):
    """Test no event lock outside event window."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    event_time = datetime.now() + timedelta(hours=5)  # 5 hours away
    current_time = datetime.now()

    detector.macro_calendar = [
        {
            "name": "Jobs Report",
            "datetime": event_time,
        }
    ]

    in_lock, message = detector.is_in_event_lock_window(current_time)

    assert in_lock is False
    assert "No event lock" in message


def test_is_in_event_lock_window_multiple_events(regime_config, llm_config):
    """Test event lock with multiple scheduled events."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    current_time = datetime.now()

    detector.macro_calendar = [
        {
            "name": "Event 1",
            "datetime": current_time + timedelta(hours=5),  # Outside window
        },
        {
            "name": "Event 2",
            "datetime": current_time + timedelta(hours=1),  # Inside window
        },
    ]

    in_lock, message = detector.is_in_event_lock_window(current_time)

    assert in_lock is True
    assert "Event 2" in message


def test_event_lock_window_configuration(regime_config, llm_config):
    """Test event lock window respects configuration."""
    # Custom config with different window sizes
    custom_config = RegimeDetectorConfig(
        event_lock_window_hours_before=4,
        event_lock_window_hours_after=2,
    )
    detector = RegimeDetector(custom_config, cast(LLMConfig, llm_config))

    event_time = datetime.now() + timedelta(hours=3)  # 3 hours away
    current_time = datetime.now()

    detector.macro_calendar = [
        {
            "name": "Test Event",
            "datetime": event_time,
        }
    ]

    # Should be in lock (3 hours < 4 hours before)
    in_lock, _ = detector.is_in_event_lock_window(current_time)
    assert in_lock is True

    # Test after event
    event_time_past = datetime.now() - timedelta(hours=1.5)  # 1.5 hours ago
    detector.macro_calendar = [
        {
            "name": "Past Event",
            "datetime": event_time_past,
        }
    ]

    # Should be in lock (1.5 hours < 2 hours after)
    in_lock, _ = detector.is_in_event_lock_window(current_time)
    assert in_lock is True


def test_trending_regime_confidence_scales_with_adx(regime_config, llm_config, bull_price_context):
    """Test trending regime confidence scales with ADX strength."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    # Weak trend
    weak_signals = RegimeSignals(
        price_context=bull_price_context,
        price_sma_20=50000.0,
        price_sma_50=48000.0,
        adx=26.0,  # Just above threshold
        realized_vol_24h=0.5,
        avg_funding_rate=0.01,
        bid_ask_spread_bps=5.0,
        order_book_depth=1000000.0,
    )

    # Strong trend
    strong_signals = RegimeSignals(
        price_context=bull_price_context,
        price_sma_20=50000.0,
        price_sma_50=48000.0,
        adx=38.0,  # Much stronger
        realized_vol_24h=0.5,
        avg_funding_rate=0.01,
        bid_ask_spread_bps=5.0,
        order_book_depth=1000000.0,
    )

    weak_classification = detector.classify_regime(weak_signals)
    strong_classification = detector.classify_regime(strong_signals)

    assert weak_classification.regime == "trending"
    assert strong_classification.regime == "trending"
    assert strong_classification.confidence > weak_classification.confidence


def test_regime_classification_priority_order(
    regime_config, llm_config, bull_price_context, range_price_context
):
    """Test regime classification checks in order: trending, range-bound, carry-friendly, event-risk."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    # Signals that match trending (checked first)
    detector.macro_calendar = [
        {
            "name": "Major Event",
            "datetime": datetime.now() + timedelta(hours=1),
        }
    ]

    trending_signals = RegimeSignals(
        price_context=bull_price_context,
        price_sma_20=50000.0,
        price_sma_50=48000.0,
        adx=30.0,  # Matches trending
        realized_vol_24h=0.5,
        avg_funding_rate=0.015,
        bid_ask_spread_bps=5.0,
        order_book_depth=1000000.0,
    )

    classification = detector.classify_regime(trending_signals)

    # Trending is checked first, so it takes priority even with event nearby
    assert classification.regime == "trending"

    # Now test with signals that don't match other regimes
    unknown_signals = RegimeSignals(
        price_context=range_price_context,
        price_sma_20=50000.0,
        price_sma_50=49500.0,
        adx=22.0,  # Doesn't match trending
        realized_vol_24h=0.45,  # Doesn't match range-bound or carry
        avg_funding_rate=0.008,
        bid_ask_spread_bps=6.0,
        order_book_depth=800000.0,
    )

    classification = detector.classify_regime(unknown_signals)

    # Event-risk should be detected when no other regime matches
    assert classification.regime == "event-risk"


def test_regime_detector_with_external_data_provider(regime_config, llm_config):
    """Test regime detector accepts external data provider."""

    # Mock external data provider
    class MockExternalData:
        def get_cross_asset_correlation(self, asset1: str, asset2: str) -> float:
            return 0.8

        def get_macro_risk_score(self) -> float:
            return 0.5

        def get_sentiment_index(self) -> float:
            return 60.0

    external_provider = MockExternalData()
    detector = RegimeDetector(
        regime_config,
        cast(LLMConfig, llm_config),
        external_data_provider=external_provider,
    )

    assert detector.external_data is not None
    assert detector.external_data == external_provider


def test_regime_history_tracking(regime_config, llm_config, trending_signals, range_bound_signals):
    """Test regime history tracks classifications correctly."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))

    # Add trending classification
    trending_class = detector.classify_regime(trending_signals)
    detector.update_and_confirm(trending_class)

    assert len(detector.regime_history) == 1
    assert detector.regime_history[0].regime == "trending"

    # Add range-bound classification
    range_class = detector.classify_regime(range_bound_signals)
    detector.update_and_confirm(range_class)

    assert len(detector.regime_history) == 2
    assert detector.regime_history[1].regime == "range-bound"


def test_regime_change_requires_sustained_signals(
    regime_config, llm_config, trending_signals, range_bound_signals
):
    """Test regime change requires sustained signals, not just majority."""
    detector = RegimeDetector(regime_config, cast(LLMConfig, llm_config))
    detector.current_regime = "range-bound"

    # Pattern: trending, trending, range-bound
    # This gives 66.7% trending but not sustained
    classifications = [trending_signals, trending_signals, range_bound_signals]

    for signals in classifications:
        classification = detector.classify_regime(signals)
        changed, _ = detector.update_and_confirm(classification)

    # Should not change (66.7% < 70% threshold)
    assert detector.current_regime == "range-bound"
