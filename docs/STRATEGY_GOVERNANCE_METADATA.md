# Strategy Governance Metadata Guide

This document explains the governance-specific metadata fields added to strategy markdown files for the Hyperliquid Trading Agent.

## Overview

The governance system extends strategy files with metadata that encodes domain knowledge about time horizons, regime compatibility, and risk constraints. This metadata guides the LLM's planning decisions and helps the Strategy Governor enforce appropriate commitments.

## Metadata Location

Governance metadata is added to the YAML front matter of strategy markdown files in the `strategies/` directory.

**Example**:

```yaml
---
title: "Funding Harvest Lite"
id: funding-harvest-lite
markets: ["perps", "spot"]
directionality: "delta-neutral"
risk_profile: "conservative"
tags: ["carry", "hedged", "delta-neutral"]

# Governance metadata
intended_horizon: "hours"
minimum_dwell_minutes: 120
compatible_regimes: ["carry-friendly", "range-bound"]
avoid_regimes: ["event-risk", "trending"]
invalidation_triggers:
  - "Funding rate flips sign and remains negative for 3 consecutive windows"
  - "Mark-index divergence exceeds 50 bps for more than 15 minutes"
max_position_pct: 40.0
max_leverage: 3.0
expected_switching_cost_bps: 15.0
---

[Strategy documentation follows...]
```

## Governance Metadata Fields

### `intended_horizon`

**Type**: String (enum)  
**Required**: Yes  
**Values**: `"minutes"`, `"hours"`, `"days"`  
**Description**: The time scale over which this strategy is designed to operate

This field communicates the strategy's natural time horizon to the governance system.

**Guidelines**:
- `"minutes"`: Ultra-short-term strategies (5-60 minutes)
  - Examples: Scalping, micro-arbitrage, order book imbalances
  - Typically not suitable for governance (too fast)
  
- `"hours"`: Short to medium-term strategies (1-24 hours)
  - Examples: Funding arbitrage, intraday trends, session-based trades
  - Sweet spot for governance system
  
- `"days"`: Medium to long-term strategies (1-7+ days)
  - Examples: Swing trading, carry trades, macro positioning
  - Excellent for governance, enforces patience

**Impact**:
- Influences LLM's understanding of strategy commitment
- Guides appropriate dwell time selection
- Affects rebalancing schedule pacing

**Examples**:
```yaml
# Scalping strategy
intended_horizon: "minutes"

# Funding arbitrage
intended_horizon: "hours"

# Swing trading
intended_horizon: "days"
```

---

### `minimum_dwell_minutes`

**Type**: Integer  
**Required**: Yes  
**Range**: 15-10080 minutes (15 minutes to 1 week)  
**Description**: Minimum time this strategy must remain active before changes are permitted

This is the core commitment mechanism that prevents premature strategy abandonment.

**Guidelines**:
- Should align with `intended_horizon`:
  - Minutes horizon: 15-60 minutes dwell
  - Hours horizon: 60-480 minutes (1-8 hours) dwell
  - Days horizon: 480-10080 minutes (8 hours to 1 week) dwell

- Consider strategy characteristics:
  - Mean-reversion: Longer dwell (need time to revert)
  - Trend-following: Moderate dwell (trends can reverse)
  - Arbitrage: Shorter dwell (opportunities close quickly)

- Balance commitment vs flexibility:
  - Too short: Allows thrashing, defeats governance
  - Too long: Traps in bad strategies, misses opportunities

**Impact**:
- Enforced by Strategy Governor
- Can be overridden by regime changes or tripwires
- Prevents plan changes during dwell period

**Examples**:
```yaml
# Quick scalping strategy
minimum_dwell_minutes: 30

# Funding arbitrage (2 hours)
minimum_dwell_minutes: 120

# Swing trading (1 day)
minimum_dwell_minutes: 1440

# Long-term positioning (3 days)
minimum_dwell_minutes: 4320
```

