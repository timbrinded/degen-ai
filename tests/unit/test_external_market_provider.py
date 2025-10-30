"""Unit tests for external market provider."""

import json
import os
import tempfile
import urllib.error
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.external_market_provider import ExternalMarketProvider
from hyperliquid_agent.signals.models import MacroEvent


@pytest.fixture
def mock_cache():
    """Create a mock cache layer."""
    cache = AsyncMock(spec=SQLiteCacheLayer)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def external_market_provider(mock_cache):
    """Create an external market provider instance."""
    return ExternalMarketProvider(cache=mock_cache, use_yfinance=True)


# ============================================================================
# CoinGecko Asset Price Tests
# ============================================================================


@pytest.mark.anyio
async def test_fetch_btc_prices_success(external_market_provider):
    """Test successful BTC price fetch from CoinGecko."""
    mock_response_data = {
        "prices": [
            [1704067200000, 42000.0],
            [1704153600000, 42500.0],
            [1704240000000, 43000.0],
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await external_market_provider.fetch_asset_prices(["BTC"], days_back=3)

    assert "BTC" in response.data
    assert response.data["BTC"] == [42000.0, 42500.0, 43000.0]
    assert response.confidence == 1.0
    assert response.source == "external_market"
    assert response.is_cached is False


@pytest.mark.anyio
async def test_fetch_eth_prices_success(external_market_provider):
    """Test successful ETH price fetch from CoinGecko."""
    mock_response_data = {
        "prices": [
            [1704067200000, 2200.0],
            [1704153600000, 2250.0],
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await external_market_provider.fetch_asset_prices(["ETH"], days_back=2)

    assert "ETH" in response.data
    assert response.data["ETH"] == [2200.0, 2250.0]
    assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_multiple_assets_success(external_market_provider):
    """Test fetching multiple assets (BTC and ETH)."""

    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)

        if "bitcoin" in url:
            data = {"prices": [[1704067200000, 42000.0]]}
        elif "ethereum" in url:
            data = {"prices": [[1704067200000, 2200.0]]}
        else:
            data = {"prices": []}

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(data).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        response = await external_market_provider.fetch_asset_prices(["BTC", "ETH"], days_back=1)

    assert "BTC" in response.data
    assert "ETH" in response.data
    assert len(response.data["BTC"]) == 1
    assert len(response.data["ETH"]) == 1
    assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_prices_network_error(external_market_provider):
    """Test handling of network errors."""
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network error")):
        response = await external_market_provider.fetch_asset_prices(["BTC"], days_back=1)

    assert "BTC" in response.data
    assert response.data["BTC"] == []
    assert response.confidence == 0.0


@pytest.mark.anyio
async def test_fetch_prices_invalid_json(external_market_provider):
    """Test handling of invalid JSON response."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"invalid json {{"
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await external_market_provider.fetch_asset_prices(["BTC"], days_back=1)

    assert "BTC" in response.data
    assert response.data["BTC"] == []
    assert response.confidence == 0.0


@pytest.mark.anyio
async def test_fetch_prices_partial_failure(external_market_provider):
    """Test handling of partial failures (one asset succeeds, one fails)."""

    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)

        if "bitcoin" in url:
            data = {"prices": [[1704067200000, 42000.0]]}
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(data).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response
        elif "ethereum" in url:
            raise urllib.error.URLError("Network error")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        response = await external_market_provider.fetch_asset_prices(["BTC", "ETH"], days_back=1)

    assert "BTC" in response.data
    assert "ETH" in response.data
    assert len(response.data["BTC"]) == 1
    assert response.data["ETH"] == []
    assert response.confidence == 0.7  # Partial data gets 0.7 confidence


@pytest.mark.anyio
async def test_fetch_prices_with_api_key(mock_cache):
    """Test that API key is included in request headers."""
    provider = ExternalMarketProvider(cache=mock_cache, coingecko_api_key="test_api_key")

    mock_response_data = {"prices": [[1704067200000, 42000.0]]}
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        await provider.fetch_asset_prices(["BTC"], days_back=1)

        # Verify API key was included in headers (case-insensitive check)
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        # Headers are case-insensitive, check both possible cases
        assert any(key.lower() == "x-cg-pro-api-key" for key in request.headers), (
            "API key header not found"
        )
        # Get the actual header value (case-insensitive)
        api_key_value = next(
            (v for k, v in request.headers.items() if k.lower() == "x-cg-pro-api-key"), None
        )
        assert api_key_value == "test_api_key"


# ============================================================================
# yfinance SPX Tests
# ============================================================================


@pytest.mark.anyio
async def test_fetch_spx_prices_success(external_market_provider):
    """Test successful SPX price fetch from yfinance."""
    mock_hist = MagicMock()
    mock_hist.__getitem__.return_value.tolist.return_value = [4500.0, 4550.0, 4600.0]

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist

    # Mock the yfinance module import
    mock_yf = MagicMock()
    mock_yf.Ticker.return_value = mock_ticker

    with patch.dict("sys.modules", {"yfinance": mock_yf}):
        response = await external_market_provider.fetch_asset_prices(["SPX"], days_back=3)

    assert "SPX" in response.data
    assert response.data["SPX"] == [4500.0, 4550.0, 4600.0]
    assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_spx_prices_yfinance_disabled(mock_cache):
    """Test SPX fetch when yfinance is disabled."""
    provider = ExternalMarketProvider(cache=mock_cache, use_yfinance=False)

    response = await provider.fetch_asset_prices(["SPX"], days_back=3)

    assert "SPX" in response.data
    assert response.data["SPX"] == []
    assert response.confidence == 0.0


@pytest.mark.anyio
async def test_fetch_spx_prices_yfinance_error(external_market_provider):
    """Test handling of yfinance errors."""
    # Mock the yfinance module import to raise an error
    mock_yf = MagicMock()
    mock_yf.Ticker.side_effect = Exception("yfinance error")

    with patch.dict("sys.modules", {"yfinance": mock_yf}):
        response = await external_market_provider.fetch_asset_prices(["SPX"], days_back=3)

    assert "SPX" in response.data
    assert response.data["SPX"] == []
    assert response.confidence == 0.0


# ============================================================================
# Macro Calendar Tests
# ============================================================================


@pytest.mark.anyio
async def test_fetch_macro_calendar_from_api(mock_cache):
    """Test fetching macro calendar from JBlanked API."""
    # Create provider with API key
    provider = ExternalMarketProvider(cache=mock_cache, jblanked_api_key="test_key")

    mock_api_response = [
        {
            "Name": "FOMC Interest Rate Decision",
            "Currency": "USD",
            "Category": "FOMC Meeting",
            "Date": "2025.12.15 19:00:00",
        },
        {
            "Name": "US CPI m/m",
            "Currency": "USD",
            "Category": "Consumer Price Index",
            "Date": "2025.12.20 13:30:00",
        },
    ]

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_api_response).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        response = await provider.fetch_macro_calendar(days_ahead=365)

    assert len(response.data) == 2
    assert isinstance(response.data[0], MacroEvent)
    assert response.data[0].name == "FOMC Interest Rate Decision"
    assert response.data[0].impact == "high"
    assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_macro_calendar_from_file_fallback(external_market_provider):
    """Test fetching macro calendar from JSON file when API unavailable."""
    # Create temporary calendar file
    with tempfile.TemporaryDirectory() as tmpdir:
        calendar_file = os.path.join(tmpdir, "macro_calendar.json")
        calendar_data = {
            "events": [
                {
                    "name": "FOMC Meeting",
                    "date": "2025-12-15T19:00:00",
                    "impact": "high",
                    "category": "FOMC",
                },
                {
                    "name": "CPI Release",
                    "date": "2025-12-20T13:30:00",
                    "impact": "high",
                    "category": "CPI",
                },
            ]
        }

        with open(calendar_file, "w") as f:
            json.dump(calendar_data, f)

        # Patch to simulate no API key (triggers fallback)
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "hyperliquid_agent.signals.external_market_provider.os.path.join",
                return_value=calendar_file,
            ),
            patch(
                "hyperliquid_agent.signals.external_market_provider.os.path.exists",
                return_value=True,
            ),
        ):
            response = await external_market_provider.fetch_macro_calendar(days_ahead=365)

        assert len(response.data) == 2
        assert isinstance(response.data[0], MacroEvent)
        assert response.data[0].name == "FOMC Meeting"
        assert response.data[0].impact == "high"
        assert response.data[0].category == "FOMC"
        assert response.confidence == 1.0


@pytest.mark.anyio
async def test_fetch_macro_calendar_file_not_found(external_market_provider):
    """Test handling when calendar file doesn't exist and no API key."""
    with patch.dict("os.environ", {}, clear=True), patch("os.path.exists", return_value=False):
        response = await external_market_provider.fetch_macro_calendar(days_ahead=7)

    assert response.data == []
    assert response.confidence == 0.5


@pytest.mark.anyio
async def test_fetch_macro_calendar_invalid_json(external_market_provider):
    """Test handling of invalid JSON in calendar file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        calendar_file = os.path.join(tmpdir, "macro_calendar.json")

        with open(calendar_file, "w") as f:
            f.write("invalid json {{")

        with (
            patch("os.path.join", return_value=calendar_file),
            patch("os.path.exists", return_value=True),
        ):
            response = await external_market_provider.fetch_macro_calendar(days_ahead=7)

        assert response.data == []
        assert response.confidence == 0.5


@pytest.mark.anyio
async def test_fetch_macro_calendar_filters_by_date(external_market_provider):
    """Test that macro calendar filters events by date range."""
    with tempfile.TemporaryDirectory() as tmpdir:
        calendar_file = os.path.join(tmpdir, "macro_calendar.json")

        # Create events: one in the past, one in the future
        now = datetime.now()
        past_date = (now.replace(year=now.year - 1)).isoformat()
        future_date = (now.replace(year=now.year + 1)).isoformat()

        calendar_data = {
            "events": [
                {
                    "name": "Past Event",
                    "date": past_date,
                    "impact": "high",
                    "category": "CPI",
                },
                {
                    "name": "Future Event",
                    "date": future_date,
                    "impact": "high",
                    "category": "FOMC",
                },
            ]
        }

        with open(calendar_file, "w") as f:
            json.dump(calendar_data, f)

        with (
            patch("os.path.join", return_value=calendar_file),
            patch("os.path.exists", return_value=True),
        ):
            response = await external_market_provider.fetch_macro_calendar(days_ahead=7)

        # Should only include future event within 7 days (none in this case)
        # or the future event if it's within the window
        assert all(event.datetime >= now for event in response.data)


# ============================================================================
# Configuration Tests
# ============================================================================


def test_external_market_provider_initialization(mock_cache):
    """Test external market provider initialization."""
    provider = ExternalMarketProvider(
        cache=mock_cache, coingecko_api_key="test_key", use_yfinance=True
    )

    assert provider.cache == mock_cache
    assert provider.coingecko_api_key == "test_key"
    assert provider.use_yfinance is True
    assert provider.provider_name == "external_market"
    assert provider.timeout_seconds == 10.0


def test_external_market_provider_cache_ttl(external_market_provider):
    """Test cache TTL configuration."""
    assert external_market_provider.get_cache_ttl() == 900  # 15 minutes


def test_external_market_provider_name(external_market_provider):
    """Test provider name."""
    assert external_market_provider.get_provider_name() == "external_market"


def test_external_market_provider_uses_pro_api_with_key(mock_cache):
    """Test that Pro API URL is used when API key is provided."""
    provider = ExternalMarketProvider(cache=mock_cache, coingecko_api_key="test_key")

    assert "pro-api.coingecko.com" in provider.coingecko_base_url


def test_external_market_provider_uses_free_api_without_key(mock_cache):
    """Test that free API URL is used when no API key is provided."""
    provider = ExternalMarketProvider(cache=mock_cache, coingecko_api_key=None)

    assert "api.coingecko.com" in provider.coingecko_base_url
    assert "pro-api" not in provider.coingecko_base_url
