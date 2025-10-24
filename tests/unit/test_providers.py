"""Unit tests for data provider base classes, retry logic, and circuit breaker."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from hyperliquid_agent.signals.providers import (
    CircuitBreaker,
    CircuitState,
    DataProvider,
    ProviderResponse,
    RetryConfig,
    fetch_with_retry,
)

# ============================================================================
# RetryConfig and fetch_with_retry Tests
# ============================================================================


@pytest.mark.anyio
async def test_fetch_with_retry_success_first_attempt():
    """Test successful fetch on first attempt."""
    mock_func = AsyncMock(return_value="success")

    result = await fetch_with_retry(
        mock_func, RetryConfig(max_attempts=3), operation_name="test_op"
    )

    assert result == "success"
    assert mock_func.call_count == 1


@pytest.mark.anyio
async def test_fetch_with_retry_success_after_failures():
    """Test successful fetch after initial failures."""
    call_count = 0

    async def failing_then_success():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Temporary failure")
        return "success"

    result = await fetch_with_retry(
        failing_then_success, RetryConfig(max_attempts=3), operation_name="test_op"
    )

    assert result == "success"
    assert call_count == 3


@pytest.mark.anyio
async def test_fetch_with_retry_all_attempts_fail():
    """Test that exception is raised after all retries fail."""
    mock_func = AsyncMock(side_effect=ValueError("Persistent failure"))

    with pytest.raises(ValueError, match="Persistent failure"):
        await fetch_with_retry(mock_func, RetryConfig(max_attempts=3), operation_name="test_op")

    assert mock_func.call_count == 3


@pytest.mark.anyio
async def test_fetch_with_retry_exponential_backoff():
    """Test exponential backoff timing."""
    call_times = []

    async def track_timing():
        call_times.append(asyncio.get_event_loop().time())
        raise ValueError("Fail")

    retry_config = RetryConfig(
        max_attempts=3, initial_delay_seconds=0.1, backoff_factor=2.0, max_delay_seconds=10.0
    )

    with pytest.raises(ValueError):
        await fetch_with_retry(track_timing, retry_config, operation_name="test_op")

    # Should have 3 attempts
    assert len(call_times) == 3

    # Check delays are approximately exponential
    # First delay: ~0.1s, second delay: ~0.2s
    if len(call_times) >= 3:
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]

        # Allow some tolerance for timing
        assert 0.08 <= delay1 <= 0.15
        assert 0.18 <= delay2 <= 0.25


@pytest.mark.anyio
async def test_fetch_with_retry_max_delay_cap():
    """Test that delay is capped at max_delay_seconds."""
    call_times = []

    async def track_timing():
        call_times.append(asyncio.get_event_loop().time())
        raise ValueError("Fail")

    retry_config = RetryConfig(
        max_attempts=4,
        initial_delay_seconds=1.0,
        backoff_factor=10.0,  # Would create huge delays
        max_delay_seconds=0.2,  # But capped at 0.2s
    )

    with pytest.raises(ValueError):
        await fetch_with_retry(track_timing, retry_config, operation_name="test_op")

    # All delays should be capped at max_delay_seconds
    if len(call_times) >= 3:
        for i in range(1, len(call_times)):
            delay = call_times[i] - call_times[i - 1]
            assert delay <= 0.25  # Allow some tolerance


# ============================================================================
# CircuitBreaker Tests
# ============================================================================


def test_circuit_breaker_initial_state():
    """Test circuit breaker starts in closed state."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=60)

    assert cb.get_state() == CircuitState.CLOSED
    assert cb.failure_count == 0
    assert cb.can_attempt() is True


def test_circuit_breaker_record_success():
    """Test recording successful calls."""
    cb = CircuitBreaker(failure_threshold=3)

    # Record some failures
    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 2

    # Success should reset
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.get_state() == CircuitState.CLOSED


def test_circuit_breaker_opens_after_threshold():
    """Test circuit opens after failure threshold."""
    cb = CircuitBreaker(failure_threshold=3)

    # Record failures up to threshold
    cb.record_failure()
    assert cb.get_state() == CircuitState.CLOSED

    cb.record_failure()
    assert cb.get_state() == CircuitState.CLOSED

    cb.record_failure()
    assert cb.get_state() == CircuitState.OPEN
    assert cb.can_attempt() is False


