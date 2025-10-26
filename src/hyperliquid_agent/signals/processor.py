"""Computed signal processor for derived metrics calculation."""

import logging
import math
from dataclasses import dataclass

from hyperliquid_agent.monitor import Position
from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.hyperliquid_provider import Candle

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Technical indicator values.

    Attributes:
        sma_20: 20-period Simple Moving Average
        sma_50: 50-period Simple Moving Average
        adx: Average Directional Index (14-period)
        rsi: Relative Strength Index (optional)
    """

    sma_20: float
    sma_50: float
    adx: float
    rsi: float | None = None


@dataclass
class VolatilityMetrics:
    """Volatility calculation results.

    Attributes:
        realized_vol_1h: 1-hour realized volatility (annualized)
        realized_vol_24h: 24-hour realized volatility (annualized)
        realized_vol_7d: 7-day realized volatility (annualized)
        annualized_vol: Overall annualized volatility
    """

    realized_vol_1h: float
    realized_vol_24h: float
    realized_vol_7d: float
    annualized_vol: float


@dataclass
class PortfolioMetrics:
    """Portfolio-level metrics.

    Attributes:
        portfolio_volatility: Position-weighted portfolio volatility (annualized)
        portfolio_beta: Portfolio beta relative to BTC
        max_drawdown_7d: Maximum drawdown over past 7 days
        sharpe_ratio: Sharpe ratio (optional)
    """

    portfolio_volatility: float
    portfolio_beta: float
    max_drawdown_7d: float
    sharpe_ratio: float | None = None


class ComputedSignalProcessor:
    """Processes raw data into computed signals.

    This processor calculates derived metrics from raw market data including:
    - Technical indicators (SMAs, ADX, trend scores)
    - Volatility metrics at multiple timeframes
    - Cross-asset correlations
    - Portfolio-level risk metrics

    All expensive computations are cached with a 5-minute TTL.
    """

    # Cache TTL for computed signals (5 minutes)
    CACHE_TTL_COMPUTED = 300

    def __init__(self, cache: SQLiteCacheLayer):
        """Initialize computed signal processor.

        Args:
            cache: SQLite cache layer for caching expensive computations
        """
        self.cache = cache

    async def calculate_technical_indicators(
        self,
        candles: list[Candle],
    ) -> TechnicalIndicators:
        """Calculate technical indicators (SMA-20, SMA-50, ADX).

        Args:
            candles: List of OHLCV candles (should have at least 50 periods)

        Returns:
            TechnicalIndicators with calculated values

        Raises:
            ValueError: If insufficient candle data provided
        """
        if not candles:
            raise ValueError("Cannot calculate technical indicators with empty candle list")

        # Sort candles by timestamp to ensure correct order
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)

        # Extract close prices
        closes = [c.close for c in sorted_candles]

        # Check cache
        cache_key = f"tech_indicators:{candles[0].coin}:{len(candles)}"
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Technical indicators cache hit (age: {cached.age_seconds:.1f}s)")
            return cached.value

        # Calculate SMAs
        sma_20 = self._calculate_sma(closes, 20)
        sma_50 = self._calculate_sma(closes, 50)

        # Calculate ADX
        adx = self._calculate_adx(sorted_candles, 14)

        indicators = TechnicalIndicators(
            sma_20=sma_20,
            sma_50=sma_50,
            adx=adx,
            rsi=None,  # RSI is optional for now
        )

        # Cache the result
        await self.cache.set(cache_key, indicators, self.CACHE_TTL_COMPUTED)

        return indicators

    async def calculate_volatility_metrics(
        self,
        candles_1h: list[Candle],
        candles_24h: list[Candle],
        candles_7d: list[Candle],
    ) -> VolatilityMetrics:
        """Calculate realized volatility at multiple timeframes.

        Volatility is calculated using close-to-close returns and annualized
        by multiplying by sqrt(periods per year).

        Args:
            candles_1h: Hourly candles for 1-hour volatility (at least 2 candles)
            candles_24h: Hourly candles for 24-hour volatility (at least 24 candles)
            candles_7d: Daily candles for 7-day volatility (at least 7 candles)

        Returns:
            VolatilityMetrics with annualized volatility values

        Raises:
            ValueError: If insufficient candle data provided
        """
        if not candles_1h or not candles_24h or not candles_7d:
            raise ValueError("Cannot calculate volatility with empty candle lists")

        # Check cache
        cache_key = f"volatility:{candles_1h[0].coin}:{len(candles_1h)}:{len(candles_24h)}:{len(candles_7d)}"
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Volatility metrics cache hit (age: {cached.age_seconds:.1f}s)")
            return cached.value

        # Calculate realized volatility for each timeframe
        vol_1h = self._calculate_realized_volatility(candles_1h, periods_per_year=24 * 365)
        vol_24h = self._calculate_realized_volatility(candles_24h, periods_per_year=365)
        vol_7d = self._calculate_realized_volatility(candles_7d, periods_per_year=52)

        # Use 24h volatility as the overall annualized volatility
        annualized_vol = vol_24h

        metrics = VolatilityMetrics(
            realized_vol_1h=vol_1h,
            realized_vol_24h=vol_24h,
            realized_vol_7d=vol_7d,
            annualized_vol=annualized_vol,
        )

        # Cache the result
        await self.cache.set(cache_key, metrics, self.CACHE_TTL_COMPUTED)

        return metrics

    async def calculate_correlation_matrix(
        self,
        price_data: dict[str, list[float]],
    ) -> dict[tuple[str, str], float]:
        """Calculate pairwise correlations between assets.

        Uses Pearson correlation coefficient on price returns.

        Args:
            price_data: Dictionary mapping asset symbols to price lists
                       (e.g., {"BTC": [50000, 51000, ...], "ETH": [3000, 3100, ...]})

        Returns:
            Dictionary mapping asset pairs to correlation coefficients
            (e.g., {("BTC", "ETH"): 0.85, ("BTC", "SPX"): 0.42})

        Raises:
            ValueError: If insufficient price data provided
        """
        if not price_data or len(price_data) < 2:
            raise ValueError("Need at least 2 assets to calculate correlations")

        # Check cache
        assets_key = "_".join(sorted(price_data.keys()))
        cache_key = f"correlation:{assets_key}"
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Correlation matrix cache hit (age: {cached.age_seconds:.1f}s)")
            return cached.value

        correlations: dict[tuple[str, str], float] = {}

        # Calculate pairwise correlations
        assets = list(price_data.keys())
        for i, asset1 in enumerate(assets):
            for asset2 in assets[i + 1 :]:
                prices1 = price_data[asset1]
                prices2 = price_data[asset2]

                # Ensure equal length
                min_len = min(len(prices1), len(prices2))
                if min_len < 2:
                    logger.warning(f"Insufficient data for correlation: {asset1}-{asset2}")
                    continue

                prices1 = prices1[-min_len:]
                prices2 = prices2[-min_len:]

                # Calculate correlation
                corr = self._calculate_pearson_correlation(prices1, prices2)
                correlations[(asset1, asset2)] = corr
                correlations[(asset2, asset1)] = corr  # Symmetric

        # Cache the result
        await self.cache.set(cache_key, correlations, self.CACHE_TTL_COMPUTED)

        return correlations

    async def calculate_portfolio_metrics(
        self,
        positions: list[Position],
        price_history: dict[str, list[float]],
        btc_price_history: list[float],
    ) -> PortfolioMetrics:
        """Calculate portfolio-level volatility, beta, and max drawdown.

        Args:
            positions: List of current positions
            price_history: Dictionary mapping coin symbols to historical prices
            btc_price_history: BTC price history for beta calculation

        Returns:
            PortfolioMetrics with portfolio-level risk metrics

        Raises:
            ValueError: If insufficient data provided
        """
        if not positions:
            logger.warning("No positions for portfolio metrics calculation")
            return PortfolioMetrics(
                portfolio_volatility=0.0,
                portfolio_beta=0.0,
                max_drawdown_7d=0.0,
                sharpe_ratio=None,
            )

        # Check cache
        position_key = "_".join(sorted([p.coin for p in positions]))
        cache_key = f"portfolio_metrics:{position_key}"
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Portfolio metrics cache hit (age: {cached.age_seconds:.1f}s)")
            return cached.value

        # Calculate position weights
        total_value = sum(abs(p.size * p.current_price) for p in positions)
        if total_value == 0:
            logger.warning("Total portfolio value is zero")
            return PortfolioMetrics(
                portfolio_volatility=0.0,
                portfolio_beta=0.0,
                max_drawdown_7d=0.0,
                sharpe_ratio=None,
            )

        weights = {p.coin: abs(p.size * p.current_price) / total_value for p in positions}

        # Calculate portfolio volatility (position-weighted)
        portfolio_vol = self._calculate_portfolio_volatility(weights, price_history)

        # Calculate portfolio beta relative to BTC
        portfolio_beta = self._calculate_portfolio_beta(weights, price_history, btc_price_history)

        # Calculate maximum drawdown over past 7 days
        max_drawdown = self._calculate_max_drawdown(weights, price_history)

        metrics = PortfolioMetrics(
            portfolio_volatility=portfolio_vol,
            portfolio_beta=portfolio_beta,
            max_drawdown_7d=max_drawdown,
            sharpe_ratio=None,  # Sharpe ratio is optional
        )

        # Cache the result
        await self.cache.set(cache_key, metrics, self.CACHE_TTL_COMPUTED)

        return metrics

    def _calculate_sma(self, prices: list[float], period: int) -> float:
        """Calculate Simple Moving Average.

        Args:
            prices: List of prices
            period: Number of periods for SMA

        Returns:
            SMA value, or 0.0 if insufficient data
        """
        if len(prices) < period:
            logger.warning(f"Insufficient data for SMA-{period}: {len(prices)} < {period}")
            return 0.0

        return sum(prices[-period:]) / period

    def _calculate_adx(self, candles: list[Candle], period: int = 14) -> float:
        """Calculate Average Directional Index (ADX).

        ADX measures trend strength regardless of direction.

        Args:
            candles: List of OHLCV candles
            period: Lookback period (default 14)

        Returns:
            ADX value (0-100), or 0.0 if insufficient data
        """
        if len(candles) < period + 1:
            logger.warning(f"Insufficient data for ADX-{period}: {len(candles)} < {period + 1}")
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

        # Calculate smoothed averages
        atr = sum(true_ranges[-period:]) / period
        plus_di = (sum(plus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0
        minus_di = (sum(minus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0

        # Calculate DX and ADX
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0

        # For simplicity, return DX as ADX approximation
        # (proper ADX requires smoothing DX over period)
        return dx

    def _calculate_realized_volatility(
        self,
        candles: list[Candle],
        periods_per_year: int,
    ) -> float:
        """Calculate realized volatility from candles.

        Uses close-to-close returns and annualizes by multiplying by sqrt(periods).

        Args:
            candles: List of OHLCV candles
            periods_per_year: Number of periods per year for annualization
                             (e.g., 365 for daily, 24*365 for hourly)

        Returns:
            Annualized realized volatility as decimal (e.g., 0.5 = 50%)
        """
        if len(candles) < 2:
            logger.warning("Insufficient candles for volatility calculation")
            return 0.0

        # Sort by timestamp
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)

        # Calculate returns
        closes = [c.close for c in sorted_candles]
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                ret = (closes[i] - closes[i - 1]) / closes[i - 1]
                returns.append(ret)

        if not returns:
            return 0.0

        # Calculate standard deviation of returns
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance)

        # Annualize by multiplying by sqrt of periods per year
        annualized_vol = std_dev * math.sqrt(periods_per_year)

        return annualized_vol

    def _calculate_pearson_correlation(
        self,
        prices1: list[float],
        prices2: list[float],
    ) -> float:
        """Calculate Pearson correlation coefficient between two price series.

        Args:
            prices1: First price series
            prices2: Second price series (must be same length as prices1)

        Returns:
            Correlation coefficient from -1.0 to 1.0
        """
        if len(prices1) != len(prices2) or len(prices1) < 2:
            logger.warning("Invalid price series for correlation calculation")
            return 0.0

        # Calculate returns
        returns1 = [
            (prices1[i] - prices1[i - 1]) / prices1[i - 1]
            for i in range(1, len(prices1))
            if prices1[i - 1] > 0
        ]
        returns2 = [
            (prices2[i] - prices2[i - 1]) / prices2[i - 1]
            for i in range(1, len(prices2))
            if prices2[i - 1] > 0
        ]

        if len(returns1) != len(returns2) or len(returns1) < 2:
            return 0.0

        # Calculate means
        mean1 = sum(returns1) / len(returns1)
        mean2 = sum(returns2) / len(returns2)

        # Calculate covariance and standard deviations
        covariance = sum(
            (returns1[i] - mean1) * (returns2[i] - mean2) for i in range(len(returns1))
        )
        std1 = math.sqrt(sum((r - mean1) ** 2 for r in returns1))
        std2 = math.sqrt(sum((r - mean2) ** 2 for r in returns2))

        # Calculate correlation
        if std1 > 0 and std2 > 0:
            correlation = covariance / (std1 * std2)
            return max(-1.0, min(1.0, correlation))  # Clamp to [-1, 1]

        return 0.0

    def _calculate_portfolio_volatility(
        self,
        weights: dict[str, float],
        price_history: dict[str, list[float]],
    ) -> float:
        """Calculate position-weighted portfolio volatility.

        Args:
            weights: Dictionary mapping coin symbols to position weights
            price_history: Dictionary mapping coin symbols to price histories

        Returns:
            Annualized portfolio volatility as decimal
        """
        # Calculate individual asset volatilities
        asset_vols: dict[str, float] = {}
        for coin, prices in price_history.items():
            if coin not in weights or len(prices) < 2:
                continue

            # Calculate returns
            returns = [
                (prices[i] - prices[i - 1]) / prices[i - 1]
                for i in range(1, len(prices))
                if prices[i - 1] > 0
            ]

            if returns:
                mean_return = sum(returns) / len(returns)
                variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
                asset_vols[coin] = math.sqrt(variance)

        # Simple weighted average (ignoring correlations for now)
        # For proper portfolio vol, we'd need the full covariance matrix
        portfolio_vol = sum(weights.get(coin, 0) * vol for coin, vol in asset_vols.items())

        # Annualize (assuming daily data)
        return portfolio_vol * math.sqrt(365)

    def _calculate_portfolio_beta(
        self,
        weights: dict[str, float],
        price_history: dict[str, list[float]],
        btc_price_history: list[float],
    ) -> float:
        """Calculate portfolio beta relative to BTC.

        Args:
            weights: Dictionary mapping coin symbols to position weights
            price_history: Dictionary mapping coin symbols to price histories
            btc_price_history: BTC price history

        Returns:
            Portfolio beta (e.g., 1.0 means moves with BTC, 0.5 means half as volatile)
        """
        if len(btc_price_history) < 2:
            logger.warning("Insufficient BTC price history for beta calculation")
            return 0.0

        # Calculate BTC returns
        btc_returns = [
            (btc_price_history[i] - btc_price_history[i - 1]) / btc_price_history[i - 1]
            for i in range(1, len(btc_price_history))
            if btc_price_history[i - 1] > 0
        ]

        if not btc_returns:
            return 0.0

        # Initialize portfolio returns list
        num_periods = len(btc_returns)
        portfolio_returns_list: list[float] = []
        for _ in range(num_periods):
            portfolio_returns_list.append(0.0)

        for coin, weight in weights.items():
            if coin not in price_history:
                continue

            prices = price_history[coin]
            if len(prices) < num_periods + 1:
                continue

            # Align with BTC returns length
            prices = prices[-num_periods - 1 :]

            # Calculate returns and add weighted to portfolio
            for i in range(1, len(prices)):
                if prices[i - 1] > 0 and i - 1 < len(portfolio_returns_list):
                    coin_return = (prices[i] - prices[i - 1]) / prices[i - 1]
                    portfolio_returns_list[i - 1] += weight * coin_return

        # Calculate beta (covariance / variance)
        mean_btc = sum(btc_returns) / len(btc_returns)
        mean_portfolio = float(sum(portfolio_returns_list)) / len(portfolio_returns_list)

        covariance = float(
            sum(
                (btc_returns[i] - mean_btc) * (portfolio_returns_list[i] - mean_portfolio)
                for i in range(len(btc_returns))
            )
        )
        variance_btc = sum((r - mean_btc) ** 2 for r in btc_returns)

        if variance_btc > 0:
            beta = covariance / variance_btc
            return beta

        return 0.0

    def _calculate_max_drawdown(
        self,
        weights: dict[str, float],
        price_history: dict[str, list[float]],
    ) -> float:
        """Calculate maximum drawdown over the price history period.

        Args:
            weights: Dictionary mapping coin symbols to position weights
            price_history: Dictionary mapping coin symbols to price histories

        Returns:
            Maximum drawdown as decimal (e.g., 0.2 = 20% drawdown)
        """
        # Calculate weighted portfolio value over time
        min_length = min(len(prices) for prices in price_history.values() if prices)
        if min_length < 2:
            return 0.0

        portfolio_values = []
        for i in range(min_length):
            value = sum(
                weights.get(coin, 0) * prices[i]
                for coin, prices in price_history.items()
                if len(prices) > i
            )
            portfolio_values.append(value)

        # Calculate drawdown at each point
        max_drawdown = 0.0
        peak = portfolio_values[0]

        for value in portfolio_values:
            if value > peak:
                peak = value

            drawdown = (peak - value) / peak if peak > 0 else 0.0
            max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown
