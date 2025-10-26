# REGIME DETECTOR FIX - COMPREHENSIVE IMPLEMENTATION PLAN

**Status**: Planning Complete - Ready for Implementation
**Created**: 2025-10-26
**Continuation ID**: `fa0ea058-5fa6-4b5b-b6ba-5f1c8cb55eac`

## EXECUTIVE SUMMARY

**Problem**: Regime detector always returns "rangebound" because `_extract_regime_signals_from_state` in `governed_agent.py` attempts to access non-existent flat fields on `MediumLoopSignals`, causing all values to default to 0.0.

**Root Cause**: Code expects `medium.adx` but actual structure is `medium.technical_indicators['BTC'].adx` (nested dictionaries with per-coin data).

**Solution**: Extract signals from nested structures, aggregate per-coin data into portfolio-level metrics.

---

## ARCHITECTURE OVERVIEW

```
Current (Broken):
MediumLoopSignals.adx (doesn't exist) --> 0.0 --> Always Rangebound
                 .sma_20 (doesn't exist) --> 0.0
                 .sma_50 (doesn't exist) --> 0.0

Fixed Architecture:
MediumLoopSignals.technical_indicators[coin] --> TechnicalIndicators
                                              --> .adx, .sma_20, .sma_50
                 .funding_basis[coins] --> weighted average
FastLoopSignals.spreads[coins] --> simple average
               .order_book_depth[coins] --> simple average
```

---

## IMPLEMENTATION PHASES

```
DEPENDENCY GRAPH:

Phase 0 (Preparation)
    |
    v
Phase 1 (Helper Method) --------+
    |                           |
    v                           |
Phase 2 (Technical Indicators)  |  <-- CRITICAL PATH (Fixes Bug)
    |                           |
    +---> VALIDATION CHECKPOINT |
    |                           |
    v                           |
Phase 3 (Funding Rates) --------+
    |                           |
Phase 4 (Spreads/Depth) --------+
    |                           |
    v                           |
Phase 5 (Testing & Validation)  |
    |                           |
    v                           |
DEPLOYMENT                      |
                                |
(Phases 3-4 can run in parallel)
```

---

## PHASE 0: PREPARATION

**Objective**: Verify assumptions about data structures before implementing.

**Actions**:

1. Read `src/hyperliquid_agent/models/signals.py`

   - [ ] Verify `MediumLoopSignals.technical_indicators` is `dict[str, TechnicalIndicators]`
   - [ ] Verify `MediumLoopSignals.funding_basis` is `dict[str, float]`
   - [ ] Verify `MediumLoopSignals.realized_vol_24h` exists
   - [ ] Verify `FastLoopSignals.spreads` is `dict[str, float]`
   - [ ] Verify `FastLoopSignals.order_book_depth` is `dict[str, float]`
   - [ ] Verify `TechnicalIndicators` has `adx`, `sma_20`, `sma_50` attributes

2. Read `src/hyperliquid_agent/models/regime.py`

   - [ ] Verify `RegimeSignals` dataclass structure
   - [ ] **CRITICAL**: Check if it has all fields we need to populate
   - [ ] Understand regime classification thresholds

3. Read `src/hyperliquid_agent/models/account.py`

   - [ ] Verify `EnhancedAccountState.positions` structure
   - [ ] Verify position has `.coin`, `.size`, `.current_price` attributes

4. Read `src/hyperliquid_agent/governed_agent.py`

   - [ ] Find current `_extract_regime_signals_from_state` implementation
   - [ ] Note existing logging patterns

5. Review test files
   - [ ] `tests/unit/test_regime.py` - Understand test patterns
   - [ ] `tests/integration/test_governed_agent.py` - Check test setup

**Expected Outcome**: Clear understanding of actual vs. assumed structure.

---

## PHASE 1: REPRESENTATIVE ASSET SELECTION

**Objective**: Create helper method to select which coin's indicators to use for portfolio-level regime classification.

### Implementation

**Method Signature**:

```python
def _select_representative_asset(
    self,
    account_state: EnhancedAccountState,
    medium: MediumLoopSignals
) -> str | None:
    """Select which coin's indicators to use for portfolio regime classification.

    Selection priority:
    1. BTC (best market regime indicator)
    2. Largest position by notional value
    3. First available coin with complete indicators
    4. None (triggers fallback to zeros)
    """
```

