# Troubleshooting Guide

This guide helps you diagnose and resolve common issues with the Hyperliquid Trading Agent. Issues are organized by category with specific error messages, root causes, and solutions.

## Quick Diagnostic Checklist

Before diving into specific errors, run through this checklist:

1. **Configuration Valid?**
   ```bash
   uv run python -c "from hyperliquid_agent.config import load_config; load_config()"
   ```

2. **API Connectivity?**
   ```bash
   uv run python -m hyperliquid_agent.cli status
   ```

3. **Dependencies Installed?**
   ```bash
   uv sync
   ```

4. **Logs Available?**
   ```bash
   tail -f logs/agent.log
   ```

---

## Configuration Errors

### Missing Required Configuration Field

**Error Message:**
```
ValueError: Missing required field in [hyperliquid]: account_address
```

**Cause:** Required configuration parameter is not set in `config.toml`.

**Solution:**
1. Check which section and field is missing from the error message
2. Add the required field to your `config.toml`:
   ```toml
   [hyperliquid]
   account_address = "0x..."
   secret_key = "0x..."
   base_url = "https://api.hyperliquid-testnet.xyz"
   ```
3. Verify all required fields are present:
   - `[hyperliquid]`: `account_address`, `secret_key`, `base_url`
   - `[llm]`: `provider`, `model`, `api_key`
   - `[agent]`: All fields have defaults

**Related:** [Configuration Reference](/guide/configuration)

---

### Invalid LLM Provider

**Error Message:**
```
ValueError: Invalid LLM provider: openrouter. Must be 'openai' or 'anthropic'
```

**Cause:** Unsupported LLM provider specified in configuration.

**Solution:**
Change `provider` to a supported value:
```toml
[llm]
provider = "openai"  # or "anthropic"
model = "gpt-4"
api_key = "sk-..."
```

**Supported Providers:**
- `openai`: GPT-4, GPT-4-turbo, GPT-3.5-turbo
- `anthropic`: Claude-3-opus, Claude-3-sonnet, Claude-3-haiku

---

### Configuration File Not Found

**Error Message:**
```
FileNotFoundError: Configuration file not found: config.toml
```

**Cause:** `config.toml` doesn't exist in the project root.

**Solution:**
1. Copy the example configuration:
   ```bash
   cp config.toml.example config.toml
   ```
2. Edit with your credentials
3. Or specify custom path:
   ```bash
   uv run python -m hyperliquid_agent.cli start --config /path/to/config.toml
   ```

---

### Invalid Temperature Value

**Error Message:**
```
Temperature must be between 0.0 and 1.0
```

**Cause:** LLM temperature parameter is outside valid range.

**Solution:**
Set temperature between 0.0 and 1.0:
```toml
[llm]
temperature = 0.7  # Valid: 0.0 to 1.0
```

**Guidelines:**
- 0.0-0.3: Deterministic, conservative
- 0.4-0.7: Balanced (recommended)
- 0.8-1.0: Creative, exploratory

---

### On-Chain Provider Missing API Key

**Error Message:**
```
ValueError: On-chain provider 'token_unlocks' is enabled but no API key provided
```

**Cause:** On-chain data provider is enabled without API key.

**Solution:**

**Option 1:** Add API key
```toml
[signals.onchain]
enabled = true
provider = "token_unlocks"
api_key = "your_api_key_here"
```

**Option 2:** Disable provider
```toml
[signals.onchain]
enabled = false
```

**Option 3:** Use environment variable
```bash
export ONCHAIN_API_KEY="your_api_key_here"
```

---

### Governance Configuration Missing

**Error Message:**
```
Error: [governance] section missing in config file
```

**Cause:** Trying to run in governed mode without governance configuration.

**Solution:**

**Option 1:** Add governance configuration
```toml
[governance]
fast_loop_interval_seconds = 10
medium_loop_interval_minutes = 30
slow_loop_interval_hours = 24

[governance.governor]
minimum_advantage_over_cost_bps = 50.0
cooldown_after_change_minutes = 60

[governance.regime_detector]
confirmation_cycles_required = 3

[governance.tripwire]
min_margin_ratio = 0.15
daily_loss_limit_pct = 5.0
```

