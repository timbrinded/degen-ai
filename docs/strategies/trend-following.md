# Slowrider Trend

A patient trend-following strategy that captures sustained directional moves in crypto perpetual futures.

## Strategy Logic

### Overview
Identifies and rides established trends using multiple timeframe confirmation. Enters on pullbacks within the trend and holds for extended periods.

### Entry Conditions
- Price above/below key moving averages (50, 200 EMA)
- Higher highs and higher lows (uptrend) or lower lows and lower highs (downtrend)
- Momentum confirmation (RSI, MACD alignment)
- Entry on pullback to support/resistance
- Volume confirmation on breakout

### Position Sizing
- Base size: 2-3% of portfolio
- Scale in on multiple pullbacks
- Pyramid into winning positions
- Maximum 8% allocation per trend

### Exit Conditions
- Trend reversal signals (MA crossover, structure break)
- Momentum divergence
- Trailing stop hit (ATR-based)
- Time-based exit after 30+ days
- Target profit reached (3-5x risk)

## Risk Management

### Stop Loss
- Initial stop: Below recent swing low/high
- Trailing stop: 2x ATR from highest/lowest point
- Break-even stop after +1R profit

### Position Management
- Scale out 1/3 at 2R profit
- Scale out 1/3 at 4R profit
- Trail remaining 1/3 with wider stop

### Correlation
- Maximum 2 concurrent trend trades
- Avoid correlated assets in same direction

## Performance Expectations

- **Win Rate**: 40-50%
- **Average Hold Time**: 10-20 days
- **Profit Factor**: 2.0-3.0
- **Max Drawdown**: 12-18%
- **Best Regimes**: Bull, Bear (strong trends)

## Configuration

```markdown
---
regime: ["bull", "bear"]
risk_level: medium
max_allocation: 0.3
min_sharpe: 0.6
---
```

## Technical Indicators

### Trend Identification
- 50 EMA vs 200 EMA (golden/death cross)
- ADX > 25 (strong trend)
- Price structure (higher highs/lows)

### Entry Timing
- Pullback to 21 EMA
- RSI 40-60 (not overbought/oversold)
- Volume expansion on resumption

### Exit Signals
- 50 EMA crosses 200 EMA
- Price closes below 21 EMA
- RSI divergence
- Parabolic move (>3 standard deviations)

## Example Trade

**Setup**: BTC in strong uptrend
- **Entry**: $42,000 on pullback to 50 EMA
- **Stop Loss**: $40,500 (below swing low)
- **Risk**: $1,500 per contract
- **Target**: $46,500 (3R)
- **Outcome**: Held 15 days, scaled out at $44,000 (1/3), $46,000 (1/3), trailed final 1/3 to $48,500 for average exit of $46,167 (+9.9%)

## Monitoring

Key metrics:
- Trend strength (ADX)
- Pullback depth
- Volume patterns
- Correlation with other positions
- Risk-adjusted returns
