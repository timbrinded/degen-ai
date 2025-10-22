"""Tripwire service data models for safety monitoring."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal


class TripwireAction(Enum):
    """Actions that can be triggered by tripwires."""

    FREEZE_NEW_RISK = "freeze_new_risk"
    CUT_SIZE_TO_FLOOR = "cut_size_to_floor"
    ESCALATE_TO_SLOW_LOOP = "escalate_to_slow_loop"
    INVALIDATE_PLAN = "invalidate_plan"


@dataclass
class TripwireEvent:
    """Event generated when a tripwire condition is triggered."""

    severity: Literal["warning", "critical"]
    category: Literal["account_safety", "plan_invalidation", "operational"]
    trigger: str
    action: TripwireAction
    timestamp: datetime
    details: dict


@dataclass
class TripwireConfig:
    """Configuration for tripwire service."""

    # Account safety
    min_margin_ratio: float = 0.15
    liquidation_proximity_threshold: float = 0.25
    daily_loss_limit_pct: float = 5.0

    # Plan invalidation
    check_invalidation_triggers: bool = True

    # Operational
    max_data_staleness_seconds: int = 300
    max_api_failure_count: int = 3
