"""Tripwire Service for independent safety monitoring."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

from hyperliquid_agent.governance.plan_card import StrategyPlanCard
from hyperliquid_agent.monitor import AccountState


class TripwireAction(Enum):
    """Actions that can be triggered by tripwires."""

    FREEZE_NEW_RISK = "freeze_new_risk"
    CUT_SIZE_TO_FLOOR = "cut_size_to_floor"
    ESCALATE_TO_SLOW_LOOP = "escalate_to_slow_loop"
    INVALIDATE_PLAN = "invalidate_plan"


@dataclass
class TripwireConfig:
    """Configuration for tripwire service."""

    # Account safety
    min_margin_ratio: float = 0.15
    liquidation_proximity_threshold: float = 0.25
    daily_loss_limit_pct: float = 5.0

    # Plan invalidation
    check_invalidation_triggers: bool = True

    # Operational
    max_data_staleness_seconds: int = 300
    max_api_failure_count: int = 3


@dataclass
class TripwireEvent:
    """Event representing a triggered tripwire."""

    severity: Literal["warning", "critical"]
    category: Literal["account_safety", "plan_invalidation", "operational"]
    trigger: str
    action: TripwireAction
    timestamp: datetime
    details: dict


class TripwireService:
    """Independent safety monitoring service with override authority."""

    def __init__(self, config: TripwireConfig):
        """Initialize the tripwire service.

        Args:
            config: TripwireConfig instance
        """
        self.config = config
        self.api_failure_count: int = 0
        self.daily_start_portfolio_value: float | None = None
        self.daily_loss_pct: float = 0.0

    def _check_account_safety(self, account_state: AccountState) -> list[TripwireEvent]:
        """Check account safety tripwires.

        Args:
            account_state: Current account state

        Returns:
            List of triggered tripwire events
        """
        events = []

        # Daily loss limit check
        if self.daily_start_portfolio_value is None:
            self.daily_start_portfolio_value = account_state.portfolio_value

        self.daily_loss_pct = (
            (self.daily_start_portfolio_value - account_state.portfolio_value)
            / self.daily_start_portfolio_value
            * 100
        )

        if self.daily_loss_pct >= self.config.daily_loss_limit_pct:
            events.append(
                TripwireEvent(
                    severity="critical",
                    category="account_safety",
                    trigger="daily_loss_limit",
                    action=TripwireAction.CUT_SIZE_TO_FLOOR,
                    timestamp=datetime.now(),
                    details={
                        "loss_pct": self.daily_loss_pct,
                        "limit": self.config.daily_loss_limit_pct,
                        "start_value": self.daily_start_portfolio_value,
                        "current_value": account_state.portfolio_value,
                    },
                )
            )

        # Margin ratio check (when margin data is available)
        # Note: Hyperliquid API provides margin data in marginSummary
        # This would require extending AccountState to include margin_ratio
        # For now, we'll check if portfolio value is dangerously low relative to positions
        total_position_value = sum(abs(pos.size * pos.current_price) for pos in account_state.positions)
        if total_position_value > 0:
            effective_margin_ratio = account_state.available_balance / total_position_value
            if effective_margin_ratio < self.config.min_margin_ratio:
                events.append(
                    TripwireEvent(
                        severity="critical",
                        category="account_safety",
                        trigger="low_margin_ratio",
                        action=TripwireAction.CUT_SIZE_TO_FLOOR,
                        timestamp=datetime.now(),
                        details={
                            "margin_ratio": effective_margin_ratio,
                            "min_required": self.config.min_margin_ratio,
                            "available_balance": account_state.available_balance,
                            "position_value": total_position_value,
                        },
                    )
                )

        # Liquidation proximity check
        # Check if unrealized losses are approaching dangerous levels
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in account_state.positions)
        if total_unrealized_pnl < 0:
            loss_ratio = float(abs(total_unrealized_pnl)) / account_state.portfolio_value
            if loss_ratio >= self.config.liquidation_proximity_threshold:
                events.append(
                    TripwireEvent(
                        severity="critical",
                        category="account_safety",
                        trigger="liquidation_proximity",
                        action=TripwireAction.ESCALATE_TO_SLOW_LOOP,
                        timestamp=datetime.now(),
                        details={
                            "loss_ratio": loss_ratio,
                            "threshold": self.config.liquidation_proximity_threshold,
                            "unrealized_pnl": total_unrealized_pnl,
                            "portfolio_value": account_state.portfolio_value,
                        },
                    )
                )

        return events

    def _check_plan_invalidation(
        self, account_state: AccountState, plan: StrategyPlanCard
    ) -> list[TripwireEvent]:
        """Check if plan invalidation triggers have fired.

        Args:
            account_state: Current account state
            plan: Active strategy plan card

        Returns:
            List of triggered invalidation events
        """
        events = []

        # Parse and evaluate invalidation triggers
        for trigger in plan.exit_rules.invalidation_triggers:
            if self._evaluate_trigger(trigger, account_state, plan):
                events.append(
                    TripwireEvent(
                        severity="warning",
                        category="plan_invalidation",
                        trigger=trigger,
                        action=TripwireAction.INVALIDATE_PLAN,
                        timestamp=datetime.now(),
                        details={"plan_id": plan.plan_id, "trigger_text": trigger},
                    )
                )

        return events

    def _evaluate_trigger(
        self, trigger: str, account_state: AccountState, plan: StrategyPlanCard
    ) -> bool:
        """Evaluate a natural language trigger condition.

        Args:
            trigger: Natural language trigger condition
            account_state: Current account state
            plan: Active strategy plan card

        Returns:
            True if trigger condition is met, False otherwise
        """
        trigger_lower = trigger.lower()

        # Funding rate triggers
        if "funding" in trigger_lower:
            # Extract threshold from trigger text
            # Examples: "funding rate drops below 0.005%", "funding turns negative"
            if "negative" in trigger_lower or "below 0" in trigger_lower:
                # Would need funding rate data in account_state
                # For now, return False as we don't have this data yet
                return False
            elif "below" in trigger_lower:
                # Try to extract numeric threshold
                try:
                    # Simple pattern matching for "below X%"
                    parts = trigger_lower.split("below")
                    if len(parts) > 1:
                        threshold_str = parts[1].strip().replace("%", "").strip()
                        threshold = float(threshold_str)
                        # Would check against actual funding rate
                        # return avg_funding_rate < threshold
                        return False
                except (ValueError, IndexError):
                    pass

        # Volatility triggers
        if "volatility" in trigger_lower or "vol" in trigger_lower:
            # Examples: "realized volatility exceeds 60%", "vol spikes above 80%"
            if "exceed" in trigger_lower or "above" in trigger_lower or "spike" in trigger_lower:
                try:
                    # Extract threshold
                    for word in trigger_lower.split():
                        if "%" in word:
                            threshold = float(word.replace("%", ""))
                            # Would check against actual volatility
                            # return realized_vol > threshold
                            return False
                except ValueError:
                    pass

        # PnL-based triggers
        if "pnl" in trigger_lower or "loss" in trigger_lower or "drawdown" in trigger_lower:
            # Examples: "plan drawdown exceeds 10%", "loss exceeds 5%"
            if plan.activated_at:
                # Calculate plan-level PnL
                # This would require tracking initial portfolio value at plan activation
                # For now, we can use unrealized PnL as a proxy
                total_unrealized_pnl = sum(pos.unrealized_pnl for pos in account_state.positions)
                pnl_pct = (total_unrealized_pnl / account_state.portfolio_value) * 100

                # Extract threshold
                try:
                    for word in trigger_lower.split():
                        if "%" in word:
                            threshold = float(word.replace("%", ""))
                            if "exceed" in trigger_lower or "above" in trigger_lower:
                                return abs(pnl_pct) > threshold
                except ValueError:
                    pass

        # Basis/spread triggers
        if "basis" in trigger_lower or "spread" in trigger_lower:
            # Examples: "perp-spot basis inverts", "spread widens beyond 2%"
            if "invert" in trigger_lower:
                # Would check if basis changed sign
                return False

        # Position size triggers
        if "position" in trigger_lower and ("exceed" in trigger_lower or "above" in trigger_lower):
            # Examples: "position size exceeds 50% of portfolio"
            try:
                for word in trigger_lower.split():
                    if "%" in word:
                        threshold = float(word.replace("%", ""))
                        # Check if any position exceeds threshold
                        for pos in account_state.positions:
                            position_value = abs(pos.size * pos.current_price)
                            position_pct = (position_value / account_state.portfolio_value) * 100
                            if position_pct > threshold:
                                return True
            except ValueError:
                pass

        # Default: trigger not fired
        return False

    def _check_operational_health(self, account_state: AccountState) -> list[TripwireEvent]:
        """Check operational health tripwires.

        Args:
            account_state: Current account state

        Returns:
            List of triggered operational health events
        """
        events = []

        # Stale data check
        if account_state.is_stale:
            current_time = datetime.now().timestamp()
            data_age = current_time - account_state.timestamp

            if data_age > self.config.max_data_staleness_seconds:
                events.append(
                    TripwireEvent(
                        severity="warning",
                        category="operational",
                        trigger="stale_data",
                        action=TripwireAction.FREEZE_NEW_RISK,
                        timestamp=datetime.now(),
                        details={
                            "data_age_seconds": data_age,
                            "max_allowed_seconds": self.config.max_data_staleness_seconds,
                            "last_update": account_state.timestamp,
                        },
                    )
                )

        # API failure count check
        if self.api_failure_count >= self.config.max_api_failure_count:
            events.append(
                TripwireEvent(
                    severity="critical",
                    category="operational",
                    trigger="api_failure_threshold",
                    action=TripwireAction.FREEZE_NEW_RISK,
                    timestamp=datetime.now(),
                    details={
                        "failure_count": self.api_failure_count,
                        "max_allowed": self.config.max_api_failure_count,
                    },
                )
            )

        return events

    def record_api_failure(self):
        """Record an API failure for tracking."""
        self.api_failure_count += 1

    def reset_api_failure_count(self):
        """Reset API failure count after successful operation."""
        self.api_failure_count = 0

    def reset_daily_tracking(self, current_portfolio_value: float):
        """Reset daily tracking metrics (call at start of new trading day).

        Args:
            current_portfolio_value: Current portfolio value to use as baseline
        """
        self.daily_start_portfolio_value = current_portfolio_value
        self.daily_loss_pct = 0.0

    def check_all_tripwires(
        self, account_state: AccountState, active_plan: StrategyPlanCard | None
    ) -> list[TripwireEvent]:
        """Check all tripwire conditions and return triggered events.

        Args:
            account_state: Current account state
            active_plan: Active strategy plan card (if any)

        Returns:
            List of all triggered tripwire events
        """
        events = []

        # Account safety checks (always run)
        events.extend(self._check_account_safety(account_state))

        # Plan invalidation checks (only if plan exists and checking is enabled)
        if active_plan and self.config.check_invalidation_triggers:
            events.extend(self._check_plan_invalidation(account_state, active_plan))

        # Operational health checks (always run)
        events.extend(self._check_operational_health(account_state))

        return events
