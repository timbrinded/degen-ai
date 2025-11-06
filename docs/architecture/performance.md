# Performance Tuning

## Overview

The Hyperliquid Trading Agent is designed for startup-scale operations (1-4 engineers) with efficient resource usage and minimal infrastructure overhead. This guide covers performance optimization strategies for signal collection, caching, API usage, and concurrent request handling.

The system uses SQLite for caching (no Redis required), async I/O for concurrent data fetching, and configurable timeouts to balance latency with reliability.

## Cache TTL Tuning Guidelines

### Understanding TTL Trade-offs

Cache Time-To-Live (TTL) values control how long data remains valid before requiring a fresh fetch. Tuning TTL involves balancing:

**Shorter TTL (more frequent updates)**:
- ✅ Fresher data for better decision accuracy
- ✅ Reduced risk of stale data during volatile markets
- ❌ Higher API call volume and costs
- ❌ Increased latency from more network requests
- ❌ Higher rate limit risk

**Longer TTL (less frequent updates)**:
- ✅ Lower API call volume and costs
- ✅ Reduced latency from cache hits
- ✅ Better rate limit compliance
- ❌ Staler data may reduce decision quality
- ❌ Slower response to market changes

### Default TTL Values

The system uses signal-type-appropriate TTL values:

```python
# Fast signals - execution-level data (changes rapidly)
order_book_ttl = 5          # 5 seconds
mid_price_ttl = 10          # 10 seconds
spread_ttl = 5              # 5 seconds

# Medium signals - tactical data (changes moderately)
candles_ttl = 300           # 5 minutes
funding_ttl = 600           # 10 minutes
open_interest_ttl = 600     # 10 minutes
technical_indicators_ttl = 300  # 5 minutes

# Slow signals - macro data (changes slowly)
macro_events_ttl = 3600     # 1 hour
correlation_ttl = 3600      # 1 hour
sentiment_ttl = 1800        # 30 minutes
token_unlocks_ttl = 86400   # 24 hours
```

### Tuning Recommendations by Use Case

#### High-Frequency Trading (HFT)
For strategies requiring sub-second execution:

```python
# Aggressive freshness - prioritize data quality over cost
order_book_ttl = 2          # 2 seconds
mid_price_ttl = 5           # 5 seconds
candles_ttl = 60            # 1 minute
funding_ttl = 300           # 5 minutes
```

**Trade-offs**: 5-10x higher API costs, requires higher rate limits

#### Medium-Frequency Trading (MFT)
For strategies with 5-15 minute decision cycles:

```python
# Balanced approach - default values work well
order_book_ttl = 10         # 10 seconds
mid_price_ttl = 30          # 30 seconds
candles_ttl = 600           # 10 minutes
funding_ttl = 1800          # 30 minutes
```

**Trade-offs**: Moderate API costs, good data freshness

#### Low-Frequency Trading (LFT)
For strategies with hourly or daily decision cycles:

```python
# Cost-optimized - prioritize cache hits
order_book_ttl = 30         # 30 seconds
mid_price_ttl = 60          # 1 minute
candles_ttl = 1800          # 30 minutes
funding_ttl = 3600          # 1 hour
```

**Trade-offs**: Lowest API costs, acceptable staleness for slow strategies

### Monitoring Cache Performance

Track cache metrics to optimize TTL values:

```python
from hyperliquid_agent.signals.orchestrator import SignalOrchestrator

orchestrator = SignalOrchestrator(config)
metrics = orchestrator.get_cache_metrics()

print(f"Hit rate: {metrics['hit_rate_percent']}%")
print(f"Total entries: {metrics['total_entries']}")
print(f"Avg age: {metrics['avg_age_seconds']}s")
print(f"Expired entries: {metrics['expired_entries']}")
```

**Target Metrics**:
- **Hit rate**: 60-80% for well-tuned TTL values
- **Avg age**: Should be < 50% of TTL (indicates good cache utilization)
- **Expired entries**: < 100 (indicates timely cleanup)

**Optimization Guidelines**:
- **Hit rate < 40%**: TTL too short, increase by 50-100%
- **Hit rate > 90%**: TTL too long, data may be stale, decrease by 30-50%
- **Avg age > 80% of TTL**: Cache underutilized, consider shorter TTL
- **Expired entries > 500**: Increase cleanup frequency

### Dynamic TTL Adjustment

For advanced users, implement dynamic TTL based on market conditions:

