# Configuration Guide

This document provides detailed information about all configuration options for the Hyperliquid Trading Agent.

## Configuration File Format

The agent uses TOML format for configuration. The default configuration file is `config.toml` in the project root.

## Configuration Sections

### `[hyperliquid]` - Hyperliquid API Settings

Controls how the agent connects to and authenticates with the Hyperliquid platform.

#### `account_address`
- **Type**: String (Ethereum address)
- **Required**: Yes
- **Description**: Your Hyperliquid wallet address (public key)
- **Format**: Must be a valid Ethereum address starting with `0x` followed by 40 hexadecimal characters
- **Example**: `"0x1234567890abcdef1234567890abcdef12345678"`
- **Security**: This is public information, but keep it private to avoid targeted attacks

#### `secret_key`
- **Type**: String (Ethereum private key)
- **Required**: Yes
- **Description**: Your wallet's private key used to sign transactions
- **Format**: Must be a valid Ethereum private key starting with `0x` followed by 64 hexadecimal characters
- **Example**: `"0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"`
- **Security**: ⚠️ **CRITICAL** - Never share this key. Anyone with this key controls your account.

#### `base_url`
- **Type**: String (URL)
- **Required**: Yes
- **Description**: Hyperliquid API endpoint URL
- **Options**:
  - Testnet: `"https://api.hyperliquid-testnet.xyz"`
  - Mainnet: `"https://api.hyperliquid.xyz"`
- **Default**: None (must be specified)
- **Recommendation**: Always start with testnet

**Example:**
```toml
[hyperliquid]
account_address = "0x1234567890abcdef1234567890abcdef12345678"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid-testnet.xyz"
```

---

### `[llm]` - LLM Provider Settings

Configures the Large Language Model used for trading decisions.

#### `provider`
- **Type**: String (enum)
- **Required**: Yes
- **Description**: Which LLM provider to use
- **Options**:
  - `"openai"` - OpenAI (GPT models)
  - `"anthropic"` - Anthropic (Claude models)
- **Default**: None (must be specified)

#### `model`
- **Type**: String
- **Required**: Yes
- **Description**: Specific model name to use
- **OpenAI Options**:
  - `"gpt-4"` - Most capable, higher cost
  - `"gpt-4-turbo"` - Fast GPT-4 variant
  - `"gpt-4o"` - Optimized GPT-4
  - `"gpt-3.5-turbo"` - Faster, cheaper, less capable
- **Anthropic Options**:
  - `"claude-3-opus-20240229"` - Most capable Claude model
  - `"claude-3-sonnet-20240229"` - Balanced performance
  - `"claude-3-haiku-20240307"` - Fastest, cheapest
- **Recommendation**: Start with `gpt-4` or `claude-3-sonnet-20240229`

#### `api_key`
- **Type**: String
- **Required**: Yes
- **Description**: API key for your chosen LLM provider
- **Format**: Provider-specific format
  - OpenAI: Starts with `sk-`
  - Anthropic: Starts with `sk-ant-`
- **Security**: Keep this secret. It's billed to your account.
- **How to get**:
  - OpenAI: https://platform.openai.com/api-keys
  - Anthropic: https://console.anthropic.com/settings/keys

#### `temperature`
- **Type**: Float (0.0 to 1.0)
- **Required**: No
- **Default**: `0.7`
- **Description**: Controls randomness in LLM responses
  - `0.0` - Deterministic, consistent responses
  - `0.5` - Balanced
  - `1.0` - Maximum creativity and randomness
- **Recommendation**: `0.5-0.7` for trading (balanced but not too random)

#### `max_tokens`
- **Type**: Integer
- **Required**: No
- **Default**: `1000`
- **Description**: Maximum number of tokens in LLM response
- **Range**: 100-4000 (depends on model)
- **Cost Impact**: Higher values = higher API costs
- **Recommendation**: `800-1200` is usually sufficient for trading decisions

**Example:**
```toml
[llm]
provider = "openai"
model = "gpt-4"
api_key = "sk-proj-abc123..."
temperature = 0.6
max_tokens = 1000
```

---

### `[agent]` - Agent Behavior Settings

Controls how the trading agent operates.

