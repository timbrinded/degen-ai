"""Unit tests for cache metrics functionality."""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hyperliquid_agent.monitor_enhanced import EnhancedPositionMonitor
from hyperliquid_agent.signals.orchestrator import SignalOrchestrator
from hyperliquid_agent.signals.service import SignalService

# ============================================================================
# Orchestrator Cache Metrics Tests
# ============================================================================


def test_orchestrator_get_cache_metrics():
    """Test orchestrator returns cache metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        config = {"cache_db_path": str(db_path)}

        orchestrator = SignalOrchestrator(config)

        # Get cache metrics
        metrics = orchestrator.get_cache_metrics()

        # Verify metrics structure
        assert isinstance(metrics, dict)
        assert "total_entries" in metrics
        assert "total_hits" in metrics
        assert "total_misses" in metrics
        assert "hit_rate_percent" in metrics
        assert "avg_hits_per_entry" in metrics
        assert "avg_age_seconds" in metrics
        assert "expired_entries" in metrics

        # Initial values should be zero
        assert metrics["total_entries"] == 0
        assert metrics["total_hits"] == 0
        assert metrics["total_misses"] == 0
        assert metrics["hit_rate_percent"] == 0.0


@pytest.mark.anyio
async def test_orchestrator_cache_metrics_with_data():
    """Test orchestrator cache metrics with actual cached data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        config = {"cache_db_path": str(db_path)}

        orchestrator = SignalOrchestrator(config)

        # Add some data to cache
        await orchestrator.cache.set("test_key_1", {"data": "value1"}, ttl_seconds=60)
        await orchestrator.cache.set("test_key_2", {"data": "value2"}, ttl_seconds=60)

        # Simulate cache hits
        await orchestrator.cache.get("test_key_1")
        await orchestrator.cache.get("test_key_1")
        await orchestrator.cache.get("test_key_2")

        # Simulate cache miss
        await orchestrator.cache.get("nonexistent_key")

        # Get metrics
        metrics = orchestrator.get_cache_metrics()

        # Verify metrics reflect activity
        assert metrics["total_entries"] == 2
        assert metrics["total_hits"] == 3
        assert metrics["total_misses"] == 1
        assert metrics["hit_rate_percent"] == 75.0


# ============================================================================
# Monitor Enhanced Cache Metrics Tests
# ============================================================================


@patch("hyperliquid_agent.monitor_enhanced.SignalService")
def test_monitor_get_cache_metrics_success(mock_signal_service_class):
    """Test monitor successfully retrieves cache metrics from orchestrator."""
    # Setup mock orchestrator with cache metrics
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_cache_metrics.return_value = {
        "total_entries": 10,
        "total_hits": 50,
        "total_misses": 5,
        "hit_rate_percent": 90.91,
        "avg_hits_per_entry": 5.0,
        "avg_age_seconds": 120.5,
        "expired_entries": 2,
    }

    # Setup mock signal service
    mock_signal_service = MagicMock()
    mock_signal_service.orchestrator = mock_orchestrator
    mock_signal_service_class.return_value = mock_signal_service

    # Create monitor
    from hyperliquid_agent.config import HyperliquidConfig

    config = HyperliquidConfig(
        account_address="0x1234567890123456789012345678901234567890",
        secret_key="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        base_url="https://api.hyperliquid-testnet.xyz",
    )

    monitor = EnhancedPositionMonitor(config)

    # Get cache metrics
    result = monitor.get_cache_metrics()

    # Verify result structure
    assert result["status"] == "success"
    assert "cache" in result
    assert result["cache"]["total_entries"] == 10
    assert result["cache"]["total_hits"] == 50
    assert result["cache"]["total_misses"] == 5
    assert result["cache"]["hit_rate_percent"] == 90.91

    # Verify orchestrator method was called
    mock_orchestrator.get_cache_metrics.assert_called_once()


@patch("hyperliquid_agent.monitor_enhanced.SignalService")
def test_monitor_get_cache_metrics_orchestrator_unavailable(mock_signal_service_class):
    """Test monitor handles orchestrator unavailability."""
    # Setup mock signal service with no orchestrator
    mock_signal_service = MagicMock()
    mock_signal_service.orchestrator = None
    mock_signal_service_class.return_value = mock_signal_service

    # Create monitor
    from hyperliquid_agent.config import HyperliquidConfig

    config = HyperliquidConfig(
        account_address="0x1234567890123456789012345678901234567890",
        secret_key="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        base_url="https://api.hyperliquid-testnet.xyz",
    )

    monitor = EnhancedPositionMonitor(config)

    # Get cache metrics
    result = monitor.get_cache_metrics()

    # Verify error response
    assert result["status"] == "orchestrator_not_available"
    assert "error" in result
    assert "Orchestrator not available" in result["error"]


@patch("hyperliquid_agent.monitor_enhanced.SignalService")
def test_monitor_get_cache_metrics_no_signal_service(mock_signal_service_class):
    """Test monitor handles missing signal service."""
    # Create monitor but delete signal service
    from hyperliquid_agent.config import HyperliquidConfig

    config = HyperliquidConfig(
        account_address="0x1234567890123456789012345678901234567890",
        secret_key="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        base_url="https://api.hyperliquid-testnet.xyz",
    )

    monitor = EnhancedPositionMonitor(config)
    del monitor.signal_service

    # Get cache metrics
    result = monitor.get_cache_metrics()

    # Verify error response
    assert result["status"] == "orchestrator_not_available"
    assert "error" in result
    assert "Signal service not initialized" in result["error"]


@patch("hyperliquid_agent.monitor_enhanced.SignalService")
def test_monitor_get_cache_metrics_exception_handling(mock_signal_service_class):
    """Test monitor handles exceptions when retrieving cache metrics."""
    # Setup mock orchestrator that raises exception
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_cache_metrics.side_effect = Exception("Database connection failed")

    # Setup mock signal service
    mock_signal_service = MagicMock()
    mock_signal_service.orchestrator = mock_orchestrator
    mock_signal_service_class.return_value = mock_signal_service

    # Create monitor
    from hyperliquid_agent.config import HyperliquidConfig

    config = HyperliquidConfig(
        account_address="0x1234567890123456789012345678901234567890",
        secret_key="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        base_url="https://api.hyperliquid-testnet.xyz",
    )

    monitor = EnhancedPositionMonitor(config)

    # Get cache metrics
    result = monitor.get_cache_metrics()

    # Verify error response
    assert result["status"] == "error"
    assert "error" in result
    assert "Database connection failed" in result["error"]


# ============================================================================
# Integration Tests
# ============================================================================


def test_signal_service_orchestrator_reference():
    """Test signal service properly stores orchestrator reference."""
    from hyperliquid_agent.monitor import AccountState

    service = SignalService()
    service.start()

    try:
        # The orchestrator is created when _process_requests starts
        # We need to trigger a request to ensure the event loop is running
        account_state = AccountState(
            portfolio_value=10000.0,
            available_balance=5000.0,
            positions=[],
            spot_balances={},
            timestamp=time.time(),
        )

        # Make a request to trigger orchestrator initialization
        service.collect_signals_sync("fast", account_state, timeout_seconds=5.0)

        # Now orchestrator should be available
        assert service.orchestrator is not None, "Orchestrator not initialized after request"
        assert hasattr(service.orchestrator, "get_cache_metrics")

        # Get cache metrics through orchestrator
        metrics = service.orchestrator.get_cache_metrics()
        assert isinstance(metrics, dict)
        assert "total_entries" in metrics

    finally:
        service.stop()


def test_end_to_end_cache_metrics_flow():
    """Test complete flow from monitor to orchestrator cache metrics."""
    # This test uses real components (not mocked) to verify integration
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"

        # Create signal service with custom cache path
        config = {"cache_db_path": str(db_path)}
        service = SignalService(config)
        service.start()

        try:
            # Give service time to initialize orchestrator
            max_wait = 2.0  # Maximum wait time in seconds
            wait_interval = 0.1
            elapsed = 0.0

            while service.orchestrator is None and elapsed < max_wait:
                time.sleep(wait_interval)
                elapsed += wait_interval

            # Verify orchestrator is available
            assert service.orchestrator is not None, "Orchestrator not initialized after waiting"

            # Get cache metrics directly from orchestrator
            metrics = service.orchestrator.get_cache_metrics()

            # Verify metrics structure
            assert isinstance(metrics, dict)
            assert "total_entries" in metrics
            assert "total_hits" in metrics
            assert "hit_rate_percent" in metrics

            # Initial state should be empty
            assert metrics["total_entries"] == 0
            assert metrics["total_hits"] == 0

        finally:
            service.stop()
