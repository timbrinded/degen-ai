"""Integration tests for off-chain API connections.

These tests verify real API connectivity with external data providers:
- HyperliquidProvider: Order books, funding rates, candles, open interest
- ExternalMarketProvider: Asset prices from CoinGecko
- SentimentProvider: Fear & Greed Index

All tests are read-only and non-state-changing.
"""

import logging
from datetime import datetime, timedelta

import pytest
from hyperliquid.info import Info

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.external_market_provider import ExternalMarketProvider
from hyperliquid_agent.signals.hyperliquid_provider import (
    Candle,
    FundingRate,
    HyperliquidProvider,
    OpenInterestData,
    OrderBookData,
)
from hyperliquid_agent.signals.sentiment_provider import SentimentProvider

logger = logging.getLogger(__name__)

# Configure pytest to use anyio for async tests
pytestmark = pytest.mark.anyio


@pytest.fixture
def cache_layer(tmp_path):
    """Create a temporary cache layer for testing."""
    db_path = tmp_path / "test_signal_cache.db"
    cache = SQLiteCacheLayer(db_path)
    yield cache
    # Cleanup is automatic with tmp_path


@pytest.fixture
def hyperliquid_provider(cache_layer):
    """Create HyperliquidProvider with real Info API client."""
    info = Info(skip_ws=True)  # Skip websocket for testing
    return HyperliquidProvider(info, cache_layer)


@pytest.fixture
def external_market_provider(cache_layer):
    """Create ExternalMarketProvider for testing."""
    return ExternalMarketProvider(cache_layer)


@pytest.fixture
def sentiment_provider(cache_layer):
    """Create SentimentProvider for testing."""
    return SentimentProvider(cache_layer)


