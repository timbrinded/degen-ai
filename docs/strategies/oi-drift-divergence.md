# OI Drift Divergence

A positioning-based strategy that exploits divergences between price trends and open interest trends to identify distribution, absorption, and potential squeeze setups.

## Strategy Logic

### Overview
Monitors the relationship between price movement and open interest (OI) changes to detect when market positioning disagrees with price action. A rally with falling OI suggests distribution (longs exiting), while a dump with rising OI suggests shorts piling in (potential squeeze setup).

### Entry Conditions
- Price trend disagrees with OI trend for confirmation period
- OI_MA_fast (8-period) crosses OI_MA_slow (34-period) against price direction
- Funding rate skew agrees with divergence thesis
- OI data feed is reliable and fresh (< 10 minutes stale)
- Confirmation: Divergence persists for 3+ bars

**Divergence Patterns:**
- **Rally + Falling OI** → Distribution → Fade/hedge (short bias)
- **Dump + Rising OI** → Shorts piling → Squeeze setup (long bias)
- **Rally + Rising OI** → Healthy trend (no divergence)
- **Dump + Falling OI** → Healthy trend (no divergence)

### Position Sizing
- Start small: 1-2% initial position (or hedged)
- Add on break of structure confirming divergence
- Maximum 35% allocation per position
- Maximum leverage: 3x

### Exit Conditions
- OI trend reverses and aligns with price direction for 5 consecutive bars
- OI data feed becomes unreliable or stale (> 10 minutes)
- ATR stop hit: Price moves 1.5x ATR against position
- Divergence resolves: Price breaks structure in direction of OI trend
- Time-based exit: Position held without progress

## Risk Management

### Stop Loss
- ATR-based stop: 1.5x ATR from entry
- Structure stop: Beyond recent swing high/low

### Take Profit
- Primary target: Divergence resolution (OI aligns with price)
- Secondary target: 2-3x ATR profit

### Position Management
- Start small or hedged to test thesis
- Add on confirmation: Break of structure or funding alignment
- Scale out: 50% at 1.5 ATR, trail remaining 50%

### Execution Strategy
- **Entry**: Maker orders where possible
- **Adds**: Maker orders on structure breaks
- **Exit**: Taker orders on stops or targets

## Performance Expectations

- **Win Rate**: 55-65%
- **Average Hold Time**: 2-6 hours (minimum 90 minutes)
- **Profit Factor**: 1.7-2.3
- **Max Drawdown**: 10-14%
- **Expected Switching Cost**: 14 bps per trade
- **Best Regimes**: Trending, Range-bound

## Configuration

Strategy parameters:

```toml
[strategy.oi-drift-divergence]
enabled = true
max_allocation = 0.35
max_leverage = 3.0
risk_per_trade = 0.015  # 1.5% risk

# OI parameters
oi_ma_fast = 8
oi_ma_slow = 34
confirmation_bars = 3
max_oi_staleness_minutes = 10

# Risk parameters
stop_atr_multiple = 1.5
target_atr_multiple = 2.5
atr_period = 14

# Filters
require_funding_alignment = true
min_oi_divergence_pct = 2.0  # 2% OI change threshold
```

## Technical Parameters

### OI Analysis
- **OI MA Fast**: 8 periods
- **OI MA Slow**: 34 periods
- **Confirmation**: 3+ bars of divergence
- **Staleness Threshold**: 10 minutes max

### Divergence Detection
- **Price Trend**: Higher highs/lows or lower highs/lows
- **OI Trend**: Rising or falling OI MA
- **Minimum Divergence**: 2% OI change

### Risk Metrics
- **Stop Loss**: 1.5x ATR
- **Take Profit**: 2.5x ATR
- **ATR Period**: 14 bars

## Regime Compatibility

### Compatible Regimes
- **Trending**: Divergences more meaningful in trends
- **Range-bound**: Can identify distribution/accumulation

### Avoid Regimes
- **Event-risk**: OI can spike unpredictably on news

## Example Trade

**Setup**: ETH rally with falling OI (distribution signal)
- **Price Action**: Rally from $2,300 to $2,500 (+8.7%)
- **OI Trend**: Declining from 150M to 142M (-5.3%)
- **OI MA Cross**: 8-period crosses below 34-period
- **Funding**: Slightly positive but declining (longs exiting)
- **Confirmation**: 4 consecutive bars of divergence
- **Entry**: Short at $2,485 (small position, 1.5% of portfolio)
- **ATR**: $65
- **Stop Loss**: $2,583 (1.5x ATR = $98)
- **Target**: $2,323 (2.5x ATR = $162)
- **Outcome**: Price broke structure at $2,450, added to position. OI continued declining. Exited at $2,380 for +$105 average profit (+4.2%)

## Monitoring

Key metrics to track:
- OI absolute levels and trends
- OI moving average crossovers
- Price structure (highs/lows)
- Funding rate alignment
- OI data freshness and reliability
- Divergence duration
- Position P&L vs thesis

## Risk Warnings

- **Data Risk**: OI data can be noisy, delayed, or unreliable
- **False Signals**: Not all divergences lead to reversals
- **Trend Risk**: Strong trends can maintain divergences for extended periods
- **Liquidity Risk**: OI changes may reflect liquidity issues, not positioning
- **Correlation**: Multiple OI divergence trades can correlate
- **Complexity**: Requires understanding of positioning dynamics

## Backtest Outline

```python
# Pseudocode for backtesting
oi_ma_fast = moving_average(oi, period=8)
oi_ma_slow = moving_average(oi, period=34)
price_trend = detect_trend(price)
oi_trend = detect_trend(oi)

# Detect divergence
if price_trend == "up" and oi_trend == "down":
    divergence = "distribution"
    if confirm_bars >= 3 and funding_declining():
        enter_small_short_or_hedge()
        set_stop_loss(entry + 1.5 * atr)
        set_target(entry - 2.5 * atr)
        
        # Add on structure break
        if price_breaks_structure_down():
            add_to_position()

elif price_trend == "down" and oi_trend == "up":
    divergence = "squeeze_setup"
    if confirm_bars >= 3 and funding_negative():
        enter_small_long_or_hedge()
        set_stop_loss(entry - 1.5 * atr)
        set_target(entry + 2.5 * atr)
        
        # Add on structure break
        if price_breaks_structure_up():
            add_to_position()

# Exit management
if oi_aligns_with_price for 5 consecutive bars:
    exit_position()  # Divergence resolved
elif oi_data_stale():
    exit_position()
elif atr_stop_hit():
    exit_position()
elif target_reached():
    exit_position()
```

## Why This Suits Small Capital + LLM Latency

- **Slow decisions**: Emphasis on positioning analysis, not tick games
- **Confirmation required**: Multiple bars needed, tolerates latency
- **Maker-friendly**: Can use limit orders for entries and adds
- **Low frequency**: Only trades when clear divergences emerge
- **Start small**: Initial positions are small, reducing risk
- **Clear thesis**: Divergence patterns are well-defined
