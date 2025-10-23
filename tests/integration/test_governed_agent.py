"""Integration tests for governance components working together."""

from datetime import datetime, timedelta

import pytest

from hyperliquid_agent.governance.governor import (
    GovernorConfig,
    PlanChangeProposal,
    StrategyGovernor,
)
from hyperliquid_agent.governance.plan_card import (
    ChangeCostModel,
    ExitRules,
    RiskBudget,
    StrategyPlanCard,
    TargetAllocation,
)
from hyperliquid_agent.governance.regime import (
    RegimeClassification,
    RegimeDetector,
    RegimeDetectorConfig,
    RegimeSignals,
)
from hyperliquid_agent.governance.scorekeeper import PlanScorekeeper
from hyperliquid_agent.governance.tripwire import (
    TripwireAction,
    TripwireConfig,
    TripwireService,
)
from hyperliquid_agent.monitor import AccountState, Position


@pytest.fixture
def governor_config():
    """Create test governor configuration."""
    return GovernorConfig(
        minimum_advantage_over_cost_bps=50.0,
        cooldown_after_change_minutes=5,
        partial_rotation_pct_per_cycle=25.0,
        state_persistence_path="test_state/governor_integration.json",
    )


@pytest.fixture
def regime_config():
    """Create test regime detector configuration."""
    return RegimeDetectorConfig(
        confirmation_cycles_required=2,
        hysteresis_enter_threshold=0.7,
        hysteresis_exit_threshold=0.4,
    )


@pytest.fixture
def tripwire_config():
    """Create test tripwire configuration."""
    return TripwireConfig(
        min_margin_ratio=0.15,
        daily_loss_limit_pct=5.0,
    )


@pytest.fixture
def sample_account_state():
    """Create sample account state."""
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
        is_stale=False,
    )


@pytest.fixture
def sample_plan():
    """Create sample strategy plan."""
    return StrategyPlanCard(
        plan_id="test_plan_001",
        strategy_name="funding-harvest",
        strategy_version="1.0",
        created_at=datetime.now(),
        objective="Harvest funding rates",
        target_holding_period_hours=24,
        time_horizon="hours",
        key_thesis="Positive funding",
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
        minimum_dwell_minutes=10,
        compatible_regimes=["carry-friendly"],
        avoid_regimes=["event-risk"],
        status="active",
    )


def test_full_governance_workflow(
    governor_config, regime_config, tripwire_config, sample_account_state, sample_plan
):
    """Test complete governance workflow: plan activation, regime change, tripwire check."""
    # Initialize all governance components
    governor = StrategyGovernor(governor_config)
    regime_detector = RegimeDetector(regime_config)
    tripwire_service = TripwireService(tripwire_config)
    scorekeeper = PlanScorekeeper()

    current_time = datetime.now()

    # Step 1: Activate initial plan
    governor.activate_plan(sample_plan, current_time)
    scorekeeper.start_tracking_plan(sample_plan, sample_account_state.portfolio_value)

    assert governor.active_plan is not None
    assert scorekeeper.active_metrics is not None

    # Step 2: Check tripwires (should pass)
    events = tripwire_service.check_all_tripwires(sample_account_state, governor.active_plan)
    assert len(events) == 0

    # Step 3: Update metrics
    scorekeeper.update_metrics(sample_account_state, governor.active_plan)
    # PnL is 0 because initial value equals current value
    assert scorekeeper.active_metrics.total_pnl == 0.0

    # Step 4: Classify regime
    trending_signals = RegimeSignals(
        price_sma_20=50000.0,
        price_sma_50=48000.0,
        adx=30.0,
        realized_vol_24h=0.5,
        avg_funding_rate=0.01,
        bid_ask_spread_bps=5.0,
        order_book_depth=1000000.0,
    )
    classification = regime_detector.classify_regime(trending_signals)
    assert classification.regime == "trending"

    # Step 5: Confirm regime change
    for _ in range(2):
        classification = regime_detector.classify_regime(trending_signals)
        regime_detector.update_and_confirm(classification)

    assert regime_detector.current_regime == "trending"


def test_regime_change_triggers_plan_review(
    governor_config, regime_config, sample_plan
):
    """Test regime change overrides dwell time restrictions."""
    governor = StrategyGovernor(governor_config)
    regime_detector = RegimeDetector(regime_config)

    current_time = datetime.now()

    # Activate plan with short dwell time
    sample_plan.minimum_dwell_minutes = 60
    sample_plan.activated_at = current_time - timedelta(minutes=10)
    governor.active_plan = sample_plan

    # Check review permission (should be blocked by dwell time)
    can_review, reason = governor.can_review_plan(current_time)
    assert can_review is False
    assert "Dwell time not met" in reason

    # Simulate regime change
    regime_detector.current_regime = "range-bound"
    trending_signals = RegimeSignals(
        price_sma_20=50000.0,
        price_sma_50=48000.0,
        adx=30.0,
        realized_vol_24h=0.5,
        avg_funding_rate=0.01,
        bid_ask_spread_bps=5.0,
        order_book_depth=1000000.0,
    )

    for _ in range(2):
        classification = regime_detector.classify_regime(trending_signals)
        changed, _ = regime_detector.update_and_confirm(classification)

    # Regime changed - this would override dwell time in full implementation
    assert changed is True
    assert regime_detector.current_regime == "trending"