**Option 2:** Run in standard mode
```bash
uv run python -m hyperliquid_agent.cli start  # Without --governed flag
```

**Related:** [Governance Architecture](/architecture/governance)

---

## API Connection Errors

### Network Connection Failed

**Error Message:**
```
ConnectionError: Failed to connect to https://api.hyperliquid.xyz
requests.exceptions.ConnectionError: HTTPSConnectionPool
```

**Cause:** Cannot reach Hyperliquid API endpoint.

**Diagnosis:**
1. Check internet connectivity:
   ```bash
   ping api.hyperliquid.xyz
   ```

2. Test API endpoint:
   ```bash
   curl https://api.hyperliquid.xyz/info
   ```

3. Check firewall/proxy settings

**Solutions:**

**Network Issue:**
- Verify internet connection
- Check DNS resolution
- Try different network

**Firewall/Proxy:**
- Whitelist `api.hyperliquid.xyz` and `api.hyperliquid-testnet.xyz`
- Configure proxy if required:
  ```bash
  export HTTPS_PROXY=http://proxy.example.com:8080
  ```

**API Endpoint:**
- Verify correct URL in config:
  - Testnet: `https://api.hyperliquid-testnet.xyz`
  - Mainnet: `https://api.hyperliquid.xyz`

---

### Authentication Failed

**Error Message:**
```
AuthenticationError: Invalid signature
Unauthorized: 401
```

**Cause:** Invalid credentials or signature mismatch.

**Diagnosis:**
1. Verify account address format (0x + 40 hex chars)
2. Verify secret key format (0x + 64 hex chars)
3. Check key matches address

**Solutions:**

**Invalid Credentials:**
```toml
[hyperliquid]
account_address = "0x1234..."  # Must be valid Ethereum address
secret_key = "0xabcd..."       # Must be valid private key
```

**Key Mismatch:**
- Ensure secret key corresponds to account address
- Generate new key pair if needed
- Test on testnet first

**Permissions:**
- Verify API key has trading permissions
- Check account is not restricted

---

### Rate Limiting

**Error Message:**
```
RateLimitError: Too many requests
429 Too Many Requests
```

**Cause:** Exceeding API rate limits.

**Diagnosis:**
Check request frequency in logs:
```bash
grep "API request" logs/agent.log | tail -20
```

**Solutions:**

**Increase Tick Interval:**
```toml
[agent]
tick_interval_seconds = 120  # Reduce frequency
```

**Adjust Retry Settings:**
```toml
[agent]
max_retries = 3              # Reduce retries
retry_backoff_base = 3.0     # Increase backoff
```

**Signal Collection:**
```toml
[signals]
timeout_seconds = 60.0       # Increase timeout

[signals.hyperliquid]
max_retries = 2              # Reduce retries
backoff_factor = 3.0         # Increase backoff
```

**Enable Caching:**
```toml
[signals]
caching_enabled = true

[signals.cache]
cleanup_interval_seconds = 3600
```

---

### Request Timeout

**Error Message:**
```
TimeoutError: Request timed out after 30.0 seconds
ReadTimeout: HTTPSConnectionPool
```

**Cause:** API request took too long to complete.

**Solutions:**

**Increase Timeout:**
```toml
[signals]
timeout_seconds = 60.0  # Increase from 30

[signals.hyperliquid]
timeout_seconds = 20.0  # Increase provider timeout
```

**Check Network Latency:**
```bash
ping -c 10 api.hyperliquid.xyz
```

**Reduce Concurrent Requests:**
- Disable unnecessary signal providers
- Increase cache TTL to reduce API calls

---

### SSL Certificate Error

**Error Message:**
```
SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

**Cause:** SSL certificate verification failed.

**Solutions:**

**Update CA Certificates:**
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install ca-certificates

# macOS
brew install ca-certificates
```

**Python Certificates:**
```bash
pip install --upgrade certifi
```

**Temporary Workaround (NOT RECOMMENDED FOR PRODUCTION):**
```python
# Only for debugging
import urllib3
urllib3.disable_warnings()
```

---

## Execution Errors

### Invalid Order Size

**Error Message:**
```
ValueError: Invalid size for buy: 0.0
Order size must be positive
```

**Cause:** Order size is zero, negative, or doesn't meet minimum requirements.

