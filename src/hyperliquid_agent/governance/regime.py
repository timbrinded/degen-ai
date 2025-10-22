"""Regime detection and classification data models."""

from dataclasses import dataclass
from datetime import datetime
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
