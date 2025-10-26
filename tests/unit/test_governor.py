"""Unit tests for Strategy Governor module."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

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


@pytest.fixture
def governor_config():
    """Create a test governor configuration."""
    return GovernorConfig(
        minimum_advantage_over_cost_bps=50.0,
        cooldown_after_change_minutes=60,
        partial_rotation_pct_per_cycle=25.0,
        state_persistence_path=tempfile.mktemp(suffix=".json"),
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
            invalidation_triggers=["funding rate drops below 0.005%"],
        ),
        change_cost=ChangeCostModel(
            estimated_fees_bps=10.0,
            estimated_slippage_bps=5.0,
            estimated_funding_change_bps=2.0,
            opportunity_cost_bps=3.0,
        ),
        expected_edge_bps=100.0,
        kpis_to_track=["funding_pnl", "execution_quality"],
        minimum_dwell_minutes=120,
        compatible_regimes=["carry-friendly"],
        avoid_regimes=["event-risk"],
        status="active",
    )


def test_governor_initialization(governor_config):
    """Test Strategy Governor initializes correctly."""
    governor = StrategyGovernor(governor_config)

    assert governor.config == governor_config
    assert governor.active_plan is None
    assert governor.last_change_at is None
    assert governor.rebalance_schedule is None


def test_can_review_plan_no_active_plan(governor_config):
    """Test plan review is permitted when no active plan exists."""
    governor = StrategyGovernor(governor_config)
    current_time = datetime.now()

    can_review, reason = governor.can_review_plan(current_time)

    assert can_review is True
    assert "No active plan" in reason


def test_can_review_plan_dwell_time_not_met(governor_config, sample_plan):
    """Test plan review is blocked when dwell time not met."""
    governor = StrategyGovernor(governor_config)
    current_time = datetime.now()

    # Activate plan
    sample_plan.activated_at = current_time - timedelta(minutes=60)  # 60 minutes ago
    sample_plan.minimum_dwell_minutes = 120  # Requires 120 minutes
    governor.active_plan = sample_plan

    can_review, reason = governor.can_review_plan(current_time)

    assert can_review is False
    assert "Dwell time not met" in reason
    assert "60.0/120" in reason


def test_can_review_plan_dwell_time_met(governor_config, sample_plan):
    """Test plan review is permitted when dwell time is met."""
    governor = StrategyGovernor(governor_config)
    current_time = datetime.now()

    # Activate plan with sufficient dwell time elapsed
    sample_plan.activated_at = current_time - timedelta(minutes=130)  # 130 minutes ago
    sample_plan.minimum_dwell_minutes = 120
    governor.active_plan = sample_plan

    can_review, reason = governor.can_review_plan(current_time)

    assert can_review is True
    assert "Review permitted" in reason


def test_can_review_plan_cooldown_active(governor_config, sample_plan):
    """Test plan review is blocked during cooldown period."""
    governor = StrategyGovernor(governor_config)
    current_time = datetime.now()

    # Set up plan with dwell time met but cooldown active
    sample_plan.activated_at = current_time - timedelta(minutes=130)
    sample_plan.minimum_dwell_minutes = 120
    governor.active_plan = sample_plan
    governor.last_change_at = current_time - timedelta(minutes=30)  # 30 minutes ago

    can_review, reason = governor.can_review_plan(current_time)

    assert can_review is False
    assert "Cooldown active" in reason
    assert "30.0/60" in reason


def test_can_review_plan_cooldown_expired(governor_config, sample_plan):
    """Test plan review is permitted after cooldown expires."""
    governor = StrategyGovernor(governor_config)
    current_time = datetime.now()

    # Set up plan with both dwell time and cooldown met
    sample_plan.activated_at = current_time - timedelta(minutes=130)
    sample_plan.minimum_dwell_minutes = 120
    governor.active_plan = sample_plan
    governor.last_change_at = current_time - timedelta(minutes=70)  # 70 minutes ago

    can_review, reason = governor.can_review_plan(current_time)

    assert can_review is True
    assert "Review permitted" in reason


def test_can_review_plan_rebalancing_in_progress(governor_config, sample_plan):
    """Test plan review is blocked during rebalancing."""
    governor = StrategyGovernor(governor_config)
    current_time = datetime.now()

    # Set up plan with rebalancing status
    sample_plan.activated_at = current_time - timedelta(minutes=130)
    sample_plan.minimum_dwell_minutes = 120
    sample_plan.status = "rebalancing"
    governor.active_plan = sample_plan

    can_review, reason = governor.can_review_plan(current_time)

    assert can_review is False
    assert "Rebalancing in progress" in reason


def test_evaluate_change_proposal_insufficient_advantage(governor_config, sample_plan):
    """Test plan change is rejected when advantage is insufficient."""
    governor = StrategyGovernor(governor_config)

    # Create proposal with insufficient net advantage
    proposal = PlanChangeProposal(
        new_plan=sample_plan,
        reason="Test proposal",
        expected_advantage_bps=60.0,
        change_cost_bps=30.0,  # Net advantage: 30 bps < 50 bps threshold
    )

    approved, reason = governor.evaluate_change_proposal(proposal)

    assert approved is False
    assert "Insufficient advantage" in reason
    assert "30.0 < 50.0" in reason


def test_evaluate_change_proposal_sufficient_advantage(governor_config, sample_plan):
    """Test plan change is approved when advantage is sufficient."""
    governor = StrategyGovernor(governor_config)

    # Create proposal with sufficient net advantage
    proposal = PlanChangeProposal(
        new_plan=sample_plan,
        reason="Test proposal",
        expected_advantage_bps=100.0,
        change_cost_bps=30.0,  # Net advantage: 70 bps > 50 bps threshold
    )

    approved, reason = governor.evaluate_change_proposal(proposal)

    assert approved is True
    assert "Approved" in reason
    assert "70.0 bps" in reason


def test_plan_change_proposal_net_advantage_calculation(sample_plan):
    """Test PlanChangeProposal calculates net advantage correctly."""
    proposal = PlanChangeProposal(
        new_plan=sample_plan,
        reason="Test",
        expected_advantage_bps=150.0,
        change_cost_bps=40.0,
    )

    assert proposal.net_advantage_bps == 110.0


def test_activate_plan(governor_config, sample_plan):
    """Test plan activation sets correct state."""
    governor = StrategyGovernor(governor_config)
    current_time = datetime.now()

    governor.activate_plan(sample_plan, current_time)

    assert governor.active_plan == sample_plan
    assert sample_plan.activated_at == current_time
    assert sample_plan.status == "active"
    assert governor.last_change_at == current_time


def test_create_rebalance_schedule_simple(governor_config):
    """Test rebalance schedule generation with simple allocations."""
    governor = StrategyGovernor(governor_config)

    from_allocations = [
        TargetAllocation(coin="BTC", target_pct=100.0, market_type="perp", leverage=1.0),
    ]

    to_allocations = [
        TargetAllocation(coin="BTC", target_pct=50.0, market_type="perp", leverage=1.0),
        TargetAllocation(coin="ETH", target_pct=50.0, market_type="perp", leverage=1.0),
    ]

    schedule = governor.create_rebalance_schedule(from_allocations, to_allocations)

    # With 25% per cycle, should have 4 steps
    assert len(schedule) == 4

    # Check first step (25% progress)
    step1 = schedule[0]
    assert step1["step"] == 1
    assert step1["progress_pct"] == 25.0
    btc_alloc = next(a for a in step1["allocations"] if a["coin"] == "BTC")
    eth_alloc = next(a for a in step1["allocations"] if a["coin"] == "ETH")
    assert btc_alloc["target_pct"] == pytest.approx(87.5)  # 100 + (50-100)*0.25
    assert eth_alloc["target_pct"] == pytest.approx(12.5)  # 0 + (50-0)*0.25

    # Check last step (100% progress)
    step4 = schedule[3]
    assert step4["step"] == 4
    assert step4["progress_pct"] == 100.0
    btc_alloc = next(a for a in step4["allocations"] if a["coin"] == "BTC")
    eth_alloc = next(a for a in step4["allocations"] if a["coin"] == "ETH")
    assert btc_alloc["target_pct"] == pytest.approx(50.0)
    assert eth_alloc["target_pct"] == pytest.approx(50.0)


def test_create_rebalance_schedule_new_coin(governor_config):
    """Test rebalance schedule handles new coins not in from_allocations."""
    governor = StrategyGovernor(governor_config)

    from_allocations = [
        TargetAllocation(coin="BTC", target_pct=100.0, market_type="perp", leverage=1.0),
    ]

    to_allocations = [
        TargetAllocation(coin="SOL", target_pct=100.0, market_type="perp", leverage=1.0),
    ]

    schedule = governor.create_rebalance_schedule(from_allocations, to_allocations)

    # Check that SOL starts from 0 and interpolates to 100
    step1 = schedule[0]
    sol_alloc = next(a for a in step1["allocations"] if a["coin"] == "SOL")
    assert sol_alloc["target_pct"] == pytest.approx(25.0)  # 0 + (100-0)*0.25


def test_state_persistence(governor_config, sample_plan):
    """Test state is persisted and loaded correctly."""
    # Create governor and activate plan
    governor1 = StrategyGovernor(governor_config)
    current_time = datetime.now()
    governor1.activate_plan(sample_plan, current_time)

    # Create new governor instance with same config
    governor2 = StrategyGovernor(governor_config)

    # Verify state was loaded
    assert governor2.active_plan is not None
    assert governor2.active_plan.plan_id == sample_plan.plan_id
    assert governor2.active_plan.strategy_name == sample_plan.strategy_name
    assert governor2.last_change_at is not None

    # Clean up
    Path(governor_config.state_persistence_path).unlink(missing_ok=True)


def test_state_persistence_no_existing_file(governor_config):
    """Test governor handles missing state file gracefully."""
    # Ensure file doesn't exist
    Path(governor_config.state_persistence_path).unlink(missing_ok=True)

    # Should initialize without error
    governor = StrategyGovernor(governor_config)

    assert governor.active_plan is None
    assert governor.last_change_at is None


def test_state_persistence_corrupted_file(governor_config):
    """Test governor handles corrupted state file gracefully."""
    # Write corrupted JSON
    with open(governor_config.state_persistence_path, "w") as f:
        f.write("{ invalid json }")

    # Should initialize without crashing
    governor = StrategyGovernor(governor_config)

    assert governor.active_plan is None
    assert governor.last_change_at is None

    # Clean up
    Path(governor_config.state_persistence_path).unlink(missing_ok=True)


def test_rebalance_schedule_with_different_rotation_percentage():
    """Test rebalance schedule respects configured rotation percentage."""
    config = GovernorConfig(
        partial_rotation_pct_per_cycle=50.0,  # 50% per cycle
        state_persistence_path=tempfile.mktemp(suffix=".json"),
    )
    governor = StrategyGovernor(config)

    from_allocations = [
        TargetAllocation(coin="BTC", target_pct=100.0, market_type="perp", leverage=1.0),
    ]

    to_allocations = [
        TargetAllocation(coin="ETH", target_pct=100.0, market_type="perp", leverage=1.0),
    ]

    schedule = governor.create_rebalance_schedule(from_allocations, to_allocations)

    # With 50% per cycle, should have 2 steps
    assert len(schedule) == 2

    # Check first step (50% progress)
    step1 = schedule[0]
    assert step1["progress_pct"] == 50.0

    # Check second step (100% progress)
    step2 = schedule[1]
    assert step2["progress_pct"] == 100.0


def test_multiple_plan_changes_respect_cooldown(governor_config, sample_plan):
    """Test multiple plan changes respect cooldown periods."""
    governor = StrategyGovernor(governor_config)
    current_time = datetime.now()

    # Activate first plan
    governor.activate_plan(sample_plan, current_time)

    # Try to review immediately - should be blocked by dwell time
    can_review, _ = governor.can_review_plan(current_time)
    assert can_review is False

    # Advance time past dwell time but within cooldown
    time_after_dwell = current_time + timedelta(minutes=130)
    can_review, reason = governor.can_review_plan(time_after_dwell)
    # Should be permitted (no previous change, so no cooldown)
    assert can_review is True

    # Simulate a plan change
    governor.last_change_at = time_after_dwell

    # Try to review again immediately - should be blocked by cooldown
    can_review, reason = governor.can_review_plan(time_after_dwell + timedelta(minutes=1))
    assert can_review is False
    assert "Cooldown active" in reason


def test_activate_plan_persists_state(governor_config, sample_plan):
    """Test activating a plan persists state to disk."""
    governor = StrategyGovernor(governor_config)
    current_time = datetime.now()

    governor.activate_plan(sample_plan, current_time)

    # Verify file was created
    assert Path(governor_config.state_persistence_path).exists()

    # Verify file contains correct data
    with open(governor_config.state_persistence_path) as f:
        data = json.load(f)
        assert data["active_plan"] is not None
        assert data["active_plan"]["plan_id"] == sample_plan.plan_id
        assert data["last_change_at"] is not None

    # Clean up
    Path(governor_config.state_persistence_path).unlink(missing_ok=True)
