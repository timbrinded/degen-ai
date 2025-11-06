# Governance Configuration Guide

This document provides detailed guidance on configuring the Strategy Governance System for the Hyperliquid Trading Agent.

## Overview

The governance system prevents "strategy thrash" by introducing multi-timescale decision-making, policy persistence, and change governance. Configuration is done through the `[governance]` section of `config.toml`.

## Quick Start

Add the governance section to your `config.toml`:

```toml
[governance]
fast_loop_interval_seconds = 10
medium_loop_interval_minutes = 30
slow_loop_interval_hours = 24

[governance.governor]
minimum_advantage_over_cost_bps = 50.0
cooldown_after_change_minutes = 60
partial_rotation_pct_per_cycle = 25.0
state_persistence_path = "state/governor.json"

[governance.regime_detector]
confirmation_cycles_required = 3
hysteresis_enter_threshold = 0.7
hysteresis_exit_threshold = 0.4
event_lock_window_hours_before = 2
event_lock_window_hours_after = 1

[governance.tripwire]
min_margin_ratio = 0.15
liquidation_proximity_threshold = 0.25
daily_loss_limit_pct = 5.0
max_data_staleness_seconds = 300
max_api_failure_count = 3
```

## Configuration Sections

### `[governance]` - Loop Timing

Controls the frequency of the three governance loops.

#### `fast_loop_interval_seconds`

**Type**: Integer  
**Default**: 10  
**Range**: 5-60 seconds  
**Description**: How often the fast loop executes to follow the active plan

The fast loop runs deterministically without LLM queries, executing the active Strategy Plan Card's targets.

**Tuning Guidance**:
- **5-10 seconds**: High-frequency execution, responsive to market changes
- **10-20 seconds**: Standard execution, good balance
- **20-60 seconds**: Lower frequency, reduces API calls

**Considerations**:
- Lower values increase API usage and costs
- Must be fast enough to manage orders and respond to tripwires
- Hyperliquid API rate limits apply

**Recommended Settings**:
- Hobby trading: 10-15 seconds
- Active trading: 5-10 seconds
- Conservative: 20-30 seconds

#### `medium_loop_interval_minutes`

**Type**: Integer  
**Default**: 30  
**Range**: 5-240 minutes  
**Description**: How often the medium loop runs to review and maintain Strategy Plan Cards

The medium loop consults the LLM when plan review is permitted, evaluates plan changes, and manages rebalancing.

**Tuning Guidance**:
- **5-15 minutes**: Frequent plan reviews, responsive to regime changes
- **15-60 minutes**: Standard planning horizon, good for most strategies
- **60-240 minutes**: Long-term planning, reduces LLM costs

**Considerations**:
- Lower values increase LLM API costs significantly
- Should align with strategy time horizons (e.g., 30 min for hourly strategies)
- Dwell times prevent changes even if loop runs frequently

**Recommended Settings**:
- Hobby trading: 30-60 minutes
- Active trading: 15-30 minutes
- Conservative: 60-120 minutes

#### `slow_loop_interval_hours`

**Type**: Integer  
**Default**: 24  
**Range**: 4-168 hours  
**Description**: How often the slow loop runs for regime detection and macro analysis

The slow loop detects regime changes, updates macro calendars, and can override dwell times when regimes shift.

**Tuning Guidance**:
- **4-8 hours**: Frequent regime checks, responsive to market shifts
- **12-24 hours**: Daily regime analysis, standard approach
- **24-168 hours**: Weekly analysis, very long-term focus

**Considerations**:
- Regime changes can also be detected during medium loops
- Slow loop provides forced re-evaluation regardless of dwell times
- Lower values increase computational overhead

**Recommended Settings**:
- Hobby trading: 24 hours (daily)
- Active trading: 12 hours (twice daily)
- Conservative: 24-48 hours

---

### `[governance.governor]` - Plan Persistence

Controls how the Strategy Governor enforces plan commitments and evaluates changes.

#### `minimum_advantage_over_cost_bps`

**Type**: Float  
**Default**: 50.0  
**Range**: 10.0-200.0 basis points  
**Description**: Minimum net advantage required to approve plan changes

The expected advantage from a new strategy must exceed the switching cost by at least this amount.

**Formula**: `net_advantage = expected_advantage - change_cost`

