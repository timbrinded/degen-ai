"""Unit tests for TradeExecutor module."""

from unittest.mock import MagicMock, patch

import pytest

from hyperliquid_agent.config import HyperliquidConfig
from hyperliquid_agent.decision import TradeAction
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
def mock_asset_metadata():
    """Mock asset metadata response."""
    return {
        "universe": [
            {"name": "BTC", "szDecimals": 4},
            {"name": "ETH", "szDecimals": 3},
            {"name": "SOL", "szDecimals": 2},
        ]
    }


@pytest.fixture
def valid_buy_action():
    """Create a valid buy action."""
    return TradeAction(
        action_type="buy",
        coin="BTC",
        market_type="perp",
        size=0.1,
        price=50000.0,
        reasoning="Test buy",
    )


@pytest.fixture
def valid_sell_action():
    """Create a valid sell action."""
    return TradeAction(
        action_type="sell",
        coin="ETH",
        market_type="spot",
        size=1.5,
        price=3000.0,
        reasoning="Test sell",
    )


@pytest.fixture
def valid_hold_action():
    """Create a valid hold action."""
    return TradeAction(
        action_type="hold",
        coin="BTC",
        market_type="perp",
        reasoning="Wait for better entry",
    )


@pytest.fixture
def valid_close_action():
    """Create a valid close action."""
    return TradeAction(
        action_type="close",
        coin="SOL",
        market_type="perp",
        size=10.0,
        reasoning="Close position",
    )


@pytest.fixture
def market_order_action():
    """Create a market order action (price is None)."""
    return TradeAction(
        action_type="buy",
        coin="BTC",
        market_type="perp",
        size=0.5,
        price=None,
        reasoning="Market buy",
    )


def test_executor_initialization(hyperliquid_config):
    """Test TradeExecutor initializes correctly."""
    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)

        assert executor.config == hyperliquid_config
        assert executor.exchange is not None
        assert executor.info is not None
        assert executor._asset_metadata_cache == {}


def test_validate_action_valid_buy(hyperliquid_config, valid_buy_action):
    """Test validation passes for valid buy action."""
    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(valid_buy_action) is True


def test_validate_action_valid_sell(hyperliquid_config, valid_sell_action):
    """Test validation passes for valid sell action."""
    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(valid_sell_action) is True


def test_validate_action_valid_hold(hyperliquid_config, valid_hold_action):
    """Test validation passes for valid hold action."""
    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(valid_hold_action) is True


def test_validate_action_valid_close(hyperliquid_config, valid_close_action):
    """Test validation passes for valid close action."""
    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(valid_close_action) is True


def test_validate_action_invalid_action_type(hyperliquid_config):
    """Test validation fails for invalid action type."""
    invalid_action = TradeAction(
        action_type="invalid",  # type: ignore[arg-type]
        coin="BTC",
        market_type="perp",
        size=0.1,
    )

    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(invalid_action) is False


def test_validate_action_missing_coin(hyperliquid_config):
    """Test validation fails when coin is not specified."""
    invalid_action = TradeAction(
        action_type="buy",
        coin="",
        market_type="perp",
        size=0.1,
    )

    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(invalid_action) is False


def test_validate_action_invalid_market_type(hyperliquid_config):
    """Test validation fails for invalid market type."""
    invalid_action = TradeAction(
        action_type="buy",
        coin="BTC",
        market_type="invalid",  # type: ignore[arg-type]
        size=0.1,
    )

    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(invalid_action) is False


def test_validate_action_missing_size_for_buy(hyperliquid_config):
    """Test validation fails when size is missing for buy action."""
    invalid_action = TradeAction(
        action_type="buy",
        coin="BTC",
        market_type="perp",
        size=None,
    )

    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(invalid_action) is False


def test_validate_action_zero_size_for_sell(hyperliquid_config):
    """Test validation fails when size is zero for sell action."""
    invalid_action = TradeAction(
        action_type="sell",
        coin="ETH",
        market_type="spot",
        size=0.0,
    )

    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(invalid_action) is False


def test_validate_action_negative_size(hyperliquid_config):
    """Test validation fails when size is negative."""
    invalid_action = TradeAction(
        action_type="buy",
        coin="BTC",
        market_type="perp",
        size=-0.1,
    )

    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        assert executor._validate_action(invalid_action) is False


