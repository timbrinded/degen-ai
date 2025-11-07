# Trading Agent Architecture - Portfolio Management

## System Flow

```mermaid
flowchart TD
    Start([TRADING AGENT LOOP<br/>Every tick_interval])
    
    Start --> Step1["STEP 1: Monitor Positions<br/><br/>PositionMonitor.get_current_state()<br/>• Fetch from Hyperliquid API<br/>• Parse positions, balances<br/>• Return AccountState<br/><br/>AccountState:<br/>portfolio_value: 50000.0<br/>available_balance: 15000.0<br/>positions: BTC: 0.5, ETH: 6.0"]
    
    Step1 --> Step2["STEP 2: LLM Decision<br/><br/>DecisionEngine.get_decision()<br/>• Format prompt<br/>• Query LLM (OpenAI/Anthropic)<br/>• Parse response"]
    
    Step2 --> Decision{Target Allocation<br/>Provided?}
    
    Decision -->|YES: Target Allocation| Step2_5["STEP 2.5: Generate Rebalancing Plan<br/><br/>PortfolioRebalancer.create_rebalancing_plan()<br/><br/>1. Convert AccountState → PortfolioState<br/>2. Calculate deltas (target - current)<br/>3. Filter insignificant deviations<br/>4. Phase 1: Close/reduce overweight<br/>5. Phase 2: Open/increase underweight"]
    
    Decision -->|NO: Direct Actions| Merge((Merge))
    
    Step2_5 --> Merge
    
    Merge --> Step3["STEP 3: Execute Trades<br/><br/>For each action:<br/>• Validate parameters<br/>• Submit order to Hyperliquid<br/>• Return ExecutionResult<br/><br/>With retry logic"]
    
    Step3 --> Sleep([Sleep until<br/>next tick])
    
    Sleep --> Start
    
    style Start fill:#e1f5ff
    style Step1 fill:#fff4e1
    style Step2 fill:#ffe1f5
    style Step2_5 fill:#e1ffe1
    style Step3 fill:#ffd4e1
    style Sleep fill:#e1f5ff
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

```mermaid
flowchart TD
    A[AccountState<br/>raw positions] --> B[PortfolioState<br/>allocation percentages]
    B --> C[TargetAllocation<br/>desired percentages]
    C --> D[RebalancingPlan<br/>ordered trades]
    D --> E[TradeAction[]<br/>individual orders]
    E --> F[ExecutionResult[]<br/>order confirmations]
    
    style A fill:#e1f5ff
    style B fill:#fff4e1
    style C fill:#ffe1f5
    style D fill:#e1ffe1
    style E fill:#ffd4e1
    style F fill:#d4e1ff
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

```mermaid
flowchart TD
    A[API Failure] --> B[Retry with exponential backoff]
    B --> C{All retries<br/>failed?}
    C -->|Yes| D[Handle by component]
    C -->|No| E[Success]
    
    D --> F[Monitor: Return stale data]
    D --> G[Decision: Return error result]
    D --> H[Executor: Return error result]
    
    F --> I[Log error and continue to next tick]
    G --> I
    H --> I
    
    style A fill:#ffcccc
    style C fill:#fff4e1
    style I fill:#e1f5ff
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

```mermaid
flowchart TD
    A["LLM: 'I want 40% BTC and 30% ETH'"] --> B["LLM must calculate:<br/>• Current BTC: 0.5 @ $52k = $26k (50%)<br/>• Target BTC: 40% of $50k = $20k<br/>• Need to sell: ($26k - $20k) / $52k = 0.115 BTC<br/>• Target ETH: 30% of $50k = $15k<br/>• Need to buy: $15k / $2.6k = 5.77 ETH"]
    
    B --> C["LLM outputs:<br/>[SELL 0.115 BTC, BUY 5.77 ETH]"]
    
    C --> D["Problems:<br/>❌ LLM bad at arithmetic<br/>❌ Doesn't check capital constraints<br/>❌ May try to buy before selling<br/>❌ Rounding errors"]
    
    style A fill:#ffe1f5
    style B fill:#fff4e1
    style C fill:#e1f5ff
    style D fill:#ffcccc
```

### After (Target Allocation)

```mermaid
flowchart TD
    A["LLM: 'I want 40% BTC and 30% ETH'"] --> B["LLM outputs:<br/>{BTC: 0.40, ETH: 0.30, USDC: 0.30}"]
    
    B --> C["Rebalancer calculates:<br/>✅ Precise arithmetic<br/>✅ Checks capital constraints<br/>✅ Orders trades correctly (sell first)<br/>✅ Filters dust trades"]
    
    C --> D["Outputs:<br/>[SELL 0.115 BTC, BUY 5.77 ETH]"]
    
    style A fill:#ffe1f5
    style B fill:#e1ffe1
    style C fill:#e1ffe1
    style D fill:#e1f5ff
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