**Tuning Guidance**:
- **10-25 bps**: Aggressive, allows frequent changes
- **50-100 bps**: Balanced, prevents unprofitable switches
- **100-200 bps**: Conservative, requires strong conviction

**Considerations**:
- Higher values reduce strategy thrashing but may miss opportunities
- Should be calibrated to typical strategy edge (e.g., 50 bps for 100-200 bps edge)
- Change costs include fees, slippage, funding impact, and opportunity cost

**Recommended Settings**:
- Hobby trading: 50-75 bps
- Active trading: 25-50 bps
- Conservative: 75-150 bps

#### `cooldown_after_change_minutes`

**Type**: Integer  
**Default**: 60  
**Range**: 15-240 minutes  
**Description**: Minimum time between plan changes

After activating a new plan, this cooldown prevents immediate subsequent changes.

**Tuning Guidance**:
- **15-30 minutes**: Short cooldown, allows rapid adaptation
- **60-120 minutes**: Standard cooldown, prevents flip-flopping
- **120-240 minutes**: Long cooldown, enforces commitment

**Considerations**:
- Works in conjunction with dwell times (both must be satisfied)
- Tripwires can override cooldowns for safety
- Regime changes can override cooldowns

**Recommended Settings**:
- Hobby trading: 60-90 minutes
- Active trading: 30-60 minutes
- Conservative: 90-180 minutes

#### `partial_rotation_pct_per_cycle`

**Type**: Float  
**Default**: 25.0  
**Range**: 10.0-100.0 percent  
**Description**: Percentage of portfolio to rotate per medium loop cycle during rebalancing

Large strategy changes are executed gradually over multiple cycles to reduce market impact.

**Tuning Guidance**:
- **10-20%**: Very gradual, minimal market impact
- **25-50%**: Standard rotation, balanced approach
- **50-100%**: Fast rotation, higher slippage

**Considerations**:
- Lower values reduce slippage but extend rebalancing time
- 25% means 4 cycles to complete full rotation
- No new plan changes allowed until rebalancing completes

**Recommended Settings**:
- Hobby trading: 25-33% (3-4 cycles)
- Active trading: 33-50% (2-3 cycles)
- Conservative: 20-25% (4-5 cycles)

#### `state_persistence_path`

**Type**: String  
**Default**: "state/governor.json"  
**Description**: Path to persist governor state for recovery after restarts

The governor saves active plan, timing state, and rebalance progress to survive restarts.

**Considerations**:
- Path is relative to project root
- Directory is created automatically if it doesn't exist
- File contains sensitive trading state (not secrets)
- Should be backed up regularly

**Recommended Settings**:
- Standard: "state/governor.json"
- Multiple instances: "state/governor-{instance}.json"

---

### `[governance.regime_detector]` - Regime Classification

Controls how the Regime Detector classifies markets and confirms regime changes.

#### `confirmation_cycles_required`

**Type**: Integer  
**Default**: 3  
**Range**: 2-10 cycles  
**Description**: Number of medium loop cycles required to confirm regime change

Prevents false regime changes from temporary market noise by requiring sustained signals.

**Tuning Guidance**:
- **2-3 cycles**: Responsive to regime shifts
- **3-5 cycles**: Balanced confirmation
- **5-10 cycles**: Very conservative, avoids false positives

**Considerations**:
- Higher values delay regime change detection
- With 30-minute medium loop, 3 cycles = 90 minutes confirmation
- Regime changes can override dwell times, so this is important

**Recommended Settings**:
- Hobby trading: 3-4 cycles
- Active trading: 2-3 cycles
- Conservative: 4-6 cycles

#### `hysteresis_enter_threshold`

**Type**: Float  
**Default**: 0.7  
**Range**: 0.5-0.9  
**Description**: Confidence threshold to enter a new regime

The percentage of recent cycles that must agree on the new regime before switching.

**Tuning Guidance**:
- **0.5-0.6**: Low threshold, easier to switch regimes
- **0.6-0.8**: Balanced threshold
- **0.8-0.9**: High threshold, requires strong evidence

**Considerations**:
- Must be higher than `hysteresis_exit_threshold` to create hysteresis
- With 3 confirmation cycles, 0.7 means 2.1 cycles must agree (rounds to 3)
- Higher values prevent premature regime switches

**Recommended Settings**:
- Hobby trading: 0.65-0.75
- Active trading: 0.60-0.70
- Conservative: 0.75-0.85