**Solutions:**

**Check Minimum Notional:**
- Hyperliquid requires minimum $5 USDC notional value
- Example: BTC at $50,000 requires minimum 0.0001 BTC

**Verify Size Calculation:**
```python
# Ensure size is positive and meets minimum
min_size = 5.0 / current_price  # $5 minimum
size = max(calculated_size, min_size)
```

**Check Decimal Precision:**
- Each asset has specific `szDecimals` requirement
- Size must be rounded to correct precision
- Agent handles this automatically via `MarketRegistry`

---

### Market Not Found

**Error Message:**
```
ValueError: Market ETH not found in registry
Symbol not found: ETH
```

**Cause:** Market registry not hydrated or symbol not available.

**Diagnosis:**
1. Check if registry is hydrated:
   ```python
   # Registry must be hydrated before use
   await registry.hydrate()
   ```

2. Verify symbol exists:
   ```bash
   uv run python -m hyperliquid_agent.cli assets-validate
   ```

**Solutions:**

**Hydrate Registry:**
```python
from hyperliquid.info import Info
from hyperliquid_agent.market_registry import MarketRegistry

info = Info(base_url, skip_ws=True)
registry = MarketRegistry(info)
await registry.hydrate()  # Must call before use
```

**Check Symbol Format:**
- Perp markets: Use base symbol (e.g., "BTC", "ETH")
- Spot markets: May require pair format (e.g., "ETH/USDC")

**Update Asset Config:**
```bash
# Validate and update asset identities
uv run python -m hyperliquid_agent.cli assets-validate
```

---

### Insufficient Balance

**Error Message:**
```
InsufficientBalanceError: Insufficient balance for order
Available: $100, Required: $500
```

**Cause:** Not enough funds in wallet for order.

**Diagnosis:**
Check account balance:
```bash
uv run python -m hyperliquid_agent.cli status
```

**Solutions:**

**Deposit Funds:**
- Transfer USDC to your Hyperliquid wallet
- Ensure funds are in correct wallet (spot vs perp)

**Enable Auto-Transfers:**
```toml
[risk]
enable_auto_transfers = true
min_perp_balance_usd = 1000.0
```

**Reduce Position Size:**
```toml
[agent]
max_position_size_usd = 100  # Reduce from 500
```

**Check Margin Requirements:**
- Perp positions require margin
- Spot positions require full notional value

---

### Order Rejected

**Error Message:**
```
OrderRejectedError: Order rejected by exchange
Reason: Price too far from mark
```

**Cause:** Order parameters don't meet exchange requirements.

**Common Reasons:**

**Price Too Far From Mark:**
- Limit price too far from current market price
- Use market orders or tighter limits

**Invalid Size:**
- Size doesn't meet `szDecimals` requirement
- Size below minimum notional ($5 USDC)

**Market Closed:**
- Some markets have trading hours
- Check market status before ordering

**Solutions:**

**Use Market Orders:**
```python
action = TradeAction(
    action_type="buy",
    coin="BTC",
    market_type="perp",
    size=0.001,
    price=None,  # Market order
)
```

**Check Market Status:**
```bash
uv run python -m hyperliquid_agent.cli status
```

---

### Position Liquidation

**Error Message:**
```
LiquidationError: Position liquidated
Margin ratio below maintenance requirement
```

**Cause:** Position was liquidated due to insufficient margin.

**Prevention:**

**Conservative Margin:**
```toml
[risk]
target_initial_margin_ratio = 1.5  # Higher cushion
```

**Tripwire Protection:**
```toml
[governance.tripwire]
min_margin_ratio = 0.20  # Trigger before liquidation
liquidation_proximity_threshold = 0.30
```

**Position Monitoring:**
- Monitor margin ratio regularly
- Set up alerts for low margin
- Use stop-loss orders

**Recovery:**
1. Deposit additional funds
2. Close other positions to free margin
3. Review risk management settings

---

## Performance Issues

### Slow Signal Collection

**Symptom:** Agent takes >30 seconds to collect signals.

**Diagnosis:**
Check signal collection times in logs:
```bash
grep "Signal collection" logs/agent.log
```

**Solutions:**

