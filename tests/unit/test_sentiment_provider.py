"""Unit tests for sentiment provider."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.sentiment_provider import SentimentProvider


@pytest.fixture
def mock_cache():
    """Create a mock cache layer."""
    cache = AsyncMock(spec=SQLiteCacheLayer)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def sentiment_provider(mock_cache):
    """Create a sentiment provider instance."""
    return SentimentProvider(cache=mock_cache)


# ============================================================================
# Fear & Greed Index Tests
# ============================================================================


@pytest.mark.anyio
async def test_fetch_fear_greed_success_extreme_fear(sentiment_provider):
    """Test successful fetch with extreme fear value (0)."""
    mock_response_data = {"data": [{"value": "0", "value_classification": "Extreme Fear"}]}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await sentiment_provider.fetch_fear_greed_index()

    assert response.data == -1.0  # 0 maps to -1.0
    assert response.confidence == 1.0
    assert response.source == "sentiment"
    assert response.is_cached is False


@pytest.mark.anyio
async def test_fetch_fear_greed_success_neutral(sentiment_provider):
    """Test successful fetch with neutral value (50)."""
    mock_response_data = {"data": [{"value": "50", "value_classification": "Neutral"}]}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await sentiment_provider.fetch_fear_greed_index()

    assert response.data == 0.0  # 50 maps to 0.0
    assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_fear_greed_success_extreme_greed(sentiment_provider):
    """Test successful fetch with extreme greed value (100)."""
    mock_response_data = {"data": [{"value": "100", "value_classification": "Extreme Greed"}]}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await sentiment_provider.fetch_fear_greed_index()

    assert response.data == 1.0  # 100 maps to +1.0
    assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_fear_greed_success_various_values(sentiment_provider):
    """Test normalization with various fear/greed values."""
    test_cases = [
        (25, -0.5),  # Fear
        (75, 0.5),  # Greed
        (10, -0.8),  # Extreme fear
        (90, 0.8),  # Extreme greed
    ]

    for raw_value, expected_normalized in test_cases:
        mock_response_data = {"data": [{"value": str(raw_value)}]}

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_response_data).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            response = await sentiment_provider.fetch_fear_greed_index()

        assert response.data == pytest.approx(expected_normalized, abs=0.01)
        assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_fear_greed_network_timeout(sentiment_provider):
    """Test handling of network timeout."""
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection timeout")):
        response = await sentiment_provider.fetch_fear_greed_index()

    # Should return neutral value with degraded confidence
    assert response.data == 0.0
    assert response.confidence == 0.3
    assert response.source == "sentiment"


@pytest.mark.anyio
async def test_fetch_fear_greed_invalid_json(sentiment_provider):
    """Test handling of invalid JSON response."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"invalid json {{"
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await sentiment_provider.fetch_fear_greed_index()

    # Should return neutral value with degraded confidence
    assert response.data == 0.0
    assert response.confidence == 0.3


@pytest.mark.anyio
async def test_fetch_fear_greed_missing_data_field(sentiment_provider):
    """Test handling of missing 'data' field in response."""
    mock_response_data = {"error": "No data available"}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await sentiment_provider.fetch_fear_greed_index()

    # Should return neutral value with degraded confidence
    assert response.data == 0.0
    assert response.confidence == 0.3


@pytest.mark.anyio
async def test_fetch_fear_greed_empty_data_array(sentiment_provider):
    """Test handling of empty data array."""
    mock_response_data = {"data": []}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await sentiment_provider.fetch_fear_greed_index()

    # Should return neutral value with degraded confidence
    assert response.data == 0.0
    assert response.confidence == 0.3


@pytest.mark.anyio
async def test_fetch_fear_greed_missing_value_field(sentiment_provider):
    """Test handling of missing 'value' field in data."""
    mock_response_data = {"data": [{"timestamp": "1234567890"}]}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await sentiment_provider.fetch_fear_greed_index()

    # Should return neutral value with degraded confidence
    assert response.data == 0.0
    assert response.confidence == 0.3


@pytest.mark.anyio
async def test_fetch_fear_greed_clamping_edge_cases(sentiment_provider):
    """Test that values are properly clamped to [-1.0, 1.0] range."""
    # Test values that might cause out-of-range results
    test_cases = [
        (-10, -1.0),  # Below 0 should clamp to -1.0
        (150, 1.0),  # Above 100 should clamp to +1.0
    ]

    for raw_value, expected_clamped in test_cases:
        mock_response_data = {"data": [{"value": str(raw_value)}]}

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_response_data).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            response = await sentiment_provider.fetch_fear_greed_index()

        assert response.data == expected_clamped
        assert -1.0 <= response.data <= 1.0


@pytest.mark.anyio
async def test_fetch_fear_greed_cache_integration(sentiment_provider, mock_cache):
    """Test that successful fetch is cached."""
    mock_response_data = {"data": [{"value": "75"}]}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        await sentiment_provider.fetch_fear_greed_index()

    # Verify cache.set was called with correct parameters
    mock_cache.set.assert_called_once()
    call_args = mock_cache.set.call_args
    assert call_args[0][0] == "sentiment:fear_greed_index"  # cache key
    assert call_args[0][1] == 0.5  # normalized value (75 -> 0.5)
    assert call_args[0][2] == 1800  # TTL


@pytest.mark.anyio
async def test_fetch_fear_greed_confidence_degradation_on_failure(sentiment_provider):
    """Test that confidence score is degraded on API failures."""
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network error")):
        response = await sentiment_provider.fetch_fear_greed_index()

    # Confidence should be degraded (0.3) on failure
    assert response.confidence == 0.3
    assert response.data == 0.0  # Neutral fallback


# ============================================================================
# Configuration Tests
# ============================================================================


def test_sentiment_provider_initialization(mock_cache):
    """Test sentiment provider initialization."""
    provider = SentimentProvider(cache=mock_cache, api_key="test_key")

    assert provider.cache == mock_cache
    assert provider.api_key == "test_key"
    assert provider.provider_name == "sentiment"
    assert provider.timeout_seconds == 10.0
    assert provider.fear_greed_api_url == "https://api.alternative.me/fng/"


def test_sentiment_provider_cache_ttl(sentiment_provider):
    """Test cache TTL configuration."""
    assert sentiment_provider.get_cache_ttl() == 1800  # 30 minutes


def test_sentiment_provider_name(sentiment_provider):
    """Test provider name."""
    assert sentiment_provider.get_provider_name() == "sentiment"
