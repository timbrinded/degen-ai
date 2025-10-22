"""Signal collectors for different time scales."""

import time
from typing import Literal

from hyperliquid.info import Info

from hyperliquid_agent.monitor import AccountState, Position
from hyperliquid_agent.signals.calculations import (
    calculate_realized_volatility,
    calculate_sma,
    calculate_spread_bps,
    calculate_trend_score,
)
from hyperliquid_agent.signals.models import (
    FastLoopSignals,
    MediumLoopSignals,
    SlowLoopSignals,
)


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
    """Collects fast-loop signals for execution-level decisions."""

    def collect(self, account_state: AccountState) -> FastLoopSignals:
        """Collect fast-loop signals.

        Args:
            account_state: Current account state

        Returns:
            FastLoopSignals with current execution-level market data
        """
        spreads = {}
        slippage_estimates = {}
        partial_fill_rates = {}
        micro_pnl = sum(p.unrealized_pnl for p in account_state.positions)

        # Collect per-position metrics
        for position in account_state.positions:
            coin = position.coin

            # Get L2 order book snapshot for spread calculation
            try:
                l2_data = self.info.l2_snapshot(coin)
                levels = l2_data.get("levels", [[[], []]])

                if levels and len(levels[0]) == 2:
                    bids = levels[0][0]  # [[price, size], ...]
                    asks = levels[0][1]  # [[price, size], ...]

                    if bids and asks:
                        best_bid = float(bids[0][0])
                        best_ask = float(asks[0][0])

                        # Calculate spread in bps
                        spread_bps = calculate_spread_bps(best_bid, best_ask)
                        spreads[coin] = spread_bps

                        # Estimate slippage based on order book depth
                        # Simple heuristic: slippage ~= spread/2 for small orders
                        slippage_estimates[coin] = spread_bps / 2
                    else:
                        spreads[coin] = 10.0  # Default wide spread
                        slippage_estimates[coin] = 5.0
                else:
                    spreads[coin] = 10.0
                    slippage_estimates[coin] = 5.0

            except Exception:
                # Fallback to conservative estimates on API failure
                spreads[coin] = 15.0
                slippage_estimates[coin] = 7.5

            # Partial fill rates - would need historical fill data
            # For now, assume high fill rate for liquid markets
            partial_fill_rates[coin] = 0.95

        # Calculate short-term volatility from recent price changes
        short_term_vol = self._calculate_short_term_volatility(account_state.positions)

        return FastLoopSignals(
            spreads=spreads,
            slippage_estimates=slippage_estimates,
            short_term_volatility=short_term_vol,
            micro_pnl=micro_pnl,
            partial_fill_rates=partial_fill_rates,
        )

    def _calculate_short_term_volatility(self, positions: list[Position]) -> float:
        """Calculate short-term volatility from largest position.

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
            candles = self.info.candles_snapshot(
                largest_position.coin, "1m", start_time, end_time
            )
            if candles and len(candles) > 1:
                return calculate_realized_volatility(candles)
        except Exception:
            pass

        return 0.0


class MediumSignalCollector(SignalCollectorBase):
    """Collects medium-loop signals for tactical planning."""

    def collect(self, account_state: AccountState) -> MediumLoopSignals:
        """Collect medium-loop signals.

        Args:
            account_state: Current account state

        Returns:
            MediumLoopSignals with tactical-level market data
        """
        funding_basis = {}
        perp_spot_basis = {}
        concentration_ratios = {}
        drift_from_targets = {}

        total_value = account_state.portfolio_value

        # Collect per-position metrics
        for position in account_state.positions:
            coin = position.coin

            # Get funding rate history (last 24 hours)
            try:
                start_time, end_time = self._get_timestamp_range(hours_back=24)
                funding_history = self.info.funding_history(coin, start_time, end_time)
                if funding_history:
                    # Calculate average funding rate
                    rates = [float(f.get("fundingRate", 0)) for f in funding_history]
                    avg_funding = sum(rates) / len(rates) if rates else 0.0
                    funding_basis[coin] = avg_funding * 100  # Convert to percentage
                else:
                    funding_basis[coin] = 0.0
            except Exception:
                funding_basis[coin] = 0.0

            # Perp-spot basis (would need spot prices - not available on Hyperliquid)
            perp_spot_basis[coin] = 0.0  # Not directly available

            # Calculate concentration
            position_value = abs(position.size * position.current_price)
            concentration_ratios[coin] = (
                position_value / total_value if total_value > 0 else 0.0
            )

            # Drift from targets (would need target allocations from active plan)
            drift_from_targets[coin] = 0.0

        # Calculate realized volatility and trend using the largest position
        realized_vol_1h, realized_vol_24h, trend_score = self._calculate_volatility_and_trend(
            account_state.positions
        )

        return MediumLoopSignals(
            realized_vol_1h=realized_vol_1h,
            realized_vol_24h=realized_vol_24h,
            trend_score=trend_score,
            funding_basis=funding_basis,
            perp_spot_basis=perp_spot_basis,
            concentration_ratios=concentration_ratios,
            drift_from_targets=drift_from_targets,
        )

    def _calculate_volatility_and_trend(
        self, positions: list[Position]
    ) -> tuple[float, float, float]:
        """Calculate volatility and trend metrics from largest position.

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
            # 1-hour realized volatility (last 24 hours of 1h candles)
            start_time_1h, end_time_1h = self._get_timestamp_range(hours_back=24)
            candles_1h = self.info.candles_snapshot(
                largest_position.coin, "1h", start_time_1h, end_time_1h
            )
            if candles_1h and len(candles_1h) > 1:
                realized_vol_1h = calculate_realized_volatility(candles_1h)

            # 24-hour realized volatility (last 7 days of 1h candles)
            start_time_24h, end_time_24h = self._get_timestamp_range(hours_back=168)
            candles_24h = self.info.candles_snapshot(
                largest_position.coin, "1h", start_time_24h, end_time_24h
            )
            if candles_24h and len(candles_24h) > 1:
                realized_vol_24h = calculate_realized_volatility(candles_24h)

            # Calculate trend score using SMA crossover
            if candles_24h and len(candles_24h) >= 50:
                closes = [float(c["c"]) for c in candles_24h]
                sma_20 = calculate_sma(closes, 20)
                sma_50 = calculate_sma(closes, 50)
                current_price = closes[-1]
                trend_score = calculate_trend_score(current_price, sma_20, sma_50)

        except Exception:
            pass

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
