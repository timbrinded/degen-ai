"""External market data provider for cross-asset prices and macro calendar."""

import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.models import MacroEvent
from hyperliquid_agent.signals.providers import DataProvider, ProviderResponse

logger = logging.getLogger(__name__)


class ExternalMarketProvider(DataProvider):
    """Provider for external market data including asset prices and macro events.

    Integrates with external APIs to fetch:
    - Historical prices for BTC, ETH, and SPX for correlation calculations
    - Macro economic calendar for upcoming high-impact events

    Uses 15-minute cache TTL for external market data as specified in requirements.
    """

    CACHE_TTL_SECONDS = 900  # 15 minutes as per requirement and design

    def __init__(
        self,
        cache: SQLiteCacheLayer,
        coingecko_api_key: str | None = None,
        use_yfinance: bool = True,
        jblanked_api_key: str | None = None,
    ):
        """Initialize external market data provider.

        Args:
            cache: Cache layer for storing fetched data
            coingecko_api_key: Optional API key for CoinGecko Pro API
            use_yfinance: Whether to use yfinance for SPX data
            jblanked_api_key: Optional API key for JBlanked macro calendar API
        """
        super().__init__()
        self.cache = cache
        self.coingecko_api_key = coingecko_api_key or os.environ.get("COINGECKO_API_KEY")
        self.use_yfinance = use_yfinance
        self.jblanked_api_key = jblanked_api_key or os.environ.get("JBLANKED_API_KEY")

        # Provider configuration
        self.provider_name = "external_market"
        self.timeout_seconds = 10.0

        # CoinGecko API endpoints
        self.coingecko_base_url = "https://api.coingecko.com/api/v3"
        if self.coingecko_api_key:
            # Use Pro API if key is available
            self.coingecko_base_url = "https://pro-api.coingecko.com/api/v3"

    def get_cache_ttl(self) -> int:
        """Return cache TTL in seconds.

        Returns:
            Cache TTL of 900 seconds (15 minutes)
        """
        return self.CACHE_TTL_SECONDS

    def get_provider_name(self) -> str:
        """Return provider identifier.

        Returns:
            Provider name string
        """
        return self.provider_name

    async def fetch(self, **kwargs) -> ProviderResponse:
        """Generic fetch method (not used directly).

        Use specific methods like fetch_asset_prices() or fetch_macro_calendar().

        Raises:
            NotImplementedError: Always, use specific fetch methods
        """
        raise NotImplementedError("Use fetch_asset_prices() or fetch_macro_calendar()")

    async def fetch_asset_prices(
        self, assets: list[str], days_back: int = 30
    ) -> ProviderResponse[dict[str, list[float]]]:
        """Fetch historical prices for BTC, ETH, and SPX for correlation calculations.

        Retrieves daily closing prices for the specified assets over the lookback period.
        Implements requirements 5.1, 5.2, 5.3, 5.4, 5.5.

        Args:
            assets: List of asset symbols (e.g., ['BTC', 'ETH', 'SPX'])
            days_back: Number of days of historical data to fetch (default: 30)

        Returns:
            ProviderResponse containing dict mapping asset -> list of daily prices

        Raises:
            RuntimeError: If circuit breaker is open
            Exception: If fetch fails after all retries
        """
        cache_key = f"external:prices:{','.join(sorted(assets))}:{days_back}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for asset prices: {cache_key}")
            return ProviderResponse(
                data=cached.value,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=0.9,  # Slightly lower confidence for cached data
                is_cached=True,
                cache_age_seconds=cached.age_seconds,
            )

        # Fetch fresh data with circuit breaker protection
        async def _fetch():
            return await self._fetch_asset_prices_impl(assets, days_back)

        response = await self.fetch_with_circuit_breaker(_fetch)

        # Cache the result
        await self.cache.set(cache_key, response.data, self.CACHE_TTL_SECONDS)

        return response

    async def _fetch_asset_prices_impl(
        self, assets: list[str], days_back: int
    ) -> ProviderResponse[dict[str, list[float]]]:
        """Implementation of asset price fetching.

        Integrates with CoinGecko API for BTC and ETH prices, and yfinance for SPX data.

        Args:
            assets: List of asset symbols
            days_back: Days of historical data to fetch

        Returns:
            ProviderResponse with price data
        """
        price_data: dict[str, list[float]] = {}
        successful_fetches = 0
        total_assets = len(assets)

        # Map asset symbols to CoinGecko IDs
        coingecko_ids = {"BTC": "bitcoin", "ETH": "ethereum"}

        for asset in assets:
            if asset in coingecko_ids:
                # Fetch from CoinGecko
                try:
                    coin_id = coingecko_ids[asset]
                    url = f"{self.coingecko_base_url}/coins/{coin_id}/market_chart"
                    params = f"?vs_currency=usd&days={days_back}&interval=daily"

                    headers = {}
                    if self.coingecko_api_key:
                        headers["x-cg-pro-api-key"] = self.coingecko_api_key

                    req = urllib.request.Request(url + params, headers=headers)

                    with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                        data = json.loads(response.read())
                        # Extract closing prices from response
                        prices = [point[1] for point in data.get("prices", [])]
                        price_data[asset] = prices
                        successful_fetches += 1
                        logger.debug(f"Fetched {len(prices)} prices for {asset} from CoinGecko")

                except Exception as e:
                    logger.warning(f"Failed to fetch {asset} prices from CoinGecko: {e}")
                    price_data[asset] = []

            elif asset == "SPX" and self.use_yfinance:
                # Fetch SPX data from Yahoo Finance using yfinance
                try:
                    import yfinance as yf

                    spx = yf.Ticker("^GSPC")
                    hist = spx.history(period=f"{days_back}d")
                    prices = hist["Close"].tolist()
                    price_data[asset] = prices
                    successful_fetches += 1
                    logger.debug(f"Fetched {len(prices)} prices for SPX from yfinance")

                except Exception as e:
                    logger.warning(f"Failed to fetch SPX data from yfinance: {e}")
                    price_data[asset] = []

            else:
                # Unknown asset or SPX without yfinance
                logger.debug(f"No data source configured for asset: {asset}")
                price_data[asset] = []

        # Calculate confidence based on successful fetches
        confidence = successful_fetches / total_assets if total_assets > 0 else 0.0

        # Adjust confidence for partial data
        if confidence < 1.0 and confidence > 0.0:
            confidence = 0.7  # Partial data gets 0.7 confidence

        return ProviderResponse(
            data=price_data,
            timestamp=datetime.now(),
            source=self.provider_name,
            confidence=confidence,
            is_cached=False,
            cache_age_seconds=None,
        )

    async def fetch_macro_calendar(self, days_ahead: int = 7) -> ProviderResponse[list[MacroEvent]]:
        """Fetch upcoming macro economic events.

        Retrieves high-impact economic events (FOMC, CPI, NFP, etc.) occurring
        within the specified time window. Implements requirements 9.1, 9.2, 9.3, 9.4, 9.5.

        Args:
            days_ahead: Number of days ahead to look for events (default: 7)

        Returns:
            ProviderResponse containing list of MacroEvent objects

        Raises:
            RuntimeError: If circuit breaker is open
            Exception: If fetch fails after all retries
        """
        cache_key = f"external:macro_calendar:{days_ahead}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for macro calendar: {cache_key}")
            return ProviderResponse(
                data=cached.value,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=0.9,  # Slightly lower confidence for cached data
                is_cached=True,
                cache_age_seconds=cached.age_seconds,
            )

        # Fetch fresh data with circuit breaker protection
        async def _fetch():
            return await self._fetch_macro_calendar_impl(days_ahead)

        response = await self.fetch_with_circuit_breaker(_fetch)

        # Cache the result
        await self.cache.set(cache_key, response.data, self.CACHE_TTL_SECONDS)

        return response

    async def _fetch_macro_calendar_impl(
        self, days_ahead: int
    ) -> ProviderResponse[list[MacroEvent]]:
        """Implementation of macro calendar fetching.

        Fetches economic calendar events from Forex Factory via JBlanked API.
        Falls back to local JSON file if API is unavailable.

        Args:
            days_ahead: Days ahead to look for events

        Returns:
            ProviderResponse with macro events
        """
        now = datetime.now()
        end_date = now + timedelta(days=days_ahead)

        events: list[MacroEvent] = []

        # Try to fetch from JBlanked API (aggregates Forex Factory data)
        if self.jblanked_api_key:
            try:
                # Fetch upcoming events from API
                url = "https://www.jblanked.com/news/api/mql5/calendar/upcoming/"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Api-Key {self.jblanked_api_key}",
                }

                req = urllib.request.Request(url, headers=headers)

                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    data = json.loads(response.read())

                    # Parse events from API response
                    for event_data in data:
                        try:
                            # Parse event datetime (format: "2024.02.08 15:30:00")
                            date_str = event_data.get("Date", "")
                            event_time = datetime.strptime(date_str, "%Y.%m.%d %H:%M:%S")

                            # Filter for events within time window
                            if now <= event_time <= end_date:
                                # Determine impact level based on currency and category
                                currency = event_data.get("Currency", "")
                                category = event_data.get("Category", "")

                                # High impact: USD events, CPI, NFP, FOMC, GDP
                                impact = "high"
                                if currency != "USD":
                                    impact = "medium"

                                high_impact_keywords = [
                                    "CPI",
                                    "NFP",
                                    "FOMC",
                                    "GDP",
                                    "Interest Rate",
                                ]
                                if not any(keyword in category for keyword in high_impact_keywords):
                                    impact = "medium"

                                events.append(
                                    MacroEvent(
                                        name=event_data.get("Name", "Unknown Event"),
                                        datetime=event_time,
                                        impact=impact,
                                        category=category,
                                    )
                                )
                        except (KeyError, ValueError) as e:
                            logger.debug(f"Failed to parse macro event from API: {e}")
                            continue

                    logger.info(
                        f"Fetched {len(events)} macro events from JBlanked API "
                        f"within {days_ahead} days"
                    )

            except Exception as e:
                logger.warning(f"Failed to fetch macro calendar from API: {e}")
                # Fall through to file-based fallback

        # Fallback to local JSON file if API unavailable or no API key
        if not events:
            calendar_file = os.path.join("data", "macro_calendar.json")

            try:
                if os.path.exists(calendar_file):
                    with open(calendar_file) as f:
                        data = json.load(f)

                    # Parse events from file
                    for event_data in data.get("events", []):
                        try:
                            # Parse event datetime
                            event_time = datetime.fromisoformat(event_data["date"])

                            # Filter for events within time window
                            if now <= event_time <= end_date:
                                events.append(
                                    MacroEvent(
                                        name=event_data["name"],
                                        datetime=event_time,
                                        impact=event_data.get("impact", "medium"),
                                        category=event_data.get("category", ""),
                                    )
                                )
                        except (KeyError, ValueError) as e:
                            logger.debug(f"Failed to parse macro event from file: {e}")
                            continue

                    logger.debug(
                        f"Loaded {len(events)} macro events from fallback file "
                        f"within {days_ahead} days"
                    )
                else:
                    logger.debug(
                        f"Macro calendar file not found at {calendar_file}, returning empty list"
                    )

            except Exception as e:
                logger.warning(f"Failed to load macro calendar from file: {e}")

        return ProviderResponse(
            data=events,
            timestamp=datetime.now(),
            source=self.provider_name,
            confidence=1.0 if events else 0.5,  # Lower confidence if no events found
            is_cached=False,
            cache_age_seconds=None,
        )
