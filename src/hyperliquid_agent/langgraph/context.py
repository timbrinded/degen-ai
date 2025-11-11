"""Shared runtime context for LangGraph nodes.

The Phase 2 graph migrates real loop logic out of ``GovernedTradingAgent``.
To avoid re-instantiating expensive services (Hyperliquid monitor, executor,
governance subsystems, etc.) within every node we create a lightweight
runtime context that is built once per compiled graph and shared via
``functools.partial`` when nodes are registered.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from hyperliquid.info import Info

from hyperliquid_agent.config import Config, GovernanceConfig, LangGraphConfig, RiskConfig
from hyperliquid_agent.decision import DecisionEngine, PromptTemplate
from hyperliquid_agent.executor import TradeExecutor
from hyperliquid_agent.governance.governor import GovernorConfig, StrategyGovernor
from hyperliquid_agent.governance.regime import (
    RegimeDetector,
    RegimeDetectorConfig,
)
from hyperliquid_agent.governance.scorekeeper import PlanScorekeeper
from hyperliquid_agent.governance.tripwire import (
    TripwireConfig,
    TripwireService,
)
from hyperliquid_agent.identity_registry import (
    AssetIdentityRegistry,
    default_assets_config_path,
)
from hyperliquid_agent.langgraph.instrumentation import node_trace
from hyperliquid_agent.llm_client import LLMClient
from hyperliquid_agent.market_registry import MarketRegistry
from hyperliquid_agent.monitor_enhanced import EnhancedPositionMonitor
from hyperliquid_agent.price_service import AssetPriceService

LoopName = Literal["fast", "medium", "slow"]


def _build_governor_config(governance: GovernanceConfig) -> GovernorConfig:
    data = governance.governor or {}
    return GovernorConfig(
        minimum_advantage_over_cost_bps=float(data.get("minimum_advantage_over_cost_bps", 50.0)),
        cooldown_after_change_minutes=int(data.get("cooldown_after_change_minutes", 60)),
        partial_rotation_pct_per_cycle=float(data.get("partial_rotation_pct_per_cycle", 25.0)),
        state_persistence_path=str(data.get("state_persistence_path", "state/governor.json")),
    )


def _build_regime_config(governance: GovernanceConfig) -> RegimeDetectorConfig:
    data = governance.regime_detector or {}
    return RegimeDetectorConfig(
        confirmation_cycles_required=int(data.get("confirmation_cycles_required", 3)),
        hysteresis_enter_threshold=float(data.get("hysteresis_enter_threshold", 0.7)),
        hysteresis_exit_threshold=float(data.get("hysteresis_exit_threshold", 0.4)),
        event_lock_window_hours_before=int(data.get("event_lock_window_hours_before", 2)),
        event_lock_window_hours_after=int(data.get("event_lock_window_hours_after", 1)),
        llm_provider=data.get("llm_provider"),
        llm_model=data.get("llm_model"),
        llm_temperature=data.get("llm_temperature"),
    )


def _build_tripwire_config(governance: GovernanceConfig) -> TripwireConfig:
    data = governance.tripwire or {}
    return TripwireConfig(
        min_margin_ratio=float(data.get("min_margin_ratio", 0.15)),
        liquidation_proximity_threshold=float(data.get("liquidation_proximity_threshold", 0.25)),
        daily_loss_limit_pct=float(data.get("daily_loss_limit_pct", 5.0)),
        check_invalidation_triggers=bool(data.get("check_invalidation_triggers", True)),
        max_data_staleness_seconds=int(data.get("max_data_staleness_seconds", 300)),
        max_api_failure_count=int(data.get("max_api_failure_count", 3)),
    )


def _hydrate_registry(registry: MarketRegistry) -> None:
    """Hydrate the market registry synchronously."""

    async def _run():
        await registry.hydrate()

    try:
        asyncio.run(_run())
    except RuntimeError:
        # Allow re-entry when an event loop is already running (tests)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(registry.hydrate())
        loop.close()


@dataclass(slots=True)
class LoopBudget:
    """Track LLM spend per loop."""

    limit_usd: float
    spent_usd: float = 0.0

    def available(self) -> float:
        return max(0.0, self.limit_usd - self.spent_usd)

    def record(self, delta: float) -> float:
        self.spent_usd += max(0.0, delta)
        return self.spent_usd


@dataclass(slots=True)
class LLMBudgetBook:
    """Budget tracker shared across nodes."""

    fast: LoopBudget = field(default_factory=lambda: LoopBudget(limit_usd=0.25))
    medium: LoopBudget = field(default_factory=lambda: LoopBudget(limit_usd=1.25))
    slow: LoopBudget = field(default_factory=lambda: LoopBudget(limit_usd=0.75))

    def limit_for(self, loop: LoopName) -> LoopBudget:
        return getattr(self, loop)


@dataclass(slots=True)
class LangGraphRuntimeContext:
    """Container for services reused by LangGraph nodes."""

    config: Config
    langgraph_config: LangGraphConfig
    governance: GovernanceConfig
    risk: RiskConfig
    logger: logging.Logger
    info: Info
    market_registry: MarketRegistry
    identity_registry: AssetIdentityRegistry
    price_service: AssetPriceService
    monitor: EnhancedPositionMonitor
    executor: TradeExecutor
    governor: StrategyGovernor
    tripwire: TripwireService
    regime_detector: RegimeDetector
    scorekeeper: PlanScorekeeper
    llm_client: LLMClient
    prompt_template: PromptTemplate
    decision_engine: DecisionEngine
    budgets: LLMBudgetBook
    cache: dict[str, Any] = field(default_factory=dict)

    def record_llm_cost(self, loop: LoopName, cost_usd: float) -> tuple[float, float]:
        """Increment LLM budget for *loop* and return (spent, limit)."""

        ledger = self.budgets.limit_for(loop)
        return ledger.record(cost_usd), ledger.limit_usd

    def shutdown(self) -> None:
        """Free external resources (monitor signal threads, etc.)."""

        with node_trace(
            "langgraph.context.shutdown", metadata={"phase": self.langgraph_config.phase_tag}
        ):
            try:
                self.monitor.shutdown()
            except Exception:
                self.logger.exception("Failed to shutdown EnhancedPositionMonitor cleanly")

    @classmethod
    def from_config(
        cls, config: Config, *, logger: logging.Logger | None = None
    ) -> LangGraphRuntimeContext:
        if config.governance is None:
            raise ValueError("LangGraph runtime requires [governance] config")
        governance = config.governance
        langgraph_cfg = config.langgraph or LangGraphConfig()
        risk_config = config.risk
        runtime_logger = logger or logging.getLogger("hyperliquid_agent.langgraph.runtime")

        info = Info(config.hyperliquid.base_url, skip_ws=True)
        market_registry = MarketRegistry(info)
        _hydrate_registry(market_registry)

        identity_registry = AssetIdentityRegistry(default_assets_config_path(), info)
        identity_registry.load()

        price_service = AssetPriceService(info, identity_registry)
        monitor = EnhancedPositionMonitor(
            config.hyperliquid,
            identity_registry=identity_registry,
            price_service=price_service,
        )

        executor = TradeExecutor(
            config.hyperliquid,
            market_registry,
            identity_registry=identity_registry,
            risk_config=risk_config,
        )

        governor = StrategyGovernor(_build_governor_config(governance), logger=runtime_logger)
        regime_detector = RegimeDetector(
            config=_build_regime_config(governance),
            llm_config=config.llm,
            logger=runtime_logger,
        )
        tripwire = TripwireService(_build_tripwire_config(governance), logger=runtime_logger)
        scorekeeper = PlanScorekeeper(logger=runtime_logger)
        llm_client = LLMClient(config.llm, logger=runtime_logger)
        prompt_template = PromptTemplate(config.agent.prompt_template_path)
        decision_engine = DecisionEngine(
            config.llm,
            prompt_template,
            identity_registry=identity_registry,
        )

        budgets = LLMBudgetBook()

        return cls(
            config=config,
            langgraph_config=langgraph_cfg,
            governance=governance,
            risk=risk_config,
            logger=runtime_logger,
            info=info,
            market_registry=market_registry,
            identity_registry=identity_registry,
            price_service=price_service,
            monitor=monitor,
            executor=executor,
            governor=governor,
            tripwire=tripwire,
            regime_detector=regime_detector,
            scorekeeper=scorekeeper,
            llm_client=llm_client,
            prompt_template=prompt_template,
            decision_engine=decision_engine,
            budgets=budgets,
            cache={},
        )


__all__ = ["LangGraphRuntimeContext", "LLMBudgetBook", "LoopBudget", "LoopName"]
