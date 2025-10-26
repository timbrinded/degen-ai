"""Data models for backtesting framework."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hyperliquid_agent.governance.regime import RegimeSignals
from hyperliquid_agent.signals.hyperliquid_provider import Candle, FundingRate, OrderBookData


@dataclass
class BacktestConfig:
    """Backtest configuration parameters.

    Defines the parameters for running a backtest including date range,
    sampling interval, assets to track, and output settings.

    Attributes:
        start_date: Start timestamp for backtest period
        end_date: End timestamp for backtest period
        interval: Sampling interval for data points ("1h", "4h", "1d")
        assets: List of asset symbols to track (e.g., ["BTC", "ETH"])
        output_dir: Directory path for saving backtest results
        hyperliquid_base_url: Base URL for Hyperliquid API
    """

    start_date: datetime
    end_date: datetime
    interval: str  # "1h", "4h", "1d"
    assets: list[str]
    output_dir: Path
    hyperliquid_base_url: str


@dataclass
class BacktestResult:
    """Single backtest data point.

    Represents the regime classification and underlying signals at a specific
    timestamp during the backtest.

    Attributes:
        timestamp: When this data point was sampled
        regime: Classified regime type ("trending", "range-bound", "carry-friendly", "event-risk", "unknown")
        confidence: Confidence score for the classification (0.0 to 1.0)
        signals: RegimeSignals used for classification
    """

    timestamp: datetime
    regime: str
    confidence: float
    signals: RegimeSignals


@dataclass
class BacktestSummary:
    """Complete backtest results and metadata.

    Contains all backtest results along with metadata about the backtest
    configuration and execution statistics.

    Attributes:
        results: List of all BacktestResult data points
        start_time: Backtest start timestamp
        end_time: Backtest end timestamp
        interval: Sampling interval used ("1h", "4h", "1d")
        assets: List of assets tracked during backtest
        total_points: Total number of timestamps in backtest period
        skipped_points: Number of timestamps skipped due to low confidence or missing data
    """

    results: list[BacktestResult]
    start_time: datetime
    end_time: datetime
    interval: str
    assets: list[str]
    total_points: int
    skipped_points: int


@dataclass
class HistoricalDataCache:
    """Cached historical data for backtest period.

    Stores pre-fetched historical data organized by asset symbol to avoid
    repeated API calls during backtest iteration.

    Attributes:
        candles: Dictionary mapping coin symbol to list of Candle objects
        funding_rates: Dictionary mapping coin symbol to list of FundingRate objects
        order_books: Dictionary mapping coin symbol to timestamp-indexed OrderBookData
    """

    candles: dict[str, list[Candle]]
    funding_rates: dict[str, list[FundingRate]]
    order_books: dict[str, dict[datetime, OrderBookData]]
