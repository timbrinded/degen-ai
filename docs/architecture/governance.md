# Governance System

The governance system manages strategy selection, portfolio allocation, and risk controls based on market conditions and performance.

## Components

### Governor
Central orchestrator that:
- Detects market regimes
- Selects appropriate strategies
- Manages portfolio allocation
- Enforces risk controls
- Persists state across restarts

### Regime Classifier
Identifies current market conditions:
- **Bull**: Strong uptrend, high momentum
- **Bear**: Strong downtrend, high fear
- **Ranging**: Low volatility, mean-reverting
- **Volatile**: High volatility, uncertain direction
- **Funding Extreme**: Unusual funding rates

Uses LLM-based classification with signal inputs.

### Scorekeeper
Tracks strategy performance:
- Win rate and profit factor
- Sharpe ratio and max drawdown
- Recent performance (7d, 30d)
- Trade count and average hold time
- Risk-adjusted returns

### Tripwires
Automatic risk controls:
- **Max Drawdown**: Pause strategy if DD exceeds threshold
- **Daily Loss Limit**: Stop trading after daily loss limit
- **Sharpe Ratio**: Disable underperforming strategies
- **Correlation**: Reduce allocation to correlated strategies

## Strategy Selection

### Plan Cards
Each strategy has metadata:
```markdown
---
regime: ["bull", "ranging"]
risk_level: medium
max_allocation: 0.3
min_sharpe: 0.5
---
```

### Selection Algorithm
1. Classify current regime
2. Filter strategies by regime compatibility
3. Check tripwire conditions
4. Score by recent performance
5. Allocate capital proportionally
6. Rebalance portfolio

## Portfolio Management

### Allocation Rules
- Minimum allocation: 10% per strategy
- Maximum allocation: 50% per strategy
- Maximum correlation: 0.7 between strategies
- Target portfolio volatility: 15%

### Rebalancing
Periodic rebalancing based on:
- Performance drift
- Regime changes
- Risk metric violations
- New strategy additions

## Configuration

```toml
[governance]
enabled = true
regime_check_interval_seconds = 3600
min_strategy_allocation = 0.1
max_strategy_allocation = 0.5

[governance.tripwires]
max_drawdown_pct = 15.0
max_daily_loss_pct = 5.0
min_sharpe_ratio = 0.5
lookback_days = 30

[portfolio]
rebalance_interval_seconds = 86400
target_volatility = 0.15
max_correlation = 0.7
```

## State Persistence

Governor state is saved to `state/governor.json`:
- Current regime
- Active strategies and allocations
- Performance history
- Tripwire status

This allows seamless restarts without losing context.

## Monitoring

Key metrics to track:
- Regime classification accuracy
- Strategy selection effectiveness
- Portfolio Sharpe ratio
- Tripwire activation frequency
- Rebalancing impact on performance
