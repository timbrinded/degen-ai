# Hyperliquid Trading Agent

Autonomous trading agent for the Hyperliquid platform using LLM-based decision making.

## Overview

This agent runs continuously in an unsupervised loop, monitoring your Hyperliquid positions, consulting an LLM (Large Language Model) for trading decisions, and executing trades in both spot and perpetual markets. The goal is to maximize portfolio value through AI-powered strategic trading.

The agent operates in a simple three-step cycle:

1. **Monitor**: Retrieve current positions, balances, and market data from Hyperliquid
2. **Decide**: Query an LLM with formatted market data and available trading strategies
3. **Execute**: Submit approved trades to Hyperliquid's spot and perps markets

## Features

- **Autonomous 24/7 Operation**: Runs continuously without manual intervention
- **LLM-Powered Decisions**: Supports OpenAI (GPT-4, etc.) and Anthropic (Claude) models
- **Dual Market Support**: Seamlessly trade both spot and perpetual futures markets with automatic market type detection
- **Strategy-Based Trading**: Define trading strategies in markdown files with metadata
- **Configurable Prompts**: Customize LLM behavior through prompt templates
- **Robust Error Handling**: Exponential backoff retry logic for transient failures
- **Structured Logging**: JSON-formatted logs to both file and console
- **Modular Architecture**: Easy to extend with new strategies or components

## Project Structure

```
hyperliquid-trading-agent/
├── src/
│   └── hyperliquid_agent/
│       ├── __init__.py
│       ├── cli.py          # CLI entry point
│       ├── agent.py        # Main orchestration loop
│       ├── monitor.py      # Position monitoring
│       ├── decision.py     # LLM decision engine
│       ├── executor.py     # Trade execution
│       ├── portfolio.py    # Portfolio state & rebalancing (NEW!)
│       └── config.py       # Configuration management
├── prompts/
│   └── default.txt         # Default LLM prompt template
├── strategies/             # Trading strategy definitions
├── docs/
│   ├── CONFIGURATION.md    # Detailed configuration guide
│   ├── PORTFOLIO_MANAGEMENT.md  # Portfolio rebalancing docs (NEW!)
│   └── ARCHITECTURE_DIAGRAM.md  # System architecture (NEW!)
├── examples/
│   └── portfolio_rebalancing_example.py  # Demo script (NEW!)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── logs/                   # Log files directory
├── config.toml.example     # Example configuration
└── pyproject.toml
```

## Installation

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) package manager

### Install uv

If you don't have uv installed:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

### Install the Agent

1. Clone the repository:

```bash
git clone <repository-url>
cd hyperliquid-trading-agent
```

2. Install dependencies using uv:

```bash
# Install in editable mode for development
uv pip install -e .

# Or install normally
uv pip install .
```

3. Verify installation:

```bash
hyperliquid-agent --help
```

## Configuration

### Quick Start

1. Copy the example configuration:

```bash
cp config.toml.example config.toml
```

2. Edit `config.toml` with your credentials and preferences (see detailed configuration below)

3. **IMPORTANT SECURITY WARNINGS**:
   - ⚠️ **Never commit `config.toml` to version control** - it contains sensitive API keys and private keys
   - ⚠️ **Keep your `secret_key` secure** - anyone with this key can control your account
   - ⚠️ **Start with testnet** - always test on Hyperliquid testnet before using mainnet
   - ⚠️ **Use small amounts** - start with minimal capital to test behavior
   - ⚠️ **Monitor actively** - especially during initial runs

### Configuration File Structure

The `config.toml` file has three main sections:

#### `[hyperliquid]` - Hyperliquid API Configuration

```toml
[hyperliquid]
# Your Hyperliquid wallet address
account_address = "0x1234567890abcdef1234567890abcdef12345678"

# Your wallet private key (KEEP THIS SECRET!)
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

# API endpoint - use testnet for testing
# Testnet: https://api.hyperliquid-testnet.xyz
# Mainnet: https://api.hyperliquid.xyz
base_url = "https://api.hyperliquid-testnet.xyz"
```

