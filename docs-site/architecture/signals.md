# Signal System

The signal system is the data backbone of the trading agent, collecting and processing market information from multiple sources.

## Architecture

### Signal Orchestrator
Coordinates parallel collection from all enabled providers:
- Manages async execution
- Handles timeouts and errors
- Aggregates results into unified format

### Signal Providers

#### Hyperliquid Provider
Native exchange data:
- Funding rates (current and historical)
- Open interest and changes
- 24h volume
- Recent liquidations
- Order book depth

#### On-chain Provider
Blockchain metrics:
- Gas prices
- Network activity
- Token transfers
- Smart contract interactions

#### Sentiment Provider
Social and news sentiment:
- Twitter/X mentions and sentiment
- News article analysis
- Community sentiment scores
- Trending topics

#### External Markets Provider
Traditional market data:
- Stock indices (S&P 500, NASDAQ)
- Commodities (Gold, Oil)
- Forex pairs
- Crypto correlations

## Signal Processing

### Calculations Module
Derives additional metrics:
- Moving averages (SMA, EMA)
- Volatility measures (ATR, Bollinger Bands)
- Momentum indicators (RSI, MACD)
- Volume profiles
- Correlation matrices

### Caching System
SQLite-based cache for efficiency:
- Configurable TTL per signal type
- Automatic cache invalidation
- Metrics tracking (hit rate, latency)
- Persistent across restarts

## Signal Format

All signals follow a standardized format:

```python
{
    "symbol": "BTC",
    "timestamp": "2024-01-01T12:00:00Z",
    "hyperliquid": {
        "funding_rate": 0.0001,
        "open_interest": 1000000,
        "volume_24h": 50000000,
        ...
    },
    "onchain": {
        "gas_price": 50,
        "active_addresses": 10000,
        ...
    },
    "sentiment": {
        "twitter_score": 0.65,
        "news_sentiment": 0.72,
        ...
    },
    "external": {
        "btc_correlation_spy": 0.45,
        "gold_price": 2000,
        ...
    }
}
```

## Configuration

Enable/disable providers in `config.toml`:

```toml
[signals]
cache_ttl_seconds = 60
max_concurrent_requests = 10

[signals.hyperliquid]
enabled = true

[signals.onchain]
enabled = true
rpc_url = "https://your-rpc"

[signals.sentiment]
enabled = false  # Optional

[signals.external_markets]
enabled = true
```

## Extending the System

Add new providers by:
1. Implementing the `SignalProvider` interface
2. Registering in the orchestrator
3. Adding configuration options
4. Updating signal format documentation
