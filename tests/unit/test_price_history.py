"""Unit tests for PriceHistory class."""

from datetime import datetime, timedelta

from hyperliquid_agent.signals.collectors import PriceHistory

# ============================================================================
# Return Calculation Tests
# ============================================================================


def test_calculate_returns_with_known_sequence():
    """Test return calculations with known price sequences."""
    ph = PriceHistory(lookback_days=90)

    base_time = datetime(2024, 1, 1)

    # Add exactly 541 candles - deque will keep last 540
    # We need 541 total to calculate 90d return (current + 540 back)
    for i in range(600):  # Add more than needed to test deque behavior
        timestamp = base_time + timedelta(hours=i * 4)
        price = 100.0  # Default price

        ph.add_candle(
            close=price,
            high=price * 1.01,
            low=price * 0.99,
            timestamp=timestamp,
        )

    # Deque now has exactly 540 items
    # Set specific prices for testing returns
    # Current price (index -1): 110
    # 1d ago (index -7): 100
    # 7d ago (index -43): 120
    # 30d ago (index -181): 150
    # 90d ago (index 0): 100

    ph.closes[-1] = 110.0
    ph.closes[-7] = 100.0
    ph.closes[-43] = 120.0
    ph.closes[-181] = 150.0
    ph.closes[0] = 100.0  # Oldest in deque

    returns = ph.calculate_returns()

    assert returns is not None
    assert abs(returns["return_1d"] - 10.0) < 0.1  # 10% return (110 vs 100)
    assert abs(returns["return_7d"] - (-8.33)) < 0.5  # -8.33% return (110 vs 120)
    assert abs(returns["return_30d"] - (-26.67)) < 0.5  # -26.67% return (110 vs 150)
    # For 90d, we need at least 541 items but deque only holds 540
    # So 90d return will be 0.0 (not enough data)
    assert returns["return_90d"] == 0.0  # Not enough data in deque


