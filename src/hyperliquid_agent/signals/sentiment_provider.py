"""Sentiment data provider for market sentiment tracking."""

import logging
import os
from datetime import datetime

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.providers import DataProvider, ProviderResponse

logger = logging.getLogger(__name__)


class SentimentProvider(DataProvider):
    """Provider for market sentiment data including fear & greed index.

    Integrates with external sentiment APIs to fetch:
    - Crypto Fear & Greed Index
    - Optional social media sentiment scores (Twitter/X)

    Uses 30-minute cache TTL for sentiment data as specified in requirements.
    """

    CACHE_TTL_SECONDS = 1800  # 30 minutes as per requirement 12.3

    def __init__(self, cache: SQLiteCacheLayer, api_key: str | None = None):
        """Initialize sentiment data provider.

        Args:
            cache: Cache layer for storing fetched data
            api_key: Optional API key for sentiment data services
        """
        super().__init__()
        self.cache = cache
        self.api_key = api_key or os.environ.get("SENTIMENT_API_KEY")

        # Provider configuration
        self.provider_name = "sentiment"
        self.timeout_seconds = 10.0

        # Fear & Greed Index API endpoint (free, no auth required)
        self.fear_greed_api_url = "https://api.alternative.me/fng/"

    def get_cache_ttl(self) -> int:
        """Return cache TTL in seconds.

        Returns:
            Cache TTL of 1800 seconds (30 minutes)
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

        Use specific methods like fetch_fear_greed_index() or fetch_social_sentiment().

        Raises:
            NotImplementedError: Always, use specific fetch methods
        """
        raise NotImplementedError("Use fetch_fear_greed_index() or fetch_social_sentiment()")

    async def fetch_fear_greed_index(self) -> ProviderResponse[float]:
        """Fetch Crypto Fear & Greed Index and normalize to -1.0 to +1.0 range.

        The Fear & Greed Index ranges from 0 (extreme fear) to 100 (extreme greed).
        This method normalizes it to -1.0 (extreme fear) to +1.0 (extreme greed).

        Implements requirements 7.1, 7.2, 12.3.

        Returns:
            ProviderResponse containing normalized sentiment score (-1.0 to +1.0)

        Raises:
            RuntimeError: If circuit breaker is open
            Exception: If fetch fails after all retries
        """
        cache_key = "sentiment:fear_greed_index"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for fear & greed index (age: {cached.age_seconds:.1f}s)")
            return ProviderResponse(
                data=cached.value,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=self._calculate_confidence(cached.age_seconds),
                is_cached=True,
                cache_age_seconds=cached.age_seconds,
            )

        # Fetch fresh data with circuit breaker protection
        async def _fetch():
            return await self._fetch_fear_greed_impl()

        response = await self.fetch_with_circuit_breaker(_fetch)

        # Cache the result
        await self.cache.set(cache_key, response.data, self.CACHE_TTL_SECONDS)

        return response

    async def _fetch_fear_greed_impl(self) -> ProviderResponse[float]:
        """Implementation of fear & greed index fetching.

        This is a placeholder implementation that returns neutral sentiment (0.0).
        In production, this would integrate with the Alternative.me Fear & Greed Index API.

        The API is free and doesn't require authentication:
        https://api.alternative.me/fng/

        Returns:
            ProviderResponse with normalized sentiment score
        """
        # Default to neutral sentiment as fallback (requirement 7.5)
        normalized_score = 0.0

        # TODO: Integrate with actual Fear & Greed Index API
        # For now, return neutral value as placeholder
        #
        # Example integration code (when ready to enable):
        # import urllib.request
        # import json
        #
        # try:
        #     url = f"{self.fear_greed_api_url}?limit=1"
        #     req = urllib.request.Request(url)
        #
        #     with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
        #         data = json.loads(response.read())
        #
        #         if data.get('data') and len(data['data']) > 0:
        #             # Extract the fear & greed value (0-100)
        #             raw_value = int(data['data'][0]['value'])
        #
        #             # Normalize to -1.0 to +1.0 range (requirement 7.2)
        #             # 0 (extreme fear) -> -1.0
        #             # 50 (neutral) -> 0.0
        #             # 100 (extreme greed) -> +1.0
        #             normalized_score = (raw_value - 50) / 50.0
        #
        #             # Clamp to valid range
        #             normalized_score = max(-1.0, min(1.0, normalized_score))
        #
        #             logger.info(
        #                 f"Fear & Greed Index: {raw_value}/100 "
        #                 f"(normalized: {normalized_score:.2f})"
        #             )
        #         else:
        #             logger.warning("No fear & greed data in API response")
        #
        # except Exception as e:
        #     logger.warning(f"Failed to fetch fear & greed index: {e}")
        #     # Fall through to return neutral value

        logger.debug(
            "Placeholder implementation - returning neutral sentiment (0.0). "
            "Enable API integration to fetch real Fear & Greed Index."
        )

        return ProviderResponse(
            data=normalized_score,
            timestamp=datetime.now(),
            source=self.provider_name,
            confidence=1.0,  # High confidence for neutral fallback
            is_cached=False,
            cache_age_seconds=None,
        )

    async def fetch_social_sentiment(self, asset: str) -> ProviderResponse[float]:
        """Fetch social media sentiment for a specific asset (optional feature).

        This method fetches Twitter/X sentiment scores for major crypto assets.
        Implements requirements 7.3, 7.4, 7.5.

        Args:
            asset: Asset symbol (e.g., 'BTC', 'ETH')

        Returns:
            ProviderResponse containing normalized sentiment score (-1.0 to +1.0)

        Raises:
            RuntimeError: If circuit breaker is open
            Exception: If fetch fails after all retries
        """
        cache_key = f"sentiment:social:{asset}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for social sentiment {asset} (age: {cached.age_seconds:.1f}s)")
            return ProviderResponse(
                data=cached.value,
                timestamp=datetime.now(),
                source=self.provider_name,
                confidence=self._calculate_confidence(cached.age_seconds),
                is_cached=True,
                cache_age_seconds=cached.age_seconds,
            )

        # Fetch fresh data with circuit breaker protection
        async def _fetch():
            return await self._fetch_social_sentiment_impl(asset)

        response = await self.fetch_with_circuit_breaker(_fetch)

        # Cache the result
        await self.cache.set(cache_key, response.data, self.CACHE_TTL_SECONDS)

        return response

    async def _fetch_social_sentiment_impl(self, asset: str) -> ProviderResponse[float]:
        """Implementation of social sentiment fetching.

        This is a placeholder implementation that returns neutral sentiment (0.0).
        In production, this would integrate with services like:
        - LunarCrush
        - Santiment
        - The TIE
        - CryptoMood

        Args:
            asset: Asset symbol

        Returns:
            ProviderResponse with normalized sentiment score
        """
        # Default to neutral sentiment as fallback (requirement 7.5)
        normalized_score = 0.0

        # TODO: Integrate with actual social sentiment API
        # For now, return neutral value as placeholder
        #
        # Example integration pattern (when API is available):
        # import urllib.request
        # import json
        #
        # if self.api_key:
        #     try:
        #         # Example: LunarCrush API
        #         url = f"https://api.lunarcrush.com/v2/assets/{asset}/sentiment"
        #         headers = {"Authorization": f"Bearer {self.api_key}"}
        #
        #         req = urllib.request.Request(url, headers=headers)
        #         with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
        #             data = json.loads(response.read())
        #
        #             # Extract sentiment score (API-specific format)
        #             raw_sentiment = data.get('sentiment', 50)  # Assume 0-100 scale
        #
        #             # Normalize to -1.0 to +1.0 range
        #             normalized_score = (raw_sentiment - 50) / 50.0
        #             normalized_score = max(-1.0, min(1.0, normalized_score))
        #
        #             logger.info(
        #                 f"Social sentiment for {asset}: {raw_sentiment}/100 "
        #                 f"(normalized: {normalized_score:.2f})"
        #             )
        #
        #     except Exception as e:
        #         logger.warning(f"Failed to fetch social sentiment for {asset}: {e}")
        #         # Fall through to return neutral value
        # else:
        #     logger.debug("No API key configured for social sentiment")

        if self.api_key:
            logger.debug(
                f"API key configured but placeholder implementation - "
                f"would fetch social sentiment for {asset}"
            )
        else:
            logger.debug(
                f"No API key configured for sentiment provider, "
                f"returning neutral sentiment for {asset}"
            )

        return ProviderResponse(
            data=normalized_score,
            timestamp=datetime.now(),
            source=self.provider_name,
            confidence=1.0 if not self.api_key else 0.5,  # Lower confidence without API key
            is_cached=False,
            cache_age_seconds=None,
        )

    async def fetch_combined_sentiment(
        self, asset: str | None = None, weights: dict[str, float] | None = None
    ) -> ProviderResponse[float]:
        """Fetch combined sentiment from multiple sources with weighted average.

        Combines fear & greed index with optional social sentiment.
        Implements requirements 7.4, 7.5.

        Args:
            asset: Optional asset symbol for social sentiment (e.g., 'BTC', 'ETH')
            weights: Optional weights for combining sources
                     Default: {'fear_greed': 0.6, 'social': 0.4}

        Returns:
            ProviderResponse containing weighted average sentiment score (-1.0 to +1.0)

        Raises:
            RuntimeError: If circuit breaker is open
            Exception: If fetch fails after all retries
        """
        # Default weights if not provided
        if weights is None:
            weights = {"fear_greed": 0.6, "social": 0.4}

        # Normalize weights to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        # Fetch fear & greed index
        fear_greed_response = await self.fetch_fear_greed_index()
        fear_greed_score = fear_greed_response.data

        # Initialize combined score with fear & greed
        combined_score = fear_greed_score * weights.get("fear_greed", 1.0)
        sources = [fear_greed_response.source]
        total_confidence = fear_greed_response.confidence * weights.get("fear_greed", 1.0)

        # Optionally fetch social sentiment if asset is provided
        if asset and weights.get("social", 0) > 0:
            try:
                social_response = await self.fetch_social_sentiment(asset)
                social_score = social_response.data

                # Add weighted social sentiment
                combined_score += social_score * weights.get("social", 0.0)
                sources.append(social_response.source)
                total_confidence += social_response.confidence * weights.get("social", 0.0)

            except Exception as e:
                logger.warning(f"Failed to fetch social sentiment for {asset}: {e}")
                # Continue with just fear & greed index
                # Renormalize weights to exclude social
                combined_score = fear_greed_score
                total_confidence = fear_greed_response.confidence

        # Clamp to valid range
        combined_score = max(-1.0, min(1.0, combined_score))

        logger.info(
            f"Combined sentiment: {combined_score:.2f} "
            f"(sources: {', '.join(sources)}, confidence: {total_confidence:.2f})"
        )

        return ProviderResponse(
            data=combined_score,
            timestamp=datetime.now(),
            source=self.provider_name,
            confidence=total_confidence,
            is_cached=False,
            cache_age_seconds=None,
        )

    def _calculate_confidence(self, age_seconds: float) -> float:
        """Calculate confidence score based on data age.

        Confidence decreases as data ages, with sentiment data being
        relatively stable over 30-minute windows.

        Args:
            age_seconds: Age of cached data in seconds

        Returns:
            Confidence score from 0.0 to 1.0
        """
        if age_seconds <= 0:
            return 1.0

        # Sentiment data is relatively stable, so confidence degrades slowly
        # Linear decay: 1.0 at age=0, 0.7 at age=TTL (30 min)
        confidence = 1.0 - (0.3 * age_seconds / self.CACHE_TTL_SECONDS)

        # Set confidence below 0.5 for data older than 10 minutes (600 seconds)
        # as per requirement 13.5
        if age_seconds > 600:
            confidence = min(confidence, 0.4)

        return max(0.0, min(1.0, confidence))