def test_execute_action_hold(hyperliquid_config, valid_hold_action):
    """Test executing hold action returns success without submitting order."""
    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(valid_hold_action)

        assert result.success is True
        assert result.action == valid_hold_action
        assert result.order_id is None
        assert result.error is None


def test_execute_action_invalid_parameters(hyperliquid_config):
    """Test executing action with invalid parameters returns failure."""
    invalid_action = TradeAction(
        action_type="buy",
        coin="",
        market_type="perp",
        size=0.1,
    )

    with patch("hyperliquid_agent.executor.Exchange"), patch("hyperliquid_agent.executor.Info"):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(invalid_action)

        assert result.success is False
        assert result.error == "Invalid action parameters"
        assert result.order_id is None


def test_execute_action_limit_order_success(
    hyperliquid_config, valid_buy_action, mock_asset_metadata
):
    """Test successful limit order execution."""
    mock_exchange = MagicMock()
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    order_response = {"status": {"resting": {"oid": "0xorder123"}}}
    mock_exchange.order.return_value = order_response

    with (
        patch("hyperliquid_agent.executor.Exchange", return_value=mock_exchange),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(valid_buy_action)

        assert result.success is True
        assert result.action == valid_buy_action
        assert result.order_id == "0xorder123"
        assert result.error is None

        # Verify order was submitted with correct parameters
        mock_exchange.order.assert_called_once()
        call_args = mock_exchange.order.call_args
        assert call_args.kwargs["name"] == "BTC"
        assert call_args.kwargs["is_buy"] is True
        assert call_args.kwargs["sz"] == 0.1
        assert call_args.kwargs["limit_px"] == 50000.0


def test_execute_action_market_order_success(
    hyperliquid_config, market_order_action, mock_asset_metadata
):
    """Test successful market order execution."""
    mock_exchange = MagicMock()
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    order_response = {"status": {"resting": {"oid": "0xmarket456"}}}
    mock_exchange.market_open.return_value = order_response

    with (
        patch("hyperliquid_agent.executor.Exchange", return_value=mock_exchange),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(market_order_action)

        assert result.success is True
        assert result.order_id == "0xmarket456"

        # Verify market order was submitted
        mock_exchange.market_open.assert_called_once()
        call_args = mock_exchange.market_open.call_args
        assert call_args.kwargs["name"] == "BTC"
        assert call_args.kwargs["is_buy"] is True
        assert call_args.kwargs["sz"] == 0.5
        assert call_args.kwargs["px"] is None


def test_execute_action_close_position(hyperliquid_config, valid_close_action, mock_asset_metadata):
    """Test closing position with market order."""
    mock_exchange = MagicMock()
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    order_response = {"status": {"resting": {"oid": "0xclose789"}}}
    mock_exchange.market_open.return_value = order_response

    with (
        patch("hyperliquid_agent.executor.Exchange", return_value=mock_exchange),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(valid_close_action)

        assert result.success is True
        assert result.order_id == "0xclose789"

        # Verify close order was submitted as market order
        mock_exchange.market_open.assert_called_once()
        call_args = mock_exchange.market_open.call_args
        assert call_args.kwargs["name"] == "SOL"
        assert call_args.kwargs["is_buy"] is True  # Close action uses buy
        assert call_args.kwargs["sz"] == 10.0
        assert call_args.kwargs["px"] is None


def test_execute_action_spot_market(hyperliquid_config, valid_sell_action, mock_asset_metadata):
    """Test order execution on spot market."""
    mock_exchange = MagicMock()
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    order_response = {"status": {"resting": {"oid": "0xspot999"}}}
    mock_exchange.order.return_value = order_response

    with (
        patch("hyperliquid_agent.executor.Exchange", return_value=mock_exchange),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(valid_sell_action)

        assert result.success is True
        assert result.order_id == "0xspot999"

        # Verify sell order was submitted
        mock_exchange.order.assert_called_once()
        call_args = mock_exchange.order.call_args
        assert call_args.kwargs["name"] == "ETH"
        assert call_args.kwargs["is_buy"] is False  # Sell action
        assert call_args.kwargs["sz"] == 1.5


def test_execute_action_api_error(hyperliquid_config, valid_buy_action, mock_asset_metadata):
    """Test execution handles API errors gracefully."""
    mock_exchange = MagicMock()
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata
    mock_exchange.order.side_effect = Exception("API connection failed")

    with (
        patch("hyperliquid_agent.executor.Exchange", return_value=mock_exchange),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(valid_buy_action)

        assert result.success is False
        assert result.error == "API connection failed"
        assert result.order_id is None


def test_execute_action_insufficient_balance_error(
    hyperliquid_config, valid_buy_action, mock_asset_metadata
):
    """Test execution handles insufficient balance error."""
    mock_exchange = MagicMock()
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata
    mock_exchange.order.side_effect = Exception("Insufficient balance")

    with (
        patch("hyperliquid_agent.executor.Exchange", return_value=mock_exchange),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(valid_buy_action)

        assert result.success is False
        assert result.error is not None and "Insufficient balance" in result.error


def test_execute_action_response_without_order_id(
    hyperliquid_config, valid_buy_action, mock_asset_metadata
):
    """Test execution handles response without order ID."""
    mock_exchange = MagicMock()
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    # Response without order ID structure
    order_response = {"status": "filled"}
    mock_exchange.order.return_value = order_response

    with (
        patch("hyperliquid_agent.executor.Exchange", return_value=mock_exchange),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(valid_buy_action)

        assert result.success is True
        assert result.order_id is None  # No order ID in response


def test_round_size_with_decimals(hyperliquid_config, mock_asset_metadata):
    """Test size rounding conforms to asset szDecimals."""
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    with (
        patch("hyperliquid_agent.executor.Exchange"),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)

        # BTC has 4 decimals
        rounded_btc = executor._round_size(0.123456, "BTC")
        assert rounded_btc == 0.1234

        # ETH has 3 decimals
        rounded_eth = executor._round_size(1.23456, "ETH")
        assert rounded_eth == 1.234

        # SOL has 2 decimals
        rounded_sol = executor._round_size(10.999, "SOL")
        assert rounded_sol == 10.99


def test_round_size_rounds_down(hyperliquid_config, mock_asset_metadata):
    """Test size rounding always rounds down."""
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    with (
        patch("hyperliquid_agent.executor.Exchange"),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)

        # Should round down, not up
        rounded = executor._round_size(0.12349, "BTC")
        assert rounded == 0.1234  # Not 0.1235


def test_get_asset_metadata_caching(hyperliquid_config, mock_asset_metadata):
    """Test asset metadata is cached after first retrieval."""
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    with (
        patch("hyperliquid_agent.executor.Exchange"),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)

        # First call should fetch from API
        metadata1 = executor._get_asset_metadata("BTC")
        assert metadata1["name"] == "BTC"
        assert mock_info.meta.call_count == 1

        # Second call should use cache
        metadata2 = executor._get_asset_metadata("BTC")
        assert metadata2 == metadata1
        assert mock_info.meta.call_count == 1  # No additional API call


def test_get_asset_metadata_not_found(hyperliquid_config, mock_asset_metadata):
    """Test error when asset not found in universe."""
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    with (
        patch("hyperliquid_agent.executor.Exchange"),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)

        with pytest.raises(ValueError, match="Asset UNKNOWN not found in universe"):
            executor._get_asset_metadata("UNKNOWN")


def test_submit_order_close_without_size(hyperliquid_config, mock_asset_metadata):
    """Test close action without size raises error."""
    mock_exchange = MagicMock()
    mock_info = MagicMock()
    mock_info.meta.return_value = mock_asset_metadata

    close_action = TradeAction(
        action_type="close",
        coin="BTC",
        market_type="perp",
        size=None,  # Missing size
    )

    with (
        patch("hyperliquid_agent.executor.Exchange", return_value=mock_exchange),
        patch("hyperliquid_agent.executor.Info", return_value=mock_info),
    ):
        executor = TradeExecutor(hyperliquid_config)
        result = executor.execute_action(close_action)

        assert result.success is False
        assert (
            result.error is not None and "Size must be specified for close action" in result.error
        )
