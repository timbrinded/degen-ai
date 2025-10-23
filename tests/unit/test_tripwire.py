"""Unit tests for Tripwire Service module."""

from datetime import datetime

import pytest

from hyperliquid_agent.governance.plan_card import (
    ChangeCostModel,
    ExitRules,
    RiskBudget,
    StrategyPlanCard,
    TargetAllocation,
)
from hyperliquid_agent.governance.tripwire import (
    TripwireAction,
    TripwireConfig,
    TripwireEvent,
    TripwireService,
)
from hyperliquid_agent.monitor import AccountState, Position


@pytest.fixture
def tripwire_config():
    """Create a test tripwire configuration."""
    return TripwireConfig(
        min_margin_ratio=0.15,
        liquidation_proximity_threshold=0.25,
        daily_loss_limit_pct=5.0,
        check_invalidation_triggers=True,
        max_data_staleness_seconds=300,
        max_api_failure_count=3,
    )


@pytest.fixture
def healthy_account_state():
    """Create a healthy account state."""
    return AccountState(
        portfolio_value=10000.0,
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
        ],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )


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
        ],
        allowed_leverage_range=(1.0, 2.0),
        risk_budget=RiskBudget(
            max_position_pct={"BTC": 60.0},
            max_leverage=2.0,
            max_adverse_excursion_pct=5.0,
            plan_max_drawdown_pct=10.0,
            per_trade_risk_pct=2.0,
        ),
        exit_rules=ExitRules(
            profit_target_pct=10.0,
            stop_loss_pct=5.0,
            time_based_review_hours=24,
            invalidation_triggers=["funding rate drops below 0.005%"],
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
        activated_at=datetime.now(),
    )


def test_tripwire_service_initialization(tripwire_config):
    """Test TripwireService initializes correctly."""
    service = TripwireService(tripwire_config)

    assert service.config == tripwire_config
    assert service.api_failure_count == 0
    assert service.daily_start_portfolio_value is None
    assert service.daily_loss_pct == 0.0


def test_check_account_safety_healthy_account(tripwire_config, healthy_account_state):
    """Test no tripwires fire for healthy account."""
    service = TripwireService(tripwire_config)

    events = service._check_account_safety(healthy_account_state)

    assert len(events) == 0


def test_check_account_safety_daily_loss_limit_exceeded(tripwire_config):
    """Test daily loss limit tripwire fires."""
    service = TripwireService(tripwire_config)

    # Set initial portfolio value
    service.daily_start_portfolio_value = 10000.0

    # Create account state with 6% loss (exceeds 5% limit)
    account_state = AccountState(
        portfolio_value=9400.0,  # 6% loss
        available_balance=4000.0,
        positions=[],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )

    events = service._check_account_safety(account_state)

    assert len(events) == 1
    event = events[0]
    assert event.severity == "critical"
    assert event.category == "account_safety"
    assert event.trigger == "daily_loss_limit"
    assert event.action == TripwireAction.CUT_SIZE_TO_FLOOR
    assert event.details["loss_pct"] >= 5.0


