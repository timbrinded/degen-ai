# Funding Flip Fade

A contrarian mean-reversion strategy that fades extreme funding rates when market positioning becomes crowded.

## Strategy Logic

### Overview
Exploits funding rate extremes by taking the opposite side of crowded positions. When funding hits tail extremes with simultaneous open interest expansion, the strategy fades the crowded side once momentum stalls, anticipating mean reversion.

### Entry Conditions
- Funding z-score exceeds entry threshold (z > 2.0 or z < -2.0)
- Open interest growth exceeds 3% over 24 hours (indicates crowding)
- Momentum shows signs of stalling
- No fresh breaking news or major market events
- ADX < 30 (not in strong breakout regime)

**Entry Logic:**
- When `z_funding > 2.0` and OI expanding → Enter **short** (fade the longs)
- When `z_funding < -2.0` and OI expanding → Enter **long** (fade the shorts)

### Position Sizing
- Risk 0.5-1.0% of portfolio per trade
- Scale in on further funding extremity
- Maximum 35% allocation per position
- Maximum leverage: 4x

### Exit Conditions
- Funding z-score returns to neutral band (|z| < 0.5) for 4 consecutive windows
- ATR-based take profit hit (1.5x ATR from entry)
- ATR-based stop loss hit (1.0x ATR from entry)
- Time stop reached: 24 hours without mean reversion
- Fresh breaking news or major market event
- Strong breakout confirmed (volume surge and ADX > 30)

## Risk Management

### Stop Loss
- Hard stop: 1.0x ATR from entry price
- Time stop: Exit after 24 hours if no mean reversion

### Take Profit
- Primary target: Funding z-score returns to neutral (|z| < 0.5)
- Secondary target: 1.5x ATR profit from entry

### Position Management
- Scale in: Add to position if funding becomes more extreme
- Scale out: Reduce position as funding normalizes
- Use maker ladder orders at edges for better fills

### Execution Strategy
- **Entry**: Maker ladder orders at price edges
- **Exit**: Taker orders on exit signals or invalidation

## Performance Expectations

- **Win Rate**: 60-70%
- **Average Hold Time**: 4-12 hours (minimum 90 minutes)
- **Profit Factor**: 1.8-2.2
- **Max Drawdown**: 8-12%
- **Expected Switching Cost**: 12 bps per trade
- **Best Regimes**: Range-bound, Carry-friendly

## Configuration

Strategy parameters:

```toml
[strategy.funding-flip-fade]
enabled = true
max_allocation = 0.35
max_leverage = 4.0
risk_per_trade = 0.01  # 1% risk

# Funding parameters
lookback_windows = 72
z_enter = 2.0
z_exit = 0.5
oi_growth_threshold = 0.03  # 3% over 24h

# Risk parameters
tp_atr_multiple = 1.5
sl_atr_multiple = 1.0
time_stop_hours = 24
```

## Technical Parameters

### Funding Analysis
- **Lookback**: 72 funding windows (~24 days on 8h funding)
- **Entry Z-Score**: ±2.0 (tail extremes)
- **Exit Z-Score**: ±0.5 (neutral band)
- **OI Growth**: >3% per 24 hours

### Risk Metrics
- **Take Profit**: 1.5x ATR
- **Stop Loss**: 1.0x ATR
- **Time Stop**: 12-24 hours
- **ATR Period**: 14 bars

## Regime Compatibility

### Compatible Regimes
- **Range-bound**: Ideal for mean reversion
- **Carry-friendly**: Funding extremes more predictable

### Avoid Regimes
- **Trending**: Strong directional moves can extend funding extremes
- **Event-risk**: News can invalidate mean reversion thesis

## Example Trade

**Setup**: ETH funding rate hits extreme positive territory
- **Funding Z-Score**: +2.3 (very high, longs paying shorts)
- **OI Growth**: +4.2% over 24h (crowding into longs)
- **Momentum**: Price stalling at resistance, volume declining
- **Entry**: Short ETH at $2,450
- **ATR**: $80
- **Stop Loss**: $2,530 (1.0x ATR = $80)
- **Take Profit**: $2,330 (1.5x ATR = $120)
- **Outcome**: Funding normalized after 8 hours, z-score dropped to +0.4, exited at $2,380 for +$70 profit (+2.86%)

## Monitoring

Key metrics to track:
- Funding rate z-score trends
- Open interest changes and growth rate
- Momentum indicators (ADX, volume)
- ATR for dynamic stop/target placement
- Time in position
- Realized P&L vs expected funding income

## Risk Warnings

- **Trend Risk**: Strong trends can keep funding extreme for extended periods
- **Event Risk**: News can cause sudden directional moves against position
- **Liquidity Risk**: Ensure sufficient liquidity for exits
- **Time Decay**: Capital locked without returns if mean reversion delays
- **Correlation**: Avoid multiple funding fade trades on correlated assets

## Backtest Outline

```python
# Pseudocode for backtesting
if z_funding > z_enter and oi_growth > threshold and momentum_stalls():
    enter_short(size=calculate_size(z_funding))
    set_stop_loss(entry - 1.0 * atr)
    set_take_profit(entry - 1.5 * atr)
    set_time_stop(24_hours)
    
elif z_funding < -z_enter and oi_growth > threshold and momentum_stalls():
    enter_long(size=calculate_size(z_funding))
    set_stop_loss(entry + 1.0 * atr)
    set_take_profit(entry + 1.5 * atr)
    set_time_stop(24_hours)

# Exit management
if abs(z_funding) < z_exit for 4 consecutive windows:
    exit_position()
elif atr_trailing_stop_hit():
    exit_position()
elif time_stop_reached():
    exit_position()
```

## Why This Suits Small Capital + LLM Latency

- **Event-driven**: Decisions made every 15-60 minute candle, not tick-by-tick
- **No HFT edge required**: Strategy relies on positioning analysis, not speed
- **Maker-friendly**: Can use limit orders for better execution
- **Low frequency**: Few trades per week, manageable with LLM decision latency
- **Clear signals**: Funding extremes are unambiguous, reducing decision complexity
