"""Portfolio state management and rebalancing logic."""

from dataclasses import dataclass
from typing import Literal

from hyperliquid_agent.decision import TradeAction
from hyperliquid_agent.monitor import AccountState, Position


@dataclass
class TargetAllocation:
    """Target portfolio allocation as percentages."""

    allocations: dict[str, float]  # coin -> target percentage (0.0 to 1.0)
    strategy_id: str | None = None
    reasoning: str = ""

    def validate(self) -> bool:
        """Validate that allocations sum to approximately 1.0.

        Returns:
            True if valid, False otherwise
        """
        total = sum(self.allocations.values())
        return 0.99 <= total <= 1.01  # Allow small floating point errors


@dataclass
class PortfolioState:
    """Current portfolio state with allocation percentages."""

    total_value: float
    available_balance: float
    allocations: dict[str, float]  # coin -> current percentage
    positions: dict[str, Position]  # coin -> Position
    timestamp: float

    @classmethod
    def from_account_state(cls, account_state: AccountState) -> "PortfolioState":
        """Convert AccountState to PortfolioState with allocation percentages.

        Args:
            account_state: Current account state from monitor

        Returns:
            PortfolioState with computed allocations
        """
        total_value = account_state.portfolio_value
        if total_value == 0:
            total_value = account_state.available_balance

        # Build position map
        positions = {pos.coin: pos for pos in account_state.positions}

        # Calculate current allocations
        allocations: dict[str, float] = {}

        # Add cash allocation
        if total_value > 0:
            allocations["USDC"] = account_state.available_balance / total_value

        # Add position allocations
        for pos in account_state.positions:
            position_value = abs(pos.size * pos.current_price)
            if total_value > 0:
                allocations[pos.coin] = position_value / total_value

        return cls(
            total_value=total_value,
            available_balance=account_state.available_balance,
            allocations=allocations,
            positions=positions,
            timestamp=account_state.timestamp,
        )


@dataclass
class RebalancingPlan:
    """Ordered sequence of trades to achieve target allocation."""

    actions: list[TradeAction]
    estimated_cost: float  # Estimated fees and slippage
    reasoning: str = ""


