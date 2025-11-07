# Governance Modules

Governance modules provide strategy governance, regime detection, performance tracking, and risk controls for the trading agent.

## StrategyGovernor

Enforces plan persistence, dwell times, and switching thresholds.

**Module:** `hyperliquid_agent.governance.governor`

### Constructor

```python
def __init__(
    self,
    config: GovernorConfig,
    logger: logging.Logger | None = None
) -> None
```

Initialize Strategy Governor with configuration.

**Parameters:**

- `config` (GovernorConfig): Governor configuration
- `logger` (logging.Logger | None): Optional logger for governance event logging

**Example:**

```python
from hyperliquid_agent.governance.governor import (
    StrategyGovernor,
    GovernorConfig
)

config = GovernorConfig(
    minimum_advantage_over_cost_bps=50.0,
    cooldown_after_change_minutes=60,
    partial_rotation_pct_per_cycle=25.0
)

governor = StrategyGovernor(config)
```

### Methods

#### can_review_plan

```python
def can_review_plan(self, current_time: datetime) -> tuple[bool, str]
```

Check if plan review is permitted based on dwell time and cooldown.

**Parameters:**

- `current_time` (datetime): Current timestamp

**Returns:**

- `tuple[bool, str]`: (can_review, reason_string)

**Example:**

```python
from datetime import datetime

can_review, reason = governor.can_review_plan(datetime.now())
if can_review:
    print("Plan review permitted")
else:
    print(f"Plan review blocked: {reason}")
```

#### evaluate_change_proposal

```python
def evaluate_change_proposal(
    self,
    proposal: PlanChangeProposal
) -> tuple[bool, str]
```

Evaluate whether to approve a plan change based on net advantage.

**Parameters:**

- `proposal` (PlanChangeProposal): Plan change proposal to evaluate

**Returns:**

- `tuple[bool, str]`: (approved, reason_string)

**Example:**

```python
from hyperliquid_agent.governance.governor import PlanChangeProposal

proposal = PlanChangeProposal(
    new_plan=new_strategy_plan,
    reason="Regime changed to trending-bull",
    expected_advantage_bps=75.0,
    change_cost_bps=20.0
)

approved, reason = governor.evaluate_change_proposal(proposal)
if approved:
    governor.activate_plan(proposal.new_plan, datetime.now())
```

#### activate_plan

```python
def activate_plan(
    self,
    plan: StrategyPlanCard,
    current_time: datetime
) -> None
```

Activate a new strategy plan.

**Parameters:**

- `plan` (StrategyPlanCard): Strategy plan card to activate
- `current_time` (datetime): Current timestamp

### Data Classes

#### GovernorConfig

Configuration for Strategy Governor.

**Fields:**

- `minimum_advantage_over_cost_bps` (float): Required advantage in basis points (default: 50.0)
- `cooldown_after_change_minutes` (int): Cooldown period after plan changes (default: 60)
- `partial_rotation_pct_per_cycle` (float): Percentage to rotate per cycle (default: 25.0)
- `state_persistence_path` (str): Path for state persistence (default: "state/governor.json")

#### PlanChangeProposal

Proposal for changing the active strategy plan.

**Fields:**

- `new_plan` (StrategyPlanCard): New strategy plan to activate
- `reason` (str): Reason for the change
- `expected_advantage_bps` (float): Expected advantage in basis points
- `change_cost_bps` (float): Cost of changing in basis points

**Properties:**

- `net_advantage_bps` (float): Net advantage after subtracting change cost

## RegimeDetector

Detects and classifies market regimes with hysteresis using LLM-based analysis.

**Module:** `hyperliquid_agent.governance.regime`

### Constructor

```python
def __init__(
    self,
    config: RegimeDetectorConfig,
    llm_config: LLMConfig,
    external_data_provider: ExternalDataProvider | None = None,
    logger: logging.Logger | None = None
) -> None
```

Initialize regime detector.

**Parameters:**

- `config` (RegimeDetectorConfig): Configuration for regime detection
- `llm_config` (LLMConfig): Main application LLM config
- `external_data_provider` (ExternalDataProvider | None): Optional external data source
- `logger` (logging.Logger | None): Optional logger for governance event logging

**Example:**

```python
from hyperliquid_agent.governance.regime import (
    RegimeDetector,
    RegimeDetectorConfig
)

config = RegimeDetectorConfig(
    confirmation_cycles_required=3,
    hysteresis_enter_threshold=0.7,
    hysteresis_exit_threshold=0.4
)

detector = RegimeDetector(config, llm_config)
```

### Methods

#### classify_regime

```python
def classify_regime(
    self,
    signals: RegimeSignals
) -> RegimeClassification
```

