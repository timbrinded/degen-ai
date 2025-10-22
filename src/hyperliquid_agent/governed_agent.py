"""Governed Trading Agent orchestration with multi-timescale decision-making."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn

from hyperliquid_agent.agent import TradingAgent
from hyperliquid_agent.config import Config
from hyperliquid_agent.decision import TradeAction
from hyperliquid_agent.governance.governor import (
    GovernorConfig,
    PlanChangeProposal,
    StrategyGovernor,
)
from hyperliquid_agent.governance.plan_card import ChangeCostModel, StrategyPlanCard
from hyperliquid_agent.governance.regime import (
    RegimeDetector,
    RegimeDetectorConfig,
    RegimeSignals,
)
from hyperliquid_agent.governance.scorekeeper import PlanScorekeeper
from hyperliquid_agent.governance.tripwire import (
    TripwireAction,
    TripwireConfig,
    TripwireService,
)
from hyperliquid_agent.monitor_enhanced import EnhancedPositionMonitor
from hyperliquid_agent.signals import EnhancedAccountState


@dataclass
class GovernedAgentConfig:
    """Configuration for governed trading agent."""

    governor: GovernorConfig
    regime_detector: RegimeDetectorConfig
    tripwire: TripwireConfig
    fast_loop_interval_seconds: int = 10
    medium_loop_interval_minutes: int = 30
    slow_loop_interval_hours: int = 24


@dataclass
class TradingConstants:
    """Constants for trading calculations to avoid magic numbers."""

    # Allocation thresholds
    ALLOCATION_GAP_THRESHOLD_PCT: float = 1.0  # Only trade if gap exceeds this

    # Fee estimates (basis points)
    MAKER_FEE_BPS: float = 2.0
    TAKER_FEE_BPS: float = 5.0
    AVG_FEE_BPS: float = 3.5  # Mixed maker/taker

    # Slippage estimates (basis points)
    BASE_SLIPPAGE_BPS: float = 3.0
    ENTRY_SLIPPAGE_BPS: float = 5.0
    ENTRY_FEE_BPS: float = 10.0

    # Funding estimates (basis points)
    CARRY_LOSS_BPS: float = 10.0  # Lost funding when exiting carry
    CARRY_GAIN_BPS: float = 5.0  # Gained funding when entering carry

    # Scorekeeper
    DEFAULT_SLIPPAGE_BPS: float = 5.0


class GovernedTradingAgent:
    """Main governed trading agent with multi-timescale decision-making.

    Wraps the existing TradingAgent with governance layer that enforces:
    - Fast loop (seconds): Deterministic execution following active plan
    - Medium loop (minutes-hours): Tactical planning and plan maintenance
    - Slow loop (daily-weekly): Regime detection and macro analysis
    """

    def __init__(self, config: Config, governance_config: GovernedAgentConfig):
        """Initialize the governed trading agent.

        Args:
            config: Base trading agent configuration
            governance_config: Governance-specific configuration
        """
        self.config = config
        self.governance_config = governance_config

        # Initialize base agent components (but don't use its run loop)
        self.base_agent = TradingAgent(config)

        # Initialize governance components
        self.governor = StrategyGovernor(governance_config.governor)
        self.regime_detector = RegimeDetector(governance_config.regime_detector)
        self.tripwire_service = TripwireService(governance_config.tripwire)
        self.scorekeeper = PlanScorekeeper()

        # Initialize enhanced monitor
        self.monitor = EnhancedPositionMonitor(config.hyperliquid)

        # Loop timing tracking
        self.last_medium_loop: datetime | None = None
        self.last_slow_loop: datetime | None = None

        # Use base agent's logger
        self.logger = self.base_agent.logger

        # Tick counter
        self.tick_count = 0

        # Trading constants
        self.constants = TradingConstants()

    def run(self) -> NoReturn:
        """Run the main governed loop indefinitely."""
        self.logger.info(
            "Starting governed trading agent",
            extra={
                "fast_loop_interval": self.governance_config.fast_loop_interval_seconds,
                "medium_loop_interval": self.governance_config.medium_loop_interval_minutes,
                "slow_loop_interval": self.governance_config.slow_loop_interval_hours,
            },
        )

        while True:
            self.tick_count += 1
            current_time = datetime.now()

            try:
                # TODO: Turn this into async parallel processes
                # Determine which loops to run
                run_fast = True
                run_medium = self._should_run_medium_loop(current_time)
                run_slow = self._should_run_slow_loop(current_time)

                # Execute loops in order: slow -> medium -> fast
                if run_slow:
                    self._execute_slow_loop(current_time)
                    self.last_slow_loop = current_time

                if run_medium:
                    self._execute_medium_loop(current_time)
                    self.last_medium_loop = current_time

                if run_fast:
                    self._execute_fast_loop(current_time)

            except Exception as e:
                self.logger.error(
                    f"Governed loop tick {self.tick_count} failed",
                    exc_info=e,
                    extra={"tick": self.tick_count},
                )

            # Sleep until next fast loop iteration
            time.sleep(self.governance_config.fast_loop_interval_seconds)

    def _should_run_medium_loop(self, current_time: datetime) -> bool:
        """Check if medium loop should run based on elapsed time.

        Args:
            current_time: Current timestamp

        Returns:
            True if medium loop should execute
        """
        if self.last_medium_loop is None:
            return True

        elapsed_minutes = (current_time - self.last_medium_loop).total_seconds() / 60
        return elapsed_minutes >= self.governance_config.medium_loop_interval_minutes

    def _should_run_slow_loop(self, current_time: datetime) -> bool:
        """Check if slow loop should run based on elapsed time.

        Args:
            current_time: Current timestamp

        Returns:
            True if slow loop should execute
        """
        if self.last_slow_loop is None:
            return True

        elapsed_hours = (current_time - self.last_slow_loop).total_seconds() / 3600
        return elapsed_hours >= self.governance_config.slow_loop_interval_hours

    def _handle_tripwire_events(self, tripwire_events: list) -> bool:
        """Handle tripwire events and determine if execution should be skipped.

        Args:
            tripwire_events: List of triggered tripwire events

        Returns:
            True if execution should be skipped, False otherwise
        """
        for event in tripwire_events:
            self.logger.warning(
                f"Tripwire fired: {event.trigger} ({event.severity})",
                extra={
                    "tick": self.tick_count,
                    "severity": event.severity,
                    "category": event.category,
                    "trigger": event.trigger,
                    "action": event.action.value,
                    "details": event.details,
                },
            )

            # Use match/case for cleaner control flow (Python 3.10+)
            match event.action:
                case TripwireAction.INVALIDATE_PLAN:
                    if self.governor.active_plan:
                        self.governor.active_plan.status = "invalidated"
                        self.logger.warning(
                            f"Plan {self.governor.active_plan.plan_id} invalidated by tripwire",
                            extra={
                                "tick": self.tick_count,
                                "plan_id": self.governor.active_plan.plan_id,
                            },
                        )

                case TripwireAction.FREEZE_NEW_RISK:
                    self.logger.warning(
                        "Freezing new risk - skipping plan execution",
                        extra={"tick": self.tick_count},
                    )
                    return True

                case TripwireAction.CUT_SIZE_TO_FLOOR:
                    self.logger.critical(
                        "Cut size to floor triggered - emergency risk reduction needed",
                        extra={"tick": self.tick_count},
                    )
                    # TODO: Implement emergency position reduction
                    return True

                case TripwireAction.ESCALATE_TO_SLOW_LOOP:
                    self.logger.warning(
                        "Escalating to slow loop for regime re-evaluation",
                        extra={"tick": self.tick_count},
                    )
                    self.last_slow_loop = None  # Force slow loop next iteration

        return False

    def _generate_rebalance_actions(
        self,
        target_allocations_data: list[dict],
        current_allocations: dict[str, float],
        total_value: float,
        account_state: EnhancedAccountState,
    ) -> list[TradeAction]:
        """Generate trade actions to rebalance portfolio to target allocations.

        Args:
            target_allocations_data: List of target allocation dicts
            current_allocations: Current allocation percentages by coin
            total_value: Total portfolio value
            account_state: Current account state with positions

        Returns:
            List of TradeAction objects to execute
        """
        actions = []

        for target_data in target_allocations_data:
            coin = str(target_data["coin"])
            target_pct = float(target_data["target_pct"])
            market_type = str(target_data["market_type"])

            current_pct = current_allocations.get(coin, 0.0)
            gap_pct = target_pct - current_pct

            # Only trade if gap exceeds threshold
            if abs(gap_pct) > self.constants.ALLOCATION_GAP_THRESHOLD_PCT:
                # Calculate size needed
                target_value = (target_pct / 100) * total_value
                current_value = (current_pct / 100) * total_value
                value_gap = target_value - current_value

                # Find current price
                matching_pos = next((p for p in account_state.positions if p.coin == coin), None)
                if matching_pos:
                    current_price = matching_pos.current_price
                else:
                    self.logger.warning(
                        f"Cannot determine price for {coin} - no existing position",
                        extra={"tick": self.tick_count, "coin": coin},
                    )
                    continue

                # Calculate size to trade
                size = abs(value_gap / current_price) if current_price > 0 else 0.0

                if size > 0:
                    action_type = "buy" if gap_pct > 0 else "sell"
                    # Validate market_type is correct literal
                    if market_type not in ["spot", "perp"]:
                        market_type = "perp"  # Default to perp

                    actions.append(
                        TradeAction(
                            action_type=action_type,  # type: ignore
                            coin=coin,
                            market_type=market_type,  # type: ignore
                            size=size,
                            price=None,  # Market order
                            reasoning=f"Rebalancing to target: {current_pct:.1f}% -> {target_pct:.1f}%",
                        )
                    )

                    self.logger.info(
                        f"Generated {action_type} action for {coin}: {size:.4f} (gap: {gap_pct:.1f}%)",
                        extra={
                            "tick": self.tick_count,
                            "coin": coin,
                            "action_type": action_type,
                            "size": size,
                            "current_pct": current_pct,
                            "target_pct": target_pct,
                            "gap_pct": gap_pct,
                        },
                    )

        return actions

    def _execute_fast_loop(self, current_time: datetime):
        """Execute fast loop: follow active plan deterministically.

        Fast loop responsibilities:
        - Collect fast signals from enhanced monitor
        - Check all tripwires for safety violations
        - Handle tripwire events (freeze, invalidate, etc.)
        - Execute active plan targets if plan is active
        - Update scorekeeper metrics

        Args:
            current_time: Current timestamp
        """
        self.logger.info(
            "Fast loop: executing active plan",
            extra={"tick": self.tick_count, "loop_type": "fast"},
        )

        # Get account state with fast signals
        try:
            account_state = self.monitor.get_current_state_with_signals("fast")
        except Exception as e:
            self.logger.error(
                "Failed to retrieve account state in fast loop",
                exc_info=e,
                extra={"tick": self.tick_count},
            )
            self.tripwire_service.record_api_failure()
            return

        # Reset API failure count on success
        self.tripwire_service.reset_api_failure_count()

        # Log account state
        self.logger.info(
            "Account state retrieved",
            extra={
                "tick": self.tick_count,
                "portfolio_value": account_state.portfolio_value,
                "available_balance": account_state.available_balance,
                "num_positions": len(account_state.positions),
                "is_stale": account_state.is_stale,
            },
        )

        # Check all tripwires
        tripwire_events = self.tripwire_service.check_all_tripwires(
            account_state, self.governor.active_plan
        )

        # Handle tripwire events
        should_skip_execution = self._handle_tripwire_events(tripwire_events)
        if should_skip_execution:
            return

        # Execute active plan if exists and is active
        if self.governor.active_plan and self.governor.active_plan.status == "active":
            self._execute_plan_targets(account_state, self.governor.active_plan)
        elif self.governor.active_plan and self.governor.active_plan.status == "rebalancing":
            self.logger.info(
                "Plan is rebalancing - executing rebalance schedule",
                extra={"tick": self.tick_count, "plan_id": self.governor.active_plan.plan_id},
            )
            self._execute_plan_targets(account_state, self.governor.active_plan)
        else:
            self.logger.info(
                "No active plan to execute",
                extra={"tick": self.tick_count},
            )

        # Update scorekeeper metrics
        if self.governor.active_plan:
            self.scorekeeper.update_metrics(account_state, self.governor.active_plan)

    def _execute_medium_loop(self, current_time: datetime):
        """Execute medium loop: plan review and maintenance.

        Medium loop responsibilities:
        - Collect medium signals from enhanced monitor
        - Classify regime and update regime detector
        - Check if plan review is permitted (dwell time, cooldown, event lock)
        - Override dwell time if regime changed
        - Query LLM for plan decision when review permitted
        - Process plan change proposals

        Args:
            current_time: Current timestamp
        """
        self.logger.info(
            "Medium loop: plan review and maintenance",
            extra={"tick": self.tick_count, "loop_type": "medium"},
        )

        # Get account state with medium signals
        try:
            account_state = self.monitor.get_current_state_with_signals("medium")
        except Exception as e:
            self.logger.error(
                "Failed to retrieve account state in medium loop",
                exc_info=e,
                extra={"tick": self.tick_count},
            )
            return

        # Extract regime signals and classify regime
        regime_signals = self._extract_regime_signals(account_state)
        classification = self.regime_detector.classify_regime(regime_signals)

        self.logger.info(
            f"Regime classified: {classification.regime} (confidence: {classification.confidence:.2f})",
            extra={
                "tick": self.tick_count,
                "regime": classification.regime,
                "confidence": classification.confidence,
            },
        )

        # Update regime detector and check for regime change
        regime_changed, regime_msg = self.regime_detector.update_and_confirm(classification)

        if regime_changed:
            self.logger.info(
                f"Regime change confirmed: {regime_msg}",
                extra={"tick": self.tick_count, "regime_change": regime_msg},
            )

        # Check if plan review is permitted
        can_review, review_msg = self.governor.can_review_plan(current_time)

        # Check event lock window
        in_event_lock, event_msg = self.regime_detector.is_in_event_lock_window(current_time)
        if in_event_lock:
            self.logger.info(
                f"Plan review blocked by event lock: {event_msg}",
                extra={"tick": self.tick_count, "event_lock": event_msg},
            )
            return

        # Override dwell time if regime changed
        if regime_changed:
            can_review = True
            review_msg = f"Regime change override: {regime_msg}"
            self.logger.info(
                "Dwell time overridden due to regime change",
                extra={"tick": self.tick_count, "override_reason": regime_msg},
            )

        if not can_review:
            self.logger.info(
                f"Plan review not permitted: {review_msg}",
                extra={"tick": self.tick_count, "review_status": review_msg},
            )
            return

        # Plan review is permitted - query LLM for decision
        self.logger.info(
            "Plan review permitted - querying LLM for decision",
            extra={"tick": self.tick_count, "review_reason": review_msg},
        )

        # Get decision from LLM (using base agent's decision engine)
        # Note: This uses the standard decision engine for now
        # In a full implementation, we would extend DecisionEngine with governance support
        decision = self.base_agent.decision_engine.get_decision(account_state)

        if not decision.success:
            self.logger.error(
                f"Decision engine failed: {decision.error}",
                extra={"tick": self.tick_count, "error": decision.error},
            )
            return

        # Log LLM response
        self.logger.info(
            f"LLM decision received: {len(decision.actions)} actions, strategy: {decision.selected_strategy}",
            extra={
                "tick": self.tick_count,
                "num_actions": len(decision.actions),
                "selected_strategy": decision.selected_strategy,
                "llm_cost_usd": decision.cost_usd,
            },
        )

        # Check if LLM is proposing a strategy change
        # If selected_strategy differs from active plan, treat as plan change proposal
        if decision.selected_strategy and self.governor.active_plan:
            if decision.selected_strategy != self.governor.active_plan.strategy_name:
                self.logger.info(
                    f"LLM proposing strategy change: {self.governor.active_plan.strategy_name} -> {decision.selected_strategy}",
                    extra={
                        "tick": self.tick_count,
                        "old_strategy": self.governor.active_plan.strategy_name,
                        "new_strategy": decision.selected_strategy,
                    },
                )
                # Would create a new StrategyPlanCard from the LLM decision
                # For now, log that a change was proposed but don't implement
                self.logger.info(
                    "Plan change proposal detected but not implemented (requires full LLM governance integration)",
                    extra={"tick": self.tick_count},
                )
        elif decision.selected_strategy and not self.governor.active_plan:
            self.logger.info(
                f"LLM selected initial strategy: {decision.selected_strategy}",
                extra={"tick": self.tick_count, "strategy": decision.selected_strategy},
            )
            # Would create initial StrategyPlanCard
            # For now, just log
        else:
            self.logger.info(
                "LLM maintaining current plan or no strategy selected",
                extra={"tick": self.tick_count},
            )

    def _execute_slow_loop(self, current_time: datetime):
        """Execute slow loop: regime detection and macro analysis.

        Slow loop responsibilities:
        - Collect slow signals from enhanced monitor
        - Update macro calendar
        - Force regime re-evaluation
        - Log regime status

        Args:
            current_time: Current timestamp
        """
        self.logger.info(
            "Slow loop: macro analysis and regime detection",
            extra={"tick": self.tick_count, "loop_type": "slow"},
        )

        # Get account state with slow signals
        try:
            account_state = self.monitor.get_current_state_with_signals("slow")
        except Exception as e:
            self.logger.error(
                "Failed to retrieve account state in slow loop",
                exc_info=e,
                extra={"tick": self.tick_count},
            )
            return

        # Update macro calendar
        # In a full implementation, this would fetch upcoming macro events
        # For now, we'll just log that the calendar would be updated
        self.logger.info(
            "Macro calendar update (placeholder - would fetch FOMC, CPI, jobs reports, etc.)",
            extra={"tick": self.tick_count},
        )

        # Force regime re-evaluation with slow signals
        regime_signals = self._extract_regime_signals(account_state)
        classification = self.regime_detector.classify_regime(regime_signals)

        self.logger.info(
            f"Slow loop regime classification: {classification.regime} (confidence: {classification.confidence:.2f})",
            extra={
                "tick": self.tick_count,
                "regime": classification.regime,
                "confidence": classification.confidence,
                "current_regime": self.regime_detector.current_regime,
            },
        )

        # Check for structural market changes
        # This would analyze slow signals for major shifts
        if account_state.slow_signals:
            self.logger.info(
                "Slow signals collected for macro analysis",
                extra={
                    "tick": self.tick_count,
                    "has_macro_events": bool(account_state.slow_signals.macro_events_upcoming),
                },
            )

        # Log current regime status
        self.logger.info(
            f"Slow loop complete. Current regime: {self.regime_detector.current_regime}",
            extra={
                "tick": self.tick_count,
                "current_regime": self.regime_detector.current_regime,
                "regime_history_length": len(self.regime_detector.regime_history),
            },
        )

    def _handle_plan_change_proposal(self, proposed_plan: StrategyPlanCard, current_time: datetime):
        """Handle a proposed plan change from LLM.

        Args:
            proposed_plan: Proposed new strategy plan card
            current_time: Current timestamp
        """
        self.logger.info(
            f"Handling plan change proposal: {proposed_plan.strategy_name}",
            extra={
                "tick": self.tick_count,
                "proposed_strategy": proposed_plan.strategy_name,
                "current_strategy": self.governor.active_plan.strategy_name
                if self.governor.active_plan
                else None,
            },
        )

        # Calculate change cost
        change_cost = self._calculate_change_cost(self.governor.active_plan, proposed_plan)

        self.logger.info(
            f"Change cost calculated: {change_cost.total_cost_bps:.1f} bps",
            extra={
                "tick": self.tick_count,
                "total_cost_bps": change_cost.total_cost_bps,
                "fees_bps": change_cost.estimated_fees_bps,
                "slippage_bps": change_cost.estimated_slippage_bps,
                "funding_change_bps": change_cost.estimated_funding_change_bps,
                "opportunity_cost_bps": change_cost.opportunity_cost_bps,
            },
        )

        # Get expected advantage from proposed plan
        expected_advantage = proposed_plan.expected_edge_bps

        # Create plan change proposal
        proposal = PlanChangeProposal(
            new_plan=proposed_plan,
            reason="LLM proposal based on regime and market conditions",
            expected_advantage_bps=expected_advantage,
            change_cost_bps=change_cost.total_cost_bps,
        )

        # Evaluate proposal through governor
        approved, approval_msg = self.governor.evaluate_change_proposal(proposal)

        if approved:
            self.logger.info(
                f"Plan change approved: {approval_msg}",
                extra={
                    "tick": self.tick_count,
                    "net_advantage_bps": proposal.net_advantage_bps,
                    "approval_reason": approval_msg,
                },
            )

            # Finalize old plan if exists
            if self.governor.active_plan:
                # Get current portfolio value for finalization
                try:
                    current_state = self.monitor.get_current_state()
                    final_value = current_state.portfolio_value
                except Exception:
                    final_value = 0.0

                summary = self.scorekeeper.finalize_plan(final_value)
                self.logger.info(
                    f"Old plan finalized:\n{summary}",
                    extra={"tick": self.tick_count, "plan_id": self.governor.active_plan.plan_id},
                )

            # Create rebalance schedule for partial rotations
            if self.governor.active_plan:
                schedule = self.governor.create_rebalance_schedule(
                    self.governor.active_plan.target_allocations,
                    proposed_plan.target_allocations,
                )
                self.governor.rebalance_schedule = schedule
                proposed_plan.status = "rebalancing"

                self.logger.info(
                    f"Rebalance schedule created: {len(schedule)} steps",
                    extra={
                        "tick": self.tick_count,
                        "num_steps": len(schedule),
                        "rotation_pct_per_cycle": self.governance_config.governor.partial_rotation_pct_per_cycle,
                    },
                )

            # Activate new plan
            self.governor.activate_plan(proposed_plan, current_time)

            # Start tracking new plan
            try:
                current_state = self.monitor.get_current_state()
                initial_value = current_state.portfolio_value
            except Exception:
                initial_value = 0.0

            self.scorekeeper.start_tracking_plan(proposed_plan, initial_value)

            self.logger.info(
                f"New plan activated: {proposed_plan.plan_id}",
                extra={
                    "tick": self.tick_count,
                    "plan_id": proposed_plan.plan_id,
                    "strategy_name": proposed_plan.strategy_name,
                    "initial_value": initial_value,
                },
            )

        else:
            self.logger.info(
                f"Plan change rejected: {approval_msg}",
                extra={
                    "tick": self.tick_count,
                    "net_advantage_bps": proposal.net_advantage_bps,
                    "rejection_reason": approval_msg,
                },
            )

    def _execute_plan_targets(self, account_state: EnhancedAccountState, plan: StrategyPlanCard):
        """Execute trades to move toward plan targets.

        Args:
            account_state: Current enhanced account state
            plan: Active strategy plan card
        """
        self.logger.info(
            f"Executing plan targets for {plan.strategy_name}",
            extra={
                "tick": self.tick_count,
                "plan_id": plan.plan_id,
                "plan_status": plan.status,
            },
        )

        # Determine target allocations based on plan status
        if plan.status == "rebalancing" and self.governor.rebalance_schedule:
            # Use rebalance schedule for gradual rotation
            current_step = int(
                plan.rebalance_progress_pct
                / self.governance_config.governor.partial_rotation_pct_per_cycle
            )

            if current_step < len(self.governor.rebalance_schedule):
                step_data = self.governor.rebalance_schedule[current_step]
                target_allocations_data = step_data["allocations"]

                self.logger.info(
                    f"Using rebalance schedule step {current_step + 1}/{len(self.governor.rebalance_schedule)}",
                    extra={
                        "tick": self.tick_count,
                        "step": current_step + 1,
                        "total_steps": len(self.governor.rebalance_schedule),
                        "progress_pct": step_data["progress_pct"],
                    },
                )

                # Update rebalance progress
                plan.rebalance_progress_pct = step_data["progress_pct"]

                # Check if rebalancing is complete
                if current_step == len(self.governor.rebalance_schedule) - 1:
                    plan.status = "active"
                    self.governor.rebalance_schedule = None
                    self.logger.info(
                        "Rebalancing complete - plan now active",
                        extra={"tick": self.tick_count, "plan_id": plan.plan_id},
                    )
            else:
                # Rebalancing complete, use final targets
                target_allocations_data = [
                    {
                        "coin": alloc.coin,
                        "target_pct": alloc.target_pct,
                        "market_type": alloc.market_type,
                        "leverage": alloc.leverage,
                    }
                    for alloc in plan.target_allocations
                ]
        else:
            # Use plan's target allocations directly
            target_allocations_data = [
                {
                    "coin": alloc.coin,
                    "target_pct": alloc.target_pct,
                    "market_type": alloc.market_type,
                    "leverage": alloc.leverage,
                }
                for alloc in plan.target_allocations
            ]

        # Calculate current allocations
        current_allocations = {}
        total_value = account_state.portfolio_value

        for position in account_state.positions:
            position_value = position.size * position.current_price
            current_pct = (position_value / total_value * 100) if total_value > 0 else 0.0
            current_allocations[position.coin] = current_pct

        # Generate trade actions to close allocation gaps
        actions = self._generate_rebalance_actions(
            target_allocations_data, current_allocations, total_value, account_state
        )

        # Execute trades via base agent's executor
        if actions:
            self.logger.info(
                f"Executing {len(actions)} rebalancing trades",
                extra={"tick": self.tick_count, "num_actions": len(actions)},
            )

            for action in actions:
                try:
                    result = self.base_agent.executor.execute_action(action)

                    # Log execution result
                    log_level = logging.INFO if result.success else logging.ERROR
                    self.logger.log(
                        log_level,
                        f"Trade execution: {action.action_type} {action.coin} - {'success' if result.success else 'failed'}",
                        extra={
                            "tick": self.tick_count,
                            "action_type": action.action_type,
                            "coin": action.coin,
                            "success": result.success,
                            "order_id": result.order_id,
                            "error": result.error,
                        },
                    )

                    # Record trade in scorekeeper
                    if result.success:
                        # Would calculate actual slippage from execution
                        # For now, use estimated slippage
                        self.scorekeeper.record_trade(
                            is_winning=True, slippage_bps=self.constants.DEFAULT_SLIPPAGE_BPS
                        )

                except Exception as e:
                    self.logger.error(
                        f"Failed to execute trade: {action.action_type} {action.coin}",
                        exc_info=e,
                        extra={"tick": self.tick_count, "coin": action.coin},
                    )

            # Record rebalance event
            self.scorekeeper.record_rebalance()

        else:
            self.logger.info(
                "No rebalancing trades needed - allocations within threshold",
                extra={"tick": self.tick_count},
            )

    def _calculate_change_cost(
        self, old_plan: StrategyPlanCard | None, new_plan: StrategyPlanCard
    ) -> ChangeCostModel:
        """Calculate cost of changing from old plan to new plan.

        Estimates:
        - Fees based on position changes
        - Slippage based on order sizes and liquidity
        - Funding rate impact
        - Opportunity cost

        Args:
            old_plan: Current strategy plan card (if any)
            new_plan: Proposed new strategy plan card

        Returns:
            ChangeCostModel with estimated costs in basis points
        """
        if old_plan is None:
            # No existing plan - only entry costs
            return ChangeCostModel(
                estimated_fees_bps=self.constants.ENTRY_FEE_BPS,
                estimated_slippage_bps=self.constants.ENTRY_SLIPPAGE_BPS,
                estimated_funding_change_bps=0.0,  # No funding change
                opportunity_cost_bps=0.0,  # No opportunity cost
            )

        # Calculate position changes needed
        old_allocations = {alloc.coin: alloc.target_pct for alloc in old_plan.target_allocations}
        new_allocations = {alloc.coin: alloc.target_pct for alloc in new_plan.target_allocations}

        # Calculate total turnover (sum of absolute changes)
        all_coins = set(old_allocations.keys()) | set(new_allocations.keys())
        total_turnover_pct = 0.0

        for coin in all_coins:
            old_pct = old_allocations.get(coin, 0.0)
            new_pct = new_allocations.get(coin, 0.0)
            turnover = abs(new_pct - old_pct)
            total_turnover_pct += turnover

        # Estimate fees based on turnover
        # Hyperliquid typical fees: ~0.02% maker, ~0.05% taker
        # Assume mix of maker/taker orders
        avg_fee_rate = self.constants.AVG_FEE_BPS / 100.0  # Convert bps to percentage
        estimated_fees_bps = total_turnover_pct * avg_fee_rate

        # Estimate slippage based on turnover and market conditions
        # Higher turnover = more market impact
        # Scale with turnover
        slippage_multiplier = 1.0 + (total_turnover_pct / 100.0)  # Scale with turnover
        estimated_slippage_bps = self.constants.BASE_SLIPPAGE_BPS * slippage_multiplier

        # Estimate funding rate impact
        # If switching from carry strategy to non-carry, lose funding income
        # Simplified: check if strategies have different funding exposure
        estimated_funding_change_bps = 0.0

        if (
            "carry" in old_plan.strategy_name.lower()
            and "carry" not in new_plan.strategy_name.lower()
        ):
            # Losing carry income
            estimated_funding_change_bps = self.constants.CARRY_LOSS_BPS
        elif (
            "carry" not in old_plan.strategy_name.lower()
            and "carry" in new_plan.strategy_name.lower()
        ):
            # Gaining carry income
            estimated_funding_change_bps = -self.constants.CARRY_GAIN_BPS  # Negative cost = benefit

        # Estimate opportunity cost using scorekeeper
        opportunity_cost_bps = self.scorekeeper.estimate_opportunity_cost()

        # If opportunity cost is negative (current plan outperforming), set to 0
        # We only count positive opportunity cost (cost of staying)
        if opportunity_cost_bps < 0:
            opportunity_cost_bps = 0.0

        return ChangeCostModel(
            estimated_fees_bps=estimated_fees_bps,
            estimated_slippage_bps=estimated_slippage_bps,
            estimated_funding_change_bps=estimated_funding_change_bps,
            opportunity_cost_bps=opportunity_cost_bps,
        )

    def _extract_regime_signals(self, account_state: EnhancedAccountState) -> RegimeSignals:
        """Extract regime signals from enhanced account state.

        Maps relevant fields from EnhancedAccountState to RegimeSignals dataclass.

        Args:
            account_state: Enhanced account state with signals

        Returns:
            RegimeSignals for regime classification
        """
        # Extract signals from medium signals if available
        if account_state.medium_signals:
            medium = account_state.medium_signals

            # Use medium signals for regime classification
            return RegimeSignals(
                # Trend indicators
                price_sma_20=medium.sma_20 if hasattr(medium, "sma_20") else 0.0,
                price_sma_50=medium.sma_50 if hasattr(medium, "sma_50") else 0.0,
                adx=medium.adx if hasattr(medium, "adx") else 0.0,
                # Volatility
                realized_vol_24h=medium.realized_vol_24h
                if hasattr(medium, "realized_vol_24h")
                else 0.0,
                # Funding/Carry
                avg_funding_rate=medium.avg_funding_rate
                if hasattr(medium, "avg_funding_rate")
                else 0.0,
                # Liquidity
                bid_ask_spread_bps=medium.avg_spread_bps
                if hasattr(medium, "avg_spread_bps")
                else 0.0,
                order_book_depth=medium.avg_order_book_depth
                if hasattr(medium, "avg_order_book_depth")
                else 0.0,
                # Enhanced signals (optional)
                cross_asset_correlation=None,
                macro_risk_score=None,
                sentiment_index=None,
                volatility_regime=None,
            )

        # Fallback: use default/placeholder values if signals not available
        self.logger.warning(
            "Medium signals not available - using placeholder regime signals",
            extra={"tick": self.tick_count},
        )

        return RegimeSignals(
            price_sma_20=0.0,
            price_sma_50=0.0,
            adx=0.0,
            realized_vol_24h=0.0,
            avg_funding_rate=0.0,
            bid_ask_spread_bps=0.0,
            order_book_depth=0.0,
        )
