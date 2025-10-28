"""Signal reconstructor for transforming historical data into RegimeSignals."""

import logging
import math
from datetime import datetime

from hyperliquid_agent.governance.regime import PriceContext, RegimeSignals
from hyperliquid_agent.signals.hyperliquid_provider import Candle, FundingRate, OrderBookData
from hyperliquid_agent.signals.processor import ComputedSignalProcessor

logger = logging.getLogger(__name__)


class SignalReconstructor:
    """Reconstructs RegimeSignals from historical data.

    Transforms raw historical OHLCV candles, funding rates, and order book data
    into RegimeSignals format required by RegimeDetector. Calculates technical
    indicators, volatility metrics, and order book metrics with confidence scoring
    based on data completeness.
    """

    # Minimum confidence threshold for returning signals
    MIN_CONFIDENCE_THRESHOLD = 0.3

    # Lookback periods for indicators
    SMA_20_PERIOD = 20
    SMA_50_PERIOD = 50
    ADX_PERIOD = 14
    VOLATILITY_HOURS = 24

    def __init__(self, processor: ComputedSignalProcessor):
        """Initialize signal reconstructor.

        Args:
            processor: ComputedSignalProcessor for technical indicator calculations
        """
        self.processor = processor

    async def reconstruct_signals(
        self,
        timestamp: datetime,
        candles: dict[str, list[Candle]],
        funding_rates: dict[str, list[FundingRate]],
        order_books: dict[str, OrderBookData | None],
    ) -> RegimeSignals | None:
        """Reconstruct RegimeSignals for specific timestamp.

        Uses BTC as representative asset for price-based indicators (SMA, ADX).
        Returns None if confidence score < 0.3 due to insufficient data quality.

        Args:
            timestamp: Target timestamp for signal reconstruction
            candles: Per-coin candle history (must include lookback period)
            funding_rates: Per-coin funding rate history
            order_books: Per-coin order book snapshots

        Returns:
            RegimeSignals or None if insufficient data (confidence < 0.3)
        """
        confidence = 1.0
        missing_indicators = []

        # Use BTC as representative asset for price-based indicators
        btc_candles = candles.get("BTC", [])
        if not btc_candles:
            logger.warning(f"No BTC candles available for timestamp {timestamp}")
            return None

        # Filter candles up to timestamp
        btc_candles_filtered = [c for c in btc_candles if c.timestamp <= timestamp]

        # Debug: Log candle availability for early dates
        if len(btc_candles_filtered) < self.SMA_50_PERIOD:
            logger.debug(
                f"Insufficient candles at {timestamp}: "
                f"filtered={len(btc_candles_filtered)}, total_available={len(btc_candles)}, "
                f"need_sma50={self.SMA_50_PERIOD}"
            )

        # Calculate SMA-20
        sma_20 = self._calculate_sma(btc_candles_filtered, self.SMA_20_PERIOD, timestamp)
        if sma_20 == 0.0:
            missing_indicators.append("sma_20")
            confidence *= 0.8

        # Calculate SMA-50
        sma_50 = self._calculate_sma(btc_candles_filtered, self.SMA_50_PERIOD, timestamp)
        if sma_50 == 0.0:
            missing_indicators.append("sma_50")
            confidence *= 0.8

        # Calculate ADX
        adx = self._calculate_adx(btc_candles_filtered, timestamp)
        if adx == 0.0:
            missing_indicators.append("adx")
            confidence *= 0.8

        # Calculate realized volatility (24-hour)
        realized_vol_24h = self._calculate_realized_volatility(
            btc_candles_filtered, self.VOLATILITY_HOURS, timestamp
        )
        if realized_vol_24h == 0.0:
            missing_indicators.append("realized_vol_24h")
            confidence *= 0.8

        # Calculate average funding rate across all assets
        avg_funding_rate = self._calculate_avg_funding_rate(funding_rates, timestamp)
        if avg_funding_rate == 0.0:
            # Check if it's truly missing or just zero
            has_funding_data = any(
                any(fr.timestamp <= timestamp for fr in rates) for rates in funding_rates.values()
            )
            if not has_funding_data:
                missing_indicators.append("avg_funding_rate")
                confidence *= 0.9  # Less critical than price indicators

        # Calculate spread and depth from order books
        bid_ask_spread_bps, order_book_depth = self._calculate_spread_and_depth(order_books)
        if bid_ask_spread_bps == 0.0 and order_book_depth == 0.0:
            missing_indicators.append("order_book_metrics")
            confidence *= 0.9  # Less critical for backtesting

        # Check if confidence is below threshold
        if confidence < self.MIN_CONFIDENCE_THRESHOLD:
            logger.warning(
                f"Insufficient data quality at {timestamp}: confidence={confidence:.2f}, "
                f"missing={missing_indicators}"
            )
            return None

        if missing_indicators:
            logger.debug(
                f"Reconstructed signals with reduced confidence at {timestamp}: "
                f"confidence={confidence:.2f}, missing={missing_indicators}"
            )

        # Extract price context from historical candles
        price_context = self._extract_price_context(btc_candles_filtered, timestamp, sma_20, sma_50)

        return RegimeSignals(
            price_context=price_context,
            price_sma_20=sma_20,
            price_sma_50=sma_50,
            adx=adx,
            realized_vol_24h=realized_vol_24h,
            avg_funding_rate=avg_funding_rate,
            bid_ask_spread_bps=bid_ask_spread_bps,
            order_book_depth=order_book_depth,
        )

    def _extract_price_context(
        self,
        candles: list[Candle],
        timestamp: datetime,
        sma_20: float,
        sma_50: float,
    ) -> PriceContext:
        """Extract price context with multi-timeframe returns from candles.

        Args:
            candles: Filtered candles up to timestamp
            timestamp: Current timestamp
            sma_20: Pre-calculated 20-period SMA
            sma_50: Pre-calculated 50-period SMA

        Returns:
            PriceContext with current price and returns
        """
        from datetime import timedelta

        # Get current price from latest candle
        current_price = candles[-1].close if candles else 0.0

        # Helper to find price N days ago
        def get_price_n_days_ago(days: int) -> float:
            target_time = timestamp - timedelta(days=days)
            # Find closest candle before or at target_time
            for candle in reversed(candles):
                if candle.timestamp <= target_time:
                    return candle.close
            # If not found, use earliest available price
            return candles[0].close if candles else current_price

        # Calculate multi-timeframe returns
        price_1d_ago = get_price_n_days_ago(1)
        price_7d_ago = get_price_n_days_ago(7)
        price_30d_ago = get_price_n_days_ago(30)
        price_90d_ago = get_price_n_days_ago(90)

        return_1d = (
            ((current_price - price_1d_ago) / price_1d_ago * 100) if price_1d_ago > 0 else 0.0
        )
        return_7d = (
            ((current_price - price_7d_ago) / price_7d_ago * 100) if price_7d_ago > 0 else 0.0
        )
        return_30d = (
            ((current_price - price_30d_ago) / price_30d_ago * 100) if price_30d_ago > 0 else 0.0
        )
        return_90d = (
            ((current_price - price_90d_ago) / price_90d_ago * 100) if price_90d_ago > 0 else 0.0
        )

        # Calculate SMA distances
        sma20_distance = ((current_price - sma_20) / sma_20 * 100) if sma_20 > 0 else 0.0
        sma50_distance = ((current_price - sma_50) / sma_50 * 100) if sma_50 > 0 else 0.0

        # Determine market structure (simplified - could be enhanced)
        # Check if making higher highs/lows by comparing recent price action
        lookback_period = min(20, len(candles))
        recent_candles = candles[-lookback_period:] if lookback_period > 0 else []

        higher_highs = False
        higher_lows = False
        if len(recent_candles) >= 2:
            # Simple heuristic: current price above median of recent highs/lows
            recent_highs = [c.high for c in recent_candles]
            recent_lows = [c.low for c in recent_candles]
            median_high = sorted(recent_highs)[len(recent_highs) // 2]
            median_low = sorted(recent_lows)[len(recent_lows) // 2]
            higher_highs = current_price > median_high
            higher_lows = current_price > median_low

        return PriceContext(
            current_price=current_price,
            return_1d=return_1d,
            return_7d=return_7d,
            return_30d=return_30d,
            return_90d=return_90d,
            sma20_distance=sma20_distance,
            sma50_distance=sma50_distance,
            higher_highs=higher_highs,
            higher_lows=higher_lows,
        )

    def _calculate_sma(
        self,
        candles: list[Candle],
        period: int,
        timestamp: datetime,
    ) -> float:
        """Calculate Simple Moving Average at specific timestamp.

        Uses lookback period from candles up to and including timestamp.
        Returns 0.0 if insufficient data.

        Args:
            candles: List of Candle objects (should be sorted by timestamp)
            period: Number of periods for SMA (e.g., 20, 50)
            timestamp: Target timestamp for calculation

        Returns:
            SMA value, or 0.0 if insufficient data
        """
        if len(candles) < period:
            logger.debug(
                f"Insufficient candles for SMA-{period}: {len(candles)} < {period} at {timestamp}"
            )
            return 0.0

        # Get the last 'period' candles up to timestamp
        closes = [c.close for c in candles[-period:]]

        if not closes or any(c <= 0 for c in closes):
            logger.warning(f"Invalid close prices for SMA-{period} at {timestamp}")
            return 0.0

        return sum(closes) / period

    def _calculate_adx(
        self,
        candles: list[Candle],
        timestamp: datetime,
    ) -> float:
        """Calculate Average Directional Index (ADX) at specific timestamp.

        ADX measures trend strength regardless of direction using 14-period lookback.
        Returns 0.0 if insufficient data.

        Args:
            candles: List of Candle objects (should be sorted by timestamp)
            timestamp: Target timestamp for calculation

        Returns:
            ADX value (0-100), or 0.0 if insufficient data
        """
        period = self.ADX_PERIOD

        if len(candles) < period + 1:
            logger.debug(
                f"Insufficient candles for ADX-{period}: {len(candles)} < {period + 1} at {timestamp}"
            )
            return 0.0

        # Calculate True Range (TR)
        true_ranges = []
        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i - 1].close

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
            true_ranges.append(tr)

        # Calculate Directional Movement (+DM and -DM)
        plus_dm = []
        minus_dm = []
        for i in range(1, len(candles)):
            high_diff = candles[i].high - candles[i - 1].high
            low_diff = candles[i - 1].low - candles[i].low

            plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
            minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)

        if not true_ranges or not plus_dm or not minus_dm:
            return 0.0

        # Calculate smoothed averages using last 'period' values
        atr = sum(true_ranges[-period:]) / period
        plus_di = (sum(plus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0
        minus_di = (sum(minus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0

        # Calculate DX
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0

        # For simplicity, return DX as ADX approximation
        # (proper ADX requires smoothing DX over period, but this is sufficient for backtesting)
        return dx

    def _calculate_realized_volatility(
        self,
        candles: list[Candle],
        hours: int,
        timestamp: datetime,
    ) -> float:
        """Calculate realized volatility over specified hours.

        Uses standard deviation of log returns for volatility calculation.
        Returns annualized volatility as decimal (e.g., 0.5 = 50%).

        Args:
            candles: List of Candle objects (should be sorted by timestamp)
            hours: Number of hours for volatility window (e.g., 24)
            timestamp: Target timestamp for calculation

        Returns:
            Annualized realized volatility as decimal, or 0.0 if insufficient data
        """
        if len(candles) < 2:
            logger.debug(f"Insufficient candles for volatility calculation at {timestamp}")
            return 0.0

        # Extract close prices
        closes = [c.close for c in candles]

        if not closes or any(c <= 0 for c in closes):
            logger.warning(f"Invalid close prices for volatility calculation at {timestamp}")
            return 0.0

        # Calculate log returns
        log_returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0 and closes[i] > 0:
                log_return = math.log(closes[i] / closes[i - 1])
                log_returns.append(log_return)

        if not log_returns:
            return 0.0

        # Calculate standard deviation of log returns
        mean_return = sum(log_returns) / len(log_returns)
        variance = sum((r - mean_return) ** 2 for r in log_returns) / len(log_returns)
        std_dev = math.sqrt(variance)

        # Annualize volatility
        # Assuming hourly candles, there are 24 * 365 = 8760 periods per year
        periods_per_year = 24 * 365
        annualized_vol = std_dev * math.sqrt(periods_per_year)

        return annualized_vol

    def _calculate_avg_funding_rate(
        self,
        funding_rates: dict[str, list[FundingRate]],
        timestamp: datetime,
    ) -> float:
        """Calculate average funding rate across all assets at timestamp.

        Weights funding rates by notional position value (using most recent funding rate
        for each asset up to timestamp). Returns 0.0 if no funding data available.

        Args:
            funding_rates: Dictionary mapping coin symbols to FundingRate lists
            timestamp: Target timestamp for calculation

        Returns:
            Average funding rate as decimal (e.g., 0.0001 = 0.01%)
        """
        if not funding_rates:
            return 0.0

        # Collect most recent funding rate for each asset up to timestamp
        asset_funding = {}
        for coin, rates in funding_rates.items():
            # Filter rates up to timestamp
            valid_rates = [fr for fr in rates if fr.timestamp <= timestamp]

            if valid_rates:
                # Get most recent rate
                most_recent = max(valid_rates, key=lambda fr: fr.timestamp)
                asset_funding[coin] = most_recent.rate

        if not asset_funding:
            logger.debug(f"No funding rate data available at {timestamp}")
            return 0.0

        # Simple average (equal weighting)
        # Note: Proper weighting would require position sizes, which we don't have in backtesting
        avg_funding = sum(asset_funding.values()) / len(asset_funding)

        return avg_funding

    def _calculate_spread_and_depth(
        self,
        order_books: dict[str, OrderBookData | None],
    ) -> tuple[float, float]:
        """Calculate bid-ask spread and order book depth.

        Spread is calculated in basis points: (ask - bid) / mid * 10000
        Depth is calculated as total size within 1% of mid-price.
        Returns (0.0, 0.0) if no order book data available.

        Args:
            order_books: Dictionary mapping coin symbols to OrderBookData or None

        Returns:
            Tuple of (bid_ask_spread_bps, order_book_depth)
        """
        if not order_books:
            return 0.0, 0.0

        spreads = []
        depths = []

        for _coin, order_book in order_books.items():
            if order_book is None:
                continue

            # Calculate spread
            if order_book.bids and order_book.asks:
                # Bids and asks are tuples of (price, size)
                best_bid = order_book.bids[0][0]
                best_ask = order_book.asks[0][0]

                if best_bid > 0 and best_ask > 0:
                    mid_price = (best_bid + best_ask) / 2
                    spread_bps = ((best_ask - best_bid) / mid_price) * 10000
                    spreads.append(spread_bps)

                    # Calculate depth within 1% of mid-price
                    lower_bound = mid_price * 0.99
                    upper_bound = mid_price * 1.01

                    bid_depth = sum(size for price, size in order_book.bids if price >= lower_bound)
                    ask_depth = sum(size for price, size in order_book.asks if price <= upper_bound)

                    total_depth = bid_depth + ask_depth
                    depths.append(total_depth)

        if not spreads or not depths:
            logger.debug("No valid order book data for spread/depth calculation")
            return 0.0, 0.0

        # Return average spread and depth across all assets
        avg_spread = sum(spreads) / len(spreads)
        avg_depth = sum(depths) / len(depths)

        return avg_spread, avg_depth