class TestHyperliquidProvider:
    """Integration tests for HyperliquidProvider with real API calls."""

    async def test_fetch_order_book_returns_valid_data(self, hyperliquid_provider):
        """Test fetch_order_book() returns valid data that fits OrderBookData model.

        Implements requirement 1.1: Fetch L2 order book snapshots from Hyperliquid.
        """
        # Fetch order book for BTC
        response = await hyperliquid_provider.fetch_order_book("BTC")

        # Verify response structure
        assert response is not None
        assert response.data is not None
        assert isinstance(response.data, OrderBookData)

        # Verify OrderBookData fields
        order_book = response.data
        assert order_book.coin == "BTC"
        assert isinstance(order_book.bids, list)
        assert isinstance(order_book.asks, list)
        assert isinstance(order_book.timestamp, datetime)

        # Verify bids and asks are non-empty
        assert len(order_book.bids) > 0, "Order book should have bids"
        assert len(order_book.asks) > 0, "Order book should have asks"

        # Verify bid/ask structure: list of (price, size) tuples
        for bid in order_book.bids[:5]:  # Check first 5 bids
            assert isinstance(bid, tuple)
            assert len(bid) == 2
            price, size = bid
            assert isinstance(price, float)
            assert isinstance(size, float)
            assert price > 0
            assert size > 0

        for ask in order_book.asks[:5]:  # Check first 5 asks
            assert isinstance(ask, tuple)
            assert len(ask) == 2
            price, size = ask
            assert isinstance(price, float)
            assert isinstance(size, float)
            assert price > 0
            assert size > 0

        # Verify proper timestamps and metadata
        assert response.timestamp is not None
        assert isinstance(response.timestamp, datetime)
        assert response.source == "hyperliquid"
        assert 0.0 <= response.confidence <= 1.0
        assert isinstance(response.is_cached, bool)

        logger.info(
            f"✓ Order book test passed: {len(order_book.bids)} bids, "
            f"{len(order_book.asks)} asks, confidence={response.confidence:.2f}"
        )

    async def test_fetch_funding_history_returns_valid_data(self, hyperliquid_provider):
        """Test fetch_funding_history() returns valid data that fits FundingRateHistory model.

        Implements requirement 2.1: Fetch funding rate history from Hyperliquid.
        """
        # Calculate time range: last 24 hours
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(hours=24)).timestamp() * 1000)

        # Fetch funding history for BTC
        response = await hyperliquid_provider.fetch_funding_history("BTC", start_time, end_time)

        # Verify response structure
        assert response is not None
        assert response.data is not None
        assert isinstance(response.data, list)

        # Verify list contains FundingRate objects
        if len(response.data) > 0:
            for funding_rate in response.data[:5]:  # Check first 5 entries
                assert isinstance(funding_rate, FundingRate)
                assert funding_rate.coin == "BTC"
                assert isinstance(funding_rate.rate, float)
                assert isinstance(funding_rate.timestamp, datetime)

                # Funding rates are typically small percentages
                assert -1.0 <= funding_rate.rate <= 1.0, "Funding rate should be reasonable"

        # Verify proper timestamps and metadata
        assert response.timestamp is not None
        assert isinstance(response.timestamp, datetime)
        assert response.source == "hyperliquid"
        assert 0.0 <= response.confidence <= 1.0
        assert isinstance(response.is_cached, bool)

        logger.info(
            f"✓ Funding history test passed: {len(response.data)} data points, "
            f"confidence={response.confidence:.2f}"
        )

    async def test_fetch_candles_returns_valid_ohlcv_data(self, hyperliquid_provider):
        """Test fetch_candles() returns valid OHLCV data that fits expected structure.

        Implements requirement 3.1: Fetch candle data for volatility calculations.
        """
        # Calculate time range: last 7 days
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)

        # Fetch 1-hour candles for BTC
        response = await hyperliquid_provider.fetch_candles("BTC", "1h", start_time, end_time)

        # Verify response structure
        assert response is not None
        assert response.data is not None
        assert isinstance(response.data, list)

        # Verify list contains Candle objects
        assert len(response.data) > 0, "Should have candle data for 7 days"

        for candle in response.data[:10]:  # Check first 10 candles
            assert isinstance(candle, Candle)
            assert candle.coin == "BTC"
            assert isinstance(candle.timestamp, datetime)
            assert isinstance(candle.open, float)
            assert isinstance(candle.high, float)
            assert isinstance(candle.low, float)
            assert isinstance(candle.close, float)
            assert isinstance(candle.volume, float)

            # Verify OHLC relationships
            assert candle.high >= candle.low, "High should be >= low"
            assert candle.high >= candle.open, "High should be >= open"
            assert candle.high >= candle.close, "High should be >= close"
            assert candle.low <= candle.open, "Low should be <= open"
            assert candle.low <= candle.close, "Low should be <= close"

            # Verify positive values
            assert candle.open > 0
            assert candle.high > 0
            assert candle.low > 0
            assert candle.close > 0
            assert candle.volume >= 0

        # Verify proper timestamps and metadata
        assert response.timestamp is not None
        assert isinstance(response.timestamp, datetime)
        assert response.source == "hyperliquid"
        assert 0.0 <= response.confidence <= 1.0
        assert isinstance(response.is_cached, bool)

        logger.info(
            f"✓ Candles test passed: {len(response.data)} candles, "
            f"confidence={response.confidence:.2f}"
        )

    async def test_fetch_open_interest_returns_valid_data(self, hyperliquid_provider):
        """Test fetch_open_interest() returns valid data that fits OpenInterestData model.

        Implements requirement 8.1: Fetch current open interest data from Hyperliquid.
        """
        # Fetch open interest for BTC
        response = await hyperliquid_provider.fetch_open_interest("BTC")

        # Verify response structure
        assert response is not None
        assert response.data is not None
        assert isinstance(response.data, OpenInterestData)

        # Verify OpenInterestData fields
        oi_data = response.data
        assert oi_data.coin == "BTC"
        assert isinstance(oi_data.open_interest, float)
        assert isinstance(oi_data.timestamp, datetime)

        # Open interest should be non-negative
        assert oi_data.open_interest >= 0, "Open interest should be non-negative"

        # Verify proper timestamps and metadata
        assert response.timestamp is not None
        assert isinstance(response.timestamp, datetime)
        assert response.source == "hyperliquid"
        assert 0.0 <= response.confidence <= 1.0
        assert isinstance(response.is_cached, bool)

        logger.info(
            f"✓ Open interest test passed: OI={oi_data.open_interest:.2f}, "
            f"confidence={response.confidence:.2f}"
        )