#### `tick_interval_seconds`
- **Type**: Integer
- **Required**: No
- **Default**: `60`
- **Description**: Seconds to wait between trading loop iterations
- **Range**: 10-3600 (10 seconds to 1 hour)
- **Considerations**:
  - Lower values = more frequent trading, higher API costs
  - Higher values = less responsive, lower costs
  - Hyperliquid API rate limits apply
- **Recommendation**: 
  - Testing: `60` (1 minute)
  - Production: `300-600` (5-10 minutes)

#### `max_retries`
- **Type**: Integer
- **Required**: No
- **Default**: `5`
- **Description**: Maximum number of retry attempts for failed API calls
- **Range**: 1-10
- **Behavior**: After max retries, the error is logged and the agent continues
- **Recommendation**: `3-5` retries

#### `retry_backoff_base`
- **Type**: Float
- **Required**: No
- **Default**: `2.0`
- **Description**: Base for exponential backoff calculation
- **Formula**: `wait_time = base^attempt` seconds
- **Example**: With base=2.0:
  - Attempt 1: wait 2^0 = 1 second
  - Attempt 2: wait 2^1 = 2 seconds
  - Attempt 3: wait 2^2 = 4 seconds
  - Attempt 4: wait 2^3 = 8 seconds
- **Range**: 1.5-3.0
- **Recommendation**: `2.0` (standard exponential backoff)

#### `log_level`
- **Type**: String (enum)
- **Required**: No
- **Default**: `"INFO"`
- **Description**: Minimum severity level for log messages
- **Options** (from most to least verbose):
  - `"DEBUG"` - All messages including debug info
  - `"INFO"` - Informational messages and above
  - `"WARNING"` - Warnings and errors only
  - `"ERROR"` - Errors only
  - `"CRITICAL"` - Critical errors only
- **Recommendation**: 
  - Development/Testing: `"DEBUG"` or `"INFO"`
  - Production: `"INFO"` or `"WARNING"`

#### `prompt_template_path`
- **Type**: String (file path)
- **Required**: No
- **Default**: `"prompts/default.txt"`
- **Description**: Path to the prompt template file
- **Format**: Relative or absolute file path
- **Template Variables**:
  - `{portfolio_value}` - Total portfolio value
  - `{available_balance}` - Available cash
  - `{positions}` - Formatted position list
  - `{timestamp}` - Current timestamp
  - `{strategies}` - Available strategies
- **Recommendation**: Start with default, customize as needed

**Example:**
```toml
[agent]
tick_interval_seconds = 300
max_retries = 5
retry_backoff_base = 2.0
log_level = "INFO"
prompt_template_path = "prompts/default.txt"
```

---

## Complete Configuration Examples

### Testnet Configuration (Recommended for Testing)

```toml
# Testnet configuration for safe testing
[hyperliquid]
account_address = "0x1234567890abcdef1234567890abcdef12345678"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid-testnet.xyz"

[llm]
provider = "openai"
model = "gpt-3.5-turbo"  # Cheaper model for testing
api_key = "sk-proj-..."
temperature = 0.7
max_tokens = 800

[agent]
tick_interval_seconds = 60  # Faster iterations for testing
max_retries = 3
retry_backoff_base = 2.0
log_level = "DEBUG"  # Verbose logging for debugging
prompt_template_path = "prompts/default.txt"
```

### Mainnet Configuration (Production)

```toml
# Mainnet configuration - USE WITH CAUTION
[hyperliquid]
account_address = "0x1234567890abcdef1234567890abcdef12345678"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid.xyz"  # MAINNET - REAL MONEY

[llm]
provider = "openai"
model = "gpt-4"  # More capable model for real trading
api_key = "sk-proj-..."
temperature = 0.6  # Slightly more conservative
max_tokens = 1000

[agent]
tick_interval_seconds = 300  # 5 minutes between trades
max_retries = 5
retry_backoff_base = 2.0
log_level = "INFO"  # Standard logging
prompt_template_path = "prompts/default.txt"
```

### Conservative Configuration (Low Frequency)

