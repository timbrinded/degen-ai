"""Signal collection system for time-scale-appropriate market signals."""

from hyperliquid_agent.signals.cache import CacheEntry, CacheMetrics, SQLiteCacheLayer
from hyperliquid_agent.signals.calculations import (
    calculate_realized_volatility,
    calculate_sma,
    calculate_spread_bps,
    calculate_trend_score,
)
from hyperliquid_agent.signals.collectors import (
    FastSignalCollector,
    MediumSignalCollector,
    SlowSignalCollector,
)
from hyperliquid_agent.signals.hyperliquid_provider import (
    Candle,
    FundingRate,
    HyperliquidProvider,
    OpenInterestData,
    OrderBookData,
)
from hyperliquid_agent.signals.models import (
    EnhancedAccountState,
    FastLoopSignals,
    MediumLoopSignals,
    SlowLoopSignals,
)
from hyperliquid_agent.signals.orchestrator import SignalOrchestrator
from hyperliquid_agent.signals.providers import (
    CircuitBreaker,
    CircuitState,
    DataProvider,
    ProviderResponse,
    RetryConfig,
    fetch_with_retry,
)
from hyperliquid_agent.signals.service import SignalRequest, SignalResponse, SignalService

__all__ = [
    # Models
    "FastLoopSignals",
    "MediumLoopSignals",
    "SlowLoopSignals",
    "EnhancedAccountState",
    # Collectors
    "FastSignalCollector",
    "MediumSignalCollector",
    "SlowSignalCollector",
    # Calculations
    "calculate_realized_volatility",
    "calculate_spread_bps",
    "calculate_sma",
    "calculate_trend_score",
    # Cache
    "SQLiteCacheLayer",
    "CacheEntry",
    "CacheMetrics",
    # Providers
    "DataProvider",
    "ProviderResponse",
    "RetryConfig",
    "CircuitBreaker",
    "CircuitState",
    "fetch_with_retry",
    # Hyperliquid Provider
    "HyperliquidProvider",
    "OrderBookData",
    "FundingRate",
    "Candle",
    "OpenInterestData",
    # Service
    "SignalService",
    "SignalRequest",
    "SignalResponse",
    # Orchestrator
    "SignalOrchestrator",
]
