"""Unit tests for signal service and cache layer."""

import tempfile
import time
from pathlib import Path

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.service import SignalService


def test_cache_initialization():
    """Test cache database initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Database file should be created
        assert db_path.exists()

        # Should be able to get metrics
        metrics = cache.get_metrics()
        assert metrics.total_entries == 0
        assert metrics.total_hits == 0


def test_cache_vacuum():
    """Test cache vacuum operation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Should not raise error
        cache.vacuum()


def test_signal_service_start_stop():
    """Test signal service lifecycle."""
    service = SignalService()

    # Start service
    service.start()
    assert service.background_thread is not None
    assert service.background_thread.is_alive()

    # Give it a moment to initialize
    time.sleep(0.1)

    # Stop service
    service.stop()
    time.sleep(0.2)

    # Thread should be stopped
    assert not service.background_thread.is_alive()


def test_signal_service_collect_signals_sync():
    """Test synchronous signal collection interface."""
    service = SignalService()
    service.start()

    try:
        # Give service time to start
        time.sleep(0.2)

        # Create minimal account state using dataclass
        from dataclasses import dataclass

        @dataclass
        class TestAccountState:
            portfolio_value: float
            available_balance: float
            positions: list
            spot_balances: dict
            timestamp: float
            is_stale: bool = False

        account_state = TestAccountState(
            portfolio_value=10000.0,
            available_balance=5000.0,
            positions=[],
            spot_balances={},
            timestamp=time.time(),
        )

        # Collect fast signals with short timeout
        signals = service.collect_signals_sync("fast", account_state, timeout_seconds=5.0)

        # Should return signals (even if empty/default)
        assert signals is not None
        assert hasattr(signals, "spreads")
        assert hasattr(signals, "slippage_estimates")

    finally:
        service.stop()


def test_signal_service_timeout_fallback():
    """Test fallback behavior on timeout."""
    service = SignalService()

    # Don't start service - should return fallback immediately
    from dataclasses import dataclass

    @dataclass
    class TestAccountState:
        portfolio_value: float
        available_balance: float
        positions: list
        spot_balances: dict
        timestamp: float
        is_stale: bool = False

    account_state = TestAccountState(
        portfolio_value=10000.0,
        available_balance=5000.0,
        positions=[],
        spot_balances={},
        timestamp=time.time(),
    )

    # Should return fallback signals
    signals = service.collect_signals_sync("fast", account_state, timeout_seconds=1.0)

    assert signals is not None
    assert signals.spreads == {}
    assert signals.slippage_estimates == {}
