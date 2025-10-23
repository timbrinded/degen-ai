"""Unit tests for Plan Scorekeeper module."""

from datetime import datetime, timedelta

import pytest

from hyperliquid_agent.governance.plan_card import (
    ChangeCostModel,
    ExitRules,
    RiskBudget,
    StrategyPlanCard,
    TargetAllocation,
)
from hyperliquid_agent.governance.scorekeeper import (
    PlanMetrics,
    PlanScorekeeper,
    ShadowPortfolio,
)
from hyperliquid_agent.monitor import AccountState, Position


@pytest.fixture
def sample_plan():
    """Create a sample strategy plan card."""
    return StrategyPlanCard(
        plan_id="test_plan_001",
        strategy_name="funding-harvest",
        strategy_version="1.0",
        created_at=datetime.now(),
        objective="Harvest funding rates",
        target_holding_period_hours=24,
        time_horizon="hours",
        key_thesis="Positive funding environment",
        target_allocations=[
            TargetAllocation(coin="BTC", target_pct=50.0, market_type="perp", leverage=1.5),
            TargetAllocation(coin="ETH", target_pct=30.0, market_type="perp", leverage=1.5),
        ],
        allowed_leverage_range=(1.0, 2.0),
        risk_budget=RiskBudget(
            max_position_pct={"BTC": 60.0, "ETH": 40.0},
            max_leverage=2.0,
            max_adverse_excursion_pct=5.0,
            plan_max_drawdown_pct=10.0,
            per_trade_risk_pct=2.0,
        ),
        exit_rules=ExitRules(
            profit_target_pct=10.0,
            stop_loss_pct=5.0,
            time_based_review_hours=24,
            invalidation_triggers=[],
        ),
        change_cost=ChangeCostModel(
            estimated_fees_bps=10.0,
            estimated_slippage_bps=5.0,
            estimated_funding_change_bps=2.0,
            opportunity_cost_bps=3.0,
        ),
        expected_edge_bps=100.0,
        kpis_to_track=["funding_pnl"],
        minimum_dwell_minutes=120,
        compatible_regimes=["carry-friendly"],
        avoid_regimes=["event-risk"],
        status="active",
    )


@pytest.fixture
def account_state_with_positions():
    """Create an account state with positions."""
    return AccountState(
        portfolio_value=10500.0,
        available_balance=5000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.1,
                entry_price=50000.0,
                current_price=51000.0,
                unrealized_pnl=100.0,
                market_type="perp",
            ),
            Position(
                coin="ETH",
                size=1.0,
                entry_price=3000.0,
                current_price=3100.0,
                unrealized_pnl=100.0,
                market_type="perp",
            ),
        ],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )


def test_scorekeeper_initialization():
    """Test PlanScorekeeper initializes correctly."""
    scorekeeper = PlanScorekeeper()

    assert scorekeeper.active_metrics is None
    assert scorekeeper.completed_plans == []
    assert scorekeeper.shadow_portfolios == []


def test_start_tracking_plan(sample_plan):
    """Test starting plan tracking."""
    scorekeeper = PlanScorekeeper()
    initial_value = 10000.0

    scorekeeper.start_tracking_plan(sample_plan, initial_value)

    assert scorekeeper.active_metrics is not None
    assert scorekeeper.active_metrics.plan_id == sample_plan.plan_id
    assert scorekeeper.active_metrics.initial_portfolio_value == initial_value
    assert scorekeeper.active_metrics.peak_portfolio_value == initial_value
    assert scorekeeper.active_metrics.end_time is None


def test_update_metrics_calculates_pnl(sample_plan, account_state_with_positions):
    """Test metrics update calculates PnL correctly."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    scorekeeper.update_metrics(account_state_with_positions, sample_plan)

    assert scorekeeper.active_metrics.total_pnl == 500.0  # 10500 - 10000


def test_update_metrics_tracks_peak_value(sample_plan):
    """Test metrics update tracks peak portfolio value."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # First update with higher value
    account_state1 = AccountState(
        portfolio_value=11000.0,
        available_balance=5000.0,
        positions=[],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )
    scorekeeper.update_metrics(account_state1, sample_plan)
    assert scorekeeper.active_metrics.peak_portfolio_value == 11000.0

    # Second update with lower value (peak should remain)
    account_state2 = AccountState(
        portfolio_value=10500.0,
        available_balance=5000.0,
        positions=[],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )
    scorekeeper.update_metrics(account_state2, sample_plan)
    assert scorekeeper.active_metrics.peak_portfolio_value == 11000.0