class PortfolioRebalancer:
    """Generates rebalancing plans to move from current to target allocation."""

    def __init__(
        self,
        min_trade_value: float = 10.0,  # Minimum trade size in USD
        max_slippage_pct: float = 0.005,  # 0.5% max slippage
        rebalance_threshold: float = 0.05,  # 5% deviation triggers rebalance
    ) -> None:
        """Initialize the rebalancer.

        Args:
            min_trade_value: Minimum trade value to execute (avoid dust trades)
            max_slippage_pct: Maximum acceptable slippage percentage
            rebalance_threshold: Minimum allocation deviation to trigger rebalance
        """
        self.min_trade_value = min_trade_value
        self.max_slippage_pct = max_slippage_pct
        self.rebalance_threshold = rebalance_threshold

    def create_rebalancing_plan(
        self,
        current: PortfolioState,
        target: TargetAllocation,
        market_type: Literal["spot", "perp"] = "perp",
    ) -> RebalancingPlan:
        """Generate ordered list of trades to rebalance portfolio.

        Strategy:
        1. Close positions that need to be reduced or eliminated
        2. Open/increase positions that need to grow
        3. Respect capital constraints and minimum trade sizes

        Args:
            current: Current portfolio state
            target: Target allocation
            market_type: Market type for new positions

        Returns:
            RebalancingPlan with ordered actions
        """
        if not target.validate():
            return RebalancingPlan(
                actions=[],
                estimated_cost=0.0,
                reasoning="Invalid target allocation (does not sum to 1.0)",
            )

        actions: list[TradeAction] = []
        reasoning_parts: list[str] = []

        # Calculate deltas (target % - current %)
        deltas = self._calculate_deltas(current, target)

        # Filter out small deviations below threshold
        significant_deltas = {
            coin: delta for coin, delta in deltas.items() if abs(delta) >= self.rebalance_threshold
        }

        if not significant_deltas:
            return RebalancingPlan(
                actions=[],
                estimated_cost=0.0,
                reasoning="No significant deviations from target allocation",
            )

        # Phase 1: Close/reduce overweight positions (generates capital)
        for coin, delta in sorted(significant_deltas.items(), key=lambda x: x[1]):
            if delta >= 0:  # Skip underweight positions
                continue

            if coin == "USDC":  # Can't trade cash directly
                continue

            # Calculate size to reduce
            target_value = target.allocations.get(coin, 0.0) * current.total_value
            current_value = current.allocations.get(coin, 0.0) * current.total_value
            reduce_value = current_value - target_value

            if reduce_value < self.min_trade_value:
                continue

            # Get current position
            position = current.positions.get(coin)
            if not position:
                continue

            # Calculate size to sell
            size_to_reduce = reduce_value / position.current_price

            # Determine action type
            action_type: Literal["sell", "close"] = "sell"
            if target.allocations.get(coin, 0.0) == 0:
                # Closing entire position
                action_type = "close"
                size_to_reduce = position.size

            actions.append(
                TradeAction(
                    action_type=action_type,
                    coin=coin,
                    market_type=position.market_type,
                    size=size_to_reduce,
                    price=None,  # Market order
                    reasoning=f"Reduce {coin} from {current.allocations.get(coin, 0) * 100:.1f}% to {target.allocations.get(coin, 0) * 100:.1f}%",
                )
            )
            reasoning_parts.append(
                f"Reduce {coin}: {current.allocations.get(coin, 0) * 100:.1f}% → {target.allocations.get(coin, 0) * 100:.1f}%"
            )

        # Phase 2: Open/increase underweight positions (uses capital)
        # Calculate available capital after Phase 1 closes
        available_after_closes = current.available_balance
        for action in actions:
            if action.action_type in ["sell", "close"] and action.size:
                # Estimate proceeds from sale
                position = current.positions.get(action.coin)
                if position:
                    available_after_closes += action.size * position.current_price

        for coin, delta in sorted(significant_deltas.items(), key=lambda x: -x[1]):
            if delta <= 0:  # Skip overweight positions
                continue

            if coin == "USDC":  # Cash target handled implicitly
                continue

            # Calculate size to increase
            target_value = target.allocations.get(coin, 0.0) * current.total_value
            current_value = current.allocations.get(coin, 0.0) * current.total_value
            increase_value = target_value - current_value

            if increase_value < self.min_trade_value:
                continue

            # Check if we have enough capital
            if increase_value > available_after_closes:
                increase_value = available_after_closes

            if increase_value < self.min_trade_value:
                continue

            # Estimate current price (use existing position or assume we need market data)
            # For now, we'll need to get price from market data
            # This is a limitation - we need current market prices for coins we don't hold
            position = current.positions.get(coin)
            if position:
                estimated_price = position.current_price
            else:
                # Skip if we don't have price data
                # In production, this would fetch from market data
                reasoning_parts.append(f"Skipped {coin}: no price data available for new position")
                continue

            size_to_buy = increase_value / estimated_price

            actions.append(
                TradeAction(
                    action_type="buy",
                    coin=coin,
                    market_type=market_type,
                    size=size_to_buy,
                    price=None,  # Market order
                    reasoning=f"Increase {coin} from {current.allocations.get(coin, 0) * 100:.1f}% to {target.allocations.get(coin, 0) * 100:.1f}%",
                )
            )
            reasoning_parts.append(
                f"Increase {coin}: {current.allocations.get(coin, 0) * 100:.1f}% → {target.allocations.get(coin, 0) * 100:.1f}%"
            )

            # Update available capital
            available_after_closes -= increase_value

        # Estimate total cost (simplified)
        estimated_cost = len(actions) * 0.0005 * current.total_value  # Assume 0.05% per trade

        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "No rebalancing needed"

        return RebalancingPlan(
            actions=actions,
            estimated_cost=estimated_cost,
            reasoning=reasoning,
        )

    def _calculate_deltas(
        self, current: PortfolioState, target: TargetAllocation
    ) -> dict[str, float]:
        """Calculate allocation deltas (target - current).

        Args:
            current: Current portfolio state
            target: Target allocation

        Returns:
            Dictionary of coin -> delta percentage
        """
        deltas: dict[str, float] = {}

        # Get all coins from both current and target
        all_coins = set(current.allocations.keys()) | set(target.allocations.keys())

        for coin in all_coins:
            current_pct = current.allocations.get(coin, 0.0)
            target_pct = target.allocations.get(coin, 0.0)
            deltas[coin] = target_pct - current_pct

        return deltas