Classify current market regime using LLM-based analysis.

**Parameters:**

- `signals` (RegimeSignals): Market signals including price context

**Returns:**

- `RegimeClassification`: Classification with regime type, confidence, and reasoning

**Example:**

```python
from hyperliquid_agent.governance.regime import (
    RegimeSignals,
    PriceContext
)

price_context = PriceContext(
    current_price=50000.0,
    return_1d=2.5,
    return_7d=8.3,
    return_30d=15.2,
    return_90d=45.0,
    sma20_distance=3.2,
    sma50_distance=8.5,
    higher_highs=True,
    higher_lows=True
)

signals = RegimeSignals(
    price_context=price_context,
    price_sma_20=48500.0,
    price_sma_50=46000.0,
    adx=35.0,
    realized_vol_24h=0.025,
    avg_funding_rate=0.0008,
    bid_ask_spread_bps=5.0,
    order_book_depth=1000000.0
)

classification = detector.classify_regime(signals)
print(f"Regime: {classification.regime}")
print(f"Confidence: {classification.confidence:.2f}")
print(f"Reasoning: {classification.reasoning}")
```

#### update_and_confirm

```python
def update_and_confirm(
    self,
    classification: RegimeClassification
) -> tuple[bool, str]
```

Update regime history and check if regime change is confirmed with hysteresis.

**Parameters:**

- `classification` (RegimeClassification): Latest regime classification

**Returns:**

- `tuple[bool, str]`: (regime_changed, reason_message)

### Data Classes

#### RegimeClassification

Classification of current market regime.

**Fields:**

- `regime` (Literal): One of "trending-bull", "trending-bear", "range-bound", "carry-friendly", "event-risk", "unknown"
- `confidence` (float): Confidence score from 0.0 to 1.0
- `timestamp` (datetime): Classification timestamp
- `signals` (RegimeSignals): Signals used for classification
- `reasoning` (str): LLM reasoning for classification

#### RegimeSignals

Market signals used for regime classification.

**Fields:**

- `price_context` (PriceContext): Price action context (primary signals)
- `price_sma_20` (float): 20-period simple moving average
- `price_sma_50` (float): 50-period simple moving average
- `adx` (float): Average Directional Index
- `realized_vol_24h` (float): 24-hour realized volatility
- `avg_funding_rate` (float): Average funding rate
- `bid_ask_spread_bps` (float): Bid-ask spread in basis points
- `order_book_depth` (float): Order book depth

## PlanScorekeeper

Tracks plan-level performance and manages shadow portfolios.

**Module:** `hyperliquid_agent.governance.scorekeeper`

### Constructor

```python
def __init__(self, logger: logging.Logger | None = None) -> None
```

Initialize the Plan Scorekeeper.

**Parameters:**

- `logger` (logging.Logger | None): Optional logger for governance event logging

**Example:**

```python
from hyperliquid_agent.governance.scorekeeper import PlanScorekeeper

scorekeeper = PlanScorekeeper()
```

### Methods

#### start_tracking_plan

```python
def start_tracking_plan(
    self,
    plan: StrategyPlanCard,
    initial_portfolio_value: float
) -> None
```

Begin tracking a new plan.

**Parameters:**

- `plan` (StrategyPlanCard): Strategy plan card to track
- `initial_portfolio_value` (float): Starting portfolio value

#### update_metrics

```python
def update_metrics(
    self,
    account_state: AccountState,
    plan: StrategyPlanCard
) -> None
```

Update metrics for the active plan.

**Parameters:**

- `account_state` (AccountState): Current account state
- `plan` (StrategyPlanCard): Active strategy plan card

#### finalize_plan

```python
def finalize_plan(
    self,
    final_portfolio_value: float
) -> str
```

Finalize plan tracking and generate post-mortem summary.

**Parameters:**

- `final_portfolio_value` (float): Final portfolio value at plan completion

**Returns:**

- `str`: Natural language post-mortem summary

**Example:**

```python
# Start tracking
scorekeeper.start_tracking_plan(plan, 10000.0)

# Update metrics each cycle
scorekeeper.update_metrics(account_state, plan)

# Finalize when plan ends
summary = scorekeeper.finalize_plan(10500.0)
print(summary)
```

#### add_shadow_portfolio

```python
def add_shadow_portfolio(
    self,
    strategy_name: str,
    initial_positions: dict[str, float],
    initial_value: float
) -> None
```

Add a new shadow portfolio for paper trading alternative strategies.

**Parameters:**

- `strategy_name` (str): Name of the shadow strategy
- `initial_positions` (dict[str, float]): Initial paper positions (coin -> size)
- `initial_value` (float): Initial portfolio value