```python
def get_adaptive_ttl(base_ttl: int, volatility: float) -> int:
    """Adjust TTL based on market volatility.
    
    Args:
        base_ttl: Base TTL in seconds
        volatility: Realized volatility (0.0 to 1.0+)
    
    Returns:
        Adjusted TTL in seconds
    """
    # High volatility = shorter TTL for fresher data
    if volatility > 0.05:  # > 5% volatility
        return int(base_ttl * 0.5)  # 50% shorter
    elif volatility > 0.03:  # > 3% volatility
        return int(base_ttl * 0.75)  # 25% shorter
    else:
        return base_ttl  # Normal TTL
```

### Cache Cleanup Configuration

Configure periodic cleanup to remove expired entries:

```toml
[signals.cache]
cleanup_interval_seconds = 3600  # Run cleanup every hour
vacuum_on_startup = true         # Optimize DB on startup
max_size_mb = 100                # Alert if DB exceeds 100MB
```

**Cleanup Frequency Guidelines**:
- **High-frequency trading**: 1800s (30 minutes) - prevents DB bloat
- **Medium-frequency trading**: 3600s (1 hour) - default, good balance
- **Low-frequency trading**: 7200s (2 hours) - minimal overhead

## Concurrent Request Optimization

### Understanding max_concurrent_requests

The signal orchestrator uses `asyncio.gather()` to fetch data concurrently, spawning multiple async tasks in parallel. This dramatically reduces latency compared to sequential fetching.

**Example**: Fetching order books for 10 positions
- **Sequential**: 10 positions × 200ms = 2000ms total
- **Concurrent**: max(200ms) = 200ms total (10x faster)

### Default Concurrency Settings

The system uses Python's `asyncio` with no hard limit on concurrent tasks:

```python
# Fast loop - concurrent order book fetching
tasks = [self.fetch_order_book(coin) for coin in coins]
results = await asyncio.gather(*tasks, return_exceptions=True)

# Medium loop - concurrent funding + OI + candles
funding_tasks = [self.fetch_funding_history(coin, ...) for coin in coins]
oi_tasks = [self.fetch_open_interest(coin) for coin in coins]
candles_tasks = [self.fetch_candles(coin, ...) for coin in coins]

results = await asyncio.gather(
    *funding_tasks, *oi_tasks, *candles_tasks,
    return_exceptions=True
)
```

### Tuning Guidelines

#### Conservative (Low Rate Limits)
For accounts with strict rate limits or shared API keys:

```python
# Implement semaphore-based rate limiting
import asyncio

class RateLimitedProvider:
    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_limit(self, fetch_func, *args):
        async with self.semaphore:
            return await fetch_func(*args)

# Usage
provider = RateLimitedProvider(max_concurrent=5)
tasks = [provider.fetch_with_limit(self.fetch_order_book, coin) for coin in coins]
results = await asyncio.gather(*tasks)
```

**Settings**: `max_concurrent=5` limits to 5 parallel requests

#### Balanced (Default)
For typical usage with standard rate limits:

```python
# No explicit limit - rely on asyncio's natural concurrency
# Hyperliquid API typically handles 10-20 concurrent requests well
tasks = [self.fetch_order_book(coin) for coin in coins]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Settings**: No limit, typically 10-20 concurrent requests

#### Aggressive (High Rate Limits)
For premium accounts or dedicated infrastructure:

```python
# Batch large request sets with controlled parallelism
async def fetch_in_batches(tasks, batch_size=50):
    results = []
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        batch_results = await asyncio.gather(*batch, return_exceptions=True)
        results.extend(batch_results)
    return results

# Usage for 100+ positions
tasks = [self.fetch_order_book(coin) for coin in coins]
results = await fetch_in_batches(tasks, batch_size=50)
```

**Settings**: Batch size of 50-100 for large portfolios

### Load Testing Examples

Test your configuration under realistic load:

```python
import asyncio
import time
from hyperliquid_agent.signals.orchestrator import SignalOrchestrator

