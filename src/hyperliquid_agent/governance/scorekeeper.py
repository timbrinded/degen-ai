"""Plan scorekeeper data models for performance tracking."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PlanMetrics:
    """Performance metrics for a strategy plan."""

    plan_id: str
    start_time: datetime
    end_time: datetime | None

    # Performance
    total_pnl: float = 0.0
    total_risk_taken: float = 0.0
    pnl_per_unit_risk: float = 0.0

    # Execution quality
    total_trades: int = 0
    winning_trades: int = 0
    hit_rate: float = 0.0
    avg_slippage_bps: float = 0.0

    # Plan adherence
    avg_drift_from_targets_pct: float = 0.0
    rebalance_count: int = 0


@dataclass
class ShadowPortfolio:
    """Shadow portfolio for paper trading alternative strategies."""

    strategy_name: str
    paper_positions: dict[str, float]
    paper_portfolio_value: float
    paper_pnl: float = 0.0
