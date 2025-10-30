"""Unit tests for OpenInterestHistory class."""

from datetime import datetime, timedelta

from hyperliquid_agent.signals.collectors import OpenInterestHistory

# ============================================================================
# 24h Change Calculation Tests
# ============================================================================


def test_calculate_24h_change_with_known_sequence():
    """Test 24h change calculation with known OI sequences."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add 7 candles (24 hours of 4-hour candles)
    # OI increases from 1000 to 1200 over 24 hours
    for i in range(7):
        timestamp = base_time + timedelta(hours=i * 4)
        oi_value = 1000.0 + (i * 200.0 / 6)  # Linear increase

        oih.add_value(oi_value, timestamp)

    # Calculate 24h change
    change = oih.calculate_24h_change()

    assert change is not None
    # Change from 1000 to ~1200 = 20% increase
    assert abs(change - 20.0) < 1.0


def test_calculate_24h_change_decrease():
    """Test 24h change calculation with decreasing OI."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add 7 candles with decreasing OI
    for i in range(7):
        timestamp = base_time + timedelta(hours=i * 4)
        oi_value = 1000.0 - (i * 200.0 / 6)  # Linear decrease

        oih.add_value(oi_value, timestamp)

    # Calculate 24h change
    change = oih.calculate_24h_change()

    assert change is not None
    # Change from 1000 to ~800 = -20% decrease
    assert abs(change - (-20.0)) < 1.0


def test_calculate_24h_change_no_change():
    """Test 24h change calculation with stable OI."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add 7 candles with constant OI
    for i in range(7):
        timestamp = base_time + timedelta(hours=i * 4)
        oih.add_value(1000.0, timestamp)

    # Calculate 24h change
    change = oih.calculate_24h_change()

    assert change is not None
    assert abs(change) < 0.1  # Should be ~0%


# ============================================================================
# Insufficient Data Handling Tests
# ============================================================================


def test_calculate_24h_change_insufficient_data():
    """Test that insufficient data returns None."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add only 5 candles (need at least 7 for 24h)
    for i in range(5):
        timestamp = base_time + timedelta(hours=i * 4)
        oih.add_value(1000.0, timestamp)

    # Should return None due to insufficient data
    change = oih.calculate_24h_change()
    assert change is None


def test_calculate_24h_change_empty():
    """Test that empty history returns None."""
    oih = OpenInterestHistory(lookback_hours=24)

    # No data added
    change = oih.calculate_24h_change()
    assert change is None


def test_calculate_24h_change_single_value():
    """Test that single value returns None."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)
    oih.add_value(1000.0, base_time)

    # Should return None with only one data point
    change = oih.calculate_24h_change()
    assert change is None


# ============================================================================
# Zero OI Edge Cases
# ============================================================================


def test_calculate_24h_change_zero_initial_oi():
    """Test 24h change calculation when initial OI is zero."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add 7 candles starting from zero OI
    for i in range(7):
        timestamp = base_time + timedelta(hours=i * 4)
        oi_value = i * 100.0  # Starts at 0

        oih.add_value(oi_value, timestamp)

    # Should return None when dividing by zero
    change = oih.calculate_24h_change()
    assert change is None


def test_calculate_24h_change_all_zero():
    """Test 24h change calculation when all OI values are zero."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add 7 candles with zero OI
    for i in range(7):
        timestamp = base_time + timedelta(hours=i * 4)
        oih.add_value(0.0, timestamp)

    # Should return None when dividing by zero
    change = oih.calculate_24h_change()
    assert change is None


def test_calculate_24h_change_zero_to_positive():
    """Test 24h change from zero to positive OI."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # First value is zero
    oih.add_value(0.0, base_time)

    # Add 6 more candles with positive OI
    for i in range(1, 7):
        timestamp = base_time + timedelta(hours=i * 4)
        oih.add_value(1000.0, timestamp)

    # Should return None due to zero initial value
    change = oih.calculate_24h_change()
    assert change is None


# ============================================================================
# Deque Overflow Tests
# ============================================================================


def test_deque_overflow_behavior():
    """Test deque overflow behavior with more than required data points."""
    oih = OpenInterestHistory(lookback_hours=24)  # Max 7 candles

    base_time = datetime(2024, 1, 1)

    # Add 20 candles (more than max of 7)
    for i in range(20):
        timestamp = base_time + timedelta(hours=i * 4)
        oi_value = 1000.0 + i * 10.0

        oih.add_value(oi_value, timestamp)

    # Should only keep last 7 candles
    assert len(oih.values) == 7
    assert len(oih.timestamps) == 7

    # Oldest value should be from index 13 (20 - 7)
    assert oih.values[0] == 1000.0 + 13 * 10.0

    # Newest value should be from index 19
    assert oih.values[-1] == 1000.0 + 19 * 10.0


def test_deque_overflow_24h_change():
    """Test 24h change calculation after deque overflow."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add 20 candles (more than max of 7)
    for i in range(20):
        timestamp = base_time + timedelta(hours=i * 4)
        oi_value = 1000.0 + i * 10.0

        oih.add_value(oi_value, timestamp)

    # Calculate 24h change using oldest and newest in deque
    change = oih.calculate_24h_change()

    assert change is not None
    # Oldest in deque: 1000 + 13*10 = 1130
    # Newest in deque: 1000 + 19*10 = 1190
    # Change: (1190 - 1130) / 1130 * 100 = ~5.31%
    expected_change = ((1190.0 - 1130.0) / 1130.0) * 100
    assert abs(change - expected_change) < 0.1


# ============================================================================
# Timestamp Tracking Tests
# ============================================================================


def test_timestamps_stored_correctly():
    """Test that timestamps are stored correctly with OI values."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add candles with specific timestamps
    for i in range(7):
        timestamp = base_time + timedelta(hours=i * 4)
        oih.add_value(1000.0 + i, timestamp)

    # Verify timestamps match
    assert len(oih.timestamps) == 7
    assert oih.timestamps[0] == base_time
    assert oih.timestamps[-1] == base_time + timedelta(hours=6 * 4)


def test_get_oldest_timestamp():
    """Test getting the oldest timestamp."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add some candles
    for i in range(5):
        timestamp = base_time + timedelta(hours=i * 4)
        oih.add_value(1000.0, timestamp)

    # Oldest timestamp should be the first one
    assert oih.timestamps[0] == base_time


def test_get_newest_timestamp():
    """Test getting the newest timestamp."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add some candles
    for i in range(5):
        timestamp = base_time + timedelta(hours=i * 4)
        oih.add_value(1000.0, timestamp)

    # Newest timestamp should be the last one
    expected_newest = base_time + timedelta(hours=4 * 4)
    assert oih.timestamps[-1] == expected_newest


# ============================================================================
# Negative OI Tests (Edge Case)
# ============================================================================


def test_calculate_24h_change_negative_oi():
    """Test 24h change calculation with negative OI values (edge case)."""
    oih = OpenInterestHistory(lookback_hours=24)

    base_time = datetime(2024, 1, 1)

    # Add 7 candles with negative OI (shouldn't happen in practice)
    for i in range(7):
        timestamp = base_time + timedelta(hours=i * 4)
        oi_value = -1000.0 - i * 10.0

        oih.add_value(oi_value, timestamp)

    # Should still calculate change correctly
    change = oih.calculate_24h_change()

    assert change is not None
    # From -1000 to -1060, change = -6%
    expected_change = ((-1060.0 - (-1000.0)) / abs(-1000.0)) * 100
    assert abs(change - expected_change) < 0.1
