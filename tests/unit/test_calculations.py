"""Unit tests for signal calculation functions."""

import pytest

from hyperliquid_agent.signals.calculations import (
    calculate_realized_volatility,
    calculate_sma,
    calculate_spread_bps,
    calculate_trend_score,
)

# ============================================================================
# Realized Volatility Tests
# ============================================================================


def test_calculate_realized_volatility_basic():
    """Test basic realized volatility calculation."""
    # Simple price series with known volatility
    candles = [
        {"c": "100.0"},
        {"c": "102.0"},  # 2% return
        {"c": "100.0"},  # -1.96% return
        {"c": "103.0"},  # 3% return
    ]

    vol = calculate_realized_volatility(candles)

    # Should return positive volatility
    assert vol > 0
    assert vol < 1.0  # Reasonable range


def test_calculate_realized_volatility_zero_volatility():
    """Test volatility calculation with constant prices."""
    candles = [{"c": "100.0"}, {"c": "100.0"}, {"c": "100.0"}, {"c": "100.0"}]

    vol = calculate_realized_volatility(candles)

    # Zero volatility for constant prices
    assert vol == 0.0


def test_calculate_realized_volatility_high_volatility():
    """Test volatility calculation with high price swings."""
    candles = [
        {"c": "100.0"},
        {"c": "120.0"},  # 20% up
        {"c": "90.0"},  # 25% down
        {"c": "110.0"},  # 22% up
    ]

    vol = calculate_realized_volatility(candles)

    # Should have high volatility
    assert vol > 0.1  # More than 10%


def test_calculate_realized_volatility_insufficient_data():
    """Test volatility calculation with insufficient data."""
    # Single candle
    vol = calculate_realized_volatility([{"c": "100.0"}])
    assert vol == 0.0

    # Empty list
    vol = calculate_realized_volatility([])
    assert vol == 0.0


def test_calculate_realized_volatility_known_values():
    """Test volatility calculation with known expected values."""
    # Create a simple series with predictable returns
    # Prices: 100, 110, 121 (10% returns each time)
    candles = [{"c": "100.0"}, {"c": "110.0"}, {"c": "121.0"}]

    vol = calculate_realized_volatility(candles)

    # Both returns are 10% (0.1), so std dev should be 0
    assert vol == pytest.approx(0.0, abs=1e-10)


def test_calculate_realized_volatility_mixed_returns():
    """Test volatility with mixed positive and negative returns."""
    candles = [
        {"c": "100.0"},
        {"c": "105.0"},  # +5%
        {"c": "100.0"},  # -4.76%
        {"c": "105.0"},  # +5%
        {"c": "100.0"},  # -4.76%
    ]

    vol = calculate_realized_volatility(candles)

    # Should have measurable volatility from oscillation
    assert vol > 0.03  # At least 3%
    assert vol < 0.1  # But not extreme


# ============================================================================
# Spread Calculation Tests
# ============================================================================


def test_calculate_spread_bps_basic():
    """Test basic spread calculation in basis points."""
    best_bid = 50000.0
    best_ask = 50010.0

    spread = calculate_spread_bps(best_bid, best_ask)

    # Spread = (50010 - 50000) / 50005 * 10000 = 1.999 bps
    assert spread == pytest.approx(2.0, rel=0.01)


def test_calculate_spread_bps_tight_spread():
    """Test spread calculation with tight spread."""
    best_bid = 50000.0
    best_ask = 50001.0

    spread = calculate_spread_bps(best_bid, best_ask)

    # Very tight spread
    assert spread == pytest.approx(0.2, rel=0.01)


def test_calculate_spread_bps_wide_spread():
    """Test spread calculation with wide spread."""
    best_bid = 50000.0
    best_ask = 50500.0

    spread = calculate_spread_bps(best_bid, best_ask)

    # Wide spread: 500 / 50250 * 10000 = 99.5 bps
    assert spread == pytest.approx(99.5, rel=0.01)


