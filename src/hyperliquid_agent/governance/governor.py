"""Strategy Governor for enforcing plan persistence and change governance."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .plan_card import StrategyPlanCard, TargetAllocation


@dataclass
class GovernorConfig:
    """Configuration for Strategy Governor."""

    minimum_advantage_over_cost_bps: float = 50.0  # Require 50bps advantage
    cooldown_after_change_minutes: int = 60
    partial_rotation_pct_per_cycle: float = 25.0
    state_persistence_path: str = "state/governor.json"


@dataclass
class PlanChangeProposal:
    """Proposal for changing the active strategy plan."""

    new_plan: StrategyPlanCard
    reason: str
    expected_advantage_bps: float
    change_cost_bps: float

    @property
    def net_advantage_bps(self) -> float:
        """Calculate net advantage after subtracting change cost."""
        return self.expected_advantage_bps - self.change_cost_bps


class StrategyGovernor:
    """Enforces plan persistence, dwell times, and switching thresholds."""

    def __init__(self, config: GovernorConfig, logger: logging.Logger | None = None):
        """Initialize Strategy Governor.

        Args:
            config: Governor configuration
            logger: Optional logger instance for governance event logging
        """
        self.config = config
        self.active_plan: StrategyPlanCard | None = None
        self.last_change_at: datetime | None = None
        self.rebalance_schedule: list[dict] | None = None
        self.logger = logger or logging.getLogger(__name__)
        self._load_state()

    def can_review_plan(self, current_time: datetime) -> tuple[bool, str]:
        """Check if plan review is permitted.

        Args:
            current_time: Current timestamp

        Returns:
            Tuple of (can_review, reason_string)
        """
        if self.active_plan is None:
            self.logger.debug(
                "Plan review permitted: no active plan",
                extra={
                    "governance_event": "plan_review_check",
                    "can_review": True,
                    "reason": "no_active_plan",
                },
            )
            return True, "No active plan"

        # Check dwell time
        if self.active_plan.activated_at:
            dwell_elapsed = (current_time - self.active_plan.activated_at).total_seconds() / 60
            if dwell_elapsed < self.active_plan.minimum_dwell_minutes:
                self.logger.info(
                    f"Plan review blocked: dwell time not met ({dwell_elapsed:.1f}/{self.active_plan.minimum_dwell_minutes} min)",
                    extra={
                        "governance_event": "plan_review_check",
                        "can_review": False,
                        "reason": "dwell_time_not_met",
                        "plan_id": self.active_plan.plan_id,
                        "strategy_name": self.active_plan.strategy_name,
                        "dwell_elapsed_minutes": dwell_elapsed,
                        "minimum_dwell_minutes": self.active_plan.minimum_dwell_minutes,
                        "activated_at": self.active_plan.activated_at.isoformat(),
                    },
                )
                return (
                    False,
                    f"Dwell time not met: {dwell_elapsed:.1f}/{self.active_plan.minimum_dwell_minutes} min",
                )

        # Check cooldown
        if self.last_change_at:
            cooldown_elapsed = (current_time - self.last_change_at).total_seconds() / 60
            if cooldown_elapsed < self.config.cooldown_after_change_minutes:
                self.logger.info(
                    f"Plan review blocked: cooldown active ({cooldown_elapsed:.1f}/{self.config.cooldown_after_change_minutes} min)",
                    extra={
                        "governance_event": "plan_review_check",
                        "can_review": False,
                        "reason": "cooldown_active",
                        "plan_id": self.active_plan.plan_id,
                        "strategy_name": self.active_plan.strategy_name,
                        "cooldown_elapsed_minutes": cooldown_elapsed,
                        "cooldown_required_minutes": self.config.cooldown_after_change_minutes,
                        "last_change_at": self.last_change_at.isoformat(),
                    },
                )
                return (
                    False,
                    f"Cooldown active: {cooldown_elapsed:.1f}/{self.config.cooldown_after_change_minutes} min",
                )

        # Check rebalancing
        if self.active_plan.status == "rebalancing":
            self.logger.info(
                "Plan review blocked: rebalancing in progress",
                extra={
                    "governance_event": "plan_review_check",
                    "can_review": False,
                    "reason": "rebalancing_in_progress",
                    "plan_id": self.active_plan.plan_id,
                    "strategy_name": self.active_plan.strategy_name,
                    "rebalance_progress_pct": self.active_plan.rebalance_progress_pct,
                },
            )
            return False, "Rebalancing in progress"

        self.logger.info(
            "Plan review permitted",
            extra={
                "governance_event": "plan_review_check",
                "can_review": True,
                "reason": "review_permitted",
                "plan_id": self.active_plan.plan_id,
                "strategy_name": self.active_plan.strategy_name,
            },
        )
        return True, "Review permitted"

    def evaluate_change_proposal(self, proposal: PlanChangeProposal) -> tuple[bool, str]:
        """Evaluate whether to approve a plan change.

        Args:
            proposal: Plan change proposal to evaluate

        Returns:
            Tuple of (approved, reason_string)
        """
        old_plan_id = self.active_plan.plan_id if self.active_plan else None
        old_strategy = self.active_plan.strategy_name if self.active_plan else None

        if proposal.net_advantage_bps < self.config.minimum_advantage_over_cost_bps:
            self.logger.warning(
                f"Plan change rejected: insufficient advantage ({proposal.net_advantage_bps:.1f} < {self.config.minimum_advantage_over_cost_bps} bps)",
                extra={
                    "governance_event": "plan_change_rejected",
                    "old_plan_id": old_plan_id,
                    "old_strategy": old_strategy,
                    "new_strategy": proposal.new_plan.strategy_name,
                    "new_plan_id": proposal.new_plan.plan_id,
                    "rejection_reason": "insufficient_advantage",
                    "net_advantage_bps": proposal.net_advantage_bps,
                    "minimum_required_bps": self.config.minimum_advantage_over_cost_bps,
                    "expected_advantage_bps": proposal.expected_advantage_bps,
                    "change_cost_bps": proposal.change_cost_bps,
                    "proposal_reason": proposal.reason,
                },
            )
            return (
                False,
                f"Insufficient advantage: {proposal.net_advantage_bps:.1f} < {self.config.minimum_advantage_over_cost_bps} bps",
            )

        self.logger.info(
            f"Plan change approved: {proposal.net_advantage_bps:.1f} bps net advantage",
            extra={
                "governance_event": "plan_change_approved",
                "old_plan_id": old_plan_id,
                "old_strategy": old_strategy,
                "new_strategy": proposal.new_plan.strategy_name,
                "new_plan_id": proposal.new_plan.plan_id,
                "net_advantage_bps": proposal.net_advantage_bps,
                "expected_advantage_bps": proposal.expected_advantage_bps,
                "change_cost_bps": proposal.change_cost_bps,
                "proposal_reason": proposal.reason,
            },
        )
        return True, f"Approved: {proposal.net_advantage_bps:.1f} bps net advantage"

    def activate_plan(self, plan: StrategyPlanCard, current_time: datetime):
        """Activate a new plan.

        Args:
            plan: Strategy plan card to activate
            current_time: Current timestamp
        """
        old_plan_id = self.active_plan.plan_id if self.active_plan else None
        old_strategy = self.active_plan.strategy_name if self.active_plan else None

        plan.activated_at = current_time
        plan.status = "active"
        self.active_plan = plan
        self.last_change_at = current_time
        self._persist_state()

        self.logger.info(
            f"Plan activated: {plan.strategy_name} ({plan.plan_id})",
            extra={
                "governance_event": "plan_activated",
                "old_plan_id": old_plan_id,
                "old_strategy": old_strategy,
                "new_plan_id": plan.plan_id,
                "new_strategy": plan.strategy_name,
                "strategy_version": plan.strategy_version,
                "objective": plan.objective,
                "time_horizon": plan.time_horizon,
                "target_holding_period_hours": plan.target_holding_period_hours,
                "minimum_dwell_minutes": plan.minimum_dwell_minutes,
                "expected_edge_bps": plan.expected_edge_bps,
                "activated_at": current_time.isoformat(),
                "target_allocations": [
                    {
                        "coin": alloc.coin,
                        "target_pct": alloc.target_pct,
                        "market_type": alloc.market_type,
                        "leverage": alloc.leverage,
                    }
                    for alloc in plan.target_allocations
                ],
                "compatible_regimes": plan.compatible_regimes,
                "avoid_regimes": plan.avoid_regimes,
            },
        )

    def create_rebalance_schedule(
        self, from_allocations: list[TargetAllocation], to_allocations: list[TargetAllocation]
    ) -> list[dict]:
        """Create multi-step rebalance schedule for partial rotations.

        Args:
            from_allocations: Current target allocations
            to_allocations: New target allocations

        Returns:
            List of rebalance steps with interpolated allocations
        """
        steps = []
        num_steps = int(100 / self.config.partial_rotation_pct_per_cycle)

        for step in range(num_steps):
            progress = (step + 1) * self.config.partial_rotation_pct_per_cycle / 100
            step_allocations = []

            for to_alloc in to_allocations:
                from_alloc = next((a for a in from_allocations if a.coin == to_alloc.coin), None)
                from_pct = from_alloc.target_pct if from_alloc else 0.0

                interpolated_pct = from_pct + (to_alloc.target_pct - from_pct) * progress
                step_allocations.append(
                    {
                        "coin": to_alloc.coin,
                        "target_pct": interpolated_pct,
                        "market_type": to_alloc.market_type,
                        "leverage": to_alloc.leverage,
                    }
                )

            steps.append(
                {"step": step + 1, "progress_pct": progress * 100, "allocations": step_allocations}
            )

        return steps

    def _load_state(self):
        """Load persisted state from disk."""
        path = Path(self.config.state_persistence_path)
        if not path.exists():
            return

        try:
            with open(path) as f:
                data = json.load(f)

                # Deserialize active_plan
                if data.get("active_plan"):
                    self.active_plan = StrategyPlanCard.from_dict(data["active_plan"])

                # Deserialize last_change_at
                if data.get("last_change_at"):
                    self.last_change_at = datetime.fromisoformat(data["last_change_at"])

                # Deserialize rebalance_schedule
                self.rebalance_schedule = data.get("rebalance_schedule")

        except Exception as e:
            # Log error but don't crash - start with clean state
            print(f"Warning: Failed to load governor state: {e}")

    def _persist_state(self):
        """Persist state to disk."""
        path = Path(self.config.state_persistence_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "active_plan": self.active_plan.to_dict() if self.active_plan else None,
            "last_change_at": self.last_change_at.isoformat() if self.last_change_at else None,
            "rebalance_schedule": self.rebalance_schedule,
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)