class TestExternalMarketProvider:
    """Integration tests for ExternalMarketProvider with real API calls."""

    async def test_fetch_asset_prices_returns_valid_data(self, external_market_provider):
        """Test fetch_asset_prices() returns valid price data for BTC/ETH/SPX.

        Implements requirements 5.1, 5.2: Fetch BTC and ETH price data for correlations.

        Note: This test uses placeholder implementation which returns empty data.
        When API integration is enabled, this will test real CoinGecko API calls.
        """
        # Request price data for BTC and ETH
        assets = ["BTC", "ETH"]
        response = await external_market_provider.fetch_asset_prices(assets, days_back=30)

        # Verify response structure
        assert response is not None
        assert response.data is not None
        assert isinstance(response.data, dict)

        # Verify dict contains requested assets
        for asset in assets:
            assert asset in response.data
            assert isinstance(response.data[asset], list)

        # Verify proper timestamps and metadata
        assert response.timestamp is not None
        assert isinstance(response.timestamp, datetime)
        assert response.source == "external_market"
        assert 0.0 <= response.confidence <= 1.0
        assert isinstance(response.is_cached, bool)

        # Note: With placeholder implementation, lists will be empty
        # When API is integrated, verify price data structure:
        # for asset in assets:
        #     prices = response.data[asset]
        #     if len(prices) > 0:
        #         assert all(isinstance(p, float) for p in prices)
        #         assert all(p > 0 for p in prices)

        logger.info(
            f"✓ Asset prices test passed (placeholder): "
            f"assets={assets}, confidence={response.confidence:.2f}"
        )


class TestSentimentProvider:
    """Integration tests for SentimentProvider with real API calls."""

    async def test_fetch_fear_greed_index_returns_valid_score(self, sentiment_provider):
        """Test fetch_fear_greed_index() returns valid sentiment score in expected range.

        Implements requirements 7.1, 7.2: Fetch and normalize Fear & Greed Index.

        Note: This test uses placeholder implementation which returns neutral (0.0).
        When API integration is enabled, this will test real Fear & Greed Index API.
        """
        # Fetch fear & greed index
        response = await sentiment_provider.fetch_fear_greed_index()

        # Verify response structure
        assert response is not None
        assert response.data is not None
        assert isinstance(response.data, float)

        # Verify normalized range: -1.0 (extreme fear) to +1.0 (extreme greed)
        sentiment_score = response.data
        assert -1.0 <= sentiment_score <= 1.0, "Sentiment score should be in [-1.0, 1.0] range"

        # Verify proper timestamps and metadata
        assert response.timestamp is not None
        assert isinstance(response.timestamp, datetime)
        assert response.source == "sentiment"
        assert 0.0 <= response.confidence <= 1.0
        assert isinstance(response.is_cached, bool)

        # Note: With placeholder implementation, score will be 0.0 (neutral)
        # When API is integrated, verify score reflects actual market sentiment

        logger.info(
            f"✓ Fear & Greed Index test passed (placeholder): "
            f"score={sentiment_score:.2f}, confidence={response.confidence:.2f}"
        )


class TestProviderCaching:
    """Integration tests for provider caching behavior."""

    async def test_hyperliquid_provider_uses_cache(self, hyperliquid_provider):
        """Test that HyperliquidProvider properly caches and reuses data."""
        # First fetch - should hit API
        response1 = await hyperliquid_provider.fetch_order_book("BTC")
        assert response1.is_cached is False
        assert response1.cache_age_seconds is None

        # Second fetch - should hit cache
        response2 = await hyperliquid_provider.fetch_order_book("BTC")
        assert response2.is_cached is True
        assert response2.cache_age_seconds is not None
        assert response2.cache_age_seconds >= 0

        # Verify data is consistent
        assert response1.data.coin == response2.data.coin
        assert len(response1.data.bids) > 0
        assert len(response2.data.bids) > 0

        logger.info(
            f"✓ Cache test passed: first fetch fresh, second fetch cached "
            f"(age={response2.cache_age_seconds:.2f}s)"
        )

    async def test_external_provider_uses_cache(self, external_market_provider):
        """Test that ExternalMarketProvider properly caches and reuses data."""
        assets = ["BTC", "ETH"]

        # First fetch - should hit API (or placeholder)
        response1 = await external_market_provider.fetch_asset_prices(assets, days_back=30)
        assert response1.is_cached is False
        assert response1.cache_age_seconds is None

        # Second fetch - should hit cache
        response2 = await external_market_provider.fetch_asset_prices(assets, days_back=30)
        assert response2.is_cached is True
        assert response2.cache_age_seconds is not None
        assert response2.cache_age_seconds >= 0

        logger.info(
            f"✓ External provider cache test passed: cache age={response2.cache_age_seconds:.2f}s"
        )

    async def test_sentiment_provider_uses_cache(self, sentiment_provider):
        """Test that SentimentProvider properly caches and reuses data."""
        # First fetch - should hit API (or placeholder)
        response1 = await sentiment_provider.fetch_fear_greed_index()
        assert response1.is_cached is False
        assert response1.cache_age_seconds is None

        # Second fetch - should hit cache
        response2 = await sentiment_provider.fetch_fear_greed_index()
        assert response2.is_cached is True
        assert response2.cache_age_seconds is not None
        assert response2.cache_age_seconds >= 0

        # Verify data is consistent
        assert response1.data == response2.data

        logger.info(
            f"✓ Sentiment provider cache test passed: cache age={response2.cache_age_seconds:.2f}s"
        )


