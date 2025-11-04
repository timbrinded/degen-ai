# Configuration

The agent is configured via `config.toml`. See `config.toml.example` for a complete reference.

## Core Settings

### Hyperliquid Connection
```toml
[hyperliquid]
private_key = "your_private_key"
testnet = true
vault_address = ""  # Optional: for vault trading
```

### LLM Provider
```toml
[llm]
provider = "openai"  # or "anthropic", "openrouter"
api_key = "your_api_key"
model = "gpt-4"
temperature = 0.7
max_tokens = 2000
```

### Agent Behavior
```toml
[agent]
check_interval_seconds = 300
max_position_size_usd = 1000
max_leverage = 3
prompt_file = "prompts/default.txt"
```

## Signal Configuration

### Data Providers
```toml
[signals]
cache_ttl_seconds = 60
max_concurrent_requests = 10

[signals.hyperliquid]
enabled = true

[signals.onchain]
enabled = true
rpc_url = "https://your-rpc-endpoint"

[signals.sentiment]
enabled = true
twitter_bearer_token = "your_token"

[signals.external_markets]
enabled = true
alpha_vantage_key = "your_key"
```

## Governance Settings

```toml
[governance]
enabled = true
regime_check_interval_seconds = 3600
min_strategy_allocation = 0.1
max_strategy_allocation = 0.5

[governance.tripwires]
max_drawdown_pct = 15.0
max_daily_loss_pct = 5.0
min_sharpe_ratio = 0.5
```

## Portfolio Management

```toml
[portfolio]
rebalance_interval_seconds = 86400
target_volatility = 0.15
max_correlation = 0.7
```

For more details, see the [full configuration documentation](https://github.com/yourusername/hyperliquid-trading-agent/blob/main/docs/CONFIGURATION.md).