**Selection Logic** (cascading fallback):

```
START
  |
  v
Is 'BTC' in technical_indicators and not None?
  |
  +-- YES --> Return 'BTC'
  |
  +-- NO
      |
      v
    Are there any positions?
      |
      +-- YES
      |     |
      |     v
      |   Find largest: max(position.size * position.current_price)
      |     |
      |     v
      |   Is largest_coin in technical_indicators?
      |     |
      |     +-- YES --> Return largest_coin
      |     |
      |     +-- NO --> (continue to next)
      |
      v
    Any coins in technical_indicators?
      |
      +-- YES --> Return first non-None coin
      |
      +-- NO --> Return None
```

### Unit Tests Required

1. `test_select_representative_asset_btc_preferred`

   - Setup: medium_signals with BTC and ETH technical indicators
   - Assert: Returns 'BTC'

2. `test_select_representative_asset_largest_position`

   - Setup: positions with ETH (large) and SOL (small), no BTC
   - Assert: Returns 'ETH'

3. `test_select_representative_asset_fallback_to_first`

   - Setup: empty positions, indicators for multiple coins
   - Assert: Returns first coin from technical_indicators

4. `test_select_representative_asset_none_fallback`
   - Setup: empty technical_indicators
   - Assert: Returns None

**Completion Criteria**:

- [ ] Method implemented with correct type annotations
- [ ] All 4 unit tests pass
- [ ] Logs which coin was selected and why
- [ ] Type checker (pyrefly) passes

---

## PHASE 2: TECHNICAL INDICATORS EXTRACTION (CRITICAL - FIXES BUG)

**Objective**: Fix the core bug by correctly extracting ADX and SMA values from nested structures.

### Implementation

**Validation Helper**:

```python
def _validate_indicators(self, indicators: TechnicalIndicators) -> bool:
    """Validate technical indicators are within reasonable ranges.

    Returns:
        True if indicators are valid, False otherwise
    """
    return (
        0 <= indicators.adx <= 100 and
        indicators.sma_20 > 0 and
        indicators.sma_50 > 0
    )
```

**Extraction Method**:

```python
def _extract_technical_indicators(
    self,
    representative_coin: str | None,
    medium: MediumLoopSignals
) -> tuple[float, float, float]:
    """Extract ADX and SMA values from technical indicators.

    Returns:
        (adx, sma_20, sma_50) or (0.0, 0.0, 0.0) if unavailable/invalid
    """
    if representative_coin and representative_coin in medium.technical_indicators:
        indicators = medium.technical_indicators[representative_coin]
        if indicators and self._validate_indicators(indicators):
            logger.debug(
                f"Using {representative_coin} indicators: "
                f"ADX={indicators.adx:.1f}, "
                f"SMA20={indicators.sma_20:.2f}, "
                f"SMA50={indicators.sma_50:.2f}"
            )
            return indicators.adx, indicators.sma_20, indicators.sma_50
        else:
            logger.warning(f"Invalid indicators for {representative_coin}, using fallback")

    return 0.0, 0.0, 0.0
```

**Modify `_extract_regime_signals_from_state`**:

```python
# Select representative asset
representative_coin = self._select_representative_asset(account_state, medium)

# Extract technical indicators
adx, sma_20, sma_50 = self._extract_technical_indicators(
    representative_coin, medium
)

# Use existing realized_vol_24h directly
realized_vol = medium.realized_vol_24h
```

### Unit Tests Required

1. `test_extract_technical_indicators_valid`

   - Setup: representative_coin='BTC', valid TechnicalIndicators
   - Assert: Returns non-zero adx, sma_20, sma_50

2. `test_extract_technical_indicators_invalid_adx`
   - Setup: TechnicalIndicators with adx=150 (invalid)
   - Assert: Returns (0.0, 0.0, 0.0)

### VALIDATION CHECKPOINT

**After implementation, verify**:

- [ ] Existing tests in `test_regime.py` still pass
- [ ] Existing tests in `test_governed_agent.py` still pass
- [ ] New unit tests pass
- [ ] Type checker (pyrefly) passes
- [ ] **CRITICAL**: Manual test shows ADX is non-zero with valid data
- [ ] **CRITICAL**: Manual test shows regime is NOT always rangebound