**Enable Caching:**
```toml
[signals]
caching_enabled = true

[signals.cache]
cleanup_interval_seconds = 3600
max_size_mb = 100
```

**Increase Cache TTL:**
```toml
[signals.hyperliquid]
cache_ttl_seconds = 300  # 5 minutes

[signals.external_market]
cache_ttl_seconds = 900  # 15 minutes

[signals.sentiment]
cache_ttl_seconds = 1800  # 30 minutes
```

**Disable Slow Providers:**
```toml
[signals.onchain]
enabled = false  # Disable if not needed

[signals.external_market]
use_tradingview = false  # Disable slow providers
```

**Optimize Lookback Windows:**
```toml
[signals.computed]
technical_lookback_hours = 24  # Reduce from 168
volatility_lookback_hours = 24
```

---

### High Memory Usage

**Symptom:** Agent uses excessive RAM (>1GB).

**Diagnosis:**
Monitor memory usage:
```bash
ps aux | grep python
```

**Solutions:**

**Limit Cache Size:**
```toml
[signals.cache]
max_size_mb = 50  # Reduce from 100
cleanup_interval_seconds = 1800  # More frequent cleanup
```

**Reduce Lookback Windows:**
```toml
[signals.computed]
technical_lookback_hours = 24
correlation_lookback_days = 7
```

**Vacuum Database:**
```bash
sqlite3 state/signal_cache.db "VACUUM;"
```

**Restart Periodically:**
- Set up cron job to restart agent daily
- Clears memory leaks and stale data

---

### Database Locked

**Error Message:**
```
sqlite3.OperationalError: database is locked
```

**Cause:** Multiple processes accessing SQLite cache simultaneously.

**Solutions:**

**Single Process:**
- Ensure only one agent instance is running
- Check for zombie processes:
  ```bash
  ps aux | grep hyperliquid_agent
  kill <pid>  # Kill duplicates
  ```

**Increase Timeout:**
```python
# In cache.py
connection = sqlite3.connect(db_path, timeout=30.0)
```

**Use WAL Mode:**
```bash
sqlite3 state/signal_cache.db "PRAGMA journal_mode=WAL;"
```

---

### LLM Response Timeout

**Error Message:**
```
TimeoutError: LLM request timed out after 60 seconds
```

**Cause:** LLM taking too long to generate response.

**Solutions:**

**Reduce Max Tokens:**
```toml
[llm]
max_tokens = 5000  # Reduce from 10000
```

**Increase Timeout:**
```python
# Adjust in llm_client.py
timeout = 120  # Increase from 60
```

**Use Faster Model:**
```toml
[llm]
model = "gpt-4-turbo"  # Faster than gpt-4
# or
model = "claude-3-sonnet-20240229"  # Faster than opus
```

**Simplify Prompt:**
- Reduce context in prompt template
- Remove unnecessary signal data
- Focus on essential information

---

## Log Analysis

### Log Locations

**Default Locations:**
- Application logs: `logs/agent.log`
- Backtest logs: `backtest_results/results.log`
- Governor state: `state/governor.json`
- Signal cache: `state/signal_cache.db`

**Custom Locations:**
Check `config.toml` for custom paths:
```toml
[agent]
log_level = "INFO"

[governance.governor]
state_persistence_path = "state/governor.json"

[signals]
db_path = "state/signal_cache.db"
```

---

### Log Format

**Standard Format:**
```
2024-01-15 10:30:45,123 - INFO - hyperliquid_agent.agent - Starting trading loop
2024-01-15 10:30:46,234 - DEBUG - hyperliquid_agent.signals - Collecting signals
2024-01-15 10:30:47,345 - WARNING - hyperliquid_agent.executor - Order size adjusted
2024-01-15 10:30:48,456 - ERROR - hyperliquid_agent.monitor - API request failed
```

**Fields:**
- Timestamp: `2024-01-15 10:30:45,123`
- Level: `INFO`, `DEBUG`, `WARNING`, `ERROR`, `CRITICAL`
- Module: `hyperliquid_agent.agent`
- Message: Descriptive text

---

### Useful Log Queries

**Find Errors:**
```bash
grep "ERROR" logs/agent.log
```

**Find Warnings:**
```bash
grep "WARNING" logs/agent.log
```

