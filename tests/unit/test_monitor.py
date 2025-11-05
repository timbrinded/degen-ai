"""Unit tests for PositionMonitor module."""

from unittest.mock import MagicMock, patch

import pytest

from hyperliquid_agent.config import HyperliquidConfig
from hyperliquid_agent.monitor import AccountState, Position, PositionMonitor


@pytest.fixture
def hyperliquid_config():
    """Create a test Hyperliquid configuration."""
    return HyperliquidConfig(
        account_address="0x1234567890123456789012345678901234567890",
        secret_key="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        base_url="https://api.hyperliquid-testnet.xyz",
    )


@pytest.fixture
def mock_user_state_with_positions():
    """Mock API response with multiple positions."""
    return {
        "marginSummary": {"accountValue": "10000.50"},
        "withdrawable": "5000.25",
        "assetPositions": [
            {
                "position": {
                    "coin": "BTC",
                    "szi": "0.5",
                    "entryPx": "50000.0",
                    "positionValue": "25500.0",
                    "unrealizedPnl": "500.0",
                }
            },
            {
                "position": {
                    "coin": "ETH",
                    "szi": "-2.0",
                    "entryPx": "3000.0",
                    "positionValue": "-6200.0",
                    "unrealizedPnl": "-200.0",
                }
            },
        ],
    }


@pytest.fixture
def mock_user_state_empty():
    """Mock API response with no positions."""
    return {
        "marginSummary": {"accountValue": "1000.0"},
        "withdrawable": "1000.0",
        "assetPositions": [],
    }


@pytest.fixture
def mock_user_state_zero_positions():
    """Mock API response with zero-sized positions (should be filtered out)."""
    return {
        "marginSummary": {"accountValue": "5000.0"},
        "withdrawable": "5000.0",
        "assetPositions": [
            {
                "position": {
                    "coin": "BTC",
                    "szi": "0",
                    "entryPx": "50000.0",
                    "positionValue": "0",
                    "unrealizedPnl": "0",
                }
            }
        ],
    }


@pytest.fixture
def mock_user_state_missing_fields():
    """Mock API response with missing optional fields."""
    return {
        "marginSummary": {},
        "assetPositions": [
            {
                "position": {
                    "coin": "SOL",
                    "szi": "10.0",
                }
            }
        ],
    }


def test_position_monitor_initialization(hyperliquid_config):
    """Test PositionMonitor initializes correctly."""
    monitor = PositionMonitor(hyperliquid_config)

    assert monitor.account_address == hyperliquid_config.account_address
    assert monitor.last_valid_state is None
    assert monitor.info is not None


@patch("hyperliquid_agent.monitor.Info")
def test_get_current_state_success(
    mock_info_class, hyperliquid_config, mock_user_state_with_positions
):
    """Test successful retrieval of current state."""
    # Setup mock
    mock_info_instance = MagicMock()
    mock_info_instance.user_state.return_value = mock_user_state_with_positions
    mock_info_class.return_value = mock_info_instance

    monitor = PositionMonitor(hyperliquid_config)
    state = monitor.get_current_state()

    # Verify API was called
    mock_info_instance.user_state.assert_called_once_with(hyperliquid_config.account_address)

    # Verify state properties
    assert state.portfolio_value == 10000.50
    assert state.available_balance == 5000.25
    assert len(state.positions) == 2
    assert state.is_stale is False
    assert state.timestamp > 0

    # Verify first position (BTC)
    btc_position = state.positions[0]
    assert btc_position.coin == "BTC"
    assert btc_position.size == 0.5
    assert btc_position.entry_price == 50000.0
    assert btc_position.current_price == 51000.0  # 25500 / 0.5
    assert btc_position.unrealized_pnl == 500.0
    assert btc_position.market_type == "perp"

    # Verify second position (ETH) - negative size should be converted to absolute
    eth_position = state.positions[1]
    assert eth_position.coin == "ETH"
    assert eth_position.size == 2.0  # Absolute value
    assert eth_position.entry_price == 3000.0
    assert eth_position.current_price == 3100.0  # abs(-6200 / -2.0)
    assert eth_position.unrealized_pnl == -200.0
    assert eth_position.market_type == "perp"

    # Verify state is cached
    assert monitor.last_valid_state == state


@patch("hyperliquid_agent.monitor.Info")
def test_get_current_state_empty_positions(
    mock_info_class, hyperliquid_config, mock_user_state_empty
):
    """Test retrieval with no positions."""
    mock_info_instance = MagicMock()
    mock_info_instance.user_state.return_value = mock_user_state_empty
    mock_info_class.return_value = mock_info_instance

    monitor = PositionMonitor(hyperliquid_config)
    state = monitor.get_current_state()

    assert state.portfolio_value == 1000.0
    assert state.available_balance == 1000.0
    assert len(state.positions) == 0
    assert state.is_stale is False


@patch("hyperliquid_agent.monitor.Info")
def test_get_current_state_filters_zero_positions(
    mock_info_class, hyperliquid_config, mock_user_state_zero_positions
):
    """Test that zero-sized positions are filtered out."""
    mock_info_instance = MagicMock()
    mock_info_instance.user_state.return_value = mock_user_state_zero_positions
    mock_info_class.return_value = mock_info_instance

    monitor = PositionMonitor(hyperliquid_config)
    state = monitor.get_current_state()

    assert state.portfolio_value == 5000.0
    assert len(state.positions) == 0  # Zero-sized position should be filtered