**Tuning Recommendations**:
- Start with 2x the typical trade duration
- Increase if seeing excessive strategy changes
- Decrease if missing clear opportunities
- Review logs for dwell time violations

---

### `compatible_regimes`

**Type**: List of strings  
**Required**: Yes  
**Values**: `["trending", "range-bound", "carry-friendly", "event-risk"]`  
**Description**: Market regimes where this strategy performs well

Guides the LLM to select strategies appropriate for current market conditions.

**Regime Definitions**:

**`trending`**: Strong directional movement
- Characteristics: High ADX, clear SMA crossovers, sustained momentum
- Suitable for: Trend-following, breakout strategies
- Avoid: Mean-reversion, range-bound strategies

**`range-bound`**: Sideways consolidation
- Characteristics: Low volatility, tight price range, low ADX
- Suitable for: Mean-reversion, range trading, theta strategies
- Avoid: Trend-following, breakout strategies

**`carry-friendly`**: Positive funding environment
- Characteristics: Stable funding rates, low volatility, positive carry
- Suitable for: Funding arbitrage, delta-neutral carry
- Avoid: Directional strategies during funding flips

**`event-risk`**: Near scheduled macro events
- Characteristics: Approaching FOMC, CPI, jobs reports, major announcements
- Suitable for: Defensive positioning, reduced exposure
- Avoid: Most active strategies (governance locks changes)

**Guidelines**:
- List all regimes where strategy has positive expectancy
- Most strategies work in 1-3 regimes
- Be honest about regime compatibility (affects performance)
- Can list multiple regimes if strategy is versatile

**Impact**:
- LLM considers regime compatibility when proposing plans
- Regime changes can trigger plan reviews
- Incompatible regimes may trigger invalidation

**Examples**:
```yaml
# Trend-following strategy
compatible_regimes: ["trending"]

# Mean-reversion strategy
compatible_regimes: ["range-bound"]

# Funding arbitrage
compatible_regimes: ["carry-friendly", "range-bound"]

# Defensive strategy
compatible_regimes: ["event-risk", "range-bound"]

# Versatile strategy
compatible_regimes: ["trending", "range-bound", "carry-friendly"]
```

---

### `avoid_regimes`

**Type**: List of strings  
**Required**: Yes  
**Values**: `["trending", "range-bound", "carry-friendly", "event-risk"]`  
**Description**: Market regimes where this strategy performs poorly or has negative expectancy

Prevents the LLM from selecting strategies in unsuitable conditions.

**Guidelines**:
- List regimes where strategy has negative expectancy
- Include regimes with high risk of adverse outcomes
- Be conservative - better to avoid than force fit
- Should be mutually exclusive with `compatible_regimes`

**Common Patterns**:
- Trend strategies avoid range-bound
- Mean-reversion avoids trending
- Carry strategies avoid event-risk
- Most strategies avoid event-risk

**Impact**:
- LLM avoids proposing strategy in these regimes
- Entering avoided regime may trigger invalidation
- Regime detector monitors for regime shifts

**Examples**:
```yaml
# Trend-following strategy
avoid_regimes: ["range-bound", "event-risk"]

# Mean-reversion strategy
avoid_regimes: ["trending", "event-risk"]

# Funding arbitrage
avoid_regimes: ["event-risk", "trending"]

# Aggressive directional
avoid_regimes: ["event-risk"]
```

**Validation**:
- No overlap between `compatible_regimes` and `avoid_regimes`
- Together should cover most common regimes
- Okay to have neutral regimes (not in either list)

---

### `invalidation_triggers`

**Type**: List of strings  
**Required**: Yes  
**Description**: Natural language conditions that invalidate the strategy and allow immediate plan changes

These are explicit conditions that, when fired, override dwell times and permit immediate strategy changes.

**Guidelines**:
- Write clear, specific conditions
- Include measurable thresholds
- Cover key failure modes
- Use natural language (LLM or rule engine evaluates)

**Common Trigger Categories**:

