"""Unit tests for GovernedTradingAgent helper methods."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from hyperliquid_agent.governed_agent import GovernedTradingAgent, TradingConstants
from hyperliquid_agent.monitor import Position
from hyperliquid_agent.signals import EnhancedAccountState, FastLoopSignals, MediumLoopSignals
from hyperliquid_agent.signals.processor import TechnicalIndicators


@pytest.fixture
def mock_agent():
    """Create a mock agent with minimal setup for testing helper methods."""
    # Create a mock agent without full initialization
    agent = Mock(spec=GovernedTradingAgent)

    # Add the logger mock
    agent.logger = Mock()
    agent.tick_count = 0
    agent.constants = TradingConstants()

    # Bind the actual methods from GovernedTradingAgent to the mock
    agent._select_representative_asset = GovernedTradingAgent._select_representative_asset.__get__(
        agent, GovernedTradingAgent
    )
    agent._validate_indicators = GovernedTradingAgent._validate_indicators.__get__(
        agent, GovernedTradingAgent
    )
    agent._extract_technical_indicators = (
        GovernedTradingAgent._extract_technical_indicators.__get__(agent, GovernedTradingAgent)
    )
    agent._calculate_weighted_funding_rate = (
        GovernedTradingAgent._calculate_weighted_funding_rate.__get__(agent, GovernedTradingAgent)
    )
    agent._calculate_average_spread_and_depth = (
        GovernedTradingAgent._calculate_average_spread_and_depth.__get__(
            agent, GovernedTradingAgent
        )
    )

    return agent


@pytest.fixture
def btc_indicators():
    """Create valid BTC technical indicators."""
    return TechnicalIndicators(
        sma_20=95000.0,
        sma_50=92000.0,
        adx=35.0,
        rsi=65.0,
    )


@pytest.fixture
def eth_indicators():
    """Create valid ETH technical indicators."""
    return TechnicalIndicators(
        sma_20=3500.0,
        sma_50=3400.0,
        adx=28.0,
        rsi=58.0,
    )


class TestSelectRepresentativeAsset:
    """Test the _select_representative_asset helper method."""

    def test_btc_preferred(self, mock_agent, btc_indicators, eth_indicators):
        """Test that BTC is preferred when available."""
        account_state = EnhancedAccountState(
            portfolio_value=50000.0,
            available_balance=10000.0,
            positions=[
                Position(
                    coin="ETH",
                    size=10.0,
                    entry_price=3400.0,
                    current_price=3500.0,
                    unrealized_pnl=1000.0,
                    market_type="perp",
                )
            ],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        medium_signals = MediumLoopSignals(
            technical_indicators={"BTC": btc_indicators, "ETH": eth_indicators},
            funding_basis={"BTC": 0.0001, "ETH": 0.00015},
            perp_spot_basis={"BTC": 2.0, "ETH": 3.0},
            concentration_ratios={"ETH": 0.7},
            drift_from_targets={"ETH": 2.5},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={"BTC": 5.0, "ETH": 3.0},
            oi_to_volume_ratio={"BTC": 0.8, "ETH": 0.7},
            funding_rate_trend={"BTC": "stable", "ETH": "increasing"},
            metadata=None,  # type: ignore
        )

        selected = mock_agent._select_representative_asset(account_state, medium_signals)

        assert selected == "BTC", "BTC should be selected when available"

    def test_largest_position_when_no_btc(self, mock_agent, eth_indicators):
        """Test that largest position is selected when BTC not available."""
        account_state = EnhancedAccountState(
            portfolio_value=50000.0,
            available_balance=10000.0,
            positions=[
                Position(
                    coin="ETH",
                    size=10.0,
                    entry_price=3400.0,
                    current_price=3500.0,
                    unrealized_pnl=1000.0,
                    market_type="perp",
                ),
                Position(
                    coin="SOL",
                    size=100.0,
                    entry_price=100.0,
                    current_price=110.0,
                    unrealized_pnl=1000.0,
                    market_type="perp",
                ),
            ],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        sol_indicators = TechnicalIndicators(sma_20=105.0, sma_50=102.0, adx=22.0, rsi=55.0)

        medium_signals = MediumLoopSignals(
            technical_indicators={"ETH": eth_indicators, "SOL": sol_indicators},
            funding_basis={"ETH": 0.00015, "SOL": 0.0002},
            perp_spot_basis={"ETH": 3.0, "SOL": 4.0},
            concentration_ratios={"ETH": 0.7, "SOL": 0.22},
            drift_from_targets={"ETH": 2.5, "SOL": 1.2},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={"ETH": 3.0, "SOL": 8.0},
            oi_to_volume_ratio={"ETH": 0.7, "SOL": 0.9},
            funding_rate_trend={"ETH": "increasing", "SOL": "stable"},
            metadata=None,  # type: ignore
        )

        selected = mock_agent._select_representative_asset(account_state, medium_signals)

        # ETH has larger notional value: 10 * 3500 = 35000 vs SOL: 100 * 110 = 11000
        assert selected == "ETH", "Largest position by notional value should be selected"

    def test_first_available_when_no_positions(self, mock_agent, eth_indicators):
        """Test fallback to first available coin when no positions."""
        account_state = EnhancedAccountState(
            portfolio_value=10000.0,
            available_balance=10000.0,
            positions=[],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        medium_signals = MediumLoopSignals(
            technical_indicators={"ETH": eth_indicators},
            funding_basis={"ETH": 0.00015},
            perp_spot_basis={"ETH": 3.0},
            concentration_ratios={},
            drift_from_targets={},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={"ETH": 3.0},
            oi_to_volume_ratio={"ETH": 0.7},
            funding_rate_trend={"ETH": "increasing"},
            metadata=None,  # type: ignore
        )

        selected = mock_agent._select_representative_asset(account_state, medium_signals)

        assert selected == "ETH", "First available coin should be selected"

    def test_none_when_no_indicators(self, mock_agent):
        """Test returns None when no indicators available."""
        account_state = EnhancedAccountState(
            portfolio_value=10000.0,
            available_balance=10000.0,
            positions=[],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        medium_signals = MediumLoopSignals(
            technical_indicators={},
            funding_basis={},
            perp_spot_basis={},
            concentration_ratios={},
            drift_from_targets={},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={},
            oi_to_volume_ratio={},
            funding_rate_trend={},
            metadata=None,  # type: ignore
        )

        selected = mock_agent._select_representative_asset(account_state, medium_signals)

        assert selected is None, "Should return None when no indicators available"


class TestValidateIndicators:
    """Test the _validate_indicators helper method."""

    def test_valid_indicators(self, mock_agent, btc_indicators):
        """Test validation passes for valid indicators."""
        assert mock_agent._validate_indicators(btc_indicators) is True

    def test_invalid_adx_too_high(self, mock_agent):
        """Test validation fails for ADX > 100."""
        invalid_indicators = TechnicalIndicators(
            sma_20=95000.0, sma_50=92000.0, adx=150.0, rsi=65.0
        )

        assert mock_agent._validate_indicators(invalid_indicators) is False

    def test_invalid_adx_negative(self, mock_agent):
        """Test validation fails for negative ADX."""
        invalid_indicators = TechnicalIndicators(sma_20=95000.0, sma_50=92000.0, adx=-5.0, rsi=65.0)

        assert mock_agent._validate_indicators(invalid_indicators) is False

    def test_invalid_sma_20_zero(self, mock_agent):
        """Test validation fails for SMA20 = 0."""
        invalid_indicators = TechnicalIndicators(sma_20=0.0, sma_50=92000.0, adx=35.0, rsi=65.0)

        assert mock_agent._validate_indicators(invalid_indicators) is False

    def test_invalid_sma_50_negative(self, mock_agent):
        """Test validation fails for negative SMA50."""
        invalid_indicators = TechnicalIndicators(sma_20=95000.0, sma_50=-1000.0, adx=35.0, rsi=65.0)

        assert mock_agent._validate_indicators(invalid_indicators) is False


class TestExtractTechnicalIndicators:
    """Test the _extract_technical_indicators helper method."""

    def test_extract_valid_indicators(self, mock_agent, btc_indicators):
        """Test extraction of valid technical indicators."""
        medium_signals = MediumLoopSignals(
            technical_indicators={"BTC": btc_indicators},
            funding_basis={"BTC": 0.0001},
            perp_spot_basis={"BTC": 2.0},
            concentration_ratios={"BTC": 0.3},
            drift_from_targets={"BTC": 1.5},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={"BTC": 5.0},
            oi_to_volume_ratio={"BTC": 0.8},
            funding_rate_trend={"BTC": "stable"},
            metadata=None,  # type: ignore
        )

        adx, sma_20, sma_50 = mock_agent._extract_technical_indicators("BTC", medium_signals)

        assert adx == 35.0
        assert sma_20 == 95000.0
        assert sma_50 == 92000.0

    def test_extract_with_none_coin(self, mock_agent):
        """Test extraction with None representative coin."""
        medium_signals = MediumLoopSignals(
            technical_indicators={},
            funding_basis={},
            perp_spot_basis={},
            concentration_ratios={},
            drift_from_targets={},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={},
            oi_to_volume_ratio={},
            funding_rate_trend={},
            metadata=None,  # type: ignore
        )

        adx, sma_20, sma_50 = mock_agent._extract_technical_indicators(None, medium_signals)

        assert adx == 0.0
        assert sma_20 == 0.0
        assert sma_50 == 0.0

    def test_extract_with_missing_coin(self, mock_agent, btc_indicators):
        """Test extraction with coin not in technical_indicators."""
        medium_signals = MediumLoopSignals(
            technical_indicators={"BTC": btc_indicators},
            funding_basis={"BTC": 0.0001},
            perp_spot_basis={"BTC": 2.0},
            concentration_ratios={"BTC": 0.3},
            drift_from_targets={"BTC": 1.5},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={"BTC": 5.0},
            oi_to_volume_ratio={"BTC": 0.8},
            funding_rate_trend={"BTC": "stable"},
            metadata=None,  # type: ignore
        )

        adx, sma_20, sma_50 = mock_agent._extract_technical_indicators("ETH", medium_signals)

        assert adx == 0.0
        assert sma_20 == 0.0
        assert sma_50 == 0.0

    def test_extract_with_invalid_indicators(self, mock_agent):
        """Test extraction with invalid indicators (ADX > 100)."""
        invalid_indicators = TechnicalIndicators(
            sma_20=95000.0, sma_50=92000.0, adx=150.0, rsi=65.0
        )

        medium_signals = MediumLoopSignals(
            technical_indicators={"BTC": invalid_indicators},
            funding_basis={"BTC": 0.0001},
            perp_spot_basis={"BTC": 2.0},
            concentration_ratios={"BTC": 0.3},
            drift_from_targets={"BTC": 1.5},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={"BTC": 5.0},
            oi_to_volume_ratio={"BTC": 0.8},
            funding_rate_trend={"BTC": "stable"},
            metadata=None,  # type: ignore
        )

        adx, sma_20, sma_50 = mock_agent._extract_technical_indicators("BTC", medium_signals)

        # Should fall back to zeros for invalid indicators
        assert adx == 0.0
        assert sma_20 == 0.0
        assert sma_50 == 0.0


class TestCalculateWeightedFundingRate:
    """Test the _calculate_weighted_funding_rate helper method."""

    def test_weighted_funding_rate(self, mock_agent):
        """Test position-weighted funding rate calculation."""
        account_state = EnhancedAccountState(
            portfolio_value=50000.0,
            available_balance=10000.0,
            positions=[
                Position(
                    coin="BTC",
                    size=0.1,
                    entry_price=94000.0,
                    current_price=95000.0,
                    unrealized_pnl=100.0,
                    market_type="perp",
                ),
                Position(
                    coin="ETH",
                    size=10.0,
                    entry_price=3400.0,
                    current_price=3500.0,
                    unrealized_pnl=1000.0,
                    market_type="perp",
                ),
            ],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        medium_signals = MediumLoopSignals(
            technical_indicators={},
            funding_basis={"BTC": 0.0001, "ETH": 0.0002},
            perp_spot_basis={},
            concentration_ratios={},
            drift_from_targets={},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={},
            oi_to_volume_ratio={},
            funding_rate_trend={},
            metadata=None,  # type: ignore
        )

        avg_funding = mock_agent._calculate_weighted_funding_rate(account_state, medium_signals)

        # BTC notional: 0.1 * 95000 = 9500
        # ETH notional: 10 * 3500 = 35000
        # Total: 44500
        # Weighted: (0.0001 * 9500 + 0.0002 * 35000) / 44500
        #         = (0.95 + 7.0) / 44500 = 7.95 / 44500 ≈ 0.0001787
        expected = (0.0001 * 9500 + 0.0002 * 35000) / 44500

        assert abs(avg_funding - expected) < 1e-6

    def test_funding_rate_empty_basis(self, mock_agent):
        """Test returns 0.0 when funding_basis is empty."""
        account_state = EnhancedAccountState(
            portfolio_value=10000.0,
            available_balance=10000.0,
            positions=[],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        medium_signals = MediumLoopSignals(
            technical_indicators={},
            funding_basis={},
            perp_spot_basis={},
            concentration_ratios={},
            drift_from_targets={},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={},
            oi_to_volume_ratio={},
            funding_rate_trend={},
            metadata=None,  # type: ignore
        )

        avg_funding = mock_agent._calculate_weighted_funding_rate(account_state, medium_signals)

        assert avg_funding == 0.0

    def test_funding_rate_no_matching_positions(self, mock_agent):
        """Test returns 0.0 when no positions have funding data."""
        account_state = EnhancedAccountState(
            portfolio_value=10000.0,
            available_balance=5000.0,
            positions=[
                Position(
                    coin="SOL",
                    size=100.0,
                    entry_price=100.0,
                    current_price=110.0,
                    unrealized_pnl=1000.0,
                    market_type="perp",
                )
            ],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        medium_signals = MediumLoopSignals(
            technical_indicators={},
            funding_basis={"BTC": 0.0001, "ETH": 0.0002},  # No SOL
            perp_spot_basis={},
            concentration_ratios={},
            drift_from_targets={},
            realized_vol_1h=0.3,
            realized_vol_24h=0.45,
            trend_score=0.6,
            open_interest_change_24h={},
            oi_to_volume_ratio={},
            funding_rate_trend={},
            metadata=None,  # type: ignore
        )

        avg_funding = mock_agent._calculate_weighted_funding_rate(account_state, medium_signals)

        assert avg_funding == 0.0


class TestCalculateAverageSpreadAndDepth:
    """Test the _calculate_average_spread_and_depth helper method."""

    def test_average_spread_and_depth(self, mock_agent):
        """Test calculation of average spread and order book depth."""
        account_state = EnhancedAccountState(
            portfolio_value=50000.0,
            available_balance=10000.0,
            positions=[],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
            fast_signals=FastLoopSignals(
                spreads={"BTC": 2.5, "ETH": 3.0, "SOL": 4.5},
                slippage_estimates={"BTC": 5.0, "ETH": 6.0},
                short_term_volatility=0.2,
                micro_pnl=100.0,
                partial_fill_rates={"BTC": 0.95, "ETH": 0.92},
                order_book_depth={"BTC": 1000000.0, "ETH": 500000.0, "SOL": 200000.0},
                api_latency_ms=50.0,
                metadata=None,  # type: ignore
            ),
        )

        avg_spread, avg_depth = mock_agent._calculate_average_spread_and_depth(account_state)

        # Average spread: (2.5 + 3.0 + 4.5) / 3 = 10.0 / 3 ≈ 3.333
        expected_spread = (2.5 + 3.0 + 4.5) / 3
        assert abs(avg_spread - expected_spread) < 0.01

        # Average depth: (1000000 + 500000 + 200000) / 3 = 566666.67
        expected_depth = (1000000.0 + 500000.0 + 200000.0) / 3
        assert abs(avg_depth - expected_depth) < 0.01

    def test_no_fast_signals(self, mock_agent):
        """Test returns (0.0, 0.0) when fast_signals is None."""
        account_state = EnhancedAccountState(
            portfolio_value=10000.0,
            available_balance=10000.0,
            positions=[],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
            fast_signals=None,
        )

        avg_spread, avg_depth = mock_agent._calculate_average_spread_and_depth(account_state)

        assert avg_spread == 0.0
        assert avg_depth == 0.0

    def test_empty_spreads_and_depth(self, mock_agent):
        """Test returns (0.0, 0.0) when spreads and depth dicts are empty."""
        account_state = EnhancedAccountState(
            portfolio_value=10000.0,
            available_balance=10000.0,
            positions=[],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
            fast_signals=FastLoopSignals(
                spreads={},
                slippage_estimates={},
                short_term_volatility=0.2,
                micro_pnl=0.0,
                partial_fill_rates={},
                order_book_depth={},
                api_latency_ms=50.0,
                metadata=None,  # type: ignore
            ),
        )

        avg_spread, avg_depth = mock_agent._calculate_average_spread_and_depth(account_state)

        assert avg_spread == 0.0
        assert avg_depth == 0.0


class TestEmergencyPositionReduction:
    """Test the emergency position reduction functionality."""

    @pytest.fixture
    def mock_governed_agent(self):
        """Create a mock governed agent for testing emergency reduction."""
        from unittest.mock import Mock

        from hyperliquid_agent.governed_agent import GovernedAgentConfig

        agent = Mock()
        agent.logger = Mock()
        agent.tick_count = 1
        agent.governance_config = Mock(spec=GovernedAgentConfig)
        agent.governance_config.emergency_reduction_pct = 100.0
        agent.monitor = Mock()
        agent.base_agent = Mock()
        agent.base_agent.executor = Mock()
        agent.executor = agent.base_agent.executor

        # Bind the actual method
        agent._handle_tripwire_action = GovernedTradingAgent._handle_tripwire_action.__get__(
            agent, GovernedTradingAgent
        )

        return agent

    def test_full_liquidation_100_percent(self, mock_governed_agent):
        """Test emergency reduction with 100% liquidation."""
        from hyperliquid_agent.governance.tripwire import TripwireAction
        from hyperliquid_agent.monitor import AccountState

        # Setup account state with positions
        account_state = AccountState(
            portfolio_value=50000.0,
            available_balance=10000.0,
            positions=[
                Position(
                    coin="BTC",
                    size=0.5,
                    entry_price=94000.0,
                    current_price=95000.0,
                    unrealized_pnl=500.0,
                    market_type="perp",
                ),
                Position(
                    coin="ETH",
                    size=10.0,
                    entry_price=3400.0,
                    current_price=3500.0,
                    unrealized_pnl=1000.0,
                    market_type="perp",
                ),
            ],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        mock_governed_agent.monitor.get_current_state.return_value = account_state

        # Mock successful execution
        mock_result = Mock()
        mock_result.success = True
        mock_result.error = None
        mock_governed_agent.base_agent.executor.execute_action.return_value = mock_result

        # Execute emergency reduction
        result = mock_governed_agent._handle_tripwire_action(TripwireAction.CUT_SIZE_TO_FLOOR)

        # Verify result
        assert result is True

        # Verify executor was called twice (once per position)
        assert mock_governed_agent.base_agent.executor.execute_action.call_count == 2

        # Verify the actions
        calls = mock_governed_agent.base_agent.executor.execute_action.call_args_list

        # First call should be for BTC
        btc_action = calls[0][0][0]
        assert btc_action.action_type == "sell"
        assert btc_action.coin == "BTC"
        assert btc_action.size == 0.5  # 100% of 0.5
        assert btc_action.price is None  # Market order
        assert "Emergency risk reduction" in btc_action.reasoning

        # Second call should be for ETH
        eth_action = calls[1][0][0]
        assert eth_action.action_type == "sell"
        assert eth_action.coin == "ETH"
        assert eth_action.size == 10.0  # 100% of 10.0
        assert eth_action.price is None  # Market order

    def test_partial_liquidation_50_percent(self, mock_governed_agent):
        """Test emergency reduction with 50% partial liquidation."""
        from hyperliquid_agent.governance.tripwire import TripwireAction
        from hyperliquid_agent.monitor import AccountState

        # Set to 50% reduction
        mock_governed_agent.governance_config.emergency_reduction_pct = 50.0

        # Setup account state with positions
        account_state = AccountState(
            portfolio_value=50000.0,
            available_balance=10000.0,
            positions=[
                Position(
                    coin="BTC",
                    size=1.0,
                    entry_price=94000.0,
                    current_price=95000.0,
                    unrealized_pnl=1000.0,
                    market_type="perp",
                ),
            ],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        mock_governed_agent.monitor.get_current_state.return_value = account_state

        # Mock successful execution
        mock_result = Mock()
        mock_result.success = True
        mock_result.error = None
        mock_governed_agent.base_agent.executor.execute_action.return_value = mock_result

        # Execute emergency reduction
        result = mock_governed_agent._handle_tripwire_action(TripwireAction.CUT_SIZE_TO_FLOOR)

        # Verify result
        assert result is True

        # Verify the action
        calls = mock_governed_agent.base_agent.executor.execute_action.call_args_list
        assert len(calls) == 1

        btc_action = calls[0][0][0]
        assert btc_action.coin == "BTC"
        assert btc_action.size == 0.5  # 50% of 1.0

    def test_error_handling_individual_position_failure(self, mock_governed_agent):
        """Test that individual position failures don't stop other positions from closing."""
        from hyperliquid_agent.governance.tripwire import TripwireAction
        from hyperliquid_agent.monitor import AccountState

        # Setup account state with multiple positions
        account_state = AccountState(
            portfolio_value=50000.0,
            available_balance=10000.0,
            positions=[
                Position(
                    coin="BTC",
                    size=0.5,
                    entry_price=94000.0,
                    current_price=95000.0,
                    unrealized_pnl=500.0,
                    market_type="perp",
                ),
                Position(
                    coin="ETH",
                    size=10.0,
                    entry_price=3400.0,
                    current_price=3500.0,
                    unrealized_pnl=1000.0,
                    market_type="perp",
                ),
                Position(
                    coin="SOL",
                    size=100.0,
                    entry_price=100.0,
                    current_price=110.0,
                    unrealized_pnl=1000.0,
                    market_type="perp",
                ),
            ],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        mock_governed_agent.monitor.get_current_state.return_value = account_state

        # Mock execution: first succeeds, second fails, third succeeds
        mock_result_success = Mock()
        mock_result_success.success = True
        mock_result_success.error = None

        mock_result_failure = Mock()
        mock_result_failure.success = False
        mock_result_failure.error = "Network timeout"

        mock_governed_agent.base_agent.executor.execute_action.side_effect = [
            mock_result_success,
            mock_result_failure,
            mock_result_success,
        ]

        # Execute emergency reduction
        result = mock_governed_agent._handle_tripwire_action(TripwireAction.CUT_SIZE_TO_FLOOR)

        # Should still return True because at least one succeeded
        assert result is True

        # Verify all three positions were attempted
        assert mock_governed_agent.base_agent.executor.execute_action.call_count == 3

        # Verify critical logging was called for each position
        assert mock_governed_agent.logger.critical.call_count >= 4  # 3 individual + 1 summary

    def test_error_handling_exception_during_execution(self, mock_governed_agent):
        """Test that exceptions during execution are caught and logged."""
        from hyperliquid_agent.governance.tripwire import TripwireAction
        from hyperliquid_agent.monitor import AccountState

        # Setup account state
        account_state = AccountState(
            portfolio_value=50000.0,
            available_balance=10000.0,
            positions=[
                Position(
                    coin="BTC",
                    size=0.5,
                    entry_price=94000.0,
                    current_price=95000.0,
                    unrealized_pnl=500.0,
                    market_type="perp",
                ),
            ],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        mock_governed_agent.monitor.get_current_state.return_value = account_state

        # Mock execution to raise exception
        mock_governed_agent.base_agent.executor.execute_action.side_effect = Exception(
            "Connection error"
        )

        # Execute emergency reduction
        result = mock_governed_agent._handle_tripwire_action(TripwireAction.CUT_SIZE_TO_FLOOR)

        # Should return False because no positions were successfully closed
        assert result is False

        # Verify exception was logged
        assert mock_governed_agent.logger.critical.call_count >= 2  # Exception + summary

    def test_logging_and_audit_trail(self, mock_governed_agent):
        """Test that comprehensive logging is performed for audit trail."""
        from hyperliquid_agent.governance.tripwire import TripwireAction
        from hyperliquid_agent.monitor import AccountState

        # Setup account state
        account_state = AccountState(
            portfolio_value=50000.0,
            available_balance=10000.0,
            positions=[
                Position(
                    coin="BTC",
                    size=0.5,
                    entry_price=94000.0,
                    current_price=95000.0,
                    unrealized_pnl=500.0,
                    market_type="perp",
                ),
            ],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        mock_governed_agent.monitor.get_current_state.return_value = account_state

        # Mock successful execution
        mock_result = Mock()
        mock_result.success = True
        mock_result.error = None
        mock_governed_agent.base_agent.executor.execute_action.return_value = mock_result

        # Execute emergency reduction
        mock_governed_agent._handle_tripwire_action(TripwireAction.CUT_SIZE_TO_FLOOR)

        # Verify logging calls
        critical_calls = mock_governed_agent.logger.critical.call_args_list

        # Should have at least 3 critical logs:
        # 1. "Executing emergency position reduction"
        # 2. "Emergency exit: BTC - SUCCESS"
        # 3. "Emergency position reduction complete: 1/1 successful"
        assert len(critical_calls) >= 3

        # Verify first log contains reduction percentage
        first_call_msg = critical_calls[0][0][0]
        assert "Executing emergency position reduction" in first_call_msg

        # Verify individual position log contains coin and success status
        second_call_msg = critical_calls[1][0][0]
        assert "BTC" in second_call_msg
        assert "SUCCESS" in second_call_msg

        # Verify summary log
        summary_call_msg = critical_calls[2][0][0]
        assert "Emergency position reduction complete" in summary_call_msg
        assert "1/1 successful" in summary_call_msg

    def test_no_positions_to_close(self, mock_governed_agent):
        """Test behavior when there are no positions to close."""
        from hyperliquid_agent.governance.tripwire import TripwireAction
        from hyperliquid_agent.monitor import AccountState

        # Setup account state with no positions
        account_state = AccountState(
            portfolio_value=10000.0,
            available_balance=10000.0,
            positions=[],
            timestamp=datetime.now().timestamp(),
            spot_balances={},
            is_stale=False,
        )

        mock_governed_agent.monitor.get_current_state.return_value = account_state

        # Execute emergency reduction
        result = mock_governed_agent._handle_tripwire_action(TripwireAction.CUT_SIZE_TO_FLOOR)

        # Should return False because no positions were closed
        assert result is False

        # Verify executor was never called
        assert mock_governed_agent.base_agent.executor.execute_action.call_count == 0

    def test_account_state_retrieval_failure(self, mock_governed_agent):
        """Test handling of account state retrieval failure."""
        from hyperliquid_agent.governance.tripwire import TripwireAction

        # Mock account state retrieval to fail
        mock_governed_agent.monitor.get_current_state.side_effect = Exception(
            "API connection failed"
        )

        # Execute emergency reduction
        result = mock_governed_agent._handle_tripwire_action(TripwireAction.CUT_SIZE_TO_FLOOR)

        # Should return False
        assert result is False

        # Verify critical error was logged
        assert mock_governed_agent.logger.critical.call_count >= 1

    def test_unhandled_tripwire_action(self, mock_governed_agent):
        """Test that unhandled tripwire actions are logged and return False."""
        from hyperliquid_agent.governance.tripwire import TripwireAction

        # Try to handle a different action
        result = mock_governed_agent._handle_tripwire_action(TripwireAction.FREEZE_NEW_RISK)

        # Should return False
        assert result is False

        # Verify warning was logged
        assert mock_governed_agent.logger.warning.call_count == 1


class TestAsyncLoopExecution:
    """Test async loop execution functionality."""

    @pytest.fixture
    def mock_async_agent(self):
        """Create a mock governed agent for testing async execution."""
        from unittest.mock import Mock

        from hyperliquid_agent.governed_agent import GovernedAgentConfig

        agent = Mock()
        agent.logger = Mock()
        agent.tick_count = 0
        agent.governance_config = Mock(spec=GovernedAgentConfig)
        agent.governance_config.fast_loop_interval_seconds = 10
        agent.governance_config.medium_loop_interval_minutes = 5
        agent.governance_config.slow_loop_interval_hours = 1
        agent.last_medium_loop = None
        agent.last_slow_loop = None

        # Mock the loop execution methods
        agent._execute_slow_loop = Mock()
        agent._execute_medium_loop = Mock()
        agent._execute_fast_loop = Mock()

        # Bind the async wrapper methods
        agent._execute_slow_loop_async = GovernedTradingAgent._execute_slow_loop_async.__get__(
            agent, GovernedTradingAgent
        )
        agent._execute_medium_loop_async = GovernedTradingAgent._execute_medium_loop_async.__get__(
            agent, GovernedTradingAgent
        )
        agent._execute_fast_loop_async = GovernedTradingAgent._execute_fast_loop_async.__get__(
            agent, GovernedTradingAgent
        )

        # Bind the should_run methods
        agent._should_run_medium_loop = GovernedTradingAgent._should_run_medium_loop.__get__(
            agent, GovernedTradingAgent
        )
        agent._should_run_slow_loop = GovernedTradingAgent._should_run_slow_loop.__get__(
            agent, GovernedTradingAgent
        )

        return agent

    @pytest.mark.asyncio
    async def test_concurrent_loop_execution(self, mock_async_agent):
        """Test that multiple loops execute concurrently."""
        import asyncio

        current_time = datetime.now()

        # All loops should run on first tick
        mock_async_agent.last_medium_loop = None
        mock_async_agent.last_slow_loop = None

        # Create tasks for concurrent execution
        tasks = [
            mock_async_agent._execute_slow_loop_async(current_time),
            mock_async_agent._execute_medium_loop_async(current_time),
            mock_async_agent._execute_fast_loop_async(current_time),
        ]

        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all loops executed
        assert mock_async_agent._execute_slow_loop.call_count == 1
        assert mock_async_agent._execute_medium_loop.call_count == 1
        assert mock_async_agent._execute_fast_loop.call_count == 1

        # Verify no exceptions
        for result in results:
            assert not isinstance(result, Exception)

    @pytest.mark.asyncio
    async def test_exception_isolation(self, mock_async_agent):
        """Test that one loop failure doesn't stop other loops."""
        import asyncio

        current_time = datetime.now()

        # Make medium loop raise an exception
        mock_async_agent._execute_medium_loop.side_effect = Exception("Medium loop error")

        # Create tasks for concurrent execution
        tasks = [
            mock_async_agent._execute_slow_loop_async(current_time),
            mock_async_agent._execute_medium_loop_async(current_time),
            mock_async_agent._execute_fast_loop_async(current_time),
        ]

        # Execute concurrently with return_exceptions=True
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify slow and fast loops still executed
        assert mock_async_agent._execute_slow_loop.call_count == 1
        assert mock_async_agent._execute_fast_loop.call_count == 1

        # Verify medium loop was attempted
        assert mock_async_agent._execute_medium_loop.call_count == 1

        # Verify one result is an exception
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 1
        assert "Medium loop error" in str(exceptions[0])

    @pytest.mark.asyncio
    async def test_timing_and_scheduling(self, mock_async_agent):
        """Test that loop scheduling logic works correctly."""
        from datetime import timedelta

        current_time = datetime.now()

        # Set last execution times
        mock_async_agent.last_medium_loop = current_time - timedelta(minutes=6)
        mock_async_agent.last_slow_loop = current_time - timedelta(hours=2)

        # Check which loops should run
        should_run_medium = mock_async_agent._should_run_medium_loop(current_time)
        should_run_slow = mock_async_agent._should_run_slow_loop(current_time)

        # Both should run (elapsed time exceeds intervals)
        assert should_run_medium is True
        assert should_run_slow is True

        # Update last execution times
        mock_async_agent.last_medium_loop = current_time
        mock_async_agent.last_slow_loop = current_time

        # Check again immediately
        should_run_medium = mock_async_agent._should_run_medium_loop(current_time)
        should_run_slow = mock_async_agent._should_run_slow_loop(current_time)

        # Neither should run (no time elapsed)
        assert should_run_medium is False
        assert should_run_slow is False

    @pytest.mark.asyncio
    async def test_fast_loop_not_blocked_by_slow_loop(self, mock_async_agent):
        """Test that fast loop executes even when slow loop is running."""
        import asyncio
        import time

        current_time = datetime.now()

        # Make slow loop take a long time
        def slow_execution(*args):
            time.sleep(0.1)  # Simulate slow operation

        # Replace the slow loop with our delayed version
        mock_async_agent._execute_slow_loop = Mock(side_effect=slow_execution)

        # Create tasks for concurrent execution
        tasks = [
            mock_async_agent._execute_slow_loop_async(current_time),
            mock_async_agent._execute_fast_loop_async(current_time),
        ]

        # Execute concurrently
        start_time = asyncio.get_event_loop().time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = asyncio.get_event_loop().time()

        # Verify both loops executed
        assert mock_async_agent._execute_slow_loop.call_count == 1
        assert mock_async_agent._execute_fast_loop.call_count == 1

        # Verify execution was concurrent (total time should be ~0.1s, not 0.2s)
        total_time = end_time - start_time
        assert total_time < 0.15  # Allow some overhead

        # Verify no exceptions
        for result in results:
            assert not isinstance(result, Exception)

    @pytest.mark.asyncio
    async def test_multiple_exceptions_handled(self, mock_async_agent):
        """Test that multiple loop failures are all caught and logged."""
        import asyncio

        current_time = datetime.now()

        # Make all loops raise exceptions
        mock_async_agent._execute_slow_loop.side_effect = Exception("Slow loop error")
        mock_async_agent._execute_medium_loop.side_effect = Exception("Medium loop error")
        mock_async_agent._execute_fast_loop.side_effect = Exception("Fast loop error")

        # Create tasks for concurrent execution
        tasks = [
            mock_async_agent._execute_slow_loop_async(current_time),
            mock_async_agent._execute_medium_loop_async(current_time),
            mock_async_agent._execute_fast_loop_async(current_time),
        ]

        # Execute concurrently with return_exceptions=True
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all loops were attempted
        assert mock_async_agent._execute_slow_loop.call_count == 1
        assert mock_async_agent._execute_medium_loop.call_count == 1
        assert mock_async_agent._execute_fast_loop.call_count == 1

        # Verify all results are exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 3

        # Verify exception messages
        exception_messages = [str(e) for e in exceptions]
        assert "Slow loop error" in exception_messages
        assert "Medium loop error" in exception_messages
        assert "Fast loop error" in exception_messages

    @pytest.mark.asyncio
    async def test_async_wrapper_methods(self, mock_async_agent):
        """Test that async wrapper methods correctly call sync methods."""
        current_time = datetime.now()

        # Test slow loop wrapper
        await mock_async_agent._execute_slow_loop_async(current_time)
        assert mock_async_agent._execute_slow_loop.call_count == 1
        mock_async_agent._execute_slow_loop.assert_called_with(current_time)

        # Test medium loop wrapper
        await mock_async_agent._execute_medium_loop_async(current_time)
        assert mock_async_agent._execute_medium_loop.call_count == 1
        mock_async_agent._execute_medium_loop.assert_called_with(current_time)

        # Test fast loop wrapper
        await mock_async_agent._execute_fast_loop_async(current_time)
        assert mock_async_agent._execute_fast_loop.call_count == 1
        mock_async_agent._execute_fast_loop.assert_called_with(current_time)
