# Signal Modules

Signal modules provide async signal collection, processing, and caching for the trading agent.

## SignalOrchestrator

Orchestrates concurrent signal collection from multiple providers.

**Module:** `hyperliquid_agent.signals.orchestrator`

### Constructor

```python
def __init__(self, config: dict | None = None) -> None
```

Initialize signal orchestrator with providers and collectors.

**Parameters:**

- `config` (dict | None): Signal configuration dictionary with optional keys:
  - `collection_timeout_seconds`: Global timeout override
  - `cache_db_path`: Path to SQLite cache database
  - `enable_caching`: Whether to enable caching (default: True)
  - `fast_timeout_seconds`: Timeout for fast signals (default: 5.0)
  - `medium_timeout_seconds`: Timeout for medium signals (default: 15.0)
  - `slow_timeout_seconds`: Timeout for slow signals (default: 30.0)

**Example:**

```python
from hyperliquid_agent.signals.orchestrator import SignalOrchestrator

config = {
    "cache_db_path": "state/signal_cache.db",
    "fast_timeout_seconds": 5.0,
    "medium_timeout_seconds": 15.0,
    "slow_timeout_seconds": 30.0
}

orchestrator = SignalOrchestrator(config)
```

### Methods

#### collect_signals

```python
async def collect_signals(
    self,
    request: SignalRequest
) -> SignalResponse
```

Collect signals based on request type with timeout and error handling.

**Parameters:**

- `request` (SignalRequest): Signal collection request with signal_type and account_state

**Returns:**

- `SignalResponse`: Collected signals and metadata

**Raises:**

- `asyncio.TimeoutError`: If collection exceeds timeout
- `ValueError`: If signal_type is unknown

**Example:**

```python
from hyperliquid_agent.signals.service import SignalRequest
from datetime import datetime

request = SignalRequest(
    signal_type="fast",
    account_state=account_state,
    timestamp=datetime.now()
)

response = await orchestrator.collect_signals(request)
print(f"Signals collected: {response.signals}")
print(f"Error: {response.error}")
```

#### collect_concurrent

```python
async def collect_concurrent(
    self,
    requests: list[SignalRequest]
) -> list[SignalResponse]
```

Collect multiple signal types concurrently using asyncio.gather().

**Parameters:**

- `requests` (list[SignalRequest]): List of signal collection requests

**Returns:**

- `list[SignalResponse]`: List of responses (one per request)

**Example:**

```python
requests = [
    SignalRequest("fast", account_state, datetime.now()),
    SignalRequest("medium", account_state, datetime.now()),
    SignalRequest("slow", account_state, datetime.now())
]

responses = await orchestrator.collect_concurrent(requests)
for response in responses:
    print(f"{response.signal_type}: {response.error or 'success'}")
```

#### get_health_status

```python
def get_health_status(self) -> dict
```

Get health status of all providers for monitoring.

**Returns:**

- `dict`: Health metrics for each provider and cache performance

#### shutdown

```python
async def shutdown(self) -> None
```

Gracefully shutdown orchestrator and cleanup resources.

## SignalService

Bridge between synchronous governance and async signal collection.

**Module:** `hyperliquid_agent.signals.service`

### Constructor

```python
def __init__(self, config: dict | None = None) -> None
```

Initialize signal service.

**Parameters:**

- `config` (dict | None): Signal configuration dictionary

**Example:**

```python
from hyperliquid_agent.signals.service import SignalService

service = SignalService(config)
service.start()
```

### Methods

#### start

```python
def start(self) -> None
```

Start background thread with async event loop.

#### stop

```python
def stop(self) -> None
```

Gracefully stop background thread.

#### collect_signals_sync

```python
def collect_signals_sync(
    self,
    signal_type: Literal["fast", "medium", "slow"],
    account_state: AccountState,
    timeout_seconds: float = 30.0
) -> FastLoopSignals | MediumLoopSignals | SlowLoopSignals
```

Synchronous interface for governance system to request signals.

**Parameters:**

- `signal_type` (Literal): Type of signals to collect
- `account_state` (AccountState): Current account state
- `timeout_seconds` (float): Timeout for signal collection (default: 30.0)

**Returns:**

- Collected signals (type depends on signal_type)

**Example:**

```python
# Start service
service = SignalService()
service.start()

# Collect signals synchronously
fast_signals = service.collect_signals_sync("fast", account_state)
print(f"Spreads: {fast_signals.spreads}")

# Stop service when done
service.stop()
```

### Data Classes

#### SignalRequest

Request for signal collection.

**Fields:**

- `signal_type` (Literal["fast", "medium", "slow"]): Type of signals to collect
- `account_state` (AccountState): Current account state
- `timestamp` (datetime): Request timestamp

#### SignalResponse

Response from signal collection.

**Fields:**

- `signal_type` (Literal["fast", "medium", "slow"]): Type of signals collected
- `signals` (FastLoopSignals | MediumLoopSignals | SlowLoopSignals): Collected signals
- `timestamp` (datetime): Collection timestamp
- `error` (str | None): Error message if collection failed

## SQLiteCacheLayer

SQLite-based caching layer with TTL management.

**Module:** `hyperliquid_agent.signals.cache`

### Constructor

```python
def __init__(
    self,
    db_path: Path | str = "state/signal_cache.db"
) -> None
```

Initialize SQLite cache layer.

**Parameters:**

- `db_path` (Path | str): Path to SQLite database file (default: "state/signal_cache.db")

**Example:**

```python
from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from pathlib import Path

cache = SQLiteCacheLayer(Path("state/signal_cache.db"))
```

### Methods

#### get

```python
async def get(self, key: str) -> CacheEntry | None
```

Retrieve cached value if not expired.

**Parameters:**

- `key` (str): Cache key

**Returns:**

- `CacheEntry | None`: Entry with value and age, or None if not found/expired

**Example:**

```python
entry = await cache.get("orderbook:BTC")
if entry:
    print(f"Value: {entry.value}")
    print(f"Age: {entry.age_seconds}s")
```

#### set

```python
async def set(
    self,
    key: str,
    value: Any,
    ttl_seconds: int
) -> None
```

Store value with TTL.

**Parameters:**

- `key` (str): Cache key
- `value` (Any): Value to cache (must be picklable)
- `ttl_seconds` (int): Time-to-live in seconds

**Example:**

```python
await cache.set("orderbook:BTC", orderbook_data, ttl_seconds=60)
```

#### invalidate

```python
async def invalidate(self, pattern: str) -> None
```

Invalidate cache entries matching pattern (SQL LIKE syntax).

**Parameters:**

- `pattern` (str): SQL LIKE pattern (e.g., "orderbook:%" for all orderbook entries)

**Example:**

```python
# Invalidate all orderbook entries
await cache.invalidate("orderbook:%")

# Invalidate all BTC-related entries
await cache.invalidate("%:BTC")
```

#### cleanup_expired

```python
async def cleanup_expired(self) -> None
```

Remove expired entries (run periodically).

#### get_metrics

```python
def get_metrics(self) -> CacheMetrics
```

Return cache hit rate and other metrics.

**Returns:**

- `CacheMetrics`: Performance statistics

**Example:**

```python
metrics = cache.get_metrics()
print(f"Hit rate: {metrics.hit_rate:.2f}%")
print(f"Total entries: {metrics.total_entries}")
print(f"Avg age: {metrics.avg_age_seconds:.1f}s")
```

### Data Classes

#### CacheEntry

Cache entry with value and age metadata.

**Fields:**

- `value` (Any): Cached value
- `age_seconds` (float): Age of entry in seconds

#### CacheMetrics

Cache performance metrics.

**Fields:**

- `total_entries` (int): Total valid entries
- `total_hits` (int): Total cache hits
- `avg_hits_per_entry` (float): Average hits per entry
- `hit_rate` (float): Hit rate percentage
- `total_misses` (int): Total cache misses
- `avg_age_seconds` (float): Average age of entries
- `expired_entries` (int): Count of expired entries

