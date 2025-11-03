# Trading Strategies

The agent includes 12 pre-built strategies covering various market conditions and trading styles.

## Strategy Categories

### Funding Rate Strategies
- **Funding Harvest Lite**: Capture funding rate arbitrage
- **Funding Flip Fade**: Trade funding rate reversals
- **Funding Calendar Clip**: Time-based funding opportunities

### Trend Following
- **Slowrider Trend**: Long-term trend following
- **Compression Pop**: Breakout from consolidation

### Mean Reversion
- **Range Sip**: Trade within established ranges
- **Markfix Mean Revert**: Revert to fair value

### Market Microstructure
- **OI Drift Divergence**: Open interest vs price divergence
- **Session Bias**: Time-of-day patterns

### Pairs & Correlation
- **Pairs Beta Sync**: Relative value between correlated assets

### Event-Driven
- **Unlock Watch**: Token unlock events
- **DCA Hedge**: Dollar-cost averaging with hedging

## Strategy Selection

Strategies are selected based on:
1. **Market Regime**: Bull, bear, ranging, volatile, funding extreme
2. **Performance**: Recent Sharpe ratio and win rate
3. **Risk Controls**: Tripwire status
4. **Correlation**: Portfolio diversification

## Adding Custom Strategies

Create a new markdown file in `strategies/`:

```markdown
---
regime: ["bull", "ranging"]
risk_level: medium
max_allocation: 0.3
min_sharpe: 0.5
---

# Strategy Name

## Overview
Brief description of the strategy logic.

## Entry Conditions
- Condition 1
- Condition 2

## Exit Conditions
- Exit rule 1
- Exit rule 2

## Risk Management
- Position sizing
- Stop loss rules
- Take profit targets

## Performance Expectations
- Expected win rate
- Typical hold time
- Best market conditions
```

The governance system will automatically discover and evaluate new strategies.

## Strategy Details

See individual strategy pages for detailed logic and parameters:
- [Funding Harvest](/strategies/funding-harvest)
- [Trend Following](/strategies/trend-following)
- More coming soon...
