# Trading Agent Architecture - Portfolio Management

## System Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TRADING AGENT LOOP                          │
│                         (Every tick_interval)                       │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: Monitor Positions                                          │
│                                                                     │
│  PositionMonitor.get_current_state()                                │
│  ├─ Fetch from Hyperliquid API                                     │
│  ├─ Parse positions, balances                                      │
│  └─ Return AccountState                                            │
│                                                                     │
│  AccountState {                                                     │
│    portfolio_value: 50000.0                                         │
│    available_balance: 15000.0                                       │
│    positions: [BTC: 0.5 @ $52k, ETH: 6.0 @ $2.6k]                  │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: LLM Decision                                               │
│                                                                     │
│  DecisionEngine.get_decision(account_state)                         │
│  ├─ Format prompt with current state + strategies                  │
│  ├─ Query LLM (OpenAI/Anthropic)                                   │
│  └─ Parse response                                                 │
│                                                                     │
│  LLM Response (Option 1 - Target Allocation):                      │
│  {                                                                  │
│    "selected_strategy": "balanced-growth",                          │
│    "target_allocation": {                                           │
│      "BTC": 0.40,    ← Want 40% in BTC                             │
│      "ETH": 0.30,    ← Want 30% in ETH                             │
│      "USDC": 0.30    ← Want 30% in cash                            │
│    }                                                                │
│  }                                                                  │
│                                                                     │
│  OR                                                                 │
│                                                                     │
│  LLM Response (Option 2 - Direct Actions):                         │
│  {                                                                  │
│    "selected_strategy": "compression-pop",                          │
│    "actions": [                                                     │
│      {"action_type": "buy", "coin": "BTC", "size": 0.5}            │
│    ]                                                                │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
    ┌───────────────────────────┐   ┌──────────────────────┐
    │ Target Allocation         │   │ Direct Actions       │
    │ Provided?                 │   │ (Legacy Path)        │
    └───────────────────────────┘   └──────────────────────┘
                    │                           │
                    │ YES                       │ NO
                    ▼                           │
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2.5: Generate Rebalancing Plan (NEW!)                         │
│                                                                     │
│  PortfolioRebalancer.create_rebalancing_plan()                      │
│                                                                     │
│  1. Convert AccountState → PortfolioState                           │
│     Current: {BTC: 50%, ETH: 20%, USDC: 30%}                       │
│                                                                     │
│  2. Calculate deltas (target - current)                             │
│     BTC: 40% - 50% = -10%  (overweight, need to sell)             │
│     ETH: 30% - 20% = +10%  (underweight, need to buy)             │
│     USDC: 30% - 30% = 0%   (balanced, no action)                   │
│                                                                     │
│  3. Filter insignificant deviations (< 5% threshold)                │
│     BTC: -10% → KEEP (significant)                                 │
│     ETH: +10% → KEEP (significant)                                 │
│     USDC: 0% → SKIP (no change)                                    │
│                                                                     │
│  4. Phase 1: Close/reduce overweight positions                      │
│     Action: SELL 0.1 BTC (frees ~$5,200)                           │
│                                                                     │
│  5. Phase 2: Open/increase underweight positions                    │
│     Action: BUY 2.0 ETH (uses ~$5,200)                             │
│                                                                     │
│  RebalancingPlan {                                                  │
│    actions: [                                                       │
│      SELL 0.1 BTC,                                                  │
│      BUY 2.0 ETH                                                    │
│    ],                                                               │
│    estimated_cost: $25.00,                                          │
│    reasoning: "Reduce BTC: 50% → 40%; Increase ETH: 20% → 30%"    │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ (Both paths merge)
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: Execute Trades                                             │
│                                                                     │
│  For each action in actions_to_execute:                             │
│    TradeExecutor.execute_action(action)                             │
│    ├─ Validate action parameters                                   │
│    ├─ Submit order to Hyperliquid                                  │
│    └─ Return ExecutionResult                                       │
│                                                                     │
│  Execution with retry logic:                                        │
│  ├─ Attempt 1: SELL 0.1 BTC → Success (order_id: abc123)          │
│  ├─ Attempt 1: BUY 2.0 ETH → Success (order_id: def456)           │
│  └─ Log results                                                    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                        ┌─────────────────┐
                        │ Sleep until     │
                        │ next tick       │
                        └─────────────────┘
```

## Key Components

### 1. PositionMonitor
- **Purpose**: Fetch current portfolio state from Hyperliquid
- **Output**: `AccountState` with positions, balances, portfolio value
- **Caching**: Returns stale data if API fails

### 2. DecisionEngine
- **Purpose**: Query LLM for trading decisions
- **Input**: Current account state + available strategies
- **Output**: `DecisionResult` with actions OR target allocation
- **Providers**: OpenAI, Anthropic

### 3. PortfolioRebalancer (NEW!)
- **Purpose**: Convert target allocation → ordered trade sequence
- **Logic**: 
  - Calculate deltas
  - Filter small deviations
  - Order trades (close before open)
  - Respect capital constraints
- **Output**: `RebalancingPlan` with ordered actions

### 4. TradeExecutor
- **Purpose**: Submit orders to Hyperliquid exchange
- **Features**: 
  - Validation
  - Market/limit orders
  - Retry logic
  - Error handling

## Data Flow

```
AccountState (raw positions)
      ↓
PortfolioState (allocation percentages)
      ↓
TargetAllocation (desired percentages)
      ↓
RebalancingPlan (ordered trades)
      ↓
TradeAction[] (individual orders)
      ↓
ExecutionResult[] (order confirmations)
```

## Decision Modes

### Mode 1: Target Allocation (Recommended)

**When to use:**
- Strategic rebalancing
- Multi-step position changes
- Capital constraints matter
- Allocation-based strategies

**Example strategies:**
- Balanced portfolio (40% BTC, 30% ETH, 30% cash)
- Risk-off (100% cash)
- Funding arbitrage (40% short perp, 40% long spot, 20% cash)

### Mode 2: Direct Actions (Legacy)

**When to use:**
- Time-sensitive tactical trades
- Specific order types (limit orders)
- Single-step actions
- Direct control needed

**Example strategies:**
- Breakout trading (buy BTC on signal)
- Stop-loss (close position immediately)
- Limit order placement

## Configuration

```python
# Agent initialization
agent = TradingAgent(config)

# Rebalancer settings
agent.rebalancer = PortfolioRebalancer(
    min_trade_value=10.0,        # Skip trades < $10
    max_slippage_pct=0.005,      # 0.5% max slippage
    rebalance_threshold=0.05,    # 5% deviation triggers action
)

# Tick interval
config.agent.tick_interval_seconds = 60  # Run every 60 seconds
```

## Error Handling

```
API Failure
    ↓
Retry with exponential backoff
    ↓
If all retries fail:
    - Monitor: Return stale data (if available)
    - Decision: Return error result
    - Executor: Return error result
    ↓
Log error and continue to next tick
```

## Logging

All operations are logged with structured JSON:

```json
{
  "timestamp": "2025-10-22T10:30:00Z",
  "level": "INFO",
  "tick": 42,
  "portfolio_value": 50000.0,
  "num_actions": 2,
  "selected_strategy": "balanced-growth",
  "num_rebalance_actions": 2,
  "estimated_cost": 25.0
}
```

## Performance Characteristics

- **Latency tolerance**: Minutes (suitable for LLM decision-making)
- **Tick interval**: 60 seconds (configurable)
- **Portfolio size**: $500 - $5,000 (small startup scale)
- **Trades per tick**: 0-10 (typically 1-3)
- **Decision time**: 2-10 seconds (LLM query)
- **Execution time**: 1-5 seconds per trade

## Comparison: Before vs After

### Before (Direct Actions Only)

```
LLM: "I want 40% BTC and 30% ETH"
     ↓
LLM must calculate:
  - Current BTC: 0.5 @ $52k = $26k (50%)
  - Target BTC: 40% of $50k = $20k
  - Need to sell: ($26k - $20k) / $52k = 0.115 BTC
  - Target ETH: 30% of $50k = $15k
  - Need to buy: $15k / $2.6k = 5.77 ETH
     ↓
LLM outputs:
  [SELL 0.115 BTC, BUY 5.77 ETH]
     ↓
Problems:
  ❌ LLM bad at arithmetic
  ❌ Doesn't check capital constraints
  ❌ May try to buy before selling
  ❌ Rounding errors
```

### After (Target Allocation)

```
LLM: "I want 40% BTC and 30% ETH"
     ↓
LLM outputs:
  {"BTC": 0.40, "ETH": 0.30, "USDC": 0.30}
     ↓
Rebalancer calculates:
  ✅ Precise arithmetic
  ✅ Checks capital constraints
  ✅ Orders trades correctly (sell first)
  ✅ Filters dust trades
     ↓
Outputs:
  [SELL 0.115 BTC, BUY 5.77 ETH]
```

## Summary

The new architecture separates concerns:
- **LLM**: Strategy and allocation decisions (what to do)
- **Code**: Execution planning and constraints (how to do it)

This results in:
- ✅ More reliable trade execution
- ✅ Better capital management
- ✅ Simpler LLM prompts
- ✅ Testable rebalancing logic
- ✅ Fewer execution errors
