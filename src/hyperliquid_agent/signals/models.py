"""Signal data models for time-scale-appropriate market signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from hyperliquid_agent.monitor import AccountState

if TYPE_CHECKING:
    from hyperliquid_agent.signals.processor import TechnicalIndicators


@dataclass
class SignalQualityMetadata:
    """Metadata about signal data quality and freshness.

    Tracks the quality, age, and source of signal data to enable downstream
    components to assess data reliability and make informed decisions about
    whether to use or discard signals.
    """

    timestamp: datetime
    """When the signal data was collected or last updated."""

    confidence: float
    """Confidence score from 0.0 to 1.0 based on data completeness and freshness.

    - 1.0: Fresh data from all expected sources
    - 0.5-0.9: Partial data or slightly stale
    - <0.5: Stale data (>10 minutes old) or significant missing data
    - 0.0: No valid data available
    """

    staleness_seconds: float
    """Age of the data in seconds. 0.0 for fresh data, increases with cache age."""

    sources: list[str]
    """List of data sources that contributed to this signal (e.g., ['hyperliquid', 'coingecko'])."""

    is_cached: bool
    """Whether this data came from cache (True) or fresh fetch (False)."""

    def calculate_confidence(
        self,
        expected_sources: list[str],
        max_staleness_seconds: float = 600.0,  # 10 minutes
    ) -> float:
        """Calculate confidence score based on data completeness and freshness.

        Args:
            expected_sources: List of sources that should have provided data
            max_staleness_seconds: Maximum acceptable staleness before confidence drops below 0.5

        Returns:
            Confidence score from 0.0 to 1.0
        """
        # Start with base confidence
        confidence = 1.0

        # Reduce confidence based on missing sources
        if expected_sources:
            source_completeness = len(self.sources) / len(expected_sources)
            confidence *= source_completeness

        # Reduce confidence based on staleness
        if self.staleness_seconds > max_staleness_seconds:
            # Data older than 10 minutes gets confidence below 0.5
            staleness_penalty = max_staleness_seconds / max(self.staleness_seconds, 1.0)
            confidence *= staleness_penalty
        elif self.staleness_seconds > 0:
            # Linear decay from 1.0 to 0.5 as staleness approaches max
            staleness_factor = 1.0 - (0.5 * self.staleness_seconds / max_staleness_seconds)
            confidence *= staleness_factor

        # Ensure confidence stays in valid range
        return max(0.0, min(1.0, confidence))

    @classmethod
    def create_fresh(cls, sources: list[str]) -> SignalQualityMetadata:
        """Create metadata for freshly fetched data.

        Args:
            sources: List of data sources that provided the data

        Returns:
            SignalQualityMetadata with fresh timestamp and high confidence
        """
        return cls(
            timestamp=datetime.now(),
            confidence=1.0,
            staleness_seconds=0.0,
            sources=sources,
            is_cached=False,
        )

    @classmethod
    def create_cached(
        cls, sources: list[str], cache_age_seconds: float, expected_sources: list[str] | None = None
    ) -> SignalQualityMetadata:
        """Create metadata for cached data with automatic confidence calculation.

        Args:
            sources: List of data sources in the cached data
            cache_age_seconds: Age of the cached data in seconds
            expected_sources: Optional list of expected sources for confidence calculation

        Returns:
            SignalQualityMetadata with cached flag and calculated confidence
        """
        metadata = cls(
            timestamp=datetime.now(),
            confidence=0.0,  # Will be calculated
            staleness_seconds=cache_age_seconds,
            sources=sources,
            is_cached=True,
        )

        # Calculate confidence based on staleness and completeness
        if expected_sources:
            metadata.confidence = metadata.calculate_confidence(expected_sources)
        else:
            # Without expected sources, base confidence only on staleness
            metadata.confidence = metadata.calculate_confidence([])

        return metadata

    @classmethod
    def create_fallback(cls) -> SignalQualityMetadata:
        """Create metadata for fallback/default data with zero confidence.

        Returns:
            SignalQualityMetadata indicating no valid data available
        """
        return cls(
            timestamp=datetime.now(),
            confidence=0.0,
            staleness_seconds=float("inf"),
            sources=[],
            is_cached=False,
        )


@dataclass
class FastLoopSignals:
    """Signals collected at fast loop frequency (seconds).

    These signals are used for execution-level decisions and immediate risk management.
    """

    spreads: dict[str, float]  # Coin -> spread in bps
    slippage_estimates: dict[str, float]  # Coin -> estimated slippage in bps
    short_term_volatility: float  # Recent volatility measure
    micro_pnl: float  # Very short-term PnL change
    partial_fill_rates: dict[str, float]  # Coin -> fill rate (0.0 to 1.0)

    # Enhanced fields from task 7
    order_book_depth: dict[str, float]  # Coin -> depth within 1% of mid-price
    api_latency_ms: float  # API response time in milliseconds
    metadata: SignalQualityMetadata  # Signal quality and freshness metadata


@dataclass
class MediumLoopSignals:
    """Signals collected at medium loop frequency (minutes-hours).

    These signals are used for tactical planning and Strategy Plan Card maintenance.
    """

    realized_vol_1h: float  # 1-hour realized volatility
    realized_vol_24h: float  # 24-hour realized volatility
    trend_score: float  # Trend strength indicator (-1 to 1)
    funding_basis: dict[str, float]  # Coin -> funding rate
    perp_spot_basis: dict[str, float]  # Coin -> perp-spot basis in bps
    concentration_ratios: dict[str, float]  # Coin -> position concentration (0.0 to 1.0)
    drift_from_targets: dict[str, float]  # Coin -> drift from target allocation in pct

    # Enhanced fields from task 8
    technical_indicators: dict[str, TechnicalIndicators | None]  # Coin -> technical indicators
    open_interest_change_24h: dict[str, float]  # Coin -> 24h OI change percentage
    oi_to_volume_ratio: dict[str, float]  # Coin -> OI-to-volume ratio for leverage assessment
    funding_rate_trend: dict[
        str, Literal["increasing", "decreasing", "stable"]
    ]  # Coin -> funding rate trend
    metadata: SignalQualityMetadata  # Signal quality and freshness metadata


@dataclass
class SlowLoopSignals:
    """Signals collected at slow loop frequency (daily-weekly).

    These signals are used for regime detection and macro-level policy changes.
    """

    macro_events_upcoming: list[dict]  # List of upcoming macro events
    cross_asset_risk_on_score: float  # Risk-on/risk-off score (-1 to 1)
    venue_health_score: float  # Exchange health indicator (0 to 1)
    liquidity_regime: Literal["high", "medium", "low"]  # Overall liquidity assessment


@dataclass
class UnlockEvent:
    """Token unlock event data.

    Represents a scheduled token unlock that could impact market liquidity.
    """

    asset: str
    """Asset symbol (e.g., 'BTC', 'ETH')."""

    unlock_date: datetime
    """When the tokens will be unlocked."""

    amount: float
    """Number of tokens being unlocked."""

    percentage_of_supply: float
    """Percentage of total supply being unlocked."""


@dataclass
class WhaleFlowData:
    """Whale transaction flow data.

    Tracks large wallet movements to identify potential market impact.
    """

    asset: str
    """Asset symbol (e.g., 'BTC', 'ETH')."""

    inflow: float
    """Total inflow from large transactions in 24h period."""

    outflow: float
    """Total outflow from large transactions in 24h period."""

    net_flow: float
    """Net flow (inflow - outflow) in 24h period."""

    large_tx_count: int
    """Number of large transactions detected."""


@dataclass
class EnhancedAccountState(AccountState):
    """Extended account state with time-scale-appropriate signals.

    Extends the base AccountState with optional signal collections for different
    decision time-scales.
    """

    fast_signals: FastLoopSignals | None = None
    medium_signals: MediumLoopSignals | None = None
    slow_signals: SlowLoopSignals | None = None