def test_update_metrics_calculates_max_drawdown(sample_plan):
    """Test metrics update calculates max drawdown."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # Update to peak
    account_state1 = AccountState(
        portfolio_value=12000.0,
        available_balance=6000.0,
        positions=[],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )
    scorekeeper.update_metrics(account_state1, sample_plan)

    # Update with drawdown
    account_state2 = AccountState(
        portfolio_value=10800.0,  # 10% drawdown from peak
        available_balance=5400.0,
        positions=[],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )
    scorekeeper.update_metrics(account_state2, sample_plan)

    assert scorekeeper.active_metrics.max_drawdown_pct == pytest.approx(10.0)


def test_update_metrics_calculates_pnl_per_unit_risk(sample_plan):
    """Test metrics update calculates PnL per unit risk."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # Create scenario with drawdown
    account_state1 = AccountState(
        portfolio_value=11000.0,
        available_balance=5500.0,
        positions=[],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )
    scorekeeper.update_metrics(account_state1, sample_plan)

    account_state2 = AccountState(
        portfolio_value=10500.0,  # 4.5% drawdown from peak
        available_balance=5250.0,
        positions=[],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )
    scorekeeper.update_metrics(account_state2, sample_plan)

    # PnL per unit risk = total_pnl / max_drawdown_pct
    # 500 / 4.5 ≈ 111.11
    assert scorekeeper.active_metrics.pnl_per_unit_risk == pytest.approx(111.11, rel=0.01)


def test_update_metrics_calculates_drift_from_targets(sample_plan, account_state_with_positions):
    """Test metrics update calculates drift from target allocations."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    scorekeeper.update_metrics(account_state_with_positions, sample_plan)

    # BTC target: 50%, actual: ~48.6% (5100/10500)
    # ETH target: 30%, actual: ~29.5% (3100/10500)
    # Average drift should be small
    assert scorekeeper.active_metrics.avg_drift_from_targets_pct < 5.0


def test_finalize_plan_generates_summary(sample_plan):
    """Test plan finalization generates post-mortem summary."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # Simulate some activity
    scorekeeper.active_metrics.total_pnl = 500.0
    scorekeeper.active_metrics.peak_portfolio_value = 10800.0
    scorekeeper.active_metrics.max_drawdown_pct = 5.0
    scorekeeper.active_metrics.total_trades = 10
    scorekeeper.active_metrics.winning_trades = 7

    summary = scorekeeper.finalize_plan(10500.0)

    assert "test_plan_001" in summary
    assert "500.00" in summary  # PnL
    assert "5.00%" in summary  # Max drawdown
    assert "10" in summary  # Total trades
    assert scorekeeper.active_metrics is None  # Reset after finalization
    assert len(scorekeeper.completed_plans) == 1


def test_finalize_plan_calculates_hit_rate(sample_plan):
    """Test plan finalization calculates hit rate."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    scorekeeper.active_metrics.total_trades = 10
    scorekeeper.active_metrics.winning_trades = 7

    scorekeeper.finalize_plan(10500.0)

    completed_plan = scorekeeper.completed_plans[0]
    assert completed_plan.hit_rate == pytest.approx(0.7)


def test_finalize_plan_no_active_plan():
    """Test finalize_plan handles no active plan gracefully."""
    scorekeeper = PlanScorekeeper()

    summary = scorekeeper.finalize_plan(10000.0)

    assert "No active plan" in summary
    assert len(scorekeeper.completed_plans) == 0


def test_record_trade_updates_metrics(sample_plan):
    """Test recording trades updates metrics."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # Record winning trade
    scorekeeper.record_trade(is_winning=True, slippage_bps=5.0)

    assert scorekeeper.active_metrics.total_trades == 1
    assert scorekeeper.active_metrics.winning_trades == 1
    assert scorekeeper.active_metrics.avg_slippage_bps == 5.0

    # Record losing trade
    scorekeeper.record_trade(is_winning=False, slippage_bps=7.0)

    assert scorekeeper.active_metrics.total_trades == 2
    assert scorekeeper.active_metrics.winning_trades == 1
    assert scorekeeper.active_metrics.avg_slippage_bps == pytest.approx(6.0)


