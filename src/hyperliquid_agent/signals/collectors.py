"""Signal collectors for different time scales."""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from typing import Any, Literal

from hyperliquid.info import Info

from hyperliquid_agent.monitor import AccountState, Position
from hyperliquid_agent.signals.calculations import (
    calculate_realized_volatility,
    calculate_sma,
    calculate_spread_bps,
    calculate_trend_score,
)
from hyperliquid_agent.signals.hyperliquid_provider import HyperliquidProvider
from hyperliquid_agent.signals.models import (
    FastLoopSignals,
    MediumLoopSignals,
    SignalQualityMetadata,
    SlowLoopSignals,
)
from hyperliquid_agent.signals.processor import ComputedSignalProcessor, TechnicalIndicators

logger = logging.getLogger(__name__)


class PriceHistory:
    """Maintains rolling buffer of historical price data for multi-timeframe analysis.

    Stores 90 days of 4-hour candles (540 data points) to enable accurate calculation
    of 1d, 7d, 30d, and 90d returns, as well as market structure detection.
    """

    def __init__(self, lookback_days: int = 90):
        """Initialize price history with specified lookback period.

        Args:
            lookback_days: Number of days to maintain in history (default 90)
        """
        # 4-hour candles: 6 per day * lookback_days
        max_len = lookback_days * 6
        self.closes: deque[float] = deque(maxlen=max_len)
        self.highs: deque[float] = deque(maxlen=max_len)
        self.lows: deque[float] = deque(maxlen=max_len)
        self.timestamps: deque[datetime] = deque(maxlen=max_len)
        self.lookback_days = lookback_days

    def add_candle(self, close: float, high: float, low: float, timestamp: datetime):
        """Add new price data point to history.

        Args:
            close: Closing price
            high: High price
            low: Low price
            timestamp: Candle timestamp
        """
        self.closes.append(close)
        self.highs.append(high)
        self.lows.append(low)
        self.timestamps.append(timestamp)

    def calculate_returns(self) -> dict[str, float] | None:
        """Calculate multi-timeframe returns from historical price data.

        Returns:
            Dictionary with keys: return_1d, return_7d, return_30d, return_90d
            Returns None if insufficient data available
        """
        if len(self.closes) < 7:  # Need at least 1 day of data (6 candles)
            return None

        current_price = self.closes[-1]

        # Calculate returns for each timeframe
        # 1d = 6 candles ago (6 * 4h = 24h)
        # 7d = 42 candles ago (42 * 4h = 168h = 7d)
        # 30d = 180 candles ago (180 * 4h = 720h = 30d)
        # 90d = 540 candles ago (540 * 4h = 2160h = 90d)

        returns = {}

        # 1-day return
        if len(self.closes) >= 7:
            price_1d_ago = self.closes[-7]
            if price_1d_ago > 0:
                returns["return_1d"] = ((current_price - price_1d_ago) / price_1d_ago) * 100
            else:
                returns["return_1d"] = 0.0
        else:
            returns["return_1d"] = 0.0

        # 7-day return
        if len(self.closes) >= 43:
            price_7d_ago = self.closes[-43]
            if price_7d_ago > 0:
                returns["return_7d"] = ((current_price - price_7d_ago) / price_7d_ago) * 100
            else:
                returns["return_7d"] = 0.0
        else:
            returns["return_7d"] = 0.0

        # 30-day return
        if len(self.closes) >= 181:
            price_30d_ago = self.closes[-181]
            if price_30d_ago > 0:
                returns["return_30d"] = ((current_price - price_30d_ago) / price_30d_ago) * 100
            else:
                returns["return_30d"] = 0.0
        else:
            returns["return_30d"] = 0.0

        # 90-day return
        if len(self.closes) >= 541:
            price_90d_ago = self.closes[-541]
            if price_90d_ago > 0:
                returns["return_90d"] = ((current_price - price_90d_ago) / price_90d_ago) * 100
            else:
                returns["return_90d"] = 0.0
        else:
            returns["return_90d"] = 0.0

        return returns

    def detect_market_structure(self) -> dict[str, bool]:
        """Detect higher highs and higher lows patterns using peak and trough analysis.

        Analyzes the most recent price action to identify trend structure:
        - Higher highs: Recent peaks are higher than earlier peaks
        - Higher lows: Recent troughs are higher than earlier troughs

        Returns:
            Dictionary with keys: higher_highs, higher_lows
        """
        if len(self.highs) < 50:  # Need sufficient data for pattern detection
            return {"higher_highs": False, "higher_lows": False}

        # Analyze last 50 candles for market structure
        recent_highs = list(self.highs)[-50:]
        recent_lows = list(self.lows)[-50:]

        # Find peaks (local maxima) in highs
        peaks = []
        for i in range(1, len(recent_highs) - 1):
            if recent_highs[i] > recent_highs[i - 1] and recent_highs[i] > recent_highs[i + 1]:
                peaks.append(recent_highs[i])

        # Find troughs (local minima) in lows
        troughs = []
        for i in range(1, len(recent_lows) - 1):
            if recent_lows[i] < recent_lows[i - 1] and recent_lows[i] < recent_lows[i + 1]:
                troughs.append(recent_lows[i])

        # Determine higher highs: compare recent peaks to earlier peaks
        higher_highs = False
        if len(peaks) >= 2:
            # Compare last peak to previous peak
            higher_highs = peaks[-1] > peaks[-2]

        # Determine higher lows: compare recent troughs to earlier troughs
        higher_lows = False
        if len(troughs) >= 2:
            # Compare last trough to previous trough
            higher_lows = troughs[-1] > troughs[-2]

        return {"higher_highs": higher_highs, "higher_lows": higher_lows}

    def get_data_quality(self) -> str:
        """Assess data quality based on available history.

        Returns:
            "complete" if 90d of data, "partial" if 7-90d, "insufficient" if <7d
        """
        num_candles = len(self.closes)

        if num_candles >= 540:  # 90 days
            return "complete"
        elif num_candles >= 42:  # 7 days
            return "partial"
        else:
            return "insufficient"

    def get_oldest_data_point(self) -> datetime | None:
        """Get timestamp of oldest data point in history.

        Returns:
            Oldest timestamp or None if no data
        """
        if len(self.timestamps) > 0:
            return self.timestamps[0]
        return None


