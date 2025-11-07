# Compression Pop

A breakout strategy that trades volatility expansion after tight consolidation periods, capturing explosive moves when price breaks out of compression zones.

## Strategy Logic

### Overview
Identifies tight consolidation ranges (compression boxes) characterized by low ATR and flat Bollinger Bands, then trades the breakout when price moves beyond the box with volume confirmation. Adds to positions on retests of the breakout level.

### Entry Conditions
- Tight consolidation: ATR declining, Bollinger Bands flat
- Volume dry-up during compression phase
- Price closes beyond box boundary + buffer (0.15x ATR)
- Volume surge on breakout (or liquidity sweep pattern)
- No imminent event risk
- Confirmation: Price stays outside box for at least 1 bar

**Entry Logic:**
- **Long**: Close > box_high + buffer with volume surge
- **Short**: Close < box_low - buffer with volume surge

### Position Sizing
- Initial position: 2-3% of portfolio
- Add on retest of breakout level (maker orders)
- Maximum 40% allocation per position
- Maximum leverage: 4x

### Exit Conditions
- Price closes back inside compression box after 3 bars (fakeout)
- Volume surge fades: Volume drops below 50% of breakout bar within 5 bars
- Time stop reached: 90 minutes elapsed without follow-through
- Fakeout pattern: Price whipsaws through both box boundaries within 30 minutes
- Trailing stop hit: 2x ATR from highest/lowest point

## Risk Management

### Stop Loss
- Initial stop: Inside the compression box (opposite boundary)
- Trailing stop: 2x ATR after position moves 1R in favor

### Take Profit
- Primary target: 2-3x the box height
- Scale out: 1/3 at 1R, 1/3 at 2R, trail remaining 1/3

### Position Management
- Add on retest: Use maker limit orders at breakout level
- Scale in: Up to 3 entries if momentum continues
- Quick exit: If price closes back inside box

### Execution Strategy
- **Entry**: IOC/taker orders on initial breakout trigger
- **Adds**: Maker limit orders on retest of breakout level
- **Exit**: Taker orders on invalidation signals

## Performance Expectations

- **Win Rate**: 50-60%
- **Average Hold Time**: 1-3 hours (minimum 60 minutes)
- **Profit Factor**: 1.8-2.5
- **Max Drawdown**: 10-15%
- **Expected Switching Cost**: 18 bps per trade
- **Best Regimes**: Range-bound (pre-breakout), Trending (post-breakout)

## Configuration

Strategy parameters:

```toml
[strategy.compression-pop]
enabled = true
max_allocation = 0.40
max_leverage = 4.0
risk_per_trade = 0.02  # 2% risk

# Compression parameters
box_length = 30  # bars for box definition
buffer_atr_multiple = 0.15
min_compression_bars = 20

# Breakout parameters
volume_surge_threshold = 1.5  # 1.5x average volume
trail_stop_atr = 2.0
time_stop_minutes = 90

# Invalidation
max_bars_inside_box = 3
whipsaw_window_minutes = 30
```

## Technical Parameters

### Compression Detection
- **Box Length**: 20-50 bars
- **Buffer**: 0.15x ATR above/below box boundaries
- **Minimum Compression**: At least 20 bars of tight range
- **ATR Decline**: ATR should be declining during compression

### Breakout Confirmation
- **Volume Surge**: >1.5x average volume
- **Price Confirmation**: Close beyond box + buffer
- **Time Confirmation**: Stay outside box for at least 1 bar

### Risk Metrics
- **Trailing Stop**: 2.0x ATR
- **Time Stop**: 90 minutes
- **Fakeout Window**: 30 minutes

## Regime Compatibility

### Compatible Regimes
- **Range-bound**: Ideal for compression formation
- **Trending**: Good for breakout follow-through

### Avoid Regimes
- **Event-risk**: Scheduled events can cause fakeouts

## Example Trade

**Setup**: ETH consolidating in tight range
- **Box Range**: $2,400 - $2,450 (50-bar consolidation)
- **ATR**: $30 (declining from $50)
- **Volume**: Declining during compression
- **Breakout**: Price closes at $2,455 (above $2,450 + $4.50 buffer)
- **Volume**: 2.1x average (strong surge)
- **Entry**: Long at $2,456 (IOC order)
- **Stop Loss**: $2,395 (inside box, below $2,400)
- **Risk**: $61 per contract
- **Add**: Retest at $2,452, added 50% more size
- **Outcome**: Price rallied to $2,520, trailed stop to $2,490 (2x ATR = $60), exited at $2,490 for +$34 average profit (+1.4%)

## Monitoring

Key metrics to track:
- Compression box boundaries
- ATR levels and trends
- Volume patterns (dry-up then surge)
- Time in compression
- Breakout follow-through
- Retest opportunities
- False breakout rate

## Risk Warnings

- **Fakeout Risk**: Many breakouts fail and reverse quickly
- **Event Risk**: Scheduled events can cause whipsaw moves
- **Liquidity Risk**: Low liquidity during compression can cause slippage
- **Time Decay**: Capital locked during long compression periods
- **Overtrading**: Not every consolidation leads to explosive breakout
- **Correlation**: Multiple compression trades can correlate during market-wide breakouts

## Backtest Outline

```python
# Pseudocode for backtesting
def define_compression_box(lookback=30):
    box_high = max(high[-lookback:])
    box_low = min(low[-lookback:])
    return box_high, box_low

box_high, box_low = define_compression_box()
buffer = 0.15 * atr

if close > box_high + buffer and volume > 1.5 * avg_volume:
    enter_long()
    set_stop_loss(box_low)
    set_trailing_stop(2.0 * atr)
    set_time_stop(90_minutes)
    
    # Add on retest
    if price_retests(box_high) and volume_ok:
        add_to_position()

elif close < box_low - buffer and volume > 1.5 * avg_volume:
    enter_short()
    set_stop_loss(box_high)
    set_trailing_stop(2.0 * atr)
    set_time_stop(90_minutes)
    
    # Add on retest
    if price_retests(box_low) and volume_ok:
        add_to_position()

# Exit management
if close_inside_box for 3 consecutive bars:
    exit_position()  # Fakeout
elif volume_fades():
    exit_position()
elif time_stop_reached():
    exit_position()
elif trailing_stop_hit():
    exit_position()
```

## Why This Suits Small Capital + LLM Latency

- **Discrete triggers**: Breakouts are clear events, not continuous monitoring
- **No sub-second speed needed**: Breakout confirmation takes multiple bars
- **Maker adds**: Can use limit orders on retests for better fills
- **Low frequency**: Only trades when compression resolves
- **Clear invalidation**: Easy to identify failed breakouts
- **Tolerates latency**: Minutes-scale response time is acceptable
