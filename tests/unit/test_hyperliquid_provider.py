"""Unit tests for HyperliquidProvider."""

import contextlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.hyperliquid_provider import (
    HyperliquidProvider,
    OrderBookData,
)


@pytest.fixture
def cache():
    """Create temporary cache for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        yield SQLiteCacheLayer(db_path)


@pytest.fixture
def mock_info():
    """Create mock Hyperliquid Info API client."""
    return MagicMock()


@pytest.fixture
def provider(mock_info, cache):
    """Create HyperliquidProvider instance."""
    return HyperliquidProvider(mock_info, cache)


@pytest.mark.anyio
async def test_fetch_order_book_success(provider, mock_info):
    """Test successful order book fetch."""
    # Mock API response - matches real Hyperliquid API structure
    mock_info.l2_snapshot.return_value = {
        "levels": [
            [
                {"px": "50000.0", "sz": "1.5", "n": 1},
                {"px": "49999.0", "sz": "2.0", "n": 1},
            ],  # bids
            [
                {"px": "50001.0", "sz": "1.0", "n": 1},
                {"px": "50002.0", "sz": "1.5", "n": 1},
            ],  # asks
        ]
    }

    # Fetch order book
    response = await provider.fetch_order_book("BTC")

    # Verify response
    assert response.data.coin == "BTC"
    assert len(response.data.bids) == 2
    assert len(response.data.asks) == 2
    assert response.data.bids[0] == (50000.0, 1.5)
    assert response.data.asks[0] == (50001.0, 1.0)
    assert response.confidence == 1.0
    assert not response.is_cached


@pytest.mark.anyio
async def test_fetch_order_book_cached(provider, mock_info, cache):
    """Test order book fetch from cache."""
    from datetime import datetime

    # Pre-populate cache
    cached_data = OrderBookData(
        coin="BTC",
        bids=[(50000.0, 1.0)],
        asks=[(50001.0, 1.0)],
        timestamp=datetime.now(),
    )
    await cache.set("orderbook:BTC", cached_data, 60)

    # Fetch should return cached data
    response = await provider.fetch_order_book("BTC")

    assert response.data.coin == "BTC"
    assert response.is_cached
    assert response.cache_age_seconds is not None
    assert response.cache_age_seconds >= 0


@pytest.mark.anyio
async def test_fetch_funding_history_success(provider, mock_info):
    """Test successful funding history fetch."""
    # Mock API response
    mock_info.funding_history.return_value = [
        {"fundingRate": "0.0001", "time": 1700000000000},
        {"fundingRate": "0.0002", "time": 1700000001000},
    ]

    # Fetch funding history
    response = await provider.fetch_funding_history("BTC", 1700000000000, 1700000002000)

    # Verify response
    assert len(response.data) == 2
    assert response.data[0].coin == "BTC"
    assert response.data[0].rate == 0.0001
    assert response.confidence == 1.0
    assert not response.is_cached


@pytest.mark.anyio
async def test_fetch_candles_success(provider, mock_info):
    """Test successful candles fetch."""
    # Mock API response
    mock_info.candles_snapshot.return_value = [
        {"t": 1700000000000, "o": "50000", "h": "50100", "l": "49900", "c": "50050", "v": "100"},
        {"t": 1700000060000, "o": "50050", "h": "50150", "l": "49950", "c": "50100", "v": "120"},
    ]

    # Fetch candles
    response = await provider.fetch_candles("BTC", "1m", 1700000000000, 1700000120000)

    # Verify response
    assert len(response.data) == 2
    assert response.data[0].coin == "BTC"
    assert response.data[0].open == 50000.0
    assert response.data[0].close == 50050.0
    assert response.confidence == 1.0
    assert not response.is_cached


@pytest.mark.anyio
async def test_fetch_open_interest_success(provider, mock_info):
    """Test successful open interest fetch."""
    # Mock API response
    mock_info.meta.return_value = {
        "universe": [
            {"name": "BTC", "openInterest": "1000000"},
            {"name": "ETH", "openInterest": "500000"},
        ]
    }

    # Fetch open interest
    response = await provider.fetch_open_interest("BTC")

    # Verify response
    assert response.data.coin == "BTC"
    assert response.data.open_interest == 1000000.0
    assert response.confidence == 1.0
    assert not response.is_cached


@pytest.mark.anyio
async def test_fetch_with_retry_on_failure(provider, mock_info):
    """Test retry logic on API failure."""
    # Mock API to fail twice then succeed
    call_count = 0

    def mock_l2_snapshot(coin):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("API error")
        return {
            "levels": [
                [{"px": "50000.0", "sz": "1.0", "n": 1}],
                [{"px": "50001.0", "sz": "1.0", "n": 1}],
            ]
        }

    mock_info.l2_snapshot = mock_l2_snapshot

    # Should succeed after retries
    response = await provider.fetch_order_book("BTC")
    assert response.data.coin == "BTC"
    assert call_count == 3  # Failed twice, succeeded on third


@pytest.mark.anyio
async def test_circuit_breaker_opens_on_failures(provider, mock_info):
    """Test circuit breaker opens after sustained failures."""
    # Mock API to always fail
    mock_info.l2_snapshot.side_effect = Exception("API error")

    # Attempt multiple fetches to trigger circuit breaker
    for _ in range(6):
        with contextlib.suppress(Exception):
            await provider.fetch_order_book("BTC")

    # Circuit breaker should be open
    assert provider.circuit_breaker.get_state().value == "open"


def test_confidence_calculation(provider):
    """Test confidence score calculation based on age."""
    # Fresh data should have confidence 1.0
    assert provider._calculate_confidence(0, 60) == 1.0

    # Data at TTL should have confidence 0.5
    assert provider._calculate_confidence(60, 60) == 0.5

    # Very old data should have low confidence
    assert provider._calculate_confidence(700, 60) < 0.5

    # Confidence should never go below 0
    assert provider._calculate_confidence(10000, 60) >= 0.0


def test_provider_name(provider):
    """Test provider name."""
    assert provider.get_provider_name() == "hyperliquid"


def test_cache_ttl(provider):
    """Test cache TTL."""
    assert provider.get_cache_ttl() == 60