```toml
# Conservative setup with infrequent trading
[hyperliquid]
account_address = "0x1234567890abcdef1234567890abcdef12345678"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid.xyz"

[llm]
provider = "anthropic"
model = "claude-3-sonnet-20240229"
api_key = "sk-ant-..."
temperature = 0.5  # More deterministic
max_tokens = 1000

[agent]
tick_interval_seconds = 600  # 10 minutes between checks
max_retries = 5
retry_backoff_base = 2.0
log_level = "INFO"
prompt_template_path = "prompts/conservative.txt"
```

### Aggressive Configuration (High Frequency)

```toml
# Aggressive setup with frequent trading - HIGHER RISK
[hyperliquid]
account_address = "0x1234567890abcdef1234567890abcdef12345678"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid.xyz"

[llm]
provider = "openai"
model = "gpt-4-turbo"  # Fast model for quick decisions
api_key = "sk-proj-..."
temperature = 0.7
max_tokens = 800

[agent]
tick_interval_seconds = 60  # Check every minute
max_retries = 3  # Fail faster
retry_backoff_base = 1.5
log_level = "INFO"
prompt_template_path = "prompts/aggressive.txt"
```

---

## Prompt Template Customization

### Template Structure

Prompt templates are plain text files with Python string formatting placeholders.

**Default Template Location**: `prompts/default.txt`

**Available Variables**:
- `{portfolio_value}` - Current total portfolio value (float)
- `{available_balance}` - Available cash balance (float)
- `{positions}` - Formatted string of current positions
- `{timestamp}` - Current Unix timestamp (float)
- `{strategies}` - Formatted string of available strategies

### Creating Custom Templates

1. **Copy the default template**:
```bash
cp prompts/default.txt prompts/my-template.txt
```

2. **Edit the template** to change:
   - Instructions to the LLM
   - Risk management guidelines
   - Output format requirements
   - Decision-making criteria

3. **Update configuration**:
```toml
[agent]
prompt_template_path = "prompts/my-template.txt"
```

### Template Best Practices

- **Be specific**: Clear instructions lead to better decisions
- **Define output format**: Specify exact JSON structure expected
- **Include risk guidelines**: Remind the LLM about risk management
- **Reference strategies**: Tell the LLM to consider available strategies
- **Keep it concise**: Shorter prompts = lower costs and faster responses

### Example Custom Template

```text
You are a conservative trading agent for Hyperliquid.

Portfolio: ${portfolio_value} | Available: ${available_balance}
Time: ${timestamp}

Positions:
${positions}

Strategies:
${strategies}

RULES:
1. Maximum 3 positions at once
2. Never use more than 30% of available balance per trade
3. Only trade BTC and ETH
4. Prefer spot over perps
5. Close losing positions quickly

Respond with JSON:
{
  "selected_strategy": "strategy-id",
  "actions": [
    {
      "action_type": "buy|sell|hold|close",
      "coin": "BTC|ETH",
      "market_type": "spot|perp",
      "size": 0.1,
      "price": null,
      "reasoning": "explanation"
    }
  ]
}

Decision:
```

---

## Environment Variables (Alternative Configuration)

For enhanced security, you can use environment variables instead of storing secrets in `config.toml`.

### Supported Environment Variables

- `HYPERLIQUID_ACCOUNT_ADDRESS` - Overrides `hyperliquid.account_address`
- `HYPERLIQUID_SECRET_KEY` - Overrides `hyperliquid.secret_key`
- `LLM_API_KEY` - Overrides `llm.api_key`

### Usage

```bash
# Set environment variables
export HYPERLIQUID_SECRET_KEY="0xabc..."
export LLM_API_KEY="sk-proj-..."

# Run agent (will use env vars for secrets)
hyperliquid-agent
```

### Docker Configuration

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install uv && uv pip install .

# Secrets passed as environment variables
ENV HYPERLIQUID_SECRET_KEY=""
ENV LLM_API_KEY=""

CMD ["hyperliquid-agent"]
```

```bash
# Run with Docker
docker run -e HYPERLIQUID_SECRET_KEY="0xabc..." \
           -e LLM_API_KEY="sk-proj-..." \
           hyperliquid-agent