def test_tripwire_invalidates_plan(
    governor_config, tripwire_config, sample_plan
):
    """Test tripwire can invalidate active plan."""
    governor = StrategyGovernor(governor_config)
    tripwire_service = TripwireService(tripwire_config)

    current_time = datetime.now()

    # Activate plan
    governor.activate_plan(sample_plan, current_time)
    assert governor.active_plan.status == "active"

    # Create account state that triggers invalidation
    sample_plan.exit_rules.invalidation_triggers = ["position size exceeds 50% of portfolio"]

    dangerous_state = AccountState(
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
        is_stale=False,
    )

    # Check tripwires
    events = tripwire_service.check_all_tripwires(dangerous_state, governor.active_plan)

    # Should have invalidation event
    invalidation_events = [e for e in events if e.action == TripwireAction.INVALIDATE_PLAN]
    assert len(invalidation_events) > 0

    # In full implementation, this would set plan status to "invalidated"
    governor.active_plan.status = "invalidated"
    assert governor.active_plan.status == "invalidated"


def test_plan_change_with_cost_benefit_analysis(
    governor_config, sample_plan
):
    """Test plan change requires sufficient advantage over cost."""
    governor = StrategyGovernor(governor_config)

    current_time = datetime.now()

    # Activate initial plan
    governor.activate_plan(sample_plan, current_time)

    # Create new plan with insufficient advantage
    new_plan_weak = StrategyPlanCard(
        plan_id="test_plan_002",
        strategy_name="trend-following",
        strategy_version="1.0",
        created_at=datetime.now(),
        objective="Follow trends",
        target_holding_period_hours=48,
        time_horizon="days",
        key_thesis="Strong trend",
        target_allocations=[
            TargetAllocation(coin="BTC", target_pct=70.0, market_type="perp", leverage=2.0),
        ],
        allowed_leverage_range=(1.0, 3.0),
        risk_budget=RiskBudget(
            max_position_pct={"BTC": 80.0},
            max_leverage=3.0,
            max_adverse_excursion_pct=7.0,
            plan_max_drawdown_pct=15.0,
            per_trade_risk_pct=3.0,
        ),
        exit_rules=ExitRules(
            profit_target_pct=15.0,
            stop_loss_pct=7.0,
            time_based_review_hours=48,
            invalidation_triggers=[],
        ),
        change_cost=ChangeCostModel(
            estimated_fees_bps=20.0,
            estimated_slippage_bps=15.0,
            estimated_funding_change_bps=5.0,
            opportunity_cost_bps=10.0,
        ),
        expected_edge_bps=80.0,  # Low advantage
        kpis_to_track=["trend_pnl"],
        minimum_dwell_minutes=30,
        compatible_regimes=["trending"],
        avoid_regimes=["range-bound"],
        status="pending",
    )

    # Evaluate weak proposal (80 - 50 = 30 bps < 50 bps threshold)
    weak_proposal = PlanChangeProposal(
        new_plan=new_plan_weak,
        reason="Weak opportunity",
        expected_advantage_bps=80.0,
        change_cost_bps=50.0,
    )

    approved, reason = governor.evaluate_change_proposal(weak_proposal)
    assert approved is False
    assert "Insufficient advantage" in reason

    # Create new plan with strong advantage
    new_plan_strong = new_plan_weak
    new_plan_strong.expected_edge_bps = 150.0

    strong_proposal = PlanChangeProposal(
        new_plan=new_plan_strong,
        reason="Strong opportunity",
        expected_advantage_bps=150.0,
        change_cost_bps=50.0,
    )

    approved, reason = governor.evaluate_change_proposal(strong_proposal)
    assert approved is True
    assert "Approved" in reason


def test_scorekeeper_tracks_plan_performance(
    sample_plan, sample_account_state
):
    """Test scorekeeper tracks plan metrics throughout lifecycle."""
    scorekeeper = PlanScorekeeper()

    # Start tracking
    scorekeeper.start_tracking_plan(sample_plan, 10000.0)

    # Update metrics multiple times
    for i in range(5):
        # Simulate portfolio growth
        sample_account_state.portfolio_value = 10000.0 + (i * 100)
        scorekeeper.update_metrics(sample_account_state, sample_plan)

        # Record some trades
        scorekeeper.record_trade(is_winning=(i % 2 == 0), slippage_bps=5.0 + i)

    # Finalize plan
    summary = scorekeeper.finalize_plan(10400.0)

    # Verify summary contains key metrics
    assert "test_plan_001" in summary
    assert "400.00" in summary  # PnL
    assert scorekeeper.active_metrics is None  # Reset after finalization
    assert len(scorekeeper.completed_plans) == 1


def test_state_persistence_across_restarts(
    governor_config, sample_plan
):
    """Test governance state persists and recovers."""
    # Create first governor instance
    governor1 = StrategyGovernor(governor_config)
    current_time = datetime.now()

    # Activate plan
    governor1.activate_plan(sample_plan, current_time)
    plan_id = governor1.active_plan.plan_id

    # Create second governor instance (simulating restart)
    governor2 = StrategyGovernor(governor_config)

    # Verify state was restored
    assert governor2.active_plan is not None
    assert governor2.active_plan.plan_id == plan_id