def test_record_trade_no_active_plan():
    """Test recording trade with no active plan does nothing."""
    scorekeeper = PlanScorekeeper()

    # Should not raise error
    scorekeeper.record_trade(is_winning=True, slippage_bps=5.0)


def test_record_rebalance(sample_plan):
    """Test recording rebalance events."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    assert scorekeeper.active_metrics.rebalance_count == 0

    scorekeeper.record_rebalance()
    assert scorekeeper.active_metrics.rebalance_count == 1

    scorekeeper.record_rebalance()
    assert scorekeeper.active_metrics.rebalance_count == 2


def test_record_rebalance_no_active_plan():
    """Test recording rebalance with no active plan does nothing."""
    scorekeeper = PlanScorekeeper()

    # Should not raise error
    scorekeeper.record_rebalance()


def test_add_shadow_portfolio():
    """Test adding shadow portfolio."""
    scorekeeper = PlanScorekeeper()

    initial_positions = {"BTC": 0.1, "ETH": 1.0}
    scorekeeper.add_shadow_portfolio("trend-following", initial_positions, 10000.0)

    assert len(scorekeeper.shadow_portfolios) == 1
    shadow = scorekeeper.shadow_portfolios[0]
    assert shadow.strategy_name == "trend-following"
    assert shadow.paper_positions == initial_positions
    assert shadow.initial_value == 10000.0
    assert shadow.paper_portfolio_value == 10000.0


def test_update_shadow_portfolios():
    """Test updating shadow portfolio values."""
    scorekeeper = PlanScorekeeper()

    # Add shadow portfolio
    initial_positions = {"BTC": 0.1, "ETH": 1.0}
    scorekeeper.add_shadow_portfolio("trend-following", initial_positions, 10000.0)

    # Create account state with updated prices
    account_state = AccountState(
        portfolio_value=10500.0,
        available_balance=5000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.1,
                entry_price=50000.0,
                current_price=51000.0,
                unrealized_pnl=100.0,
                market_type="perp",
            ),
            Position(
                coin="ETH",
                size=1.0,
                entry_price=3000.0,
                current_price=3100.0,
                unrealized_pnl=100.0,
                market_type="perp",
            ),
        ],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )

    scorekeeper.update_shadow_portfolios(account_state)

    shadow = scorekeeper.shadow_portfolios[0]
    # BTC: 0.1 * 51000 = 5100
    # ETH: 1.0 * 3100 = 3100
    # Total: 8200
    assert shadow.paper_portfolio_value == pytest.approx(8200.0)
    assert shadow.paper_pnl == pytest.approx(-1800.0)  # 8200 - 10000


def test_estimate_opportunity_cost_no_shadows(sample_plan):
    """Test opportunity cost estimation with no shadow portfolios."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    opportunity_cost = scorekeeper.estimate_opportunity_cost()

    assert opportunity_cost == 0.0


def test_estimate_opportunity_cost_with_shadows(sample_plan):
    """Test opportunity cost estimation with shadow portfolios."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # Active plan has 500 PnL
    scorekeeper.active_metrics.total_pnl = 500.0

    # Add shadow portfolios with different performance
    shadow1 = ShadowPortfolio(
        strategy_name="strategy1",
        paper_positions={},
        paper_portfolio_value=10300.0,
        paper_pnl=300.0,
        initial_value=10000.0,
    )
    shadow2 = ShadowPortfolio(
        strategy_name="strategy2",
        paper_positions={},
        paper_portfolio_value=10800.0,
        paper_pnl=800.0,  # Best performing
        initial_value=10000.0,
    )
    scorekeeper.shadow_portfolios = [shadow1, shadow2]

    opportunity_cost = scorekeeper.estimate_opportunity_cost()

    # Best shadow (800) - active (500) = 300
    # 300 / 10000 * 10000 = 300 bps
    assert opportunity_cost == pytest.approx(300.0)


def test_get_active_plan_summary_no_plan():
    """Test getting summary with no active plan."""
    scorekeeper = PlanScorekeeper()

    summary = scorekeeper.get_active_plan_summary()

    assert "No active plan" in summary


def test_get_active_plan_summary_with_plan(sample_plan):
    """Test getting summary of active plan."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # Update some metrics
    scorekeeper.active_metrics.total_pnl = 500.0
    scorekeeper.active_metrics.max_drawdown_pct = 3.5
    scorekeeper.active_metrics.total_trades = 5
    scorekeeper.active_metrics.winning_trades = 3

    summary = scorekeeper.get_active_plan_summary()

    assert "test_plan_001" in summary
    assert "500.00" in summary
    assert "3.50%" in summary
    assert "5" in summary


