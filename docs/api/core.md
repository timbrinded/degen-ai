# Core Modules

Core modules provide the fundamental trading agent functionality including agent orchestration, trade execution, and portfolio management.

## TradingAgent

Main trading agent that orchestrates the trading loop.

**Module:** `hyperliquid_agent.agent`

### Constructor

```python
def __init__(self, config: Config) -> None
```

Initialize the trading agent with configuration.

**Parameters:**

- `config` (Config): Configuration instance containing all settings

**Raises:**

- `RuntimeError`: If asset identities fail to load

**Example:**

```python
from hyperliquid_agent.agent import TradingAgent
from hyperliquid_agent.config import load_config

config = load_config("config.toml")
agent = TradingAgent(config)
```

### Methods

#### run

```python
def run(self) -> NoReturn
```

Run the main agent loop indefinitely. Executes trading cycles at configured intervals.

**Example:**

```python
agent = TradingAgent(config)
agent.run()  # Runs forever
```

#### _execute_tick

```python
def _execute_tick(self) -> None
```

Execute one iteration of the trading loop. This method:

1. Monitors current positions and account state
2. Gets trading decision from LLM
3. Generates rebalancing plan if target allocation provided
4. Executes trades with retry logic

**Internal method** - called automatically by `run()`.

## TradeExecutor

Executes trades on the Hyperliquid platform.

**Module:** `hyperliquid_agent.executor`

### Constructor

```python
def __init__(
    self,
    config: HyperliquidConfig,
    registry: MarketRegistry,
    *,
    identity_registry: AssetIdentityRegistry | None = None,
) -> None
```

Initialize the trade executor.

**Parameters:**

- `config` (HyperliquidConfig): Hyperliquid configuration with credentials
- `registry` (MarketRegistry): Market registry for symbol resolution (must be hydrated)
- `identity_registry` (AssetIdentityRegistry | None): Optional asset identity registry

**Raises:**

- `RuntimeError`: If spot metadata cannot be fetched or is malformed

**Example:**

```python
from hyperliquid_agent.executor import TradeExecutor
from hyperliquid_agent.market_registry import MarketRegistry
from hyperliquid.info import Info

info = Info(config.hyperliquid.base_url, skip_ws=True)
registry = MarketRegistry(info)
await registry.hydrate()

executor = TradeExecutor(config.hyperliquid, registry)
```

### Methods

#### execute_action

```python
def execute_action(self, action: TradeAction) -> ExecutionResult
```

Execute a single trade action.

**Parameters:**

- `action` (TradeAction): Trade action to execute

**Returns:**

- `ExecutionResult`: Execution result with success status and details

**Example:**

```python
from hyperliquid_agent.decision import TradeAction

action = TradeAction(
    action_type="buy",
    coin="BTC",
    market_type="perp",
    size=0.1,
    price=None,  # Market order
    reasoning="Enter long position"
)

result = executor.execute_action(action)
if result.success:
    print(f"Order executed: {result.order_id}")
else:
    print(f"Execution failed: {result.error}")
```

### Data Classes

#### ExecutionResult

Result of a trade execution attempt.

**Fields:**

- `action` (TradeAction): The action that was executed
- `success` (bool): Whether execution succeeded
- `order_id` (str | None): Order ID if successful
- `error` (str | None): Error message if failed

## PortfolioRebalancer

Generates rebalancing plans to move from current to target allocation.

**Module:** `hyperliquid_agent.portfolio`

### Constructor

```python
def __init__(
    self,
    min_trade_value: float = 10.0,
    max_slippage_pct: float = 0.005,
    rebalance_threshold: float = 0.05,
) -> None
```

Initialize the rebalancer with trading constraints.

**Parameters:**

- `min_trade_value` (float): Minimum trade value in USD (default: 10.0)
- `max_slippage_pct` (float): Maximum acceptable slippage percentage (default: 0.005)
- `rebalance_threshold` (float): Minimum allocation deviation to trigger rebalance (default: 0.05)

