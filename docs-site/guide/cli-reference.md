# CLI Reference

Complete command-line interface reference for the Hyperliquid Trading Agent.

## Overview

The trading agent provides a comprehensive CLI for managing trading operations, monitoring positions, running backtests, and inspecting governance state. All commands are executed through the Python module:

```bash
uv run python -m hyperliquid_agent.cli <command> [OPTIONS]
```

## Commands

### start

Start the Hyperliquid trading agent in either standard or governed mode.

**Usage:**

```bash
uv run python -m hyperliquid_agent.cli start [OPTIONS]
```

**Options:**

- `--config` / `-c` - Path to configuration file (default: `config.toml`)
- `--governed` / `-g` - Run in governed mode with multi-timescale decision-making (default: `False`)
- `--async` / `--sync` - Use async concurrent loop execution (default: `--async`)

**Standard Mode:**

Standard mode runs a single decision loop that collects signals, makes trading decisions via LLM, and executes trades.

```bash
# Start in standard mode with default config
uv run python -m hyperliquid_agent.cli start

# Start with custom config file
uv run python -m hyperliquid_agent.cli start --config my-config.toml
```

**Governed Mode:**

Governed mode enables multi-timescale decision-making with three concurrent loops:

- **Fast loop**: Real-time signal collection and position monitoring
- **Medium loop**: Technical indicator calculation and tactical adjustments
- **Slow loop**: Macro event tracking and strategic regime classification

```bash
# Start in governed mode
uv run python -m hyperliquid_agent.cli start --governed

# Start in governed mode with sync execution (sequential loops)
uv run python -m hyperliquid_agent.cli start --governed --sync
```

**Async vs Sync Execution:**

- **Async mode** (default): All three loops run concurrently using asyncio, providing maximum responsiveness
- **Sync mode**: Loops execute sequentially in order (fast → medium → slow), useful for debugging or resource-constrained environments

**Example Output:**

```
Starting agent in GOVERNED mode...
  Fast loop: every 30s | Medium loop: every 15m | Slow loop: every 4h
  Execution mode: ASYNC (concurrent loops)
```

---

### status

Check current account status, portfolio value, and open positions.

**Usage:**

```bash
uv run python -m hyperliquid_agent.cli status [OPTIONS]
```

**Options:**

- `--config` / `-c` - Path to configuration file (default: `config.toml`)

**Examples:**

```bash
# Check account status with default config
uv run python -m hyperliquid_agent.cli status

# Check status with custom config
uv run python -m hyperliquid_agent.cli status --config testnet-config.toml
```

**Example Output:**

```
Fetching account state...

============================================================
Account Status
============================================================
Portfolio Value:    $10,523.45
Available Balance:  $8,234.12
Number of Positions: 2

============================================================
Positions:
============================================================

BTC (PERP)
  Size:          0.1500
  Entry Price:   $42,150.00
  Current Price: $43,200.00
  Unrealized PnL: +$157.50

ETH (SPOT)
  Size:          5.0000
  Entry Price:   $2,245.00
  Current Price: $2,310.00
  Unrealized PnL: +$325.00

============================================================
```

**Output Fields:**

- **Portfolio Value**: Total account value including positions and available balance
- **Available Balance**: Cash available for new positions
- **Number of Positions**: Count of open positions
- **Size**: Position size in base currency
- **Entry Price**: Average entry price for the position
- **Current Price**: Current market price
- **Unrealized PnL**: Profit/loss on open position

---

### backtest

Run regime detection backtest on historical Hyperliquid data.

**Usage:**

```bash
uv run python -m hyperliquid_agent.cli backtest [OPTIONS]
```

**Options:**

- `--start-date` - Backtest start date in ISO 8601 format (e.g., `2024-01-01`) **[REQUIRED]**
- `--end-date` - Backtest end date in ISO 8601 format (e.g., `2024-03-31`) **[REQUIRED]**
- `--interval` - Sampling interval for data points: `1h`, `4h`, or `1d` (default: `4h`)
- `--assets` - Comma-separated list of asset symbols (default: `BTC,ETH`)
- `--output` - Output directory for backtest results (default: `./backtest_results`)
- `--config` / `-c` - Path to configuration file (default: `config.toml`)
- `--clear-cache` - Clear cached historical data before running backtest (default: `False`)