**Price-based triggers**:
- "Price breaks below support level X"
- "Price exceeds stop loss at Y"
- "Drawdown exceeds Z%"

**Funding-based triggers** (for carry strategies):
- "Funding rate flips sign and remains negative for N windows"
- "Funding rate drops below X% per window"
- "Funding rate volatility exceeds Y%"

**Volatility-based triggers**:
- "Realized volatility exceeds X%"
- "Implied volatility spikes above Y%"
- "ATR increases by Z%"

**Basis-based triggers** (for arbitrage):
- "Perp-spot basis inverts"
- "Mark-index divergence exceeds X bps for Y minutes"
- "Basis compresses below Z bps"

**Liquidity-based triggers**:
- "Bid-ask spread exceeds X bps"
- "Order book depth drops below Y% of average"
- "Slippage exceeds Z bps on test orders"

**Delta-based triggers** (for hedged strategies):
- "Delta drift exceeds X despite rehedging"
- "Hedge ratio falls outside Y-Z range"
- "Correlation breaks down below W"

**Time-based triggers**:
- "Strategy active for X hours without profit"
- "No favorable entry for Y hours"
- "Approaching expiry/event in Z hours"

**Impact**:
- Evaluated by Tripwire Service every fast loop
- Firing triggers plan invalidation
- Allows immediate plan change despite dwell time
- Logged with severity and details

**Examples**:

```yaml
# Funding arbitrage strategy
invalidation_triggers:
  - "Funding rate flips sign and remains negative for 3 consecutive windows"
  - "Mark-index divergence exceeds 50 bps for more than 15 minutes"
  - "Spot depth collapses below 50% of 24h average"
  - "Delta drift exceeds 0.08 notional despite rehedging attempts"

# Trend-following strategy
invalidation_triggers:
  - "Price breaks below 20-period SMA with volume confirmation"
  - "ADX drops below 20 for 3 consecutive periods"
  - "Drawdown from peak exceeds 5%"
  - "Trend reversal signal confirmed by multiple indicators"

# Mean-reversion strategy
invalidation_triggers:
  - "Price breaks out of range with volume > 2x average"
  - "Volatility regime shifts from low to high"
  - "Position held for 24 hours without mean reversion"
  - "Correlation with mean breaks down"

# Carry trade strategy
invalidation_triggers:
  - "Funding rate turns negative for 6 consecutive hours"
  - "Volatility exceeds 60% annualized"
  - "Margin ratio drops below 25%"
  - "Correlation between legs breaks down below 0.7"
```

**Best Practices**:
- Include 3-6 triggers per strategy
- Mix different trigger types (price, funding, liquidity, etc.)
- Specify thresholds and durations
- Test triggers in backtests
- Review fired triggers in logs
- Update based on experience

---

### `max_position_pct`

**Type**: Float  
**Required**: Yes  
**Range**: 1.0-100.0 percent  
**Description**: Maximum percentage of portfolio to allocate to this strategy

Position sizing constraint that limits strategy exposure.

**Guidelines**:
- Conservative strategies: 30-50%
- Moderate strategies: 20-40%
- Aggressive strategies: 10-30%
- Experimental strategies: 5-15%

**Considerations**:
- Should reflect strategy risk profile
- Account for correlation with other positions
- Leave room for multiple strategies
- Consider liquidity constraints

**Impact**:
- Enforced during plan execution
- Included in Strategy Plan Card risk budget
- Affects rebalancing calculations
- Prevents over-concentration

**Examples**:
```yaml
# Conservative funding arbitrage
max_position_pct: 40.0

# Moderate trend-following
max_position_pct: 30.0

# Aggressive directional
max_position_pct: 20.0

# Experimental strategy
max_position_pct: 10.0
```

**Tuning Recommendations**:
- Start conservative (20-30%)
- Increase for proven strategies
- Decrease for volatile strategies
- Coordinate with `max_leverage`

---

### `max_leverage`

