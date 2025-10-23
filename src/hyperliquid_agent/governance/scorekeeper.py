"""Plan Scorekeeper for tracking strategy performance and shadow portfolios."""

import logging
from dataclasses import dataclass
from datetime import datetime

from hyperliquid_agent.governance.plan_card import StrategyPlanCard
from hyperliquid_agent.monitor import AccountState


@dataclass
class PlanMetrics:
    """Performance metrics for a strategy plan."""

    plan_id: str
    start_time: datetime
    end_time: datetime | None

    # Performance
    total_pnl: float = 0.0
    total_risk_taken: float = 0.0
    pnl_per_unit_risk: float = 0.0

    # Execution quality
    total_trades: int = 0
    winning_trades: int = 0
    hit_rate: float = 0.0
    avg_slippage_bps: float = 0.0

    # Plan adherence
    avg_drift_from_targets_pct: float = 0.0
    rebalance_count: int = 0

    # Tracking state
    initial_portfolio_value: float = 0.0
    peak_portfolio_value: float = 0.0
    max_drawdown_pct: float = 0.0


@dataclass
class ShadowPortfolio:
    """Paper trading portfolio for alternative strategies."""

    strategy_name: str
    paper_positions: dict[str, float]  # coin -> size
    paper_portfolio_value: float
    paper_pnl: float = 0.0
    initial_value: float = 0.0