## DataProvider

Abstract base class for all data providers.

**Module:** `hyperliquid_agent.signals.providers`

### Constructor

```python
def __init__(self) -> None
```

Initialize provider with circuit breaker and retry config.

### Abstract Methods

#### fetch

```python
@abstractmethod
async def fetch(self, **kwargs) -> ProviderResponse
```

Fetch data from the provider.

**Parameters:**

- `**kwargs`: Provider-specific parameters

**Returns:**

- `ProviderResponse`: Data with quality metadata

**Raises:**

- `Exception`: If fetch fails after all retries

#### get_cache_ttl

```python
@abstractmethod
def get_cache_ttl(self) -> int
```

Return cache TTL in seconds for this provider's data.

#### get_provider_name

```python
@abstractmethod
def get_provider_name(self) -> str
```

Return provider identifier for logging and metrics.

### Methods

#### fetch_with_circuit_breaker

```python
async def fetch_with_circuit_breaker(
    self,
    fetch_func: Callable[[], Any]
) -> ProviderResponse
```

Execute fetch with circuit breaker protection.

**Parameters:**

- `fetch_func` (Callable): Async callable that performs the actual fetch

**Returns:**

- `ProviderResponse`: Result from fetch_func

**Raises:**

- `RuntimeError`: If circuit breaker is open
- `Exception`: If fetch fails after retries

#### get_health_status

```python
def get_health_status(self) -> dict[str, Any]
```

Get provider health status for monitoring.

**Returns:**

- `dict`: Health metrics including circuit state and failure count

### Data Classes

#### ProviderResponse

Standardized response from data providers with quality metadata.

**Fields:**

- `data` (T): The actual data payload
- `timestamp` (datetime): When the data was collected
- `source` (str): Provider identifier
- `confidence` (float): Data quality score (0.0 to 1.0)
- `is_cached` (bool): Whether data came from cache
- `cache_age_seconds` (float | None): Age of cached data

#### RetryConfig

Configuration for exponential backoff retry logic.

**Fields:**

- `max_attempts` (int): Maximum retry attempts (default: 3)
- `backoff_factor` (float): Exponential backoff multiplier (default: 2.0)
- `initial_delay_seconds` (float): Initial delay before first retry (default: 1.0)
- `max_delay_seconds` (float): Maximum delay between retries (default: 10.0)

#### CircuitBreaker

Circuit breaker for handling sustained provider failures.

**Methods:**

- `record_success()`: Record successful call, reset failure count
- `record_failure()`: Record failed call, potentially open circuit
- `can_attempt()`: Check if call should be attempted
- `get_state()`: Get current circuit state

**States:**

- `CLOSED`: Normal operation, all requests allowed
- `OPEN`: Provider failing, reject requests immediately
- `HALF_OPEN`: Testing recovery, allow limited requests

## Utility Functions

### fetch_with_retry

```python
async def fetch_with_retry(
    fetch_func: Callable[[], Any],
    retry_config: RetryConfig,
    operation_name: str = "fetch"
) -> Any
```

Execute async fetch with exponential backoff retry.

**Parameters:**

- `fetch_func` (Callable): Async callable to execute
- `retry_config` (RetryConfig): Retry configuration
- `operation_name` (str): Name for logging purposes

**Returns:**

- Result from fetch_func

**Raises:**

- `Exception`: If all retry attempts fail

**Example:**

```python
from hyperliquid_agent.signals.providers import (
    fetch_with_retry,
    RetryConfig
)

async def fetch_data():
    # Your fetch logic here
    return await api.get_data()

config = RetryConfig(max_attempts=3, backoff_factor=2.0)
result = await fetch_with_retry(fetch_data, config, "my_operation")
```

## See Also

- [Core Modules](/api/core) - Main agent and execution
- [Governance Modules](/api/governance) - Strategy governance
- [Signals Architecture](/architecture/signals) - Detailed signal design
- [Performance Tuning](/architecture/performance) - Cache optimization