**Examples:**

```bash
# Run 3-month backtest with default settings
uv run python -m hyperliquid_agent.cli backtest \
  --start-date 2024-01-01 \
  --end-date 2024-03-31

# Run 1-year backtest with hourly sampling
uv run python -m hyperliquid_agent.cli backtest \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --interval 1h

# Run backtest for specific assets
uv run python -m hyperliquid_agent.cli backtest \
  --start-date 2024-01-01 \
  --end-date 2024-03-31 \
  --assets BTC,ETH,SOL

# Clear cache before running (useful if data seems stale)
uv run python -m hyperliquid_agent.cli backtest \
  --start-date 2024-06-01 \
  --end-date 2024-07-01 \
  --clear-cache
```

**Output:**

The backtest command generates three output files in the specified directory:

- `summary.txt` - Human-readable summary with regime distribution and statistics
- `results.csv` - Detailed CSV export with timestamp, regime, confidence, and signals
- `timeline.png` - Visual timeline showing regime transitions over time

**Example Console Output:**

```
================================================================================
BACKTEST COMPLETE
================================================================================

Execution Time: 45.3 seconds

Results:
  Total Points: 720
  Collected Points: 698
  Skipped Points: 22
  Skip Rate: 3.1%

Regime Distribution:
  bull                : 35.24%
  ranging             : 28.65%
  bear                : 18.91%
  volatile            : 12.32%
  funding_extreme     :  4.87%

Generated Reports:
  Summary: ./backtest_results/summary.txt
  CSV Data: ./backtest_results/results.csv
  Visualization: ./backtest_results/timeline.png

================================================================================
```

For detailed backtesting guidance, see the [Backtesting Guide](/guide/backtesting).

---

### gov_plan

Show active governance plan status including strategy, allocations, and risk budget.

**Usage:**

```bash
uv run python -m hyperliquid_agent.cli gov_plan [OPTIONS]
```

**Options:**

- `--config` / `-c` - Path to configuration file (default: `config.toml`)

**Examples:**

```bash
# View active plan status
uv run python -m hyperliquid_agent.cli gov_plan

# View plan with custom config
uv run python -m hyperliquid_agent.cli gov_plan --config governed-config.toml
```

**Example Output:**

```
======================================================================
ACTIVE PLAN STATUS
======================================================================

Plan ID:          plan_20240315_143022
Strategy:         funding-harvest-lite (v1.2)
Status:           ACTIVE
Objective:        Harvest funding rate arbitrage opportunities
Time Horizon:     short_term
Target Duration:  24h

----------------------------------------------------------------------
TIMING
----------------------------------------------------------------------
Created:          2024-03-15 14:30:22
Activated:        2024-03-15 14:35:10
Dwell Time:       45.2 / 60 min
Cooldown:         0.0 min
Can Review:       ✗ NO
Review Reason:    Minimum dwell time not met (need 14.8 more minutes)
Rebalance:        75.0% complete

----------------------------------------------------------------------
TARGET ALLOCATIONS
----------------------------------------------------------------------
  BTC      30.00% (perp, 2x)
  ETH      25.00% (perp, 2x)
  SOL      15.00% (perp, 3x)

----------------------------------------------------------------------
RISK BUDGET
----------------------------------------------------------------------
Max Leverage:     3x
Max Adverse Exc:  5.0%
Max Drawdown:     8.0%

----------------------------------------------------------------------
REGIME COMPATIBILITY
----------------------------------------------------------------------
Compatible:       bull, ranging, funding_extreme
Avoid:            bear, volatile

======================================================================
```

**Output Interpretation:**

- **Plan ID**: Unique identifier for the active plan
- **Strategy**: Strategy name and version from plan card metadata
- **Status**: Current plan state (ACTIVE, PENDING, COMPLETED)
- **Dwell Time**: Time elapsed since activation / minimum required before review
- **Can Review**: Whether the plan can be reviewed for rotation (requires minimum dwell time and cooldown)
- **Rebalance Progress**: Percentage of target allocations achieved (gradual rotation)
- **Target Allocations**: Desired position sizes per asset with market type and leverage
- **Risk Budget**: Maximum risk parameters from plan card
- **Regime Compatibility**: Market regimes where this strategy performs well

