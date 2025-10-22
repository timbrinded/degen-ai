"""Signal data models for time-scale-appropriate market signals."""

from dataclasses import dataclass
from typing import Literal

from hyperliquid_agent.monitor import AccountState


@dataclass
class FastLoopSignals:
    """Signals collected at fast loop frequency (seconds).

    These signals are used for execution-level decisions and immediate risk management.
    """

    spreads: dict[str, float]  # Coin -> spread in bps
    slippage_estimates: dict[str, float]  # Coin -> estimated slippage in bps
    short_term_volatility: float  # Recent volatility measure
    micro_pnl: float  # Very short-term PnL change
    partial_fill_rates: dict[str, float]  # Coin -> fill rate (0.0 to 1.0)


@dataclass
class MediumLoopSignals:
    """Signals collected at medium loop frequency (minutes-hours).

    These signals are used for tactical planning and Strategy Plan Card maintenance.
    """

    realized_vol_1h: float  # 1-hour realized volatility
    realized_vol_24h: float  # 24-hour realized volatility
    trend_score: float  # Trend strength indicator (-1 to 1)
    funding_basis: dict[str, float]  # Coin -> funding rate
    perp_spot_basis: dict[str, float]  # Coin -> perp-spot basis in bps
    concentration_ratios: dict[str, float]  # Coin -> position concentration (0.0 to 1.0)
    drift_from_targets: dict[str, float]  # Coin -> drift from target allocation in pct


@dataclass
class SlowLoopSignals:
    """Signals collected at slow loop frequency (daily-weekly).

    These signals are used for regime detection and macro-level policy changes.
    """

    macro_events_upcoming: list[dict]  # List of upcoming macro events
    cross_asset_risk_on_score: float  # Risk-on/risk-off score (-1 to 1)
    venue_health_score: float  # Exchange health indicator (0 to 1)
    liquidity_regime: Literal["high", "medium", "low"]  # Overall liquidity assessment


@dataclass
class EnhancedAccountState(AccountState):
    """Extended account state with time-scale-appropriate signals.

    Extends the base AccountState with optional signal collections for different
    decision time-scales.
    """

    fast_signals: FastLoopSignals | None = None
    medium_signals: MediumLoopSignals | None = None
    slow_signals: SlowLoopSignals | None = None
