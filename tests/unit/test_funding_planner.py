"""Unit tests for the FundingPlanner module."""

import logging
from decimal import Decimal
from typing import Any, cast

from hyperliquid_agent.config import RiskConfig
from hyperliquid_agent.decision import TradeAction
from hyperliquid_agent.executor import TradeExecutor
from hyperliquid_agent.funding import FundingPlanner
from hyperliquid_agent.monitor import AccountState


class DummyExecutor:
    """Minimal stub implementing methods used by FundingPlanner."""

    def _get_market_name(self, coin: str, market_type: str) -> str:
        return f"{coin}/USDC" if market_type == "spot" else coin

    def _get_reference_price(
        self,
        coin: str,
        market_type: str,
        market_name: str,
        *,
        is_buy: bool | None = None,
    ) -> Decimal:
        return Decimal("100")


def make_account_state(**overrides) -> AccountState:
    """Helper to create baseline AccountState objects for tests."""

    base: dict[str, Any] = {
        "portfolio_value": 2000.0,
        "available_balance": 1000.0,
        "positions": [],
        "timestamp": 0.0,
        "spot_balances": {"USDC": 10.0},
        "account_value": 1500.0,
        "total_initial_margin": 500.0,
        "total_maintenance_margin": 400.0,
        "margin_fraction": 0.3,
    }
    base.update(overrides)
    return AccountState(**base)


def test_funding_planner_inserts_transfer_when_spot_insufficient():
    risk = RiskConfig(
        enable_auto_transfers=True,
        target_initial_margin_ratio=1.1,
        min_perp_balance_usd=500.0,
        target_spot_usdc_buffer_usd=50.0,
    )

    executor = cast(TradeExecutor, DummyExecutor())
    planner = FundingPlanner(risk, executor, logger=logging.getLogger("funding-test"))
    account_state = make_account_state()

    actions = [
        TradeAction(action_type="buy", coin="ETH", market_type="spot", size=5.0, price=None),
    ]

    result = planner.plan(account_state, actions)

    assert result.inserted_transfers == 1
    assert not result.skipped_actions
    assert len(result.actions) == 2
    transfer_action = result.actions[0]
    assert transfer_action.action_type == "transfer"
    assert transfer_action.market_type == "spot"
    assert transfer_action.size is not None and transfer_action.size > 0
    assert result.actions[1].action_type == "buy"


def test_funding_planner_skips_buy_when_buffer_would_break():
    risk = RiskConfig(
        enable_auto_transfers=True,
        target_initial_margin_ratio=1.1,
        min_perp_balance_usd=500.0,
        target_spot_usdc_buffer_usd=50.0,
    )

    executor = cast(TradeExecutor, DummyExecutor())
    planner = FundingPlanner(risk, executor, logger=logging.getLogger("funding-test"))

    # Account value equals required capital; no headroom to transfer
    total_initial_margin = 500.0
    target_ratio = risk.target_initial_margin_ratio
    required_capital = total_initial_margin * target_ratio

    account_state = make_account_state(
        account_value=required_capital,
        available_balance=300.0,
        spot_balances={"USDC": 10.0},
    )

    actions = [
        TradeAction(action_type="buy", coin="BTC", market_type="spot", size=2.0, price=None),
    ]

    result = planner.plan(account_state, actions)

    assert result.inserted_transfers == 0
    assert result.skipped_actions  # buy should be skipped
    assert all(action.action_type != "buy" for action in result.actions)


def test_funding_planner_allows_sell_to_increase_spot_balance():
    risk = RiskConfig(enable_auto_transfers=True)
    executor = cast(TradeExecutor, DummyExecutor())
    planner = FundingPlanner(risk, executor, logger=logging.getLogger("funding-test"))
    account_state = make_account_state(spot_balances={"USDC": 0.0})

    actions = [
        TradeAction(action_type="sell", coin="SOL", market_type="spot", size=3.0, price=20.0),
    ]

    result = planner.plan(account_state, actions)

    assert result.actions[0].action_type == "sell"
    assert result.inserted_transfers == 0
    assert not result.skipped_actions
