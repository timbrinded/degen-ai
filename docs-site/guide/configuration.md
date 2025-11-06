# Configuration Reference

The Hyperliquid Trading Agent is configured via `config.toml` in the project root. This document provides a complete reference for all configuration sections, parameters, validation rules, and examples.

## Quick Start

1. Copy the example configuration:
   ```bash
   cp config.toml.example config.toml
   ```

2. Edit `config.toml` with your credentials and preferences

3. Validate your configuration:
   ```bash
   uv run python -m hyperliquid_agent.cli status
   ```

## Configuration Sections

- [Hyperliquid Connection](#hyperliquid-connection) - Exchange API credentials and endpoints
- [LLM Provider](#llm-provider) - AI model configuration for decision-making
- [Agent Behavior](#agent-behavior) - Trading loop and execution settings
- [Risk Controls](#risk-controls) - Capital allocation and safety limits
- [Governance System](#governance-system) - Multi-timescale decision framework
- [Signal System](#signal-system) - Market data collection and caching

---

## Hyperliquid Connection

Configure connection to the Hyperliquid exchange API.

```toml
[hyperliquid]
account_address = "0x..."
secret_key = "0x..."
base_url = "https://api.hyperliquid-testnet.xyz"
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `account_address` | string | ✅ Yes | - | Your Hyperliquid wallet address (0x...) |
| `secret_key` | string | ✅ Yes | - | Private key for signing transactions (0x...) |
| `base_url` | string | ✅ Yes | - | API endpoint URL |

### Validation Rules

- `account_address`: Must be valid Ethereum address format (0x followed by 40 hex characters)
- `secret_key`: Must be valid private key format (0x followed by 64 hex characters)
- `base_url`: Must be one of:
  - Testnet: `https://api.hyperliquid-testnet.xyz`
  - Mainnet: `https://api.hyperliquid.xyz`

### Security Best Practices

::: warning SECURITY
Never commit `config.toml` with real credentials to version control. Use environment variables for production deployments.
:::

- Store `secret_key` in environment variable: `HYPERLIQUID_SECRET_KEY`
- Use testnet for development and testing
- Rotate keys regularly
- Use separate keys for different environments

---

## LLM Provider

Configure the AI model used for trading decisions.

```toml
[llm]
provider = "openai"
model = "gpt-4"
api_key = "sk-..."
temperature = 0.7
max_tokens = 10000
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `provider` | string | ✅ Yes | - | LLM provider: `"openai"` or `"anthropic"` |
| `model` | string | ✅ Yes | - | Model name (e.g., `"gpt-4"`, `"claude-3-opus-20240229"`) |
| `api_key` | string | ✅ Yes | - | API key for the LLM provider |
| `temperature` | float | No | `0.7` | Response creativity (0.0-1.0) |
| `max_tokens` | integer | No | `10000` | Maximum tokens in response |

### Validation Rules

- `provider`: Must be `"openai"` or `"anthropic"`
- `temperature`: Must be between 0.0 and 1.0
  - Lower (0.0-0.3): More deterministic, conservative decisions
  - Medium (0.4-0.7): Balanced creativity and consistency
  - Higher (0.8-1.0): More creative, exploratory decisions
- `max_tokens`: Must be positive integer, typically 1000-10000

### Supported Models

**OpenAI:**
- `gpt-4` - Most capable, higher cost
- `gpt-4-turbo` - Faster, lower cost
- `gpt-3.5-turbo` - Budget option (not recommended for trading)

**Anthropic:**
- `claude-3-opus-20240229` - Most capable
- `claude-3-sonnet-20240229` - Balanced performance/cost
- `claude-3-haiku-20240307` - Fastest, lowest cost

### Environment Variables

Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` to override config file.

---

## Agent Behavior

Configure the trading agent's execution loop and retry behavior.

```toml
[agent]
tick_interval_seconds = 60
max_retries = 5
retry_backoff_base = 2.0
log_level = "INFO"
prompt_template_path = "prompts/default.txt"
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `tick_interval_seconds` | integer | No | `60` | Time between trading loop iterations |
| `max_retries` | integer | No | `5` | Maximum retry attempts for failed API calls |
| `retry_backoff_base` | float | No | `2.0` | Exponential backoff multiplier |
| `log_level` | string | No | `"INFO"` | Logging verbosity level |
| `prompt_template_path` | string | No | `"prompts/default.txt"` | Path to LLM prompt template |

### Validation Rules

- `tick_interval_seconds`: Must be positive integer
  - Minimum recommended: 30 seconds (avoid rate limits)
  - Maximum recommended: 300 seconds (5 minutes for responsiveness)
- `max_retries`: Must be positive integer (1-10 recommended)
- `retry_backoff_base`: Must be positive float (1.5-3.0 recommended)
  - Wait time formula: `initial_delay * (backoff_base ^ attempt)`
- `log_level`: Must be one of: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`
- `prompt_template_path`: Must be valid file path relative to project root

### Environment Variables

Set `LOG_LEVEL` to override config file log level.

---

## Risk Controls

Configure capital allocation between perpetual and spot wallets.

```toml
[risk]
enable_auto_transfers = true
target_initial_margin_ratio = 1.25
min_perp_balance_usd = 1000.0
target_spot_usdc_buffer_usd = 0.0
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `enable_auto_transfers` | boolean | No | `true` | Enable automatic wallet transfers |
| `target_initial_margin_ratio` | float | No | `1.25` | Cushion above margin requirement (1.25 = 125%) |
| `min_perp_balance_usd` | float | No | `1000.0` | Minimum perpetual wallet balance |
| `target_spot_usdc_buffer_usd` | float | No | `0.0` | Idle USDC to keep in spot wallet |

### Validation Rules

- `target_initial_margin_ratio`: Must be ≥ 1.0
  - 1.0-1.2: Aggressive (higher capital efficiency, higher risk)
  - 1.2-1.5: Balanced (recommended)
  - 1.5+: Conservative (lower risk, lower capital efficiency)
- `min_perp_balance_usd`: Must be positive
  - Should cover minimum margin requirements for your positions
- `target_spot_usdc_buffer_usd`: Must be non-negative
  - 0: Maximize capital efficiency
  - 100-1000: Keep buffer for spot opportunities

---

## Governance System

Configure multi-timescale decision-making framework. See [Governance Architecture](/architecture/governance) for details.

```toml
[governance]
fast_loop_interval_seconds = 10
medium_loop_interval_minutes = 30
slow_loop_interval_hours = 24
emergency_reduction_pct = 100.0
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `fast_loop_interval_seconds` | integer | No | `10` | Execution loop frequency |
| `medium_loop_interval_minutes` | integer | No | `30` | Planning loop frequency |
| `slow_loop_interval_hours` | integer | No | `24` | Regime detection frequency |
| `emergency_reduction_pct` | float | No | `100.0` | Position reduction on tripwire (0-100) |

### Validation Rules

- `fast_loop_interval_seconds`: 5-60 seconds recommended
- `medium_loop_interval_minutes`: 15-120 minutes recommended
- `slow_loop_interval_hours`: 4-24 hours recommended
- `emergency_reduction_pct`: 0.0-100.0
  - 100.0: Full liquidation (maximum safety)
  - 50.0-75.0: Partial reduction
  - 0.0: No automatic reduction (not recommended)

### Governor Configuration

```toml
[governance.governor]
minimum_advantage_over_cost_bps = 50.0
cooldown_after_change_minutes = 60
partial_rotation_pct_per_cycle = 25.0
state_persistence_path = "state/governor.json"
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `minimum_advantage_over_cost_bps` | float | No | `50.0` | Minimum edge required for strategy switch (basis points) |
| `cooldown_after_change_minutes` | integer | No | `60` | Minimum time between plan changes |
| `partial_rotation_pct_per_cycle` | float | No | `25.0` | Portfolio rotation rate per cycle (0-100) |
| `state_persistence_path` | string | No | `"state/governor.json"` | Path to save governor state |

**Validation:**
- `minimum_advantage_over_cost_bps`: 25-100 recommended
- `cooldown_after_change_minutes`: 30-120 recommended
- `partial_rotation_pct_per_cycle`: 10-50 recommended

### Regime Detector Configuration

```toml
[governance.regime_detector]
confirmation_cycles_required = 3
hysteresis_enter_threshold = 0.7
hysteresis_exit_threshold = 0.4
event_lock_window_hours_before = 2
event_lock_window_hours_after = 1
llm_model = "gpt-4"
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `confirmation_cycles_required` | integer | No | `3` | Cycles to confirm regime change |
| `hysteresis_enter_threshold` | float | No | `0.7` | Confidence to enter new regime (0-1) |
| `hysteresis_exit_threshold` | float | No | `0.4` | Confidence to exit regime (0-1) |
| `event_lock_window_hours_before` | integer | No | `2` | Lock changes before macro events |
| `event_lock_window_hours_after` | integer | No | `1` | Lock changes after macro events |
| `llm_model` | string | No | Uses `[llm]` config | Override model for regime classification |

**Validation:**
- `confirmation_cycles_required`: 2-5 recommended
- `hysteresis_enter_threshold`: 0.5-0.8 (higher = more conservative)
- `hysteresis_exit_threshold`: Must be < `hysteresis_enter_threshold` by 0.2-0.3
- `event_lock_window_hours_before`: 1-4 hours
- `event_lock_window_hours_after`: 0.5-2 hours

### Tripwire Configuration

```toml
[governance.tripwire]
min_margin_ratio = 0.15
liquidation_proximity_threshold = 0.25
daily_loss_limit_pct = 5.0
max_data_staleness_seconds = 300
max_api_failure_count = 3
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `min_margin_ratio` | float | No | `0.15` | Minimum margin before safety trigger (0-1) |
| `liquidation_proximity_threshold` | float | No | `0.25` | Distance to liquidation trigger (0-1) |
| `daily_loss_limit_pct` | float | No | `5.0` | Maximum daily loss before cutting (0-100) |
| `max_data_staleness_seconds` | integer | No | `300` | Maximum stale data age before freeze |
| `max_api_failure_count` | integer | No | `3` | Consecutive failures before freeze |

**Validation:**
- `min_margin_ratio`: 0.10-0.30 (exchange minimum ~0.03-0.05)
- `liquidation_proximity_threshold`: 0.15-0.30
- `daily_loss_limit_pct`: 3-10% recommended
- `max_data_staleness_seconds`: 180-600 seconds
- `max_api_failure_count`: 3-10 failures

---

## Signal System

Configure market data collection from multiple providers. See [Signals Architecture](/architecture/signals) for details.

```toml
[signals]
timeout_seconds = 30.0
caching_enabled = true
db_path = "state/signal_cache.db"
```

### Global Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `timeout_seconds` | float | No | `30.0` | Global timeout for signal collection |
| `caching_enabled` | boolean | No | `true` | Enable signal caching |
| `db_path` | string | No | `"state/signal_cache.db"` | SQLite cache database path |

### Hyperliquid Provider

```toml
[signals.hyperliquid]
max_retries = 3
timeout_seconds = 10.0
backoff_factor = 2.0
initial_delay_seconds = 1.0
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `max_retries` | integer | No | `3` | Maximum retry attempts |
| `timeout_seconds` | float | No | `10.0` | Request timeout |
| `backoff_factor` | float | No | `2.0` | Exponential backoff multiplier |
| `initial_delay_seconds` | float | No | `1.0` | Initial retry delay |

### On-Chain Provider

```toml
[signals.onchain]
enabled = false
provider = "token_unlocks"
api_key = "your_key"
cache_ttl_seconds = 3600
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `enabled` | boolean | No | `false` | Enable on-chain data collection |
| `provider` | string | No | `null` | Provider: `"token_unlocks"`, `"nansen"`, `"dune"` |
| `api_key` | string | Conditional | `null` | API key (required if provider set) |
| `cache_ttl_seconds` | integer | No | `3600` | Cache time-to-live |

**Validation:**
- If `enabled=true` and `provider` is set, `api_key` is required
- Can use `ONCHAIN_API_KEY` environment variable

**Providers:**
- `token_unlocks`: Token unlock schedules ([token.unlocks.app](https://token.unlocks.app))
- `nansen`: On-chain analytics ([nansen.ai](https://nansen.ai))
- `dune`: Blockchain queries ([dune.com](https://dune.com))

### External Market Provider

```toml
[signals.external_market]
enabled = true
use_coingecko = true
coingecko_api_key = ""
use_yfinance = true
jblanked_api_key = ""
use_tradingview = false
cache_ttl_seconds = 900
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `enabled` | boolean | No | `true` | Enable external market data |
| `use_coingecko` | boolean | No | `true` | Enable CoinGecko (FREE tier available) |
| `coingecko_api_key` | string | No | `null` | CoinGecko API key (optional) |
| `use_yfinance` | boolean | No | `true` | Enable Yahoo Finance (FREE) |
| `jblanked_api_key` | string | No | `null` | JBlanked API key for Forex Factory |
| `use_tradingview` | boolean | No | `false` | Enable TradingView (requires key) |
| `cache_ttl_seconds` | integer | No | `900` | Cache TTL (15 minutes) |

**Free Providers:**
- CoinGecko: 10-50 calls/min free tier (API key optional for higher limits)
- yfinance: Unlimited free access to Yahoo Finance data

**Paid Providers:**
- JBlanked: Economic calendar data (1 request/day free)
- TradingView: Advanced charting (requires API key)

### Sentiment Provider

```toml
[signals.sentiment]
enabled = true
use_fear_greed_index = true
use_social_sentiment = false
cache_ttl_seconds = 1800
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `enabled` | boolean | No | `true` | Enable sentiment data |
| `use_fear_greed_index` | boolean | No | `true` | Enable Fear & Greed Index (FREE) |
| `use_social_sentiment` | boolean | No | `false` | Enable social sentiment (requires key) |
| `cache_ttl_seconds` | integer | No | `1800` | Cache TTL (30 minutes) |

**Free Providers:**
- Fear & Greed Index: Alternative.me API (no key required)

### Computed Signals

```toml
[signals.computed]
enabled = true
technical_lookback_hours = 168
volatility_lookback_hours = 168
correlation_lookback_days = 30
cache_ttl_seconds = 300
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `enabled` | boolean | No | `true` | Enable computed signals |
| `technical_lookback_hours` | integer | No | `168` | Technical indicator window (7 days) |
| `volatility_lookback_hours` | integer | No | `168` | Volatility calculation window |
| `correlation_lookback_days` | integer | No | `30` | Correlation calculation window |
| `cache_ttl_seconds` | integer | No | `300` | Cache TTL (5 minutes) |

### Cache Configuration

```toml
[signals.cache]
cleanup_interval_seconds = 3600
vacuum_on_startup = true
max_size_mb = 100
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cleanup_interval_seconds` | integer | No | `3600` | Automatic cleanup frequency |
| `vacuum_on_startup` | boolean | No | `true` | Optimize database on startup |
| `max_size_mb` | integer | No | `100` | Maximum cache size |

---

## Configuration Examples

### Testnet Development

```toml
[hyperliquid]
account_address = "0x..."
secret_key = "0x..."
base_url = "https://api.hyperliquid-testnet.xyz"

[llm]
provider = "openai"
model = "gpt-4-turbo"  # Faster, cheaper for testing
api_key = "sk-..."
temperature = 0.5

[agent]
tick_interval_seconds = 60
log_level = "DEBUG"  # Verbose logging for development

[governance]
fast_loop_interval_seconds = 30
medium_loop_interval_minutes = 15
slow_loop_interval_hours = 6

[signals.onchain]
enabled = false  # Disable paid providers for testing

[signals.external_market]
enabled = true
use_coingecko = true
use_yfinance = true
```

### Mainnet Production

```toml
[hyperliquid]
account_address = "0x..."
secret_key = "0x..."
base_url = "https://api.hyperliquid.xyz"

[llm]
provider = "anthropic"
model = "claude-3-opus-20240229"  # Most capable for real trading
api_key = "sk-..."
temperature = 0.7

[agent]
tick_interval_seconds = 60
log_level = "INFO"  # Production logging

[risk]
enable_auto_transfers = true
target_initial_margin_ratio = 1.3  # Conservative margin
min_perp_balance_usd = 5000.0

[governance]
fast_loop_interval_seconds = 10
medium_loop_interval_minutes = 30
slow_loop_interval_hours = 24

[governance.tripwire]
min_margin_ratio = 0.20  # Conservative safety
daily_loss_limit_pct = 3.0  # Strict loss limit

[signals.onchain]
enabled = true
provider = "token_unlocks"
api_key = "your_key"

[signals.external_market]
enabled = true
use_coingecko = true
coingecko_api_key = "your_key"  # Pro tier for higher limits
```

### Governance Disabled (Simple Mode)

```toml
[hyperliquid]
account_address = "0x..."
secret_key = "0x..."
base_url = "https://api.hyperliquid-testnet.xyz"

[llm]
provider = "openai"
model = "gpt-4"
api_key = "sk-..."

[agent]
tick_interval_seconds = 60
prompt_template_path = "prompts/default.txt"

# No [governance] section - runs in simple mode
# Agent makes decisions every tick_interval_seconds

[signals]
timeout_seconds = 30.0
caching_enabled = true

[signals.external_market]
enabled = true
use_coingecko = true
use_yfinance = true
```

---

## Environment Variables

Override config file values with environment variables:

| Variable | Overrides | Example |
|----------|-----------|---------|
| `LOG_LEVEL` | `[agent].log_level` | `export LOG_LEVEL=DEBUG` |
| `OPENAI_API_KEY` | `[llm].api_key` | `export OPENAI_API_KEY=sk-...` |
| `ANTHROPIC_API_KEY` | `[llm].api_key` | `export ANTHROPIC_API_KEY=sk-...` |
| `ONCHAIN_API_KEY` | `[signals.onchain].api_key` | `export ONCHAIN_API_KEY=...` |
| `COINGECKO_API_KEY` | `[signals.external_market].coingecko_api_key` | `export COINGECKO_API_KEY=...` |
| `JBLANKED_API_KEY` | `[signals.external_market].jblanked_api_key` | `export JBLANKED_API_KEY=...` |

---

## Security Best Practices

### API Key Management

1. **Never commit secrets to version control**
   ```bash
   # Add to .gitignore
   config.toml
   .env
   ```

2. **Use environment variables in production**
   ```bash
   export HYPERLIQUID_SECRET_KEY="0x..."
   export OPENAI_API_KEY="sk-..."
   ```

3. **Rotate keys regularly**
   - Generate new Hyperliquid keys monthly
   - Rotate LLM API keys quarterly
   - Use separate keys per environment

4. **Restrict key permissions**
   - Use read-only keys where possible
   - Limit withdrawal permissions
   - Enable IP whitelisting

### Secrets Handling

**Development:**
```bash
# Use .env file (not committed)
cp .env.example .env
# Edit .env with your keys
source .env
```

**Production (Docker):**
```bash
# Use Docker secrets
docker secret create hyperliquid_key /path/to/key
docker service create --secret hyperliquid_key ...
```

**Production (Kubernetes):**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: trading-agent-secrets
type: Opaque
data:
  hyperliquid-key: <base64-encoded>
  openai-key: <base64-encoded>
```

### Configuration Validation

Validate your configuration before running:

```bash
# Check configuration syntax
uv run python -c "from hyperliquid_agent.config import load_config; load_config()"

# Test connection
uv run python -m hyperliquid_agent.cli status

# Dry run (testnet recommended)
uv run python -m hyperliquid_agent.cli start --dry-run
```

---

## Troubleshooting

### Common Configuration Errors

**Missing required field:**
```
ValueError: Missing required field in [hyperliquid]: account_address
```
→ Add all required fields to `[hyperliquid]` section

**Invalid LLM provider:**
```
ValueError: Invalid LLM provider: openrouter. Must be 'openai' or 'anthropic'
```
→ Use `provider = "openai"` or `provider = "anthropic"`

**On-chain provider without API key:**
```
ValueError: On-chain provider 'token_unlocks' is enabled but no API key provided
```
→ Add `api_key` or set `enabled = false`

**Invalid temperature:**
```
Temperature must be between 0.0 and 1.0
```
→ Set `temperature` in range 0.0-1.0

### Configuration Debugging

Enable debug logging to see configuration loading:

```toml
[agent]
log_level = "DEBUG"
```

Check loaded configuration:
```bash
uv run python -c "
from hyperliquid_agent.config import load_config
config = load_config()
print(f'LLM: {config.llm.provider} / {config.llm.model}')
print(f'Governance: {config.governance is not None}')
print(f'Signals: {config.signals is not None}')
"
```

---

## Related Documentation

- [Getting Started](/guide/getting-started) - Initial setup guide
- [CLI Reference](/guide/cli-reference) - Command-line interface
- [Governance Architecture](/architecture/governance) - Governance system details
- [Signals Architecture](/architecture/signals) - Signal system details
- [Deployment Guide](/guide/deployment) - Production deployment