**Type**: Float  
**Required**: Yes  
**Range**: 1.0-20.0x  
**Description**: Maximum leverage allowed for this strategy

Leverage constraint that limits risk exposure.

**Guidelines**:
- Conservative strategies: 1.0-2.0x
- Moderate strategies: 2.0-5.0x
- Aggressive strategies: 5.0-10.0x
- Expert strategies: 10.0-20.0x

**Considerations**:
- Hyperliquid allows up to 50x leverage (use cautiously)
- Higher leverage = higher liquidation risk
- Should align with strategy volatility
- Account for funding costs on leveraged positions

**Impact**:
- Enforced during plan execution
- Included in Strategy Plan Card risk budget
- Affects position sizing calculations
- Monitored by tripwires

**Examples**:
```yaml
# Spot-only strategy
max_leverage: 1.0

# Conservative hedged strategy
max_leverage: 2.0

# Moderate perp strategy
max_leverage: 3.0

# Aggressive directional
max_leverage: 5.0

# Expert high-frequency
max_leverage: 10.0
```

**Safety Recommendations**:
- Start with 1.0-2.0x leverage
- Increase gradually based on performance
- Monitor margin ratio closely
- Set tripwires well above liquidation
- Consider funding costs at high leverage

---

### `expected_switching_cost_bps`

**Type**: Float  
**Required**: Yes  
**Range**: 5.0-200.0 basis points  
**Description**: Expected cost to switch from another strategy to this one

Estimated transaction cost for strategy rotation, used in change cost analysis.

**Components**:
- Trading fees (maker/taker)
- Slippage (market impact)
- Funding rate changes
- Opportunity cost

**Guidelines**:
- Low-frequency strategies: 10-30 bps
- Medium-frequency strategies: 30-60 bps
- High-frequency strategies: 60-100 bps
- Complex strategies: 100-200 bps

**Estimation Method**:
1. Calculate position changes from typical current state
2. Estimate fees: `position_size * fee_rate`
3. Estimate slippage: `position_size * spread / 2`
4. Add funding impact if applicable
5. Sum components and convert to bps

**Impact**:
- Used in plan change evaluation
- Compared against expected advantage
- Affects approval threshold
- Logged in change proposals

**Examples**:
```yaml
# Simple spot strategy (low cost)
expected_switching_cost_bps: 15.0

# Funding arbitrage (moderate cost, needs hedging)
expected_switching_cost_bps: 25.0

# Multi-leg strategy (higher cost)
expected_switching_cost_bps: 50.0

# Complex rebalancing (high cost)
expected_switching_cost_bps: 100.0
```

**Tuning Recommendations**:
- Start with conservative estimate (higher)
- Refine based on actual costs in logs
- Increase for illiquid markets
- Decrease for liquid markets
- Update periodically based on market conditions

---

## Complete Examples

### Funding Arbitrage Strategy

```yaml
---
title: "Funding Harvest Lite"
id: funding-harvest-lite
markets: ["perps", "spot"]
directionality: "delta-neutral"
risk_profile: "conservative"
tags: ["carry", "hedged", "delta-neutral"]

# Governance metadata
intended_horizon: "hours"
minimum_dwell_minutes: 120
compatible_regimes: ["carry-friendly", "range-bound"]
avoid_regimes: ["event-risk", "trending"]
invalidation_triggers:
  - "Funding rate flips sign and remains negative for 3 consecutive windows"
  - "Mark-index divergence exceeds 50 bps for more than 15 minutes"
  - "Spot depth collapses below 50% of 24h average"
  - "Delta drift exceeds 0.08 notional despite rehedging attempts"
max_position_pct: 40.0
max_leverage: 3.0
expected_switching_cost_bps: 15.0
---
```

### Trend-Following Strategy

