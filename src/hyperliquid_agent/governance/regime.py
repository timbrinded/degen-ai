"""Regime detection and classification data models."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol


@dataclass
class RegimeSignals:
    """Market signals used for regime classification.

    Core signals are from Hyperliquid API (MVP).
    Enhanced signals are optional for future versions with external data.
    """

    # Core signals (from Hyperliquid API - MVP)
    # Trend indicators
    price_sma_20: float
    price_sma_50: float
    adx: float  # Average Directional Index

    # Volatility
    realized_vol_24h: float

    # Funding/Carry
    avg_funding_rate: float

    # Liquidity
    bid_ask_spread_bps: float
    order_book_depth: float

    # Enhanced signals (optional - for future versions)
    cross_asset_correlation: float | None = None  # BTC/SPX, BTC/ETH correlation
    macro_risk_score: float | None = None  # Composite risk-on/risk-off score
    sentiment_index: float | None = None  # Crypto Fear & Greed or similar
    volatility_regime: str | None = None  # "low", "medium", "high" from VIX-like metric


@dataclass
class RegimeClassification:
    """Classification of current market regime."""

    regime: Literal["trending", "range-bound", "carry-friendly", "event-risk", "unknown"]
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    signals: RegimeSignals


class ExternalDataProvider(Protocol):
    """Protocol for pluggable external data sources.

    This allows future enhancement with external data without changing core logic.
    """

    def get_cross_asset_correlation(self, asset1: str, asset2: str) -> float:
        """Get correlation between two assets.

        Args:
            asset1: First asset symbol (e.g., "BTC")
            asset2: Second asset symbol (e.g., "ETH")

        Returns:
            Correlation coefficient between -1 and 1
        """
        ...

    def get_macro_risk_score(self) -> float:
        """Get macro risk-on/risk-off score.

        Returns:
            Risk score between -1 (risk-off) and 1 (risk-on)
        """
        ...

    def get_sentiment_index(self) -> float:
        """Get market sentiment index.

        Returns:
            Sentiment index between 0 (extreme fear) and 100 (extreme greed)
        """
        ...


@dataclass
class RegimeDetectorConfig:
    """Configuration for regime detection and hysteresis."""

    confirmation_cycles_required: int = 3
    hysteresis_enter_threshold: float = 0.7
    hysteresis_exit_threshold: float = 0.4
    event_lock_window_hours_before: int = 2
    event_lock_window_hours_after: int = 1
    use_enhanced_signals: bool = False  # Enable external data sources


class RegimeDetector:
    """Detects and classifies market regimes with hysteresis.

    The RegimeDetector classifies market conditions into regimes (trending,
    range-bound, carry-friendly, event-risk) and requires sustained confirmation
    before transitioning to prevent ping-ponging.

    Design Philosophy:
    - MVP uses only Hyperliquid-native data (prices, funding, order book)
    - Architecture supports optional external data sources for enhanced accuracy
    - Hysteresis prevents rapid regime switching from market noise
    """

    def __init__(
        self,
        config: RegimeDetectorConfig,
        external_data_provider: ExternalDataProvider | None = None,
    ):
        """Initialize regime detector.

        Args:
            config: Configuration for regime detection
            external_data_provider: Optional external data source for enhanced signals
        """
        self.config = config
        self.current_regime: str = "unknown"
        self.regime_history: deque = deque(maxlen=config.confirmation_cycles_required)
        self.macro_calendar: list[dict] = []
        self.external_data = external_data_provider

    def classify_regime(self, signals: RegimeSignals) -> RegimeClassification:
        """Classify current market regime based on signals.

        MVP: Uses only Hyperliquid-native signals (price, funding, volatility)
        Enhanced: Incorporates external data when available to improve classification accuracy

        Args:
            signals: Market signals for regime classification

        Returns:
            RegimeClassification with regime type, confidence, and timestamp
        """
        base_confidence = 1.0

        # Enhanced: Adjust confidence based on external signals if available
        if self.config.use_enhanced_signals and self.external_data:
            base_confidence = self._adjust_confidence_with_external_data(signals)

        # Trending: Strong directional movement
        if signals.adx > 25 and abs(signals.price_sma_20 - signals.price_sma_50) / signals.price_sma_50 > 0.02:
            confidence = min(signals.adx / 40, 1.0) * base_confidence
            return RegimeClassification(
                regime="trending",
                confidence=confidence,
                timestamp=datetime.now(),
                signals=signals,
            )

        # Range-bound: Low volatility, tight range
        if signals.realized_vol_24h < 0.3 and signals.adx < 20:
            confidence = 0.8 * base_confidence
            return RegimeClassification(
                regime="range-bound",
                confidence=confidence,
                timestamp=datetime.now(),
                signals=signals,
            )

        # Carry-friendly: Positive funding, low volatility
        if signals.avg_funding_rate > 0.01 and signals.realized_vol_24h < 0.4:
            confidence = 0.75 * base_confidence
            return RegimeClassification(
                regime="carry-friendly",
                confidence=confidence,
                timestamp=datetime.now(),
                signals=signals,
            )

        # Event-risk: Near scheduled macro event
        if self._is_near_macro_event():
            return RegimeClassification(
                regime="event-risk",
                confidence=1.0,
                timestamp=datetime.now(),
                signals=signals,
            )

        return RegimeClassification(
            regime="unknown",
            confidence=0.5,
            timestamp=datetime.now(),
            signals=signals,
        )

    def _adjust_confidence_with_external_data(self, signals: RegimeSignals) -> float:
        """Adjust regime classification confidence using external data (enhanced version).

        Examples:
        - High cross-asset correlation during trending regime → increase confidence
        - Risk-off macro environment during carry regime → decrease confidence
        - Extreme sentiment during range-bound → decrease confidence

        Args:
            signals: Market signals including optional enhanced signals

        Returns:
            Confidence adjustment multiplier (capped at 1.2 for 20% boost)
        """
        if not self.external_data:
            return 1.0

        adjustment = 1.0

        # Example: Cross-asset correlation confirmation
        if signals.cross_asset_correlation is not None:
            if abs(signals.cross_asset_correlation) > 0.7:
                adjustment *= 1.1  # Strong correlation increases confidence

        # Example: Macro risk alignment
        if signals.macro_risk_score is not None:
            # Risk-on environment supports trending/carry, risk-off supports range/defensive
            # Implementation would check alignment with current regime classification
            pass

        return min(adjustment, 1.2)  # Cap at 20% confidence boost

    def update_and_confirm(self, classification: RegimeClassification) -> tuple[bool, str]:
        """Update regime history and check if regime change is confirmed.

        Implements hysteresis by requiring sustained signals over N cycles before
        confirming a regime change. This prevents rapid switching from market noise.

        Args:
            classification: Latest regime classification

        Returns:
            Tuple of (regime_changed, reason_message)
        """
        self.regime_history.append(classification)

        if len(self.regime_history) < self.config.confirmation_cycles_required:
            return False, "Insufficient history for confirmation"

        # Check for sustained new regime
        recent_regimes = [c.regime for c in self.regime_history]
        candidate_regime = max(set(recent_regimes), key=recent_regimes.count)

        if candidate_regime == self.current_regime:
            return False, "No regime change"

        # Apply hysteresis
        candidate_count = recent_regimes.count(candidate_regime)
        candidate_confidence = candidate_count / len(recent_regimes)

        if candidate_confidence >= self.config.hysteresis_enter_threshold:
            old_regime = self.current_regime
            self.current_regime = candidate_regime
            return True, f"Regime change confirmed: {old_regime} → {candidate_regime}"

        return (
            False,
            f"Regime change not confirmed: {candidate_confidence:.2f} < {self.config.hysteresis_enter_threshold}",
        )

    def is_in_event_lock_window(self, current_time: datetime) -> tuple[bool, str]:
        """Check if currently in event lock window.

        Event lock windows prevent plan changes during scheduled macro events
        (e.g., FOMC, CPI, jobs reports) unless safety tripwires fire.

        Args:
            current_time: Current timestamp to check

        Returns:
            Tuple of (in_lock_window, event_description)
        """
        for event in self.macro_calendar:
            event_time = event["datetime"]
            lock_start = event_time - timedelta(hours=self.config.event_lock_window_hours_before)
            lock_end = event_time + timedelta(hours=self.config.event_lock_window_hours_after)

            if lock_start <= current_time <= lock_end:
                return True, f"Event lock: {event['name']} at {event_time}"

        return False, "No event lock"

    def _is_near_macro_event(self) -> bool:
        """Check if near scheduled macro event.

        Returns:
            True if within event lock window before a scheduled event
        """
        now = datetime.now()
        for event in self.macro_calendar:
            time_to_event = (event["datetime"] - now).total_seconds() / 3600
            if 0 <= time_to_event <= self.config.event_lock_window_hours_before:
                return True
        return False
