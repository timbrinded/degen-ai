"""Historical data manager for backtesting framework."""

import asyncio
import logging
import random
from datetime import datetime

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.hyperliquid_provider import (
    Candle,
    FundingRate,
    HyperliquidProvider,
    OrderBookData,
)

logger = logging.getLogger(__name__)


class HistoricalDataManager:
    """Manages historical data fetching and caching for backtesting.

    Fetches OHLCV candles, funding rates, and order book snapshots from
    Hyperliquid API with pagination support, retry logic, and caching.
    """

    # Cache TTL for historical data (7 days in seconds)
    CACHE_TTL_HISTORICAL = 7 * 24 * 60 * 60

    # Maximum candles per API call (Hyperliquid limit)
    MAX_CANDLES_PER_CHUNK = 1000

    # Maximum retry attempts for API calls
    MAX_RETRIES = 5

    # Exponential backoff base
    BACKOFF_BASE = 2.0

    def __init__(
        self,
        hyperliquid_provider: HyperliquidProvider,
        cache: SQLiteCacheLayer,
    ):
        """Initialize historical data manager.

        Args:
            hyperliquid_provider: Provider for Hyperliquid API access
            cache: SQLite cache layer for data persistence
        """
        self.provider = hyperliquid_provider
        self.cache = cache

    async def fetch_candles_range(
        self,
        coin: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Candle]:
        """Fetch OHLCV candles for date range with pagination support.

        Handles pagination if needed (max 1000 candles per chunk), caches results.
        Returns list of Candle objects sorted by timestamp.

        Args:
            coin: Trading pair symbol (e.g., "BTC", "ETH")
            interval: Candle interval (e.g., "1h", "4h", "1d")
            start_time: Start timestamp for data range
            end_time: End timestamp for data range

        Returns:
            List of Candle objects sorted by timestamp

        Raises:
            Exception: If fetch fails after all retries
        """
        # Generate cache key
        cache_key = (
            f"backtest:candles:{coin}:{interval}:{start_time.isoformat()}:{end_time.isoformat()}"
        )

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(
                f"Candles cache hit for {coin} {interval} "
                f"{start_time.date()} to {end_time.date()} (age: {cached.age_seconds:.1f}s)"
            )
            return cached.value

        # Fetch from API with retry logic
        logger.info(
            f"Fetching candles for {coin} {interval} from {start_time.date()} to {end_time.date()}"
        )

        all_candles = []
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        # Calculate chunk size based on interval
        interval_ms = self._interval_to_milliseconds(interval)
        chunk_duration_ms = interval_ms * self.MAX_CANDLES_PER_CHUNK

        current_start = start_ms
        while current_start < end_ms:
            current_end = min(current_start + chunk_duration_ms, end_ms)

            # Fetch chunk with retry
            chunk_candles = await self._fetch_candles_chunk_with_retry(
                coin, interval, current_start, current_end
            )

            all_candles.extend(chunk_candles)
            current_start = current_end

        # Sort by timestamp
        all_candles.sort(key=lambda c: c.timestamp)

        # Validate data quality
        self._validate_candles(all_candles, coin, interval)

        # Cache the result
        await self.cache.set(cache_key, all_candles, self.CACHE_TTL_HISTORICAL)

        logger.info(f"Fetched {len(all_candles)} candles for {coin} {interval}")
        return all_candles

    async def fetch_funding_rates_range(
        self,
        coin: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[FundingRate]:
        """Fetch funding rate history for date range.

        Returns list of FundingRate objects sorted by timestamp.

        Args:
            coin: Trading pair symbol (e.g., "BTC", "ETH")
            start_time: Start timestamp for data range
            end_time: End timestamp for data range

        Returns:
            List of FundingRate objects sorted by timestamp

        Raises:
            Exception: If fetch fails after all retries
        """
        # Generate cache key
        cache_key = f"backtest:funding:{coin}:{start_time.isoformat()}:{end_time.isoformat()}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(
                f"Funding rates cache hit for {coin} "
                f"{start_time.date()} to {end_time.date()} (age: {cached.age_seconds:.1f}s)"
            )
            return cached.value

        # Fetch from API with retry logic
        logger.info(
            f"Fetching funding rates for {coin} from {start_time.date()} to {end_time.date()}"
        )

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        funding_rates = await self._fetch_funding_with_retry(coin, start_ms, end_ms)

        # Sort by timestamp
        funding_rates.sort(key=lambda f: f.timestamp)

        # Cache the result
        await self.cache.set(cache_key, funding_rates, self.CACHE_TTL_HISTORICAL)

        logger.info(f"Fetched {len(funding_rates)} funding rates for {coin}")
        return funding_rates

    async def fetch_order_book_snapshot(
        self,
        coin: str,
        timestamp: datetime,
    ) -> OrderBookData | None:
        """Fetch order book snapshot closest to timestamp.

        Returns None if no data available within 5 minutes of timestamp.

        Args:
            coin: Trading pair symbol (e.g., "BTC", "ETH")
            timestamp: Target timestamp for snapshot

        Returns:
            OrderBookData or None if not available

        Raises:
            Exception: If fetch fails after all retries
        """
        # Generate cache key
        cache_key = f"backtest:orderbook:{coin}:{timestamp.isoformat()}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(
                f"Order book cache hit for {coin} at {timestamp} (age: {cached.age_seconds:.1f}s)"
            )
            return cached.value

        # For historical backtesting, we can't fetch historical order book snapshots
        # as Hyperliquid API only provides current order book
        # Return None and log warning
        logger.warning(
            f"Historical order book data not available for {coin} at {timestamp}. "
            "Order book metrics will be unavailable for this backtest."
        )

        result = None

        # Cache the None result to avoid repeated attempts
        await self.cache.set(cache_key, result, self.CACHE_TTL_HISTORICAL)

        return result

    async def _fetch_with_retry(self, fetch_func, operation_name: str):
        """Execute fetch with exponential backoff retry logic.

        Handles HTTP 429 rate limit errors and 5xx server errors with
        exponential backoff. Maximum 5 retry attempts.

        Args:
            fetch_func: Async callable to execute
            operation_name: Name for logging purposes

        Returns:
            Result from fetch_func

        Raises:
            Exception: If all retry attempts fail
        """
        last_exception = None

        for attempt in range(self.MAX_RETRIES):
            try:
                result = await fetch_func()
                if attempt > 0:
                    logger.info(f"{operation_name}: Succeeded on attempt {attempt + 1}")
                return result

            except Exception as e:
                last_exception = e
                error_str = str(e).lower()

                # Check if it's a rate limit or server error
                is_rate_limit = "429" in error_str or "rate limit" in error_str
                is_server_error = any(code in error_str for code in ["500", "502", "503", "504"])

                if not (is_rate_limit or is_server_error):
                    # Not a retryable error, raise immediately
                    logger.error(f"{operation_name}: Non-retryable error: {e}")
                    raise

                if attempt == self.MAX_RETRIES - 1:
                    logger.error(
                        f"{operation_name}: All {self.MAX_RETRIES} retry attempts failed: {e}"
                    )
                    raise

                # Calculate exponential backoff with jitter for rate limits
                if is_rate_limit:
                    delay = (self.BACKOFF_BASE**attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"{operation_name}: Rate limit (429) hit, "
                        f"attempt {attempt + 1}/{self.MAX_RETRIES}, "
                        f"waiting {delay:.1f}s before retry"
                    )
                else:
                    delay = self.BACKOFF_BASE**attempt
                    logger.warning(
                        f"{operation_name}: Server error (5xx), "
                        f"attempt {attempt + 1}/{self.MAX_RETRIES}, "
                        f"waiting {delay:.1f}s before retry"
                    )

                await asyncio.sleep(delay)

        # Should never reach here, but satisfy type checker
        if last_exception:
            raise last_exception
        raise RuntimeError(f"{operation_name}: Unexpected retry loop exit")

    async def _fetch_candles_chunk_with_retry(
        self,
        coin: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> list[Candle]:
        """Fetch candles chunk with retry logic.

        Args:
            coin: Trading pair symbol
            interval: Candle interval
            start_ms: Start timestamp in milliseconds
            end_ms: End timestamp in milliseconds

        Returns:
            List of Candle objects
        """

        async def _fetch():
            response = await self.provider.fetch_candles(coin, interval, start_ms, end_ms)
            return response.data

        return await self._fetch_with_retry(
            _fetch, f"fetch_candles({coin}, {interval}, {start_ms}, {end_ms})"
        )

    async def _fetch_funding_with_retry(
        self,
        coin: str,
        start_ms: int,
        end_ms: int,
    ) -> list[FundingRate]:
        """Fetch funding rates with retry logic.

        Args:
            coin: Trading pair symbol
            start_ms: Start timestamp in milliseconds
            end_ms: End timestamp in milliseconds

        Returns:
            List of FundingRate objects
        """

        async def _fetch():
            response = await self.provider.fetch_funding_history(coin, start_ms, end_ms)
            return response.data

        return await self._fetch_with_retry(
            _fetch, f"fetch_funding_history({coin}, {start_ms}, {end_ms})"
        )

    def _validate_candles(self, candles: list[Candle], coin: str, interval: str) -> None:
        """Validate candle data quality.

        Checks for gaps in data and zero prices. Logs warnings for issues
        but does not raise exceptions (graceful degradation).

        Args:
            candles: List of Candle objects to validate
            coin: Trading pair symbol for logging
            interval: Candle interval for logging
        """
        if not candles:
            logger.warning(f"No candle data returned for {coin} {interval}")
            return

        # Check for zero prices
        zero_price_candles = [c for c in candles if c.close <= 0 or c.open <= 0]
        if zero_price_candles:
            logger.warning(
                f"Found {len(zero_price_candles)} candles with zero prices for {coin} {interval}"
            )

        # Check for gaps in data
        if len(candles) < 2:
            return

        expected_interval_ms = self._interval_to_milliseconds(interval)
        gap_threshold = expected_interval_ms * 1.5  # Allow 50% tolerance

        gaps = []
        for i in range(1, len(candles)):
            actual_gap_ms = (
                candles[i].timestamp.timestamp() - candles[i - 1].timestamp.timestamp()
            ) * 1000

            if actual_gap_ms > gap_threshold:
                gaps.append(
                    (
                        candles[i - 1].timestamp,
                        candles[i].timestamp,
                        actual_gap_ms / 1000 / 60,  # Convert to minutes
                    )
                )

        if gaps:
            logger.warning(
                f"Found {len(gaps)} data gaps in {coin} {interval} candles. "
                f"First gap: {gaps[0][0]} to {gaps[0][1]} ({gaps[0][2]:.1f} minutes)"
            )
            if len(gaps) > 1:
                logger.warning(
                    f"Last gap: {gaps[-1][0]} to {gaps[-1][1]} ({gaps[-1][2]:.1f} minutes)"
                )

    def _interval_to_milliseconds(self, interval: str) -> int:
        """Convert interval string to milliseconds.

        Args:
            interval: Interval string (e.g., "1h", "4h", "1d")

        Returns:
            Interval in milliseconds

        Raises:
            ValueError: If interval format is invalid
        """
        interval_map = {
            "1m": 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
        }

        if interval not in interval_map:
            raise ValueError(
                f"Invalid interval: {interval}. "
                f"Supported intervals: {', '.join(interval_map.keys())}"
            )

        return interval_map[interval]