async def load_test_concurrent_fetching():
    """Test concurrent signal collection performance."""
    orchestrator = SignalOrchestrator()
    
    # Simulate 20 positions
    test_coins = ["BTC", "ETH", "SOL", "AVAX", "MATIC", 
                  "ARB", "OP", "DOGE", "SHIB", "PEPE",
                  "WIF", "BONK", "JTO", "JUP", "PYTH",
                  "TIA", "DYM", "ALT", "STRK", "W"]
    
    # Test fast signal collection
    start = time.time()
    tasks = [orchestrator.hl_provider.fetch_order_book(coin) for coin in test_coins]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.time() - start
    
    success_count = sum(1 for r in results if not isinstance(r, Exception))
    print(f"Fetched {success_count}/{len(test_coins)} order books in {duration:.2f}s")
    print(f"Avg latency: {duration / len(test_coins) * 1000:.0f}ms per request")
    print(f"Effective concurrency: {len(test_coins) / duration:.1f}x")

# Run test
asyncio.run(load_test_concurrent_fetching())
```

**Expected Results**:
- **Good**: 20 order books in 0.5-1.0s (20-40x speedup)
- **Acceptable**: 20 order books in 1.0-2.0s (10-20x speedup)
- **Poor**: 20 order books in > 2.0s (< 10x speedup, check network/API)

### Timeout Configuration

Configure timeouts per signal type to prevent hanging requests:

```toml
[signals]
timeout_seconds = 30.0           # Global timeout
fast_timeout_seconds = 5.0       # Fast loop timeout
medium_timeout_seconds = 15.0    # Medium loop timeout
slow_timeout_seconds = 30.0      # Slow loop timeout
```

**Tuning Guidelines**:
- **Fast signals**: 3-10s (execution-critical, fail fast)
- **Medium signals**: 10-20s (tactical, allow retries)
- **Slow signals**: 20-60s (macro, comprehensive data)

## API Call Minimization Strategies

### Caching Best Practices

Maximize cache hit rate to reduce API calls:

#### 1. Enable Caching Globally

```toml
[signals]
caching_enabled = true
db_path = "state/signal_cache.db"
```

#### 2. Use Appropriate TTL Values

Match TTL to data update frequency:

```python
# Data that changes every second
order_book_ttl = 5  # Cache for 5 seconds

# Data that changes every minute
funding_ttl = 600  # Cache for 10 minutes

# Data that changes daily
macro_events_ttl = 3600  # Cache for 1 hour
```

#### 3. Leverage Cache Warming

Pre-populate cache before trading starts:

```python
async def warm_cache(orchestrator, watchlist):
    """Pre-fetch data for watchlist to populate cache."""
    tasks = []
    
    # Warm order books
    for coin in watchlist:
        tasks.append(orchestrator.hl_provider.fetch_order_book(coin))
    
    # Warm funding history
    for coin in watchlist:
        tasks.append(orchestrator.hl_provider.fetch_funding_history(coin, ...))
    
    # Execute all warming tasks
    await asyncio.gather(*tasks, return_exceptions=True)
    print(f"Cache warmed for {len(watchlist)} coins")
```

#### 4. Monitor Cache Metrics

Track hit rate and adjust TTL:

```python
metrics = orchestrator.get_cache_metrics()
if metrics['hit_rate_percent'] < 50:
    print("⚠️ Low cache hit rate - consider increasing TTL")
```

### Batch Request Patterns

Group related requests to minimize round trips:

#### 1. Batch Order Book Fetching

```python
# ❌ Bad: Sequential fetching
for coin in coins:
    order_book = await fetch_order_book(coin)
    process(order_book)

# ✅ Good: Concurrent batch fetching
tasks = [fetch_order_book(coin) for coin in coins]
order_books = await asyncio.gather(*tasks)
for order_book in order_books:
    process(order_book)
```

#### 2. Batch Historical Data Fetching

```python
# Fetch all historical data types concurrently
async def fetch_all_history(coin):
    funding_task = fetch_funding_history(coin, ...)
    oi_task = fetch_open_interest(coin)
    candles_task = fetch_candles(coin, ...)
    
    funding, oi, candles = await asyncio.gather(
        funding_task, oi_task, candles_task
    )
    return {"funding": funding, "oi": oi, "candles": candles}
```

#### 3. Reuse Shared Data

Avoid fetching the same data multiple times:

```python
# ❌ Bad: Fetch BTC price multiple times
btc_price_1 = await fetch_mid_price("BTC")
# ... later ...
btc_price_2 = await fetch_mid_price("BTC")

# ✅ Good: Fetch once, reuse
btc_price = await fetch_mid_price("BTC")
# ... use btc_price everywhere ...
```

### Cost Reduction Tips

#### 1. Disable Unused Signal Providers

Turn off providers you don't need:

```toml
[signals.onchain]
enabled = false  # Disable if not using on-chain data