```yaml
---
title: "Momentum Rider"
id: momentum-rider
markets: ["perps"]
directionality: "directional"
risk_profile: "moderate"
tags: ["trend", "momentum", "breakout"]

# Governance metadata
intended_horizon: "days"
minimum_dwell_minutes: 1440
compatible_regimes: ["trending"]
avoid_regimes: ["range-bound", "event-risk"]
invalidation_triggers:
  - "Price breaks below 20-period SMA with volume > 1.5x average"
  - "ADX drops below 20 for 3 consecutive 4-hour periods"
  - "Drawdown from entry exceeds 4%"
  - "Trend reversal confirmed by MACD and RSI divergence"
max_position_pct: 30.0
max_leverage: 3.0
expected_switching_cost_bps: 20.0
---
```

### Mean-Reversion Strategy

```yaml
---
title: "Range Bouncer"
id: range-bouncer
markets: ["perps", "spot"]
directionality: "mean-reverting"
risk_profile: "moderate"
tags: ["mean-reversion", "range", "oscillator"]

# Governance metadata
intended_horizon: "hours"
minimum_dwell_minutes: 240
compatible_regimes: ["range-bound"]
avoid_regimes: ["trending", "event-risk"]
invalidation_triggers:
  - "Price breaks range with volume > 2x average"
  - "Volatility regime shifts from low to high (RV > 50%)"
  - "Position held for 24 hours without mean reversion"
  - "Bollinger Bands expand beyond 2.5 standard deviations"
max_position_pct: 35.0
max_leverage: 2.0
expected_switching_cost_bps: 18.0
---
```

### Defensive Strategy

```yaml
---
title: "Event Shelter"
id: event-shelter
markets: ["spot"]
directionality: "defensive"
risk_profile: "conservative"
tags: ["defensive", "capital-preservation", "event"]

# Governance metadata
intended_horizon: "hours"
minimum_dwell_minutes: 60
compatible_regimes: ["event-risk", "range-bound"]
avoid_regimes: []
invalidation_triggers:
  - "Event passes and volatility normalizes below 30%"
  - "Market stabilizes with 2 hours of low volatility"
  - "Clear directional trend emerges post-event"
max_position_pct: 50.0
max_leverage: 1.0
expected_switching_cost_bps: 10.0
---
```

---

## Validation and Testing

### Metadata Validation

The agent validates governance metadata on startup:

**Required fields check**:
- All governance fields must be present
- Values must be within valid ranges
- Lists must contain valid regime names

**Consistency checks**:
- No overlap between `compatible_regimes` and `avoid_regimes`
- `minimum_dwell_minutes` aligns with `intended_horizon`
- `max_leverage` and `max_position_pct` are reasonable
- `expected_switching_cost_bps` is positive

**Common Validation Errors**:

```
Error: Missing required field 'minimum_dwell_minutes' in strategy 'my-strategy'
Error: Invalid regime 'bullish' in compatible_regimes (must be: trending, range-bound, carry-friendly, event-risk)
Error: Regime 'trending' appears in both compatible_regimes and avoid_regimes
Error: minimum_dwell_minutes (30) too short for intended_horizon 'days'
```

### Testing Metadata

**Test invalidation triggers**:
1. Create test scenarios matching trigger conditions
2. Verify tripwires fire correctly
3. Confirm plan invalidation occurs
4. Check logs for trigger details

**Test regime compatibility**:
1. Force regime changes in test environment
2. Verify LLM respects compatible/avoid regimes
3. Check plan proposals align with regimes
4. Monitor regime change handling

**Test dwell times**:
1. Activate plan and attempt immediate change
2. Verify rejection due to dwell time
3. Wait for dwell time to expire
4. Verify change is now permitted

**Test position limits**:
1. Propose plan exceeding `max_position_pct`
2. Verify position sizing enforcement
3. Check leverage calculations
4. Monitor tripwire responses

---

## Best Practices

### Metadata Design

1. **Be Specific**: Clear, measurable conditions in triggers
2. **Be Honest**: Accurate regime compatibility (affects performance)
3. **Be Conservative**: Start with stricter limits, relax gradually
4. **Be Consistent**: Align all fields with strategy characteristics
5. **Be Realistic**: Base estimates on actual market conditions