**Getting Hyperliquid Credentials:**

- Create a wallet on [Hyperliquid](https://app.hyperliquid.xyz/)
- For testnet, use the [testnet interface](https://app.hyperliquid-testnet.xyz/)
- Export your private key from your wallet (MetaMask, etc.)
- Your account address is your wallet's public address

#### `[llm]` - LLM Provider Configuration

```toml
[llm]
# Choose provider: "openai" or "anthropic"
provider = "openai"

# Model name
# OpenAI: "gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"
# Anthropic: "claude-3-opus-20240229", "claude-3-sonnet-20240229"
model = "gpt-4"

# Your LLM provider API key
api_key = "sk-..."

# Temperature (0.0-1.0): higher = more creative/random
temperature = 0.7

# Maximum tokens in response
max_tokens = 1000
```

**Getting LLM API Keys:**

- **OpenAI**: Sign up at [platform.openai.com](https://platform.openai.com/) and create an API key
- **Anthropic**: Sign up at [console.anthropic.com](https://console.anthropic.com/) and create an API key

#### `[agent]` - Agent Behavior Configuration

```toml
[agent]
# Seconds between trading loop iterations
tick_interval_seconds = 60

# Maximum retries for failed API calls
max_retries = 5

# Exponential backoff base (wait = base^attempt seconds)
retry_backoff_base = 2.0

# Logging level: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
log_level = "INFO"

# Path to prompt template file
prompt_template_path = "prompts/default.txt"
```

### Testnet vs Mainnet Configuration

**Testnet Configuration (Recommended for Testing):**

```toml
[hyperliquid]
base_url = "https://api.hyperliquid-testnet.xyz"
# Use testnet wallet and testnet funds
```

**Mainnet Configuration (Production):**

```toml
[hyperliquid]
base_url = "https://api.hyperliquid.xyz"
# Use real wallet with real funds - BE CAREFUL!
```

### Customizing Prompt Templates

The agent uses prompt templates to format data for the LLM. You can customize the default template or create new ones:

1. Copy the default template:

```bash
cp prompts/default.txt prompts/my-strategy.txt
```

2. Edit your template to change how the LLM receives information

3. Update your config to use the new template:

```toml
[agent]
prompt_template_path = "prompts/my-strategy.txt"
```

The template uses Python string formatting with these variables:

- `{portfolio_value}` - Total portfolio value
- `{available_balance}` - Available cash balance
- `{positions}` - Formatted list of current positions
- `{timestamp}` - Current timestamp
- `{strategies}` - Available trading strategies from `strategies/` directory

### Detailed Configuration Reference

For comprehensive documentation of all configuration options, examples, and best practices, see:

**[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**

This guide includes:

- Detailed explanation of every configuration field
- Multiple configuration examples (testnet, mainnet, conservative, aggressive)
- Prompt template customization guide
- Environment variable configuration
- Security best practices
- Troubleshooting tips

## Governance System

The agent includes an optional **Strategy Governance System** that prevents "strategy thrash" by introducing multi-timescale decision-making, policy persistence, and change governance. This transforms the agent from a tick-level oracle into a disciplined planner that commits to strategies and only changes them when conditions truly warrant it.

### Why Governance?

Without governance, the LLM can flip strategies every tick based on minor market fluctuations, leading to:
- Excessive transaction costs from constant rebalancing
- Whipsaw losses from entering/exiting positions repeatedly
- Inability to let strategies play out over their intended time horizon
- Death by a thousand cuts from fees and slippage

The governance system solves this by enforcing **plan persistence**, **dwell times**, and **change thresholds**.

### Multi-Timescale Architecture

The governance system separates concerns across three time-scales:

**Fast Loop (Execution)** - Runs every 5-30 seconds
- Executes the active Strategy Plan Card deterministically
- No LLM consultation, no strategy selection
- Manages orders, enforces per-trade risk checks
- Monitors tripwires for safety overrides

**Medium Loop (Tactical Planning)** - Runs every 15 minutes to 2 hours
- Produces and maintains Strategy Plan Cards
- Consults LLM only when plan review is permitted
- Evaluates plan change proposals against cost thresholds
- Implements gradual rebalancing for large position changes

**Slow Loop (Macro/Regime)** - Runs daily/weekly or on event triggers
- Detects market regime changes with hysteresis
- Updates macro event calendar
- Can override dwell times when regime shifts are confirmed
- Forces plan re-evaluation for structural market changes

### Strategy Plan Cards

A Strategy Plan Card is a first-class commitment that includes:

- **Identity**: Strategy name, version, plan ID, creation timestamp
- **Intent**: Objective, target holding period, time horizon, key thesis
- **Targets**: Portfolio allocations, leverage bands
- **Risk Budget**: Position limits, max leverage, drawdown limits
- **Exit Rules**: Profit targets, stop conditions, invalidation triggers
- **Change Cost**: Estimated fees, slippage, funding impact, opportunity cost
- **Dwell Time**: Minimum commitment duration before changes are permitted

### Key Governance Features

**Dwell Time Enforcement**
- Plans must remain active for their minimum dwell time (e.g., 2 hours)
- Prevents premature abandonment of strategies
- Can be overridden by regime changes or tripwires

**Change Cost Analysis**
- Calculates total cost of switching strategies (fees + slippage + funding + opportunity cost)
- Requires expected advantage to exceed change cost by a configurable threshold (e.g., 50 bps)
- Rejects unprofitable strategy switches

**Regime Detection with Hysteresis**
- Classifies markets into regimes: trending, range-bound, carry-friendly, event-risk
- Requires sustained confirmation over multiple cycles before regime changes
- Different thresholds for entering vs exiting regimes prevent ping-ponging

**Independent Safety Tripwires**
- Monitor account safety (margin, liquidation proximity, daily loss limits)
- Check plan invalidation triggers (strategy-specific conditions)
- Monitor operational health (API failures, stale data)
- Override LLM decisions when safety is at risk

**Gradual Rebalancing**
- Large strategy changes are executed over multiple cycles
- Reduces market impact and slippage
- Tracks rebalance progress and prevents new changes until complete

**Event Lock Windows**
- Freezes plan changes before/after scheduled macro events (FOMC, CPI, etc.)
- Prevents strategy switches during high-volatility periods
- Maintains positions through announcements unless tripwires fire

### Running with Governance

**Enable governed mode:**

```bash
hyperliquid-agent --governed
```

**Run with custom config:**

```bash
hyperliquid-agent --governed --config config.toml
```

**View governance status:**

```bash
# Show active plan
hyperliquid-agent status plan

# Show current regime
hyperliquid-agent status regime

# Show tripwire status
hyperliquid-agent status tripwires

# Show plan performance
hyperliquid-agent status metrics
```

### Governance Configuration

The governance system is configured in the `[governance]` section of `config.toml`:

```toml
[governance]
fast_loop_interval_seconds = 10
medium_loop_interval_minutes = 30
slow_loop_interval_hours = 24

[governance.governor]
minimum_advantage_over_cost_bps = 50.0
cooldown_after_change_minutes = 60
partial_rotation_pct_per_cycle = 25.0

[governance.regime_detector]
confirmation_cycles_required = 3
hysteresis_enter_threshold = 0.7
hysteresis_exit_threshold = 0.4

[governance.tripwire]
daily_loss_limit_pct = 5.0
min_margin_ratio = 0.15
```

See **[docs/GOVERNANCE_CONFIG.md](docs/GOVERNANCE_CONFIG.md)** for detailed configuration guidance.

### Strategy Metadata for Governance

Strategies now include governance-specific metadata in their front matter:

```yaml
---
title: "Funding Harvest Lite"
intended_horizon: "hours"
minimum_dwell_minutes: 120
compatible_regimes: ["carry-friendly", "range-bound"]
avoid_regimes: ["event-risk"]
invalidation_triggers:
  - "Funding rate flips negative for 3 consecutive windows"
  - "Delta drift exceeds 0.08 despite rehedging"
max_position_pct: 40.0
max_leverage: 3.0
expected_switching_cost_bps: 15.0
---
```

See **[docs/STRATEGY_GOVERNANCE_METADATA.md](docs/STRATEGY_GOVERNANCE_METADATA.md)** for complete metadata documentation.

### When to Use Governance

**Use governed mode when:**
- You want to reduce transaction costs from strategy thrashing
- You're running strategies with specific time horizons (hours to days)
- You want the agent to commit to plans and see them through
- You need safety tripwires independent of LLM decisions
- You're trading with real capital and want disciplined behavior

**Use standard mode when:**
- You want maximum LLM flexibility every tick
- You're testing new strategies and want rapid iteration
- You're running very short-term strategies (seconds to minutes)
- You prefer manual oversight over automated governance

### Governance vs Standard Mode Comparison

| Aspect | Standard Mode | Governed Mode |
|--------|--------------|---------------|
| LLM Queries | Every tick | Only when review permitted |
| Strategy Changes | Unrestricted | Dwell time + cost threshold |
| Execution | LLM decides each tick | Follows active plan |
| Safety | Manual monitoring | Automated tripwires |
| Transaction Costs | Higher (frequent changes) | Lower (committed plans) |
| Latency Tolerance | Requires fast LLM | Tolerates slow LLM |
| Best For | Testing, short-term | Production, medium-term |

## Usage

### Running the Agent

**Basic usage with default config:**

```bash
hyperliquid-agent
```

This looks for `config.toml` in the current directory.

**Using a custom config file:**

```bash
hyperliquid-agent --config path/to/my-config.toml
```

**View help and options:**

```bash
hyperliquid-agent --help
```

### CLI Commands

The agent provides a simple CLI interface:

```
Usage: hyperliquid-agent [OPTIONS]

  Start the Hyperliquid trading agent

Options:
  -c, --config PATH  Path to configuration file [default: config.toml]
  --help            Show this message and exit
```

### What Happens When Running

When you start the agent, it will:

1. Load configuration from `config.toml`
2. Initialize connections to Hyperliquid API and LLM provider
3. Log startup information including configuration parameters
4. Enter the main trading loop:
   - **Monitor**: Fetch current positions and account state
   - **Decide**: Query LLM with market data and strategies
   - **Execute**: Submit approved trades to Hyperliquid
   - **Wait**: Sleep for `tick_interval_seconds` before next iteration

### Monitoring the Agent

**Console Output:**
The agent logs to console in real-time. You'll see:

- Tick numbers and timestamps
- Portfolio value and changes
- LLM decisions and reasoning
- Trade executions and results
- Any errors or warnings

**Log Files:**
Detailed logs are written to `logs/agent.log` in JSON format for analysis.

**Example Console Output:**

```
2025-10-22 10:30:00 - INFO - Starting trading agent
2025-10-22 10:30:00 - INFO - Starting tick 1
2025-10-22 10:30:01 - INFO - Account state retrieved: portfolio_value=$10000.00, positions=2
2025-10-22 10:30:03 - INFO - Decision received: 1 actions, strategy=funding-harvest-lite
2025-10-22 10:30:04 - INFO - Trade executed: buy BTC perp, success=True
```

### Stopping the Agent

Press `Ctrl+C` to gracefully stop the agent. It will complete the current tick and exit.

## Development

### Requirements

- Python 3.11 or later
- uv package manager
- Git

### Setup Development Environment

1. Clone and enter the repository:

```bash
git clone <repository-url>
cd hyperliquid-trading-agent
```

2. Install with dev dependencies:

```bash
uv pip install -e ".[dev]"
```

3. Set up pre-commit hooks (optional):

```bash
# Format and lint before committing
git config core.hooksPath .githooks
```

### Code Quality Tools

**Format code with Ruff:**

```bash
uv run ruff format src/ tests/
```

**Lint code with Ruff:**

```bash
uv run ruff check src/ tests/

# Auto-fix issues
uv run ruff check --fix src/ tests/
```

**Type check with Pyrefly:**

```bash
uv run pyrefly check src/
```

**Run all quality checks:**

```bash
uv run ruff format src/ tests/ && \
uv run ruff check src/ tests/ && \
uv run pyrefly check src/
```

### Testing

**Run all tests:**

```bash
uv run pytest
```

**Run specific test categories:**

```bash
# Unit tests only
uv run pytest tests/unit/

# Integration tests only
uv run pytest tests/integration/
```

**Run with coverage:**

```bash
uv run pytest --cov=hyperliquid_agent --cov-report=html
```

### Project Architecture

The codebase follows a modular architecture:

- **`cli.py`**: Command-line interface using Typer
- **`agent.py`**: Main orchestration loop and tick execution
- **`monitor.py`**: Position and account state monitoring via Hyperliquid API
- **`decision.py`**: LLM integration and decision making
- **`executor.py`**: Trade execution via Hyperliquid API
- **`config.py`**: Configuration loading and validation

### Adding New Features

**Adding a new LLM provider:**

1. Update `LLMConfig` in `config.py` to support new provider
2. Add initialization logic in `DecisionEngine._init_llm_client()`
3. Implement query logic in `DecisionEngine._query_llm()`

**Adding new market types:**

1. Update `TradeAction.market_type` type hints
2. Add execution logic in `TradeExecutor._submit_order()`
3. Update prompt template to include new market type

**Adding risk management:**

1. Create new `risk.py` module
2. Add validation in `TradeExecutor.execute_action()`
3. Integrate checks before order submission

### Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and add tests
4. Run quality checks: `ruff format`, `ruff check`, `pyrefly check`
5. Commit with clear messages
6. Push and create a pull request

## Portfolio Management

The agent now supports **target allocation-based portfolio management**, allowing the LLM to specify desired portfolio allocations rather than individual trades. The system automatically generates optimal rebalancing plans that respect capital constraints and execution order.

### Two Decision Modes

**Mode 1: Target Allocation (Recommended)**
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

The system automatically:
- Calculates allocation deltas
- Orders trades (close overweight positions first)
- Respects capital constraints
- Filters dust trades

**Mode 2: Direct Actions (Legacy)**
```json
{
  "selected_strategy": "compression-pop",
  "actions": [
    {"action_type": "buy", "coin": "BTC", "size": 0.5}
  ]
}
```

### Documentation

- **[Portfolio Management Guide](docs/PORTFOLIO_MANAGEMENT.md)**: Comprehensive documentation
- **[Architecture Diagram](docs/ARCHITECTURE_DIAGRAM.md)**: Visual system flow
- **[Example Script](examples/portfolio_rebalancing_example.py)**: Runnable demo

### Quick Example

```bash
# Run the portfolio rebalancing demo
cd hyperliquid-trading-agent
uv run python examples/portfolio_rebalancing_example.py
```

## Dual Market Support: Spot and Perpetual Trading

The agent supports trading on both **spot markets** (e.g., ETH/USDC) and **perpetual futures markets** (e.g., ETH) simultaneously. The system automatically handles market type detection, asset identifier resolution, and order routing.

### How It Works

The agent uses a **MarketRegistry** that maintains metadata for all available markets on Hyperliquid. When the LLM decides to trade an asset, the agent:

1. **Detects market availability**: Checks if the asset is available on spot, perp, or both
2. **Resolves market identifiers**: Converts coin symbols to the correct format for each market type
3. **Routes orders correctly**: Uses the appropriate SDK methods for spot vs perp orders
4. **Handles precision**: Applies correct size and price rounding for each market

### Market Name Formats

Different market types use different identifier formats:

**Perpetual Markets:**
- Format: `"ETH"`, `"BTC"`, `"SOL"`
- Simple coin symbol without quote currency
- Used for perpetual futures contracts

**Spot Markets:**
- Format: `"ETH/USDC"`, `"BTC/USDC"`, `"PURR/USDC"`
- Includes both base and quote currency
- Alternative format: `"@123"` (token index) for some markets

### Trading Both Market Types

The LLM can specify which market type to use in its trading decisions:

**Example LLM Response (Perp Market):**
```json
{
  "selected_strategy": "funding-harvest-lite",
  "actions": [
    {
      "action_type": "buy",
      "coin": "ETH",
      "market_type": "perp",
      "size": 0.5,
      "price": null,
      "reasoning": "Funding rate is positive, opening delta-neutral position"
    }
  ]
}
```

**Example LLM Response (Spot Market):**
```json
{
  "selected_strategy": "spot-accumulation",
  "actions": [
    {
      "action_type": "buy",
      "coin": "ETH",
      "market_type": "spot",
      "size": 0.5,
      "price": null,
      "reasoning": "Accumulating spot ETH for long-term hold"
    }
  ]
}
```

### Configuration for Dual Markets

No special configuration is required. The agent automatically:
- Loads spot market metadata on initialization
- Loads perpetual market metadata on initialization
- Maintains a unified registry of all available markets

The Hyperliquid SDK Exchange client is initialized with spot metadata to support both market types:

```python
# Automatic initialization in TradeExecutor
spot_meta = info.spot_meta()
exchange = Exchange(
    account_address=config.account_address,
    wallet=account,
    base_url=config.base_url,
    spot_meta=spot_meta,  # Required for spot trading
)
```

### Strategy Configuration for Market Types

Strategies can specify which market types they support in their front matter:

**Perp-only strategy:**
```yaml
---
id: funding-harvest
title: Funding Rate Arbitrage
markets: [perps]
---
```

**Spot-only strategy:**
```yaml
---
id: spot-accumulation
title: Spot Accumulation
markets: [spot]
---
```

**Multi-market strategy:**
```yaml
---
id: cross-market-arb
title: Cross-Market Arbitrage
markets: [spot, perps]
---
```

### Market Availability Detection

The agent automatically detects which markets are available for each asset:

```python
# Example: Check ETH availability
eth_info = market_registry.get_asset_info("ETH")

if eth_info.has_spot:
    spot_name = market_registry.get_market_name("ETH", "spot")
    # Returns: "ETH/USDC" or "@123"

if eth_info.has_perp:
    perp_name = market_registry.get_market_name("ETH", "perp")
    # Returns: "ETH"
```

### Size and Price Precision

Each market has specific precision requirements:

**Perpetual Markets:**
- Size decimals: Typically 3-5 decimals (e.g., 0.001 ETH)
- Price decimals: Typically 1-2 decimals (e.g., $2500.50)

**Spot Markets:**
- Size decimals: Varies by market (check metadata)
- Price decimals: Varies by market (check metadata)

The agent automatically rounds sizes and prices to the correct precision:

```python
# Automatic rounding in TradeExecutor
sz_decimals = market_registry.get_sz_decimals(coin, market_type)
rounded_size = round(size, sz_decimals)
```

### Testing Dual Market Support

**Test scripts are provided to verify both market types:**

```bash
# Test spot order execution
python test_spot_order.py

# Test perp order execution
python test_perp_order.py

# Test end-to-end with both markets
python test_e2e_dual_markets.py
```

### Monitoring Both Market Types

The agent logs market type information for all trades:

```
2025-10-22 10:30:04 - INFO - Executing buy for ETH on perp market
2025-10-22 10:30:05 - INFO - Order submitted: market=ETH, type=perp, size=0.5
2025-10-22 10:31:04 - INFO - Executing buy for ETH on spot market
2025-10-22 10:31:05 - INFO - Order submitted: market=ETH/USDC, type=spot, size=0.5
```

## Trading Strategies

The agent supports defining trading strategies as markdown files in the `strategies/` directory. Each strategy file includes:

- **Front matter metadata**: Strategy characteristics (risk profile, markets, leverage, etc.)
- **Strategy documentation**: Entry/exit signals, sizing rules, execution guidelines

The LLM receives all active strategies and can choose which to follow based on current market conditions.

### Example Strategies Included

- `01-funding-harvest-lite.md`: Delta-neutral funding rate arbitrage (perps)
- `02-funding-flip-fade.md`: Mean-reversion on funding rate extremes (perps)

### Creating Custom Strategies

1. Create a new markdown file in `strategies/`:

```bash
touch strategies/03-my-strategy.md
```

2. Add front matter metadata:

```yaml
---
id: my-strategy
title: My Custom Strategy
markets: [spot, perps]  # Specify which market types
risk_profile: moderate
status: active
---
```

3. Document your strategy logic below the front matter

4. The agent will automatically load and present it to the LLM

## Safety and Risk Management

### Critical Safety Guidelines

⚠️ **This is experimental software. Use at your own risk.**

- **Start with testnet**: Always test thoroughly on Hyperliquid testnet before mainnet
- **Use small amounts**: Start with minimal capital you can afford to lose
- **Monitor actively**: Watch the agent closely, especially during initial runs
- **Set position limits**: Configure reasonable position sizes in your strategies
- **Review LLM decisions**: Check the logs to understand what the LLM is deciding
- **Have kill switch ready**: Know how to stop the agent quickly (Ctrl+C)

### Security Best Practices

- **Never commit secrets**: Keep `config.toml` out of version control (it's in `.gitignore`)
- **Secure your keys**: Store API keys and private keys securely
- **Use environment variables**: Consider using env vars for sensitive data instead of config files
- **Limit API permissions**: Use API keys with minimal required permissions
- **Regular audits**: Review logs and trading activity regularly
- **Backup configuration**: Keep secure backups of your config (encrypted)

### Risk Considerations

- **LLM unpredictability**: LLMs can make unexpected decisions
- **Market volatility**: Crypto markets are highly volatile
- **API failures**: Network issues can cause missed opportunities or errors
- **Execution risk**: Orders may not fill at expected prices
- **Funding costs**: Perpetual positions incur funding rate costs
- **Liquidation risk**: Leveraged positions can be liquidated

### Recommended Testing Approach

1. **Testnet testing**: Run for several days on testnet
2. **Paper trading**: Log decisions without executing (modify executor)
3. **Small capital**: Start with $100-500 on mainnet
4. **Single strategy**: Test one strategy at a time
5. **Gradual scaling**: Increase capital only after proven performance

## Troubleshooting

### Common Issues

**"Module not found" errors:**

```bash
# Reinstall the package
uv pip install -e .
```

**"Invalid API key" errors:**

- Verify your LLM API key in `config.toml`
- Check that you're using the correct provider (openai vs anthropic)
- Ensure your API key has sufficient credits/quota

**"Connection refused" to Hyperliquid:**

- Check your internet connection
- Verify the `base_url` in config (testnet vs mainnet)
- Check Hyperliquid API status

**"Insufficient balance" errors:**

- Ensure you have funds in your Hyperliquid account
- For testnet, request testnet funds from Hyperliquid
- Check that your account address is correct

**Agent not making trades:**

- Check logs for LLM decision reasoning
- Verify strategies are marked as `status: active` in front matter
- Ensure LLM is returning valid JSON responses
- Check that positions meet strategy criteria

**High API costs:**

- Increase `tick_interval_seconds` to reduce LLM queries
- Use a cheaper model (e.g., gpt-3.5-turbo instead of gpt-4)
- Reduce `max_tokens` in LLM config

### Dual Market Troubleshooting

**"Unknown asset" or "Market not found" errors:**

- Verify the asset is available on Hyperliquid (check testnet vs mainnet)
- Run `python test_market_metadata.py` to see available markets
- Check that MarketRegistry is properly hydrated on startup
- Look for "MarketRegistry hydrated" message in logs

**"Failed to fetch spot metadata" errors:**

- Verify Hyperliquid API is accessible
- Check that `base_url` in config is correct
- Ensure spot markets are available on your network (testnet/mainnet)
- Review logs for API response details

**Orders rejected with "Invalid market name" errors:**

- Check the market name format in logs
- Spot markets should be "SYMBOL/USDC" or "@index"
- Perp markets should be just "SYMBOL"
- Verify the market exists: `python test_market_metadata.py`

**Wrong market type being used:**

- Check LLM response in logs for `market_type` field
- Verify strategy metadata specifies correct `markets: [spot, perps]`
- Ensure LLM is including `market_type` in trade actions
- Review prompt template to ensure market type is requested

**Size precision errors ("Invalid size decimals"):**

- Check `sz_decimals` for the specific market in logs
- Verify MarketRegistry has correct metadata
- Run `python test_market_metadata.py` to see precision requirements
- Ensure size rounding is working: look for "Rounded size" in logs

**Spot orders failing but perp orders working:**

- Verify Exchange client was initialized with `spot_meta`
- Check for "Exchange initialized with spot metadata" in logs
- Ensure spot markets are loaded: look for "Loaded X spot markets"
- Test with `python test_spot_order.py`

**Perp orders failing but spot orders working:**

- Verify perpetual markets are loaded in MarketRegistry
- Check for "Loaded X perp markets" in logs
- Ensure market name doesn't include "/" for perps
- Test with `python test_perp_order.py`

**Market availability confusion (asset on both markets):**

- Use `python find_dual_market_assets.py` to see which assets support both
- Check logs for market resolution: "Resolved ETH/spot -> ETH/USDC"
- Verify LLM is specifying correct `market_type` in decisions
- Review strategy to ensure it's compatible with both market types

**Debugging market resolution:**

Enable debug logging to see detailed market resolution:

```toml
[agent]
log_level = "DEBUG"
```

Then check logs for:
- "MarketRegistry: Looking up market for SYMBOL/TYPE"
- "Resolved market name: RESULT"
- "Market metadata: sz_decimals=X, px_decimals=Y"

**Testing market functionality:**

Run the diagnostic scripts to verify setup:

```bash
# Check what markets are available
python test_market_metadata.py

# Find assets available on both spot and perp
python find_dual_market_assets.py

# Test spot order execution
python test_spot_order.py

# Test perp order execution
python test_perp_order.py

# Test end-to-end with both markets
python test_e2e_dual_markets.py
```

### Getting Help

- Check logs in `logs/agent.log` for detailed error information
- Review the design document in `.kiro/specs/spot-perp-trading-fix/design.md`
- Run diagnostic scripts to verify market setup
- Open an issue on GitHub with logs and configuration (redact sensitive data)

## Disclaimer

This software is provided "as is" without warranty of any kind. Trading cryptocurrencies involves substantial risk of loss. The authors and contributors are not responsible for any financial losses incurred through the use of this software.

**Use at your own risk. Only trade with capital you can afford to lose.**

## License

MIT

## Acknowledgments

- Built with [Hyperliquid Python SDK](https://github.com/hyperliquid-dex/hyperliquid-python-sdk)
- Uses [OpenAI](https://openai.com/) and [Anthropic](https://anthropic.com/) LLM APIs
- Developed using [uv](https://docs.astral.sh/uv/) package manager
