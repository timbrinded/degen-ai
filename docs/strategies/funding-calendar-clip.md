# Funding Calendar Clip

A timing-based strategy that exploits predictable trader behavior around funding rate accrual windows, capturing de-risking patterns before and after funding payments.

## Strategy Logic

### Overview
Times entries around funding rate accrual windows to capture predictable behavior: traders often de-risk positions before funding payments (to avoid paying) and re-enter after. The strategy shorts into positive funding windows and longs into negative funding windows, exiting after the expected behavior materializes.

### Entry Conditions
- Funding rate consistently one-sided (above 70th percentile for positive, below 30th for negative)
- OI roll-off pattern near window start (traders de-risking)
- Pre-window timing: 30-90 minutes before funding accrual
- No major event risk during window
- Funding rate stable (not flipping signs unexpectedly)

**Entry Logic:**
- **Short**: Funding > threshold + OI roll-off in pre-window → Short, cover post-window
- **Long**: Funding < -threshold + OI roll-off in pre-window → Long, de-risk post-window

### Position Sizing
- Small, time-boxed positions: 2-3% of portfolio
- Maximum 30% allocation per position
- Maximum leverage: 3x
- Hard time stops to prevent capital lock

### Exit Conditions
- Post-window period ends (15-45 minutes after funding)
- Funding rate flips sign unexpectedly during window
- OI rotation pattern breaks: OI increases instead of rolling off
- Price volatility spike: Realized vol exceeds 2x normal
- Time stop reached: Maximum hold time exceeded
- Target profit reached: 0.5-1.0% from entry

## Risk Management

### Stop Loss
- Hard stop: 1.5% from entry
- Time stop: Exit at post-window end regardless of P&L

### Take Profit
- Primary target: 0.5-1.0% profit from entry
- Secondary target: Post-window end time

### Position Management
- Enter in pre-window (30-90 min before funding)
- Monitor OI behavior during window
- Exit in post-window (15-45 min after funding)
- No position carries beyond post-window

### Execution Strategy
- **Entry**: Maker orders if time permits, taker if urgent
- **Exit**: Taker orders around window end

## Performance Expectations

- **Win Rate**: 60-70%
- **Average Hold Time**: 1-2 hours (minimum 60 minutes)
- **Profit Factor**: 1.5-2.0
- **Max Drawdown**: 8-12%
- **Expected Switching Cost**: 16 bps per trade
- **Best Regimes**: Carry-friendly, Range-bound

## Configuration

Strategy parameters:

```toml
[strategy.funding-calendar-clip]
enabled = true
max_allocation = 0.30
max_leverage = 3.0
risk_per_trade = 0.02  # 2% risk

# Funding parameters
funding_threshold_percentile = 70  # 70th percentile for positive
min_funding_rate = 0.01  # 1% per 8h minimum

# Timing parameters
pre_window_minutes = 60  # Enter 60 min before funding
post_window_minutes = 30  # Exit 30 min after funding

# Risk parameters
stop_loss_pct = 0.015
target_profit_pct = 0.008
max_volatility_multiple = 2.0

# OI parameters
require_oi_rolloff = true
min_oi_decline_pct = 1.0  # 1% OI decline in pre-window
```

## Technical Parameters

### Funding Analysis
- **Threshold**: 70th percentile (positive) or 30th percentile (negative)
- **Minimum Rate**: 0.01% per 8h (or equivalent for different intervals)
- **Stability**: No sign flips in last 3 windows

### Timing Windows
- **Pre-Window**: 30-90 minutes before funding accrual
- **Post-Window**: 15-45 minutes after funding accrual
- **Total Hold**: Typically 1-2 hours

### Risk Metrics
- **Stop Loss**: 1.5% from entry
- **Take Profit**: 0.5-1.0% from entry
- **Volatility Filter**: < 2x normal realized vol

## Regime Compatibility

### Compatible Regimes
- **Carry-friendly**: Funding patterns more predictable
- **Range-bound**: Less directional noise

### Avoid Regimes
- **Event-risk**: News can disrupt timing patterns

## Example Trade

**Setup**: ETH funding consistently positive, traders de-risking before window
- **Funding Rate**: +0.015% per 8h (75th percentile, very high)
- **OI Trend**: Declining 2.3% in last hour (roll-off pattern)
- **Current Time**: 60 minutes before funding accrual
- **Entry**: Short ETH at $2,450
- **Entry Time**: 07:00 UTC (funding at 08:00 UTC)
- **Stop Loss**: $2,487 (1.5% = $37)
- **Target**: $2,430 (0.8% = $20)
- **Outcome**: OI continued declining into funding window. Price drifted to $2,438 by 08:30 UTC (post-window). Exited at $2,438 for +$12 profit (+0.49%)

## Monitoring

Key metrics to track:
- Funding rate levels and trends
- OI changes around funding windows
- Pre-window and post-window behavior
- Volatility during windows
- Time in position
- Pattern consistency over time
- Slippage at entry/exit

## Risk Warnings

- **Pattern Decay**: Funding window patterns can change over time
- **Volatility Risk**: Sudden moves can overwhelm small edges
- **Timing Risk**: Early/late entries can miss the pattern
- **Funding Flip**: Unexpected funding sign changes invalidate thesis
- **Liquidity Risk**: Thin liquidity around funding times can cause slippage
- **Correlation**: Multiple funding window trades can correlate

## Backtest Outline

```python
# Pseudocode for backtesting
funding_windows = get_funding_schedule()  # e.g., every 8 hours

for window in funding_windows:
    funding_rate = get_current_funding_rate()
    oi_trend = calculate_oi_trend(lookback_minutes=60)
    
    pre_window_time = window.time - timedelta(minutes=60)
    post_window_time = window.time + timedelta(minutes=30)
    
    # Check entry conditions at pre-window
    if current_time == pre_window_time:
        if funding_rate > threshold and oi_trend < -0.01:
            # Positive funding + OI roll-off → Short
            enter_short()
            set_stop_loss(entry * 1.015)
            set_target(entry * 0.992)
            set_time_stop(post_window_time)
            
        elif funding_rate < -threshold and oi_trend < -0.01:
            # Negative funding + OI roll-off → Long
            enter_long()
            set_stop_loss(entry * 0.985)
            set_target(entry * 1.008)
            set_time_stop(post_window_time)
    
    # Exit at post-window
    if current_time == post_window_time:
        exit_position()
    
    # Exit on invalidation
    if funding_flips_sign():
        exit_position()
    elif oi_increases_unexpectedly():
        exit_position()
    elif volatility > 2.0 * normal:
        exit_position()
```

## Why This Suits Small Capital + LLM Latency

- **Clock-driven**: Decisions based on scheduled funding times
- **Minutes-scale tolerant**: Pre/post windows are 30-90 minutes
- **Known cadence**: Funding windows are predictable (every 8h typically)
- **Time-boxed**: Hard time stops prevent capital lock
- **Clear signals**: Funding rates and OI trends are unambiguous
- **Low frequency**: Only trades around funding windows (3x per day max)