def test_circuit_breaker_half_open_after_timeout():
    """Test circuit enters half-open state after recovery timeout."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=1)

    # Open the circuit
    cb.record_failure()
    cb.record_failure()
    assert cb.get_state() == CircuitState.OPEN
    assert cb.can_attempt() is False

    # Wait for recovery timeout
    import time

    time.sleep(1.1)

    # Should now allow attempt (half-open)
    assert cb.can_attempt() is True
    assert cb.get_state() == CircuitState.HALF_OPEN


def test_circuit_breaker_closes_on_half_open_success():
    """Test circuit closes after successful call in half-open state."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=1)

    # Open the circuit
    cb.record_failure()
    cb.record_failure()
    assert cb.get_state() == CircuitState.OPEN

    # Wait for recovery
    import time

    time.sleep(1.1)
    assert cb.can_attempt() is True

    # Success in half-open should close circuit
    cb.record_success()
    assert cb.get_state() == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_circuit_breaker_reopens_on_half_open_failure():
    """Test circuit reopens if half-open attempt fails."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=1)

    # Open the circuit
    cb.record_failure()
    cb.record_failure()
    assert cb.get_state() == CircuitState.OPEN

    # Wait for recovery
    import time

    time.sleep(1.1)
    assert cb.can_attempt() is True

    # Failure in half-open should reopen circuit
    cb.record_failure()
    assert cb.get_state() == CircuitState.OPEN
    assert cb.can_attempt() is False


# ============================================================================
# DataProvider Base Class Tests
# ============================================================================


class TestDataProvider(DataProvider):
    """Concrete implementation for testing."""

    def __init__(self):
        super().__init__()
        self.fetch_called = False

    async def fetch(self, **kwargs) -> ProviderResponse:
        self.fetch_called = True
        return ProviderResponse(
            data={"test": "data"},
            timestamp=datetime.now(),
            source="test_provider",
            confidence=1.0,
            is_cached=False,
        )

    def get_cache_ttl(self) -> int:
        return 60

    def get_provider_name(self) -> str:
        return "test_provider"


@pytest.mark.anyio
async def test_data_provider_fetch_with_circuit_breaker_success():
    """Test successful fetch with circuit breaker."""
    provider = TestDataProvider()

    async def mock_fetch():
        return ProviderResponse(
            data={"result": "success"},
            timestamp=datetime.now(),
            source="test",
            confidence=1.0,
            is_cached=False,
        )

    response = await provider.fetch_with_circuit_breaker(mock_fetch)

    assert response.data == {"result": "success"}
    assert provider.circuit_breaker.get_state() == CircuitState.CLOSED
    assert provider.circuit_breaker.failure_count == 0


@pytest.mark.anyio
async def test_data_provider_fetch_with_circuit_breaker_failure():
    """Test fetch failure with circuit breaker."""
    provider = TestDataProvider()

    async def failing_fetch():
        raise ValueError("Fetch failed")

    with pytest.raises(ValueError, match="Fetch failed"):
        await provider.fetch_with_circuit_breaker(failing_fetch)

    # Circuit breaker should record failure
    assert provider.circuit_breaker.failure_count == 1


@pytest.mark.anyio
async def test_data_provider_circuit_breaker_opens():
    """Test circuit breaker opens after sustained failures."""
    provider = TestDataProvider()
    provider.circuit_breaker.failure_threshold = 3

    async def failing_fetch():
        raise ValueError("Fetch failed")

    # Fail 3 times to open circuit
    for _ in range(3):
        with pytest.raises(ValueError):
            await provider.fetch_with_circuit_breaker(failing_fetch)

    # Circuit should be open
    assert provider.circuit_breaker.get_state() == CircuitState.OPEN

    # Next attempt should be rejected immediately
    with pytest.raises(RuntimeError, match="Circuit breaker is OPEN"):
        await provider.fetch_with_circuit_breaker(failing_fetch)


def test_data_provider_get_health_status():
    """Test provider health status reporting."""
    provider = TestDataProvider()

    # Initial health
    health = provider.get_health_status()
    assert health["provider"] == "test_provider"
    assert health["circuit_state"] == "closed"
    assert health["failure_count"] == 0
    assert health["last_failure"] is None

    # After failure
    provider.circuit_breaker.record_failure()
    health = provider.get_health_status()
    assert health["failure_count"] == 1
    assert health["last_failure"] is not None


@pytest.mark.anyio
async def test_data_provider_retry_integration():
    """Test that provider uses retry logic correctly."""
    provider = TestDataProvider()
    provider.retry_config = RetryConfig(max_attempts=3)

    call_count = 0

    async def flaky_fetch():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Temporary failure")
        return ProviderResponse(
            data={"success": True},
            timestamp=datetime.now(),
            source="test",
            confidence=1.0,
            is_cached=False,
        )

    response = await provider.fetch_with_circuit_breaker(flaky_fetch)

    assert response.data == {"success": True}
    assert call_count == 3
    assert provider.circuit_breaker.get_state() == CircuitState.CLOSED


def test_provider_response_dataclass():
    """Test ProviderResponse dataclass structure."""
    response = ProviderResponse(
        data={"price": 50000.0},
        timestamp=datetime.now(),
        source="test_source",
        confidence=0.95,
        is_cached=True,
        cache_age_seconds=30.0,
    )

    assert response.data == {"price": 50000.0}
    assert response.source == "test_source"
    assert response.confidence == 0.95
    assert response.is_cached is True
    assert response.cache_age_seconds == 30.0


def test_retry_config_defaults():
    """Test RetryConfig default values."""
    config = RetryConfig()

    assert config.max_attempts == 3
    assert config.backoff_factor == 2.0
    assert config.initial_delay_seconds == 1.0
    assert config.max_delay_seconds == 10.0


def test_retry_config_custom_values():
    """Test RetryConfig with custom values."""
    config = RetryConfig(
        max_attempts=5, backoff_factor=3.0, initial_delay_seconds=0.5, max_delay_seconds=20.0
    )

    assert config.max_attempts == 5
    assert config.backoff_factor == 3.0
    assert config.initial_delay_seconds == 0.5
    assert config.max_delay_seconds == 20.0