### Maintenance

1. **Review Regularly**: Update metadata based on performance
2. **Track Triggers**: Monitor which triggers fire and why
3. **Refine Costs**: Update switching costs based on actual data
4. **Adjust Limits**: Modify position/leverage limits as needed
5. **Document Changes**: Keep notes on metadata evolution

### Common Mistakes

**Mistake**: Dwell time too short
- **Problem**: Allows thrashing, defeats governance
- **Solution**: Increase to 2-3x typical trade duration

**Mistake**: Too many compatible regimes
- **Problem**: Strategy used inappropriately
- **Solution**: Be selective, 1-3 regimes maximum

**Mistake**: Vague invalidation triggers
- **Problem**: Triggers don't fire when they should
- **Solution**: Add specific thresholds and durations

**Mistake**: Underestimating switching costs
- **Problem**: Excessive strategy changes
- **Solution**: Increase estimate, monitor actual costs

**Mistake**: Excessive leverage limits
- **Problem**: High liquidation risk
- **Solution**: Start conservative, increase gradually

---

## Integration with Governance System

### How Metadata is Used

**Strategy Governor**:
- Enforces `minimum_dwell_minutes`
- Includes `max_position_pct` and `max_leverage` in risk budget
- Uses `expected_switching_cost_bps` in change cost calculation

**Regime Detector**:
- Matches current regime against `compatible_regimes`
- Checks for `avoid_regimes` violations
- Triggers plan review on regime changes

**Tripwire Service**:
- Evaluates `invalidation_triggers` every fast loop
- Fires tripwire events when triggers match
- Allows immediate plan changes on invalidation

**Decision Engine**:
- Presents metadata to LLM in prompt
- LLM considers regime compatibility
- LLM respects position and leverage limits
- LLM includes metadata in Strategy Plan Cards

### Metadata Flow

```
Strategy File (YAML)
    ↓
Loaded by Agent
    ↓
Presented to LLM
    ↓
Included in Strategy Plan Card
    ↓
Enforced by Governor
    ↓
Monitored by Tripwires
    ↓
Logged for Analysis
```

---

## Migration Guide

### Adding Governance Metadata to Existing Strategies

1. **Identify Strategy Characteristics**:
   - What's the natural time horizon?
   - Which regimes does it work in?
   - What are the failure modes?

2. **Set Time Horizon and Dwell**:
   ```yaml
   intended_horizon: "hours"  # or "minutes", "days"
   minimum_dwell_minutes: 120  # 2x typical trade duration
   ```

3. **Define Regime Compatibility**:
   ```yaml
   compatible_regimes: ["carry-friendly", "range-bound"]
   avoid_regimes: ["event-risk", "trending"]
   ```

4. **Write Invalidation Triggers**:
   ```yaml
   invalidation_triggers:
     - "Specific condition with threshold"
     - "Another condition with duration"
     - "Third condition with measurable criteria"
   ```

5. **Set Position Limits**:
   ```yaml
   max_position_pct: 30.0  # Conservative starting point
   max_leverage: 2.0       # Conservative starting point
   ```

6. **Estimate Switching Cost**:
   ```yaml
   expected_switching_cost_bps: 20.0  # Conservative estimate
   ```

7. **Test and Refine**:
   - Run with governance enabled
   - Monitor logs for metadata usage
   - Adjust based on observed behavior

---

## Related Documentation

- [Governance Configuration Guide](GOVERNANCE_CONFIG.md) - System-level governance settings
- [Configuration Guide](CONFIGURATION.md) - General agent configuration
- [README](../README.md) - Governance system overview

---

## Support

For issues or questions about strategy metadata:

1. Check validation errors on agent startup
2. Review this guide for field specifications
3. Consult example strategies in `strategies/` directory
4. Check logs for metadata-related events
5. Open an issue on GitHub with strategy file (redact sensitive info)