def test_plan_metrics_structure():
    """Test PlanMetrics data structure."""
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=24)

    metrics = PlanMetrics(
        plan_id="test_plan",
        start_time=start_time,
        end_time=end_time,
        total_pnl=500.0,
        total_risk_taken=100.0,
        pnl_per_unit_risk=5.0,
        total_trades=10,
        winning_trades=7,
        hit_rate=0.7,
        avg_slippage_bps=5.5,
        avg_drift_from_targets_pct=2.0,
        rebalance_count=2,
        initial_portfolio_value=10000.0,
        peak_portfolio_value=10800.0,
        max_drawdown_pct=5.0,
    )

    assert metrics.plan_id == "test_plan"
    assert metrics.start_time == start_time
    assert metrics.end_time == end_time
    assert metrics.total_pnl == 500.0
    assert metrics.hit_rate == 0.7


def test_shadow_portfolio_structure():
    """Test ShadowPortfolio data structure."""
    shadow = ShadowPortfolio(
        strategy_name="test_strategy",
        paper_positions={"BTC": 0.1, "ETH": 1.0},
        paper_portfolio_value=10500.0,
        paper_pnl=500.0,
        initial_value=10000.0,
    )

    assert shadow.strategy_name == "test_strategy"
    assert shadow.paper_positions == {"BTC": 0.1, "ETH": 1.0}
    assert shadow.paper_portfolio_value == 10500.0
    assert shadow.paper_pnl == 500.0
    assert shadow.initial_value == 10000.0


def test_multiple_plans_tracking(sample_plan):
    """Test tracking multiple plans sequentially."""
    scorekeeper = PlanScorekeeper()

    # Track first plan
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)
    scorekeeper.active_metrics.total_pnl = 500.0
    scorekeeper.finalize_plan(10500.0)

    # Track second plan
    sample_plan.plan_id = "test_plan_002"
    scorekeeper.start_tracking_plan(sample_plan, 10500.0)
    scorekeeper.active_metrics.total_pnl = 300.0
    scorekeeper.finalize_plan(10800.0)

    # Should have two completed plans
    assert len(scorekeeper.completed_plans) == 2
    assert scorekeeper.completed_plans[0].plan_id == "test_plan_001"
    assert scorekeeper.completed_plans[1].plan_id == "test_plan_002"


def test_avg_slippage_calculation_incremental(sample_plan):
    """Test average slippage is calculated incrementally."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # Record trades with different slippage
    scorekeeper.record_trade(is_winning=True, slippage_bps=5.0)
    assert scorekeeper.active_metrics.avg_slippage_bps == 5.0

    scorekeeper.record_trade(is_winning=True, slippage_bps=7.0)
    assert scorekeeper.active_metrics.avg_slippage_bps == pytest.approx(6.0)

    scorekeeper.record_trade(is_winning=False, slippage_bps=9.0)
    assert scorekeeper.active_metrics.avg_slippage_bps == pytest.approx(7.0)


def test_drift_calculation_with_missing_positions(sample_plan):
    """Test drift calculation when positions don't match targets."""
    scorekeeper = PlanScorekeeper()
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # Account state missing ETH position (target is 30%)
    account_state = AccountState(
        portfolio_value=10000.0,
        available_balance=5000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.1,
                entry_price=50000.0,
                current_price=50000.0,
                unrealized_pnl=0.0,
                market_type="perp",
            ),
        ],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )

    scorekeeper.update_metrics(account_state, sample_plan)

    # Should calculate drift for missing position (30% target, 0% actual = 30% drift)
    assert scorekeeper.active_metrics.avg_drift_from_targets_pct > 0.0