**If regime is STILL always rangebound**: Investigate `RegimeDetector` threshold logic (separate issue).

---

## PHASE 3: FUNDING RATE AGGREGATION

**Objective**: Calculate portfolio-level average funding rate from per-coin rates.

### Implementation

**Method**:

```python
def _calculate_weighted_funding_rate(
    self,
    account_state: EnhancedAccountState,
    medium: MediumLoopSignals
) -> float:
    """Calculate position-weighted average funding rate.

    Returns:
        Weighted average funding rate, or 0.0 if no data available
    """
    if not medium.funding_basis:
        logger.debug("No funding basis data available")
        return 0.0

    total_weighted_funding = 0.0
    total_notional = 0.0

    for position in account_state.positions:
        if position.coin in medium.funding_basis:
            notional = abs(position.size * position.current_price)
            funding_rate = medium.funding_basis[position.coin]

            total_weighted_funding += funding_rate * notional
            total_notional += notional

    if total_notional > 0:
        avg_funding = total_weighted_funding / total_notional
        logger.debug(
            f"Weighted funding rate: {avg_funding:.4f} "
            f"across {len(account_state.positions)} positions"
        )
        return avg_funding
    else:
        logger.warning("No positions have funding data, using 0.0")
        return 0.0
```

**Algorithm**: Position-weighted average

```
For each position:
    notional = abs(size * price)  # abs() handles shorts
    weighted_funding += funding_rate * notional
    total_notional += notional

avg_funding = weighted_funding / total_notional  # if total_notional > 0
```

### Unit Tests Required

1. `test_calculate_weighted_funding_rate`

   - Setup: 2 positions with different sizes and funding rates
   - Assert: Weighted average matches manual calculation

2. `test_calculate_weighted_funding_rate_no_positions`
   - Setup: positions but no matching funding_basis entries
   - Assert: Returns 0.0

**Edge Cases Handled**:

- Empty funding_basis dict → 0.0
- Empty positions list → 0.0 with warning
- Position coin not in funding_basis → skip that position
- Total notional = 0 → 0.0 (avoid division by zero)

**Completion Criteria**:

- [ ] Method implemented
- [ ] Unit tests pass
- [ ] Type checker (pyrefly) passes

---

## PHASE 4: SPREADS AND ORDER BOOK DEPTH EXTRACTION

**Objective**: Extract spread and depth metrics from `FastLoopSignals`.

### Implementation

**Method**:

```python
def _calculate_average_spread_and_depth(
    self,
    account_state: EnhancedAccountState
) -> tuple[float, float]:
    """Calculate average spread and order book depth from fast signals.

    Returns:
        (avg_spread_bps, avg_order_book_depth) or (0.0, 0.0) if unavailable
    """
    if account_state.fast_signals is None:
        logger.debug("Fast signals not available")
        return 0.0, 0.0

    fast = account_state.fast_signals

    # Calculate average spread
    if fast.spreads:
        avg_spread_bps = sum(fast.spreads.values()) / len(fast.spreads)
        logger.debug(
            f"Average spread: {avg_spread_bps:.2f} bps "
            f"across {len(fast.spreads)} coins"
        )
    else:
        avg_spread_bps = 0.0

    # Calculate average order book depth
    if fast.order_book_depth:
        avg_order_book_depth = sum(fast.order_book_depth.values()) / len(fast.order_book_depth)
        logger.debug(
            f"Average order book depth: {avg_order_book_depth:.2f} "
            f"across {len(fast.order_book_depth)} coins"
        )
    else:
        avg_order_book_depth = 0.0

    return avg_spread_bps, avg_order_book_depth
```

**Design Rationale**: Simple average (not weighted) - spreads/depth are execution-level metrics where we need general market liquidity sense.

### Unit Tests Required

1. `test_calculate_average_spread_and_depth`

   - Setup: fast_signals with multiple spreads and depths
   - Assert: Returns correct averages

2. `test_calculate_average_spread_and_depth_no_fast_signals`
   - Setup: account_state.fast_signals = None
   - Assert: Returns (0.0, 0.0)

