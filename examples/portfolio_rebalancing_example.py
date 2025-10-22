"""Example demonstrating portfolio rebalancing functionality."""

from hyperliquid_agent.monitor import AccountState, Position
from hyperliquid_agent.portfolio import (
    PortfolioRebalancer,
    PortfolioState,
    TargetAllocation,
)


def main():
    """Demonstrate portfolio rebalancing from current to target allocation."""
    
    # Example 1: Current portfolio with BTC and ETH positions
    print("=" * 60)
    print("Example 1: Rebalancing from 80% BTC to balanced portfolio")
    print("=" * 60)
    
    current_positions = [
        Position(
            coin="BTC",
            size=0.8,
            entry_price=50000.0,
            current_price=52000.0,
            unrealized_pnl=1600.0,
            market_type="perp",
        ),
    ]
    
    account_state = AccountState(
        portfolio_value=50000.0,
        available_balance=8400.0,  # 50000 - (0.8 * 52000)
        positions=current_positions,
        timestamp=1234567890.0,
    )
    
    # Convert to portfolio state
    portfolio_state = PortfolioState.from_account_state(account_state)
    
    print(f"\nCurrent Portfolio:")
    print(f"  Total Value: ${portfolio_state.total_value:,.2f}")
    print(f"  Available Cash: ${portfolio_state.available_balance:,.2f}")
    print(f"  Allocations:")
    for coin, pct in sorted(portfolio_state.allocations.items()):
        print(f"    {coin}: {pct*100:.1f}%")
    
    # Target: 40% BTC, 30% ETH, 30% USDC
    target = TargetAllocation(
        allocations={
            "BTC": 0.40,
            "ETH": 0.30,
            "USDC": 0.30,
        },
        strategy_id="balanced-growth",
    )
    
    print(f"\nTarget Allocation:")
    for coin, pct in sorted(target.allocations.items()):
        print(f"  {coin}: {pct*100:.1f}%")
    
    # Generate rebalancing plan
    rebalancer = PortfolioRebalancer(
        min_trade_value=10.0,
        rebalance_threshold=0.05,
    )
    
    plan = rebalancer.create_rebalancing_plan(portfolio_state, target)
    
    print(f"\nRebalancing Plan:")
    print(f"  Actions: {len(plan.actions)}")
    print(f"  Estimated Cost: ${plan.estimated_cost:.2f}")
    print(f"  Reasoning: {plan.reasoning}")
    
    print(f"\nActions to Execute:")
    for i, action in enumerate(plan.actions, 1):
        print(f"  {i}. {action.action_type.upper()} {action.size:.4f} {action.coin}")
        print(f"     Market: {action.market_type}")
        print(f"     Reasoning: {action.reasoning}")
    
    # Example 2: Small deviation - should not trigger rebalancing
    print("\n" + "=" * 60)
    print("Example 2: Small deviation - no rebalancing needed")
    print("=" * 60)
    
    current_positions_2 = [
        Position(
            coin="BTC",
            size=0.4,
            entry_price=50000.0,
            current_price=52000.0,
            unrealized_pnl=800.0,
            market_type="perp",
        ),
        Position(
            coin="ETH",
            size=6.0,
            entry_price=2500.0,
            current_price=2600.0,
            unrealized_pnl=600.0,
            market_type="perp",
        ),
    ]
    
    account_state_2 = AccountState(
        portfolio_value=50000.0,
        available_balance=14200.0,
        positions=current_positions_2,
        timestamp=1234567890.0,
    )
    
    portfolio_state_2 = PortfolioState.from_account_state(account_state_2)
    
    print(f"\nCurrent Portfolio:")
    print(f"  Total Value: ${portfolio_state_2.total_value:,.2f}")
    print(f"  Allocations:")
    for coin, pct in sorted(portfolio_state_2.allocations.items()):
        print(f"    {coin}: {pct*100:.1f}%")
    
    # Target is close to current
    target_2 = TargetAllocation(
        allocations={
            "BTC": 0.42,
            "ETH": 0.32,
            "USDC": 0.26,
        },
        strategy_id="balanced-growth",
    )
    
    print(f"\nTarget Allocation:")
    for coin, pct in sorted(target_2.allocations.items()):
        print(f"  {coin}: {pct*100:.1f}%")
    
    plan_2 = rebalancer.create_rebalancing_plan(portfolio_state_2, target_2)
    
    print(f"\nRebalancing Plan:")
    print(f"  Actions: {len(plan_2.actions)}")
    print(f"  Reasoning: {plan_2.reasoning}")
    
    # Example 3: Close all positions
    print("\n" + "=" * 60)
    print("Example 3: Exit all positions to cash")
    print("=" * 60)
    
    target_3 = TargetAllocation(
        allocations={
            "USDC": 1.0,
        },
        strategy_id="risk-off",
    )
    
    print(f"\nTarget Allocation:")
    for coin, pct in sorted(target_3.allocations.items()):
        print(f"  {coin}: {pct*100:.1f}%")
    
    plan_3 = rebalancer.create_rebalancing_plan(portfolio_state_2, target_3)
    
    print(f"\nRebalancing Plan:")
    print(f"  Actions: {len(plan_3.actions)}")
    print(f"  Reasoning: {plan_3.reasoning}")
    
    print(f"\nActions to Execute:")
    for i, action in enumerate(plan_3.actions, 1):
        print(f"  {i}. {action.action_type.upper()} {action.size:.4f} {action.coin}")
        print(f"     Reasoning: {action.reasoning}")


if __name__ == "__main__":
    main()
