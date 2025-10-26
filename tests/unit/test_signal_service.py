"""Unit tests for signal service and cache layer."""

import tempfile
import time
from pathlib import Path

import pytest

from hyperliquid_agent.monitor import AccountState
from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.models import FastLoopSignals
from hyperliquid_agent.signals.service import SignalService

# ============================================================================
# SQLiteCacheLayer Tests
# ============================================================================


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


@pytest.mark.anyio
async def test_cache_set_and_get():
    """Test basic cache set and get operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Set a value
        test_data = {"price": 50000.0, "volume": 1000.0}
        await cache.set("test_key", test_data, ttl_seconds=60)

        # Get the value
        entry = await cache.get("test_key")
        assert entry is not None
        assert entry.value == test_data
        assert entry.age_seconds >= 0
        assert entry.age_seconds < 1  # Should be very fresh


@pytest.mark.anyio
async def test_cache_ttl_expiration():
    """Test that cache entries expire after TTL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Set a value with 1 second TTL
        await cache.set("expiring_key", "test_value", ttl_seconds=1)

        # Should be available immediately
        entry = await cache.get("expiring_key")
        assert entry is not None
        assert entry.value == "test_value"

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        entry = await cache.get("expiring_key")
        assert entry is None


@pytest.mark.anyio
async def test_cache_hit_miss_tracking():
    """Test cache hit and miss tracking for metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Initial metrics
        metrics = cache.get_metrics()
        assert metrics.total_hits == 0
        assert metrics.total_misses == 0
        assert metrics.hit_rate == 0.0

        # Set a value
        await cache.set("key1", "value1", ttl_seconds=60)

        # First get is a hit
        await cache.get("key1")
        metrics = cache.get_metrics()
        assert metrics.total_hits == 1
        assert metrics.total_misses == 0
        assert metrics.hit_rate == 100.0

        # Miss on non-existent key
        await cache.get("nonexistent")
        metrics = cache.get_metrics()
        assert metrics.total_hits == 1
        assert metrics.total_misses == 1
        assert metrics.hit_rate == 50.0

        # Another hit
        await cache.get("key1")
        metrics = cache.get_metrics()
        assert metrics.total_hits == 2
        assert metrics.total_misses == 1
        assert metrics.hit_rate == pytest.approx(66.67, rel=0.1)


@pytest.mark.anyio
async def test_cache_cleanup_expired():
    """Test cleanup of expired entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Add entries with different TTLs
        await cache.set("short_ttl", "value1", ttl_seconds=1)
        await cache.set("long_ttl", "value2", ttl_seconds=60)

        # Wait for short TTL to expire
        time.sleep(1.1)

        # Before cleanup, metrics show expired entry
        metrics = cache.get_metrics()
        assert metrics.expired_entries == 1

        # Run cleanup
        await cache.cleanup_expired()

        # After cleanup, expired entry should be removed
        metrics = cache.get_metrics()
        assert metrics.expired_entries == 0
        assert metrics.total_entries == 1  # Only long_ttl remains


@pytest.mark.anyio
async def test_cache_invalidate_pattern():
    """Test cache invalidation by pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Add multiple entries
        await cache.set("orderbook:BTC", "btc_data", ttl_seconds=60)
        await cache.set("orderbook:ETH", "eth_data", ttl_seconds=60)
        await cache.set("funding:BTC", "funding_data", ttl_seconds=60)

        # Invalidate all orderbook entries
        await cache.invalidate("orderbook:%")

        # Orderbook entries should be gone
        assert await cache.get("orderbook:BTC") is None
        assert await cache.get("orderbook:ETH") is None

        # Funding entry should remain
        entry = await cache.get("funding:BTC")
        assert entry is not None
        assert entry.value == "funding_data"


@pytest.mark.anyio
async def test_cache_invalidate_by_key():
    """Test cache invalidation by exact key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Add entries
        await cache.set("key1", "value1", ttl_seconds=60)
        await cache.set("key2", "value2", ttl_seconds=60)

        # Invalidate specific key
        await cache.invalidate_by_key("key1")

        # key1 should be gone
        assert await cache.get("key1") is None

        # key2 should remain
        entry = await cache.get("key2")
        assert entry is not None
        assert entry.value == "value2"


@pytest.mark.anyio
async def test_cache_invalidate_all():
    """Test invalidation of all cache entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Add multiple entries
        await cache.set("key1", "value1", ttl_seconds=60)
        await cache.set("key2", "value2", ttl_seconds=60)
        await cache.set("key3", "value3", ttl_seconds=60)

        # Invalidate all
        await cache.invalidate_all()

        # All entries should be gone
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is None

        metrics = cache.get_metrics()
        assert metrics.total_entries == 0


@pytest.mark.anyio
async def test_cache_metrics_avg_age():
    """Test average age calculation in metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Add entry and wait
        await cache.set("key1", "value1", ttl_seconds=60)
        time.sleep(0.5)

        metrics = cache.get_metrics()
        assert metrics.avg_age_seconds >= 0.5
        assert metrics.avg_age_seconds < 1.0


def test_cache_reset_metrics():
    """Test resetting cache metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = SQLiteCacheLayer(db_path)

        # Simulate some activity
        cache._total_requests = 10
        cache._total_hits = 7

        # Reset metrics
        cache.reset_metrics()

        assert cache._total_requests == 0
        assert cache._total_hits == 0

        metrics = cache.get_metrics()
        assert metrics.hit_rate == 0.0


# ============================================================================
# SignalService Tests
# ============================================================================


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

        # Create minimal account state
        account_state = AccountState(
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

    account_state = AccountState(
        portfolio_value=10000.0,
        available_balance=5000.0,
        positions=[],
        spot_balances={},
        timestamp=time.time(),
    )

    # Should return fallback signals
    signals = service.collect_signals_sync("fast", account_state, timeout_seconds=1.0)

    assert signals is not None
    assert isinstance(signals, FastLoopSignals)
    assert signals.spreads == {}
    assert signals.slippage_estimates == {}


def test_signal_service_thread_safety():
    """Test thread-safe queue communication."""
    service = SignalService()
    service.start()

    try:
        time.sleep(0.2)

        account_state = AccountState(
            portfolio_value=10000.0,
            available_balance=5000.0,
            positions=[],
            spot_balances={},
            timestamp=time.time(),
        )

        # Make multiple concurrent requests
        import threading

        results = []

        def collect_signals():
            signals = service.collect_signals_sync("fast", account_state, timeout_seconds=5.0)
            results.append(signals)

        threads = [threading.Thread(target=collect_signals) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All requests should complete successfully
        assert len(results) == 3
        assert all(r is not None for r in results)

    finally:
        service.stop()
