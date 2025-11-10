"""Unit tests for size rounding in TradeExecutor.

This test suite verifies that size rounding works correctly for both spot and perp markets,
with different sz_decimals values and edge cases.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from hyperliquid_agent.config import HyperliquidConfig
from hyperliquid_agent.executor import TradeExecutor


@pytest.fixture
def hyperliquid_config():
    """Create a test Hyperliquid configuration."""
    return HyperliquidConfig(
        account_address="0x1234567890123456789012345678901234567890",
        secret_key="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        base_url="https://api.hyperliquid-testnet.xyz",
    )


@pytest.fixture
def mock_spot_metadata():
    """Mock spot metadata response."""
    return {
        "universe": [
            {"name": "ETH/USDC", "index": 0},
            {"name": "BTC/USDC", "index": 1},
        ],
        "tokens": [
            {"name": "USDC", "index": 0},
            {"name": "ETH", "index": 1},
            {"name": "BTC", "index": 2},
        ],
    }


@pytest.fixture
def mock_registry_with_decimals():
    """Create a mock MarketRegistry with various decimal configurations."""
    registry = MagicMock()
    registry.is_ready = True

    # Define different sz_decimals for different coins and market types
    decimals_config = {
        ("BTC", "perp"): 4,
        ("BTC", "spot"): 5,
        ("ETH", "perp"): 3,
        ("ETH", "spot"): 4,
        ("SOL", "perp"): 2,
        ("SOL", "spot"): 3,
        ("DOGE", "perp"): 0,  # Edge case: no decimals
        ("DOGE", "spot"): 1,
        ("SHIB", "perp"): 8,  # Edge case: many decimals
        ("SHIB", "spot"): 8,
    }

    def get_sz_decimals(coin, market_type):
        return decimals_config.get((coin, market_type), 4)

    registry.get_sz_decimals.side_effect = get_sz_decimals

    def get_market_name(coin, market_type):
        return coin if market_type == "perp" else f"{coin}/USDC"

    registry.get_market_name.side_effect = get_market_name
    registry.get_spot_market_info.side_effect = (
        lambda symbol, quote="USDC", market_identifier=None: SimpleNamespace(
            market_name=f"{symbol}/{quote.upper()}",
            quote_symbol=quote.upper(),
            aliases=[f"{symbol}/{quote.upper()}"],
        )
    )

    return registry


def create_executor(config, registry, spot_metadata):
    """Helper to create TradeExecutor with mocked dependencies."""
    mock_info = MagicMock()
    mock_info.spot_meta.return_value = spot_metadata
    mock_info.meta.return_value = {"universe": []}

    with (
        patch("hyperliquid_agent.executor.Exchange"),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        return TradeExecutor(config, registry)


class TestSizeRoundingBasic:
    """Test basic size rounding functionality."""

    def test_round_size_btc_perp_4_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test BTC perp rounding with 4 decimals."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # Should round down to 4 decimals
        result = executor._round_size(0.123456789, "BTC", "perp")
        assert result == 0.1234

    def test_round_size_btc_spot_5_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test BTC spot rounding with 5 decimals."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # Should round down to 5 decimals
        result = executor._round_size(0.123456789, "BTC", "spot")
        assert result == 0.12345

    def test_round_size_eth_perp_3_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test ETH perp rounding with 3 decimals."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        result = executor._round_size(1.23456, "ETH", "perp")
        assert result == 1.234

    def test_round_size_eth_spot_4_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test ETH spot rounding with 4 decimals."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        result = executor._round_size(1.23456, "ETH", "spot")
        assert result == 1.2345

    def test_round_size_sol_perp_2_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test SOL perp rounding with 2 decimals."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        result = executor._round_size(10.999, "SOL", "perp")
        assert result == 10.99

    def test_round_size_sol_spot_3_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test SOL spot rounding with 3 decimals."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        result = executor._round_size(10.999, "SOL", "spot")
        assert result == 10.999


class TestSizeRoundingDirection:
    """Test that rounding always rounds down (ROUND_DOWN)."""

    def test_rounds_down_not_up(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test that rounding always rounds down, never up."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # 0.12349 should round down to 0.1234, not up to 0.1235
        result = executor._round_size(0.12349, "BTC", "perp")
        assert result == 0.1234

        # 0.99999 should round down to 0.9999, not up to 1.0000
        result = executor._round_size(0.99999, "BTC", "perp")
        assert result == 0.9999

    def test_rounds_down_with_9s(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test rounding down when trailing digits are all 9s."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # ETH perp has 3 decimals
        result = executor._round_size(1.2349999, "ETH", "perp")
        assert result == 1.234

        # SOL perp has 2 decimals
        result = executor._round_size(10.9999, "SOL", "perp")
        assert result == 10.99


class TestSizeRoundingEdgeCases:
    """Test edge cases for size rounding."""

    def test_very_small_size(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test rounding very small sizes."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # Very small BTC amount
        result = executor._round_size(0.00001234, "BTC", "perp")
        assert result == 0.0000

        # Very small ETH amount
        result = executor._round_size(0.0001234, "ETH", "perp")
        assert result == 0.000

    def test_very_large_size(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test rounding very large sizes."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # Large BTC amount
        result = executor._round_size(12345.6789, "BTC", "perp")
        assert result == 12345.6789

        # Large ETH amount
        result = executor._round_size(99999.9999, "ETH", "perp")
        assert result == 99999.999

    def test_zero_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test rounding with 0 decimals (whole numbers only)."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # DOGE perp has 0 decimals
        result = executor._round_size(123.456, "DOGE", "perp")
        assert result == 123.0

        result = executor._round_size(99.999, "DOGE", "perp")
        assert result == 99.0

    def test_many_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test rounding with many decimals (8)."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # SHIB has 8 decimals
        result = executor._round_size(0.123456789012345, "SHIB", "perp")
        assert result == 0.12345678

        result = executor._round_size(1.999999999, "SHIB", "perp")
        assert result == 1.99999999

    def test_exact_decimal_match(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test when size already matches required decimals."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # BTC perp has 4 decimals, input already has 4
        result = executor._round_size(0.1234, "BTC", "perp")
        assert result == 0.1234

        # ETH perp has 3 decimals, input already has 3
        result = executor._round_size(1.234, "ETH", "perp")
        assert result == 1.234

    def test_fewer_decimals_than_required(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test when input has fewer decimals than required."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # BTC perp has 4 decimals, input has 2
        result = executor._round_size(0.12, "BTC", "perp")
        assert result == 0.12

        # ETH perp has 3 decimals, input has 1
        result = executor._round_size(1.2, "ETH", "perp")
        assert result == 1.2

    def test_whole_number_input(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test rounding whole numbers."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        result = executor._round_size(10.0, "BTC", "perp")
        assert result == 10.0

        result = executor._round_size(5.0, "ETH", "perp")
        assert result == 5.0


class TestSizeRoundingPrecision:
    """Test precision handling in size rounding."""

    def test_decimal_precision_maintained(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test that Decimal precision is maintained during rounding."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # Test that we don't lose precision due to float arithmetic
        result = executor._round_size(0.1 + 0.2, "ETH", "perp")  # 0.30000000000000004 in float
        assert result == 0.3

    def test_no_floating_point_errors(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test that floating point errors don't affect rounding."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        # These operations can cause floating point errors
        result = executor._round_size(0.1 * 3, "ETH", "perp")
        assert result == 0.3

        # 0.7 - 0.4 = 0.29999999999999993 in float, rounds down to 0.299 with 3 decimals
        result = executor._round_size(0.7 - 0.4, "ETH", "perp")
        assert result == 0.299  # Correctly rounds down


class TestSizeRoundingMarketTypeDifferences:
    """Test that spot and perp markets use different sz_decimals."""

    def test_btc_spot_vs_perp_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test BTC uses different decimals for spot vs perp."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        size = 0.123456789

        # BTC perp: 4 decimals
        perp_result = executor._round_size(size, "BTC", "perp")
        assert perp_result == 0.1234

        # BTC spot: 5 decimals
        spot_result = executor._round_size(size, "BTC", "spot")
        assert spot_result == 0.12345

        # Results should be different
        assert perp_result != spot_result

    def test_eth_spot_vs_perp_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test ETH uses different decimals for spot vs perp."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        size = 1.23456789

        # ETH perp: 3 decimals
        perp_result = executor._round_size(size, "ETH", "perp")
        assert perp_result == 1.234

        # ETH spot: 4 decimals
        spot_result = executor._round_size(size, "ETH", "spot")
        assert spot_result == 1.2345

        # Results should be different
        assert perp_result != spot_result

    def test_sol_spot_vs_perp_decimals(
        self, hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
    ):
        """Test SOL uses different decimals for spot vs perp."""
        executor = create_executor(
            hyperliquid_config, mock_registry_with_decimals, mock_spot_metadata
        )

        size = 10.9999

        # SOL perp: 2 decimals
        perp_result = executor._round_size(size, "SOL", "perp")
        assert perp_result == 10.99

        # SOL spot: 3 decimals
        spot_result = executor._round_size(size, "SOL", "spot")
        assert spot_result == 10.999

        # Results should be different
        assert perp_result != spot_result


class TestSizeRoundingErrorHandling:
    """Test error handling in size rounding."""

    def test_rounding_with_invalid_coin(self, hyperliquid_config, mock_spot_metadata):
        """Test rounding handles errors gracefully when coin is invalid."""
        registry = MagicMock()
        registry.is_ready = True
        registry.get_sz_decimals.side_effect = ValueError("Unknown asset")
        registry.get_market_name.side_effect = lambda coin, market_type: f"{coin}/{market_type}"

        executor = create_executor(hyperliquid_config, registry, mock_spot_metadata)

        # Should return original value on error
        result = executor._round_size(0.123456, "INVALID", "perp")
        assert result == 0.123456

    def test_rounding_with_registry_error(self, hyperliquid_config, mock_spot_metadata):
        """Test rounding handles registry errors gracefully."""
        registry = MagicMock()
        registry.is_ready = True
        registry.get_sz_decimals.side_effect = Exception("Registry error")
        registry.get_market_name.side_effect = lambda coin, market_type: f"{coin}/{market_type}"

        executor = create_executor(hyperliquid_config, registry, mock_spot_metadata)

        # Should return original value on error
        result = executor._round_size(1.23456, "ETH", "perp")
        assert result == 1.23456