[signals.external_market]
enabled = false  # Disable if not using external market data

[signals.sentiment]
enabled = false  # Disable if not using sentiment data
```

#### 2. Reduce Slow Loop Frequency

Slow signals change infrequently:

```toml
[governance]
slow_loop_interval_hours = 24  # Run once per day instead of hourly
```

#### 3. Use Free Data Sources

Prefer free providers when available:

```toml
[signals.external_market]
use_yfinance = true          # FREE - no API key required
use_coingecko = true         # FREE tier available
coingecko_api_key = ""       # Optional for higher limits

[signals.sentiment]
use_fear_greed_index = true  # FREE - no API key required
```

#### 4. Implement Request Deduplication

Avoid duplicate requests within short time windows:

```python
class RequestDeduplicator:
    def __init__(self, window_seconds=1.0):
        self.pending = {}
        self.window = window_seconds
    
    async def fetch_deduplicated(self, key, fetch_func):
        # If request already pending, wait for it
        if key in self.pending:
            return await self.pending[key]
        
        # Create new request
        task = asyncio.create_task(fetch_func())
        self.pending[key] = task
        
        try:
            result = await task
            return result
        finally:
            # Clean up after window expires
            await asyncio.sleep(self.window)
            self.pending.pop(key, None)
```

## Performance Metrics to Track

### Signal Collection Latency

Monitor how long signal collection takes:

```python
import time

async def collect_with_timing(orchestrator, signal_type, account_state):
    start = time.time()
    response = await orchestrator.collect_signals(
        SignalRequest(signal_type=signal_type, account_state=account_state)
    )
    duration = time.time() - start
    
    print(f"{signal_type} signals collected in {duration:.2f}s")
    print(f"  Confidence: {response.signals.metadata.confidence:.2f}")
    print(f"  Sources: {response.signals.metadata.sources}")
    print(f"  Cached: {response.signals.metadata.is_cached}")
    
    return response, duration
```

**Target Latencies**:
- **Fast signals**: < 1s (execution-critical)
- **Medium signals**: < 5s (tactical planning)
- **Slow signals**: < 15s (macro analysis)

### Decision Engine Latency

Track LLM response times:

```python
import time

async def make_decision_with_timing(agent, state):
    start = time.time()
    decision = await agent.make_decision(state)
    duration = time.time() - start
    
    print(f"Decision made in {duration:.2f}s")
    print(f"  Token usage: {decision.token_usage}")
    print(f"  Cost: ${decision.cost:.4f}")
    
    return decision, duration
```

**Target Latencies**:
- **Fast loop**: < 2s (quick decisions)
- **Medium loop**: < 10s (tactical planning)
- **Slow loop**: < 30s (comprehensive analysis)

### Execution Latency

Monitor trade execution speed:

```python
import time

async def execute_with_timing(executor, action):
    start = time.time()
    result = await executor.execute_action(action)
    duration = time.time() - start
    
    print(f"Trade executed in {duration:.2f}s")
    print(f"  Success: {result.success}")
    print(f"  Fill price: {result.fill_price}")
    
    return result, duration
```

**Target Latencies**:
- **Market orders**: < 1s (immediate execution)
- **Limit orders**: < 2s (order placement)
- **Cancellations**: < 1s (risk management)

### End-to-End Latency

Track complete decision cycle:

```python
async def full_cycle_timing(agent):
    start = time.time()
    
    # 1. Collect signals
    t1 = time.time()
    state = await agent.monitor.get_current_state_with_signals("fast")
    signal_time = time.time() - t1
    
    # 2. Make decision
    t2 = time.time()
    decision = await agent.make_decision(state)
    decision_time = time.time() - t2
    
    # 3. Execute trades
    t3 = time.time()
    results = await agent.execute_trades(decision.actions)
    execution_time = time.time() - t3
    
    total_time = time.time() - start
    
    print(f"Full cycle: {total_time:.2f}s")
    print(f"  Signal collection: {signal_time:.2f}s ({signal_time/total_time*100:.0f}%)")
    print(f"  Decision making: {decision_time:.2f}s ({decision_time/total_time*100:.0f}%)")
    print(f"  Trade execution: {execution_time:.2f}s ({execution_time/total_time*100:.0f}%)")
