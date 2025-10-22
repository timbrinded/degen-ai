"""Strategy Governor for enforcing plan persistence and change governance."""

import json
from dataclasses import asdict, dataclass
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

    def __init__(self, config: GovernorConfig):
        """Initialize Strategy Governor.

        Args:
            config: Governor configuration
        """
        self.config = config
        self.active_plan: StrategyPlanCard | None = None
        self.last_change_at: datetime | None = None
        self.rebalance_schedule: list[dict] | None = None
        self._load_state()

    def can_review_plan(self, current_time: datetime) -> tuple[bool, str]:
        """Check if plan review is permitted.

        Args:
            current_time: Current timestamp

        Returns:
            Tuple of (can_review, reason_string)
        """
        if self.active_plan is None:
            return True, "No active plan"

        # Check dwell time
        if self.active_plan.activated_at:
            dwell_elapsed = (current_time - self.active_plan.activated_at).total_seconds() / 60
            if dwell_elapsed < self.active_plan.minimum_dwell_minutes:
                return (
                    False,
                    f"Dwell time not met: {dwell_elapsed:.1f}/{self.active_plan.minimum_dwell_minutes} min",
                )

        # Check cooldown
        if self.last_change_at:
            cooldown_elapsed = (current_time - self.last_change_at).total_seconds() / 60
            if cooldown_elapsed < self.config.cooldown_after_change_minutes:
                return (
                    False,
                    f"Cooldown active: {cooldown_elapsed:.1f}/{self.config.cooldown_after_change_minutes} min",
                )

        # Check rebalancing
        if self.active_plan.status == "rebalancing":
            return False, "Rebalancing in progress"

        return True, "Review permitted"

    def evaluate_change_proposal(self, proposal: PlanChangeProposal) -> tuple[bool, str]:
        """Evaluate whether to approve a plan change.

        Args:
            proposal: Plan change proposal to evaluate

        Returns:
            Tuple of (approved, reason_string)
        """
        if proposal.net_advantage_bps < self.config.minimum_advantage_over_cost_bps:
            return (
                False,
                f"Insufficient advantage: {proposal.net_advantage_bps:.1f} < {self.config.minimum_advantage_over_cost_bps} bps",
            )

        return True, f"Approved: {proposal.net_advantage_bps:.1f} bps net advantage"

    def activate_plan(self, plan: StrategyPlanCard, current_time: datetime):
        """Activate a new plan.

        Args:
            plan: Strategy plan card to activate
            current_time: Current timestamp
        """
        plan.activated_at = current_time
        plan.status = "active"
        self.active_plan = plan
        self.last_change_at = current_time
        self._persist_state()

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

            steps.append({"step": step + 1, "progress_pct": progress * 100, "allocations": step_allocations})

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
