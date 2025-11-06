# MarkFix Mean Revert

A basis arbitrage strategy that fades sustained mark-index price dislocations in perpetual futures, capturing convergence as the gap closes.

## Strategy Logic

### Overview
Monitors the gap between perpetual futures mark price and spot index price. When the gap persists for several minutes in quiet market conditions, the strategy fades the dislocation expecting mean reversion. This exploits temporary pricing inefficiencies between perp and spot markets.

### Entry Conditions
- Mark-index gap exceeds entry threshold (20-40 bps)
- Gap persists for minimum duration (3-5 minutes)
- Low volatility environment (below 60th percentile)
- No event tape or rapid repricing in progress
- Gap is not widening (stable or narrowing)
- Sufficient liquidity in both mark and index markets

**Gap Calculation:**
```
gap = (mark_price - index_price) / index_price
```

**Entry Logic:**
- **Long Perp**: gap < -20 bps for 3+ minutes (perp trading below index)
- **Short Perp**: gap > +20 bps for 3+ minutes (perp trading above index)

### Position Sizing
- Small positions: 1-2% of portfolio
- Maximum 25% allocation per position
- Maximum leverage: 2x
- Conservative sizing due to quick invalidation

### Exit Conditions
- Gap closes to exit threshold (5-10 bps)
- Gap widens beyond 2x entry threshold (invalidation)
- Volatility regime flips: Realized vol exceeds 80th percentile
- Event tape detected: Breaking news or rapid repricing
- Time stop reached: 20 minutes without convergence
- Stop loss: 1% from entry

## Risk Management

### Stop Loss
- Hard stop: 1% from entry price
- Gap widening stop: Exit if gap exceeds 2x entry threshold
- Time stop: 20 minutes maximum hold

### Take Profit
- Primary target: Gap closes to 5-10 bps
- Partial exit: 50% at 10 bps, 50% at 5 bps

### Position Management
- Enter with taker orders once confirmation met
- Add with maker orders if gap persists and widens slightly
- Quick exit on invalidation signals

### Execution Strategy
- **Entry**: Taker orders for immediate execution
- **Adds**: Maker orders if gap remains favorable
- **Exit**: Taker orders on target or invalidation

## Performance Expectations

- **Win Rate**: 70-80%
- **Average Hold Time**: 10-20 minutes (minimum 30 minutes)
- **Profit Factor**: 1.8-2.5
- **Max Drawdown**: 6-10%
- **Expected Switching Cost**: 22 bps per trade
- **Best Regimes**: Range-bound, Carry-friendly

## Configuration

Strategy parameters:

```toml
[strategy.markfix-mean-revert]
enabled = true
max_allocation = 0.25
max_leverage = 2.0
risk_per_trade = 0.015  # 1.5% risk

# Gap parameters
gap_entry_bps = 25  # 25 bps entry threshold
gap_exit_bps = 8    # 8 bps exit threshold
gap_invalidation_multiple = 2.0  # Exit if gap exceeds 2x entry

# Timing parameters
min_persistence_minutes = 4
time_stop_minutes = 20

# Volatility filters
max_volatility_percentile = 60
volatility_spike_percentile = 80

# Risk parameters
stop_loss_pct = 0.01
```

## Technical Parameters

### Gap Analysis
- **Entry Threshold**: 20-40 bps
- **Exit Threshold**: 5-10 bps
- **Persistence**: 3-5 minutes minimum
- **Invalidation**: Gap > 2x entry threshold

### Volatility Filters
- **Entry Filter**: Volatility < 60th percentile
- **Exit Filter**: Volatility > 80th percentile (regime flip)

### Risk Metrics
- **Stop Loss**: 1% from entry
- **Time Stop**: 20 minutes
- **Gap Stop**: 2x entry threshold

## Regime Compatibility

### Compatible Regimes
- **Range-bound**: Gaps more likely to mean revert
- **Carry-friendly**: Stable funding environment

### Avoid Regimes
- **Event-risk**: News can cause sustained dislocations
- **Trending**: Strong trends can maintain gaps

## Example Trade

**Setup**: BTC perp trading above index in quiet conditions
- **Mark Price**: $43,550
- **Index Price**: $43,440
- **Gap**: +25.3 bps (perp premium)
- **Persistence**: 4 minutes at this level
- **Volatility**: 42nd percentile (low)
- **Entry**: Short perp at $43,545
- **Stop Loss**: $43,980 (1% = $435)
- **Target**: $43,475 (gap closes to 8 bps)
- **Outcome**: Gap converged in 12 minutes. Mark price dropped to $43,475 while index stayed at $43,440. Exited at $43,475 for +$70 profit (+0.16%)

## Monitoring

Key metrics to track:
- Mark-index gap in real-time
- Gap persistence duration
- Volatility regime
- Event calendar and news flow
- Liquidity in both markets
- Gap convergence speed
- Win rate by gap size

## Risk Warnings

- **Event Risk**: News can cause sustained dislocations
- **Liquidity Risk**: Thin markets can have persistent gaps
- **Volatility Risk**: Sudden vol spikes can widen gaps
- **Execution Risk**: Slippage on taker orders can erode edge
- **Funding Risk**: Extreme funding can maintain gaps
- **Correlation**: Multiple mark-index trades can correlate

## Backtest Outline

```python
# Pseudocode for backtesting
def calculate_gap(mark_price, index_price):
    return (mark_price - index_price) / index_price

gap = calculate_gap(mark_price, index_price)
gap_history = []

# Track gap persistence
gap_history.append(gap)
if len(gap_history) > persistence_minutes:
    gap_history.pop(0)

# Check entry conditions
if len(gap_history) >= persistence_minutes:
    avg_gap = mean(gap_history)
    volatility = calculate_realized_vol()
    
    if abs(avg_gap) > gap_entry_bps / 10000 and volatility < 60th_percentile:
        if not event_tape_detected():
            if avg_gap > 0:
                # Perp trading above index → Short perp
                enter_short()
                set_stop_loss(entry * 1.01)
                set_target(entry * (1 - gap_exit_bps / 10000))
                set_time_stop(20_minutes)
                
            elif avg_gap < 0:
                # Perp trading below index → Long perp
                enter_long()
                set_stop_loss(entry * 0.99)
                set_target(entry * (1 + gap_exit_bps / 10000))
                set_time_stop(20_minutes)

# Exit management
current_gap = calculate_gap(mark_price, index_price)

if abs(current_gap) < gap_exit_bps / 10000:
    exit_position()  # Gap closed
elif abs(current_gap) > 2.0 * gap_entry_bps / 10000:
    exit_position()  # Gap widening (invalidation)
elif volatility > 80th_percentile:
    exit_position()  # Volatility spike
elif event_tape_detected():
    exit_position()
elif time_stop_reached():
    exit_position()
```

## Why This Suits Small Capital + LLM Latency

- **Signal requires persistence**: 3-5 minute confirmation, not instant
- **No need to be first**: Gap convergence is gradual
- **Clear entry/exit**: Gap thresholds are unambiguous
- **Quick trades**: Typically resolved in 10-20 minutes
- **Low frequency**: Only trades when clear dislocations occur
- **Tolerates latency**: Minutes-scale response time acceptable