#### `hysteresis_exit_threshold`

**Type**: Float  
**Default**: 0.4  
**Range**: 0.3-0.7  
**Description**: Confidence threshold to exit current regime

Lower than enter threshold to create hysteresis and prevent ping-ponging.

**Tuning Guidance**:
- **0.3-0.4**: Wide hysteresis band, sticky regimes
- **0.4-0.5**: Moderate hysteresis
- **0.5-0.6**: Narrow hysteresis, easier to exit

**Considerations**:
- Should be 0.2-0.3 below `hysteresis_enter_threshold`
- Wider bands (larger difference) prevent regime oscillation
- Too wide can trap in wrong regime

**Recommended Settings**:
- Hobby trading: 0.35-0.45 (0.3 below enter)
- Active trading: 0.40-0.50 (0.2 below enter)
- Conservative: 0.30-0.40 (0.4 below enter)

#### `event_lock_window_hours_before`

**Type**: Integer  
**Default**: 2  
**Range**: 0-12 hours  
**Description**: Hours before scheduled macro event to lock plan changes

Prevents strategy changes immediately before high-impact events (FOMC, CPI, jobs reports).

**Tuning Guidance**:
- **0-1 hours**: Minimal lock, allows late positioning
- **2-4 hours**: Standard lock, avoids pre-event volatility
- **4-12 hours**: Extended lock, very conservative

**Considerations**:
- Tripwires can still override during lock windows
- Events include FOMC, CPI, jobs reports, major earnings
- Lock windows are configured per event in macro calendar

**Recommended Settings**:
- Hobby trading: 2-3 hours
- Active trading: 1-2 hours
- Conservative: 3-6 hours

#### `event_lock_window_hours_after`

**Type**: Integer  
**Default**: 1  
**Range**: 0-6 hours  
**Description**: Hours after scheduled macro event to lock plan changes

Allows volatility to settle before making strategy decisions.

**Tuning Guidance**:
- **0-0.5 hours**: Minimal lock, quick reaction
- **1-2 hours**: Standard lock, lets dust settle
- **2-6 hours**: Extended lock, waits for full digestion

**Considerations**:
- Shorter than before-window since event has passed
- Some events (FOMC) have press conferences extending volatility
- Can be adjusted per event type

**Recommended Settings**:
- Hobby trading: 1-2 hours
- Active trading: 0.5-1 hour
- Conservative: 2-4 hours

---

### `[governance.tripwire]` - Safety Monitoring

Controls independent safety tripwires that can override LLM decisions.

#### `min_margin_ratio`

**Type**: Float  
**Default**: 0.15  
**Range**: 0.05-0.50  
**Description**: Minimum margin ratio before triggering safety tripwire

Triggers when account margin falls below this level.

**Tuning Guidance**:
- **0.05-0.10**: Aggressive, close to exchange minimum
- **0.15-0.25**: Balanced, safe buffer
- **0.25-0.50**: Conservative, large safety margin

**Considerations**:
- Hyperliquid minimum is typically 0.03-0.05 (3-5%)
- Lower values allow higher leverage but increase liquidation risk
- Tripwire freezes new risk and may cut positions

**Recommended Settings**:
- Hobby trading: 0.15-0.20
- Active trading: 0.10-0.15
- Conservative: 0.20-0.30

#### `liquidation_proximity_threshold`

**Type**: Float  
**Default**: 0.25  
**Range**: 0.10-0.50  
**Description**: Proximity to liquidation price that triggers warning

Triggers when position is within this percentage of liquidation price.

**Formula**: `proximity = (current_price - liquidation_price) / current_price`

**Tuning Guidance**:
- **0.10-0.15**: Tight threshold, allows close calls
- **0.20-0.30**: Standard threshold, reasonable buffer
- **0.30-0.50**: Wide threshold, very conservative

**Considerations**:
- Lower values allow positions closer to liquidation
- Triggers position reduction or closure
- Should coordinate with `min_margin_ratio`

**Recommended Settings**:
- Hobby trading: 0.20-0.30
- Active trading: 0.15-0.25
- Conservative: 0.30-0.40

#### `daily_loss_limit_pct`

**Type**: Float  
**Default**: 5.0  
**Range**: 1.0-20.0 percent  
**Description**: Maximum daily loss percentage before cutting positions

