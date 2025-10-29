# Placeholder Code & TODO Analysis Report

**Generated:** 2025-10-29
**Analysis Type:** Code Quality & Completeness Audit
**Status:** 11 TODOs | 8 Stubbed Methods | 6 Hardcoded Values

---

## Executive Summary

The codebase has **11 TODOs**, **8 stubbed provider methods**, and **6 hardcoded placeholder values**. The architecture is solid and well-designed for a multi-timescale trading agent, but **critical data inputs are currently using placeholder calculations that undermine the LLM regime classification system**. The agent is functional for basic operations but not production-ready due to missing external data integrations and incomplete safety features.

**Production Readiness Assessment:**
- ✅ Core trading execution works
- ⚠️ LLM regime classification uses approximate data
- ❌ External data enrichment disabled
- ❌ Emergency tripwire action not implemented
- ⚠️ Async optimization not done

---

## 🚨 CRITICAL PRIORITY

### 1. Price History Calculations (Regime Classification Accuracy)

**Location:** `governed_agent.py:1307-1367` (`_extract_price_context()`)

**Issue:** Multi-timeframe returns are calculated using **formula multipliers** instead of actual historical price data:

```python
# Current implementation (WRONG)
return_proxy = sma20_distance  # Very rough approximation

return PriceContext(
    current_price=current_price,
    # TODO: Replace with actual historical return calculations
    return_1d=return_proxy * 0.2,   # Placeholder
    return_7d=return_proxy * 0.5,   # Placeholder
    return_30d=return_proxy,        # Placeholder
    return_90d=return_proxy * 1.5,  # Placeholder
    sma20_distance=sma20_distance,
    sma50_distance=sma50_distance,
    # TODO: Calculate from actual price history
    higher_highs=sma20_distance > 0 and sma20_distance > sma50_distance,  # Rough proxy
    higher_lows=sma20_distance > sma50_distance,  # Rough proxy
)
```

**Impact Analysis:**
- ❌ The LLM regime classifier receives **fundamentally incorrect data**
- ❌ SMA distance is NOT a valid proxy for multi-timeframe returns
- ❌ Market structure detection (higher highs/lows) is unreliable
- ❌ Regime misclassification leads to **wrong strategy selection** → financial losses

**Why This Matters:**
The entire governance system depends on accurate regime classification. If the LLM thinks the market is `trending-bull` when it's actually `range-bound`, the agent will activate an inappropriate trading plan and lose money.

**Documentation Reference:**
`NEXT_STEPS.md` lines 40-99 provides detailed implementation guidance:
1. Add price history cache in signal collectors (deque with 90-day lookback)
2. Calculate actual returns from historical closes
3. Implement real market structure analysis (peak/trough detection)

**Implementation Sketch:**
```python
class PriceHistory:
    def __init__(self, lookback_days=90):
        self.closes = deque(maxlen=lookback_days * 6)  # 4h candles
        self.highs = deque(maxlen=lookback_days * 6)
        self.lows = deque(maxlen=lookback_days * 6)
        self.timestamps = deque(maxlen=lookback_days * 6)

    def calculate_returns(self) -> dict:
        """Calculate multi-timeframe returns."""
        if len(self.closes) < 90 * 6:
            return None  # Not enough data yet

        current = self.closes[-1]
        # 1d = 6 candles ago (6 * 4h = 24h)
        # 7d = 42 candles ago
        # 30d = 180 candles ago
        # 90d = 540 candles ago

        return {
            "return_1d": ((current - self.closes[-6]) / self.closes[-6]) * 100,
            "return_7d": ((current - self.closes[-42]) / self.closes[-42]) * 100,
            "return_30d": ((current - self.closes[-180]) / self.closes[-180]) * 100,
            "return_90d": ((current - self.closes[-540]) / self.closes[-540]) * 100,
        }
```

**Validation Test:**
Run 2024 backtest and verify regime classifications match actual market conditions:
- Jan-Mar: `trending-bull` (BTC ETF approval, +50% gains)
- Apr-Jun: `trending-bull` (Halving event)
- Jul-Oct: `range-bound` or `trending-bull` (consolidation)
- Nov-Dec: `trending-bull` (Post-election rally, new ATHs)

**NOT expected:**
- ❌ 90% range-bound classification
- ❌ Only detecting trends in final 2 months
- ❌ Missing the sustained bull market

---

## 🔴 HIGH PRIORITY - External Data Providers (All Stubbed)

All three external data providers return empty/neutral placeholder values instead of real market data.