def test_calculate_spread_bps_zero_spread():
    """Test spread calculation with zero spread (same bid/ask)."""
    best_bid = 50000.0
    best_ask = 50000.0

    spread = calculate_spread_bps(best_bid, best_ask)

    assert spread == 0.0


def test_calculate_spread_bps_different_price_levels():
    """Test spread calculation at different price levels."""
    # Low price with 0.1% spread
    spread_low = calculate_spread_bps(10.0, 10.01)

    # High price with 0.1% spread
    spread_high = calculate_spread_bps(100000.0, 100100.0)

    # Spread in bps should be similar for same percentage spread
    assert spread_low == pytest.approx(spread_high, rel=0.01)


# ============================================================================
# Simple Moving Average Tests
# ============================================================================


def test_calculate_sma_basic():
    """Test basic SMA calculation."""
    prices = [100.0, 102.0, 104.0, 106.0, 108.0]
    period = 3

    sma = calculate_sma(prices, period)

    # Last 3 prices: 104, 106, 108 -> avg = 106
    assert sma == pytest.approx(106.0)


def test_calculate_sma_full_period():
    """Test SMA with period equal to data length."""
    prices = [100.0, 110.0, 120.0]
    period = 3

    sma = calculate_sma(prices, period)

    # Average of all: (100 + 110 + 120) / 3 = 110
    assert sma == pytest.approx(110.0)


def test_calculate_sma_insufficient_data():
    """Test SMA with insufficient data."""
    prices = [100.0, 102.0]
    period = 5

    sma = calculate_sma(prices, period)

    # Not enough data
    assert sma == 0.0


def test_calculate_sma_empty_list():
    """Test SMA with empty price list."""
    sma = calculate_sma([], 5)
    assert sma == 0.0


def test_calculate_sma_period_one():
    """Test SMA with period of 1."""
    prices = [100.0, 102.0, 104.0]
    period = 1

    sma = calculate_sma(prices, period)

    # Should return last price
    assert sma == pytest.approx(104.0)


def test_calculate_sma_constant_prices():
    """Test SMA with constant prices."""
    prices = [100.0, 100.0, 100.0, 100.0]
    period = 3

    sma = calculate_sma(prices, period)

    # Should return constant value
    assert sma == pytest.approx(100.0)


def test_calculate_sma_trending_up():
    """Test SMA with upward trending prices."""
    prices = [100.0, 105.0, 110.0, 115.0, 120.0]
    period = 3

    sma = calculate_sma(prices, period)

    # Last 3: 110, 115, 120 -> avg = 115
    assert sma == pytest.approx(115.0)


def test_calculate_sma_trending_down():
    """Test SMA with downward trending prices."""
    prices = [120.0, 115.0, 110.0, 105.0, 100.0]
    period = 3

    sma = calculate_sma(prices, period)

    # Last 3: 110, 105, 100 -> avg = 105
    assert sma == pytest.approx(105.0)


# ============================================================================
# Trend Score Tests
# ============================================================================


def test_calculate_trend_score_strong_uptrend():
    """Test trend score with strong uptrend."""
    current_price = 110.0
    sma_20 = 100.0
    sma_50 = 95.0

    score = calculate_trend_score(current_price, sma_20, sma_50)

    # Price above both SMAs, 20 > 50 -> positive trend
    assert score > 0
    assert score <= 1.0


def test_calculate_trend_score_strong_downtrend():
    """Test trend score with strong downtrend."""
    current_price = 90.0
    sma_20 = 100.0
    sma_50 = 105.0

    score = calculate_trend_score(current_price, sma_20, sma_50)

    # Price below both SMAs, 20 < 50 -> negative trend
    assert score < 0
    assert score >= -1.0


def test_calculate_trend_score_neutral():
    """Test trend score near neutral."""
    current_price = 100.0
    sma_20 = 100.0
    sma_50 = 99.0

    score = calculate_trend_score(current_price, sma_20, sma_50)

    # Price at SMA_20, slight uptrend
    assert abs(score) < 0.1  # Near neutral


def test_calculate_trend_score_price_above_sma20_uptrend():
    """Test trend score with price above SMA20 in uptrend."""
    current_price = 105.0
    sma_20 = 100.0
    sma_50 = 95.0

    score = calculate_trend_score(current_price, sma_20, sma_50)

    # 5% above SMA20 in uptrend
    assert score > 0
    assert score <= 1.0


def test_calculate_trend_score_price_below_sma20_downtrend():
    """Test trend score with price below SMA20 in downtrend."""
    current_price = 95.0
    sma_20 = 100.0
    sma_50 = 105.0

    score = calculate_trend_score(current_price, sma_20, sma_50)

    # 5% below SMA20 in downtrend
    assert score < 0
    assert score >= -1.0


def test_calculate_trend_score_clamping():
    """Test that trend score is clamped to [-1, 1]."""
    # Extreme uptrend
    current_price = 200.0
    sma_20 = 100.0
    sma_50 = 95.0

    score = calculate_trend_score(current_price, sma_20, sma_50)
    assert score <= 1.0

    # Extreme downtrend
    current_price = 50.0
    sma_20 = 100.0
    sma_50 = 105.0

    score = calculate_trend_score(current_price, sma_20, sma_50)
    assert score >= -1.0


def test_calculate_trend_score_sma_crossover():
    """Test trend score at SMA crossover point."""
    current_price = 100.0
    sma_20 = 100.0
    sma_50 = 100.0

    score = calculate_trend_score(current_price, sma_20, sma_50)

    # At crossover, should be near zero
    assert abs(score) < 0.01


def test_calculate_trend_score_golden_cross():
    """Test trend score with golden cross (SMA20 > SMA50)."""
    current_price = 102.0
    sma_20 = 101.0
    sma_50 = 99.0

    score = calculate_trend_score(current_price, sma_20, sma_50)

    # Bullish configuration
    assert score > 0


def test_calculate_trend_score_death_cross():
    """Test trend score with death cross (SMA20 < SMA50)."""
    current_price = 98.0
    sma_20 = 99.0
    sma_50 = 101.0

    score = calculate_trend_score(current_price, sma_20, sma_50)

    # Bearish configuration
    assert score < 0


# ============================================================================
# Integration Tests for Multiple Calculations
# ============================================================================


def test_calculations_with_real_world_data():
    """Test calculations with realistic market data."""
    # Simulate a day of BTC price action
    candles = [
        {"c": "50000.0"},
        {"c": "50200.0"},
        {"c": "50100.0"},
        {"c": "50300.0"},
        {"c": "50250.0"},
        {"c": "50400.0"},
        {"c": "50350.0"},
        {"c": "50500.0"},
    ]

    # Calculate volatility
    vol = calculate_realized_volatility(candles)
    assert vol > 0
    assert vol < 0.1  # Reasonable intraday volatility

    # Extract prices for SMA
    prices = [float(c["c"]) for c in candles]

    # Calculate SMAs
    sma_3 = calculate_sma(prices, 3)
    sma_5 = calculate_sma(prices, 5)

    assert sma_3 > 0
    assert sma_5 > 0
    assert sma_3 > sma_5  # Shorter SMA should be higher in uptrend

    # Calculate trend score
    current_price = prices[-1]
    trend = calculate_trend_score(current_price, sma_3, sma_5)

    assert trend > 0  # Uptrend


def test_calculations_consistency():
    """Test that calculations are consistent across multiple calls."""
    candles = [{"c": "100.0"}, {"c": "102.0"}, {"c": "104.0"}, {"c": "106.0"}]

    # Multiple calls should return same result
    vol1 = calculate_realized_volatility(candles)
    vol2 = calculate_realized_volatility(candles)

    assert vol1 == vol2

    prices = [100.0, 102.0, 104.0, 106.0]
    sma1 = calculate_sma(prices, 3)
    sma2 = calculate_sma(prices, 3)

    assert sma1 == sma2