**Track Order Execution:**
```bash
grep "Order executed" logs/agent.log
```

**Monitor API Calls:**
```bash
grep "API request" logs/agent.log | tail -20
```

**Check Signal Collection:**
```bash
grep "Signal collection" logs/agent.log
```

**View Recent Activity:**
```bash
tail -f logs/agent.log
```

**Filter by Time Range:**
```bash
grep "2024-01-15 10:" logs/agent.log
```

**Count Error Types:**
```bash
grep "ERROR" logs/agent.log | cut -d'-' -f4 | sort | uniq -c
```

---

### Enable Debug Logging

**Temporary (CLI):**
```bash
export LOG_LEVEL=DEBUG
uv run python -m hyperliquid_agent.cli start
```

**Permanent (Config):**
```toml
[agent]
log_level = "DEBUG"
```

**Module-Specific:**
```python
import logging
logging.getLogger('hyperliquid_agent.signals').setLevel(logging.DEBUG)
```

---

## Configuration Validation

### Validate Configuration File

**Syntax Check:**
```bash
uv run python -c "from hyperliquid_agent.config import load_config; load_config()"
```

**Expected Output:**
```
# No output = success
```

**Error Output:**
```
ValueError: Missing required field in [hyperliquid]: account_address
```

---

### Test API Connection

**Status Command:**
```bash
uv run python -m hyperliquid_agent.cli status
```

**Expected Output:**
```
Fetching account state...

============================================================
Account Status
============================================================
Portfolio Value:    $10,000.00
Available Balance:  $9,500.00
Number of Positions: 2
...
```

---

### Validate Asset Configuration

**Check Asset Identities:**
```bash
uv run python -m hyperliquid_agent.cli assets-validate
```

**Expected Output:**
```
Loaded identities:
  - BTC: wallet=BTC perp=BTC spot_aliases=['BTC', 'WBTC']
  - ETH: wallet=ETH perp=ETH spot_aliases=['ETH', 'WETH']
...

All perp markets present in config.
All spot markets present in config.

Descriptor validation:
  - BTC spot descriptor: OK
  - BTC perp descriptor: OK
...

Validation complete.
```

---

### Common Misconfigurations

**Wrong Base URL:**
```toml
# ❌ Wrong
base_url = "https://hyperliquid.xyz"

# ✅ Correct
base_url = "https://api.hyperliquid-testnet.xyz"
```

**Invalid Address Format:**
```toml
# ❌ Wrong
account_address = "1234567890abcdef"

# ✅ Correct
account_address = "0x1234567890abcdef1234567890abcdef12345678"
```

**Missing Quotes:**
```toml
# ❌ Wrong
provider = openai

# ✅ Correct
provider = "openai"
```

**Wrong Data Types:**
```toml
# ❌ Wrong
tick_interval_seconds = "60"

# ✅ Correct
tick_interval_seconds = 60
```

---

## Support and Debugging

### Collect Diagnostic Information

When reporting issues, include:

1. **Configuration (sanitized):**
   ```bash
   # Remove sensitive keys before sharing
   cat config.toml | grep -v "key\|secret"
   ```

2. **Error Logs:**
   ```bash
   tail -100 logs/agent.log > error_log.txt
   ```

3. **System Information:**
   ```bash
   python --version
   uv --version
   uname -a
   ```

4. **Package Versions:**
   ```bash
   uv pip list > packages.txt
   ```

---

### Debug Mode

**Enable Maximum Verbosity:**
```toml
[agent]
log_level = "DEBUG"
```

```bash
export LOG_LEVEL=DEBUG
uv run python -m hyperliquid_agent.cli start
```

---

### Test Executor

**Test Order Submission:**
```bash
uv run python -m hyperliquid_agent.cli test_executor \
  --coin BTC \
  --action buy \
  --market perp \
  --size 0.001 \
  --config config.toml
```

**Expected Output:**
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
Order ID: 12345678
============================================================
```

---

## Related Documentation

- [Configuration Reference](/guide/configuration) - Complete configuration guide
- [CLI Reference](/guide/cli-reference) - Command-line interface
- [Deployment Guide](/guide/deployment) - Production deployment
- [Architecture Overview](/architecture/overview) - System architecture