---

### gov_regime

Show current regime classification status and recent history.

**Usage:**

```bash
uv run python -m hyperliquid_agent.cli gov_regime [OPTIONS]
```

**Options:**

- `--config` / `-c` - Path to configuration file (default: `config.toml`)

**Examples:**

```bash
# View current regime
uv run python -m hyperliquid_agent.cli gov_regime

# View regime with custom config
uv run python -m hyperliquid_agent.cli gov_regime --config governed-config.toml
```

**Example Output:**

```
======================================================================
REGIME CLASSIFICATION STATUS
======================================================================

Current Regime:   BULL
History Length:   127 classifications

----------------------------------------------------------------------
CONFIGURATION
----------------------------------------------------------------------
Confirmation Cycles:  3
Enter Threshold:      0.70
Exit Threshold:       0.40

----------------------------------------------------------------------
RECENT CLASSIFICATIONS
----------------------------------------------------------------------
  2024-03-15 14:30:00 | bull            | confidence: 0.85
  2024-03-15 14:00:00 | bull            | confidence: 0.82
  2024-03-15 13:30:00 | ranging         | confidence: 0.68
  2024-03-15 13:00:00 | ranging         | confidence: 0.72
  2024-03-15 12:30:00 | ranging         | confidence: 0.75

======================================================================
```

**Output Interpretation:**

- **Current Regime**: Active market regime classification (bull, bear, ranging, volatile, funding_extreme)
- **History Length**: Total number of regime classifications recorded
- **Confirmation Cycles**: Number of consecutive classifications required before regime change
- **Enter Threshold**: Confidence threshold to enter a new regime
- **Exit Threshold**: Confidence threshold to exit current regime (hysteresis prevents oscillation)
- **Recent Classifications**: Last 5 regime classifications with timestamps and confidence scores

**Event Lock:**

When a high-impact macro event is imminent, the regime detector enters "event lock" mode:

```
⚠️  EVENT LOCK ACTIVE
    High-impact event within lock window: FOMC Rate Decision at 2024-03-20 14:00
```

During event lock, regime changes are suppressed to avoid whipsaw during volatile periods.

---

### gov_tripwire

Show tripwire status and active risk alerts.

**Usage:**

```bash
uv run python -m hyperliquid_agent.cli gov_tripwire [OPTIONS]
```

**Options:**

- `--config` / `-c` - Path to configuration file (default: `config.toml`)

**Examples:**

```bash
# Check tripwire status
uv run python -m hyperliquid_agent.cli gov_tripwire

# Check tripwires with custom config
uv run python -m hyperliquid_agent.cli gov_tripwire --config governed-config.toml
```

**Example Output (No Alerts):**

```
======================================================================
TRIPWIRE STATUS
======================================================================

Active Tripwires: 0

✓ All systems nominal - no tripwires active

----------------------------------------------------------------------
CURRENT STATE
----------------------------------------------------------------------
Portfolio Value:  $10,523.45
Daily Loss:       -1.23%
API Failures:     0

----------------------------------------------------------------------
CONFIGURATION
----------------------------------------------------------------------
Min Margin Ratio:         0.15
Liquidation Threshold:    0.25
Daily Loss Limit:         5.0%
Max Data Staleness:       300s
Max API Failures:         3

======================================================================
```

**Example Output (With Alerts):**