```

**Target Breakdown**:
- **Signal collection**: 30-40% of total time
- **Decision making**: 40-50% of total time
- **Trade execution**: 10-20% of total time

### Cache Performance Metrics

Monitor cache effectiveness:

```python
def log_cache_metrics(orchestrator):
    metrics = orchestrator.get_cache_metrics()
    
    print("Cache Performance:")
    print(f"  Hit rate: {metrics['hit_rate_percent']:.1f}%")
    print(f"  Total entries: {metrics['total_entries']}")
    print(f"  Total hits: {metrics['total_hits']}")
    print(f"  Total misses: {metrics['total_misses']}")
    print(f"  Avg age: {metrics['avg_age_seconds']:.0f}s")
    print(f"  Expired entries: {metrics['expired_entries']}")
```

**Target Metrics**:
- **Hit rate**: 60-80% (well-tuned TTL)
- **Avg age**: < 50% of TTL (good utilization)
- **Expired entries**: < 100 (timely cleanup)

## Load Testing Procedures

### Test Scenarios

#### Scenario 1: High-Frequency Fast Loop

Test rapid signal collection:

```python
async def test_high_frequency_fast_loop():
    """Simulate high-frequency trading with fast loop signals."""
    orchestrator = SignalOrchestrator()
    account_state = get_test_account_state()
    
    iterations = 100
    durations = []
    
    for i in range(iterations):
        start = time.time()
        response = await orchestrator.collect_signals(
            SignalRequest(signal_type="fast", account_state=account_state)
        )
        duration = time.time() - start
        durations.append(duration)
        
        if i % 10 == 0:
            print(f"Iteration {i}: {duration:.3f}s")
        
        await asyncio.sleep(0.1)  # 10 Hz frequency
    
    print(f"\nResults over {iterations} iterations:")
    print(f"  Mean: {sum(durations)/len(durations):.3f}s")
    print(f"  Min: {min(durations):.3f}s")
    print(f"  Max: {max(durations):.3f}s")
    print(f"  P95: {sorted(durations)[int(len(durations)*0.95)]:.3f}s")
```

**Success Criteria**:
- Mean < 0.5s
- P95 < 1.0s
- No timeouts

#### Scenario 2: Concurrent Multi-Loop Collection

Test collecting all signal types simultaneously:

```python
async def test_concurrent_multi_loop():
    """Test concurrent collection of fast, medium, and slow signals."""
    orchestrator = SignalOrchestrator()
    account_state = get_test_account_state()
    
    start = time.time()
    
    # Collect all signal types concurrently
    requests = [
        SignalRequest(signal_type="fast", account_state=account_state),
        SignalRequest(signal_type="medium", account_state=account_state),
        SignalRequest(signal_type="slow", account_state=account_state),
    ]
    
    responses = await orchestrator.collect_concurrent(requests)
    
    duration = time.time() - start
    
    print(f"Concurrent collection: {duration:.2f}s")
    for response in responses:
        print(f"  {response.signal_type}: confidence={response.signals.metadata.confidence:.2f}")
```

**Success Criteria**:
- Total time < 15s (concurrent speedup)
- All signals collected successfully
- Confidence > 0.7 for all signals

#### Scenario 3: Large Portfolio Stress Test

Test with many positions:

```python
async def test_large_portfolio():
    """Test signal collection for large portfolio (50+ positions)."""
    orchestrator = SignalOrchestrator()
    
    # Create account state with 50 positions
    positions = [
        Position(coin=f"COIN{i}", size=1.0, entry_price=100.0, ...)
        for i in range(50)
    ]
    account_state = AccountState(positions=positions, ...)
    
    start = time.time()
    response = await orchestrator.collect_signals(
        SignalRequest(signal_type="medium", account_state=account_state)
    )
    duration = time.time() - start
    
    print(f"Large portfolio ({len(positions)} positions): {duration:.2f}s")
    print(f"  Confidence: {response.signals.metadata.confidence:.2f}")
```

**Success Criteria**:
- Duration < 10s for 50 positions
- Confidence > 0.6
- No timeouts

### Benchmarking Tools

#### Built-in Profiling

Use Python's cProfile for detailed profiling:

```bash
python -m cProfile -o profile.stats -m hyperliquid_agent.cli start

# Analyze results
python -c "
import pstats
p = pstats.Stats('profile.stats')
p.sort_stats('cumulative')
p.print_stats(20)
"
```

#### Custom Benchmarking Script

Create a comprehensive benchmark:

```python
# scripts/benchmark_performance.py
import asyncio
import time
from hyperliquid_agent.signals.orchestrator import SignalOrchestrator