def test_calculate_returns_insufficient_data():
    """Test return calculations with insufficient data."""
    ph = PriceHistory()

    # Add only 5 candles (need at least 7 for 1d return)
    base_time = datetime(2024, 1, 1)
    for i in range(5):
        ph.add_candle(
            close=100.0,
            high=101.0,
            low=99.0,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    returns = ph.calculate_returns()
    assert returns is None


def test_calculate_returns_partial_data():
    """Test return calculations with partial data (only 1d and 7d available)."""
    ph = PriceHistory()

    # Add 50 candles (enough for 1d and 7d, not enough for 30d and 90d)
    base_time = datetime(2024, 1, 1)
    for i in range(50):
        price = 100.0 + i  # Increasing price
        ph.add_candle(
            close=price,
            high=price * 1.01,
            low=price * 0.99,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    returns = ph.calculate_returns()

    assert returns is not None
    assert returns["return_1d"] != 0.0  # Should have 1d return
    assert returns["return_7d"] != 0.0  # Should have 7d return
    assert returns["return_30d"] == 0.0  # Not enough data
    assert returns["return_90d"] == 0.0  # Not enough data


def test_calculate_returns_zero_price():
    """Test return calculations with zero prices (edge case)."""
    ph = PriceHistory()

    base_time = datetime(2024, 1, 1)
    for i in range(100):
        ph.add_candle(
            close=0.0,  # Zero price
            high=0.0,
            low=0.0,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    returns = ph.calculate_returns()

    assert returns is not None
    assert returns["return_1d"] == 0.0
    assert returns["return_7d"] == 0.0


# ============================================================================
# Market Structure Detection Tests
# ============================================================================


def test_detect_market_structure_higher_highs_lows():
    """Test market structure detection with synthetic higher highs/lows pattern."""
    ph = PriceHistory()

    base_time = datetime(2024, 1, 1)

    # Create uptrend with higher highs and higher lows
    for i in range(60):
        # Create oscillating pattern with upward bias
        base_price = 100.0 + i * 0.5
        oscillation = 5.0 if i % 4 < 2 else -5.0
        price = base_price + oscillation

        ph.add_candle(
            close=price,
            high=price + 2.0,
            low=price - 2.0,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    structure = ph.detect_market_structure()

    # Should detect uptrend structure
    assert structure["higher_highs"] is True
    assert structure["higher_lows"] is True


def test_detect_market_structure_lower_highs_lows():
    """Test market structure detection with downtrend pattern."""
    ph = PriceHistory()

    base_time = datetime(2024, 1, 1)

    # Create downtrend with lower highs and lower lows
    for i in range(60):
        # Create oscillating pattern with downward bias
        base_price = 100.0 - i * 0.5
        oscillation = 5.0 if i % 4 < 2 else -5.0
        price = base_price + oscillation

        ph.add_candle(
            close=price,
            high=price + 2.0,
            low=price - 2.0,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    structure = ph.detect_market_structure()

    # Should detect downtrend structure
    assert structure["higher_highs"] is False
    assert structure["higher_lows"] is False


def test_detect_market_structure_insufficient_data():
    """Test market structure detection with insufficient data."""
    ph = PriceHistory()

    base_time = datetime(2024, 1, 1)

    # Add only 30 candles (need at least 50)
    for i in range(30):
        ph.add_candle(
            close=100.0,
            high=101.0,
            low=99.0,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    structure = ph.detect_market_structure()

    assert structure["higher_highs"] is False
    assert structure["higher_lows"] is False


# ============================================================================
# Deque Overflow Tests
# ============================================================================


def test_deque_overflow_behavior():
    """Test deque overflow behavior with more than 540 data points."""
    ph = PriceHistory(lookback_days=90)  # Max 540 candles

    base_time = datetime(2024, 1, 1)

    # Add 600 candles (60 more than max)
    for i in range(600):
        ph.add_candle(
            close=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    # Should only keep last 540 candles
    assert len(ph.closes) == 540
    assert len(ph.highs) == 540
    assert len(ph.lows) == 540
    assert len(ph.timestamps) == 540

    # Oldest candle should be the 61st one (index 60)
    assert ph.closes[0] == 100.0 + 60

    # Newest candle should be the 600th one (index 599)
    assert ph.closes[-1] == 100.0 + 599


# ============================================================================
# Data Quality Tests
# ============================================================================


def test_get_data_quality_complete():
    """Test data quality assessment with complete 90-day history."""
    ph = PriceHistory()

    base_time = datetime(2024, 1, 1)

    # Add 540 candles (90 days)
    for i in range(540):
        ph.add_candle(
            close=100.0,
            high=101.0,
            low=99.0,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    assert ph.get_data_quality() == "complete"


def test_get_data_quality_partial():
    """Test data quality assessment with partial history (7-90 days)."""
    ph = PriceHistory()

    base_time = datetime(2024, 1, 1)

    # Add 100 candles (between 7d and 90d)
    for i in range(100):
        ph.add_candle(
            close=100.0,
            high=101.0,
            low=99.0,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    assert ph.get_data_quality() == "partial"


def test_get_data_quality_insufficient():
    """Test data quality assessment with insufficient history (<7 days)."""
    ph = PriceHistory()

    base_time = datetime(2024, 1, 1)

    # Add only 20 candles (less than 7 days)
    for i in range(20):
        ph.add_candle(
            close=100.0,
            high=101.0,
            low=99.0,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    assert ph.get_data_quality() == "insufficient"


def test_get_oldest_data_point():
    """Test getting oldest data point timestamp."""
    ph = PriceHistory()

    base_time = datetime(2024, 1, 1)

    # Add some candles
    for i in range(10):
        ph.add_candle(
            close=100.0,
            high=101.0,
            low=99.0,
            timestamp=base_time + timedelta(hours=i * 4),
        )

    oldest = ph.get_oldest_data_point()
    assert oldest == base_time


def test_get_oldest_data_point_empty():
    """Test getting oldest data point with no data."""
    ph = PriceHistory()

    oldest = ph.get_oldest_data_point()
    assert oldest is None