```
======================================================================
TRIPWIRE STATUS
======================================================================

Active Tripwires: 2

⚠️  ALERTS ACTIVE

----------------------------------------------------------------------
TRIGGERED EVENTS
----------------------------------------------------------------------

🟡 WARNING - margin_ratio
   Trigger: Margin ratio below threshold
   Action:  reduce_exposure
   Time:    2024-03-15 14:25:33
   Details: Current margin ratio: 0.18, threshold: 0.20

🔴 CRITICAL - daily_loss_limit
   Trigger: Daily loss limit exceeded
   Action:  emergency_close_all
   Time:    2024-03-15 14:30:15
   Details: Daily loss: -5.2%, limit: -5.0%

----------------------------------------------------------------------
CURRENT STATE
----------------------------------------------------------------------
Portfolio Value:  $9,480.00
Daily Loss:       -5.23%
API Failures:     0

----------------------------------------------------------------------
CONFIGURATION
----------------------------------------------------------------------
Min Margin Ratio:         0.15
Liquidation Threshold:    0.25
Daily Loss Limit:         5.0%
Max Data Staleness:       300s
Max API Failures:         3

======================================================================
```

**Output Interpretation:**

- **Active Tripwires**: Count of currently triggered risk alerts
- **Severity**: 🟡 WARNING (reduce exposure) or 🔴 CRITICAL (emergency close)
- **Category**: Type of tripwire (margin_ratio, liquidation_proximity, daily_loss_limit, data_staleness, api_failures)
- **Trigger**: Condition that activated the tripwire
- **Action**: Automated response taken by the system
- **Current State**: Real-time portfolio metrics
- **Configuration**: Tripwire thresholds from config file

**Tripwire Categories:**

- **margin_ratio**: Triggers when account margin ratio falls below minimum
- **liquidation_proximity**: Triggers when positions approach liquidation price
- **daily_loss_limit**: Triggers when daily loss exceeds percentage threshold
- **data_staleness**: Triggers when market data becomes too old
- **api_failures**: Triggers after consecutive API call failures

---

### gov_metrics

Show plan performance metrics and execution quality.

**Usage:**

```bash
uv run python -m hyperliquid_agent.cli gov_metrics [OPTIONS]
```

**Options:**

- `--config` / `-c` - Path to configuration file (default: `config.toml`)

**Examples:**

```bash
# View performance metrics
uv run python -m hyperliquid_agent.cli gov_metrics

# View metrics with custom config
uv run python -m hyperliquid_agent.cli gov_metrics --config governed-config.toml
```

**Example Output:**

```
======================================================================
PLAN PERFORMANCE METRICS
======================================================================

Plan ID:          plan_20240315_143022
Start Time:       2024-03-15 14:30:22
Duration:         8.50 hours

----------------------------------------------------------------------
PERFORMANCE
----------------------------------------------------------------------
Total PnL:        +$234.56
Risk Taken:       45.20
PnL per Risk:     5.1903

----------------------------------------------------------------------
EXECUTION QUALITY
----------------------------------------------------------------------
Total Trades:     12
Winning Trades:   8
Hit Rate:         66.7%
Avg Slippage:     2.34 bps

----------------------------------------------------------------------
PLAN ADHERENCE
----------------------------------------------------------------------
Avg Drift:        1.23%
Rebalances:       3

----------------------------------------------------------------------
TRACKING
----------------------------------------------------------------------
Completed Plans:  5
Shadow Portfolios: 2

======================================================================
```

**Output Interpretation:**

- **Plan ID**: Identifier for the currently active plan
- **Duration**: Time elapsed since plan activation
- **Total PnL**: Cumulative profit/loss for this plan
- **Risk Taken**: Total risk exposure measured in risk units
- **PnL per Risk**: Risk-adjusted return (higher is better)
- **Total Trades**: Number of trades executed under this plan
- **Winning Trades**: Number of profitable trades
- **Hit Rate**: Percentage of winning trades
- **Avg Slippage**: Average execution slippage in basis points
- **Avg Drift**: Average deviation from target allocations
- **Rebalances**: Number of portfolio rebalancing operations
- **Completed Plans**: Total number of plans completed historically
- **Shadow Portfolios**: Number of alternative strategies being tracked

**No Active Plan:**

```
======================================================================
PLAN PERFORMANCE METRICS
======================================================================

No active plan to report metrics for.
Completed Plans: 5

======================================================================
```

---

### test_executor

Test the trade executor with a single action on testnet.

**Usage:**

```bash
uv run python -m hyperliquid_agent.cli test_executor [OPTIONS]
```

**Options:**