async def run_benchmarks():
    orchestrator = SignalOrchestrator()
    
    print("=== Performance Benchmarks ===\n")
    
    # Benchmark 1: Cache hit rate
    print("1. Cache Performance")
    metrics = orchestrator.get_cache_metrics()
    print(f"   Hit rate: {metrics['hit_rate_percent']:.1f}%")
    print(f"   Total entries: {metrics['total_entries']}")
    
    # Benchmark 2: Fast signal latency
    print("\n2. Fast Signal Latency")
    durations = []
    for _ in range(10):
        start = time.time()
        await orchestrator.collect_signals(...)
        durations.append(time.time() - start)
    print(f"   Mean: {sum(durations)/len(durations)*1000:.0f}ms")
    print(f"   P95: {sorted(durations)[9]*1000:.0f}ms")
    
    # Benchmark 3: Concurrent fetching
    print("\n3. Concurrent Fetching")
    start = time.time()
    tasks = [orchestrator.hl_provider.fetch_order_book(coin) for coin in test_coins]
    await asyncio.gather(*tasks)
    duration = time.time() - start
    print(f"   {len(test_coins)} order books: {duration:.2f}s")
    print(f"   Effective concurrency: {len(test_coins)/duration:.1f}x")

if __name__ == "__main__":
    asyncio.run(run_benchmarks())
```

Run benchmarks:

```bash
uv run python scripts/benchmark_performance.py
```

### Performance Baselines

Establish baseline metrics for your environment:

| Metric | Target | Good | Acceptable | Poor |
|--------|--------|------|------------|------|
| Fast signal latency | < 500ms | < 1s | < 2s | > 2s |
| Medium signal latency | < 3s | < 5s | < 10s | > 10s |
| Slow signal latency | < 10s | < 15s | < 30s | > 30s |
| Cache hit rate | > 70% | > 60% | > 40% | < 40% |
| Concurrent speedup | > 15x | > 10x | > 5x | < 5x |
| Decision latency | < 5s | < 10s | < 20s | > 20s |
| Execution latency | < 1s | < 2s | < 5s | > 5s |

## Troubleshooting Performance Issues

### High Latency

**Symptoms**: Signal collection takes > 5s consistently

**Diagnosis**:
```python
# Check cache hit rate
metrics = orchestrator.get_cache_metrics()
if metrics['hit_rate_percent'] < 40:
    print("Low cache hit rate - increase TTL")

# Check network latency
start = time.time()
await orchestrator.hl_provider.fetch_order_book("BTC")
latency = time.time() - start
if latency > 1.0:
    print("High network latency - check connection")
```

**Solutions**:
1. Increase cache TTL values
2. Enable caching if disabled
3. Check network connectivity
4. Reduce concurrent request count

### Low Cache Hit Rate

**Symptoms**: Hit rate < 40%

**Diagnosis**:
```python
metrics = orchestrator.get_cache_metrics()
print(f"Hit rate: {metrics['hit_rate_percent']}%")
print(f"Avg age: {metrics['avg_age_seconds']}s")
```

**Solutions**:
1. Increase TTL values by 50-100%
2. Verify caching is enabled
3. Check for cache invalidation issues
4. Warm cache before trading

### High API Costs

**Symptoms**: Excessive API calls, high costs

**Diagnosis**:
```python
# Track API call count
call_count = 0

async def tracked_fetch(*args):
    global call_count
    call_count += 1
    return await original_fetch(*args)

# Monitor for 1 hour
print(f"API calls in 1 hour: {call_count}")
```

**Solutions**:
1. Increase cache TTL values
2. Disable unused signal providers
3. Reduce loop frequencies
4. Implement request deduplication

### Memory Issues

**Symptoms**: High memory usage, OOM errors

**Diagnosis**:
```bash
# Check cache database size
ls -lh state/signal_cache.db

# Check Python memory usage
import psutil
process = psutil.Process()
print(f"Memory: {process.memory_info().rss / 1024 / 1024:.0f} MB")
```

**Solutions**:
1. Reduce cache max_size_mb
2. Increase cleanup frequency
3. Run VACUUM more frequently
4. Limit historical data retention

## Related Documentation

- [Monitoring Architecture](/architecture/monitoring) - Signal collection system
- [Configuration Guide](/guide/configuration) - TTL and timeout settings
- [Troubleshooting](/guide/troubleshooting) - Common performance issues