### 2.1 On-Chain Provider

**File:** `src/hyperliquid_agent/signals/onchain_provider.py`

**Stubbed Methods:**
- `_fetch_token_unlocks_impl()` → returns `[]` (empty list)
- `_fetch_whale_flows_impl()` → returns zero flows

**Evidence:**
```python
# Lines 136-137
# TODO: Integrate with actual on-chain data API
# For now, return empty list as placeholder
unlocks: list[UnlockEvent] = []
```

**Intended Integrations:**
- Token Unlocks API (https://token.unlocks.app)
- Nansen
- Dune Analytics

**Impact:**
- ❌ Cannot detect upcoming token unlock events (major selling pressure)
- ❌ Misses whale wallet movement signals
- ❌ No visibility into on-chain capital flows

**Implementation Status:**
- ✅ Data models defined (`UnlockEvent`, `WhaleFlowData`)
- ✅ Provider interface complete
- ✅ Cache integration ready
- ❌ API integration code commented out with examples
- ⚠️ API key configuration exists but unused

---

### 2.2 External Market Provider

**File:** `src/hyperliquid_agent/signals/external_market_provider.py`

**Stubbed Methods:**
- `_fetch_asset_prices_impl()` → returns `{}` (empty dict)
- `fetch_macro_calendar()` → returns `[]` (empty list)

**Evidence:**
```python
# Lines 141-142
# TODO: Integrate with actual external market data APIs
# For now, return empty dict as placeholder
price_data: dict[str, list[float]] = {}
```

**Intended Integrations:**
- CoinGecko API for BTC and ETH prices
- Yahoo Finance or similar for SPX index data
- Macro economic calendar API (FOMC, CPI, jobs reports)

**Impact:**
- ❌ Cannot correlate crypto with traditional markets (SPX)
- ❌ Misses macro economic event risk (FOMC meetings, CPI releases)
- ❌ No cross-asset analysis for regime classification
- ❌ Slow loop macro calendar update is just a log message (line 614 in `governed_agent.py`)

**Implementation Status:**
- ✅ CoinGecko API key configuration exists
- ✅ Example integration code commented out
- ❌ No macro calendar API selected yet

---

### 2.3 Sentiment Provider

**File:** `src/hyperliquid_agent/signals/sentiment_provider.py`

**Stubbed Methods:**
- `_fetch_fear_greed_impl()` → returns `0.0` (neutral)
- `fetch_social_sentiment()` → returns `0.0` (neutral)

**Evidence:**
```python
# Lines 125-126
# TODO: Integrate with actual Fear & Greed Index API
# For now, return neutral value as placeholder
normalized_score = 0.0
```

**Intended Integrations:**
- Alternative.me Fear & Greed Index API (FREE, no auth required!)
- Twitter/X social sentiment APIs (optional)

**Impact:**
- ❌ No market sentiment awareness (fear/greed cycles)
- ❌ Cannot detect extreme sentiment conditions
- ❌ Missing contrarian indicators

**Implementation Status:**
- ✅ Free API available: https://api.alternative.me/fng/
- ✅ Example integration code commented out (lines 128-161)
- ✅ No authentication required
- ❌ Simple uncomment + test needed

**Quick Win Potential:** ⭐⭐⭐⭐⭐
This is the easiest integration - free API, no auth, simple JSON parsing, high-value signal!

---

### Summary: External Data Provider Impact

**Combined Effect:**
The agent was designed to make decisions based on a rich, multi-faceted view of the market. Without these external signals, it cannot react to critical events and is exposed to risks it was intended to mitigate.

**Common Pattern Across All Providers:**
- ✅ Placeholder return values with degraded confidence scores
- ✅ Commented example integration code showing intended patterns
- ✅ Proper error handling and fallback logic
- ✅ Cache integration ready
- ❌ API integration not activated

---

## 🟠 MEDIUM PRIORITY - Safety & Performance

### 3.1 Emergency Position Reduction (Safety Gap)

**Location:** `governed_agent.py:242`

```python
case TripwireAction.CUT_SIZE_TO_FLOOR:
    self.logger.critical(
        "Cut size to floor triggered - emergency risk reduction needed",
        extra={"tick": self.tick_count},
    )
    # TODO: Implement emergency position reduction
    return True
```

**Issue:** Critical tripwire fires but does **nothing**. System can freeze new risk but cannot actively reduce existing positions during flash crash or crisis.

**Impact:**
- ❌ Safety mechanism incomplete
- ❌ Cannot execute emergency de-risking
- ⚠️ Other tripwire actions work correctly (FREEZE_NEW_RISK, INVALIDATE_PLAN, ESCALATE_TO_SLOW_LOOP)

**Implementation Requirements:**
1. Generate sell orders for all positions
2. Use market orders for immediate execution
3. Consider partial vs. full liquidation based on severity
4. Log emergency action for audit trail
5. Update scorekeeper metrics

**Risk Level:** High - this is a safety feature that should exist

---

### 3.2 Sequential Loop Execution (Performance)

**Location:** `governed_agent.py:137`

```python
# TODO: Turn this into async parallel processes
# Determine which loops to run
run_fast = True
run_medium = self._should_run_medium_loop(current_time)
run_slow = self._should_run_slow_loop(current_time)

# Execute loops in order: slow -> medium -> fast
if run_slow:
    self._execute_slow_loop(current_time)
    self.last_slow_loop = current_time

if run_medium:
    self._execute_medium_loop(current_time)
    self.last_medium_loop = current_time

if run_fast:
    self._execute_fast_loop(current_time)
```

**Issue:** Loops run sequentially. Slow loops can delay fast loops, creating latency in time-sensitive operations.

**Impact:**
- ⚠️ Slow loop blocks medium and fast loops
- ⚠️ Fast loop (10s interval) may miss ticks if slower loops run long
- ⚠️ Scalability issue as more features are added

**Solution:** Refactor to use `asyncio` for concurrent execution:
```python
async def run_async(self):
    while True:
        tasks = []

        if self._should_run_slow_loop(current_time):
            tasks.append(self._execute_slow_loop_async(current_time))

        if self._should_run_medium_loop(current_time):
            tasks.append(self._execute_medium_loop_async(current_time))

        tasks.append(self._execute_fast_loop_async(current_time))

        # Run all loops concurrently
        await asyncio.gather(*tasks, return_exceptions=True)

        await asyncio.sleep(self.governance_config.fast_loop_interval_seconds)
```

**Priority:** Medium - not critical now but will become important at scale

---

## 🟡 LOW PRIORITY - Minor Issues

### 4.1 Historical Open Interest Change

**Location:** `collectors.py:360`

```python
# Calculate 24h OI change (would need historical OI data)
# For now, use placeholder - in production, fetch historical OI
open_interest_change_24h[coin] = 0.0
```

**Impact:** OI change metric always reports 0.0, limiting analysis of market positioning trends.

---

### 4.2 Macro Calendar Update

**Location:** `governed_agent.py:614`

```python
# Update macro calendar
# In a full implementation, this would fetch upcoming macro events
# For now, we'll just log that the calendar would be updated
self.logger.info(
    "Macro calendar update (placeholder - would fetch FOMC, CPI, jobs reports, etc.)",
    extra={"tick": self.tick_count},
)
```

**Impact:** Slow loop doesn't actually update the macro economic calendar. Related to external market provider stub.

---

### 4.3 Cache Metrics Placeholder

**Location:** `monitor_enhanced.py:67`

```python
# Note: Cache metrics are accessed via the orchestrator which is created
# in the background thread. For proper access, we'd need to pass a request
# through the queue. For now, return a placeholder.
return {
    "status": "metrics_available_via_orchestrator",
    "note": "Use orchestrator.get_health_status() for detailed cache metrics",
}
```

**Impact:** Cannot get cache performance metrics via monitor interface. Reduces observability.

**Solution:** Implement queue-based request to orchestrator for cache metrics.

---

### 4.4 Configuration Default Clarity

**Location:** `config.py:55`

```python
@dataclass
class OnChainConfig:
    """On-chain data provider configuration."""

    enabled: bool = True
    provider: str = "placeholder"  # e.g., "token_unlocks", "nansen", "dune"
    api_key: str | None = None
    cache_ttl_seconds: int = 3600
```

**Issue:** Default value `"placeholder"` is confusing - should be `None` for clarity.

**Impact:** Minimal - gets overridden by config file, but reduces code clarity.

**Quick Fix:**
```python
provider: str | None = None  # e.g., "token_unlocks", "nansen", "dune"
```

---

## 📈 Summary Statistics

| Category | Count | Status |
|----------|-------|--------|
| **TODOs** | 11 | All documented |
| **Stubbed Methods** | 8 | All external providers |
| **Hardcoded Values** | 6 | Mostly multipliers |
| **Critical Issues** | 1 | Price history |
| **High Priority** | 3 providers | External data |
| **Medium Priority** | 2 | Safety + performance |
| **Low Priority** | 4 | Minor features |

---

## 🎯 Top 3 Strategic Recommendations

### #1 - Implement Historical Price Tracking

**Effort:** Medium | **Impact:** CRITICAL | **Timeline:** Immediate

**What to Do:**
Follow the implementation guide in `NEXT_STEPS.md:40-99`:

1. **Add `PriceHistory` class in signal collectors** (`signals/collectors.py`):
   - Deque-based storage with 90-day lookback
   - Track closes, highs, lows, timestamps
   - 4-hour candles = 540 data points for 90 days

2. **Calculate real returns** from historical closes:
   - 1d = 6 candles ago
   - 7d = 42 candles ago
   - 30d = 180 candles ago
   - 90d = 540 candles ago

3. **Implement market structure analysis**:
   - Higher highs/lows detection
   - Peak/trough identification
   - Trend continuation validation

4. **Update `_extract_price_context()`** in `governed_agent.py`:
   - Use real historical data
   - Remove placeholder multipliers
   - Return actual `PriceContext`

**Success Metric:**
Run 2024 backtest and see regime classifications that match actual market conditions:
- Jan-Mar 2024: `trending-bull` (not range-bound)
- Sustained bull market properly detected
- Regime transitions align with market events

**Files to Modify:**
- `src/hyperliquid_agent/signals/collectors.py` (add `PriceHistory`)
- `src/hyperliquid_agent/governed_agent.py:1307-1367` (fix `_extract_price_context()`)
- `src/hyperliquid_agent/backtesting/signal_reconstructor.py` (enhance for backtesting)

---

### #2 - Integrate Sentiment Provider (Quick Win!)

**Effort:** Low | **Impact:** High | **Timeline:** 1-2 hours

**What to Do:**
Uncomment the example code in `sentiment_provider.py:128-161`:

1. **Enable Fear & Greed Index API**:
   - Free API: `https://api.alternative.me/fng/`
   - No authentication required
   - Simple JSON parsing
   - Returns value 0-100

2. **Normalize the score** to -1.0 to +1.0 range:
   ```python
   raw_value = int(data['data'][0]['value'])
   normalized_score = (raw_value - 50) / 50.0
   # 0 (extreme fear) -> -1.0
   # 50 (neutral) -> 0.0
   # 100 (extreme greed) -> +1.0
   ```

3. **Test the integration**:
   ```bash
   # Run agent for one tick
   uv run degen run --max-ticks 1

   # Check logs for real sentiment values
   # Should see: "Fear & Greed Index: 65/100 (normalized: 0.30)"
   ```

**Success Metric:**
- Logs show real fear/greed values instead of 0.0
- Regime classifier receives actual sentiment signal
- No errors in API calls

**Why This First:**
- Easiest integration (free, no auth)
- High-value signal for regime classification
- Builds confidence for other provider integrations
- Immediate visible result in logs

---

### #3 - Implement Emergency Position Reduction

**Effort:** Medium | **Impact:** High (safety) | **Timeline:** 1-2 days

**What to Do:**
In `governed_agent.py:242`, implement emergency de-risking logic:

1. **Generate emergency exit orders**:
   ```python
   case TripwireAction.CUT_SIZE_TO_FLOOR:
       self.logger.critical(
           "Cut size to floor triggered - executing emergency position reduction",
           extra={"tick": self.tick_count}
       )

       # Get all current positions
       account_state = self.monitor.get_current_state()

       # Generate market sell orders for all positions
       for position in account_state.positions:
           if position.size > 0:  # Only close actual positions
               action = TradeAction(
                   action_type="sell",
                   coin=position.coin,
                   market_type=position.market_type,
                   size=position.size,  # Full position
                   price=None,  # Market order for immediate execution
                   reasoning="Emergency risk reduction (tripwire triggered)"
               )

               try:
                   result = self.base_agent.executor.execute_action(action)
                   self.logger.critical(
                       f"Emergency exit: {action.coin} - {'success' if result.success else 'failed'}",
                       extra={"coin": action.coin, "size": position.size}
                   )
               except Exception as e:
                   self.logger.critical(
                       f"Emergency exit failed for {action.coin}: {e}",
                       exc_info=True
                   )

       return True
   ```

2. **Add configuration** for partial vs. full liquidation:
   ```python
   # In TripwireConfig
   emergency_reduction_pct: float = 100.0  # 100% = full exit, 50% = half
   ```

3. **Test the implementation**:
   - Create unit test for emergency trigger
   - Test with paper trading first
   - Verify all positions are closed
   - Check audit trail in logs

**Success Metric:**
- Tripwire test triggers actual position reduction
- All positions closed within acceptable time
- Proper logging for audit trail
- No execution errors

**Safety Considerations:**
- Use market orders for immediate execution
- Log every action for audit trail
- Consider network failures (retry logic)
- Update scorekeeper metrics
- Notify external monitoring systems

---

## 🏗️ Architectural Strengths (Validation)

The codebase demonstrates several architectural strengths that make these fixes straightforward:

✅ **Clean Separation of Concerns**
- Governance layer properly isolated from core agent
- Signal collection abstracted into dedicated service
- Clear boundaries between components

✅ **Multi-Timescale Loop Design**
- Fast/medium/slow loop pattern well-suited for trading
- Proper use of dwell times and cooldowns
- Event-driven regime override mechanism

✅ **Excellent Documentation**
- `NEXT_STEPS.md` provides clear implementation guidance
- Code comments explain placeholder logic
- Example integration code commented in providers

✅ **Extensible Provider Pattern**
- Easy to add new data sources
- Consistent interface across providers
- Cache integration built-in

✅ **Comprehensive Test Coverage**
- Tests exist for stubbed features
- Integration test framework ready
- Backtesting infrastructure complete

**Assessment:** The architecture is **production-grade**. The issue is execution completeness, not design quality.

---

## 📋 Complete TODO Inventory

### Critical (1)
1. `governed_agent.py:1249-1250` - Price context uses placeholder values
2. `governed_agent.py:1316` - Price context calculations simplified/placeholder
3. `governed_agent.py:1350` - Calculate actual returns from price history
4. `governed_agent.py:1357-1361` - Replace with actual historical return calculations
5. `governed_agent.py:1364` - Calculate market structure from actual price history

### High Priority (3 providers × 2 methods each)
6. `onchain_provider.py:136-137` - Integrate with actual on-chain data API
7. `onchain_provider.py:251-252` - Integrate whale flows API
8. `external_market_provider.py:141-142` - Integrate with external market data APIs
9. `external_market_provider.py:269-270` - Integrate with macro calendar API
10. `sentiment_provider.py:125-126` - Integrate with Fear & Greed Index API
11. `sentiment_provider.py:238-239` - Integrate with social sentiment API

### Medium Priority (2)
12. `governed_agent.py:137` - Turn loops into async parallel processes
13. `governed_agent.py:242` - Implement emergency position reduction

### Low Priority (4)
14. `governed_agent.py:614` - Macro calendar update placeholder
15. `collectors.py:360` - Historical open interest placeholder
16. `monitor_enhanced.py:67` - Cache metrics placeholder
17. `config.py:55` - On-chain provider default "placeholder" string

---

## 🔄 Implementation Priority Order

**Week 1: Critical Path**
1. Historical price tracking (3-5 days)
2. Sentiment provider integration (0.5 days)
3. Validate with 2024 backtest (1 day)

**Week 2: Safety & Data**
4. Emergency position reduction (1-2 days)
5. External market provider (2-3 days)
6. Test emergency scenarios (1 day)

**Week 3: Enrichment**
7. On-chain provider integration (2-4 days)
8. Async loop refactoring (1-2 days)
9. Full integration testing (1 day)

**Week 4: Polish**
10. Historical OI change calculation
11. Cache metrics implementation
12. Configuration cleanup
13. Documentation updates

---

## 📚 References

- **Implementation Guide:** `NEXT_STEPS.md` (lines 40-99)
- **Regime Refactor Summary:** `REGIME_REFACTOR_SUMMARY.md`
- **Configuration Documentation:** `docs/CONFIGURATION.md`
- **Architecture Diagram:** `docs/ARCHITECTURE_DIAGRAM.md`

---

## ✅ Validation Checklist

Before declaring production-ready, verify:

- [ ] 2024 backtest shows realistic regime classifications
- [ ] External data providers return real data (not 0.0 or empty)
- [ ] Emergency tripwire executes actual position reduction
- [ ] Sentiment index shows real fear/greed values
- [ ] Multi-timeframe returns calculated from historical prices
- [ ] Market structure detection uses real peak/trough analysis
- [ ] Async loops prevent fast loop blocking
- [ ] Cache metrics available for monitoring
- [ ] All TODOs resolved or documented
- [ ] Integration tests pass with real data sources

---

**End of Report**