Absolute safety limit - cuts positions when daily loss exceeds this percentage.

**Tuning Guidance**:
- **1-3%**: Tight limit, protects capital aggressively
- **3-7%**: Standard limit, reasonable drawdown tolerance
- **7-20%**: Wide limit, allows larger drawdowns

**Considerations**:
- Measured from daily start portfolio value
- Triggers immediate position reduction
- Resets at start of each day
- Should align with overall risk tolerance

**Recommended Settings**:
- Hobby trading: 3-5%
- Active trading: 5-10%
- Conservative: 2-3%

#### `max_data_staleness_seconds`

**Type**: Integer  
**Default**: 300  
**Range**: 60-1800 seconds  
**Description**: Maximum seconds of data staleness before freezing new risk

Prevents trading on stale data when API is slow or unresponsive.

**Tuning Guidance**:
- **60-180 seconds**: Tight tolerance, requires fresh data
- **300-600 seconds**: Standard tolerance (5-10 minutes)
- **600-1800 seconds**: Loose tolerance, allows delays

**Considerations**:
- Freezes new risk but doesn't close positions
- Useful during API outages or network issues
- Should be longer than typical API response time

**Recommended Settings**:
- Hobby trading: 300-600 seconds
- Active trading: 180-300 seconds
- Conservative: 600-900 seconds

#### `max_api_failure_count`

**Type**: Integer  
**Default**: 3  
**Range**: 1-10 failures  
**Description**: Maximum consecutive API failures before triggering operational tripwire

Freezes new risk when API becomes unreliable.

**Tuning Guidance**:
- **1-2 failures**: Strict tolerance, quick reaction
- **3-5 failures**: Standard tolerance, allows transient issues
- **5-10 failures**: Loose tolerance, patient with problems

**Considerations**:
- Counts consecutive failures (resets on success)
- Triggers operational health tripwire
- Should coordinate with retry logic in agent config

**Recommended Settings**:
- Hobby trading: 3-5 failures
- Active trading: 2-3 failures
- Conservative: 5-7 failures

---

## Configuration Profiles

### Hobby Trader Profile

For casual traders with small capital, infrequent monitoring, and low risk tolerance.

```toml
[governance]
fast_loop_interval_seconds = 15
medium_loop_interval_minutes = 60
slow_loop_interval_hours = 24

[governance.governor]
minimum_advantage_over_cost_bps = 75.0
cooldown_after_change_minutes = 90
partial_rotation_pct_per_cycle = 25.0
state_persistence_path = "state/governor.json"

[governance.regime_detector]
confirmation_cycles_required = 4
hysteresis_enter_threshold = 0.75
hysteresis_exit_threshold = 0.40
event_lock_window_hours_before = 3
event_lock_window_hours_after = 2

[governance.tripwire]
min_margin_ratio = 0.20
liquidation_proximity_threshold = 0.30
daily_loss_limit_pct = 3.0
max_data_staleness_seconds = 600
max_api_failure_count = 5
```

**Characteristics**:
- Infrequent plan reviews (hourly)
- High switching threshold (75 bps)
- Conservative safety limits (3% daily loss)
- Wide event lock windows
- Patient with API issues

### Active Trader Profile

For engaged traders with moderate capital, regular monitoring, and balanced risk tolerance.

```toml
[governance]
fast_loop_interval_seconds = 10
medium_loop_interval_minutes = 30
slow_loop_interval_hours = 12

[governance.governor]
minimum_advantage_over_cost_bps = 50.0
cooldown_after_change_minutes = 60
partial_rotation_pct_per_cycle = 33.0
state_persistence_path = "state/governor.json"

[governance.regime_detector]
confirmation_cycles_required = 3
hysteresis_enter_threshold = 0.70
hysteresis_exit_threshold = 0.40
event_lock_window_hours_before = 2
event_lock_window_hours_after = 1

[governance.tripwire]
min_margin_ratio = 0.15
liquidation_proximity_threshold = 0.25
daily_loss_limit_pct = 5.0
max_data_staleness_seconds = 300
max_api_failure_count = 3
```

**Characteristics**:
- Standard plan reviews (30 minutes)
- Balanced switching threshold (50 bps)
- Moderate safety limits (5% daily loss)
- Standard event lock windows
- Standard API tolerance

### Aggressive Trader Profile

For experienced traders with larger capital, active monitoring, and higher risk tolerance.

