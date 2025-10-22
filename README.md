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
- **Multi-Market Support**: Trade both spot and perpetual futures markets
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

## Trading Strategies

The agent supports defining trading strategies as markdown files in the `strategies/` directory. Each strategy file includes:

- **Front matter metadata**: Strategy characteristics (risk profile, markets, leverage, etc.)
- **Strategy documentation**: Entry/exit signals, sizing rules, execution guidelines

The LLM receives all active strategies and can choose which to follow based on current market conditions.

### Example Strategies Included

- `01-funding-harvest-lite.md`: Delta-neutral funding rate arbitrage
- `02-funding-flip-fade.md`: Mean-reversion on funding rate extremes

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
markets: [perps]
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

### Getting Help

- Check logs in `logs/agent.log` for detailed error information
- Review the design document in `.kiro/specs/hyperliquid-trading-agent/design.md`
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
