"""Async Hyperliquid data provider with retry logic and caching."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from hyperliquid.info import Info

from hyperliquid_agent.market_registry import MarketRegistry
from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.providers import DataProvider, ProviderResponse

logger = logging.getLogger(__name__)


@dataclass
class OrderBookData:
    """Order book snapshot data.

    Attributes:
        coin: Trading pair symbol
        bids: List of (price, size) tuples for bid side
        asks: List of (price, size) tuples for ask side
        timestamp: When the snapshot was taken
    """

    coin: str
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    timestamp: datetime


@dataclass
class FundingRate:
    """Funding rate data point.

    Attributes:
        coin: Trading pair symbol
        rate: Funding rate as decimal (e.g., 0.0001 = 0.01%)
        timestamp: When the funding rate was recorded
    """

    coin: str
    rate: float
    timestamp: datetime


@dataclass
class Candle:
    """OHLCV candle data.

    Attributes:
        coin: Trading pair symbol
        timestamp: Candle start time
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Trading volume
    """

    coin: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OpenInterestData:
    """Open interest data.

    Attributes:
        coin: Trading pair symbol
        open_interest: Current open interest value
        timestamp: When the data was recorded
    """

    coin: str
    open_interest: float
    timestamp: datetime


class HyperliquidProvider(DataProvider):
    """Provider for Hyperliquid Info API data with async support.

    This provider fetches real-time market data from Hyperliquid including:
    - L2 order book snapshots
    - Funding rate history
    - OHLCV candle data
    - Open interest metrics

    All methods include retry logic, circuit breaker protection, and caching.
    """

    # Cache TTLs for different data types (in seconds)
    CACHE_TTL_ORDER_BOOK = 5  # Order books change rapidly
    CACHE_TTL_FUNDING = 300  # Funding rates update every 8 hours
    CACHE_TTL_CANDLES = 60  # Candles are relatively stable
    CACHE_TTL_OPEN_INTEREST = 30  # OI updates frequently

    def __init__(self, info: Info, cache: SQLiteCacheLayer, registry: MarketRegistry | None = None):
        """Initialize Hyperliquid provider.

        Args:
            info: Hyperliquid Info API client
            cache: SQLite cache layer for data persistence
            registry: Optional market registry for symbol validation
        """
        super().__init__()
        self.info = info
        self.cache = cache
        self.registry = registry

    def get_provider_name(self) -> str:
        """Return provider identifier.

        Returns:
            Provider name string
        """
        return "hyperliquid"

    def get_cache_ttl(self) -> int:
        """Return default cache TTL in seconds.

        Returns:
            Default cache TTL (60 seconds)
        """
        return 60

    def _validate_symbol(self, coin: str) -> None:
        """Validate that a symbol exists in the registry.

        Args:
            coin: Symbol to validate

        Raises:
            ValueError: If symbol not found and registry is available
        """
        if self.registry and self.registry.is_ready:
            asset_info = self.registry.get_asset_info(coin)

            # Try resolving via registry alias mapping (handles symbols like "UETH")
            if not asset_info:
                resolved = self.registry.resolve_symbol(coin)
                if resolved:
                    asset_info = self.registry.get_asset_info(resolved[0])

            # Fallback: strip leading "U" if present (Hyperliquid spot prefix)
            if not asset_info and coin.upper().startswith("U") and len(coin) > 1:
                asset_info = self.registry.get_asset_info(coin[1:])

            if not asset_info:
                raise ValueError(f"Unknown symbol: {coin}. Not found in market registry.")

    async def fetch(self, **kwargs) -> ProviderResponse:
        """Generic fetch method (not used directly).

        Use specific fetch methods instead (fetch_order_book, etc.)

        Args:
            **kwargs: Provider-specific parameters

        Returns:
            ProviderResponse with data

        Raises:
            NotImplementedError: Use specific fetch methods
        """
        raise NotImplementedError("Use specific fetch methods (fetch_order_book, etc.)")

    async def fetch_order_book(self, coin: str) -> ProviderResponse[OrderBookData]:
        """Fetch L2 order book snapshot with caching.

        Args:
            coin: Trading pair symbol (e.g., "BTC", "ETH")

        Returns:
            ProviderResponse containing OrderBookData

        Raises:
            Exception: If fetch fails after all retries
        """
        # Validate symbol if registry available
        self._validate_symbol(coin)

        cache_key = f"orderbook:{coin}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Order book cache hit for {coin} (age: {cached.age_seconds:.1f}s)")
            return ProviderResponse(
                data=cached.value,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=self._calculate_confidence(
                    cached.age_seconds, self.CACHE_TTL_ORDER_BOOK
                ),
                is_cached=True,
                cache_age_seconds=cached.age_seconds,
            )

        # Fetch from API with circuit breaker and retry
        async def _fetch():
            l2_data = await asyncio.to_thread(self.info.l2_snapshot, coin)
            levels = l2_data.get("levels", [[], []])

            # Validate structure: levels should be [bids_list, asks_list]
            if not levels or len(levels) != 2:
                raise ValueError(
                    f"Invalid order book data for {coin}: expected 2 levels, got {len(levels) if levels else 0}"
                )

            bids_raw = levels[0]
            asks_raw = levels[1]

            if not bids_raw or not asks_raw:
                raise ValueError(f"Invalid order book data for {coin}: empty bids or asks")

            # Convert to typed tuples
            # API returns list of dicts like [{'px': '50000.0', 'sz': '1.5', 'n': 22}, ...]
            bids = [(float(b["px"]), float(b["sz"])) for b in bids_raw]
            asks = [(float(a["px"]), float(a["sz"])) for a in asks_raw]

            order_book = OrderBookData(
                coin=coin,
                bids=bids,
                asks=asks,
                timestamp=datetime.now(),
            )

            # Cache the result
            await self.cache.set(cache_key, order_book, self.CACHE_TTL_ORDER_BOOK)

            return ProviderResponse(
                data=order_book,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=1.0,
                is_cached=False,
                cache_age_seconds=None,
            )

        return await self.fetch_with_circuit_breaker(_fetch)

    async def fetch_funding_history(
        self,
        coin: str,
        start_time: int,
        end_time: int,
    ) -> ProviderResponse[list[FundingRate]]:
        """Fetch funding rate history with time range support.

        Args:
            coin: Trading pair symbol (e.g., "BTC", "ETH")
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds

        Returns:
            ProviderResponse containing list of FundingRate objects

        Raises:
            Exception: If fetch fails after all retries
        """
        cache_key = f"funding:{coin}:{start_time}:{end_time}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Funding history cache hit for {coin} (age: {cached.age_seconds:.1f}s)")
            return ProviderResponse(
                data=cached.value,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=self._calculate_confidence(cached.age_seconds, self.CACHE_TTL_FUNDING),
                is_cached=True,
                cache_age_seconds=cached.age_seconds,
            )

        # Fetch from API with circuit breaker and retry
        async def _fetch():
            funding_history_raw = await asyncio.to_thread(
                self.info.funding_history, coin, start_time, end_time
            )

            if not funding_history_raw:
                logger.warning(f"No funding history data for {coin}")
                funding_history_raw = []

            # Convert to typed objects
            funding_rates = [
                FundingRate(
                    coin=coin,
                    rate=float(f.get("fundingRate", 0)),
                    timestamp=datetime.fromtimestamp(f.get("time", 0) / 1000),
                )
                for f in funding_history_raw
            ]

            # Cache the result
            await self.cache.set(cache_key, funding_rates, self.CACHE_TTL_FUNDING)

            return ProviderResponse(
                data=funding_rates,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=1.0,
                is_cached=False,
                cache_age_seconds=None,
            )

        return await self.fetch_with_circuit_breaker(_fetch)

    async def fetch_candles(
        self,
        coin: str,
        interval: str,
        start_time: int,
        end_time: int,
    ) -> ProviderResponse[list[Candle]]:
        """Fetch OHLCV candle data with configurable intervals.

        Args:
            coin: Trading pair symbol (e.g., "BTC", "ETH")
            interval: Candle interval (e.g., "1m", "5m", "1h", "1d")
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds

        Returns:
            ProviderResponse containing list of Candle objects

        Raises:
            Exception: If fetch fails after all retries
        """
        cache_key = f"candles:{coin}:{interval}:{start_time}:{end_time}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(
                f"Candles cache hit for {coin} {interval} (age: {cached.age_seconds:.1f}s)"
            )
            return ProviderResponse(
                data=cached.value,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=self._calculate_confidence(cached.age_seconds, self.CACHE_TTL_CANDLES),
                is_cached=True,
                cache_age_seconds=cached.age_seconds,
            )

        # Fetch from API with circuit breaker and retry
        async def _fetch():
            candles_raw = await asyncio.to_thread(
                self.info.candles_snapshot, coin, interval, start_time, end_time
            )

            if not candles_raw:
                logger.warning(f"No candle data for {coin} {interval}")
                candles_raw = []

            # Convert to typed objects
            candles = [
                Candle(
                    coin=coin,
                    timestamp=datetime.fromtimestamp(c.get("t", 0) / 1000),
                    open=float(c.get("o", 0)),
                    high=float(c.get("h", 0)),
                    low=float(c.get("l", 0)),
                    close=float(c.get("c", 0)),
                    volume=float(c.get("v", 0)),
                )
                for c in candles_raw
            ]

            # Cache the result
            await self.cache.set(cache_key, candles, self.CACHE_TTL_CANDLES)

            return ProviderResponse(
                data=candles,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=1.0,
                is_cached=False,
                cache_age_seconds=None,
            )

        return await self.fetch_with_circuit_breaker(_fetch)

    async def fetch_open_interest(self, coin: str) -> ProviderResponse[OpenInterestData]:
        """Fetch current open interest data.

        Args:
            coin: Trading pair symbol (e.g., "BTC", "ETH")

        Returns:
            ProviderResponse containing OpenInterestData

        Raises:
            Exception: If fetch fails after all retries
        """
        # Validate symbol if registry available
        self._validate_symbol(coin)

        cache_key = f"open_interest:{coin}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Open interest cache hit for {coin} (age: {cached.age_seconds:.1f}s)")
            return ProviderResponse(
                data=cached.value,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=self._calculate_confidence(
                    cached.age_seconds, self.CACHE_TTL_OPEN_INTEREST
                ),
                is_cached=True,
                cache_age_seconds=cached.age_seconds,
            )

        # Fetch from API with circuit breaker and retry
        async def _fetch():
            # Get meta info which includes open interest
            meta = await asyncio.to_thread(self.info.meta)
            universe = meta.get("universe", [])

            # Find the coin in the universe
            coin_info = None
            for asset in universe:
                if asset.get("name") == coin:
                    coin_info = asset
                    break

            if not coin_info:
                raise ValueError(f"Coin {coin} not found in universe")

            # Extract open interest (in USD)
            oi_raw = coin_info.get("openInterest")
            if oi_raw is None:
                oi_value = 0.0
            elif isinstance(oi_raw, (int, float)):
                oi_value = float(oi_raw)
            else:
                oi_value = float(str(oi_raw))

            open_interest = OpenInterestData(
                coin=coin,
                open_interest=oi_value,
                timestamp=datetime.now(),
            )

            # Cache the result
            await self.cache.set(cache_key, open_interest, self.CACHE_TTL_OPEN_INTEREST)

            return ProviderResponse(
                data=open_interest,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=1.0,
                is_cached=False,
                cache_age_seconds=None,
            )

        return await self.fetch_with_circuit_breaker(_fetch)

    async def fetch_mid_price(self, coin: str) -> ProviderResponse[float]:
        """Fetch current mid-price for a coin using order book.

        This lightweight method fetches just the mid-price (average of best bid/ask)
        for use in the price_map watchlist. Uses aggressive caching since prices
        are fetched frequently.

        Args:
            coin: Trading pair symbol (e.g., "BTC", "ETH")

        Returns:
            ProviderResponse containing mid-price as float

        Raises:
            Exception: If fetch fails after all retries
        """
        cache_key = f"midprice:{coin}"

        # Check cache first (30 second TTL for watchlist prices)
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Mid-price cache hit for {coin} (age: {cached.age_seconds:.1f}s)")
            return ProviderResponse(
                data=cached.value,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=self._calculate_confidence(cached.age_seconds, 30),
                is_cached=True,
                cache_age_seconds=cached.age_seconds,
            )

        # Fetch order book and extract mid-price
        async def _fetch():
            l2_data = await asyncio.to_thread(self.info.l2_snapshot, coin)
            levels = l2_data.get("levels", [[], []])

            if not levels or len(levels) != 2:
                raise ValueError(f"Invalid order book data for {coin}")

            bids_raw = levels[0]
            asks_raw = levels[1]

            if not bids_raw or not asks_raw:
                raise ValueError(f"Invalid order book data for {coin}: empty bids or asks")

            # Calculate mid-price from best bid/ask
            best_bid = float(bids_raw[0]["px"])
            best_ask = float(asks_raw[0]["px"])
            mid_price = (best_bid + best_ask) / 2.0

            # Cache the result (30s TTL)
            await self.cache.set(cache_key, mid_price, 30)

            return ProviderResponse(
                data=mid_price,
                timestamp=datetime.now(),
                source=self.get_provider_name(),
                confidence=1.0,
                is_cached=False,
                cache_age_seconds=None,
            )

        return await self.fetch_with_circuit_breaker(_fetch)

    def _calculate_confidence(self, age_seconds: float, ttl_seconds: int) -> float:
        """Calculate confidence score based on data age.

        Confidence decreases linearly as data ages, reaching 0.5 at TTL
        and continuing to decrease for stale data.

        Args:
            age_seconds: Age of cached data in seconds
            ttl_seconds: TTL for this data type

        Returns:
            Confidence score from 0.0 to 1.0
        """
        if age_seconds <= 0:
            return 1.0

        # Linear decay: 1.0 at age=0, 0.5 at age=TTL
        confidence = 1.0 - (0.5 * age_seconds / ttl_seconds)

        # Set confidence below 0.5 for data older than 10 minutes (600 seconds)
        if age_seconds > 600:
            confidence = min(confidence, 0.4)

        return max(0.0, min(1.0, confidence))