def test_check_account_safety_low_margin_ratio(tripwire_config):
    """Test low margin ratio tripwire fires."""
    service = TripwireService(tripwire_config)

    # Create account state with low margin ratio
    account_state = AccountState(
        portfolio_value=10000.0,
        available_balance=500.0,  # Very low available balance
        positions=[
            Position(
                coin="BTC",
                size=0.2,
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

    events = service._check_account_safety(account_state)

    # Should fire low margin ratio tripwire
    margin_events = [e for e in events if e.trigger == "low_margin_ratio"]
    assert len(margin_events) == 1
    event = margin_events[0]
    assert event.severity == "critical"
    assert event.action == TripwireAction.CUT_SIZE_TO_FLOOR


def test_check_account_safety_liquidation_proximity(tripwire_config):
    """Test liquidation proximity tripwire fires."""
    service = TripwireService(tripwire_config)

    # Create account state with large unrealized losses (>25% of portfolio)
    account_state = AccountState(
        portfolio_value=10000.0,
        available_balance=5000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.2,
                entry_price=50000.0,
                current_price=45000.0,  # 10% loss
                unrealized_pnl=-1000.0,
                market_type="perp",
            ),
            Position(
                coin="ETH",
                size=2.0,
                entry_price=3000.0,
                current_price=2400.0,  # 20% loss
                unrealized_pnl=-1200.0,
                market_type="perp",
            ),
            Position(
                coin="SOL",
                size=10.0,
                entry_price=100.0,
                current_price=90.0,  # 10% loss
                unrealized_pnl=-100.0,
                market_type="perp",
            ),
        ],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )

    events = service._check_account_safety(account_state)

    # Should fire liquidation proximity tripwire (total loss -2300 / 10000 = 23% < 25% threshold)
    # Actually, let's increase losses to exceed 25%
    account_state.positions[2].unrealized_pnl = -300.0  # Total now -2500 = 25%

    events = service._check_account_safety(account_state)

    liquidation_events = [e for e in events if e.trigger == "liquidation_proximity"]
    assert len(liquidation_events) == 1
    event = liquidation_events[0]
    assert event.severity == "critical"
    assert event.action == TripwireAction.ESCALATE_TO_SLOW_LOOP


def test_check_plan_invalidation_no_triggers(tripwire_config, healthy_account_state, sample_plan):
    """Test no invalidation when triggers not fired."""
    service = TripwireService(tripwire_config)

    events = service._check_plan_invalidation(healthy_account_state, sample_plan)

    assert len(events) == 0


def test_check_plan_invalidation_trigger_fired(tripwire_config, sample_plan):
    """Test plan invalidation when trigger condition met."""
    service = TripwireService(tripwire_config)

    # Create plan with position size trigger
    sample_plan.exit_rules.invalidation_triggers = ["position size exceeds 60% of portfolio"]

    # Create account state with large position
    account_state = AccountState(
        portfolio_value=10000.0,
        available_balance=3000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.15,
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

    events = service._check_plan_invalidation(account_state, sample_plan)

    # Should fire invalidation trigger (position is 75% of portfolio)
    assert len(events) == 1
    event = events[0]
    assert event.severity == "warning"
    assert event.category == "plan_invalidation"
    assert event.action == TripwireAction.INVALIDATE_PLAN


def test_check_operational_health_stale_data(tripwire_config):
    """Test stale data tripwire fires."""
    service = TripwireService(tripwire_config)

    # Create account state with stale data
    account_state = AccountState(
        portfolio_value=10000.0,
        available_balance=5000.0,
        positions=[],
        spot_balances={},
        timestamp=datetime.now().timestamp() - 400,  # 400 seconds old
        is_stale=True,
    )

    events = service._check_operational_health(account_state)

    assert len(events) == 1
    event = events[0]
    assert event.severity == "warning"
    assert event.category == "operational"
    assert event.trigger == "stale_data"
    assert event.action == TripwireAction.FREEZE_NEW_RISK


def test_check_operational_health_api_failures(tripwire_config, healthy_account_state):
    """Test API failure threshold tripwire fires."""
    service = TripwireService(tripwire_config)

    # Record multiple API failures
    service.api_failure_count = 3

    events = service._check_operational_health(healthy_account_state)

    assert len(events) == 1
    event = events[0]
    assert event.severity == "critical"
    assert event.category == "operational"
    assert event.trigger == "api_failure_threshold"
    assert event.action == TripwireAction.FREEZE_NEW_RISK


def test_check_all_tripwires_no_events(tripwire_config, healthy_account_state, sample_plan):
    """Test check_all_tripwires with no events."""
    service = TripwireService(tripwire_config)

    events = service.check_all_tripwires(healthy_account_state, sample_plan)

    assert len(events) == 0


def test_check_all_tripwires_multiple_events(tripwire_config, sample_plan):
    """Test check_all_tripwires aggregates events from all checks."""
    service = TripwireService(tripwire_config)
    service.daily_start_portfolio_value = 10000.0
    service.api_failure_count = 3

    # Create account state that triggers multiple tripwires
    account_state = AccountState(
        portfolio_value=9400.0,  # Daily loss
        available_balance=500.0,  # Low margin
        positions=[
            Position(
                coin="BTC",
                size=0.2,
                entry_price=50000.0,
                current_price=50000.0,
                unrealized_pnl=0.0,
                market_type="perp",
            ),
        ],
        spot_balances={},
        timestamp=datetime.now().timestamp() - 400,  # Stale data
        is_stale=True,
    )

    events = service.check_all_tripwires(account_state, sample_plan)

    # Should have multiple events
    assert len(events) >= 3
    categories = {e.category for e in events}
    assert "account_safety" in categories
    assert "operational" in categories


def test_record_api_failure(tripwire_config):
    """Test recording API failures."""
    service = TripwireService(tripwire_config)

    assert service.api_failure_count == 0

    service.record_api_failure()
    assert service.api_failure_count == 1

    service.record_api_failure()
    assert service.api_failure_count == 2


def test_reset_api_failure_count(tripwire_config):
    """Test resetting API failure count."""
    service = TripwireService(tripwire_config)

    service.api_failure_count = 5
    service.reset_api_failure_count()

    assert service.api_failure_count == 0


def test_reset_daily_tracking(tripwire_config):
    """Test resetting daily tracking metrics."""
    service = TripwireService(tripwire_config)

    service.daily_start_portfolio_value = 10000.0
    service.daily_loss_pct = 3.5

    service.reset_daily_tracking(12000.0)

    assert service.daily_start_portfolio_value == 12000.0
    assert service.daily_loss_pct == 0.0


def test_evaluate_trigger_funding_rate_negative(
    tripwire_config, healthy_account_state, sample_plan
):
    """Test trigger evaluation for negative funding rate."""
    service = TripwireService(tripwire_config)

    trigger = "funding rate turns negative"
    result = service._evaluate_trigger(trigger, healthy_account_state, sample_plan)

    # Should return False (we don't have funding rate data in account state yet)
    assert result is False


def test_evaluate_trigger_volatility_spike(tripwire_config, healthy_account_state, sample_plan):
    """Test trigger evaluation for volatility spike."""
    service = TripwireService(tripwire_config)

    trigger = "volatility exceeds 60%"
    result = service._evaluate_trigger(trigger, healthy_account_state, sample_plan)

    # Should return False (we don't have volatility data in account state yet)
    assert result is False


def test_evaluate_trigger_position_size_exceeded(tripwire_config, sample_plan):
    """Test trigger evaluation for position size."""
    service = TripwireService(tripwire_config)

    # Create account state with large position (75% of portfolio)
    account_state = AccountState(
        portfolio_value=10000.0,
        available_balance=3000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.15,
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

    trigger = "position size exceeds 50% of portfolio"
    result = service._evaluate_trigger(trigger, account_state, sample_plan)

    # Should return True (position is 75% > 50%)
    assert result is True


def test_evaluate_trigger_pnl_drawdown(tripwire_config, sample_plan):
    """Test trigger evaluation for PnL drawdown."""
    service = TripwireService(tripwire_config)

    # Create account state with large losses
    account_state = AccountState(
        portfolio_value=10000.0,
        available_balance=5000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.2,
                entry_price=50000.0,
                current_price=45000.0,
                unrealized_pnl=-1000.0,
                market_type="perp",
            ),
        ],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )

    trigger = "drawdown exceeds 8%"
    result = service._evaluate_trigger(trigger, account_state, sample_plan)

    # Should return True (10% loss > 8%)
    assert result is True


def test_evaluate_trigger_unknown_pattern(tripwire_config, healthy_account_state, sample_plan):
    """Test trigger evaluation for unknown pattern."""
    service = TripwireService(tripwire_config)

    trigger = "some unknown condition that we don't parse"
    result = service._evaluate_trigger(trigger, healthy_account_state, sample_plan)

    # Should return False for unknown patterns
    assert result is False


def test_tripwire_event_structure():
    """Test TripwireEvent data structure."""
    event = TripwireEvent(
        severity="critical",
        category="account_safety",
        trigger="test_trigger",
        action=TripwireAction.FREEZE_NEW_RISK,
        timestamp=datetime.now(),
        details={"key": "value"},
    )

    assert event.severity == "critical"
    assert event.category == "account_safety"
    assert event.trigger == "test_trigger"
    assert event.action == TripwireAction.FREEZE_NEW_RISK
    assert isinstance(event.timestamp, datetime)
    assert event.details == {"key": "value"}


def test_tripwire_action_enum():
    """Test TripwireAction enum values."""
    assert TripwireAction.FREEZE_NEW_RISK.value == "freeze_new_risk"
    assert TripwireAction.CUT_SIZE_TO_FLOOR.value == "cut_size_to_floor"
    assert TripwireAction.ESCALATE_TO_SLOW_LOOP.value == "escalate_to_slow_loop"
    assert TripwireAction.INVALIDATE_PLAN.value == "invalidate_plan"


def test_check_invalidation_triggers_disabled(tripwire_config, healthy_account_state, sample_plan):
    """Test plan invalidation checks can be disabled."""
    tripwire_config.check_invalidation_triggers = False
    service = TripwireService(tripwire_config)

    # Even with triggers in plan, should not check them
    events = service.check_all_tripwires(healthy_account_state, sample_plan)

    # Should not have any plan invalidation events
    invalidation_events = [e for e in events if e.category == "plan_invalidation"]
    assert len(invalidation_events) == 0


def test_daily_loss_calculation_updates(tripwire_config):
    """Test daily loss percentage updates correctly."""
    service = TripwireService(tripwire_config)

    # First check sets baseline
    account_state1 = AccountState(
        portfolio_value=10000.0,
        available_balance=5000.0,
        positions=[],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )
    service._check_account_safety(account_state1)
    assert service.daily_start_portfolio_value == 10000.0
    assert service.daily_loss_pct == 0.0

    # Second check with loss
    account_state2 = AccountState(
        portfolio_value=9700.0,
        available_balance=4700.0,
        positions=[],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )
    service._check_account_safety(account_state2)
    assert service.daily_loss_pct == pytest.approx(3.0)


def test_multiple_position_size_triggers(tripwire_config, sample_plan):
    """Test trigger fires when any position exceeds threshold."""
    service = TripwireService(tripwire_config)

    # Create account state with multiple positions, one exceeding threshold
    account_state = AccountState(
        portfolio_value=10000.0,
        available_balance=3000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.05,
                entry_price=50000.0,
                current_price=50000.0,
                unrealized_pnl=0.0,
                market_type="perp",
            ),
            Position(
                coin="ETH",
                size=2.0,
                entry_price=3000.0,
                current_price=3000.0,
                unrealized_pnl=0.0,
                market_type="perp",
            ),
        ],
        timestamp=datetime.now().timestamp(),
        spot_balances={},
        is_stale=False,
    )

    trigger = "position size exceeds 50% of portfolio"
    result = service._evaluate_trigger(trigger, account_state, sample_plan)

    # ETH position is 60% of portfolio, should trigger
    assert result is True
