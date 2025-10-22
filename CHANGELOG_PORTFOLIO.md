# Portfolio State Management Implementation

## Summary

Implemented target allocation-based portfolio management system that allows the LLM to specify desired portfolio allocations rather than individual trades. The system automatically generates optimal rebalancing plans that respect capital constraints and execution order.

## Changes Made

### New Files

1. **`src/hyperliquid_agent/portfolio.py`** - Core portfolio management module
   - `PortfolioState`: Current portfolio with allocation percentages
   - `TargetAllocation`: Desired portfolio allocation
   - `PortfolioRebalancer`: Generates optimal rebalancing plans
   - `RebalancingPlan`: Ordered sequence of trades

2. **`examples/portfolio_rebalancing_example.py`** - Demonstration script
   - Shows rebalancing from 80% BTC to balanced portfolio
   - Demonstrates threshold-based filtering (no action for small deviations)
   - Shows risk-off scenario (exit all positions)

3. **`docs/PORTFOLIO_MANAGEMENT.md`** - Comprehensive documentation
   - Architecture overview with diagrams
   - Usage examples
   - Configuration guidelines
   - Integration with strategies
   - Limitations and future work

### Modified Files

1. **`src/hyperliquid_agent/decision.py`**
   - Added `target_allocation` field to `DecisionResult`
   - Updated `_parse_response()` to extract target allocation from LLM response
   - Modified return type to include target allocation

2. **`src/hyperliquid_agent/agent.py`**
   - Added `PortfolioRebalancer` initialization
   - Added Step 2.5: Generate rebalancing plan if target allocation provided
   - Converts `AccountState` to `PortfolioState`
   - Uses rebalancing plan actions instead of direct LLM actions when applicable
   - Enhanced logging for rebalancing operations

3. **`prompts/default.txt`**
   - Updated to support two response formats:
     - Option 1: Target allocation (recommended)
     - Option 2: Direct actions (legacy)
   - Added guidance on when to use each format

## Architecture

### Two-Phase Flow

**Phase 1: LLM Decision**
- Input: Current portfolio state, market data, strategies
- Output: Target allocation percentages OR direct actions

**Phase 2: Rebalancing Plan Generation (Deterministic)**
- Input: Current state, target allocation
- Output: Ordered list of trades
- Logic:
  1. Calculate allocation deltas
  2. Filter insignificant deviations (< 5% threshold)
  3. Close/reduce overweight positions first (frees capital)
  4. Open/increase underweight positions second (uses capital)
  5. Respect minimum trade sizes and capital constraints

### Key Design Decisions

1. **Separation of Concerns**
   - LLM: Strategy and allocation (what to do)
   - Code: Execution planning (how to do it)
   - Rationale: LLMs are good at strategy, bad at arithmetic and constraints

2. **Deterministic Rebalancing**
   - Pure function: same inputs → same outputs
   - Testable without LLM calls
   - No hallucination in trade sizing

3. **Capital-Aware Ordering**
   - Closes positions before opens
   - Prevents "insufficient balance" errors
   - Handles multi-step rebalancing automatically

4. **Threshold-Based Filtering**
   - Default: 5% deviation triggers rebalance
   - Avoids excessive trading on small fluctuations
   - Configurable per deployment

## Benefits

✅ **Handles Capital Constraints**: Automatically orders trades to free capital before using it

✅ **Multi-Step Rebalancing**: Handles complex transitions (e.g., 100% BTC → 50% BTC / 50% ETH)

✅ **Minimal Code Changes**: Added one module, modified two files slightly

✅ **Idiomatic Python**: Simple dataclasses, pure functions, no external dependencies

✅ **Testable**: Rebalancing logic is deterministic and unit-testable

✅ **Strategy-Friendly**: Strategies can now think in allocations, not individual trades

✅ **Cost-Aware**: Filters dust trades, estimates total rebalancing cost

## Example Usage

### LLM Response (Target Allocation)

```json
{
  "selected_strategy": "balanced-growth",
  "target_allocation": {
    "BTC": 0.40,
    "ETH": 0.30,
    "USDC": 0.30
  }
}
```

### Generated Rebalancing Plan

**Current:** 80% BTC, 20% USDC
**Target:** 40% BTC, 30% ETH, 30% USDC

**Actions:**
1. SELL 0.4 BTC (reduce from 80% to 40%)
2. BUY ETH with $15,000 (increase from 0% to 30%)

## Configuration

```python
# In agent.py
self.rebalancer = PortfolioRebalancer(
    min_trade_value=10.0,        # Minimum $10 per trade
    max_slippage_pct=0.005,      # 0.5% max slippage
    rebalance_threshold=0.05,    # 5% deviation triggers action
)
```

## Testing

Run the example:

```bash
cd hyperliquid-trading-agent
uv run python examples/portfolio_rebalancing_example.py
```

## Limitations

1. **Price Data**: Cannot open new positions without current market prices
   - Workaround: LLM should only target assets with existing positions

2. **Position Direction**: No explicit long/short modeling
   - Workaround: Use separate coins for long/short (e.g., "BTC-LONG", "BTC-SHORT")

3. **Partial Fills**: Assumes orders fill completely
   - Future: Add order status tracking

## Future Enhancements

1. **Multi-LLM Calls**: Strategy selection → allocation → plan review
2. **Gradual Rebalancing**: Spread large rebalances over multiple ticks (TWAP)
3. **Risk Limits**: Max leverage, concentration, correlation constraints
4. **Market Data Integration**: Fetch prices for new positions
5. **Backtesting**: Simulate rebalancing plans against historical data

## Migration Guide

### For Existing Strategies

**Before (Direct Actions):**
```json
{
  "actions": [
    {"action_type": "sell", "coin": "BTC", "size": 0.4},
    {"action_type": "buy", "coin": "ETH", "size": 5.0}
  ]
}
```

**After (Target Allocation):**
```json
{
  "target_allocation": {
    "BTC": 0.40,
    "ETH": 0.30,
    "USDC": 0.30
  }
}
```

### Backward Compatibility

The system supports both formats:
- If `target_allocation` is provided → use rebalancing plan
- If only `actions` are provided → execute directly (legacy behavior)

No breaking changes to existing strategies.

## Conclusion

This implementation provides a robust foundation for portfolio state management with minimal complexity. The architecture separates strategic decision-making (LLM) from tactical execution (code), resulting in more reliable and testable trading behavior.

The approach was chosen for:
- **Highest probability of success**: Simple, deterministic logic
- **Minimal code changes**: One new module, small modifications
- **Idiomatic Python**: Dataclasses, pure functions, no enterprise dependencies
- **Startup-appropriate**: No Redis, Kafka, or complex infrastructure