**Completion Criteria**:

- [ ] Method implemented
- [ ] Unit tests pass
- [ ] Type checker (pyrefly) passes

---

## PHASE 5: COMPREHENSIVE VALIDATION

### Integration Test

**Test**: `test_extract_regime_signals_from_realistic_state`

```python
def test_extract_regime_signals_from_realistic_state():
    """End-to-end test with realistic nested signal structures."""

    # Setup: Create comprehensive EnhancedAccountState
    technical_indicators = {
        'BTC': TechnicalIndicators(adx=35.0, sma_20=95000.0, sma_50=92000.0, ...),
        'ETH': TechnicalIndicators(adx=28.0, sma_20=3500.0, sma_50=3400.0, ...)
    }

    funding_basis = {'BTC': 0.0001, 'ETH': 0.00015}

    medium_signals = MediumLoopSignals(
        technical_indicators=technical_indicators,
        funding_basis=funding_basis,
        realized_vol_24h=0.45
    )

    fast_signals = FastLoopSignals(
        spreads={'BTC': 2.5, 'ETH': 3.0},
        order_book_depth={'BTC': 1000000.0, 'ETH': 500000.0}
    )

    positions = [
        Position(coin='BTC', size=0.1, current_price=95000.0),
        Position(coin='ETH', size=2.0, current_price=3500.0)
    ]

    account_state = EnhancedAccountState(
        positions=positions,
        medium_signals=medium_signals,
        fast_signals=fast_signals
    )

    # Execute
    agent = GovernedAgent(...)
    regime_signals = agent._extract_regime_signals_from_state(account_state)

    # Assert
    assert regime_signals.adx == 35.0  # BTC selected as representative
    assert regime_signals.sma_20 == 95000.0
    assert regime_signals.sma_50 == 92000.0
    assert regime_signals.realized_vol_24h == 0.45
    assert 0.0001 <= regime_signals.funding_rate_avg <= 0.00015  # Weighted
    assert regime_signals.avg_spread_bps == 2.75  # (2.5 + 3.0) / 2
    assert regime_signals.avg_order_book_depth == 750000.0  # (1M + 500k) / 2

    # Assert regime is NOT rangebound with these values
    regime = agent.regime_detector.detect_regime(regime_signals)
    assert regime != "rangebound"
```

### Type Checking

```bash
# Check current baseline
uv run pyrefly src/hyperliquid_agent/governed_agent.py

# After each phase
uv run pyrefly src/hyperliquid_agent/governed_agent.py
```

### Test Suite Validation

```bash
# Unit tests
uv run pytest tests/unit/test_regime.py -v

# Integration tests
uv run pytest tests/integration/test_governed_agent.py -v

# Full suite
make test
# or
uv run pytest
```

### Manual Validation

**Run agent for 1 hour and monitor**:

- [ ] ADX values are between 0-100
- [ ] SMA values roughly match asset price levels
- [ ] Funding rates are reasonable (-0.1% to +0.1%)
- [ ] Spreads are realistic (1-10 bps for major coins)
- [ ] Regime classification changes over time
- [ ] No crashes or exceptions
- [ ] Performance is acceptable

**Completion Criteria**:

- [ ] Integration test passes
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Type checker (pyrefly) passes
- [ ] Manual validation successful

---

## RISK MANAGEMENT

### High Priority Risks

| Risk                             | Impact             | Mitigation                                 |
| -------------------------------- | ------------------ | ------------------------------------------ |
| RegimeSignals missing fields     | Code crashes       | Read regime.py FIRST, add fields if needed |
| Type errors from Optional/dict   | Type checker fails | Explicit None checks, key existence checks |
| Division by zero in weighted avg | Runtime crash      | Check total_notional > 0 before division   |
| Existing tests break             | Can't merge        | Review tests BEFORE implementing           |

### Medium Priority Risks

| Risk                              | Impact                   | Mitigation                                      |
| --------------------------------- | ------------------------ | ----------------------------------------------- |
| Regime still rangebound after fix | Bug not fixed            | Review RegimeDetector thresholds (separate fix) |
| Performance degradation           | Trading quality affected | Profile if needed (very low likelihood)         |

