# Getting Started

## Prerequisites

- Python 3.11+
- `uv` package manager
- Hyperliquid API credentials
- OpenAI API key (or compatible LLM provider)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/hyperliquid-trading-agent.git
cd hyperliquid-trading-agent
```

2. Install dependencies using `uv`:
```bash
uv sync
```

3. Copy the example configuration:
```bash
cp config.toml.example config.toml
```

4. Configure your API keys and settings in `config.toml`

## Basic Configuration

Edit `config.toml` with your credentials:

```toml
[hyperliquid]
private_key = "your_private_key_here"
testnet = true  # Start with testnet

[llm]
provider = "openai"
api_key = "your_openai_key"
model = "gpt-4"

[agent]
check_interval_seconds = 300
max_position_size_usd = 1000
```

See the [Configuration Guide](/guide/configuration) for detailed options.

## Running the Agent

### Standard Mode
```bash
uv run python -m hyperliquid_agent.cli run
```

### With Governance
```bash
uv run python -m hyperliquid_agent.cli run --governed
```

### Backtesting
```bash
uv run python -m hyperliquid_agent.backtesting.cli backtest \
  --symbol BTC \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

## Next Steps

- Review [Architecture Overview](/architecture/overview)
- Explore available [Strategies](/strategies/)
- Learn about [Signal System](/architecture/signals)
- Understand [Governance](/architecture/governance)