**Example:**

```python
from hyperliquid_agent.portfolio import PortfolioRebalancer

rebalancer = PortfolioRebalancer(
    min_trade_value=10.0,
    max_slippage_pct=0.005,
    rebalance_threshold=0.05
)
```

### Methods

#### create_rebalancing_plan

```python
def create_rebalancing_plan(
    self,
    current: PortfolioState,
    target: TargetAllocation,
    market_type: Literal["spot", "perp"] = "perp",
) -> RebalancingPlan
```

Generate ordered list of trades to rebalance portfolio.

**Strategy:**

1. Close positions that need to be reduced or eliminated
2. Open/increase positions that need to grow
3. Respect capital constraints and minimum trade sizes

**Parameters:**

- `current` (PortfolioState): Current portfolio state
- `target` (TargetAllocation): Target allocation percentages
- `market_type` (Literal["spot", "perp"]): Market type for new positions (default: "perp")

**Returns:**

- `RebalancingPlan`: Ordered actions with estimated cost

**Example:**

```python
from hyperliquid_agent.portfolio import (
    PortfolioState,
    TargetAllocation,
    PortfolioRebalancer
)

# Convert account state to portfolio state
portfolio_state = PortfolioState.from_account_state(account_state)

# Define target allocation
target = TargetAllocation(
    allocations={
        "BTC": 0.4,
        "ETH": 0.3,
        "USDC": 0.3
    },
    strategy_id="trend-following"
)

# Generate rebalancing plan
rebalancer = PortfolioRebalancer()
plan = rebalancer.create_rebalancing_plan(portfolio_state, target)

print(f"Actions: {len(plan.actions)}")
print(f"Estimated cost: ${plan.estimated_cost:.2f}")
print(f"Reasoning: {plan.reasoning}")

# Execute actions
for action in plan.actions:
    result = executor.execute_action(action)
```

### Data Classes

#### PortfolioState

Current portfolio state with allocation percentages.

**Fields:**

- `total_value` (float): Total portfolio value in USD
- `available_balance` (float): Available cash balance
- `allocations` (dict[str, float]): Current allocation percentages by coin
- `positions` (dict[str, Position]): Current positions by coin
- `timestamp` (float): State timestamp

**Class Methods:**

```python
@classmethod
def from_account_state(cls, account_state: AccountState) -> "PortfolioState"
```

Convert AccountState to PortfolioState with computed allocation percentages.

#### TargetAllocation

Target portfolio allocation as percentages.

**Fields:**

- `allocations` (dict[str, float]): Target allocation percentages (0.0 to 1.0)
- `strategy_id` (str | None): Strategy identifier
- `reasoning` (str): Allocation reasoning

**Methods:**

```python
def validate(self) -> bool
```

Validate that allocations sum to approximately 1.0.

#### RebalancingPlan

Ordered sequence of trades to achieve target allocation.

**Fields:**

- `actions` (list[TradeAction]): Ordered list of trade actions
- `estimated_cost` (float): Estimated fees and slippage
- `reasoning` (str): Plan reasoning

## Utility Functions

### retry_with_backoff

```python
def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int,
    backoff_base: float
) -> T
```

Retry a function with exponential backoff.

**Parameters:**

- `func` (Callable): Function to retry
- `max_retries` (int): Maximum number of retry attempts
- `backoff_base` (float): Base for exponential backoff calculation

**Returns:**

- Result of the function call

**Raises:**

- `Exception`: If all retries are exhausted

**Example:**

```python
from hyperliquid_agent.agent import retry_with_backoff

result = retry_with_backoff(
    lambda: monitor.get_current_state(),
    max_retries=3,
    backoff_base=2.0
)
```

## See Also

- [Governance Modules](/api/governance) - Strategy governance and risk controls
- [Signal Modules](/api/signals) - Signal collection and processing
- [Portfolio Management Architecture](/architecture/portfolio) - Detailed portfolio design
- [Getting Started](/guide/getting-started) - Quick start guide
