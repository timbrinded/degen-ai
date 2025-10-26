"""Backtest runner for orchestrating backtest execution."""

import asyncio
import logging
from datetime import datetime, timedelta

from tqdm import tqdm

from hyperliquid_agent.backtesting.historical_data import HistoricalDataManager
from hyperliquid_agent.backtesting.models import (
    BacktestResult,
    BacktestSummary,
    HistoricalDataCache,
)
from hyperliquid_agent.backtesting.signal_reconstructor import SignalReconstructor
from hyperliquid_agent.governance.regime import RegimeDetector

logger = logging.getLogger(__name__)


class BacktestRunner:
    """Orchestrates backtest execution.

    Coordinates historical data fetching, signal reconstruction, and regime
    classification across a specified time period. Implements batch data
    fetching optimization and progress tracking.
    """

    # Minimum confidence threshold for including data points
    MIN_CONFIDENCE_THRESHOLD = 0.3

    # Warning threshold for skipped points percentage
    MAX_SKIP_PERCENTAGE = 20.0

    def __init__(
        self,
        historical_data_manager: HistoricalDataManager,
        signal_reconstructor: SignalReconstructor,
        regime_detector: RegimeDetector,
    ):
        """Initialize backtest runner.

        Args:
            historical_data_manager: Manager for fetching historical data
            signal_reconstructor: Reconstructor for building RegimeSignals
            regime_detector: Detector for classifying regimes
        """
        self.data_manager = historical_data_manager
        self.signal_reconstructor = signal_reconstructor
        self.regime_detector = regime_detector

    async def run_backtest(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str,
        assets: list[str],
    ) -> BacktestSummary:
        """Execute backtest over date range.

        Validates date range, generates timestamp sequence, pre-fetches all
        historical data, iterates through timestamps to reconstruct signals
        and classify regimes, and returns complete summary.

        Args:
            start_date: Backtest start timestamp
            end_date: Backtest end timestamp
            interval: Sampling interval ("1h", "4h", "1d")
            assets: List of asset symbols to track

        Returns:
            BacktestSummary with all results and metadata

        Raises:
            ValueError: If date range is invalid
        """
        # Validate date range
        self._validate_date_range(start_date, end_date)

        logger.info(
            f"Starting backtest: {start_date.date()} to {end_date.date()}, "
            f"interval={interval}, assets={assets}"
        )

        # Generate timestamp sequence
        timestamps = self._generate_timestamp_sequence(start_date, end_date, interval)
        total_points = len(timestamps)

        logger.info(f"Generated {total_points} timestamps for backtest")

        # Pre-fetch all historical data (batch optimization)
        logger.info("Pre-fetching historical data...")
        data_cache = await self._batch_fetch_data(start_date, end_date, interval, assets)

        # Iterate through timestamps and collect results
        results = []
        skipped_points = 0

        logger.info("Processing timestamps...")
        try:
            for timestamp in tqdm(timestamps, desc="Backtesting", unit="point"):  # type: ignore[misc]
                # Reconstruct signals for this timestamp
                signals = await self.signal_reconstructor.reconstruct_signals(
                    timestamp=timestamp,
                    candles=data_cache.candles,
                    funding_rates=data_cache.funding_rates,
                    order_books={},  # Order books not available for historical backtesting
                )

                # Skip if confidence too low
                if signals is None:
                    skipped_points += 1
                    logger.debug(f"Skipped timestamp {timestamp} due to low confidence")
                    continue

                # Classify regime
                classification = self.regime_detector.classify_regime(signals)

                # Store result
                result = BacktestResult(
                    timestamp=timestamp,
                    regime=classification.regime,
                    confidence=classification.confidence,
                    signals=signals,
                )
                results.append(result)

        except KeyboardInterrupt:
            logger.warning(
                f"Backtest interrupted by user. Saving partial results ({len(results)} points)..."
            )

        # Generate summary
        summary = BacktestSummary(
            results=results,
            start_time=start_date,
            end_time=end_date,
            interval=interval,
            assets=assets,
            total_points=total_points,
            skipped_points=skipped_points,
        )

        # Display warning if too many points skipped
        skip_percentage = (skipped_points / total_points * 100) if total_points > 0 else 0
        if skip_percentage > self.MAX_SKIP_PERCENTAGE:
            logger.warning(
                f"High skip rate: {skip_percentage:.1f}% of timestamps skipped "
                f"({skipped_points}/{total_points}). "
                "Consider using a different date range or interval with better data coverage."
            )

        logger.info(
            f"Backtest complete: {len(results)} data points collected, "
            f"{skipped_points} skipped ({skip_percentage:.1f}%)"
        )

        return summary

    def _validate_date_range(self, start_date: datetime, end_date: datetime) -> None:
        """Validate date range parameters.

        Args:
            start_date: Start timestamp
            end_date: End timestamp

        Raises:
            ValueError: If date range is invalid
        """
        if end_date <= start_date:
            raise ValueError(f"End date ({end_date}) must be after start date ({start_date})")

        now = datetime.now()
        if start_date > now:
            raise ValueError(f"Start date ({start_date}) cannot be in the future")

        if end_date > now:
            raise ValueError(f"End date ({end_date}) cannot be in the future")

    def _generate_timestamp_sequence(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> list[datetime]:
        """Generate timestamp sequence based on interval.

        Args:
            start_date: Start timestamp
            end_date: End timestamp
            interval: Sampling interval ("1h", "4h", "1d")

        Returns:
            List of timestamps at specified interval

        Raises:
            ValueError: If interval is invalid
        """
        interval_map = {
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }

        if interval not in interval_map:
            raise ValueError(
                f"Invalid interval: {interval}. "
                f"Supported intervals: {', '.join(interval_map.keys())}"
            )

        delta = interval_map[interval]
        timestamps = []
        current = start_date

        while current <= end_date:
            timestamps.append(current)
            current += delta

        return timestamps

    async def _batch_fetch_data(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str,
        assets: list[str],
    ) -> HistoricalDataCache:
        """Pre-fetch all historical data before iteration.

        Fetches multiple assets concurrently for performance using asyncio.gather.
        Includes extra lookback period for indicator calculations.

        Args:
            start_date: Start timestamp
            end_date: End timestamp
            interval: Sampling interval
            assets: List of asset symbols

        Returns:
            HistoricalDataCache with all pre-fetched data
        """
        # Add lookback period for indicator calculations (50 periods for SMA-50)
        lookback_periods = 50
        interval_delta = self._interval_to_timedelta(interval)
        lookback_start = start_date - (interval_delta * lookback_periods)

        # Fetch candles for all assets concurrently
        candle_tasks = [
            self.data_manager.fetch_candles_range(
                coin=asset,
                interval=interval,
                start_time=lookback_start,
                end_time=end_date,
            )
            for asset in assets
        ]

        # Fetch funding rates for all assets concurrently
        funding_tasks = [
            self.data_manager.fetch_funding_rates_range(
                coin=asset,
                start_time=lookback_start,
                end_time=end_date,
            )
            for asset in assets
        ]

        # Execute all fetches concurrently with progress bar
        logger.info(f"Fetching data for {len(assets)} assets...")

        with tqdm(total=len(assets) * 2, desc="Fetching data", unit="asset") as pbar:  # type: ignore[misc]
            # Fetch candles
            candle_results = []
            for task in asyncio.as_completed(candle_tasks):
                result = await task
                candle_results.append(result)
                pbar.update(1)

            # Fetch funding rates
            funding_results = []
            for task in asyncio.as_completed(funding_tasks):
                result = await task
                funding_results.append(result)
                pbar.update(1)

        # Build cache structure
        candles_dict = dict(zip(assets, candle_results, strict=True))
        funding_dict = dict(zip(assets, funding_results, strict=True))

        # Order books not available for historical backtesting
        order_books_dict = {asset: {} for asset in assets}

        return HistoricalDataCache(
            candles=candles_dict,
            funding_rates=funding_dict,
            order_books=order_books_dict,
        )

    def _interval_to_timedelta(self, interval: str) -> timedelta:
        """Convert interval string to timedelta.

        Args:
            interval: Interval string (e.g., "1h", "4h", "1d")

        Returns:
            Timedelta for the interval

        Raises:
            ValueError: If interval is invalid
        """
        interval_map = {
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }

        if interval not in interval_map:
            raise ValueError(
                f"Invalid interval: {interval}. "
                f"Supported intervals: {', '.join(interval_map.keys())}"
            )

        return interval_map[interval]
