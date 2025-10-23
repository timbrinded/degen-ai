"""Signal collection system for time-scale-appropriate market signals."""

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
]