```toml
[governance]
fast_loop_interval_seconds = 5
medium_loop_interval_minutes = 15
slow_loop_interval_hours = 8

[governance.governor]
minimum_advantage_over_cost_bps = 25.0
cooldown_after_change_minutes = 30
partial_rotation_pct_per_cycle = 50.0
state_persistence_path = "state/governor.json"

[governance.regime_detector]
confirmation_cycles_required = 2
hysteresis_enter_threshold = 0.65
hysteresis_exit_threshold = 0.45
event_lock_window_hours_before = 1
event_lock_window_hours_after = 0.5

[governance.tripwire]
min_margin_ratio = 0.10
liquidation_proximity_threshold = 0.20
daily_loss_limit_pct = 8.0
max_data_staleness_seconds = 180
max_api_failure_count = 2
```

**Characteristics**:
- Frequent plan reviews (15 minutes)
- Low switching threshold (25 bps)
- Aggressive safety limits (8% daily loss)
- Narrow event lock windows
- Strict API requirements

---

## Tuning Recommendations

### Starting Point

Begin with the **Active Trader Profile** and adjust based on observed behavior:

1. Run for 1-2 weeks with default settings
2. Review logs for plan changes, rejections, and tripwires
3. Adjust parameters based on patterns

### Common Adjustments

**Too many plan changes**:
- Increase `minimum_advantage_over_cost_bps`
- Increase `cooldown_after_change_minutes`
- Increase `confirmation_cycles_required`

**Too few plan changes**:
- Decrease `minimum_advantage_over_cost_bps`
- Decrease `medium_loop_interval_minutes`
- Decrease `hysteresis_enter_threshold`

**Excessive transaction costs**:
- Increase `minimum_advantage_over_cost_bps`
- Decrease `partial_rotation_pct_per_cycle` (slower rotation)
- Increase dwell times in strategy metadata

**Missing opportunities**:
- Decrease `confirmation_cycles_required`
- Decrease `cooldown_after_change_minutes`
- Narrow hysteresis band (smaller difference between enter/exit)

**False regime changes**:
- Increase `confirmation_cycles_required`
- Increase `hysteresis_enter_threshold`
- Widen hysteresis band (larger difference between enter/exit)

**Tripwires firing too often**:
- Increase `daily_loss_limit_pct`
- Increase `max_data_staleness_seconds`
- Increase `max_api_failure_count`

**Insufficient safety**:
- Decrease `daily_loss_limit_pct`
- Increase `min_margin_ratio`
- Increase `liquidation_proximity_threshold`

### Seasonal Adjustments

**High volatility periods** (e.g., major events, market crashes):
- Increase safety thresholds
- Widen event lock windows
- Increase confirmation cycles
- Decrease daily loss limit

**Low volatility periods** (e.g., summer doldrums):
- Can be more aggressive with thresholds
- Narrow event lock windows
- Decrease confirmation cycles

### Strategy-Specific Tuning

**Short-term strategies** (minutes to hours):
- Shorter medium loop intervals
- Lower switching thresholds
- Faster rebalancing

**Long-term strategies** (days to weeks):
- Longer medium loop intervals
- Higher switching thresholds
- Slower rebalancing

**High-frequency strategies**:
- May not benefit from governance
- Consider running without `--governed` flag

---

## Monitoring and Validation

### Key Metrics to Track

1. **Plan Change Frequency**: How often plans change
2. **Plan Change Approval Rate**: Percentage of proposals approved
3. **Average Plan Duration**: How long plans stay active
4. **Transaction Cost Ratio**: Costs as percentage of PnL
5. **Tripwire Fire Rate**: How often safety overrides occur
6. **Regime Change Frequency**: How often regimes shift

### Log Analysis

Check logs for governance events:

```bash
# Plan changes
grep "Plan change approved" logs/agent.log

# Rejected changes
grep "Plan change rejected" logs/agent.log

# Tripwire events
grep "Tripwire fired" logs/agent.log

# Regime changes
grep "Regime change confirmed" logs/agent.log
```

### Performance Validation

Compare governed vs ungoverned performance:

1. Run A/B test with same strategies
2. Measure transaction costs
3. Measure net PnL after costs
4. Measure Sharpe ratio
5. Measure maximum drawdown