#### estimate_opportunity_cost

```python
def estimate_opportunity_cost(self) -> float
```

Estimate opportunity cost of staying vs switching strategies.

**Returns:**

- `float`: Opportunity cost in basis points (positive means shadow is outperforming)

### Data Classes

#### PlanMetrics

Performance metrics for a strategy plan.

**Fields:**

- `plan_id` (str): Plan identifier
- `start_time` (datetime): Plan start time
- `end_time` (datetime | None): Plan end time
- `total_pnl` (float): Total profit/loss
- `total_risk_taken` (float): Total risk taken
- `pnl_per_unit_risk` (float): PnL per unit of risk
- `total_trades` (int): Total number of trades
- `winning_trades` (int): Number of winning trades
- `hit_rate` (float): Win rate percentage
- `avg_slippage_bps` (float): Average slippage in basis points
- `avg_drift_from_targets_pct` (float): Average drift from target allocations
- `rebalance_count` (int): Number of rebalances
- `initial_portfolio_value` (float): Initial portfolio value
- `peak_portfolio_value` (float): Peak portfolio value
- `max_drawdown_pct` (float): Maximum drawdown percentage

## TripwireService

Independent safety monitoring service with override authority.

**Module:** `hyperliquid_agent.governance.tripwire`

### Constructor

```python
def __init__(
    self,
    config: TripwireConfig,
    logger: logging.Logger | None = None
) -> None
```

Initialize the tripwire service.

**Parameters:**

- `config` (TripwireConfig): Tripwire configuration
- `logger` (logging.Logger | None): Optional logger for governance event logging

**Example:**

```python
from hyperliquid_agent.governance.tripwire import (
    TripwireService,
    TripwireConfig
)

config = TripwireConfig(
    min_margin_ratio=0.15,
    daily_loss_limit_pct=5.0,
    max_data_staleness_seconds=300
)

tripwire = TripwireService(config)
```

### Methods

#### check_all_tripwires

```python
def check_all_tripwires(
    self,
    account_state: AccountState,
    active_plan: StrategyPlanCard | None
) -> list[TripwireEvent]
```

Check all tripwire conditions and return triggered events.

**Parameters:**

- `account_state` (AccountState): Current account state
- `active_plan` (StrategyPlanCard | None): Active strategy plan card (if any)

**Returns:**

- `list[TripwireEvent]`: List of all triggered tripwire events

**Example:**

```python
events = tripwire.check_all_tripwires(account_state, active_plan)

for event in events:
    print(f"Tripwire fired: {event.trigger}")
    print(f"Severity: {event.severity}")
    print(f"Action: {event.action.value}")
    
    if event.severity == "critical":
        # Take immediate action
        handle_critical_tripwire(event)
```

#### reset_daily_tracking

```python
def reset_daily_tracking(
    self,
    current_portfolio_value: float
) -> None
```

Reset daily tracking metrics (call at start of new trading day).

**Parameters:**

- `current_portfolio_value` (float): Current portfolio value to use as baseline

### Data Classes

#### TripwireConfig

Configuration for tripwire service.

**Fields:**

- `min_margin_ratio` (float): Minimum margin ratio (default: 0.15)
- `liquidation_proximity_threshold` (float): Liquidation proximity threshold (default: 0.25)
- `daily_loss_limit_pct` (float): Daily loss limit percentage (default: 5.0)
- `check_invalidation_triggers` (bool): Check plan invalidation triggers (default: True)
- `max_data_staleness_seconds` (int): Maximum data staleness (default: 300)
- `max_api_failure_count` (int): Maximum API failure count (default: 3)

#### TripwireEvent

Event representing a triggered tripwire.

**Fields:**

- `severity` (Literal["warning", "critical"]): Event severity
- `category` (Literal): One of "account_safety", "plan_invalidation", "operational"
- `trigger` (str): Trigger identifier
- `action` (TripwireAction): Action to take
- `timestamp` (datetime): Event timestamp
- `details` (dict): Additional event details

#### TripwireAction

Actions that can be triggered by tripwires.

**Values:**

- `FREEZE_NEW_RISK`: Prevent new risk-taking
- `CUT_SIZE_TO_FLOOR`: Reduce position sizes to minimum
- `ESCALATE_TO_SLOW_LOOP`: Escalate to slow decision loop
- `INVALIDATE_PLAN`: Invalidate current strategy plan

## See Also

- [Core Modules](/api/core) - Main agent and execution
- [Signal Modules](/api/signals) - Signal collection and processing
- [Governance Architecture](/architecture/governance) - Detailed governance design
- [Configuration](/guide/configuration) - Governance configuration options
