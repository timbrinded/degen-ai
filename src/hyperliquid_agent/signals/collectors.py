"""Signal collectors for different time scales."""

import asyncio
import logging
import time
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
        micro_pnl = sum(p.unrealized_pnl for p in account_state.positions)

        # Track API latency
        api_start_time = time.time()

        # Collect order books for all positions concurrently
        tasks = [
            self.hyperliquid_provider.fetch_order_book(pos.coin) for pos in account_state.positions
        ]

        order_book_responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Measure API latency
        api_latency_ms = (time.time() - api_start_time) * 1000

        # Process order book data
        successful_fetches = 0
        total_confidence = 0.0

        for pos, ob_response in zip(account_state.positions, order_book_responses, strict=True):
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
        short_term_vol = await self._calculate_short_term_volatility(account_state.positions)

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
        open_interest_change_24h: dict[str, float] = {}
        oi_to_volume_ratio: dict[str, float] = {}
        technical_indicators: dict[str, TechnicalIndicators | None] = {}

        total_value = account_state.portfolio_value

        # Initialize tracking variables
        successful_fetches = 0
        total_confidence = 0.0
        funding_responses: Any = []
        oi_responses: Any = []
        candles_responses: Any = []

        # Collect data for all positions concurrently
        if account_state.positions:
            # Create concurrent tasks for each position
            funding_tasks = []
            oi_tasks = []
            candles_tasks = []

            for position in account_state.positions:
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

            for i, position in enumerate(account_state.positions):  # type: ignore[assignment]
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

                    # Calculate 24h OI change (would need historical OI data)
                    # For now, use placeholder - in production, fetch historical OI
                    open_interest_change_24h[coin] = 0.0

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
                    open_interest_change_24h[coin] = 0.0
                    oi_to_volume_ratio[coin] = 0.0

                # Process candles for technical indicators
                candles_response = candles_responses[i]
                if not isinstance(candles_response, BaseException):
                    candles = candles_response.data
                    if candles and len(candles) >= 50:
                        try:
                            # Calculate technical indicators using ComputedSignalProcessor
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

        # Calculate realized volatility and trend using the largest position
        realized_vol_1h, realized_vol_24h, trend_score = await self._calculate_volatility_and_trend(
            account_state.positions
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
            ),
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
    """Collects slow-loop signals for regime detection and macro analysis."""

    def collect(self, account_state: AccountState) -> SlowLoopSignals:
        """Collect slow-loop signals.

        Args:
            account_state: Current account state

        Returns:
            SlowLoopSignals with macro-level market data
        """
        macro_events_upcoming = []
        cross_asset_risk_on_score = self._calculate_risk_on_score()
        venue_health_score = self._assess_venue_health()
        liquidity_regime = self._assess_liquidity_regime(account_state.positions)

        return SlowLoopSignals(
            macro_events_upcoming=macro_events_upcoming,
            cross_asset_risk_on_score=cross_asset_risk_on_score,
            venue_health_score=venue_health_score,
            liquidity_regime=liquidity_regime,
        )

    def _calculate_risk_on_score(self) -> float:
        """Calculate cross-asset risk-on score using BTC funding as proxy.

        Returns:
            Risk-on score from -1 to +1
        """
        try:
            start_time, end_time = self._get_timestamp_range(hours_back=168)  # 7 days
            btc_funding = self.info.funding_history("BTC", start_time, end_time)
            if btc_funding:
                rates = [float(f.get("fundingRate", 0)) for f in btc_funding]
                avg_funding = sum(rates) / len(rates) if rates else 0.0

                # Positive funding = longs paying shorts = risk-on
                # Normalize to -1 to +1 scale (typical funding is -0.01% to +0.01%)
                return max(-1.0, min(1.0, avg_funding * 10000))
        except Exception:
            pass

        return 0.0

    def _assess_venue_health(self) -> float:
        """Assess venue health via API responsiveness.

        Returns:
            Health score from 0 to 1
        """
        try:
            meta = self.info.meta()
            return 1.0 if meta and "universe" in meta else 0.5
        except Exception:
            return 0.3  # Degraded health

    def _assess_liquidity_regime(
        self, positions: list[Position]
    ) -> Literal["high", "medium", "low"]:
        """Assess liquidity regime from order book depth.

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

            l2_data = self.info.l2_snapshot(largest_position.coin)
            levels = l2_data.get("levels", [[[], []]])

            if levels and len(levels[0]) == 2:
                bids = levels[0][0]
                asks = levels[0][1]

                # Calculate total depth within 1% of mid
                if bids and asks:
                    mid_price = (float(bids[0][0]) + float(asks[0][0])) / 2
                    threshold = mid_price * 0.01

                    bid_depth = sum(
                        float(b[1]) for b in bids if abs(float(b[0]) - mid_price) <= threshold
                    )
                    ask_depth = sum(
                        float(a[1]) for a in asks if abs(float(a[0]) - mid_price) <= threshold
                    )
                    total_depth = bid_depth + ask_depth

                    # Classify liquidity based on depth
                    # These thresholds would be calibrated per asset
                    if total_depth > 100:
                        return "high"
                    if total_depth > 20:
                        return "medium"
                    return "low"
        except Exception:
            pass

        return "medium"