Expected improvements with governance:
- 30-50% reduction in transaction costs
- 20-40% reduction in strategy changes
- Improved risk-adjusted returns (Sharpe ratio)
- More consistent performance

---

## Troubleshooting

### Plans Never Change

**Symptoms**: Active plan stays the same for days

**Possible Causes**:
- `minimum_advantage_over_cost_bps` too high
- `cooldown_after_change_minutes` too long
- Dwell times in strategies too long
- LLM not proposing changes

**Solutions**:
- Lower switching threshold to 25-40 bps
- Reduce cooldown to 30-45 minutes
- Check strategy dwell times
- Review LLM prompt for change conditions

### Plans Change Too Frequently

**Symptoms**: Plan changes every medium loop

**Possible Causes**:
- `minimum_advantage_over_cost_bps` too low
- Change cost calculation underestimating costs
- Regime detector too sensitive

**Solutions**:
- Increase switching threshold to 75-100 bps
- Increase `confirmation_cycles_required`
- Increase cooldown period
- Review change cost calculations

### Tripwires Fire Constantly

**Symptoms**: Safety tripwires trigger every loop

**Possible Causes**:
- Thresholds too strict for market conditions
- Actual risk exceeds configuration
- Data quality issues

**Solutions**:
- Increase `daily_loss_limit_pct`
- Increase `max_data_staleness_seconds`
- Review position sizing
- Check API connectivity

### Regime Changes Not Detected

**Symptoms**: Regime stays the same despite market shifts

**Possible Causes**:
- `confirmation_cycles_required` too high
- `hysteresis_enter_threshold` too high
- Regime signals not capturing market state

**Solutions**:
- Decrease confirmation cycles to 2-3
- Lower enter threshold to 0.60-0.65
- Review regime classification logic
- Check signal calculations

---

## Advanced Configuration

### Multiple Instances

Run multiple agents with different governance profiles:

```bash
# Conservative instance
hyperliquid-agent --governed --config configs/conservative.toml

# Aggressive instance
hyperliquid-agent --governed --config configs/aggressive.toml
```

Ensure different `state_persistence_path` for each instance.

### Dynamic Adjustment

For advanced users, governance parameters can be adjusted programmatically:

```python
from hyperliquid_agent.config import load_config
from hyperliquid_agent.governed_agent import GovernedTradingAgent

config = load_config("config.toml")

# Adjust based on market conditions
if high_volatility:
    config.governance.governor.minimum_advantage_over_cost_bps = 100.0
    config.governance.tripwire.daily_loss_limit_pct = 3.0
else:
    config.governance.governor.minimum_advantage_over_cost_bps = 50.0
    config.governance.tripwire.daily_loss_limit_pct = 5.0

agent = GovernedTradingAgent(config)
agent.run()
```

### Custom Regime Detection

Extend regime detector with custom signals:

```python
from hyperliquid_agent.governance.regime import RegimeDetector, ExternalDataProvider

class CustomDataProvider(ExternalDataProvider):
    def get_cross_asset_correlation(self, asset1: str, asset2: str) -> float:
        # Custom correlation calculation
        return 0.75
    
    def get_macro_risk_score(self) -> float:
        # Custom risk score
        return 0.5

detector = RegimeDetector(config, external_data_provider=CustomDataProvider())
```

---

## Best Practices

1. **Start Conservative**: Begin with hobby trader profile and relax constraints gradually
2. **Monitor Closely**: Watch logs for first week to understand behavior
3. **Backtest First**: Test configuration on historical data before live trading
4. **Document Changes**: Keep notes on parameter adjustments and their effects
5. **Review Regularly**: Reassess configuration monthly based on performance
6. **Coordinate Settings**: Ensure governance config aligns with strategy metadata
7. **Test Tripwires**: Verify safety limits trigger correctly in simulation
8. **Version Control**: Track configuration changes in git (excluding secrets)

---

## Related Documentation

- [Strategy Governance Metadata](STRATEGY_GOVERNANCE_METADATA.md) - Strategy-level governance settings
- [Configuration Guide](CONFIGURATION.md) - General agent configuration
- [README](../README.md) - Governance system overview

---

## Support

For issues or questions about governance configuration:

1. Check logs for specific error messages
2. Review this guide for tuning recommendations
3. Consult the design document at `.kiro/specs/strategy-governance/design.md`
4. Open an issue on GitHub with configuration and logs (redact secrets)
