"""Regime detection and classification using LLM-based analysis."""

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from hyperliquid_agent.config import LLMConfig


@dataclass
class PriceContext:
    """Price action context for regime classification.

    Multi-timeframe price returns and market structure indicators.
    These are the PRIMARY signals for LLM-based regime detection.
    """

    # Current price info
    current_price: float

    # Multi-timeframe returns (PRIMARY SIGNALS)
    return_1d: float  # 1-day return %
    return_7d: float  # 7-day return %
    return_30d: float  # 30-day return %
    return_90d: float  # 90-day return %

    # SMA distances (supporting signals)
    sma20_distance: float  # % distance from 20-SMA
    sma50_distance: float  # % distance from 50-SMA

    # Market structure (supporting signals)
    higher_highs: bool  # Making higher highs?
    higher_lows: bool  # Making higher lows?


@dataclass
class RegimeSignals:
    """Market signals used for regime classification.

    Technical indicators serve as CONFIRMING signals for the LLM.
    Price context (returns, structure) are the PRIMARY signals.
    """

    # Price context (PRIMARY - added for LLM approach)
    price_context: PriceContext

    # Technical indicators (CONFIRMING)
    price_sma_20: float
    price_sma_50: float
    adx: float  # Average Directional Index
    realized_vol_24h: float

    # Funding/Carry
    avg_funding_rate: float

    # Liquidity
    bid_ask_spread_bps: float
    order_book_depth: float

    # Enhanced signals (optional)
    cross_asset_correlation: float | None = None
    macro_risk_score: float | None = None
    sentiment_index: float | None = None
    volatility_regime: str | None = None


@dataclass
class RegimeClassification:
    """Classification of current market regime."""

    regime: Literal[
        "trending-bull", "trending-bear", "range-bound", "carry-friendly", "event-risk", "unknown"
    ]
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    signals: RegimeSignals
    reasoning: str = ""  # LLM reasoning for classification


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

    # Optional LLM override for regime classification
    # If not provided, will use main application LLM config
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None


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
        llm_config: "LLMConfig",  # Main application LLM config
        external_data_provider: ExternalDataProvider | None = None,
        logger: logging.Logger | None = None,
    ):
        """Initialize regime detector.

        Args:
            config: Configuration for regime detection
            llm_config: Main application LLM config (used unless overridden)
            external_data_provider: Optional external data source for enhanced signals
            logger: Optional logger instance for governance event logging
        """
        self.config = config
        self.llm_config = llm_config
        self.current_regime: str = "unknown"
        self.regime_history: deque = deque(maxlen=config.confirmation_cycles_required)
        self.macro_calendar: list[dict] = []
        self.external_data = external_data_provider
        self.logger = logger or logging.getLogger(__name__)

        # Initialize centralized LLM client
        self.llm_client = self._init_llm_client()

    def _init_llm_client(self):
        """Initialize centralized LLM client for regime classification.

        Uses main application LLM config by default, with optional overrides
        from regime detector config for using a different/cheaper model.

        Returns:
            Initialized LLMClient from centralized utility
        """
        from hyperliquid_agent.config import LLMConfig
        from hyperliquid_agent.llm_client import create_llm_client

        # Create effective config (main config + regime detector overrides)
        provider = self.config.llm_provider or self.llm_config.provider
        # Ensure provider is a valid Literal type
        if provider not in ("openai", "anthropic"):
            provider = "anthropic"  # Default fallback

        effective_config = LLMConfig(
            provider=provider,  # type: ignore[arg-type]
            model=self.config.llm_model or self.llm_config.model,
            api_key=self.llm_config.api_key,  # Always use main API key
            temperature=self.config.llm_temperature
            if self.config.llm_temperature is not None
            else 0.0,  # Default to 0.0 for deterministic regime classification
            max_tokens=1000,  # Regime classification is concise
        )

        return create_llm_client(effective_config, logger=self.logger)

    def classify_regime(self, signals: RegimeSignals) -> RegimeClassification:
        """Classify current market regime using LLM-based analysis.

        Uses multi-timeframe price returns as primary signals and technical
        indicators as confirming signals. The LLM naturally handles:
        - Direction awareness (bull vs bear trends)
        - "Steady grind" bull markets that boolean logic missed
        - Ambiguous scenarios without strict thresholds

        Args:
            signals: Market signals including price context

        Returns:
            RegimeClassification with regime type, confidence, reasoning, and timestamp
        """
        from hyperliquid_agent.governance.llm_regime_classifier import classify_regime_with_llm

        # Check for event-risk first (overrides LLM classification)
        if self._is_near_macro_event():
            classification = RegimeClassification(
                regime="event-risk",
                confidence=1.0,
                reasoning="Near scheduled macro event",
                timestamp=datetime.now(),
                signals=signals,
            )
            self.logger.info(
                "Regime classified: event-risk (near macro event)",
                extra={
                    "governance_event": "regime_classified",
                    "regime": "event-risk",
                    "confidence": 1.0,
                    "macro_events_count": len(self.macro_calendar),
                },
            )
            return classification

        # Use LLM for classification (centralized client handles all details)
        return classify_regime_with_llm(
            signals=signals,
            llm_client=self.llm_client,
            logger=self.logger,
        )

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
            self.logger.debug(
                f"Regime confirmation pending: {len(self.regime_history)}/{self.config.confirmation_cycles_required} cycles",
                extra={
                    "governance_event": "regime_confirmation_pending",
                    "current_regime": self.current_regime,
                    "latest_classification": classification.regime,
                    "history_length": len(self.regime_history),
                    "required_cycles": self.config.confirmation_cycles_required,
                },
            )
            return False, "Insufficient history for confirmation"

        # Check for sustained new regime
        recent_regimes = [c.regime for c in self.regime_history]
        candidate_regime = max(set(recent_regimes), key=recent_regimes.count)

        if candidate_regime == self.current_regime:
            self.logger.debug(
                "No regime change detected",
                extra={
                    "governance_event": "regime_no_change",
                    "current_regime": self.current_regime,
                    "recent_regimes": recent_regimes,
                },
            )
            return False, "No regime change"

        # Apply hysteresis
        candidate_count = recent_regimes.count(candidate_regime)
        candidate_confidence = candidate_count / len(recent_regimes)

        if candidate_confidence >= self.config.hysteresis_enter_threshold:
            old_regime = self.current_regime
            self.current_regime = candidate_regime

            self.logger.info(
                f"Regime change confirmed: {old_regime} → {candidate_regime}",
                extra={
                    "governance_event": "regime_change_confirmed",
                    "old_regime": old_regime,
                    "new_regime": candidate_regime,
                    "candidate_confidence": candidate_confidence,
                    "hysteresis_threshold": self.config.hysteresis_enter_threshold,
                    "confirmation_cycles": len(self.regime_history),
                    "recent_regimes": recent_regimes,
                },
            )
            return True, f"Regime change confirmed: {old_regime} → {candidate_regime}"

        self.logger.debug(
            f"Regime change not confirmed: {candidate_confidence:.2f} < {self.config.hysteresis_enter_threshold}",
            extra={
                "governance_event": "regime_change_not_confirmed",
                "current_regime": self.current_regime,
                "candidate_regime": candidate_regime,
                "candidate_confidence": candidate_confidence,
                "hysteresis_threshold": self.config.hysteresis_enter_threshold,
                "recent_regimes": recent_regimes,
            },
        )
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
