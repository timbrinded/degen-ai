"""On-chain data provider for token unlocks and whale flow tracking."""

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.models import UnlockEvent, WhaleFlowData
from hyperliquid_agent.signals.providers import DataProvider, ProviderResponse

logger = logging.getLogger(__name__)


class OnChainProvider(DataProvider):
    """Provider for on-chain metrics including token unlocks and whale flows.

    Integrates with external on-chain data APIs to fetch:
    - Upcoming token unlock schedules
    - Large wallet transaction data (whale flows)

    Uses 1-hour cache TTL for on-chain data as specified in requirements.
    """

    CACHE_TTL_SECONDS = 3600  # 1 hour as per requirement 12.2

    def __init__(
        self,
        cache: SQLiteCacheLayer,
        api_key: str | None = None,
        provider_name: str | None = None,
        api_base_url: str | None = None,
    ):
        """Initialize on-chain data provider.

        Args:
            cache: Cache layer for storing fetched data
            api_key: Optional API key for on-chain data services
            provider_name: Name of the provider (e.g., "token_unlocks", "nansen")
            api_base_url: Base URL for the API (provider-specific)
        """
        super().__init__()
        self.cache = cache
        self.api_key = api_key or os.environ.get("ONCHAIN_API_KEY")
        self.provider_name = provider_name or "onchain"
        self.timeout_seconds = 10.0

        # Set default API base URL based on provider
        if api_base_url:
            self.api_base_url: str | None = api_base_url
        elif self.provider_name == "messari":
            self.api_base_url = "https://api.messari.io/token-unlocks/v1"
        elif self.provider_name == "token_unlocks":
            # Legacy support for token.unlocks.app (now tokenomist.ai)
            self.api_base_url = "https://api.token.unlocks.app/api/v1"
        else:
            self.api_base_url = None

    def get_cache_ttl(self) -> int:
        """Return cache TTL in seconds.

        Returns:
            Cache TTL of 3600 seconds (1 hour)
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

        Use specific methods like fetch_token_unlocks() or fetch_whale_flows().

        Raises:
            NotImplementedError: Always, use specific fetch methods
        """
        raise NotImplementedError("Use fetch_token_unlocks() or fetch_whale_flows()")

    async def fetch_token_unlocks(
        self, assets: list[str], days_ahead: int = 7
    ) -> ProviderResponse[list[UnlockEvent]]:
        """Fetch upcoming token unlock schedules.

        Retrieves token unlock events occurring within the specified time window.
        Implements requirements 6.1, 6.2, and 12.2.

        Args:
            assets: List of asset symbols to check for unlocks
            days_ahead: Number of days ahead to look for unlocks (default: 7)

        Returns:
            ProviderResponse containing list of UnlockEvent objects

        Raises:
            RuntimeError: If circuit breaker is open
            Exception: If fetch fails after all retries
        """
        cache_key = f"onchain:unlocks:{','.join(sorted(assets))}:{days_ahead}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for token unlocks: {cache_key}")
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
            return await self._fetch_token_unlocks_impl(assets, days_ahead)

        response = await self.fetch_with_circuit_breaker(_fetch)

        # Cache the result
        await self.cache.set(cache_key, response.data, self.CACHE_TTL_SECONDS)

        return response

    async def _fetch_token_unlocks_impl(
        self, assets: list[str], days_ahead: int
    ) -> ProviderResponse[list[UnlockEvent]]:
        """Implementation of token unlock fetching.

        Integrates with token unlock APIs to fetch upcoming unlock events.
        Supports providers like token.unlocks.app, Nansen, and Dune Analytics.

        Args:
            assets: List of asset symbols
            days_ahead: Days ahead to look for unlocks

        Returns:
            ProviderResponse with unlock events
        """
        # Calculate time window for filtering
        now = datetime.now()
        end_date = now + timedelta(days=days_ahead)

        unlocks: list[UnlockEvent] = []

        # Return empty results if no API key configured
        if not self.api_key:
            logger.debug("No API key configured for on-chain provider, returning empty unlocks")
            return ProviderResponse(
                data=unlocks,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=0.3,  # Low confidence without API key
                is_cached=False,
                cache_age_seconds=None,
            )

        # Return empty results if no API base URL configured
        if not self.api_base_url:
            logger.warning(
                f"No API base URL configured for provider '{self.provider_name}', "
                "returning empty unlocks"
            )
            return ProviderResponse(
                data=unlocks,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=0.3,
                is_cached=False,
                cache_age_seconds=None,
            )

        try:
            # Build API request based on provider
            if self.provider_name == "messari":
                unlocks = await self._fetch_from_messari_api(assets, days_ahead, end_date)
            elif self.provider_name == "token_unlocks":
                unlocks = await self._fetch_from_token_unlocks_api(assets, days_ahead, end_date)
            else:
                logger.warning(f"Unknown provider '{self.provider_name}', returning empty unlocks")
                return ProviderResponse(
                    data=[],
                    timestamp=datetime.now(),
                    source=self.provider_name,
                    confidence=0.3,
                    is_cached=False,
                    cache_age_seconds=None,
                )

            logger.info(
                f"Fetched {len(unlocks)} unlock events for {len(assets)} assets "
                f"within {days_ahead} days"
            )

            return ProviderResponse(
                data=unlocks,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=1.0,
                is_cached=False,
                cache_age_seconds=None,
            )

        except Exception as e:
            logger.error(f"Failed to fetch token unlocks: {e}", exc_info=True)
            # Return low confidence to indicate failure
            return ProviderResponse(
                data=[],
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=0.1,  # Very low confidence on error
                is_cached=False,
                cache_age_seconds=None,
            )

    async def _fetch_from_messari_api(
        self, assets: list[str], days_ahead: int, end_date: datetime
    ) -> list[UnlockEvent]:
        """Fetch unlock events from Messari Token Unlocks API.

        Args:
            assets: List of asset symbols
            days_ahead: Days ahead to look for unlocks
            end_date: End date for filtering unlocks

        Returns:
            List of UnlockEvent objects
        """
        unlocks: list[UnlockEvent] = []
        now = datetime.now()

        # Messari uses asset slugs, need to query each asset individually
        for asset in assets:
            try:
                # Build URL for asset events endpoint
                # Format: /assets/{assetId}/events
                url = f"{self.api_base_url}/assets/{asset.lower()}/events"

                # Build request with API key header
                headers: dict[str, str] = {
                    "x-messari-api-key": self.api_key or "",
                    "Content-Type": "application/json",
                }

                req = urllib.request.Request(url, headers=headers)

                # Make HTTP request
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    data = json.loads(response.read())

                    # Parse response
                    if "data" not in data or "unlockEvents" not in data["data"]:
                        continue

                    asset_info = data["data"].get("asset", {})
                    asset_symbol = asset_info.get("symbol", asset).upper()

                    # Process unlock events
                    for event in data["data"]["unlockEvents"]:
                        try:
                            # Parse timestamp
                            timestamp_str = event.get("timestamp")
                            if not timestamp_str:
                                continue

                            unlock_date = datetime.fromisoformat(
                                timestamp_str.replace("Z", "+00:00")
                            )

                            # Convert to naive datetime for comparison
                            unlock_date_naive = unlock_date.replace(tzinfo=None)

                            # Filter by date range (only future unlocks within window)
                            if unlock_date_naive <= now or unlock_date_naive > end_date:
                                continue

                            # Get cliff data (immediate unlock amount)
                            cliff = event.get("cliff")
                            if not cliff:
                                continue

                            amount = float(cliff.get("amountNative", 0))
                            percentage = float(cliff.get("percentOfTotalAllocation", 0)) * 100

                            if amount <= 0:
                                continue

                            # Create UnlockEvent (use naive datetime)
                            unlock_event = UnlockEvent(
                                asset=asset_symbol,
                                unlock_date=unlock_date_naive,
                                amount=amount,
                                percentage_of_supply=percentage,
                            )

                            unlocks.append(unlock_event)

                        except (ValueError, KeyError, TypeError) as e:
                            logger.debug(f"Failed to parse unlock event: {e}, event: {event}")
                            continue

            except Exception as e:
                logger.debug(f"Failed to fetch unlocks for {asset} from Messari: {e}")
                continue

        return unlocks

    async def _fetch_from_token_unlocks_api(
        self, assets: list[str], days_ahead: int, end_date: datetime
    ) -> list[UnlockEvent]:
        """Fetch unlock events from token.unlocks.app API (legacy).

        Args:
            assets: List of asset symbols
            days_ahead: Days ahead to look for unlocks
            end_date: End date for filtering unlocks

        Returns:
            List of UnlockEvent objects
        """
        unlocks: list[UnlockEvent] = []

        # Build query parameters
        params: dict[str, str | int] = {
            "days_ahead": days_ahead,
        }

        # Add assets filter if provided
        if assets:
            params["assets"] = ",".join(assets)

        # Build URL with query parameters
        url = f"{self.api_base_url}/unlocks"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        # Build request with authorization header
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(url, headers=headers)

        # Make HTTP request
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read())

            # Parse response based on expected format
            # Assuming response format: {"unlocks": [...]}
            unlock_list = data.get("unlocks", []) if isinstance(data, dict) else data

            for item in unlock_list:
                try:
                    # Parse unlock date
                    unlock_date_str = item.get("date") or item.get("unlock_date")
                    if not unlock_date_str:
                        continue

                    # Handle different date formats
                    try:
                        unlock_date = datetime.fromisoformat(unlock_date_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        # Try parsing as timestamp
                        unlock_date = datetime.fromtimestamp(float(unlock_date_str))

                    # Filter by date range
                    if unlock_date > end_date:
                        continue

                    # Extract token symbol
                    token = item.get("token") or item.get("asset") or item.get("symbol")
                    if not token:
                        continue

                    # Extract amount and percentage
                    amount = float(item.get("amount", 0))
                    percentage = float(
                        item.get("percentage_of_supply", 0)
                        or item.get("percentage", 0)
                        or item.get("pct_supply", 0)
                    )

                    # Create UnlockEvent
                    unlock_event = UnlockEvent(
                        asset=token.upper(),
                        unlock_date=unlock_date,
                        amount=amount,
                        percentage_of_supply=percentage,
                    )

                    unlocks.append(unlock_event)

                except (ValueError, KeyError, TypeError) as e:
                    logger.debug(f"Failed to parse unlock event: {e}, item: {item}")
                    continue

        return unlocks

    async def fetch_whale_flows(
        self, asset: str, hours_back: int = 24
    ) -> ProviderResponse[WhaleFlowData]:
        """Fetch large wallet transaction data for an asset.

        Retrieves whale flow data (large transactions) for the specified time period.
        Implements requirements 6.3, 6.4, 6.5, and 12.2.

        Args:
            asset: Asset symbol to check for whale flows
            hours_back: Number of hours to look back (default: 24)

        Returns:
            ProviderResponse containing WhaleFlowData

        Raises:
            RuntimeError: If circuit breaker is open
            Exception: If fetch fails after all retries
        """
        cache_key = f"onchain:whale_flows:{asset}:{hours_back}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for whale flows: {cache_key}")
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
            return await self._fetch_whale_flows_impl(asset, hours_back)

        response = await self.fetch_with_circuit_breaker(_fetch)

        # Cache the result
        await self.cache.set(cache_key, response.data, self.CACHE_TTL_SECONDS)

        return response

    async def _fetch_whale_flows_impl(
        self, asset: str, hours_back: int
    ) -> ProviderResponse[WhaleFlowData]:
        """Implementation of whale flow fetching.

        Integrates with whale tracking APIs to fetch large wallet movements.
        Supports providers like Whale Alert, Nansen, Glassnode, and Dune Analytics.

        Args:
            asset: Asset symbol
            hours_back: Hours to look back

        Returns:
            ProviderResponse with whale flow data
        """
        # Calculate time window for filtering
        now = datetime.now()
        start_time = now - timedelta(hours=hours_back)

        # Default whale flow data (no flows detected)
        whale_data = WhaleFlowData(
            asset=asset,
            inflow=0.0,
            outflow=0.0,
            net_flow=0.0,
            large_tx_count=0,
        )

        # Return default data if no API key configured
        if not self.api_key:
            logger.debug("No API key configured for on-chain provider, returning zero flows")
            return ProviderResponse(
                data=whale_data,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=0.3,  # Low confidence without API key
                is_cached=False,
                cache_age_seconds=None,
            )

        # Return default data if no API base URL configured
        if not self.api_base_url:
            logger.warning(
                f"No API base URL configured for provider '{self.provider_name}', "
                "returning zero flows"
            )
            return ProviderResponse(
                data=whale_data,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=0.3,
                is_cached=False,
                cache_age_seconds=None,
            )

        try:
            # Build API request based on provider
            if self.provider_name == "messari":
                # Messari doesn't provide whale flow data, return zero flows
                logger.debug("Messari provider doesn't support whale flows, returning zero flows")
                return ProviderResponse(
                    data=whale_data,
                    timestamp=datetime.now(),
                    source=self.provider_name,
                    confidence=0.3,
                    is_cached=False,
                    cache_age_seconds=None,
                )
            elif self.provider_name == "token_unlocks":
                # token.unlocks.app may also provide whale flow data
                whale_data = await self._fetch_whale_flows_from_token_unlocks_api(
                    asset, hours_back, start_time
                )
            else:
                logger.warning(f"Unknown provider '{self.provider_name}', returning zero flows")
                return ProviderResponse(
                    data=whale_data,
                    timestamp=datetime.now(),
                    source=self.provider_name,
                    confidence=0.3,
                    is_cached=False,
                    cache_age_seconds=None,
                )

            logger.info(
                f"Fetched whale flows for {asset}: "
                f"inflow={whale_data.inflow}, outflow={whale_data.outflow}, "
                f"net={whale_data.net_flow}, count={whale_data.large_tx_count}"
            )

            return ProviderResponse(
                data=whale_data,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=1.0,
                is_cached=False,
                cache_age_seconds=None,
            )

        except Exception as e:
            logger.error(f"Failed to fetch whale flows: {e}", exc_info=True)
            return ProviderResponse(
                data=whale_data,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=0.1,  # Very low confidence on error
                is_cached=False,
                cache_age_seconds=None,
            )

    async def _fetch_whale_flows_from_token_unlocks_api(
        self, asset: str, hours_back: int, start_time: datetime
    ) -> WhaleFlowData:
        """Fetch whale flow data from token.unlocks.app API.

        Args:
            asset: Asset symbol
            hours_back: Hours to look back
            start_time: Start time for filtering flows

        Returns:
            WhaleFlowData object
        """
        # Build query parameters
        params = {
            "asset": asset,
            "hours_back": hours_back,
        }

        # Build URL with query parameters
        url = f"{self.api_base_url}/whale-flows"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        # Build request with authorization header
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(url, headers=headers)

        # Make HTTP request
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read())

            # Parse response based on expected format
            # Assuming response format: {"inflow": ..., "outflow": ..., "transactions": [...]}
            inflow = float(data.get("inflow", 0))
            outflow = float(data.get("outflow", 0))
            net_flow = inflow - outflow
            large_tx_count = int(data.get("transaction_count", 0)) or len(
                data.get("transactions", [])
            )

            return WhaleFlowData(
                asset=asset.upper(),
                inflow=inflow,
                outflow=outflow,
                net_flow=net_flow,
                large_tx_count=large_tx_count,
            )