```

---

## Configuration Validation

The agent validates configuration on startup and will exit with an error if:

- Required fields are missing
- Values are invalid (e.g., invalid Ethereum address format)
- Files don't exist (e.g., prompt template not found)
- API keys are invalid format

### Common Validation Errors

**"Invalid account_address format"**
- Must be 42 characters starting with `0x`
- Must contain only hexadecimal characters

**"Invalid secret_key format"**
- Must be 66 characters starting with `0x`
- Must contain only hexadecimal characters

**"Unsupported LLM provider"**
- Must be exactly `"openai"` or `"anthropic"`

**"Prompt template not found"**
- Check that the file exists at the specified path
- Use relative path from project root

---

## Security Best Practices

### Configuration File Security

1. **Never commit `config.toml`** to version control
   - It's already in `.gitignore`
   - Double-check before pushing

2. **Use restrictive file permissions**:
```bash
chmod 600 config.toml  # Only owner can read/write
```

3. **Encrypt sensitive configs**:
```bash
# Encrypt config file
gpg -c config.toml

# Decrypt when needed
gpg config.toml.gpg
```

4. **Use environment variables** for secrets in production

5. **Rotate keys regularly**:
   - Change API keys periodically
   - Use different keys for testnet and mainnet

### API Key Management

- **Separate keys per environment**: Different keys for dev/test/prod
- **Monitor usage**: Check API provider dashboards for unusual activity
- **Set spending limits**: Configure billing alerts on API providers
- **Revoke compromised keys**: Immediately revoke if exposed

---

## Troubleshooting Configuration Issues

### Configuration Not Loading

**Problem**: Agent can't find `config.toml`

**Solution**:
```bash
# Specify full path
hyperliquid-agent --config /full/path/to/config.toml

# Or run from project directory
cd hyperliquid-trading-agent
hyperliquid-agent
```

### Invalid TOML Syntax

**Problem**: "TOML parsing error"

**Solution**:
- Check for missing quotes around strings
- Ensure proper section headers `[section]`
- Validate TOML syntax online: https://www.toml-lint.com/

### API Connection Failures

**Problem**: "Connection refused" or "Unauthorized"

**Solution**:
1. Verify `base_url` is correct (testnet vs mainnet)
2. Check API keys are valid and not expired
3. Ensure internet connection is working
4. Check Hyperliquid API status

### LLM Response Errors

**Problem**: "Failed to parse LLM response"

**Solution**:
1. Check `max_tokens` is sufficient (increase to 1200)
2. Verify prompt template has clear JSON format instructions
3. Try different `temperature` value (0.5-0.7)
4. Check LLM provider status and quotas

---

## Advanced Configuration

### Multiple Configuration Files

Run different strategies with different configs:

```bash
# Conservative strategy
hyperliquid-agent --config configs/conservative.toml

# Aggressive strategy
hyperliquid-agent --config configs/aggressive.toml
```

### Configuration Profiles

Create profile-specific configs:

```
configs/
├── testnet.toml
├── mainnet-conservative.toml
├── mainnet-aggressive.toml
└── development.toml
```

### Dynamic Configuration

For advanced users, configuration can be modified programmatically:

```python
from hyperliquid_agent.config import load_config

# Load and modify config
config = load_config("config.toml")
config.agent.tick_interval_seconds = 120
config.llm.temperature = 0.5

# Use modified config
from hyperliquid_agent.agent import TradingAgent
agent = TradingAgent(config)
agent.run()
```

---

## Configuration Reference Summary

| Section | Field | Type | Required | Default |
|---------|-------|------|----------|---------|
| `[hyperliquid]` | `account_address` | string | Yes | - |
| | `secret_key` | string | Yes | - |
| | `base_url` | string | Yes | - |
| `[llm]` | `provider` | string | Yes | - |
| | `model` | string | Yes | - |
| | `api_key` | string | Yes | - |
| | `temperature` | float | No | 0.7 |
| | `max_tokens` | int | No | 1000 |
| `[agent]` | `tick_interval_seconds` | int | No | 60 |
| | `max_retries` | int | No | 5 |
| | `retry_backoff_base` | float | No | 2.0 |
| | `log_level` | string | No | "INFO" |
| | `prompt_template_path` | string | No | "prompts/default.txt" |