class OpenInterestHistory:
    """Track historical open interest for change calculations.

    Maintains a rolling buffer of open interest values with timestamps to enable
    accurate 24-hour change calculations.
    """

    def __init__(self, lookback_hours: int = 24):
        """Initialize open interest history with specified lookback period.

        Args:
            lookback_hours: Number of hours to maintain in history (default 24)
        """
        # 4-hour candles: lookback_hours / 4 + 1 for accurate 24h lookback
        max_len = (lookback_hours // 4) + 1
        self.values: deque[float] = deque(maxlen=max_len)
        self.timestamps: deque[datetime] = deque(maxlen=max_len)
        self.lookback_hours = lookback_hours

    def add_value(self, oi: float, timestamp: datetime):
        """Add new OI data point to history.

        Args:
            oi: Open interest value
            timestamp: Data point timestamp
        """
        self.values.append(oi)
        self.timestamps.append(timestamp)

    def calculate_24h_change(self) -> float | None:
        """Calculate 24-hour OI change percentage.

        Returns:
            Percentage change from 24h ago to current, or None if insufficient data
        """
        if len(self.values) < 7:  # Need at least 24h of data (6 * 4h candles + current)
            return None

        current_oi = self.values[-1]
        oi_24h_ago = self.values[0]

        if oi_24h_ago == 0:
            return None

        change_pct = ((current_oi - oi_24h_ago) / abs(oi_24h_ago)) * 100
        return change_pct


class SignalCollectorBase:
    """Base class for signal collectors."""

    def __init__(self, info: Info):
        """Initialize signal collector.

        Args:
            info: Hyperliquid Info API client
        """
        self.info = info

    def _get_timestamp_range(self, hours_back: float) -> tuple[int, int]:
        """Get timestamp range for API calls.

        Args:
            hours_back: Number of hours to look back (can be fractional)

        Returns:
            Tuple of (start_time_ms, end_time_ms)
        """
        end_time = int(time.time() * 1000)
        start_time = int(end_time - (hours_back * 3600 * 1000))
        return start_time, end_time


class FastSignalCollector(SignalCollectorBase):
    """Collects fast-loop signals for execution-level decisions using async providers."""

    def __init__(
        self,
        info: Info,
        hyperliquid_provider: HyperliquidProvider,
        computed_processor: ComputedSignalProcessor,
    ):
        """Initialize fast signal collector with async providers.

        Args:
            info: Hyperliquid Info API client (for backward compatibility)
            hyperliquid_provider: Async Hyperliquid data provider
            computed_processor: Computed signal processor
        """
        super().__init__(info)
        self.hyperliquid_provider = hyperliquid_provider
        self.computed_processor = computed_processor

    async def collect(self, account_state: AccountState) -> FastLoopSignals:
        """Collect fast-loop signals asynchronously with concurrent order book fetching.

        Args:
            account_state: Current account state

        Returns:
            FastLoopSignals with current execution-level market data and quality metadata
        """
        spreads = {}
        slippage_estimates = {}
        partial_fill_rates = {}
        order_book_depth = {}

        # Only request market data for perpetual positions; spot balances share the AccountState
        perp_positions = [p for p in account_state.positions if p.market_type == "perp"]
        micro_pnl = sum(p.unrealized_pnl for p in perp_positions)

        if not perp_positions:
            metadata = SignalQualityMetadata(
                timestamp=datetime.now(),
                confidence=0.0,
                staleness_seconds=0.0,
                sources=["hyperliquid"],
                is_cached=False,
            )

            return FastLoopSignals(
                spreads=spreads,
                slippage_estimates=slippage_estimates,
                short_term_volatility=0.0,
                micro_pnl=micro_pnl,
                partial_fill_rates=partial_fill_rates,
                order_book_depth=order_book_depth,
                api_latency_ms=0.0,
                metadata=metadata,
            )

        # Track API latency for perp positions only
        api_start_time = time.time()

        # Collect order books for perpetual positions concurrently
        tasks = [self.hyperliquid_provider.fetch_order_book(pos.coin) for pos in perp_positions]

        order_book_responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Measure API latency
        api_latency_ms = (time.time() - api_start_time) * 1000

        # Process order book data
        successful_fetches = 0
        total_confidence = 0.0

        for pos, ob_response in zip(perp_positions, order_book_responses, strict=True):
            coin = pos.coin

            if isinstance(ob_response, BaseException):
                # Fallback to conservative estimates on API failure
                spreads[coin] = 15.0
                slippage_estimates[coin] = 7.5
                order_book_depth[coin] = 0.0
                partial_fill_rates[coin] = 0.95
                continue

            # Extract order book data (ob_response is ProviderResponse here)
            ob_data = ob_response.data
            successful_fetches += 1
            total_confidence += ob_response.confidence

            # Calculate spread in bps
            if ob_data.bids and ob_data.asks:
                best_bid = ob_data.bids[0][0]
                best_ask = ob_data.asks[0][0]
                mid_price = (best_bid + best_ask) / 2

                spread_bps = calculate_spread_bps(best_bid, best_ask)
                spreads[coin] = spread_bps

                # Calculate order book depth within 1% of mid-price
                threshold = mid_price * 0.01
                bid_depth = sum(
                    size for price, size in ob_data.bids if abs(price - mid_price) <= threshold
                )
                ask_depth = sum(
                    size for price, size in ob_data.asks if abs(price - mid_price) <= threshold
                )
                total_depth = bid_depth + ask_depth
                order_book_depth[coin] = total_depth

                # Estimate slippage based on order book depth analysis
                # More sophisticated: consider depth relative to typical order size
                if total_depth > 100:
                    # High liquidity - low slippage
                    slippage_estimates[coin] = spread_bps * 0.3
                elif total_depth > 20:
                    # Medium liquidity
                    slippage_estimates[coin] = spread_bps * 0.5
                else:
                    # Low liquidity - higher slippage
                    slippage_estimates[coin] = spread_bps * 0.8
            else:
                spreads[coin] = 10.0
                slippage_estimates[coin] = 5.0
                order_book_depth[coin] = 0.0

            # Partial fill rates - assume high fill rate for liquid markets
            partial_fill_rates[coin] = 0.95

        # Calculate short-term volatility from recent price changes
        short_term_vol = await self._calculate_short_term_volatility(perp_positions)

        # Build quality metadata
        avg_confidence = total_confidence / successful_fetches if successful_fetches > 0 else 0.0
        metadata = SignalQualityMetadata(
            timestamp=datetime.now(),
            confidence=avg_confidence,
            staleness_seconds=0.0,
            sources=["hyperliquid"],
            is_cached=any(
                not isinstance(r, BaseException) and r.is_cached for r in order_book_responses
            ),
        )

        return FastLoopSignals(
            spreads=spreads,
            slippage_estimates=slippage_estimates,
            short_term_volatility=short_term_vol,
            micro_pnl=micro_pnl,
            partial_fill_rates=partial_fill_rates,
            order_book_depth=order_book_depth,
            api_latency_ms=api_latency_ms,
            metadata=metadata,
        )

    async def _calculate_short_term_volatility(self, positions: list[Position]) -> float:
        """Calculate short-term volatility from largest position using async provider.

        Args:
            positions: List of current positions

        Returns:
            Short-term volatility measure
        """
        if not positions:
            return 0.0

        # Use the largest position as proxy for portfolio volatility
        largest_position = max(
            positions,
            key=lambda p: abs(p.size * p.current_price),
            default=None,
        )

        if not largest_position:
            return 0.0

        try:
            # Get recent 1-minute candles for volatility (last 15 minutes)
            start_time, end_time = self._get_timestamp_range(hours_back=0.25)
            candles_response = await self.hyperliquid_provider.fetch_candles(
                largest_position.coin, "1m", start_time, end_time
            )

            candles = candles_response.data
            if candles and len(candles) > 1:
                # Convert to dict format expected by calculate_realized_volatility
                candles_dict = [
                    {
                        "t": int(c.timestamp.timestamp() * 1000),
                        "o": c.open,
                        "h": c.high,
                        "l": c.low,
                        "c": c.close,
                        "v": c.volume,
                    }
                    for c in candles
                ]
                return calculate_realized_volatility(candles_dict)
        except Exception:
            pass

        return 0.0


class MediumSignalCollector(SignalCollectorBase):
    """Collects medium-loop signals for tactical planning using async providers."""

    def __init__(
        self,
        info: Info,
        hyperliquid_provider: HyperliquidProvider,
        computed_processor: ComputedSignalProcessor,
    ):
        """Initialize medium signal collector with async providers.

        Args:
            info: Hyperliquid Info API client (for backward compatibility)
            hyperliquid_provider: Async Hyperliquid data provider
            computed_processor: Computed signal processor
        """
        super().__init__(info)
        self.hyperliquid_provider = hyperliquid_provider
        self.computed_processor = computed_processor
        # Price history tracking for each coin
        self.price_history: dict[str, PriceHistory] = {}
        # Open interest history tracking for each coin
        self.oi_history: dict[str, OpenInterestHistory] = {}

    async def collect(self, account_state: AccountState) -> MediumLoopSignals:
        """Collect medium-loop signals asynchronously with concurrent data fetching.

        Args:
            account_state: Current account state

        Returns:
            MediumLoopSignals with tactical-level market data and quality metadata
        """
        funding_basis: dict[str, float] = {}
        perp_spot_basis: dict[str, float] = {}
        concentration_ratios: dict[str, float] = {}
        drift_from_targets: dict[str, float] = {}
        funding_rate_trend: dict[str, Literal["increasing", "decreasing", "stable"]] = {}
        open_interest_change_24h: dict[str, float | None] = {}
        oi_to_volume_ratio: dict[str, float] = {}
        technical_indicators: dict[str, TechnicalIndicators | None] = {}

        total_value = account_state.portfolio_value

        # Focus medium-loop analytics on perpetual markets; spot balances lack required data
        perp_positions = [p for p in account_state.positions if p.market_type == "perp"]

        if not perp_positions:
            metadata = SignalQualityMetadata(
                timestamp=datetime.now(),
                confidence=0.0,
                staleness_seconds=0.0,
                sources=["hyperliquid"],
                is_cached=False,
            )

            return MediumLoopSignals(
                realized_vol_1h=0.0,
                realized_vol_24h=0.0,
                trend_score=0.0,
                funding_basis=funding_basis,
                perp_spot_basis=perp_spot_basis,
                concentration_ratios=concentration_ratios,
                drift_from_targets=drift_from_targets,
                technical_indicators=technical_indicators,
                open_interest_change_24h=open_interest_change_24h,
                oi_to_volume_ratio=oi_to_volume_ratio,
                funding_rate_trend={},
                metadata=metadata,
            )

        # Initialize tracking variables
        successful_fetches = 0
        total_confidence = 0.0
        funding_responses: Any = []
        oi_responses: Any = []
        candles_responses: Any = []

        # Collect data for all positions concurrently
        if perp_positions:
            # Create concurrent tasks for each position
            funding_tasks = []
            oi_tasks = []
            candles_tasks = []

            for position in perp_positions:
                coin = position.coin

                # Funding rate history (last 24 hours)
                start_time, end_time = self._get_timestamp_range(hours_back=24)
                funding_tasks.append(
                    self.hyperliquid_provider.fetch_funding_history(coin, start_time, end_time)
                )

                # Open interest data
                oi_tasks.append(self.hyperliquid_provider.fetch_open_interest(coin))

                # Candles for technical indicators (last 7 days of 1h candles)
                start_time_candles, end_time_candles = self._get_timestamp_range(hours_back=168)
                candles_tasks.append(
                    self.hyperliquid_provider.fetch_candles(
                        coin, "1h", start_time_candles, end_time_candles
                    )
                )

            # Execute all tasks concurrently
            funding_responses = await asyncio.gather(*funding_tasks, return_exceptions=True)
            oi_responses = await asyncio.gather(*oi_tasks, return_exceptions=True)
            candles_responses = await asyncio.gather(*candles_tasks, return_exceptions=True)

            for i, position in enumerate(perp_positions):  # type: ignore[assignment]
                coin = position.coin

                # Calculate concentration
                position_value = abs(position.size * position.current_price)
                concentration_ratios[coin] = (
                    position_value / total_value if total_value > 0 else 0.0
                )

                # Drift from targets (would need target allocations from active plan)
                drift_from_targets[coin] = 0.0

                # Perp-spot basis (not directly available on Hyperliquid)
                perp_spot_basis[coin] = 0.0

                # Process funding rate data
                funding_response = funding_responses[i]
                if not isinstance(funding_response, BaseException):
                    funding_rates = funding_response.data
                    if funding_rates:
                        # Calculate average funding rate
                        rates = [fr.rate for fr in funding_rates]
                        avg_funding = sum(rates) / len(rates) if rates else 0.0
                        funding_basis[coin] = avg_funding * 100  # Convert to percentage

                        # Calculate funding rate trend
                        funding_rate_trend[coin] = self._calculate_funding_trend(rates)

                        successful_fetches += 1
                        total_confidence += funding_response.confidence
                    else:
                        funding_basis[coin] = 0.0
                        funding_rate_trend[coin] = "stable"
                else:
                    funding_basis[coin] = 0.0
                    funding_rate_trend[coin] = "stable"

                # Process open interest data
                oi_response = oi_responses[i]
                if not isinstance(oi_response, BaseException):
                    oi_data = oi_response.data

                    # Update OI history for this coin
                    if coin not in self.oi_history:
                        self.oi_history[coin] = OpenInterestHistory()

                    # Use actual data timestamp instead of datetime.now() to prevent drift
                    self.oi_history[coin].add_value(oi_data.open_interest, oi_data.timestamp)

                    # Calculate 24h OI change from historical data
                    # Preserve None to indicate insufficient data for transparency
                    oi_change = self.oi_history[coin].calculate_24h_change()
                    open_interest_change_24h[coin] = oi_change

                    # Calculate OI-to-volume ratio
                    # Fetch 24h volume from candles
                    candles_response = candles_responses[i]
                    if not isinstance(candles_response, BaseException):
                        candles = candles_response.data
                        if candles:
                            # Sum volume from last 24 candles (24 hours)
                            volume_24h = sum(c.volume for c in candles[-24:])
                            if volume_24h > 0:
                                oi_to_volume_ratio[coin] = oi_data.open_interest / volume_24h
                            else:
                                oi_to_volume_ratio[coin] = 0.0
                        else:
                            oi_to_volume_ratio[coin] = 0.0
                    else:
                        oi_to_volume_ratio[coin] = 0.0

                    successful_fetches += 1
                    total_confidence += oi_response.confidence
                else:
                    open_interest_change_24h[coin] = None
                    oi_to_volume_ratio[coin] = 0.0

                # Process candles for technical indicators and price history
                candles_response = candles_responses[i]
                if not isinstance(candles_response, BaseException):
                    candles = candles_response.data
                    if candles:
                        if coin not in self.price_history:
                            self.price_history[coin] = PriceHistory()

                        history = self.price_history[coin]
                        last_timestamp = history.timestamps[-1] if history.timestamps else None

                        for candle in candles:
                            if last_timestamp and candle.timestamp <= last_timestamp:
                                continue

                            history.add_candle(
                                close=candle.close,
                                high=candle.high,
                                low=candle.low,
                                timestamp=candle.timestamp,
                            )
                            last_timestamp = candle.timestamp

                        if len(candles) >= 50:
                            try:
                                indicators = (
                                    await self.computed_processor.calculate_technical_indicators(
                                        candles
                                    )
                                )
                                technical_indicators[coin] = indicators

                                successful_fetches += 1
                                total_confidence += candles_response.confidence
                            except Exception as e:
                                logger.warning(
                                    f"Failed to calculate technical indicators for {coin}: {e}"
                                )
                                technical_indicators[coin] = None
                        else:
                            technical_indicators[coin] = None
                    else:
                        technical_indicators[coin] = None
                else:
                    technical_indicators[coin] = None

        # Calculate realized volatility and trend using the largest position
        realized_vol_1h, realized_vol_24h, trend_score = await self._calculate_volatility_and_trend(
            perp_positions
        )

        # Build quality metadata
        avg_confidence = total_confidence / successful_fetches if successful_fetches > 0 else 0.0
        metadata = SignalQualityMetadata(
            timestamp=datetime.now(),
            confidence=avg_confidence,
            staleness_seconds=0.0,
            sources=["hyperliquid"],
            is_cached=any(
                not isinstance(r, BaseException) and r.is_cached
                for responses in [funding_responses, oi_responses, candles_responses]
                for r in responses
            )
            if perp_positions
            else False,
        )

        # Type cast for funding_rate_trend to satisfy type checker
        funding_rate_trend_typed: dict[str, Literal["increasing", "decreasing", "stable"]] = (
            funding_rate_trend  # type: ignore[assignment]
        )

        return MediumLoopSignals(
            realized_vol_1h=realized_vol_1h,
            realized_vol_24h=realized_vol_24h,
            trend_score=trend_score,
            funding_basis=funding_basis,
            perp_spot_basis=perp_spot_basis,
            concentration_ratios=concentration_ratios,
            drift_from_targets=drift_from_targets,
            technical_indicators=technical_indicators,
            open_interest_change_24h=open_interest_change_24h,
            oi_to_volume_ratio=oi_to_volume_ratio,
            funding_rate_trend=funding_rate_trend_typed,
            metadata=metadata,
        )

    def _calculate_funding_trend(
        self, rates: list[float]
    ) -> Literal["increasing", "decreasing", "stable"]:
        """Calculate funding rate trend from historical rates.

        Args:
            rates: List of funding rates (oldest to newest)

        Returns:
            Trend classification: "increasing", "decreasing", or "stable"
        """
        if len(rates) < 3:
            return "stable"

        # Split into first half and second half
        mid = len(rates) // 2
        first_half_avg = sum(rates[:mid]) / mid if mid > 0 else 0.0
        second_half_avg = sum(rates[mid:]) / (len(rates) - mid) if (len(rates) - mid) > 0 else 0.0

        # Calculate percentage change
        if abs(first_half_avg) < 1e-10:  # Avoid division by zero
            return "stable"

        pct_change = (second_half_avg - first_half_avg) / abs(first_half_avg)

        # Classify trend based on threshold (10% change)
        if pct_change > 0.1:
            return "increasing"
        if pct_change < -0.1:
            return "decreasing"
        return "stable"

    def get_price_history(self, coin: str) -> PriceHistory | None:
        """Get price history for a specific coin.

        Args:
            coin: Coin symbol

        Returns:
            PriceHistory object or None if not available
        """
        return self.price_history.get(coin)

    def get_oi_history(self, coin: str) -> OpenInterestHistory | None:
        """Get open interest history for a specific coin.

        Args:
            coin: Coin symbol

        Returns:
            OpenInterestHistory object or None if not available
        """
        return self.oi_history.get(coin)

    async def _calculate_volatility_and_trend(
        self, positions: list[Position]
    ) -> tuple[float, float, float]:
        """Calculate volatility and trend metrics from largest position using async provider.

        Args:
            positions: List of current positions

        Returns:
            Tuple of (realized_vol_1h, realized_vol_24h, trend_score)
        """
        if not positions:
            return 0.0, 0.0, 0.0

        largest_position = max(
            positions,
            key=lambda p: abs(p.size * p.current_price),
        )

        realized_vol_1h = 0.0
        realized_vol_24h = 0.0
        trend_score = 0.0

        try:
            # Fetch candles concurrently
            start_time_1h, end_time_1h = self._get_timestamp_range(hours_back=24)
            start_time_24h, end_time_24h = self._get_timestamp_range(hours_back=168)

            candles_1h_task = self.hyperliquid_provider.fetch_candles(
                largest_position.coin, "1h", start_time_1h, end_time_1h
            )
            candles_24h_task = self.hyperliquid_provider.fetch_candles(
                largest_position.coin, "1h", start_time_24h, end_time_24h
            )

            candles_1h_response, candles_24h_response = await asyncio.gather(
                candles_1h_task, candles_24h_task, return_exceptions=True
            )

            # Process 1-hour volatility
            if not isinstance(candles_1h_response, BaseException):
                candles_1h = candles_1h_response.data
                if candles_1h and len(candles_1h) > 1:
                    # Convert to dict format expected by calculate_realized_volatility
                    candles_dict = [
                        {
                            "t": int(c.timestamp.timestamp() * 1000),
                            "o": c.open,
                            "h": c.high,
                            "l": c.low,
                            "c": c.close,
                            "v": c.volume,
                        }
                        for c in candles_1h
                    ]
                    realized_vol_1h = calculate_realized_volatility(candles_dict)

            # Process 24-hour volatility and trend
            if not isinstance(candles_24h_response, BaseException):
                candles_24h = candles_24h_response.data
                if candles_24h and len(candles_24h) > 1:
                    # Convert to dict format for volatility calculation
                    candles_dict = [
                        {
                            "t": int(c.timestamp.timestamp() * 1000),
                            "o": c.open,
                            "h": c.high,
                            "l": c.low,
                            "c": c.close,
                            "v": c.volume,
                        }
                        for c in candles_24h
                    ]
                    realized_vol_24h = calculate_realized_volatility(candles_dict)

                    # Calculate trend score using SMA crossover
                    if len(candles_24h) >= 50:
                        closes = [c.close for c in candles_24h]
                        sma_20 = calculate_sma(closes, 20)
                        sma_50 = calculate_sma(closes, 50)
                        current_price = closes[-1]
                        trend_score = calculate_trend_score(current_price, sma_20, sma_50)

        except Exception as e:
            logger.warning(f"Error calculating volatility and trend: {e}")

        return realized_vol_1h, realized_vol_24h, trend_score


class SlowSignalCollector(SignalCollectorBase):
    """Collects slow-loop signals for regime detection and macro analysis using async providers."""

    def __init__(
        self,
        info: Info,
        hyperliquid_provider: HyperliquidProvider,
        onchain_provider: Any,  # OnChainProvider
        external_market_provider: Any,  # ExternalMarketProvider
        sentiment_provider: Any,  # SentimentProvider
        computed_processor: ComputedSignalProcessor,
    ):
        """Initialize slow signal collector with async providers.

        Args:
            info: Hyperliquid Info API client (for backward compatibility)
            hyperliquid_provider: Async Hyperliquid data provider
            onchain_provider: Async on-chain data provider
            external_market_provider: Async external market data provider
            sentiment_provider: Async sentiment data provider
            computed_processor: Computed signal processor
        """
        super().__init__(info)
        self.hyperliquid_provider = hyperliquid_provider
        self.onchain_provider = onchain_provider
        self.external_market_provider = external_market_provider
        self.sentiment_provider = sentiment_provider
        self.computed_processor = computed_processor

    async def collect(self, account_state: AccountState) -> SlowLoopSignals:
        """Collect slow-loop signals asynchronously with concurrent provider calls.

        Args:
            account_state: Current account state

        Returns:
            SlowLoopSignals with macro-level market data and quality metadata
        """
        # Track successful fetches for confidence calculation
        successful_fetches = 0
        total_confidence = 0.0
        sources = ["hyperliquid"]

        # Fetch macro events
        macro_events_task = self._fetch_macro_events()
        btc_eth_corr_task = self._fetch_btc_eth_correlation()
        btc_spx_corr_task = self._fetch_btc_spx_correlation()
        fear_greed_task = self._fetch_fear_greed_index()
        token_unlocks_task = self._fetch_token_unlocks(account_state.positions)
        whale_flows_task = self._fetch_whale_flows(account_state.positions)
        venue_health_task = self._assess_venue_health_async()
        liquidity_regime_task = self._assess_liquidity_regime_async(account_state.positions)

        # Execute all tasks concurrently
        results = await asyncio.gather(  # type: ignore[misc]
            macro_events_task,
            btc_eth_corr_task,
            btc_spx_corr_task,
            fear_greed_task,
            token_unlocks_task,
            whale_flows_task,
            venue_health_task,
            liquidity_regime_task,
            return_exceptions=True,
        )

        # Unpack results with proper type handling
        macro_events: list[Any] = results[0] if not isinstance(results[0], BaseException) else []
        btc_eth_corr: float = results[1] if not isinstance(results[1], BaseException) else 0.0
        btc_spx_corr: float | None = (
            results[2] if not isinstance(results[2], BaseException) else None
        )
        fear_greed: float = results[3] if not isinstance(results[3], BaseException) else 0.0
        token_unlocks: list[Any] = results[4] if not isinstance(results[4], BaseException) else []
        whale_flows: dict[str, float] = (
            results[5] if not isinstance(results[5], BaseException) else {}
        )
        venue_health: float = results[6] if not isinstance(results[6], BaseException) else 0.5
        liquidity_regime: Literal["high", "medium", "low"] = (
            results[7] if not isinstance(results[7], BaseException) else "medium"
        )

        # Calculate cross-asset risk-on score using BTC funding as proxy
        cross_asset_risk_on_score = await self._calculate_risk_on_score()

        # Track sources and confidence
        if not isinstance(results[0], BaseException):
            sources.append("external_market")
            successful_fetches += 1
            total_confidence += 1.0

        if not isinstance(results[3], BaseException):
            sources.append("sentiment")
            successful_fetches += 1
            total_confidence += 1.0

        if not isinstance(results[4], BaseException) or not isinstance(results[5], BaseException):
            sources.append("onchain")
            successful_fetches += 1
            total_confidence += 1.0

        # Build quality metadata
        avg_confidence = total_confidence / successful_fetches if successful_fetches > 0 else 0.5
        metadata = SignalQualityMetadata(
            timestamp=datetime.now(),
            confidence=avg_confidence,
            staleness_seconds=0.0,
            sources=list(set(sources)),
            is_cached=False,
        )

        return SlowLoopSignals(
            macro_events_upcoming=macro_events,
            cross_asset_risk_on_score=cross_asset_risk_on_score,
            venue_health_score=venue_health,
            liquidity_regime=liquidity_regime,
            btc_eth_correlation=btc_eth_corr,
            btc_spx_correlation=btc_spx_corr,
            fear_greed_index=fear_greed,
            token_unlocks_7d=token_unlocks,
            whale_flow_24h=whale_flows,
            metadata=metadata,
        )

    async def _fetch_macro_events(self) -> list[Any]:
        """Fetch upcoming macro economic events.

        Returns:
            List of MacroEvent objects
        """
        try:
            response = await self.external_market_provider.fetch_macro_calendar(days_ahead=7)
            return response.data
        except Exception as e:
            logger.warning(f"Failed to fetch macro events: {e}")
            return []

    async def _fetch_btc_eth_correlation(self) -> float:
        """Calculate BTC-ETH correlation using ComputedSignalProcessor.

        Returns:
            Correlation coefficient from -1.0 to 1.0
        """
        try:
            # Fetch 30 days of price data for BTC and ETH
            response = await self.external_market_provider.fetch_asset_prices(
                assets=["BTC", "ETH"], days_back=30
            )
            price_data = response.data

            if price_data.get("BTC") and price_data.get("ETH"):
                # Calculate correlation matrix
                correlations = await self.computed_processor.calculate_correlation_matrix(
                    price_data
                )
                return correlations.get(("BTC", "ETH"), 0.0)
        except Exception as e:
            logger.warning(f"Failed to calculate BTC-ETH correlation: {e}")

        return 0.0

    async def _fetch_btc_spx_correlation(self) -> float | None:
        """Calculate BTC-SPX correlation with optional external data.

        Returns:
            Correlation coefficient from -1.0 to 1.0, or None if data unavailable
        """
        try:
            # Fetch 30 days of price data for BTC and SPX
            response = await self.external_market_provider.fetch_asset_prices(
                assets=["BTC", "SPX"], days_back=30
            )
            price_data = response.data

            if price_data.get("BTC") and price_data.get("SPX"):
                # Calculate correlation matrix
                correlations = await self.computed_processor.calculate_correlation_matrix(
                    price_data
                )
                return correlations.get(("BTC", "SPX"), 0.0)
        except Exception as e:
            logger.warning(f"Failed to calculate BTC-SPX correlation: {e}")

        return None

    async def _fetch_fear_greed_index(self) -> float:
        """Fetch fear & greed index from SentimentProvider.

        Returns:
            Normalized sentiment score from -1.0 to +1.0
        """
        try:
            response = await self.sentiment_provider.fetch_fear_greed_index()
            return response.data
        except Exception as e:
            logger.warning(f"Failed to fetch fear & greed index: {e}")
            return 0.0

    async def _fetch_token_unlocks(self, positions: list[Position]) -> list[Any]:
        """Fetch token unlock data from OnChainProvider.

        Args:
            positions: List of current positions

        Returns:
            List of UnlockEvent objects
        """
        if not positions:
            return []

        try:
            # Get unique assets from positions
            assets = list({p.coin for p in positions})

            response = await self.onchain_provider.fetch_token_unlocks(assets=assets, days_ahead=7)
            return response.data
        except Exception as e:
            logger.warning(f"Failed to fetch token unlocks: {e}")
            return []

    async def _fetch_whale_flows(self, positions: list[Position]) -> dict[str, float]:
        """Fetch whale flow data from OnChainProvider.

        Args:
            positions: List of current positions

        Returns:
            Dictionary mapping asset -> net flow (24h)
        """
        if not positions:
            return {}

        whale_flows: dict[str, float] = {}

        try:
            # Get unique assets from positions
            assets = list({p.coin for p in positions})

            # Fetch whale flows for each asset concurrently
            tasks = [
                self.onchain_provider.fetch_whale_flows(asset=asset, hours_back=24)
                for asset in assets
            ]

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for asset, response in zip(assets, responses, strict=True):
                if not isinstance(response, BaseException):
                    whale_flows[asset] = response.data.net_flow
                else:
                    whale_flows[asset] = 0.0

        except Exception as e:
            logger.warning(f"Failed to fetch whale flows: {e}")

        return whale_flows

    async def _assess_venue_health_async(self) -> float:
        """Assess venue health based on API response times and status.

        Implements requirement 10.1, 10.2, 10.3, 10.4, 10.5.

        Returns:
            Health score from 0.0 to 1.0
        """
        try:
            # Measure API response time
            start_time = time.time()

            # Make a lightweight API call to test responsiveness
            meta = self.info.meta()

            response_time = time.time() - start_time
            response_time_ms = response_time * 1000

            # Calculate health score based on response time
            # < 1s = 1.0 (excellent)
            # 1-2s = 0.8 (good)
            # 2-5s = 0.5 (degraded)
            # > 5s = 0.3 (poor) - requirement 10.5
            if response_time_ms < 1000:
                health_score = 1.0
            elif response_time_ms < 2000:
                health_score = 0.8
            elif response_time_ms < 5000:
                health_score = 0.5
            else:
                health_score = 0.3

            # Check if meta response is valid
            if not meta or "universe" not in meta:
                health_score *= 0.5  # Reduce score if API response is invalid

            logger.debug(
                f"Venue health: {health_score:.2f} (response time: {response_time_ms:.1f}ms)"
            )

            return health_score

        except Exception as e:
            logger.warning(f"Failed to assess venue health: {e}")
            return 0.3  # Degraded health on error

    async def _assess_liquidity_regime_async(
        self, positions: list[Position]
    ) -> Literal["high", "medium", "low"]:
        """Assess liquidity regime from order book depth using async provider.

        Args:
            positions: List of current positions

        Returns:
            Liquidity regime classification
        """
        if not positions:
            return "medium"

        try:
            # Sample liquidity from largest position
            largest_position = max(
                positions,
                key=lambda p: abs(p.size * p.current_price),
            )

            # Fetch order book using async provider
            ob_response = await self.hyperliquid_provider.fetch_order_book(largest_position.coin)
            ob_data = ob_response.data

            if ob_data.bids and ob_data.asks:
                best_bid = ob_data.bids[0][0]
                best_ask = ob_data.asks[0][0]
                mid_price = (best_bid + best_ask) / 2
                threshold = mid_price * 0.01

                # Calculate total depth within 1% of mid
                bid_depth = sum(
                    size for price, size in ob_data.bids if abs(price - mid_price) <= threshold
                )
                ask_depth = sum(
                    size for price, size in ob_data.asks if abs(price - mid_price) <= threshold
                )
                total_depth = bid_depth + ask_depth

                # Classify liquidity based on depth
                # These thresholds would be calibrated per asset
                if total_depth > 100:
                    return "high"
                if total_depth > 20:
                    return "medium"
                return "low"

        except Exception as e:
            logger.warning(f"Failed to assess liquidity regime: {e}")

        return "medium"

    async def _calculate_risk_on_score(self) -> float:
        """Calculate cross-asset risk-on score using BTC funding as proxy.

        Returns:
            Risk-on score from -1 to +1
        """
        try:
            start_time, end_time = self._get_timestamp_range(hours_back=168)  # 7 days
            funding_response = await self.hyperliquid_provider.fetch_funding_history(
                "BTC", start_time, end_time
            )

            funding_rates = funding_response.data
            if funding_rates:
                rates = [fr.rate for fr in funding_rates]
                avg_funding = sum(rates) / len(rates) if rates else 0.0

                # Positive funding = longs paying shorts = risk-on
                # Normalize to -1 to +1 scale (typical funding is -0.01% to +0.01%)
                return max(-1.0, min(1.0, avg_funding * 10000))
        except Exception as e:
            logger.warning(f"Failed to calculate risk-on score: {e}")

        return 0.0
