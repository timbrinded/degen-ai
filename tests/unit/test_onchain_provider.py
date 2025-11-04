"""Unit tests for on-chain provider."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.onchain_provider import OnChainProvider


@pytest.fixture
def mock_cache():
    """Create a mock cache layer."""
    cache = AsyncMock(spec=SQLiteCacheLayer)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def onchain_provider(mock_cache):
    """Create an on-chain provider instance with token_unlocks provider."""
    return OnChainProvider(
        cache=mock_cache,
        api_key="test_api_key",
        provider_name="token_unlocks",
    )


@pytest.fixture
def messari_provider(mock_cache):
    """Create an on-chain provider instance with Messari provider."""
    return OnChainProvider(
        cache=mock_cache,
        api_key="test_messari_key",
        provider_name="messari",
    )


@pytest.fixture
def onchain_provider_no_key(mock_cache):
    """Create an on-chain provider instance without API key."""
    return OnChainProvider(
        cache=mock_cache,
        api_key=None,
        provider_name="token_unlocks",
    )


# ============================================================================
# Token Unlock Tests
# ============================================================================


@pytest.mark.anyio
async def test_fetch_token_unlocks_success(onchain_provider):
    """Test successful fetch of token unlock events."""
    now = datetime.now()
    unlock_date = now + timedelta(days=3)

    mock_response_data = {
        "unlocks": [
            {
                "token": "BTC",
                "date": unlock_date.isoformat(),
                "amount": 1000000,
                "percentage_of_supply": 2.5,
            },
            {
                "token": "ETH",
                "date": (now + timedelta(days=5)).isoformat(),
                "amount": 5000000,
                "percentage_of_supply": 1.2,
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await onchain_provider.fetch_token_unlocks(["BTC", "ETH"], days_ahead=7)

    assert len(response.data) == 2
    assert response.confidence == 1.0
    assert response.source == "token_unlocks"
    assert response.is_cached is False

    # Verify first unlock event
    unlock1 = response.data[0]
    assert unlock1.asset == "BTC"
    assert unlock1.amount == 1000000
    assert unlock1.percentage_of_supply == 2.5


@pytest.mark.anyio
async def test_fetch_token_unlocks_no_api_key(onchain_provider_no_key):
    """Test fetch without API key returns empty results with low confidence."""
    response = await onchain_provider_no_key.fetch_token_unlocks(["BTC"], days_ahead=7)

    assert response.data == []
    assert response.confidence == 0.3
    assert response.source == "token_unlocks"


@pytest.mark.anyio
async def test_fetch_token_unlocks_network_error(onchain_provider):
    """Test handling of network errors."""
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection timeout")):
        response = await onchain_provider.fetch_token_unlocks(["BTC"], days_ahead=7)

    assert response.data == []
    assert response.confidence == 0.1  # Very low confidence on error


@pytest.mark.anyio
async def test_fetch_token_unlocks_invalid_json(onchain_provider):
    """Test handling of invalid JSON response."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"invalid json {{"
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await onchain_provider.fetch_token_unlocks(["BTC"], days_ahead=7)

    assert response.data == []
    assert response.confidence == 0.1  # Very low confidence on error


@pytest.mark.anyio
async def test_fetch_token_unlocks_empty_response(onchain_provider):
    """Test handling of empty unlock list."""
    mock_response_data = {"unlocks": []}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await onchain_provider.fetch_token_unlocks(["BTC"], days_ahead=7)

    assert response.data == []
    assert response.confidence == 1.0  # Successful fetch, just no unlocks


@pytest.mark.anyio
async def test_fetch_token_unlocks_date_filtering(onchain_provider):
    """Test that unlocks outside date range are filtered."""
    now = datetime.now()

    mock_response_data = {
        "unlocks": [
            {
                "token": "BTC",
                "date": (now + timedelta(days=3)).isoformat(),
                "amount": 1000000,
                "percentage_of_supply": 2.5,
            },
            {
                "token": "ETH",
                "date": (now + timedelta(days=10)).isoformat(),  # Outside 7-day window
                "amount": 5000000,
                "percentage_of_supply": 1.2,
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await onchain_provider.fetch_token_unlocks(["BTC", "ETH"], days_ahead=7)

    # Only BTC unlock should be included (within 7 days)
    assert len(response.data) == 1
    assert response.data[0].asset == "BTC"


@pytest.mark.anyio
async def test_fetch_token_unlocks_alternative_field_names(onchain_provider):
    """Test parsing with alternative field names."""
    now = datetime.now()
    unlock_date = now + timedelta(days=3)

    mock_response_data = {
        "unlocks": [
            {
                "asset": "BTC",  # Alternative to "token"
                "unlock_date": unlock_date.isoformat(),  # Alternative to "date"
                "amount": 1000000,
                "pct_supply": 2.5,  # Alternative to "percentage_of_supply"
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await onchain_provider.fetch_token_unlocks(["BTC"], days_ahead=7)

    assert len(response.data) == 1
    assert response.data[0].asset == "BTC"
    assert response.data[0].percentage_of_supply == 2.5


@pytest.mark.anyio
async def test_fetch_token_unlocks_missing_required_fields(onchain_provider):
    """Test handling of unlock events with missing required fields."""
    now = datetime.now()

    mock_response_data = {
        "unlocks": [
            {
                "token": "BTC",
                "date": (now + timedelta(days=3)).isoformat(),
                "amount": 1000000,
                "percentage_of_supply": 2.5,
            },
            {
                # Missing token field - should be skipped
                "date": (now + timedelta(days=4)).isoformat(),
                "amount": 2000000,
            },
            {
                "token": "ETH",
                # Missing date field - should be skipped
                "amount": 3000000,
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await onchain_provider.fetch_token_unlocks(["BTC", "ETH"], days_ahead=7)

    # Only BTC unlock should be included (has all required fields)
    assert len(response.data) == 1
    assert response.data[0].asset == "BTC"


@pytest.mark.anyio
async def test_fetch_token_unlocks_cache_integration(onchain_provider, mock_cache):
    """Test that successful fetch is cached."""
    now = datetime.now()
    unlock_date = now + timedelta(days=3)

    mock_response_data = {
        "unlocks": [
            {
                "token": "BTC",
                "date": unlock_date.isoformat(),
                "amount": 1000000,
                "percentage_of_supply": 2.5,
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        await onchain_provider.fetch_token_unlocks(["BTC"], days_ahead=7)

    # Verify cache.set was called
    mock_cache.set.assert_called_once()
    call_args = mock_cache.set.call_args
    assert "onchain:unlocks:" in call_args[0][0]  # cache key
    assert call_args[0][2] == 3600  # TTL


# ============================================================================
# Messari Provider Tests
# ============================================================================


@pytest.mark.anyio
async def test_fetch_token_unlocks_messari_success(messari_provider):
    """Test successful fetch from Messari API."""
    now = datetime.now()
    unlock_date = now + timedelta(days=3)

    mock_response_data = {
        "data": {
            "asset": {"id": "test-id", "name": "Bitcoin", "slug": "bitcoin", "symbol": "BTC"},
            "unlockEvents": [
                {
                    "timestamp": unlock_date.isoformat() + "Z",
                    "cliff": {
                        "amountNative": 1000000,
                        "amountUSD": 50000000,
                        "percentOfTotalAllocation": 0.025,
                        "allocations": [],
                    },
                    "dailyLinearRateChange": None,
                }
            ],
        }
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await messari_provider.fetch_token_unlocks(["BTC"], days_ahead=7)

    assert len(response.data) == 1
    assert response.data[0].asset == "BTC"
    assert response.data[0].amount == 1000000
    assert response.data[0].percentage_of_supply == 2.5  # 0.025 * 100
    assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_token_unlocks_messari_filters_past_events(messari_provider):
    """Test that Messari provider filters out past unlock events."""
    now = datetime.now()
    past_date = now - timedelta(days=1)
    future_date = now + timedelta(days=3)

    mock_response_data = {
        "data": {
            "asset": {"symbol": "BTC"},
            "unlockEvents": [
                {
                    "timestamp": past_date.isoformat() + "Z",
                    "cliff": {"amountNative": 500000, "percentOfTotalAllocation": 0.01},
                },
                {
                    "timestamp": future_date.isoformat() + "Z",
                    "cliff": {"amountNative": 1000000, "percentOfTotalAllocation": 0.02},
                },
            ],
        }
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await messari_provider.fetch_token_unlocks(["BTC"], days_ahead=7)

    # Only future unlock should be included
    assert len(response.data) == 1
    assert response.data[0].amount == 1000000


@pytest.mark.anyio
async def test_fetch_whale_flows_messari_not_supported(messari_provider):
    """Test that Messari provider returns zero flows (not supported)."""
    response = await messari_provider.fetch_whale_flows("BTC", hours_back=24)

    assert response.data.asset == "BTC"
    assert response.data.inflow == 0.0
    assert response.data.outflow == 0.0
    assert response.data.net_flow == 0.0
    assert response.confidence == 0.3  # Low confidence as feature not supported


# ============================================================================
# Whale Flow Tests
# ============================================================================


@pytest.mark.anyio
async def test_fetch_whale_flows_success(onchain_provider):
    """Test successful fetch of whale flow data."""
    mock_response_data = {
        "inflow": 1500000.0,
        "outflow": 800000.0,
        "transaction_count": 25,
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await onchain_provider.fetch_whale_flows("BTC", hours_back=24)

    assert response.data.asset == "BTC"
    assert response.data.inflow == 1500000.0
    assert response.data.outflow == 800000.0
    assert response.data.net_flow == 700000.0  # inflow - outflow
    assert response.data.large_tx_count == 25
    assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_whale_flows_no_api_key(onchain_provider_no_key):
    """Test fetch without API key returns zero flows with low confidence."""
    response = await onchain_provider_no_key.fetch_whale_flows("BTC", hours_back=24)

    assert response.data.asset == "BTC"
    assert response.data.inflow == 0.0
    assert response.data.outflow == 0.0
    assert response.data.net_flow == 0.0
    assert response.data.large_tx_count == 0
    assert response.confidence == 0.3


@pytest.mark.anyio
async def test_fetch_whale_flows_network_error(onchain_provider):
    """Test handling of network errors."""
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection timeout")):
        response = await onchain_provider.fetch_whale_flows("BTC", hours_back=24)

    assert response.data.net_flow == 0.0
    assert response.confidence == 0.1  # Very low confidence on error


@pytest.mark.anyio
async def test_fetch_whale_flows_invalid_json(onchain_provider):
    """Test handling of invalid JSON response."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"invalid json {{"
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await onchain_provider.fetch_whale_flows("BTC", hours_back=24)

    assert response.data.net_flow == 0.0
    assert response.confidence == 0.1  # Very low confidence on error


@pytest.mark.anyio
async def test_fetch_whale_flows_alternative_transaction_count(onchain_provider):
    """Test parsing transaction count from transactions array."""
    mock_response_data = {
        "inflow": 1000000.0,
        "outflow": 500000.0,
        "transactions": [{"id": 1}, {"id": 2}, {"id": 3}],  # Count from array length
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await onchain_provider.fetch_whale_flows("BTC", hours_back=24)

    assert response.data.large_tx_count == 3


@pytest.mark.anyio
async def test_fetch_whale_flows_cache_integration(onchain_provider, mock_cache):
    """Test that successful fetch is cached."""
    mock_response_data = {
        "inflow": 1000000.0,
        "outflow": 500000.0,
        "transaction_count": 10,
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        await onchain_provider.fetch_whale_flows("BTC", hours_back=24)

    # Verify cache.set was called
    mock_cache.set.assert_called_once()
    call_args = mock_cache.set.call_args
    assert "onchain:whale_flows:" in call_args[0][0]  # cache key
    assert call_args[0][2] == 3600  # TTL


# ============================================================================
# Configuration Tests
# ============================================================================


def test_onchain_provider_initialization(mock_cache):
    """Test on-chain provider initialization."""
    provider = OnChainProvider(
        cache=mock_cache,
        api_key="test_key",
        provider_name="token_unlocks",
    )

    assert provider.cache == mock_cache
    assert provider.api_key == "test_key"
    assert provider.provider_name == "token_unlocks"
    assert provider.timeout_seconds == 10.0
    assert provider.api_base_url == "https://api.token.unlocks.app/api/v1"


def test_messari_provider_initialization(mock_cache):
    """Test Messari provider initialization."""
    provider = OnChainProvider(
        cache=mock_cache,
        api_key="test_messari_key",
        provider_name="messari",
    )

    assert provider.cache == mock_cache
    assert provider.api_key == "test_messari_key"
    assert provider.provider_name == "messari"
    assert provider.timeout_seconds == 10.0
    assert provider.api_base_url == "https://api.messari.io/token-unlocks/v1"


def test_onchain_provider_initialization_no_key(mock_cache):
    """Test on-chain provider initialization without API key."""
    provider = OnChainProvider(
        cache=mock_cache,
        api_key=None,
        provider_name="token_unlocks",
    )

    assert provider.api_key is None


def test_onchain_provider_initialization_custom_url(mock_cache):
    """Test on-chain provider initialization with custom API URL."""
    custom_url = "https://custom.api.com/v2"
    provider = OnChainProvider(
        cache=mock_cache,
        api_key="test_key",
        provider_name="custom",
        api_base_url=custom_url,
    )

    assert provider.api_base_url == custom_url


def test_onchain_provider_cache_ttl(onchain_provider):
    """Test cache TTL configuration."""
    assert onchain_provider.get_cache_ttl() == 3600  # 1 hour


def test_onchain_provider_name(onchain_provider):
    """Test provider name."""
    assert onchain_provider.get_provider_name() == "token_unlocks"


# ============================================================================
# API Key Validation Tests
# ============================================================================


@pytest.mark.anyio
async def test_api_key_validation_in_config():
    """Test that OnChainConfig validates API key when provider is enabled."""
    from hyperliquid_agent.config import OnChainConfig

    # Should raise error when provider is set but no API key
    with pytest.raises(ValueError, match="no API key provided"):
        OnChainConfig(enabled=True, provider="token_unlocks", api_key=None)


@pytest.mark.anyio
async def test_api_key_validation_disabled_provider():
    """Test that OnChainConfig doesn't validate when provider is disabled."""
    from hyperliquid_agent.config import OnChainConfig

    # Should not raise error when disabled
    config = OnChainConfig(enabled=False, provider="token_unlocks", api_key=None)
    assert config.enabled is False


@pytest.mark.anyio
async def test_api_key_validation_no_provider():
    """Test that OnChainConfig doesn't validate when provider is None."""
    from hyperliquid_agent.config import OnChainConfig

    # Should not raise error when provider is None
    config = OnChainConfig(enabled=True, provider=None, api_key=None)
    assert config.provider is None
