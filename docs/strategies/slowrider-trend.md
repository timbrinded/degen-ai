# SlowRider Trend

A patient trend-following strategy that captures sustained directional moves using time-series momentum with ATR-based risk management.

## Strategy Logic

### Overview
Classic trend-following approach that identifies clear higher timeframe (HTF) trends and enters on pullbacks with trailing stops. Uses EMA crossovers, Donchian breakouts, and volatility filters to ride established trends while managing risk dynamically.

### Entry Conditions
- EMA21 > EMA55 for long bias (reverse for shorts)
- Price above weekly VWAP for longs (below for shorts)
- Donchian 20-bar breakout confirmation
- ATR percentile above minimum threshold (rising volatility)
- ADX > 20 (trending market, not choppy)
- Clear higher highs and higher lows (uptrend) or lower lows and lower highs (downtrend)

### Position Sizing
- Position size = `risk_per_trade / ATR`
- Maximum 50% allocation per position
- Maximum leverage: 3x
- Portfolio heat cap to limit total exposure

### Exit Conditions
- EMA crossover reversal: Fast EMA crosses below slow EMA for longs (above for shorts)
- Trailing stop hit: Price moves 3x ATR against position
- Market enters choppy regime: ADX drops below 20 for 3 consecutive periods
- Volatility collapse: ATR percentile drops below 30th percentile
- Time-based exit: Position held for extended period without progress

## Risk Management

### Stop Loss
- Initial stop: Below recent swing low/high
- Trailing stop: 3x ATR from highest/lowest point in trade
- Move to break-even after +1R profit

### Position Management
- Add on pullbacks to 21 EMA within trend
- Scale out partially at key resistance/support levels
- Trail remaining position with wider stop
- Use maker orders for adds, taker for exits

### Execution Strategy
- **Entry**: Maker orders on pullbacks to moving averages
- **Exit**: Taker orders on stop hits or reversal signals

## Performance Expectations

- **Win Rate**: 40-50%
- **Average Hold Time**: 4+ hours (minimum 240 minutes)
- **Profit Factor**: 2.0-3.0
- **Max Drawdown**: 12-18%
- **Expected Switching Cost**: 8 bps per trade
- **Best Regimes**: Trending (bull or bear)

## Configuration

Strategy parameters:

```toml
[strategy.slowrider-trend]
enabled = true
max_allocation = 0.50
max_leverage = 3.0
risk_per_trade = 0.02  # 2% risk

# Trend parameters
ema_fast = 21
ema_slow = 55
donchian_period = 20
atr_period = 14

# Risk parameters
trail_stop_atr = 3.0
min_adx = 20
min_atr_percentile = 30
```

## Technical Parameters

### Trend Identification
- **EMA Fast**: 21 periods
- **EMA Slow**: 55 periods
- **Donchian Breakout**: 20 bars
- **VWAP**: Weekly timeframe

### Volatility Filters
- **ATR Period**: 14 bars
- **Minimum ATR Percentile**: 30th percentile
- **ADX Threshold**: 20 (trending vs choppy)

### Risk Metrics
- **Trailing Stop**: 3.0x ATR
- **Position Sizing**: Risk per trade / ATR

## Regime Compatibility

### Compatible Regimes
- **Trending**: Ideal for capturing sustained directional moves
- **Bull/Bear**: Strong trends in either direction

### Avoid Regimes
- **Range-bound**: Choppy markets cause whipsaws
- **Event-risk**: Sudden reversals can hit stops

## Example Trade

**Setup**: BTC in strong uptrend
- **HTF Trend**: Clear higher highs and higher lows
- **EMA21**: $43,500 > EMA55: $42,000
- **Price**: $44,200 above weekly VWAP at $43,000
- **ADX**: 28 (strong trend)
- **Entry**: $43,600 on pullback to 21 EMA
- **ATR**: $1,200
- **Stop Loss**: $40,000 (below swing low, 3x ATR = $3,600)
- **Risk**: $3,600 per contract
- **Outcome**: Held for 6 days, trailed stop to $46,800 as price reached $50,400, exited at $46,800 for +$3,200 profit (+7.3%)

## Monitoring

Key metrics to track:
- EMA alignment and crossovers
- Trend strength (ADX)
- Volatility levels (ATR percentile)
- Pullback depth to moving averages
- Trailing stop distance
- Risk-adjusted returns (Sharpe ratio)

## Risk Warnings

- **Whipsaw Risk**: False breakouts in choppy markets can cause losses
- **Trend Exhaustion**: Late entries near trend end can result in quick reversals
- **Volatility Risk**: Low volatility can lead to tight stops being hit prematurely
- **Correlation**: Multiple trend trades in same direction increase portfolio risk
- **Drawdown**: Trend strategies typically have lower win rates but larger winners

## Backtest Outline

```python
# Pseudocode for backtesting
if htf_trend_up and ema_fast > ema_slow and atr_percentile > min_threshold:
    if price_pullback_to_ema21():
        enter_long()
        set_trailing_stop(3.0 * atr)
        
elif htf_trend_down and ema_fast < ema_slow and atr_percentile > min_threshold:
    if price_pullback_to_ema21():
        enter_short()
        set_trailing_stop(3.0 * atr)

# Exit management
if ema_crossover_reversal():
    exit_position()
elif trailing_stop_hit():
    exit_position()
elif adx < 20 for 3 consecutive periods:
    exit_position()
elif atr_percentile < 30:
    exit_position()
```

## Why This Suits Small Capital + LLM Latency

- **Low decision frequency**: Decisions made on bar closes, not tick-by-tick
- **Stop/scale logic tolerates latency**: Minute-scale response time is acceptable
- **Clear trend signals**: EMA crossovers and Donchian breakouts are unambiguous
- **Maker-friendly**: Can use limit orders on pullbacks for better fills
- **Few trades**: Trend strategies typically have low trade frequency
- **Systematic rules**: Reduces discretionary decision-making complexity
