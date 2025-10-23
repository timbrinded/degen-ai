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
from hyperliquid_agent.signals.models import (
    EnhancedAccountState,
    FastLoopSignals,
    MediumLoopSignals,
    SlowLoopSignals,
)
from hyperliquid_agent.signals.orchestrator import SignalOrchestrator
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
    # Service
    "SignalService",
    "SignalRequest",
    "SignalResponse",
    # Orchestrator
    "SignalOrchestrator",
]