- `--config` / `-c` - Path to configuration file (default: `config.toml`)
- `--coin` - Coin to test with (default: `BTC`)
- `--action` - Action type: `buy`, `sell`, `hold`, or `close` (default: `buy`)
- `--market` - Market type: `spot` or `perp` (default: `perp`)
- `--size` - Order size in base currency (default: `0.001`)
- `--price` - Limit price (optional, uses market order if not specified)

**Examples:**

```bash
# Test market buy order for BTC perp
uv run python -m hyperliquid_agent.cli test_executor \
  --coin BTC \
  --action buy \
  --size 0.001

# Test limit sell order for ETH spot
uv run python -m hyperliquid_agent.cli test_executor \
  --coin ETH \
  --action sell \
  --market spot \
  --size 0.1 \
  --price 2300.00

# Test close position for SOL perp
uv run python -m hyperliquid_agent.cli test_executor \
  --coin SOL \
  --action close

# Test with testnet config
uv run python -m hyperliquid_agent.cli test_executor \
  --config testnet-config.toml \
  --coin BTC \
  --action buy \
  --size 0.01
```

**Interactive Confirmation:**

The command displays order details and requires confirmation before execution:

```
============================================================
Testing Trade Executor
============================================================
Action:  BUY
Coin:    BTC
Market:  PERP
Size:    0.001
Price:   MARKET
============================================================

Execute this test order? [y/N]: y

Executing order...

============================================================
Execution Result
============================================================
Success:  True
Order ID: 0x1234567890abcdef
============================================================
```

**Safety Warnings:**

⚠️ **IMPORTANT SAFETY NOTES:**

1. **Use Testnet First**: Always test with testnet configuration before using mainnet
2. **Small Sizes**: Start with minimal order sizes to verify behavior
3. **Real Money**: Orders executed on mainnet use real funds and cannot be reversed
4. **Market Orders**: Market orders execute immediately at current price with potential slippage
5. **Limit Orders**: Limit orders may not fill if price doesn't reach specified level

**Testnet Configuration:**

To use testnet, ensure your config file has testnet settings:

```toml
[hyperliquid]
base_url = "https://api.hyperliquid-testnet.xyz"
private_key = "your_testnet_private_key"
account_address = "your_testnet_address"
```

**Error Handling:**

If execution fails, the command displays error details:

```
============================================================
Execution Result
============================================================
Success:  False
Error:    Insufficient margin for order
============================================================
```

**Common Errors:**

- **Insufficient margin**: Account doesn't have enough balance for the order
- **Invalid symbol**: Coin not supported on the exchange
- **Size too small**: Order size below minimum for the market
- **Price out of range**: Limit price too far from current market price
- **Market closed**: Trading temporarily suspended for the asset

---

## Related Documentation

- [Getting Started Guide](/guide/getting-started) - Initial setup and configuration
- [Configuration Reference](/guide/configuration) - Detailed config file documentation
- [Backtesting Guide](/guide/backtesting) - In-depth backtesting tutorial
- [Governance Architecture](/architecture/governance) - Governance system design
- [Deployment Guide](/guide/deployment) - Production deployment instructions

## Tips and Best Practices

### Running in Background

Use `nohup` or `screen` to run the agent in the background:

```bash
# Using nohup
nohup uv run python -m hyperliquid_agent.cli start --governed > agent.log 2>&1 &

# Using screen
screen -S trading-agent
uv run python -m hyperliquid_agent.cli start --governed
# Press Ctrl+A, then D to detach
```

### Monitoring Logs

Tail the log file to monitor agent activity:

```bash
tail -f logs/agent.log
```

### Graceful Shutdown

The agent handles `SIGINT` (Ctrl+C) and `SIGTERM` gracefully, completing in-flight operations before shutdown.

### Config File Management

Keep separate config files for different environments:

```bash
config.toml           # Production mainnet
testnet-config.toml   # Testnet for testing
dev-config.toml       # Development with verbose logging
```

### Checking Before Trading

Always run `status` before starting the agent to verify account state:

```bash
uv run python -m hyperliquid_agent.cli status
uv run python -m hyperliquid_agent.cli start --governed
```
