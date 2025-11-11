"""Governed Trading Agent orchestration with multi-timescale decision-making."""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn

from hyperliquid.info import Info

from hyperliquid_agent.agent import TradingAgent
from hyperliquid_agent.asset_identity import AssetIdentity
from hyperliquid_agent.config import Config
from hyperliquid_agent.decision import TradeAction
from hyperliquid_agent.executor import TradeExecutor
from hyperliquid_agent.governance.governor import (
    GovernorConfig,
    PlanChangeProposal,
    StrategyGovernor,
)
from hyperliquid_agent.governance.plan_card import ChangeCostModel, StrategyPlanCard
from hyperliquid_agent.governance.regime import (
    PriceContext,
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
from hyperliquid_agent.identity_registry import AssetIdentityRegistry, default_assets_config_path
from hyperliquid_agent.market_registry import MarketRegistry
from hyperliquid_agent.monitor import Position
from hyperliquid_agent.monitor_enhanced import EnhancedPositionMonitor
from hyperliquid_agent.price_service import AssetPriceService
from hyperliquid_agent.signals import EnhancedAccountState, MediumLoopSignals, TechnicalIndicators


@dataclass
class GovernedAgentConfig:
    """Configuration for governed trading agent."""

    governor: GovernorConfig
    regime_detector: RegimeDetectorConfig
    tripwire: TripwireConfig
    fast_loop_interval_seconds: int = 10
    medium_loop_interval_minutes: int = 30
    slow_loop_interval_hours: int = 24
    emergency_reduction_pct: float = 100.0  # Percentage of positions to close in emergency


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

        # Initialize market registry (will be hydrated during startup)
        self.info = Info(config.hyperliquid.base_url, skip_ws=True)
        self.registry = MarketRegistry(self.info)

        # Load asset identity registry for unified symbol handling
        assets_config = default_assets_config_path()
        self.identity_registry = AssetIdentityRegistry(assets_config, self.info)
        try:
            self.identity_registry.load()
        except Exception as exc:  # pragma: no cover - startup failure must surface
            raise RuntimeError(f"Failed to load asset identity registry: {exc}") from exc

        self.price_service = AssetPriceService(self.info, self.identity_registry)

        # Initialize executor with registry
        self.executor = TradeExecutor(
            config.hyperliquid,
            self.registry,
            identity_registry=self.identity_registry,
            risk_config=config.risk,
        )

        # Initialize governance components with logger
        self.governor = StrategyGovernor(governance_config.governor, logger=self.base_agent.logger)
        self.regime_detector = RegimeDetector(
            config=governance_config.regime_detector,
            llm_config=config.llm,  # Pass main LLM config for reuse
            logger=self.base_agent.logger,
        )
        self.tripwire_service = TripwireService(
            governance_config.tripwire, logger=self.base_agent.logger
        )
        self.scorekeeper = PlanScorekeeper(logger=self.base_agent.logger)

        # Initialize enhanced monitor
        self.monitor = EnhancedPositionMonitor(
            config.hyperliquid,
            identity_registry=self.identity_registry,
            price_service=self.price_service,
        )

        # Loop timing tracking
        self.last_medium_loop: datetime | None = None
        self.last_slow_loop: datetime | None = None

        # Use base agent's logger
        self.logger = self.base_agent.logger

        # Tick counter
        self.tick_count = 0

        # Trading constants
        self.constants = TradingConstants()

        # Track which tripwires are currently active to suppress duplicate actions
        self._active_tripwire_triggers: set[str] = set()

        # Note: _startup_hydration() is called explicitly in run() and run_async()
        # BEFORE the main loop starts to ensure proper initialization sequence

    async def _startup_hydration_async(self):
        """Hydrate system with initial data before starting trading loops.

        Performs comprehensive startup initialization:
        0. Hydrate market registry with all available markets
        1. Pre-warms watchlist prices
        2. Collects initial signals (fast, medium) to populate caches
        3. Performs initial regime classification
        4. Ensures all components are ready before trading begins

        This prevents race conditions and ensures regime/signals are available
        on first trading decision.
        """
        self.logger.info("Starting startup hydration sequence...")

        try:
            # Step 0: Hydrate market registry
            self.logger.info("Step 0/5: Hydrating market registry...")
            await self.registry.hydrate()
            self.logger.info("Step 0/5: Market registry hydrated successfully")

            # Step 1: Get base account state
            base_state = self.monitor.get_current_state()
            self.logger.info(
                "Step 1/5: Retrieved base account state",
                extra={"portfolio_value": base_state.portfolio_value},
            )

            # Step 2: Pre-warm watchlist prices
            watchlist = self.monitor.build_watchlist(base_state, self.governor.active_plan)
            price_map = self.monitor.fetch_watchlist_prices(watchlist)
            self.logger.info(
                f"Step 2/5: Pre-warmed {len(price_map)}/{len(watchlist)} watchlist prices",
                extra={"watchlist": sorted(watchlist), "prices_fetched": len(price_map)},
            )

            # Step 3: Hydrate signal caches (fast and medium)
            # This populates technical indicators, funding rates, etc.
            self.logger.info("Step 3/5: Hydrating signal caches...")
            account_state_medium = None  # Initialize to avoid unbound variable
            try:
                # Collect fast signals to warm cache
                account_state_fast = self.monitor.get_current_state_with_signals(
                    "fast", active_plan=self.governor.active_plan
                )
                self.logger.info(
                    "  - Fast signals collected",
                    extra={
                        "has_fast_signals": account_state_fast.fast_signals is not None,
                        "is_cached": (
                            account_state_fast.fast_signals.metadata.is_cached
                            if account_state_fast.fast_signals
                            else None
                        ),
                        "staleness_seconds": (
                            account_state_fast.fast_signals.metadata.staleness_seconds
                            if account_state_fast.fast_signals
                            else None
                        ),
                    },
                )

                # Collect medium signals to warm cache and populate technical indicators
                account_state_medium = self.monitor.get_current_state_with_signals(
                    "medium", active_plan=self.governor.active_plan
                )
                self.logger.info(
                    "  - Medium signals collected",
                    extra={
                        "has_medium_signals": account_state_medium.medium_signals is not None,
                        "technical_indicators_count": (
                            len(account_state_medium.medium_signals.technical_indicators)
                            if account_state_medium.medium_signals
                            else 0
                        ),
                        "is_cached": (
                            account_state_medium.medium_signals.metadata.is_cached
                            if account_state_medium.medium_signals
                            else None
                        ),
                        "staleness_seconds": (
                            account_state_medium.medium_signals.metadata.staleness_seconds
                            if account_state_medium.medium_signals
                            else None
                        ),
                    },
                )
            except Exception as e:
                self.logger.warning(
                    f"Signal hydration encountered errors (non-critical): {e}",
                    exc_info=True,
                )

            # Step 4: Perform initial regime classification
            self.logger.info("Step 4/5: Performing initial regime classification...")
            try:
                # Use medium signals from hydration
                if account_state_medium and account_state_medium.medium_signals:
                    regime_signals = self._extract_regime_signals(account_state_medium)
                    classification = self.regime_detector.classify_regime(regime_signals)

                    self.logger.info(
                        f"  - Initial regime: {classification.regime} "
                        f"(confidence: {classification.confidence:.2f})",
                        extra={
                            "regime": classification.regime,
                            "confidence": classification.confidence,
                            "reasoning": classification.reasoning,
                        },
                    )

                    # Update regime detector with initial classification
                    self.regime_detector.update_and_confirm(classification)
                else:
                    self.logger.warning(
                        "  - Could not perform initial regime classification "
                        "(medium signals unavailable)"
                    )
            except Exception as e:
                self.logger.warning(
                    f"Initial regime classification failed (non-critical): {e}",
                    exc_info=True,
                )

            self.logger.info(
                "✓ Startup hydration complete - system ready for trading",
                extra={
                    "watchlist_size": len(watchlist),
                    "prices_available": len(price_map),
                    "current_regime": self.regime_detector.current_regime,
                },
            )

        except Exception as e:
            # Log error but don't crash - system can recover during first loop
            self.logger.error(
                f"Startup hydration failed: {e}. System will attempt to initialize during first loop.",
                exc_info=True,
            )

    def _startup_hydration(self) -> None:
        """Synchronously hydrate startup state, guarding against nested event loops."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._startup_hydration_async())
        else:
            raise RuntimeError(
                "GovernedTradingAgent.run() cannot be invoked while an event loop is running. "
                "Use run_async() instead."
            )

    def run(self) -> NoReturn:
        """Run the main governed loop indefinitely (synchronous version for backward compatibility)."""
        self.logger.info(
            "Starting governed trading agent (sync mode)",
            extra={
                "fast_loop_interval": self.governance_config.fast_loop_interval_seconds,
                "medium_loop_interval": self.governance_config.medium_loop_interval_minutes,
                "slow_loop_interval": self.governance_config.slow_loop_interval_hours,
            },
        )

        # Perform startup hydration before entering main loop
        self._startup_hydration()

        while True:
            self.tick_count += 1
            current_time = datetime.now()

            try:
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

    async def run_async(self) -> NoReturn:
        """Run the main governed loop indefinitely with async concurrent execution.

        This method executes fast, medium, and slow loops concurrently using asyncio.gather,
        preventing slow loop operations from blocking time-sensitive fast loop execution.
        """
        self.logger.info(
            "Starting governed trading agent (async mode)",
            extra={
                "fast_loop_interval": self.governance_config.fast_loop_interval_seconds,
                "medium_loop_interval": self.governance_config.medium_loop_interval_minutes,
                "slow_loop_interval": self.governance_config.slow_loop_interval_hours,
            },
        )

        # Perform startup hydration before entering main loop
        await self._startup_hydration_async()

        while True:
            self.tick_count += 1
            current_time = datetime.now()

            # Determine which loops to run
            run_fast = True
            run_medium = self._should_run_medium_loop(current_time)
            run_slow = self._should_run_slow_loop(current_time)

            # Build task list for concurrent execution
            tasks = []

            if run_slow:
                tasks.append(self._execute_slow_loop_async(current_time))

            if run_medium:
                tasks.append(self._execute_medium_loop_async(current_time))

            if run_fast:
                tasks.append(self._execute_fast_loop_async(current_time))

            # Execute all loops concurrently
            # return_exceptions=True prevents one loop failure from stopping others
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Log any exceptions
                loop_types = []
                if run_slow:
                    loop_types.append("slow")
                if run_medium:
                    loop_types.append("medium")
                if run_fast:
                    loop_types.append("fast")

                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        loop_type = loop_types[i] if i < len(loop_types) else "unknown"
                        self.logger.error(
                            f"{loop_type} loop failed",
                            exc_info=result,
                            extra={"tick": self.tick_count, "loop_type": loop_type},
                        )

            # Update last execution times
            if run_slow:
                self.last_slow_loop = current_time
            if run_medium:
                self.last_medium_loop = current_time

            # Sleep until next fast loop tick
            await asyncio.sleep(self.governance_config.fast_loop_interval_seconds)

    async def _execute_slow_loop_async(self, current_time: datetime):
        """Async wrapper for slow loop execution.

        Args:
            current_time: Current timestamp
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._execute_slow_loop, current_time)

    async def _execute_medium_loop_async(self, current_time: datetime):
        """Async wrapper for medium loop execution.

        Args:
            current_time: Current timestamp
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._execute_medium_loop, current_time)

    async def _execute_fast_loop_async(self, current_time: datetime):
        """Async wrapper for fast loop execution.

        Args:
            current_time: Current timestamp
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._execute_fast_loop, current_time)

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
        skip_execution = False
        current_triggers: set[str] = set()

        for event in tripwire_events:
            current_triggers.add(event.trigger)
            already_active = bool(event.details.get("already_active")) or (
                event.trigger in self._active_tripwire_triggers
            )

            if already_active:
                self.logger.debug(
                    "Tripwire still active: %s (%s)",
                    event.trigger,
                    event.severity,
                    extra={
                        "tick": self.tick_count,
                        "trigger": event.trigger,
                        "action": event.action.value,
                        "details": event.details,
                    },
                )
                if event.action in {
                    TripwireAction.CUT_SIZE_TO_FLOOR,
                    TripwireAction.FREEZE_NEW_RISK,
                }:
                    skip_execution = True
                if event.action == TripwireAction.ESCALATE_TO_SLOW_LOOP:
                    self.last_slow_loop = None
                continue

            self._active_tripwire_triggers.add(event.trigger)

            log_extra = {
                "tick": self.tick_count,
                "severity": event.severity,
                "category": event.category,
                "trigger": event.trigger,
                "action": event.action.value,
                "details": event.details,
            }

            log_fn = self.logger.warning
            if event.severity == "critical":
                log_fn = self.logger.critical

            log_fn(f"Tripwire fired: {event.trigger} ({event.severity})", extra=log_extra)

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
                    skip_execution = True

                case TripwireAction.CUT_SIZE_TO_FLOOR:
                    self.logger.critical(
                        "Cut size to floor triggered - emergency risk reduction needed",
                        extra={"tick": self.tick_count},
                    )
                    self._handle_tripwire_action(event.action)
                    skip_execution = True
                    self.last_slow_loop = None  # Force regime reassessment ASAP
                    if self.governor.active_plan:
                        self.governor.active_plan.status = "invalidated"
                        self.logger.warning(
                            f"Plan {self.governor.active_plan.plan_id} invalidated after emergency reduction",
                            extra={
                                "tick": self.tick_count,
                                "plan_id": self.governor.active_plan.plan_id,
                            },
                        )

                case TripwireAction.ESCALATE_TO_SLOW_LOOP:
                    self.logger.warning(
                        "Escalating to slow loop for regime re-evaluation",
                        extra={"tick": self.tick_count},
                    )
                    self.last_slow_loop = None

        if not tripwire_events:
            self._active_tripwire_triggers.clear()
        else:
            stale = {
                trigger
                for trigger in list(self._active_tripwire_triggers)
                if trigger not in current_triggers
            }
            for trigger in stale:
                self._active_tripwire_triggers.discard(trigger)

        return skip_execution

    def _handle_tripwire_action(self, action: TripwireAction) -> bool:
        """Handle tripwire action for emergency position reduction.

        Args:
            action: Tripwire action to handle

        Returns:
            True if action was handled successfully, False otherwise
        """
        if action != TripwireAction.CUT_SIZE_TO_FLOOR:
            self.logger.warning(
                f"Unhandled tripwire action: {action}",
                extra={"tick": self.tick_count, "action": action.value},
            )
            return False

        self.logger.critical(
            "Executing emergency position reduction",
            extra={
                "tick": self.tick_count,
                "reduction_pct": self.governance_config.emergency_reduction_pct,
            },
        )

        # Get current positions
        try:
            account_state = self.monitor.get_current_state()
        except Exception as e:
            self.logger.critical(
                "Failed to retrieve account state for emergency reduction",
                exc_info=e,
                extra={"tick": self.tick_count},
            )
            return False

        # Calculate reduction percentage from config
        reduction_pct = self.governance_config.emergency_reduction_pct

        # Generate emergency exit orders
        exit_results = []
        for position in account_state.positions:
            if position.size <= 0:
                continue

            # Calculate size to close
            size_to_close = position.size * (reduction_pct / 100.0)

            # Create emergency exit action
            exit_action = TradeAction(
                action_type="sell",
                coin=position.coin,
                market_type=position.market_type,
                size=size_to_close,
                price=None,  # Market order for immediate execution
                reasoning=f"Emergency risk reduction (tripwire: {reduction_pct}% reduction)",
            )

            try:
                result = self.executor.execute_action(exit_action)
                exit_results.append(
                    {
                        "coin": exit_action.coin,
                        "size": size_to_close,
                        "success": result.success,
                        "error": result.error if not result.success else None,
                    }
                )

                self.logger.critical(
                    f"Emergency exit: {exit_action.coin} - "
                    f"{'SUCCESS' if result.success else 'FAILED'}",
                    extra={
                        "tick": self.tick_count,
                        "coin": exit_action.coin,
                        "size": size_to_close,
                        "success": result.success,
                        "error": result.error if not result.success else None,
                    },
                )

            except Exception as e:
                self.logger.critical(
                    f"Emergency exit exception for {exit_action.coin}: {e}",
                    exc_info=True,
                    extra={"tick": self.tick_count, "coin": exit_action.coin},
                )
                exit_results.append(
                    {
                        "coin": exit_action.coin,
                        "size": size_to_close,
                        "success": False,
                        "error": str(e),
                    }
                )

        # Log summary
        successful = sum(1 for r in exit_results if r["success"])
        total = len(exit_results)
        self.logger.critical(
            f"Emergency position reduction complete: {successful}/{total} successful",
            extra={"tick": self.tick_count, "results": exit_results},
        )

        return successful > 0

    def _generate_rebalance_actions(
        self,
        target_allocations_data: list[dict],
        current_allocations: dict[tuple[str, str], float],
        total_value: float,
        account_state: EnhancedAccountState,
    ) -> list[TradeAction]:
        """Generate trade actions to rebalance portfolio to target allocations.

        Args:
            target_allocations_data: List of target allocation dicts
            current_allocations: Current allocation percentages by (coin, market_type) tuple
            total_value: Total portfolio value
            account_state: Current account state with positions

        Returns:
            List of TradeAction objects to execute
        """
        actions = []
        alias_map = self._build_alias_map(account_state)

        for target_data in target_allocations_data:
            raw_coin = str(target_data["coin"])
            canonical_coin = self._resolve_canonical(raw_coin, alias_map)
            target_pct = float(target_data["target_pct"])
            market_type = str(target_data["market_type"])

            # Use tuple key to distinguish spot from perp
            allocation_key = (canonical_coin, market_type)
            current_pct = current_allocations.get(allocation_key, 0.0)
            gap_pct = target_pct - current_pct

            # Only trade if gap exceeds threshold
            if abs(gap_pct) > self.constants.ALLOCATION_GAP_THRESHOLD_PCT:
                # Calculate size needed
                target_value = (target_pct / 100) * total_value
                current_value = (current_pct / 100) * total_value
                value_gap = target_value - current_value

                # Find current price
                if canonical_coin == "USDC":
                    # USDC is the margin/collateral, not a tradeable asset - skip it
                    continue

                # Try to get price from position first, then fall back to price_map
                matching_pos = next(
                    (
                        p
                        for p in account_state.positions
                        if self._resolve_canonical(
                            p.coin, alias_map, getattr(p, "asset_identity", None)
                        )
                        == canonical_coin
                    ),
                    None,
                )
                if matching_pos:
                    current_price = matching_pos.current_price
                elif account_state.price_map and (
                    raw_coin in account_state.price_map
                    or canonical_coin in account_state.price_map
                    or (raw_coin.startswith("U") and raw_coin[1:] in account_state.price_map)
                ):
                    # Use price from watchlist for new positions
                    if raw_coin in account_state.price_map:
                        current_price = account_state.price_map[raw_coin]
                    elif canonical_coin in account_state.price_map:
                        current_price = account_state.price_map[canonical_coin]
                    else:
                        current_price = account_state.price_map.get(raw_coin[1:], 0.0)
                    self.logger.info(
                        f"Using watchlist price for {canonical_coin}: {current_price}",
                        extra={
                            "tick": self.tick_count,
                            "coin": canonical_coin,
                            "price": current_price,
                        },
                    )
                else:
                    # Final fallback: try to fetch price on-demand
                    current_price = self.monitor.get_market_price(canonical_coin)
                    if current_price:
                        self.logger.info(
                            f"Fetched on-demand price for {canonical_coin}: {current_price}",
                            extra={
                                "tick": self.tick_count,
                                "coin": canonical_coin,
                                "price": current_price,
                            },
                        )
                    else:
                        self.logger.warning(
                            f"Cannot determine price for {canonical_coin} - not in positions or watchlist",
                            extra={"tick": self.tick_count, "coin": canonical_coin},
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
                            coin=canonical_coin,
                            market_type=market_type,  # type: ignore
                            size=size,
                            price=None,  # Market order
                            reasoning=f"Rebalancing to target: {current_pct:.1f}% -> {target_pct:.1f}%",
                            asset_identity=self._resolve_identity(canonical_coin),
                            native_symbol=raw_coin,
                        )
                    )

                    self.logger.info(
                        f"Generated {action_type} action for {canonical_coin} on {market_type.upper()}: {size:.4f} (gap: {gap_pct:.1f}%)",
                        extra={
                            "tick": self.tick_count,
                            "coin": canonical_coin,
                            "market_type": market_type,
                            "action_type": action_type,
                            "size": size,
                            "current_pct": current_pct,
                            "target_pct": target_pct,
                            "gap_pct": gap_pct,
                            "allocation_key": f"{canonical_coin}/{market_type}",
                        },
                    )

        return actions

    def _build_alias_map(self, account_state: EnhancedAccountState) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        assets = getattr(account_state, "assets", {}) or {}
        for canonical, identity in assets.items():
            canonical_upper = canonical.upper()
            alias_map[canonical_upper] = canonical
            for alias in identity.all_aliases:
                if alias:
                    alias_map[alias.upper()] = canonical
            alias_map[identity.wallet_symbol.upper()] = canonical
        alias_map.setdefault("USDC", "USDC")
        return alias_map

    def _resolve_canonical(
        self,
        symbol: str,
        alias_map: dict[str, str],
        identity: AssetIdentity | None = None,
    ) -> str:
        if identity and identity.canonical_symbol:
            return identity.canonical_symbol
        if not symbol:
            return symbol
        upper = symbol.upper()
        return alias_map.get(upper, upper)

    def _resolve_identity(self, symbol: str) -> AssetIdentity | None:
        if not symbol or not self.identity_registry:
            return None

        identity = self.identity_registry.resolve(symbol)
        if identity:
            return identity

        identity = self.identity_registry.resolve_spot_symbol(symbol)
        if identity:
            return identity

        if symbol.upper().startswith("U"):
            return self.identity_registry.resolve(symbol[1:])

        return None

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
            account_state = self.monitor.get_current_state_with_signals(
                "fast", active_plan=self.governor.active_plan
            )
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
            account_state = self.monitor.get_current_state_with_signals(
                "medium", active_plan=self.governor.active_plan
            )
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

        # Plan review is permitted - query LLM for governance decision
        self.logger.info(
            "Plan review permitted - querying LLM for governance decision",
            extra={"tick": self.tick_count, "review_reason": review_msg},
        )

        # Get governance-aware decision from LLM
        decision = self.base_agent.decision_engine.get_decision_with_governance(
            account_state=account_state,
            active_plan=self.governor.active_plan,
            current_regime=self.regime_detector.current_regime,
            can_review=can_review,
        )

        if not decision.success:
            self.logger.error(
                f"Governance decision engine failed: {decision.error}",
                extra={"tick": self.tick_count, "error": decision.error},
            )
            return

        # Log LLM response
        self.logger.info(
            f"Governance decision received: maintain_plan={decision.maintain_plan}",
            extra={
                "tick": self.tick_count,
                "maintain_plan": decision.maintain_plan,
                "has_proposed_plan": decision.proposed_plan is not None,
                "has_micro_adjustments": decision.micro_adjustments is not None,
                "llm_cost_usd": decision.cost_usd,
            },
        )

        # Handle governance decision
        if decision.maintain_plan:
            self.logger.info(
                f"LLM maintaining current plan: {decision.reasoning}",
                extra={"tick": self.tick_count, "reasoning": decision.reasoning},
            )

            # Execute micro-adjustments if provided
            if decision.micro_adjustments:
                self.logger.info(
                    f"Executing {len(decision.micro_adjustments)} micro-adjustments",
                    extra={
                        "tick": self.tick_count,
                        "num_adjustments": len(decision.micro_adjustments),
                    },
                )

                for action in decision.micro_adjustments:
                    try:
                        result = self.executor.execute_action(action)
                        log_level = logging.INFO if result.success else logging.ERROR
                        self.logger.log(
                            log_level,
                            f"Micro-adjustment: {action.action_type} {action.coin} - {'success' if result.success else 'failed'}",
                            extra={
                                "tick": self.tick_count,
                                "action_type": action.action_type,
                                "coin": action.coin,
                                "success": result.success,
                                "error": result.error,
                            },
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to execute micro-adjustment: {action.action_type} {action.coin}",
                            exc_info=e,
                            extra={"tick": self.tick_count, "coin": action.coin},
                        )
        else:
            # LLM proposing a plan change
            if decision.proposed_plan:
                self.logger.info(
                    f"LLM proposing plan change: {decision.reasoning}",
                    extra={
                        "tick": self.tick_count,
                        "proposed_strategy": decision.proposed_plan.strategy_name,
                        "reasoning": decision.reasoning,
                    },
                )
                self._handle_plan_change_proposal(decision.proposed_plan, current_time)
            else:
                self.logger.warning(
                    "LLM indicated plan change but no proposed plan provided",
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
            account_state = self.monitor.get_current_state_with_signals(
                "slow", active_plan=self.governor.active_plan
            )
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

        # Calculate current allocations - key by (coin, market_type) to separate spot and perp
        current_allocations: dict[tuple[str, str], float] = {}
        total_value = account_state.portfolio_value

        alias_map = self._build_alias_map(account_state)

        for position in account_state.positions:
            position_value = position.size * position.current_price
            current_pct = (position_value / total_value * 100) if total_value > 0 else 0.0
            canonical_coin = self._resolve_canonical(
                position.coin,
                alias_map,
                getattr(position, "asset_identity", None),
            )
            allocation_key = (canonical_coin, position.market_type)
            current_allocations[allocation_key] = current_pct

        # Log current allocations for visibility
        self.logger.info(
            "Current portfolio allocations:",
            extra={
                "tick": self.tick_count,
                "total_value": total_value,
                "allocations": {
                    f"{coin}/{mkt}": f"{pct:.2f}%"
                    for (coin, mkt), pct in current_allocations.items()
                },
            },
        )

        # Log target allocations for comparison
        target_summary = {
            f"{self._resolve_canonical(str(t['coin']), alias_map)}/{t['market_type']}": f"{t['target_pct']:.2f}%"
            for t in target_allocations_data
        }
        self.logger.info(
            "Target portfolio allocations:",
            extra={"tick": self.tick_count, "targets": target_summary},
        )

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
                    result = self.executor.execute_action(action)

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

    def _select_representative_asset(
        self, account_state: EnhancedAccountState, medium: "MediumLoopSignals"
    ) -> str | None:
        """Select which coin's indicators to use for portfolio regime classification.

        Selection priority:
        1. BTC (best market regime indicator)
        2. Largest position by notional value
        3. First available coin with complete indicators
        4. None (triggers fallback to zeros)

        Args:
            account_state: Enhanced account state with positions
            medium: Medium loop signals with technical indicators

        Returns:
            Selected coin symbol or None if no valid indicators available
        """
        indicator_key_map = {coin.upper(): coin for coin in medium.technical_indicators}

        # Priority 1: BTC if available
        btc_key = indicator_key_map.get("BTC")
        if btc_key and medium.technical_indicators[btc_key] is not None:
            self.logger.debug(
                "Selected BTC as representative asset for regime classification",
                extra={"tick": self.tick_count, "selection_reason": "btc_preferred"},
            )
            return btc_key

        # Priority 2: Largest position by notional value
        if account_state.positions:
            # Find largest position
            largest_position = max(
                account_state.positions,
                key=lambda p: abs(p.size * p.current_price),
                default=None,
            )

            if largest_position:
                candidate_symbol = GovernedTradingAgent._resolve_position_symbol(
                    largest_position, candidate_keys=set(indicator_key_map.keys())
                )
            else:
                candidate_symbol = None

            if (
                largest_position
                and candidate_symbol
                and candidate_symbol in indicator_key_map
                and medium.technical_indicators[indicator_key_map[candidate_symbol]] is not None
            ):
                resolved_key = indicator_key_map[candidate_symbol]
                self.logger.debug(
                    f"Selected {resolved_key} as representative asset (largest position)",
                    extra={
                        "tick": self.tick_count,
                        "coin": largest_position.coin,
                        "notional": abs(largest_position.size * largest_position.current_price),
                        "selection_reason": "largest_position",
                    },
                )
                return resolved_key

        # Priority 3: First available coin with complete indicators
        for coin, indicators in medium.technical_indicators.items():
            if indicators is not None:
                self.logger.debug(
                    f"Selected {coin} as representative asset (first available)",
                    extra={
                        "tick": self.tick_count,
                        "coin": coin,
                        "selection_reason": "first_available",
                    },
                )
                return coin

        # Priority 4: No valid indicators available
        self.logger.warning(
            "No valid technical indicators available for any coin",
            extra={"tick": self.tick_count, "selection_reason": "none_available"},
        )
        return None

    @staticmethod
    def _resolve_position_symbol(
        position: Position | None,
        *,
        candidate_keys: set[str] | None = None,
    ) -> str | None:
        """Resolve a position's coin into a canonical symbol optionally constrained by keys."""

        if position is None or not position.coin:
            return None

        raw = position.coin.upper()
        candidates: list[str] = []

        if position.asset_identity:
            if position.asset_identity.perp_symbol:
                candidates.append(position.asset_identity.perp_symbol.upper())
            if position.asset_identity.canonical_symbol:
                candidates.append(position.asset_identity.canonical_symbol.upper())

        if position.market_type == "spot" and raw.startswith("U") and len(raw) > 1:
            candidates.append(raw[1:])

        candidates.append(raw)

        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            if candidate_keys and candidate not in candidate_keys:
                continue
            return candidate

        return None

    @staticmethod
    def _resolve_indicator_key(
        coin: str | None, indicators: dict[str, TechnicalIndicators | None]
    ) -> str | None:
        if not coin:
            return None

        target = coin.upper()
        for key in indicators:
            if key.upper() == target:
                return key
        return None

    def _validate_indicators(self, indicators: TechnicalIndicators) -> bool:
        """Validate technical indicators are within reasonable ranges.

        Args:
            indicators: Technical indicators to validate

        Returns:
            True if indicators are valid, False otherwise
        """
        return 0 <= indicators.adx <= 100 and indicators.sma_20 > 0 and indicators.sma_50 > 0

    def _extract_technical_indicators(
        self, representative_coin: str | None, medium: MediumLoopSignals
    ) -> tuple[float, float, float]:
        """Extract ADX and SMA values from technical indicators.

        Args:
            representative_coin: Selected coin for portfolio-level indicators
            medium: Medium loop signals with technical indicators

        Returns:
            (adx, sma_20, sma_50) or (0.0, 0.0, 0.0) if unavailable/invalid
        """
        resolved_key = GovernedTradingAgent._resolve_indicator_key(
            representative_coin, medium.technical_indicators
        )
        if resolved_key and resolved_key in medium.technical_indicators:
            indicators = medium.technical_indicators[resolved_key]
            if indicators and self._validate_indicators(indicators):
                self.logger.debug(
                    f"Using {resolved_key} indicators: "
                    f"ADX={indicators.adx:.1f}, "
                    f"SMA20={indicators.sma_20:.2f}, "
                    f"SMA50={indicators.sma_50:.2f}",
                    extra={
                        "tick": self.tick_count,
                        "coin": resolved_key,
                        "adx": indicators.adx,
                        "sma_20": indicators.sma_20,
                        "sma_50": indicators.sma_50,
                    },
                )
                return indicators.adx, indicators.sma_20, indicators.sma_50
            else:
                self.logger.warning(
                    f"Invalid indicators for {resolved_key}, using fallback",
                    extra={"tick": self.tick_count, "coin": resolved_key},
                )

        return 0.0, 0.0, 0.0

    def _calculate_weighted_funding_rate(
        self, account_state: EnhancedAccountState, medium: MediumLoopSignals
    ) -> float:
        """Calculate position-weighted average funding rate.

        Args:
            account_state: Enhanced account state with positions
            medium: Medium loop signals with funding basis

        Returns:
            Weighted average funding rate, or 0.0 if no data available
        """
        if not medium.funding_basis:
            self.logger.debug(
                "No funding basis data available",
                extra={"tick": self.tick_count},
            )
            return 0.0

        normalized_basis = {coin.upper(): rate for coin, rate in medium.funding_basis.items()}
        candidate_keys = set(normalized_basis.keys())

        total_weighted_funding = 0.0
        total_notional = 0.0

        for position in account_state.positions:
            normalized_coin = GovernedTradingAgent._resolve_position_symbol(
                position, candidate_keys=candidate_keys
            )
            if not normalized_coin:
                continue

            notional = abs(position.size * position.current_price)
            funding_rate = normalized_basis[normalized_coin]

            total_weighted_funding += funding_rate * notional
            total_notional += notional

        if total_notional > 0:
            avg_funding = total_weighted_funding / total_notional
            self.logger.debug(
                f"Weighted funding rate: {avg_funding:.4f} "
                f"across {len(account_state.positions)} positions",
                extra={
                    "tick": self.tick_count,
                    "avg_funding_rate": avg_funding,
                    "num_positions": len(account_state.positions),
                },
            )
            return avg_funding
        else:
            self.logger.warning(
                "No positions have funding data, using 0.0",
                extra={"tick": self.tick_count},
            )
            return 0.0

    def _calculate_average_spread_and_depth(
        self, account_state: EnhancedAccountState
    ) -> tuple[float, float]:
        """Calculate average spread and order book depth from fast signals.

        Args:
            account_state: Enhanced account state with fast signals

        Returns:
            (avg_spread_bps, avg_order_book_depth) or (0.0, 0.0) if unavailable
        """
        if account_state.fast_signals is None:
            self.logger.debug(
                "Fast signals not available",
                extra={"tick": self.tick_count},
            )
            return 0.0, 0.0

        fast = account_state.fast_signals

        # Calculate average spread
        if fast.spreads:
            avg_spread_bps = sum(fast.spreads.values()) / len(fast.spreads)
            self.logger.debug(
                f"Average spread: {avg_spread_bps:.2f} bps across {len(fast.spreads)} coins",
                extra={
                    "tick": self.tick_count,
                    "avg_spread_bps": avg_spread_bps,
                    "num_coins": len(fast.spreads),
                },
            )
        else:
            avg_spread_bps = 0.0

        # Calculate average order book depth
        if fast.order_book_depth:
            avg_order_book_depth = sum(fast.order_book_depth.values()) / len(fast.order_book_depth)
            self.logger.debug(
                f"Average order book depth: {avg_order_book_depth:.2f} "
                f"across {len(fast.order_book_depth)} coins",
                extra={
                    "tick": self.tick_count,
                    "avg_order_book_depth": avg_order_book_depth,
                    "num_coins": len(fast.order_book_depth),
                },
            )
        else:
            avg_order_book_depth = 0.0

        return avg_spread_bps, avg_order_book_depth

    def _extract_regime_signals(self, account_state: EnhancedAccountState) -> RegimeSignals:
        """Extract regime signals from enhanced account state.

        Maps relevant fields from EnhancedAccountState to RegimeSignals dataclass.
        Now includes PriceContext with multi-timeframe returns for LLM classification.

        Args:
            account_state: Enhanced account state with signals

        Returns:
            RegimeSignals for regime classification (including PriceContext)
        """
        from hyperliquid_agent.governance.regime import PriceContext

        # Extract signals from medium signals if available
        if account_state.medium_signals:
            medium = account_state.medium_signals

            # Select representative asset for technical indicators
            representative_coin = self._select_representative_asset(account_state, medium)

            # Extract technical indicators from nested structure
            adx, sma_20, sma_50 = self._extract_technical_indicators(representative_coin, medium)

            # Calculate funding rate from funding_basis dict (Phase 3)
            avg_funding = self._calculate_weighted_funding_rate(account_state, medium)

            # Calculate spreads and depth from fast_signals (Phase 4)
            avg_spread_bps, avg_order_book_depth = self._calculate_average_spread_and_depth(
                account_state
            )

            # Extract or calculate price context
            # TODO: This currently uses placeholder values - needs to be enhanced with actual
            # price history tracking in signal collectors for proper multi-timeframe returns
            price_context = self._extract_price_context(
                account_state, representative_coin, sma_20, sma_50
            )

            # Use medium signals for regime classification
            return RegimeSignals(
                # Price context (PRIMARY for LLM classification)
                price_context=price_context,
                # Trend indicators (extracted from technical_indicators dict)
                price_sma_20=sma_20,
                price_sma_50=sma_50,
                adx=adx,
                # Volatility (direct attribute on medium)
                realized_vol_24h=medium.realized_vol_24h,
                # Funding/Carry (Phase 3 - aggregated from funding_basis dict)
                avg_funding_rate=avg_funding,
                # Liquidity (Phase 4 - aggregated from fast_signals)
                bid_ask_spread_bps=avg_spread_bps,
                order_book_depth=avg_order_book_depth,
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

        # Create placeholder price context
        placeholder_price_context = PriceContext(
            current_price=0.0,
            return_1d=0.0,
            return_7d=0.0,
            return_30d=0.0,
            return_90d=0.0,
            sma20_distance=0.0,
            sma50_distance=0.0,
            higher_highs=False,
            higher_lows=False,
        )

        return RegimeSignals(
            price_context=placeholder_price_context,
            price_sma_20=0.0,
            price_sma_50=0.0,
            adx=0.0,
            realized_vol_24h=0.0,
            avg_funding_rate=0.0,
            bid_ask_spread_bps=0.0,
            order_book_depth=0.0,
        )

    def _extract_price_context(
        self,
        account_state: EnhancedAccountState,
        representative_coin: str | None,
        sma_20: float,
        sma_50: float,
    ) -> "PriceContext":
        """Extract price context with multi-timeframe returns.

        Uses real price history from signal collectors when available, otherwise
        falls back to placeholder calculations.

        Args:
            account_state: Enhanced account state
            representative_coin: Selected coin for regime analysis
            sma_20: 20-period SMA value
            sma_50: 50-period SMA value

        Returns:
            PriceContext with price returns and market structure
        """
        from hyperliquid_agent.governance.regime import PriceContext

        # Get current price from positions
        current_price = 0.0
        if representative_coin and account_state.positions:
            target_key = representative_coin.upper()
            matching_pos = None
            for position in account_state.positions:
                if GovernedTradingAgent._resolve_position_symbol(
                    position, candidate_keys={target_key}
                ):
                    matching_pos = position
                    break

            if matching_pos:
                current_price = matching_pos.current_price

        # Calculate SMA distances
        sma20_distance = 0.0
        sma50_distance = 0.0
        if current_price > 0 and sma_20 > 0:
            sma20_distance = ((current_price - sma_20) / sma_20) * 100
        if current_price > 0 and sma_50 > 0:
            sma50_distance = ((current_price - sma_50) / sma_50) * 100

        # Try to get price history from signal service
        price_history = None
        if hasattr(self.monitor, "signal_service") and representative_coin:
            try:
                # Access the orchestrator's medium collector to get price history
                orchestrator = getattr(self.monitor.signal_service, "orchestrator", None)
                if orchestrator and hasattr(orchestrator, "medium_collector"):
                    price_history = orchestrator.medium_collector.get_price_history(
                        representative_coin
                    )
            except Exception as e:
                self.logger.debug(f"Could not access price history: {e}")

        # Use real price history if available
        if price_history:
            returns = price_history.calculate_returns()
            market_structure = price_history.detect_market_structure()
            data_quality = price_history.get_data_quality()
            oldest_data = price_history.get_oldest_data_point()

            if returns:
                self.logger.debug(
                    f"Using real price history for {representative_coin}",
                    extra={
                        "tick": self.tick_count,
                        "coin": representative_coin,
                        "data_quality": data_quality,
                        "oldest_data": oldest_data,
                    },
                )
                return PriceContext(
                    current_price=current_price,
                    return_1d=returns.get("return_1d", 0.0),
                    return_7d=returns.get("return_7d", 0.0),
                    return_30d=returns.get("return_30d", 0.0),
                    return_90d=returns.get("return_90d", 0.0),
                    sma20_distance=sma20_distance,
                    sma50_distance=sma50_distance,
                    higher_highs=market_structure.get("higher_highs", False),
                    higher_lows=market_structure.get("higher_lows", False),
                    data_quality=data_quality,
                    oldest_data_point=oldest_data,
                )
            else:
                self.logger.warning(
                    f"Price history exists but returns calculation failed for {representative_coin}",
                    extra={
                        "tick": self.tick_count,
                        "coin": representative_coin,
                        "data_quality": data_quality,
                    },
                )

        # Price history not available - log warning and use placeholder
        self.logger.warning(
            f"Price history not available for {representative_coin} - regime classification will be degraded",
            extra={
                "tick": self.tick_count,
                "coin": representative_coin,
                "reason": "price_history_missing",
            },
        )

        return_proxy = sma20_distance  # Very rough approximation

        return PriceContext(
            current_price=current_price,
            return_1d=return_proxy * 0.2,  # Placeholder
            return_7d=return_proxy * 0.5,  # Placeholder
            return_30d=return_proxy,  # Placeholder
            return_90d=return_proxy * 1.5,  # Placeholder
            sma20_distance=sma20_distance,
            sma50_distance=sma50_distance,
            higher_highs=sma20_distance > 0 and sma20_distance > sma50_distance,  # Rough proxy
            higher_lows=sma20_distance > sma50_distance,  # Rough proxy
            data_quality="insufficient",
            oldest_data_point=None,
        )

    # Status methods for CLI commands

    def get_active_plan_status(self) -> dict:
        """Get current active plan status.

        Returns:
            Dictionary with active plan information
        """
        if self.governor.active_plan is None:
            return {
                "has_active_plan": False,
                "message": "No active plan",
            }

        plan = self.governor.active_plan
        current_time = datetime.now()

        # Calculate dwell time elapsed
        dwell_elapsed_minutes = 0.0
        if plan.activated_at:
            dwell_elapsed_minutes = (current_time - plan.activated_at).total_seconds() / 60

        # Calculate cooldown elapsed
        cooldown_elapsed_minutes = 0.0
        if self.governor.last_change_at:
            cooldown_elapsed_minutes = (
                current_time - self.governor.last_change_at
            ).total_seconds() / 60

        # Check if review is permitted
        can_review, review_reason = self.governor.can_review_plan(current_time)

        return {
            "has_active_plan": True,
            "plan_id": plan.plan_id,
            "strategy_name": plan.strategy_name,
            "strategy_version": plan.strategy_version,
            "objective": plan.objective,
            "status": plan.status,
            "created_at": plan.created_at.isoformat(),
            "activated_at": plan.activated_at.isoformat() if plan.activated_at else None,
            "time_horizon": plan.time_horizon,
            "target_holding_period_hours": plan.target_holding_period_hours,
            "minimum_dwell_minutes": plan.minimum_dwell_minutes,
            "dwell_elapsed_minutes": dwell_elapsed_minutes,
            "cooldown_elapsed_minutes": cooldown_elapsed_minutes,
            "can_review": can_review,
            "review_reason": review_reason,
            "rebalance_progress_pct": plan.rebalance_progress_pct,
            "target_allocations": [
                {
                    "coin": alloc.coin,
                    "target_pct": alloc.target_pct,
                    "market_type": alloc.market_type,
                    "leverage": alloc.leverage,
                }
                for alloc in plan.target_allocations
            ],
            "risk_budget": {
                "max_leverage": plan.risk_budget.max_leverage,
                "max_adverse_excursion_pct": plan.risk_budget.max_adverse_excursion_pct,
                "plan_max_drawdown_pct": plan.risk_budget.plan_max_drawdown_pct,
            },
            "compatible_regimes": plan.compatible_regimes,
            "avoid_regimes": plan.avoid_regimes,
        }

    def get_regime_status(self) -> dict:
        """Get current regime classification status.

        Returns:
            Dictionary with regime information
        """
        current_regime = self.regime_detector.current_regime
        history_length = len(self.regime_detector.regime_history)

        # Get recent regime history
        recent_regimes = []
        if self.regime_detector.regime_history:
            recent_regimes = [
                {
                    "regime": classification.regime,
                    "confidence": classification.confidence,
                    "timestamp": classification.timestamp.isoformat(),
                }
                for classification in list(self.regime_detector.regime_history)[-5:]
            ]

        # Check event lock status
        current_time = datetime.now()
        in_event_lock, event_lock_reason = self.regime_detector.is_in_event_lock_window(
            current_time
        )

        return {
            "current_regime": current_regime,
            "history_length": history_length,
            "recent_classifications": recent_regimes,
            "in_event_lock": in_event_lock,
            "event_lock_reason": event_lock_reason,
            "confirmation_cycles_required": self.regime_detector.config.confirmation_cycles_required,
            "hysteresis_enter_threshold": self.regime_detector.config.hysteresis_enter_threshold,
            "hysteresis_exit_threshold": self.regime_detector.config.hysteresis_exit_threshold,
        }

    def get_tripwire_status(self) -> dict:
        """Get current tripwire status.

        Returns:
            Dictionary with tripwire information
        """
        # Get current account state
        account_state = self.monitor.get_current_state()

        # Check all tripwires
        tripwire_events = self.tripwire_service.check_all_tripwires(
            account_state, self.governor.active_plan
        )

        # Format events
        events = [
            {
                "severity": event.severity,
                "category": event.category,
                "trigger": event.trigger,
                "action": event.action.value,
                "timestamp": event.timestamp.isoformat(),
                "details": event.details,
            }
            for event in tripwire_events
        ]

        return {
            "active_tripwires": len(tripwire_events),
            "events": events,
            "config": {
                "min_margin_ratio": self.tripwire_service.config.min_margin_ratio,
                "liquidation_proximity_threshold": self.tripwire_service.config.liquidation_proximity_threshold,
                "daily_loss_limit_pct": self.tripwire_service.config.daily_loss_limit_pct,
                "max_data_staleness_seconds": self.tripwire_service.config.max_data_staleness_seconds,
                "max_api_failure_count": self.tripwire_service.config.max_api_failure_count,
            },
            "current_state": {
                "api_failure_count": self.tripwire_service.api_failure_count,
                "daily_loss_pct": self.tripwire_service.daily_loss_pct,
                "portfolio_value": account_state.portfolio_value,
            },
        }

    def get_plan_performance_metrics(self) -> dict:
        """Get current plan performance metrics.

        Returns:
            Dictionary with performance metrics
        """
        if self.scorekeeper.active_metrics is None:
            return {
                "has_active_metrics": False,
                "message": "No active plan being tracked",
                "completed_plans_count": len(self.scorekeeper.completed_plans),
            }

        metrics = self.scorekeeper.active_metrics
        current_time = datetime.now()

        # Calculate duration
        duration_hours = (current_time - metrics.start_time).total_seconds() / 3600

        return {
            "has_active_metrics": True,
            "plan_id": metrics.plan_id,
            "start_time": metrics.start_time.isoformat(),
            "duration_hours": duration_hours,
            "total_pnl": metrics.total_pnl,
            "total_risk_taken": metrics.total_risk_taken,
            "pnl_per_unit_risk": metrics.pnl_per_unit_risk,
            "total_trades": metrics.total_trades,
            "winning_trades": metrics.winning_trades,
            "hit_rate": metrics.hit_rate,
            "avg_slippage_bps": metrics.avg_slippage_bps,
            "avg_drift_from_targets_pct": metrics.avg_drift_from_targets_pct,
            "rebalance_count": metrics.rebalance_count,
            "completed_plans_count": len(self.scorekeeper.completed_plans),
            "shadow_portfolios_count": len(self.scorekeeper.shadow_portfolios),
        }
