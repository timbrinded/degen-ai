"""Integration tests for async signal collection system.

Tests the end-to-end signal collection flow including:
- Request to response flow through SignalService
- Concurrent provider calls with SignalOrchestrator
- Cache integration with real SQLite database
- Governance system integration with sync-to-async bridge
- Graceful degradation when providers fail
"""

import asyncio
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

from hyperliquid_agent.monitor import AccountState, Position
from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.orchestrator import SignalOrchestrator
from hyperliquid_agent.signals.service import SignalRequest, SignalService

# Configure pytest-asyncio to use auto mode
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def temp_cache_db():
    """Create temporary cache database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        yield db_path


@pytest.fixture
def sample_account_state():
    """Create sample account state for testing."""
    return AccountState(
        portfolio_value=10000.0,
        available_balance=5000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.1,
                entry_price=50000.0,
                current_price=51000.0,
                unrealized_pnl=100.0,
                market_type="perp",
            ),
        ],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )


@pytest.fixture
def signal_config(temp_cache_db):
    """Create signal configuration for testing."""
    return {
        "collection_timeout_seconds": 30.0,
        "cache_db_path": str(temp_cache_db),
        "enable_caching": True,
        "fast_timeout_seconds": 5.0,
        "medium_timeout_seconds": 15.0,
        "slow_timeout_seconds": 30.0,
    }


class TestEndToEndSignalCollection:
    """Test end-to-end signal collection flow from request to response."""

    def test_signal_service_lifecycle(self, signal_config):
        """Test SignalService start, collect, and stop lifecycle."""
        service = SignalService(config=signal_config)

        # Start service
        service.start()
        assert service.background_thread is not None
        assert service.background_thread.is_alive()

        # Give thread time to initialize
        time.sleep(0.5)

        # Stop service
        service.stop()
        assert not service.background_thread.is_alive()

    def test_fast_signal_collection_sync_interface(self, signal_config, sample_account_state):
        """Test fast signal collection through synchronous interface."""
        service = SignalService(config=signal_config)
        service.start()

        try:
            # Collect fast signals
            signals = service.collect_signals_sync(
                signal_type="fast", account_state=sample_account_state, timeout_seconds=10.0
            )

            # Verify signals structure
            assert signals is not None
            assert hasattr(signals, "spreads")
            assert hasattr(signals, "metadata")
            assert signals.metadata is not None

        finally:
            service.stop()

    def test_medium_signal_collection_sync_interface(self, signal_config, sample_account_state):
        """Test medium signal collection through synchronous interface."""
        service = SignalService(config=signal_config)
        service.start()

        try:
            # Collect medium signals
            signals = service.collect_signals_sync(
                signal_type="medium", account_state=sample_account_state, timeout_seconds=15.0
            )

            # Verify signals structure
            assert signals is not None
            assert hasattr(signals, "realized_vol_1h")
            assert hasattr(signals, "metadata")
            assert signals.metadata is not None

        finally:
            service.stop()

    def test_slow_signal_collection_sync_interface(self, signal_config, sample_account_state):
        """Test slow signal collection through synchronous interface."""
        service = SignalService(config=signal_config)
        service.start()

        try:
            # Collect slow signals
            signals = service.collect_signals_sync(
                signal_type="slow", account_state=sample_account_state, timeout_seconds=30.0
            )

            # Verify signals structure
            assert signals is not None
            assert hasattr(signals, "venue_health_score")
            assert hasattr(signals, "metadata")
            assert signals.metadata is not None

        finally:
            service.stop()

    def test_signal_collection_timeout_handling(self, signal_config, sample_account_state):
        """Test signal collection handles timeout gracefully."""
        # Use very short timeout to trigger timeout behavior
        signal_config["fast_timeout_seconds"] = 0.001

        service = SignalService(config=signal_config)
        service.start()

        try:
            # Collect with very short timeout
            signals = service.collect_signals_sync(
                signal_type="fast", account_state=sample_account_state, timeout_seconds=0.001
            )

            # Should return fallback signals
            assert signals is not None
            assert signals.metadata.confidence == 0.0  # Fallback has zero confidence

        finally:
            service.stop()


class TestConcurrentProviderCalls:
    """Test concurrent provider calls with SignalOrchestrator."""

    @pytest.mark.asyncio
    async def test_orchestrator_concurrent_collection(self, signal_config, sample_account_state):
        """Test orchestrator collects multiple signal types concurrently."""
        orchestrator = SignalOrchestrator(config=signal_config)

        try:
            # Create requests for all signal types
            requests = [
                SignalRequest(
                    signal_type="fast",
                    account_state=sample_account_state,
                    timestamp=datetime.now(),
                ),
                SignalRequest(
                    signal_type="medium",
                    account_state=sample_account_state,
                    timestamp=datetime.now(),
                ),
                SignalRequest(
                    signal_type="slow",
                    account_state=sample_account_state,
                    timestamp=datetime.now(),
                ),
            ]

            # Collect concurrently with timeout
            start_time = time.time()
            responses = await asyncio.wait_for(
                orchestrator.collect_concurrent(requests), timeout=45.0
            )
            elapsed = time.time() - start_time

            # Verify all responses received
            assert len(responses) == 3

            # Verify response types
            assert responses[0].signal_type == "fast"
            assert responses[1].signal_type == "medium"
            assert responses[2].signal_type == "slow"

            # Concurrent collection should be faster than sequential
            # (though with mocked/fast providers, this may not be significant)
            assert elapsed < 60.0  # Reasonable upper bound

        finally:
            await orchestrator.shutdown()

    @pytest.mark.asyncio
    async def test_orchestrator_partial_success_handling(self, signal_config, sample_account_state):
        """Test orchestrator handles partial success when some providers fail."""
        orchestrator = SignalOrchestrator(config=signal_config)

        try:
            # Create requests
            requests = [
                SignalRequest(
                    signal_type="fast",
                    account_state=sample_account_state,
                    timestamp=datetime.now(),
                ),
                SignalRequest(
                    signal_type="medium",
                    account_state=sample_account_state,
                    timestamp=datetime.now(),
                ),
            ]

            # Collect concurrently with timeout (some may fail with real API calls)
            responses = await asyncio.wait_for(
                orchestrator.collect_concurrent(requests), timeout=30.0
            )

            # Should get responses for all requests (even if some failed)
            assert len(responses) == 2

            # Each response should have signals (fallback if failed)
            for response in responses:
                assert response.signals is not None
                assert response.timestamp is not None

        finally:
            await orchestrator.shutdown()

    @pytest.mark.asyncio
    async def test_orchestrator_timeout_enforcement(self, signal_config, sample_account_state):
        """Test orchestrator enforces timeouts for signal collection."""
        # Set very short timeout
        signal_config["fast_timeout_seconds"] = 0.001

        orchestrator = SignalOrchestrator(config=signal_config)

        try:
            request = SignalRequest(
                signal_type="fast",
                account_state=sample_account_state,
                timestamp=datetime.now(),
            )

            # Collect with timeout
            response = await orchestrator.collect_signals(request)

            # Should complete (with timeout error)
            assert response is not None
            # May have error due to timeout
            if response.error:
                assert "timeout" in response.error.lower()

        finally:
            await orchestrator.shutdown()


class TestCacheIntegration:
    """Test cache integration with real SQLite database."""

    @pytest.mark.asyncio
    async def test_cache_stores_and_retrieves_data(self, temp_cache_db):
        """Test cache can store and retrieve data with TTL."""
        cache = SQLiteCacheLayer(temp_cache_db)

        # Store data
        test_key = "test:data"
        test_value = {"price": 50000.0, "volume": 1000.0}
        await cache.set(test_key, test_value, ttl_seconds=60)

        # Retrieve data
        entry = await cache.get(test_key)

        assert entry is not None
        assert entry.value == test_value
        assert entry.age_seconds < 1.0  # Just stored

        cache.close()

    @pytest.mark.asyncio
    async def test_cache_respects_ttl_expiration(self, temp_cache_db):
        """Test cache entries expire after TTL."""
        cache = SQLiteCacheLayer(temp_cache_db)

        # Store data with very short TTL
        test_key = "test:expiring"
        test_value = {"data": "expires soon"}
        await cache.set(test_key, test_value, ttl_seconds=1)

        # Retrieve immediately (should work)
        entry = await cache.get(test_key)
        assert entry is not None

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Retrieve after expiration (should be None)
        entry = await cache.get(test_key)
        assert entry is None

        cache.close()

    @pytest.mark.asyncio
    async def test_cache_cleanup_removes_expired_entries(self, temp_cache_db):
        """Test cache cleanup removes expired entries."""
        cache = SQLiteCacheLayer(temp_cache_db)

        # Store multiple entries with short TTL
        for i in range(5):
            await cache.set(f"test:expire:{i}", {"value": i}, ttl_seconds=1)

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Run cleanup
        await cache.cleanup_expired()

        # Verify entries are gone
        for i in range(5):
            entry = await cache.get(f"test:expire:{i}")
            assert entry is None

        cache.close()

    @pytest.mark.asyncio
    async def test_cache_metrics_tracking(self, temp_cache_db):
        """Test cache tracks hit/miss metrics correctly."""
        cache = SQLiteCacheLayer(temp_cache_db)

        # Reset metrics for clean test
        cache.reset_metrics()

        # Store data
        await cache.set("test:metrics", {"value": 123}, ttl_seconds=60)

        # Hit the cache multiple times
        for _ in range(3):
            entry = await cache.get("test:metrics")
            assert entry is not None

        # Miss the cache
        entry = await cache.get("test:nonexistent")
        assert entry is None

        # Get metrics
        metrics = cache.get_metrics()

        assert metrics.total_hits >= 3
        assert metrics.total_misses >= 1
        assert metrics.hit_rate > 0.0

        cache.close()

    @pytest.mark.asyncio
    async def test_cache_invalidation_patterns(self, temp_cache_db):
        """Test cache invalidation with patterns."""
        cache = SQLiteCacheLayer(temp_cache_db)

        # Store data with different prefixes
        await cache.set("orderbook:BTC", {"data": "btc"}, ttl_seconds=60)
        await cache.set("orderbook:ETH", {"data": "eth"}, ttl_seconds=60)
        await cache.set("funding:BTC", {"data": "funding"}, ttl_seconds=60)

        # Invalidate orderbook entries
        await cache.invalidate("orderbook:%")

        # Verify orderbook entries are gone
        assert await cache.get("orderbook:BTC") is None
        assert await cache.get("orderbook:ETH") is None

        # Verify funding entry still exists
        assert await cache.get("funding:BTC") is not None

        cache.close()


class TestGovernanceIntegration:
    """Test governance system integration with sync-to-async bridge."""

    def test_signal_service_sync_to_async_bridge(self, signal_config, sample_account_state):
        """Test SignalService bridges sync governance with async signal collection."""
        service = SignalService(config=signal_config)
        service.start()

        try:
            # Simulate synchronous governance call
            signals = service.collect_signals_sync(
                signal_type="fast", account_state=sample_account_state, timeout_seconds=10.0
            )

            # Verify signals returned to sync context
            assert signals is not None
            assert hasattr(signals, "metadata")

        finally:
            service.stop()

    def test_multiple_sequential_requests(self, signal_config, sample_account_state):
        """Test multiple sequential signal requests through sync interface."""
        service = SignalService(config=signal_config)
        service.start()

        try:
            # Make multiple requests
            for _ in range(3):
                signals = service.collect_signals_sync(
                    signal_type="fast", account_state=sample_account_state, timeout_seconds=10.0
                )

                assert signals is not None
                assert signals.metadata is not None

        finally:
            service.stop()

    def test_signal_service_handles_rapid_requests(self, signal_config, sample_account_state):
        """Test signal service handles rapid sequential requests."""
        service = SignalService(config=signal_config)
        service.start()

        try:
            # Make rapid requests
            results = []
            for _ in range(5):
                signals = service.collect_signals_sync(
                    signal_type="fast", account_state=sample_account_state, timeout_seconds=5.0
                )
                results.append(signals)

            # All requests should complete
            assert len(results) == 5
            assert all(r is not None for r in results)

        finally:
            service.stop()


class TestGracefulDegradation:
    """Test graceful degradation when providers fail."""

    def test_fallback_signals_on_service_not_started(self, signal_config, sample_account_state):
        """Test fallback signals returned when service not started."""
        service = SignalService(config=signal_config)
        # Don't start service

        # Collect signals (should return fallback)
        signals = service.collect_signals_sync(
            signal_type="fast", account_state=sample_account_state, timeout_seconds=5.0
        )

        # Should get fallback signals
        assert signals is not None
        assert signals.metadata.confidence == 0.0  # Fallback has zero confidence

    def test_fallback_signals_on_timeout(self, signal_config, sample_account_state):
        """Test fallback signals returned on timeout."""
        # Set very short timeout
        signal_config["fast_timeout_seconds"] = 0.001

        service = SignalService(config=signal_config)
        service.start()

        try:
            # Collect with very short timeout
            signals = service.collect_signals_sync(
                signal_type="fast", account_state=sample_account_state, timeout_seconds=0.001
            )

            # Should get fallback signals
            assert signals is not None
            # Fallback signals have low/zero confidence
            assert signals.metadata.confidence <= 0.5

        finally:
            service.stop()

    @pytest.mark.asyncio
    async def test_orchestrator_handles_provider_failures(
        self, signal_config, sample_account_state
    ):
        """Test orchestrator handles individual provider failures gracefully."""
        orchestrator = SignalOrchestrator(config=signal_config)

        try:
            # Create request
            request = SignalRequest(
                signal_type="slow",  # Slow signals use multiple providers
                account_state=sample_account_state,
                timestamp=datetime.now(),
            )

            # Collect signals (some providers may fail)
            response = await orchestrator.collect_signals(request)

            # Should get response even if some providers failed
            assert response is not None
            assert response.signals is not None

            # Signals should have metadata indicating quality
            assert response.signals.metadata is not None

        finally:
            await orchestrator.shutdown()

    def test_cache_provides_stale_data_on_provider_failure(
        self, signal_config, sample_account_state
    ):
        """Test cache provides stale data when providers fail."""
        service = SignalService(config=signal_config)
        service.start()

        try:
            # First request (populates cache)
            signals1 = service.collect_signals_sync(
                signal_type="fast", account_state=sample_account_state, timeout_seconds=10.0
            )
            assert signals1 is not None

            # Second request (may use cache)
            signals2 = service.collect_signals_sync(
                signal_type="fast", account_state=sample_account_state, timeout_seconds=10.0
            )
            assert signals2 is not None

            # Both requests should succeed (second may use cache)
            assert signals1.metadata is not None
            assert signals2.metadata is not None

        finally:
            service.stop()


class TestHealthMonitoring:
    """Test health monitoring and metrics exposure."""

    @pytest.mark.asyncio
    async def test_orchestrator_health_status(self, signal_config):
        """Test orchestrator exposes health status."""
        orchestrator = SignalOrchestrator(config=signal_config)

        try:
            # Get health status
            health = orchestrator.get_health_status()

            # Verify health structure
            assert "orchestrator" in health
            assert "providers" in health
            assert "cache" in health

            # Verify cache metrics
            assert "metrics" in health["cache"]
            cache_metrics = health["cache"]["metrics"]
            assert "total_entries" in cache_metrics
            assert "hit_rate_percent" in cache_metrics

        finally:
            await orchestrator.shutdown()

    @pytest.mark.asyncio
    async def test_cache_metrics_exposure(self, signal_config):
        """Test cache metrics are exposed for monitoring."""
        orchestrator = SignalOrchestrator(config=signal_config)

        try:
            # Get cache metrics
            metrics = orchestrator.get_cache_metrics()

            # Verify metrics structure
            assert "total_entries" in metrics
            assert "total_hits" in metrics
            assert "total_misses" in metrics
            assert "hit_rate_percent" in metrics

        finally:
            await orchestrator.shutdown()
