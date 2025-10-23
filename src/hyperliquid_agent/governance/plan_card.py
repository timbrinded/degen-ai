"""Strategy Plan Card data models for governance."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal


@dataclass
class TargetAllocation:
    """Target allocation for a specific asset."""

    coin: str
    target_pct: float  # Percentage of portfolio
    market_type: Literal["spot", "perp"]
    leverage: float = 1.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TargetAllocation":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class RiskBudget:
    """Risk budget constraints for a strategy plan."""

    max_position_pct: dict[str, float]  # Per-asset limits
    max_leverage: float
    max_adverse_excursion_pct: float
    plan_max_drawdown_pct: float
    per_trade_risk_pct: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RiskBudget":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ExitRules:
    """Exit and review rules for a strategy plan."""

    profit_target_pct: float | None
    stop_loss_pct: float | None
    time_based_review_hours: int
    invalidation_triggers: list[str]  # Natural language conditions

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExitRules":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ChangeCostModel:
    """Model for estimating the cost of changing strategies."""

    estimated_fees_bps: float
    estimated_slippage_bps: float
    estimated_funding_change_bps: float
    opportunity_cost_bps: float

    @property
    def total_cost_bps(self) -> float:
        """Calculate total change cost in basis points."""
        return sum(
            [
                self.estimated_fees_bps,
                self.estimated_slippage_bps,
                self.estimated_funding_change_bps,
                self.opportunity_cost_bps,
            ]
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChangeCostModel":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class StrategyPlanCard:
    """Complete strategy plan card with all governance metadata."""

    # Identity
    plan_id: str
    strategy_name: str
    strategy_version: str
    created_at: datetime

    # Intent
    objective: str
    target_holding_period_hours: int
    time_horizon: Literal["minutes", "hours", "days"]
    key_thesis: str

    # Targets
    target_allocations: list[TargetAllocation]
    allowed_leverage_range: tuple[float, float]

    # Risk
    risk_budget: RiskBudget

    # Exit & Review
    exit_rules: ExitRules

    # Change Cost
    change_cost: ChangeCostModel

    # Confidence & Monitoring
    expected_edge_bps: float
    kpis_to_track: list[str]
    minimum_dwell_minutes: int

    # Regime Compatibility
    compatible_regimes: list[str]
    avoid_regimes: list[str]

    # State
    status: Literal["active", "rebalancing", "invalidated", "completed"] = "active"
    activated_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    rebalance_progress_pct: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data["created_at"] = self.created_at.isoformat()
        if self.activated_at:
            data["activated_at"] = self.activated_at.isoformat()
        if self.last_reviewed_at:
            data["last_reviewed_at"] = self.last_reviewed_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyPlanCard":
        """Create from dictionary."""
        # Parse datetime strings
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("activated_at"):
            data["activated_at"] = datetime.fromisoformat(data["activated_at"])
        if data.get("last_reviewed_at"):
            data["last_reviewed_at"] = datetime.fromisoformat(data["last_reviewed_at"])

        # Parse nested objects
        data["target_allocations"] = [
            TargetAllocation.from_dict(a) for a in data["target_allocations"]
        ]
        data["allowed_leverage_range"] = tuple(data["allowed_leverage_range"])
        data["risk_budget"] = RiskBudget.from_dict(data["risk_budget"])
        data["exit_rules"] = ExitRules.from_dict(data["exit_rules"])
        data["change_cost"] = ChangeCostModel.from_dict(data["change_cost"])

        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "StrategyPlanCard":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