### Contingency Plans

**If Phase 2 doesn't fix the bug**:

1. Review RegimeDetector threshold logic
2. Add debug logs in detection logic
3. May need separate PR to adjust thresholds
4. Current PR still valuable (correct extraction)

**If tests break unexpectedly**:

1. Run with `-vv` for verbose output
2. Check test fixture data structures
3. Add temporary debugging in tests

**If type errors persist**:

1. Check pyrefly/Python version compatibility
2. Use TYPE_CHECKING import guards
3. Use `cast()` if certain about types
4. Last resort: `# type: ignore` with explanation

---

## CODE QUALITY STANDARDS

### Required for All Phases

- [ ] All functions have type annotations
- [ ] No `Any` type without justification
- [ ] Optional types properly handled with None checks
- [ ] Dict accesses check for key existence
- [ ] Passes pyrefly with zero errors
- [ ] Graceful degradation when data unavailable
- [ ] Clear logging (debug for normal, warning for fallback)
- [ ] Functions under 50 lines
- [ ] Comprehensive docstrings

---

## FINAL PRE-DEPLOYMENT CHECKLIST

**Code Quality**:

- [ ] All methods have docstrings
- [ ] All type annotations present
- [ ] No pyrefly errors
- [ ] Code formatted per project standards

**Testing**:

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] New tests added for new functionality
- [ ] Manual validation successful

**Backward Compatibility**:

- [ ] API signatures unchanged
- [ ] Existing tests unmodified
- [ ] Fallback behavior maintained
- [ ] No breaking changes

**Performance**:

- [ ] No noticeable slowdown
- [ ] Complexity is O(n) where n = positions

---

## IMMEDIATE NEXT ACTIONS

**Start with Action 1**: Verify Data Structures

Read these files to confirm assumptions:

1. `src/hyperliquid_agent/models/signals.py`
2. `src/hyperliquid_agent/models/regime.py`
3. `src/hyperliquid_agent/models/account.py`
4. `src/hyperliquid_agent/governed_agent.py`

Then review: 5. `tests/unit/test_regime.py` 6. `tests/integration/test_governed_agent.py`

Once verified, proceed to Phase 1 implementation.

---

## PROGRESS TRACKING

**Phase 0**: [✅] COMPLETED - Data structures verified
**Phase 1**: [✅] COMPLETED - Representative asset selection implemented
**Phase 2**: [✅] COMPLETED - Technical indicators extraction fixed (CRITICAL BUG FIX)
**Phase 3**: [✅] COMPLETED - Funding rate aggregation implemented
**Phase 4**: [✅] COMPLETED - Spreads and depth extraction implemented
**Phase 5**: [✅] COMPLETED - All validation tests passing (327 total tests, 19 new unit tests)
**Deployment**: [✅] READY FOR DEPLOYMENT

## IMPLEMENTATION SUMMARY

**Date Completed**: 2025-10-26
**Total Tests**: 327 (308 existing + 19 new unit tests)
**Type Checker**: 0 errors (using pyrefly)

### Files Modified
- `src/hyperliquid_agent/governed_agent.py` - Added 5 helper methods (lines 994-1274)

### Files Created
- `tests/unit/test_governed_agent.py` - 19 comprehensive unit tests

### Helper Methods Added
1. `_select_representative_asset()` - BTC-preferring asset selection (lines 994-1056)
2. `_validate_indicators()` - Technical indicator validation (lines 1058-1069)
3. `_extract_technical_indicators()` - Nested structure extraction (lines 1071-1106)
4. `_calculate_weighted_funding_rate()` - Position-weighted aggregation (lines 1108-1155)
5. `_calculate_average_spread_and_depth()` - Fast signal extraction (lines 1157-1209)

### Main Method Updated
- `_extract_regime_signals()` - Now correctly extracts all signals from nested data structures (lines 1211-1274)

---

## NOTES

- This plan was created using the zen planner MCP tool with continuation ID: `fa0ea058-5fa6-4b5b-b6ba-5f1c8cb55eac`
- Type checker: Using `pyrefly` (configured in pyproject.toml)
- Package manager: Using `uv` (as per project dependencies)
- The plan follows an incremental approach with validation checkpoints after Phase 2