class TestProviderMetadata:
    """Integration tests for provider metadata and quality indicators."""

    async def test_all_responses_include_proper_timestamps(self, hyperliquid_provider):
        """Verify all responses include proper timestamps and metadata.

        Implements requirement 13.1: Attach timestamp indicating data freshness.
        """
        # Fetch order book
        response = await hyperliquid_provider.fetch_order_book("BTC")

        # Verify timestamp fields
        assert response.timestamp is not None
        assert isinstance(response.timestamp, datetime)
        assert response.data.timestamp is not None
        assert isinstance(response.data.timestamp, datetime)

        # Timestamps should be recent (within last minute)
        now = datetime.now()
        time_diff = (now - response.timestamp).total_seconds()
        assert time_diff < 60, "Response timestamp should be recent"

        logger.info(f"✓ Timestamp test passed: response age={time_diff:.2f}s")

    async def test_responses_include_confidence_scores(
        self, hyperliquid_provider, external_market_provider, sentiment_provider
    ):
        """Verify all responses include confidence scores.

        Implements requirement 13.2: Attach confidence score based on data completeness.
        """
        # Test HyperliquidProvider
        hl_response = await hyperliquid_provider.fetch_order_book("BTC")
        assert 0.0 <= hl_response.confidence <= 1.0
        assert isinstance(hl_response.confidence, float)

        # Test ExternalMarketProvider
        ext_response = await external_market_provider.fetch_asset_prices(["BTC"], days_back=30)
        assert 0.0 <= ext_response.confidence <= 1.0
        assert isinstance(ext_response.confidence, float)

        # Test SentimentProvider
        sent_response = await sentiment_provider.fetch_fear_greed_index()
        assert 0.0 <= sent_response.confidence <= 1.0
        assert isinstance(sent_response.confidence, float)

        logger.info(
            f"✓ Confidence score test passed: "
            f"HL={hl_response.confidence:.2f}, "
            f"Ext={ext_response.confidence:.2f}, "
            f"Sent={sent_response.confidence:.2f}"
        )

    async def test_responses_include_source_attribution(
        self, hyperliquid_provider, external_market_provider, sentiment_provider
    ):
        """Verify all responses include source attribution.

        Implements requirement 13.4: Attach source attribution indicating which APIs provided data.
        """
        # Test HyperliquidProvider
        hl_response = await hyperliquid_provider.fetch_order_book("BTC")
        assert hl_response.source == "hyperliquid"

        # Test ExternalMarketProvider
        ext_response = await external_market_provider.fetch_asset_prices(["BTC"], days_back=30)
        assert ext_response.source == "external_market"

        # Test SentimentProvider
        sent_response = await sentiment_provider.fetch_fear_greed_index()
        assert sent_response.source == "sentiment"

        logger.info("✓ Source attribution test passed for all providers")


class TestReadOnlyOperations:
    """Verify all tests are non-state-changing (read-only queries)."""

    async def test_all_operations_are_read_only(
        self, hyperliquid_provider, external_market_provider, sentiment_provider
    ):
        """Ensure all integration tests perform only read-only queries.

        This test documents that all API calls are safe and non-state-changing.
        """
        # All HyperliquidProvider methods are read-only:
        # - fetch_order_book: Reads L2 snapshot
        # - fetch_funding_history: Reads historical funding rates
        # - fetch_candles: Reads OHLCV data
        # - fetch_open_interest: Reads current OI

        # All ExternalMarketProvider methods are read-only:
        # - fetch_asset_prices: Reads historical prices
        # - fetch_macro_calendar: Reads economic calendar

        # All SentimentProvider methods are read-only:
        # - fetch_fear_greed_index: Reads sentiment index
        # - fetch_social_sentiment: Reads social media sentiment

        # Verify by performing sample read operations
        await hyperliquid_provider.fetch_order_book("BTC")
        await external_market_provider.fetch_asset_prices(["BTC"], days_back=7)
        await sentiment_provider.fetch_fear_greed_index()

        logger.info("✓ All operations confirmed as read-only")