class PlanScorekeeper:
    """Tracks plan-level performance and manages shadow portfolios."""

    def __init__(self, logger: logging.Logger | None = None):
        """Initialize the Plan Scorekeeper.

        Args:
            logger: Optional logger instance for governance event logging
        """
        self.active_metrics: PlanMetrics | None = None
        self.completed_plans: list[PlanMetrics] = []
        self.shadow_portfolios: list[ShadowPortfolio] = []
        self.logger = logger or logging.getLogger(__name__)

    def start_tracking_plan(self, plan: StrategyPlanCard, initial_portfolio_value: float):
        """Begin tracking a new plan.

        Args:
            plan: Strategy plan card to track
            initial_portfolio_value: Starting portfolio value
        """
        self.active_metrics = PlanMetrics(
            plan_id=plan.plan_id,
            start_time=datetime.now(),
            end_time=None,
            initial_portfolio_value=initial_portfolio_value,
            peak_portfolio_value=initial_portfolio_value,
        )

        self.logger.info(
            f"Started tracking plan: {plan.plan_id}",
            extra={
                "governance_event": "plan_tracking_started",
                "plan_id": plan.plan_id,
                "strategy_name": plan.strategy_name,
                "initial_portfolio_value": initial_portfolio_value,
                "start_time": self.active_metrics.start_time.isoformat(),
            },
        )

    def update_metrics(self, account_state: AccountState, plan: StrategyPlanCard):
        """Update metrics for the active plan.

        Args:
            account_state: Current account state
            plan: Active strategy plan card
        """
        if not self.active_metrics:
            return

        # Update portfolio tracking
        current_value = account_state.portfolio_value

        # Track peak value for drawdown calculation
        if current_value > self.active_metrics.peak_portfolio_value:
            self.active_metrics.peak_portfolio_value = current_value

        # Calculate PnL
        self.active_metrics.total_pnl = current_value - self.active_metrics.initial_portfolio_value

        # Calculate max drawdown
        if self.active_metrics.peak_portfolio_value > 0:
            current_drawdown = (
                (self.active_metrics.peak_portfolio_value - current_value)
                / self.active_metrics.peak_portfolio_value
                * 100
            )
            if current_drawdown > self.active_metrics.max_drawdown_pct:
                self.active_metrics.max_drawdown_pct = current_drawdown

        # Calculate PnL per unit risk
        # Use max drawdown as proxy for risk taken
        if self.active_metrics.max_drawdown_pct > 0:
            self.active_metrics.pnl_per_unit_risk = (
                self.active_metrics.total_pnl / self.active_metrics.max_drawdown_pct
            )

        # Calculate drift from target allocations
        drift_values = []
        for target_alloc in plan.target_allocations:
            # Find matching position
            matching_pos = next(
                (p for p in account_state.positions if p.coin == target_alloc.coin), None
            )

            if matching_pos:
                # Calculate actual allocation percentage
                position_value = matching_pos.size * matching_pos.current_price
                actual_pct = (position_value / current_value * 100) if current_value > 0 else 0.0

                # Calculate drift
                drift = abs(actual_pct - target_alloc.target_pct)
                drift_values.append(drift)
            else:
                # Position doesn't exist but target does
                drift_values.append(abs(target_alloc.target_pct))

        # Calculate average drift
        if drift_values:
            self.active_metrics.avg_drift_from_targets_pct = sum(drift_values) / len(drift_values)

    def finalize_plan(self, final_portfolio_value: float) -> str:
        """Finalize plan tracking and generate post-mortem summary.

        Args:
            final_portfolio_value: Final portfolio value at plan completion

        Returns:
            Natural language post-mortem summary
        """
        if not self.active_metrics:
            return "No active plan to finalize"

        # Set end time
        self.active_metrics.end_time = datetime.now()

        # Calculate final metrics
        duration_hours = (
            self.active_metrics.end_time - self.active_metrics.start_time
        ).total_seconds() / 3600

        # Calculate hit rate if we have trade data
        if self.active_metrics.total_trades > 0:
            self.active_metrics.hit_rate = (
                self.active_metrics.winning_trades / self.active_metrics.total_trades
            )

        # Calculate final PnL percentage
        pnl_pct = (
            (self.active_metrics.total_pnl / self.active_metrics.initial_portfolio_value * 100)
            if self.active_metrics.initial_portfolio_value > 0
            else 0.0
        )

        # Log plan finalization with comprehensive metrics
        self.logger.info(
            f"Plan finalized: {self.active_metrics.plan_id}",
            extra={
                "governance_event": "plan_finalized",
                "plan_id": self.active_metrics.plan_id,
                "start_time": self.active_metrics.start_time.isoformat(),
                "end_time": self.active_metrics.end_time.isoformat(),
                "duration_hours": duration_hours,
                "initial_portfolio_value": self.active_metrics.initial_portfolio_value,
                "final_portfolio_value": final_portfolio_value,
                "total_pnl": self.active_metrics.total_pnl,
                "pnl_pct": pnl_pct,
                "peak_portfolio_value": self.active_metrics.peak_portfolio_value,
                "max_drawdown_pct": self.active_metrics.max_drawdown_pct,
                "pnl_per_unit_risk": self.active_metrics.pnl_per_unit_risk,
                "total_trades": self.active_metrics.total_trades,
                "winning_trades": self.active_metrics.winning_trades,
                "hit_rate": self.active_metrics.hit_rate,
                "avg_slippage_bps": self.active_metrics.avg_slippage_bps,
                "avg_drift_from_targets_pct": self.active_metrics.avg_drift_from_targets_pct,
                "rebalance_count": self.active_metrics.rebalance_count,
            },
        )

        # Generate natural language summary
        summary = f"""
Plan {self.active_metrics.plan_id} Post-Mortem:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Duration: {duration_hours:.1f} hours
Initial Value: ${self.active_metrics.initial_portfolio_value:.2f}
Final Value: ${final_portfolio_value:.2f}
Total PnL: ${self.active_metrics.total_pnl:.2f} ({pnl_pct:.2f}%)
Peak Value: ${self.active_metrics.peak_portfolio_value:.2f}
Max Drawdown: {self.active_metrics.max_drawdown_pct:.2f}%
PnL per Unit Risk: {self.active_metrics.pnl_per_unit_risk:.2f}
Total Trades: {self.active_metrics.total_trades}
Hit Rate: {self.active_metrics.hit_rate:.1%}
Avg Slippage: {self.active_metrics.avg_slippage_bps:.1f} bps
Avg Drift from Targets: {self.active_metrics.avg_drift_from_targets_pct:.2f}%
Rebalance Count: {self.active_metrics.rebalance_count}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        # Store completed plan
        self.completed_plans.append(self.active_metrics)

        # Reset active tracking
        self.active_metrics = None

        return summary.strip()

    def update_shadow_portfolios(self, account_state: AccountState):
        """Update paper trading for shadow strategies.

        Args:
            account_state: Current account state for price data
        """
        for shadow in self.shadow_portfolios:
            # Calculate current shadow portfolio value
            shadow_value = 0.0

            for coin, size in shadow.paper_positions.items():
                # Find current price from account state positions
                matching_pos = next((p for p in account_state.positions if p.coin == coin), None)

                if matching_pos:
                    position_value = size * matching_pos.current_price
                    shadow_value += position_value

            # Update shadow portfolio value and PnL
            shadow.paper_portfolio_value = shadow_value
            if shadow.initial_value > 0:
                shadow.paper_pnl = shadow_value - shadow.initial_value

    def estimate_opportunity_cost(self) -> float:
        """Estimate opportunity cost of staying vs switching.

        Returns:
            Opportunity cost in basis points (positive means shadow is outperforming)
        """
        if not self.shadow_portfolios or not self.active_metrics:
            return 0.0

        # Find best performing shadow portfolio
        best_shadow_pnl = max(s.paper_pnl for s in self.shadow_portfolios)

        # Compare to active plan PnL
        active_pnl = self.active_metrics.total_pnl

        # Calculate opportunity cost as difference
        opportunity_cost = best_shadow_pnl - active_pnl

        # Convert to basis points relative to initial portfolio value
        if self.active_metrics.initial_portfolio_value > 0:
            opportunity_cost_bps = (
                opportunity_cost / self.active_metrics.initial_portfolio_value * 10000
            )
            return opportunity_cost_bps

        return 0.0

    def add_shadow_portfolio(
        self, strategy_name: str, initial_positions: dict[str, float], initial_value: float
    ):
        """Add a new shadow portfolio for tracking.

        Args:
            strategy_name: Name of the shadow strategy
            initial_positions: Initial paper positions (coin -> size)
            initial_value: Initial portfolio value
        """
        shadow = ShadowPortfolio(
            strategy_name=strategy_name,
            paper_positions=initial_positions.copy(),
            paper_portfolio_value=initial_value,
            initial_value=initial_value,
        )
        self.shadow_portfolios.append(shadow)

    def record_trade(self, is_winning: bool, slippage_bps: float):
        """Record a trade execution for metrics tracking.

        Args:
            is_winning: Whether the trade was profitable
            slippage_bps: Slippage in basis points
        """
        if not self.active_metrics:
            return

        self.active_metrics.total_trades += 1
        if is_winning:
            self.active_metrics.winning_trades += 1

        # Update running average of slippage
        if self.active_metrics.total_trades == 1:
            self.active_metrics.avg_slippage_bps = slippage_bps
        else:
            # Incremental average calculation
            self.active_metrics.avg_slippage_bps = (
                self.active_metrics.avg_slippage_bps * (self.active_metrics.total_trades - 1)
                + slippage_bps
            ) / self.active_metrics.total_trades

    def record_rebalance(self):
        """Record a rebalance event."""
        if not self.active_metrics:
            return

        self.active_metrics.rebalance_count += 1

    def get_active_plan_summary(self) -> str:
        """Get a summary of the currently active plan metrics.

        Returns:
            Summary string of active plan performance
        """
        if not self.active_metrics:
            return "No active plan being tracked"

        duration_hours = (datetime.now() - self.active_metrics.start_time).total_seconds() / 3600

        return f"""
Active Plan: {self.active_metrics.plan_id}
Duration: {duration_hours:.1f} hours
Current PnL: ${self.active_metrics.total_pnl:.2f}
Max Drawdown: {self.active_metrics.max_drawdown_pct:.2f}%
Trades: {self.active_metrics.total_trades} (Hit Rate: {self.active_metrics.hit_rate:.1%})
Avg Drift: {self.active_metrics.avg_drift_from_targets_pct:.2f}%
""".strip()