@patch("hyperliquid_agent.monitor.Info")
def test_parse_user_state_missing_fields(
    mock_info_class, hyperliquid_config, mock_user_state_missing_fields
):
    """Test parsing with missing optional fields uses defaults."""
    mock_info_instance = MagicMock()
    mock_info_instance.user_state.return_value = mock_user_state_missing_fields
    mock_info_class.return_value = mock_info_instance

    monitor = PositionMonitor(hyperliquid_config)
    state = monitor.get_current_state()

    # Should use defaults for missing fields
    assert state.portfolio_value == 0.0
    assert state.available_balance == 0.0
    assert len(state.positions) == 1

    # Position with missing fields should use defaults
    position = state.positions[0]
    assert position.coin == "SOL"
    assert position.size == 10.0
    assert position.entry_price == 0.0
    assert position.unrealized_pnl == 0.0


@patch("hyperliquid_agent.monitor.Info")
def test_get_current_state_api_error_no_cache(mock_info_class, hyperliquid_config):
    """Test API error with no cached state raises exception."""
    mock_info_instance = MagicMock()
    mock_info_instance.user_state.side_effect = Exception("API connection failed")
    mock_info_class.return_value = mock_info_instance

    monitor = PositionMonitor(hyperliquid_config)

    with pytest.raises(
        Exception, match="Failed to retrieve account state and no cached state available"
    ):
        monitor.get_current_state()


@patch("hyperliquid_agent.monitor.Info")
def test_get_current_state_api_error_with_cache(
    mock_info_class, hyperliquid_config, mock_user_state_with_positions
):
    """Test API error with cached state returns stale state."""
    mock_info_instance = MagicMock()
    mock_info_class.return_value = mock_info_instance

    monitor = PositionMonitor(hyperliquid_config)

    # First call succeeds and caches state
    mock_info_instance.user_state.return_value = mock_user_state_with_positions
    first_state = monitor.get_current_state()
    assert first_state.is_stale is False
    assert monitor.last_valid_state is not None

    # Second call fails, should return cached state with stale flag
    mock_info_instance.user_state.side_effect = Exception("API connection failed")
    second_state = monitor.get_current_state()

    assert second_state.is_stale is True
    assert second_state.portfolio_value == first_state.portfolio_value
    assert len(second_state.positions) == len(first_state.positions)
    # Verify it's the same cached object
    assert second_state is monitor.last_valid_state


@patch("hyperliquid_agent.monitor.Info")
def test_get_current_state_multiple_calls_updates_cache(
    mock_info_class, hyperliquid_config, mock_user_state_with_positions, mock_user_state_empty
):
    """Test multiple successful calls update the cached state."""
    mock_info_instance = MagicMock()
    mock_info_class.return_value = mock_info_instance

    monitor = PositionMonitor(hyperliquid_config)

    # First call with positions
    mock_info_instance.user_state.return_value = mock_user_state_with_positions
    first_state = monitor.get_current_state()
    assert len(first_state.positions) == 2
    assert first_state.portfolio_value == 10000.50

    # Second call with empty positions
    mock_info_instance.user_state.return_value = mock_user_state_empty
    second_state = monitor.get_current_state()
    assert len(second_state.positions) == 0
    assert second_state.portfolio_value == 1000.0

    # Verify cache was updated
    assert monitor.last_valid_state == second_state
    assert monitor.last_valid_state != first_state


def test_parse_user_state_directly(hyperliquid_config, mock_user_state_with_positions):
    """Test _parse_user_state method directly."""
    monitor = PositionMonitor(hyperliquid_config)
    mock_spot_state = {"balances": []}
    state = monitor._parse_user_state(mock_user_state_with_positions, mock_spot_state)

    assert isinstance(state, AccountState)
    assert state.portfolio_value == 10000.50
    assert state.available_balance == 5000.25
    assert len(state.positions) == 2
    assert all(isinstance(pos, Position) for pos in state.positions)


@patch("hyperliquid_agent.monitor.Info")
def test_parse_user_state_values_spot_assets(mock_info_class, hyperliquid_config):
    """Spot balances should be valued when pricing data is available."""

    mock_info_instance = MagicMock()
    mock_info_class.return_value = mock_info_instance

    monitor = PositionMonitor(hyperliquid_config)

    def fake_price_lookup(coin: str) -> float | None:
        return 1.0 if coin.upper() == "USDC" else 2000.0

    monitor._get_spot_price = MagicMock(side_effect=fake_price_lookup)

    account_state = monitor._parse_user_state(
        {
            "marginSummary": {"accountValue": "8000"},
            "withdrawable": "4000",
            "assetPositions": [],
        },
        {
            "balances": [
                {"coin": "USDC", "total": "3000"},
                {"coin": "UETH", "total": "1.5"},
            ]
        },
    )

    assert account_state.portfolio_value == pytest.approx(14000.0)
    assert account_state.spot_balances["UETH"] == pytest.approx(1.5)
    spot_positions = [p for p in account_state.positions if p.market_type == "spot"]
    assert len(spot_positions) == 1
    assert spot_positions[0].coin == "UETH"
    assert spot_positions[0].current_price == pytest.approx(2000.0)
