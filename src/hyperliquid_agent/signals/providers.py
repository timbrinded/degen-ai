"""Base provider infrastructure for async data collection with retry and circuit breaker."""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class ProviderResponse(Generic[T]):
    """Standardized response from data providers with quality metadata.

    Attributes:
        data: The actual data payload
        timestamp: When the data was collected
        source: Provider identifier
        confidence: Data quality score (0.0 to 1.0)
        is_cached: Whether data came from cache
        cache_age_seconds: Age of cached data, None if fresh
    """

    data: T
    timestamp: datetime
    source: str
    confidence: float  # 0.0 to 1.0
    is_cached: bool
    cache_age_seconds: float | None = None


@dataclass
class RetryConfig:
    """Configuration for exponential backoff retry logic.

    Attributes:
        max_attempts: Maximum number of retry attempts
        backoff_factor: Exponential backoff multiplier
        initial_delay_seconds: Initial delay before first retry
        max_delay_seconds: Maximum delay between retries
    """

    max_attempts: int = 3
    backoff_factor: float = 2.0
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 10.0


class CircuitBreaker:
    """Circuit breaker for handling sustained provider failures.

    Implements the circuit breaker pattern to prevent cascading failures
    when a provider is consistently failing. States:
    - CLOSED: Normal operation, all requests allowed
    - OPEN: Provider failing, reject requests immediately
    - HALF_OPEN: Testing recovery, allow limited requests

    Attributes:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout_seconds: Time to wait before testing recovery
        failure_count: Current count of consecutive failures
        state: Current circuit state
        last_failure_time: Timestamp of last failure
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 60,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout_seconds: Seconds to wait before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time: datetime | None = None

    def record_success(self) -> None:
        """Record successful call, reset failure count and close circuit."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        logger.debug("Circuit breaker: Success recorded, circuit closed")

    def record_failure(self) -> None:
        """Record failed call, increment failure count and potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker: Opened after {self.failure_count} failures")
        else:
            logger.debug(f"Circuit breaker: Failure {self.failure_count}/{self.failure_threshold}")

    def can_attempt(self) -> bool:
        """Check if call should be attempted based on circuit state.

        Returns:
            True if call should be attempted, False if circuit is open
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker: Entering half-open state for testing")
                    return True
            return False

        # HALF_OPEN state - allow one attempt to test recovery
        return True

    def get_state(self) -> CircuitState:
        """Get current circuit state.

        Returns:
            Current CircuitState
        """
        return self.state


async def fetch_with_retry(
    fetch_func: Callable[[], Any],
    retry_config: RetryConfig,
    operation_name: str = "fetch",
) -> Any:
    """Execute async fetch with exponential backoff retry.

    Args:
        fetch_func: Async callable to execute
        retry_config: Retry configuration
        operation_name: Name for logging purposes

    Returns:
        Result from fetch_func

    Raises:
        Exception: If all retry attempts fail, raises last exception
    """
    last_exception = None

    for attempt in range(retry_config.max_attempts):
        try:
            result = await fetch_func()
            if attempt > 0:
                logger.info(f"{operation_name}: Succeeded on attempt {attempt + 1}")
            return result

        except Exception as e:
            last_exception = e

            if attempt == retry_config.max_attempts - 1:
                logger.error(
                    f"{operation_name}: All {retry_config.max_attempts} retry attempts failed: {e}"
                )
                raise

            delay = min(
                retry_config.initial_delay_seconds * (retry_config.backoff_factor**attempt),
                retry_config.max_delay_seconds,
            )

            logger.warning(
                f"{operation_name}: Attempt {attempt + 1}/{retry_config.max_attempts} failed, "
                f"retrying in {delay:.1f}s: {e}"
            )

            await asyncio.sleep(delay)

    # Should never reach here, but satisfy type checker
    if last_exception:
        raise last_exception
    raise RuntimeError(f"{operation_name}: Unexpected retry loop exit")


class DataProvider(ABC):
    """Abstract base class for all data providers.

    All data providers must implement this interface to ensure consistent
    behavior across different data sources. Providers should:
    - Use async/await for I/O operations
    - Return ProviderResponse with quality metadata
    - Handle errors gracefully with retry logic
    - Support caching with appropriate TTLs
    """

    def __init__(self):
        """Initialize provider with circuit breaker and retry config."""
        self.circuit_breaker = CircuitBreaker()
        self.retry_config = RetryConfig()

    @abstractmethod
    async def fetch(self, **kwargs) -> ProviderResponse:
        """Fetch data from the provider.

        Args:
            **kwargs: Provider-specific parameters

        Returns:
            ProviderResponse with data and quality metadata

        Raises:
            Exception: If fetch fails after all retries
        """
        pass

    @abstractmethod
    def get_cache_ttl(self) -> int:
        """Return cache TTL in seconds for this provider's data.

        Returns:
            Cache TTL in seconds
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider identifier for logging and metrics.

        Returns:
            Provider name string
        """
        pass

    async def fetch_with_circuit_breaker(self, fetch_func: Callable[[], Any]) -> ProviderResponse:
        """Execute fetch with circuit breaker protection.

        Args:
            fetch_func: Async callable that performs the actual fetch

        Returns:
            ProviderResponse from fetch_func

        Raises:
            RuntimeError: If circuit breaker is open
            Exception: If fetch fails after retries
        """
        if not self.circuit_breaker.can_attempt():
            raise RuntimeError(
                f"{self.get_provider_name()}: Circuit breaker is OPEN, rejecting request"
            )

        try:
            result = await fetch_with_retry(
                fetch_func,
                self.retry_config,
                operation_name=self.get_provider_name(),
            )
            self.circuit_breaker.record_success()
            return result

        except Exception:
            self.circuit_breaker.record_failure()
            raise

    def get_health_status(self) -> dict[str, Any]:
        """Get provider health status for monitoring.

        Returns:
            Dictionary with health metrics
        """
        return {
            "provider": self.get_provider_name(),
            "circuit_state": self.circuit_breaker.get_state().value,
            "failure_count": self.circuit_breaker.failure_count,
            "last_failure": self.circuit_breaker.last_failure_time.isoformat()
            if self.circuit_breaker.last_failure_time
            else None,
        }
