# Session Bias

A time-based strategy that exploits repeatable intraday session patterns by trading assets that show consistent directional drift during specific time windows.

## Strategy Logic

### Overview
Identifies assets with statistically significant session edges (positive mean and Sharpe ratio during specific time windows) and trades those sessions systematically. Overlays funding and volatility filters to avoid trading during unfavorable conditions.

### Entry Conditions
- Asset shows repeatable session drift (analyzed monthly)
- Session has positive mean return and Sharpe > 0.5 over rolling 30 days
- No macro events or breaking news scheduled during session
- Volatility below 70th percentile threshold at session entry
- Funding rate filter: Avoid sessions against strong funding bias
- Market not in strong trending regime (ADX < 30)

**Session Selection:**
- Analyze historical returns by time window (e.g., Asian session, US open, etc.)
- Select sessions with consistent positive edge
- Update session selection monthly based on rolling performance

### Position Sizing
- Fixed size per session: 2-3% of portfolio
- Maximum 25% allocation per position
- Maximum leverage: 2x
- Flat at session end (no overnight holds)

### Exit Conditions
- Session end time reached (scheduled exit)
- Macro event or breaking news announced during session
- Volatility exceeds 70th percentile threshold
- Session edge degrades: Rolling 30-day Sharpe drops below 0.5
- Regime change detected: Market transitions to strong trending behavior
- Stop loss: 2% from entry (safety net)

## Risk Management

### Stop Loss
- Hard stop: 2% from entry (rarely hit due to session exit)
- Session end: Flat at scheduled time regardless of P&L

### Take Profit
- No fixed target: Hold until session end
- Optional: Scale out at 1% profit, hold remainder

### Position Management
- Enter at session open
- Exit at session close
- No intra-session management (set and forget)
- Skip sessions on event days

### Execution Strategy
- **Entry**: Market orders at session open (or limit orders in pre-session)
- **Exit**: Market orders at session close

## Performance Expectations

- **Win Rate**: 55-65%
- **Average Hold Time**: 3-6 hours (minimum 180 minutes)
- **Profit Factor**: 1.4-1.8
- **Max Drawdown**: 6-10%
- **Expected Switching Cost**: 10 bps per trade
- **Best Regimes**: Range-bound, Carry-friendly

## Configuration

Strategy parameters:

```toml
[strategy.session-bias]
enabled = true
max_allocation = 0.25
max_leverage = 2.0
risk_per_trade = 0.02  # 2% risk

# Session parameters
session_windows = [
    { name = "asian", start = "00:00", end = "08:00", bias = "long" },
    { name = "london", start = "08:00", end = "16:00", bias = "short" },
    { name = "us", start = "14:00", end = "22:00", bias = "long" }
]

# Filters
skip_event_days = true
max_volatility_percentile = 70
min_sharpe_30d = 0.5
max_adx = 30

# Risk parameters
stop_loss_pct = 0.02
reanalyze_frequency_days = 30
```

## Technical Parameters

### Session Analysis
- **Lookback Period**: 30 days rolling
- **Minimum Sharpe**: 0.5 for session selection
- **Reanalysis Frequency**: Monthly

### Filters
- **Volatility Cap**: 70th percentile
- **ADX Threshold**: < 30 (avoid strong trends)
- **Event Calendar**: Skip scheduled macro events

### Risk Metrics
- **Stop Loss**: 2% from entry
- **Session Exit**: Mandatory flat at session end

## Regime Compatibility

### Compatible Regimes
- **Range-bound**: Session patterns more reliable
- **Carry-friendly**: Funding biases can enhance edges

### Avoid Regimes
- **Event-risk**: Macro events disrupt patterns
- **Trending**: Strong trends can override session biases

## Example Trade

**Setup**: BTC shows consistent positive drift during Asian session
- **Historical Edge**: +0.3% average return, Sharpe 0.8 over 30 days
- **Session**: Asian (00:00-08:00 UTC)
- **Entry Time**: 00:00 UTC
- **Entry Price**: $43,500
- **Volatility**: 45th percentile (below 70th threshold)
- **Event Check**: No scheduled events
- **Position Size**: 3% of portfolio
- **Exit Time**: 08:00 UTC (scheduled)
- **Exit Price**: $43,680
- **Outcome**: +$180 profit (+0.41% in 8 hours)

## Monitoring

Key metrics to track:
- Session performance (mean, Sharpe, win rate)
- Rolling 30-day statistics
- Event calendar compliance
- Volatility regime at entry
- Regime changes during session
- Slippage at entry/exit
- Overall strategy Sharpe ratio

## Risk Warnings

- **Edge Decay**: Session patterns can degrade over time
- **Event Risk**: Unexpected news can disrupt patterns
- **Overfitting**: Historical patterns may not persist
- **Slippage**: Market orders at session boundaries can have slippage
- **Regime Shifts**: Market structure changes can invalidate edges
- **Correlation**: Multiple session trades can correlate during market-wide moves

## Backtest Outline

```python
# Pseudocode for backtesting
def analyze_sessions(asset, lookback_days=30):
    """Analyze historical returns by session"""
    sessions = []
    for window in session_windows:
        returns = get_returns_in_window(asset, window, lookback_days)
        mean_return = returns.mean()
        sharpe = returns.mean() / returns.std() * sqrt(252)
        
        if sharpe > 0.5 and mean_return > 0:
            sessions.append({
                'window': window,
                'mean': mean_return,
                'sharpe': sharpe
            })
    return sessions

# Monthly reanalysis
if day_of_month == 1:
    selected_sessions = analyze_sessions(asset)

# Daily trading
for session in selected_sessions:
    if current_time == session.start_time:
        if not is_event_day() and volatility < 70th_percentile:
            enter_at_open(direction=session.bias)
            set_stop_loss(entry * 0.98)  # 2% stop
            
    if current_time == session.end_time:
        exit_position()  # Mandatory session end exit

# Exit management
if macro_event_announced():
    exit_position()
elif volatility > 70th_percentile:
    exit_position()
elif sharpe_30d < 0.5:
    exit_position()
elif regime_change_to_trending():
    exit_position()
```

## Why This Suits Small Capital + LLM Latency

- **Fully scheduled**: Cron-like execution, minimal real-time decisions
- **Easy to risk-cap**: Fixed session times and sizes
- **Low frequency**: Only trades specific sessions
- **No intra-session management**: Set and forget until session end
- **Clear rules**: Entry/exit times are predetermined
- **Tolerates latency**: Minutes-scale response time acceptable
